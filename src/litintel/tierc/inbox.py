"""Drive inbox processing for Tier C manual-PDF path.

Workflow per PDF in ``GOOGLE_DRIVE_TIERC_INBOX_FOLDER_ID``:

  1. Download bytes.
  2. ``resolve_identity`` -> Identity + source_note.
  3. If PMID already in Notion -> move to ``inbox/skipped/``, return a
     ``TierC_Status='skipped_dedup'`` record.
  4. Else run the full three-stage engine, upload the artifact JSON, move the
     source PDF to ``inbox/processed/``, return a ``TierC_Status='complete'``
     record.

Per-file exceptions are caught and surfaced as ``TierC_Status='failed'``
records; the loop continues.
"""

import io
import logging
from typing import Any, Dict, List, Optional

from googleapiclient.http import MediaIoBaseDownload

from litintel.constants import DEFAULT_GEMINI_MODEL
from litintel.storage.drive import ensure_folder_exists, upload_tierc_artifact
from litintel.tierc.engine import run_all_stages
from litintel.tierc.identity import resolve_identity
from litintel.tierc.schema import TierCArtifact, TierCRecord

logger = logging.getLogger(__name__)


def list_inbox_pdfs(drive_service, inbox_folder_id: str) -> List[Dict[str, Any]]:
    """List PDFs directly inside ``inbox_folder_id`` (non-recursive).

    Subfolders (``processed/``, ``skipped/``) are skipped because the query
    filters on ``mimeType='application/pdf'``.

    Args:
        drive_service: Authenticated Drive service.
        inbox_folder_id: Inbox folder Drive ID.

    Returns:
        List of dicts ``{"id": str, "name": str, "size": int}``. Empty list on
        query failure.
    """
    query = (
        f"'{inbox_folder_id}' in parents "
        f"and mimeType='application/pdf' and trashed=false"
    )
    files: List[Dict[str, Any]] = []
    page_token: Optional[str] = None
    try:
        while True:
            resp = drive_service.files().list(
                q=query,
                fields="nextPageToken, files(id, name, size)",
                pageSize=100,
                includeItemsFromAllDrives=True,
                supportsAllDrives=True,
                pageToken=page_token,
            ).execute()
            for f in resp.get("files", []) or []:
                files.append({
                    "id": f.get("id"),
                    "name": f.get("name", ""),
                    "size": int(f.get("size") or 0),
                })
            page_token = resp.get("nextPageToken")
            if not page_token:
                break
    except Exception as exc:
        logger.error("list_inbox_pdfs failed: %s", exc)
        return []

    logger.info("Tier C inbox: %d PDF(s) found in folder %s", len(files), inbox_folder_id)
    return files


def download_drive_pdf(drive_service, file_id: str) -> bytes:
    """Download a PDF's raw bytes from Drive.

    Args:
        drive_service: Authenticated Drive service.
        file_id: Drive file ID.

    Returns:
        Raw PDF bytes.

    Raises:
        Exception: Propagates underlying transport / HTTP errors.
    """
    request = drive_service.files().get_media(fileId=file_id, supportsAllDrives=True)
    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return buf.getvalue()


def move_to_subfolder(
    drive_service,
    file_id: str,
    current_parent: str,
    target_subfolder_id: str,
) -> None:
    """Move a file from one Drive folder to another via parent swap."""
    drive_service.files().update(
        fileId=file_id,
        addParents=target_subfolder_id,
        removeParents=current_parent,
        fields="id, parents",
        supportsAllDrives=True,
    ).execute()


def _make_failed_record(pmid: Optional[str], doi: Optional[str], error: str) -> TierCRecord:
    return TierCRecord(
        PMID=pmid,
        DOI=doi,
        TierC_Status="failed",
        TierC_Source="Manual_Inbox",
        TierC_Error=error,
    )


from litintel.tierc.runner import _summarize_verification, _top_findings_str  # noqa: E402,F401


def process_inbox(
    drive_service,
    inbox_folder_id: str,
    notion_index: Dict[str, str],
    output_folder_id: str,
    engine_model: str,
    identity_model: str = DEFAULT_GEMINI_MODEL,
) -> List[TierCRecord]:
    """Process every PDF in the Drive inbox.

    Args:
        drive_service: Authenticated Drive service.
        inbox_folder_id: Drive folder containing user-dropped PDFs.
        notion_index: ``{PMID: page_id}`` mapping for dedup.
        output_folder_id: Drive folder to receive ``<PMID>_tierC.json``.
        engine_model: Gemini model id for the three-stage engine.
        identity_model: Cheaper Gemini model for the page-1 identity call.

    Returns:
        One TierCRecord per file processed (including skipped and failed).
    """
    files = list_inbox_pdfs(drive_service, inbox_folder_id)
    if not files:
        logger.info("Tier C inbox: nothing to process")
        return []

    # Lazily create subfolders only if we actually need them.
    processed_id: Optional[str] = None
    skipped_id: Optional[str] = None
    results: List[TierCRecord] = []

    for f in files:
        file_id = f["id"]
        name = f["name"]
        logger.info("Tier C inbox: processing %s (%s)", name, file_id)
        try:
            pdf_bytes = download_drive_pdf(drive_service, file_id)
        except Exception as exc:
            logger.error("Tier C inbox: download failed for %s: %s", name, exc)
            results.append(_make_failed_record(None, None, f"download failed: {exc}"))
            continue

        try:
            identity, source_note = resolve_identity(pdf_bytes, model=identity_model)
        except Exception as exc:
            logger.error("Tier C inbox: identity resolution failed for %s: %s", name, exc)
            results.append(_make_failed_record(None, None, f"identity failed: {exc}"))
            continue

        pmid_real = identity.PMID if (identity.PMID and identity.PMID.isdigit()) else None
        doi_real = identity.DOI if (identity.DOI and identity.DOI.upper() != "UNKNOWN") else None
        logger.info(
            "Tier C inbox: %s -> PMID=%s DOI=%s (source=%s)",
            name, pmid_real or "UNKNOWN", doi_real or "UNKNOWN", source_note,
        )

        # Dedup against Notion
        if pmid_real and pmid_real in notion_index:
            logger.info(
                "Tier C inbox: PMID %s already in Notion; moving %s to skipped/",
                pmid_real, name,
            )
            try:
                if skipped_id is None:
                    skipped_id = ensure_folder_exists(drive_service, "skipped", inbox_folder_id)
                move_to_subfolder(drive_service, file_id, inbox_folder_id, skipped_id)
            except Exception as exc:
                logger.warning("Tier C inbox: failed to move %s to skipped/: %s", name, exc)
            results.append(TierCRecord(
                PMID=pmid_real,
                DOI=doi_real,
                TierC_Status="skipped_dedup",
                TierC_Source="Manual_Inbox",
            ))
            continue

        # Run the three-stage engine
        try:
            artifact, usage, warnings = run_all_stages(pdf_bytes, model=engine_model)
        except Exception as exc:
            logger.exception("Tier C inbox: engine failed for %s", name)
            results.append(_make_failed_record(pmid_real, doi_real, f"engine failed: {exc}"))
            continue

        # Stamp PMID/DOI/source on the artifact
        artifact = artifact.model_copy(update={
            "pmid": pmid_real,
            "doi": doi_real,
            "source": "Manual_Inbox",
        })

        # Upload artifact JSON
        stem = pmid_real or name.rsplit(".", 1)[0] or "inbox"
        try:
            link = upload_tierc_artifact(
                drive_service,
                output_folder_id,
                stem,
                artifact.model_dump(),
            )
        except Exception as exc:
            logger.exception("Tier C inbox: artifact upload failed for %s", name)
            results.append(_make_failed_record(pmid_real, doi_real, f"upload failed: {exc}"))
            continue

        # Move source PDF to processed/
        try:
            if processed_id is None:
                processed_id = ensure_folder_exists(drive_service, "processed", inbox_folder_id)
            move_to_subfolder(drive_service, file_id, inbox_folder_id, processed_id)
        except Exception as exc:
            logger.warning("Tier C inbox: failed to move %s to processed/: %s", name, exc)

        rec = TierCRecord(
            PMID=pmid_real,
            DOI=doi_real,
            TierC_Status="complete",
            TierC_Source="Manual_Inbox",
            TierC_DriveLink=link or "",
            TierC_FigureCount=len(artifact.evidence_map.figures),
            TierC_AnchorCount=len(artifact.evidence_map.anchors),
            TierC_MethodCount=len(artifact.evidence_map.methods.BioinfoMethods),
            TierC_TopFindings=_top_findings_str(artifact),
            TierC_VerificationStatus=_summarize_verification(artifact),
        )
        if warnings:
            rec.TierC_Error = "; ".join(warnings)
        results.append(rec)
        logger.info(
            "Tier C inbox: %s complete. figs=%d anchors=%d methods=%d verify=%s",
            name, rec.TierC_FigureCount, rec.TierC_AnchorCount,
            rec.TierC_MethodCount, rec.TierC_VerificationStatus,
        )

    return results
