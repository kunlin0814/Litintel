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

import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# Default minimum RelevanceScore for RAG corpus inclusion.
# Papers below this threshold are too noisy to be useful for retrieval.
DEFAULT_MIN_SCORE = 85


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
    project_id: str,
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
        project_id: GCP project ID. Set via GCP_PROJECT_ID env var.
        location: GCP region where the corpus is hosted (default: us-central1).
        min_score: Minimum RelevanceScore for RAG inclusion (default: 70).
        force_update: If True, delete + re-upload existing documents.
    """
    import vertexai
    from vertexai.preview import rag  # VERIFY: requires google-cloud-aiplatform >= 1.49.0

    if not records:
        logger.info("RAG upsert: no records to process")
        return

    # Extract location from corpus_name (projects/{project}/locations/{loc}/ragCorpora/{id})
    if not location:
        parts = corpus_name.split("/")
        if len(parts) >= 6 and parts[2] == "locations":
            location = parts[3]
        else:
            location = "us-central1"

    vertexai.init(project=project_id, location=location)

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
                rag.upload_file(
                    corpus_name=corpus_name,
                    path=str(doc_file),
                    display_name=pmid,
                    description=f"Score:{score} | {title}",
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
