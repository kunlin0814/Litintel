"""Tier C auto-path runner.

One function -- ``run_tier_c_for_record`` -- consumed by ``pipeline/tier1.py``
after Pass 2. Given an enriched Tier 1 record (must already carry a PMCID and
``RelevanceScore`` >= the configured threshold), this:

  1. Fetches the PMC OA PDF.
  2. Runs the three-stage Tier C engine (Evidence Map -> Synthesis -> Verification).
  3. Uploads ``<PMID>_tierC.json`` to the Tier C Drive output folder.
  4. Returns a flat dict of ``TierC_*`` fields suitable for ``record.update(...)``.

All failure modes are caught and surfaced as ``TierC_Status="failed"`` (or
``skipped_no_pdf``) -- never raises, so the pipeline keeps moving.
"""

import logging
import os
from typing import Any, Dict, Optional

from litintel.config import TierCConfig
from litintel.tierc.engine import run_all_stages
from litintel.tierc.pdf_io import load_pmc_pdf_bytes
from litintel.tierc.schema import TierCArtifact


def _summarize_verification(artifact: TierCArtifact) -> str:
    findings = artifact.verification.TopFindings or []
    if not findings:
        return "unsupported"
    statuses = [f.status for f in findings]
    if all(s == "supported" for s in statuses):
        return "all_supported"
    if any(s in ("supported", "supported_with_issues") for s in statuses):
        return "some_issues"
    return "unsupported"


def _top_findings_str(artifact: TierCArtifact, k: int = 3) -> str:
    top = artifact.synthesis.TopFindings or []
    sorted_top = sorted(top, key=lambda f: f.rank or 0)
    headlines = [f.headline for f in sorted_top[:k] if f.headline]
    return "; ".join(headlines)

logger = logging.getLogger(__name__)


def _empty_fields(status: str, source: str, error: Optional[str] = None) -> Dict[str, Any]:
    """Return a TierC_* field dict populated with sentinels."""
    out: Dict[str, Any] = {
        "TierC_Status": status,
        "TierC_Source": source,
        "TierC_DriveLink": "",
        "TierC_FigureCount": 0,
        "TierC_AnchorCount": 0,
        "TierC_MethodCount": 0,
        "TierC_TopFindings": "",
        "TierC_VerificationStatus": "",
    }
    if error:
        out["TierC_Error"] = error
    return out


def _fields_from_artifact(artifact: TierCArtifact, drive_link: str) -> Dict[str, Any]:
    return {
        "TierC_Status": "complete",
        "TierC_Source": "PMC_OA",
        "TierC_DriveLink": drive_link or "",
        "TierC_FigureCount": len(artifact.evidence_map.figures),
        "TierC_AnchorCount": len(artifact.evidence_map.anchors),
        "TierC_MethodCount": len(artifact.evidence_map.methods.BioinfoMethods),
        "TierC_TopFindings": _top_findings_str(artifact),
        "TierC_VerificationStatus": _summarize_verification(artifact),
    }


def run_tier_c_for_record(
    record: Dict[str, Any],
    tier_c_cfg: TierCConfig,
    source: str = "PMC_OA",
) -> Dict[str, Any]:
    """Run Tier C for one enriched record on the auto path.

    Args:
        record: Pipeline record carrying at minimum ``PMID``, ``PMCID``, and
            ``RelevanceScore``. The gate check (score >= threshold and PMCID
            present) is expected upstream; this function still defends against
            missing PMCID by short-circuiting with ``skipped_no_pdf``.
        tier_c_cfg: Resolved Tier C config block.
        source: ``"PMC_OA"`` (default) or ``"Manual_Inbox"``. The inbox path
            does not call this function -- it stays in ``inbox.py`` -- but the
            argument is retained for symmetry.

    Returns:
        Dict of ``TierC_*`` fields suitable for ``record.update(...)``. Never
        raises.
    """
    pmid = record.get("PMID")
    pmcid = record.get("PMCID")

    if not pmcid:
        logger.info("Tier C [auto]: PMID=%s has no PMCID; skipped_no_pdf", pmid)
        return _empty_fields("skipped_no_pdf", source, error="no PMCID")

    try:
        pdf_bytes = load_pmc_pdf_bytes(pmcid)
    except Exception as exc:
        logger.exception("Tier C [auto]: fetch_pmc_pdf raised for %s", pmcid)
        return _empty_fields("failed", source, error=f"pdf fetch raised: {exc}")
    if not pdf_bytes:
        logger.info("Tier C [auto]: no PMC OA PDF for PMCID=%s (PMID=%s)", pmcid, pmid)
        return _empty_fields("skipped_no_pdf", source, error="PMC OA unavailable")

    try:
        artifact, usage, warnings = run_all_stages(
            pdf_bytes,
            model=tier_c_cfg.model,
            thinking=tier_c_cfg.thinking,
            max_size_mb=tier_c_cfg.max_size_mb,
            chunk_pages=tier_c_cfg.chunk_pages,
            max_chunks=tier_c_cfg.max_chunks,
        )
    except Exception as exc:
        logger.exception("Tier C [auto]: engine failed for PMID=%s", pmid)
        return _empty_fields("failed", source, error=f"engine failed: {exc}")

    artifact = artifact.model_copy(update={
        "pmid": str(pmid) if pmid is not None else None,
        "doi": record.get("DOI"),
        "source": source,
    })

    drive_link = ""
    output_env = tier_c_cfg.output_folder_id_env
    output_folder_id = os.environ.get(output_env) if output_env else None
    if not output_folder_id:
        logger.warning(
            "Tier C [auto]: %s not set; artifact not uploaded to Drive (PMID=%s)",
            output_env, pmid,
        )
    else:
        try:
            from litintel.storage.drive import get_drive_service, upload_tierc_artifact

            creds_path = os.environ.get("GOOGLE_CREDENTIALS_PATH")
            service = get_drive_service(credentials_path=creds_path)
            stem = str(pmid) if pmid is not None else pmcid
            drive_link = upload_tierc_artifact(
                service=service,
                folder_id=output_folder_id,
                pmid_or_name=stem,
                artifact_dict=artifact.model_dump(),
            )
            logger.info("Tier C [auto]: uploaded artifact for PMID=%s -> %s", pmid, drive_link)
        except Exception as exc:
            logger.exception("Tier C [auto]: artifact upload failed for PMID=%s", pmid)
            fields = _fields_from_artifact(artifact, drive_link="")
            fields["TierC_Status"] = "failed"
            fields["TierC_Error"] = f"upload failed: {exc}"
            return fields

    fields = _fields_from_artifact(artifact, drive_link=drive_link)
    if warnings:
        fields["TierC_Error"] = "; ".join(warnings)
    logger.info(
        "Tier C [auto] complete: PMID=%s figs=%d anchors=%d methods=%d verify=%s",
        pmid,
        fields["TierC_FigureCount"],
        fields["TierC_AnchorCount"],
        fields["TierC_MethodCount"],
        fields["TierC_VerificationStatus"],
    )
    return fields
