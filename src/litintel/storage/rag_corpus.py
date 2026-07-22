"""
#================================================================
# Module: rag_corpus.py
# Purpose: Upsert enriched Tier1Records into Vertex AI RAG Engine corpus
# Input:   List of Tier1Record dicts from the LitIntel pipeline
# Output:  Indexed documents in a Vertex AI RAG corpus for semantic retrieval
# Dependencies: google-cloud-aiplatform >= 1.49.0
#               pip install google-cloud-aiplatform
# Provenance: Python 3.11 / vertexai.preview.rag
# Date: 2026-03-28
# Context: LitIntel storage backend -- called at end of tier1.py pipeline
#================================================================
"""

import json
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Scope required for every Vertex AI / RAG call.
_CLOUD_PLATFORM_SCOPE = "https://www.googleapis.com/auth/cloud-platform"

# Default minimum RelevanceScore for RAG corpus inclusion.
# Papers below this threshold are too noisy to be useful for retrieval.
DEFAULT_MIN_SCORE = 85

# Uploads go through _upload_file_rest() rather than
# vertexai.preview.rag.upload_file(), which is broken for this deployment in
# two independent ways (both confirmed against the live API 2026-07-22):
#   1. It calls google.auth.default() internally, ignoring the credentials
#      handed to vertexai.init(). With the corpus in a personal project and
#      the shell authenticated to the company project, every upload returned
#      403 IAM_PERMISSION_DENIED on aiplatform.ragFiles.upload.
#   2. It posts to /upload/v1beta1/, which stalls and then dies with
#      RemoteDisconnected after ~60s. The same multipart POST to /upload/v1/
#      returns 200 in 7-30s.
# It also has no request timeout and no retry. A dropped upload is permanent:
# the paper is already in Notion, so the next run dedups it out of the PubMed
# search and never re-offers it to the corpus.
_UPLOAD_MAX_RETRIES = 3
_UPLOAD_TIMEOUT_SECONDS = 180


# ===========================================================================
# Project / credential resolution
#
# The RAG corpus and Gemini inference deliberately live in DIFFERENT GCP
# projects: Gemini runs on the company project (GCP_PROJECT_ID + ambient ADC)
# while the corpus lives in a personal project. So RAG must never read
# GCP_PROJECT_ID and must never rely on the ambient credential -- it derives
# its project from the corpus resource name and authenticates with the key in
# RAG_CREDENTIALS_JSON.
# ===========================================================================

def parse_corpus_name(corpus_name: str) -> Tuple[str, str]:
    """Split a RAG corpus resource name into (project_id, location).

    Args:
        corpus_name: projects/{project}/locations/{loc}/ragCorpora/{id}

    Returns:
        (project_id, location) parsed from the name.

    Raises:
        ValueError: The name does not match the expected resource format.
            Guessing a project here would silently target the wrong account,
            so a malformed name is fatal.
    """
    parts = corpus_name.split("/")
    if len(parts) < 6 or parts[0] != "projects" or parts[2] != "locations":
        raise ValueError(
            "VERTEX_RAG_CORPUS_NAME is malformed: %r. Expected "
            "projects/{project}/locations/{location}/ragCorpora/{id}"
            % corpus_name
        )
    return parts[1], parts[3]


def rag_credentials():
    """Return explicit credentials for the RAG project, or None for ADC.

    RAG_CREDENTIALS_JSON points at a service-account key for the project that
    owns the corpus. When unset, the ambient ADC is used -- correct only when
    the corpus lives in the same project the shell is authenticated against.

    Raises:
        FileNotFoundError: RAG_CREDENTIALS_JSON is set but does not exist.
    """
    key_path = os.environ.get("RAG_CREDENTIALS_JSON")
    if not key_path:
        return None
    if not os.path.exists(key_path):
        raise FileNotFoundError(
            "RAG_CREDENTIALS_JSON points at a missing file: %s" % key_path
        )
    from google.oauth2 import service_account

    return service_account.Credentials.from_service_account_file(
        key_path, scopes=[_CLOUD_PLATFORM_SCOPE]
    )


def init_rag(corpus_name: str, location: Optional[str] = None) -> Tuple[str, str]:
    """Point the vertexai global config at the corpus's own project + credential.

    Args:
        corpus_name: Full RAG corpus resource name.
        location: Override for the region; defaults to the one in the name.

    Returns:
        (project_id, location) that were applied.
    """
    import vertexai

    project_id, parsed_location = parse_corpus_name(corpus_name)
    location = location or parsed_location
    creds = rag_credentials()
    vertexai.init(project=project_id, location=location, credentials=creds)
    logger.info(
        "RAG target: project=%s location=%s (credential: %s)",
        project_id,
        location,
        "RAG_CREDENTIALS_JSON" if creds else "ambient ADC",
    )
    return project_id, location


# ===========================================================================
# Helpers
# ===========================================================================

def _get_comp_methods_summary(comp: Any) -> str:
    """Extract summary text from comp_methods field (dict or Pydantic model).

    Args:
        comp: comp_methods value from a Tier1Record -- may be dict, Pydantic
              model, or None.

    Returns:
        Summary string, or empty string if unavailable.
    """
    if comp is None:
        return ""
    if isinstance(comp, dict):
        return comp.get("summary_2to3_sentences", "")
    # Pydantic model
    return getattr(comp, "summary_2to3_sentences", "")


def _format_rag_document(rec: Dict[str, Any]) -> str:
    """Format a Tier1Record dict as a structured plain-text document.

    Layout ensures both structured metadata fields (for keyword/filter
    retrieval) and free-text semantic fields (abstract, summary, findings)
    are co-located in a single retrievable chunk.

    Args:
        rec: Tier1Record dict from the pipeline.

    Returns:
        Formatted UTF-8 plain text string ready for RAG upload.
    """
    pmid = rec.get("PMID", "")
    doi = rec.get("DOI", "")
    title = rec.get("Title", "")
    authors = rec.get("Authors", "")
    journal = rec.get("Journal", "")
    year = rec.get("Year", "")
    pub_date = rec.get("PubDate", "")
    score = rec.get("RelevanceScore", 0)
    confidence = rec.get("PipelineConfidence", "")
    evidence_level = rec.get("AI_EvidenceLevel", "")
    data_types = rec.get("DataTypes", "")
    theme = rec.get("Theme", "")
    geo = rec.get("GEO_Validated", "")
    sra = rec.get("SRA_Validated", "")

    abstract = rec.get("Abstract", "")
    why_relevant = rec.get("WhyRelevant", "")
    study_summary = rec.get("StudySummary", "")
    paper_role = rec.get("PaperRole", "")
    key_findings = rec.get("KeyFindings", "")
    methods = rec.get("Methods", "")
    why_care = rec.get("WhyYouMightCare", "")
    comp_summary = _get_comp_methods_summary(rec.get("comp_methods"))

    lines = [
        "=== PAPER METADATA ===",
        f"PMID: {pmid}",
        f"DOI: {doi}",
        f"Title: {title}",
        f"Authors: {authors}",
        f"Journal: {journal} ({year})",
        f"Published: {pub_date}",
        f"RelevanceScore: {score}",
        f"PipelineConfidence: {confidence}",
        f"EvidenceLevel: {evidence_level}",
        f"DataTypes: {data_types}",
        f"Theme: {theme}",
    ]

    if geo:
        lines.append(f"GEO_Datasets: {geo}")
    if sra:
        lines.append(f"SRA_Datasets: {sra}")

    lines += [
        "",
        "=== ABSTRACT ===",
        abstract,
        "",
        "=== WHY RELEVANT ===",
        why_relevant,
        "",
        "=== STUDY SUMMARY ===",
        study_summary,
        "",
        "=== PAPER ROLE ===",
        paper_role,
        "",
        "=== KEY FINDINGS ===",
        key_findings,
        "",
        "=== METHODS ===",
        methods,
        "",
        "=== WHY YOU MIGHT CARE ===",
        why_care,
    ]

    if comp_summary:
        lines += [
            "",
            "=== COMPUTATIONAL METHODS SUMMARY ===",
            comp_summary,
        ]

    return "\n".join(lines)


def _upload_file_rest(
    corpus_name: str,
    path: str,
    display_name: str,
    description: str,
    credentials=None,
    timeout: int = _UPLOAD_TIMEOUT_SECONDS,
) -> Dict[str, Any]:
    """Upload one file to a RAG corpus with a direct multipart POST.

    This deliberately bypasses vertexai.preview.rag.upload_file(), which has
    two defects that make it unusable here (see _UPLOAD_TIMEOUT_SECONDS note):
    it calls google.auth.default() directly -- discarding the credentials given
    to vertexai.init() -- and it posts to /upload/v1beta1/.

    Returns:
        The decoded ragFile resource dict.

    Raises:
        RuntimeError: Non-2xx response, carrying the server's error body.
    """
    import google.auth.transport.requests as google_auth_requests
    import requests

    project_id, location = parse_corpus_name(corpus_name)
    if credentials is None:
        import google.auth

        credentials, _ = google.auth.default(scopes=[_CLOUD_PLATFORM_SCOPE])
    credentials.refresh(google_auth_requests.Request())

    url = "https://{}-aiplatform.googleapis.com/upload/v1/{}/ragFiles:upload".format(
        location, corpus_name
    )
    metadata = {"rag_file": {"display_name": display_name}}
    if description:
        metadata["rag_file"]["description"] = description

    with open(path, "rb") as fh:
        response = requests.post(
            url,
            headers={
                "Authorization": "Bearer %s" % credentials.token,
                "X-Goog-Upload-Protocol": "multipart",
            },
            files={
                "metadata": (None, json.dumps(metadata), "application/json; charset=UTF-8"),
                "file": (os.path.basename(path), fh, "text/plain"),
            },
            timeout=timeout,
        )

    if response.status_code != 200:
        raise RuntimeError(
            "RAG upload failed with HTTP %d: %s"
            % (response.status_code, response.text[:500])
        )
    body = response.json()
    if body.get("error"):
        raise RuntimeError("RAG upload returned an error: %s" % body["error"])
    return body.get("ragFile", body)


def _upload_file_with_retry(
    corpus_name: str,
    path: str,
    display_name: str,
    description: str,
    credentials=None,
    max_retries: int = _UPLOAD_MAX_RETRIES,
):
    """Upload with exponential backoff on transient failures.

    Raises the last exception if every attempt fails, so the caller still
    counts it as an error rather than silently dropping the document.
    """
    for attempt in range(max_retries + 1):
        try:
            return _upload_file_rest(
                corpus_name=corpus_name,
                path=path,
                display_name=display_name,
                description=description,
                credentials=credentials,
            )
        except Exception as exc:
            if attempt >= max_retries:
                raise
            wait = 2 ** attempt  # 1s, 2s, 4s
            logger.warning(
                "RAG upload failed for %s (attempt %d/%d) -- retrying in %ds: %s",
                display_name, attempt + 1, max_retries, wait, exc,
            )
            time.sleep(wait)


def _build_corpus_index(corpus_name: str) -> Dict[str, str]:
    """List existing files in a RAG corpus and map display_name -> resource name.

    Used to detect already-uploaded documents before each run,
    enabling INCREMENTAL upsert behavior (skip existing, update on demand).

    Args:
        corpus_name: Full resource name of the RAG corpus.
            Format: projects/{project}/locations/{loc}/ragCorpora/{id}

    Returns:
        Dict mapping display_name (PMID string) -> file resource name.
        Returns empty dict on failure so the caller can continue.
    """
    from vertexai.preview import rag  # VERIFY: requires google-cloud-aiplatform >= 1.49.0

    index: Dict[str, str] = {}
    try:
        files = rag.list_files(corpus_name=corpus_name)
        for f in files:
            if f.display_name:
                index[f.display_name] = f.name
        logger.info("RAG corpus index: %d existing documents found", len(index))
    except Exception:
        logger.exception("Failed to build RAG corpus index -- treating corpus as empty")
    return index


# ===========================================================================
# Public entry point
# ===========================================================================

def upsert_to_rag_corpus(
    records: List[Dict[str, Any]],
    corpus_name: str,
    project_id: str = None,
    location: str = None,
    min_score: int = DEFAULT_MIN_SCORE,
    force_update: bool = False,
) -> None:
    """Upsert enriched Tier1Records into a Vertex AI RAG Engine corpus.

    Behavior:
    - Only records with RelevanceScore >= min_score are ingested.
    - Documents are matched by PMID (stored as display_name on the RAG file).
    - By default (force_update=False): existing PMIDs are skipped (INCREMENTAL).
    - With force_update=True: existing documents are deleted and re-uploaded.

    Called from tier1.py after Notion and Drive sync -- see integration note
    at the bottom of this file.

    Args:
        records: List of enriched Tier1Record dicts from the pipeline.
        corpus_name: Full RAG corpus resource name.
            Format: projects/{project}/locations/{loc}/ragCorpora/{id}
            Set via VERTEX_RAG_CORPUS_NAME environment variable.
        project_id: Ignored. The project is read from corpus_name so RAG stays
            on its own account regardless of GCP_PROJECT_ID (which targets the
            company project used for Gemini). Accepted only for call
            compatibility.
        location: GCP region override; defaults to the one in corpus_name.
        min_score: Minimum RelevanceScore for RAG inclusion (default: 85).
        force_update: If True, delete + re-upload existing documents.
    """
    from vertexai.preview import rag  # VERIFY: requires google-cloud-aiplatform >= 1.49.0

    if not records:
        logger.info("RAG upsert: no records to process")
        return

    rag_project, location = init_rag(corpus_name, location)
    if project_id and project_id != rag_project:
        logger.info(
            "Ignoring project_id=%s -- the RAG corpus lives in %s. Gemini and "
            "RAG deliberately use different projects.",
            project_id, rag_project,
        )
    credentials = rag_credentials()

    # Filter to records meeting quality threshold
    eligible = [r for r in records if r.get("RelevanceScore", 0) >= min_score]
    skipped_low_score = len(records) - len(eligible)
    logger.info(
        "RAG upsert: %d eligible (score >= %d), %d below threshold -- skipped",
        len(eligible),
        min_score,
        skipped_low_score,
    )

    if not eligible:
        logger.info("RAG upsert: no records meet min_score=%d -- nothing to do", min_score)
        return

    # Build dedup index: PMID -> existing file resource name
    existing_index = _build_corpus_index(corpus_name)

    uploaded = 0
    updated = 0
    skipped = 0
    errors = 0

    # Write each paper to a temp file and upload.
    # TemporaryDirectory is used so all temp files are cleaned up on exit,
    # even if an exception is raised mid-loop.
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        for rec in eligible:
            pmid = rec.get("PMID", "")
            score = rec.get("RelevanceScore", 0)
            title = rec.get("Title", "")[:60]

            if not pmid:
                logger.warning("Record missing PMID -- skipping: '%s'", title)
                errors += 1
                continue

            # Handle existing document
            if pmid in existing_index:
                if not force_update:
                    logger.debug("PMID %s already in corpus -- skipping", pmid)
                    skipped += 1
                    continue

                # force_update: delete existing before re-uploading
                try:
                    rag.delete_file(name=existing_index[pmid])
                    logger.debug("Deleted existing RAG file for PMID %s", pmid)
                except Exception:
                    logger.exception(
                        "Failed to delete existing RAG file for PMID %s -- skipping update",
                        pmid,
                    )
                    errors += 1
                    continue

            # Format document and write to temp file
            doc_text = _format_rag_document(rec)
            doc_file = tmp_path / f"{pmid}.txt"
            doc_file.write_text(doc_text, encoding="utf-8")

            # Upload to RAG corpus
            try:
                _upload_file_with_retry(
                    corpus_name=corpus_name,
                    path=str(doc_file),
                    display_name=pmid,
                    description=f"Score:{score} | {title}",
                    credentials=credentials,
                )
                if pmid in existing_index:
                    logger.info("Updated  RAG doc: PMID %s (score=%d)", pmid, score)
                    updated += 1
                else:
                    logger.info("Uploaded RAG doc: PMID %s (score=%d)", pmid, score)
                    uploaded += 1
            except Exception as e:
                logger.error("Failed to upload RAG doc for PMID %s: %s", pmid, e)
                errors += 1

    logger.info(
        "RAG upsert complete: %d uploaded, %d updated, %d skipped (existing), %d errors",
        uploaded,
        updated,
        skipped,
        errors,
    )
    if errors:
        # Loud on purpose: these papers are already in Notion, so the pipeline
        # will dedup them out of future runs and never retry them here.
        # Recover with scripts/backfill_rag_from_notion.py.
        logger.warning(
            "RAG upsert: %d document(s) failed after %d retries and are NOT in the "
            "corpus. They will not be retried automatically -- run "
            "scripts/backfill_rag_from_notion.py to recover them.",
            errors, _UPLOAD_MAX_RETRIES,
        )


#================================================================
# Integration: tier1.py patch
#
# Add these lines to run_tier1_pipeline() in tier1.py, after the
# Drive sync block (line ~313), before append_run_log():
#
#     # RAG Corpus Sync (if enabled)
#     corpus_name = os.environ.get("VERTEX_RAG_CORPUS_NAME")
#     if corpus_name:
#         project_id = os.environ.get("GCP_PROJECT_ID")
#         if project_id:
#             try:
#                 from litintel.storage.rag_corpus import upsert_to_rag_corpus
#                 logger.info("Syncing to Vertex AI RAG corpus...")
#                 upsert_to_rag_corpus(
#                     records=valid_records,
#                     corpus_name=corpus_name,
#                     project_id=project_id,
#                 )
#             except Exception as e:
#                 logger.error(f"RAG corpus sync failed: {e}")
#         else:
#             logger.warning("GCP_PROJECT_ID not set -- skipping RAG sync")
#
# Required .env additions:
#     VERTEX_RAG_CORPUS_NAME=projects/YOUR_PROJECT/locations/us-central1/ragCorpora/YOUR_CORPUS_ID
#     GCP_PROJECT_ID=YOUR_PROJECT_ID
#
# One-time corpus creation (run once before first pipeline run):
#     import vertexai
#     from vertexai.preview import rag
#     vertexai.init(project="YOUR_PROJECT_ID", location="us-central1")
#     corpus = rag.create_corpus(display_name="litintel-papers")
#     print(corpus.name)  # copy this into VERTEX_RAG_CORPUS_NAME
#================================================================

#================================================================
# QC Checkpoint
# - After first run: check corpus file count in GCP Console
#   -> Vertex AI -> RAG Engine -> your corpus -> Files tab
# - Verify PMID appears as display_name on uploaded files
# - Test retrieval with a sample query via ADK agent or SDK:
#     from vertexai.preview import rag
#     response = rag.retrieval_query(
#         rag_resources=[rag.RagResource(rag_corpus=corpus_name)],
#         text="CTCF binding prostate cancer spatial ATAC",
#         similarity_top_k=5,
#     )
# - Expected: relevant paper chunks returned with PMID in content
# - Edge case: papers with comp_methods=None -- handled (empty section skipped)
# - Edge case: PMID missing -- logged as error, pipeline continues
#================================================================
