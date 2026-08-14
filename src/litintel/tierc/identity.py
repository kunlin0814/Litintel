"""Stage 0 identity extraction for Tier C.

Cheap page-1 multimodal call to obtain ``{title, DOI, PMID, journal, year}``
from a manual-inbox PDF, with a DOI->PMID fallback via NCBI eutils.

Used by the inbox runner to dedup against Notion before paying for the full
three-stage engine.
"""

import io
import logging
import re
from typing import Optional, Tuple

import requests
from pydantic import ValidationError

from litintel.constants import DEFAULT_GEMINI_MODEL
from litintel.enrich.ai_client import _call_gemini_multimodal, _get_gemini_client
from litintel.pubmed.client import _ncbi_params
from litintel.tierc.pdf_io import build_multimodal_parts, split_pdf_by_pages
from litintel.tierc.prompts import IDENTITY_SYSTEM, IDENTITY_USER
from litintel.tierc.schema import Identity

logger = logging.getLogger(__name__)


_EUTILS_ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"


def _first_page_pdf(pdf_bytes: bytes) -> bytes:
    """Return a 1-page PDF (page 1) to keep the identity call cheap.

    Falls back to the original bytes if pypdf cannot split (e.g. malformed PDF).
    """
    try:
        chunks = split_pdf_by_pages(pdf_bytes, chunk_pages=1, max_chunks=1)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("identity: split_pdf_by_pages failed (%s); using full PDF", exc)
        return pdf_bytes
    if not chunks:
        return pdf_bytes
    return chunks[0]


def extract_identity_from_pdf(
    pdf_bytes: bytes,
    model: str = DEFAULT_GEMINI_MODEL,
    thinking: str = "LOW",
) -> Identity:
    """Run a single multimodal call on page 1 of the PDF to extract Identity.

    Args:
        pdf_bytes: Raw PDF content.
        model: Gemini model id (Flash is plenty for page-1 extraction).
        thinking: ThinkingConfig level.

    Returns:
        Identity populated from page 1. On any ValidationError, empty
        response, or transport error, returns a default Identity().
    """
    if not pdf_bytes:
        logger.warning("extract_identity_from_pdf: empty pdf_bytes")
        return Identity()

    page1 = _first_page_pdf(pdf_bytes)
    try:
        parts = build_multimodal_parts(IDENTITY_USER, page1)
    except Exception as exc:
        logger.warning("extract_identity_from_pdf: build_multimodal_parts failed: %s", exc)
        return Identity()

    try:
        client = _get_gemini_client()
        raw, usage = _call_gemini_multimodal(
            client=client,
            model=model,
            system_prompt=IDENTITY_SYSTEM,
            parts=parts,
            schema=Identity.model_json_schema(),
            thinking_level=thinking,
        )
        logger.info(
            "Tier C [Stage 0] Identity usage: In=%s Out=%s Cached=%s Thinking=%s",
            usage.get("input"), usage.get("output"),
            usage.get("cached"), usage.get("thinking"),
        )
    except Exception as exc:
        logger.warning("extract_identity_from_pdf: Gemini call failed: %s", exc)
        return Identity()

    if not raw:
        logger.warning("extract_identity_from_pdf: empty raw response")
        return Identity()

    try:
        return Identity.model_validate(raw)
    except ValidationError as exc:
        logger.warning("extract_identity_from_pdf: validation failed: %s", exc)
        return Identity()


def _clean_doi(doi: str) -> str:
    """Strip trailing punctuation and whitespace common in extracted DOIs."""
    if not doi:
        return ""
    cleaned = doi.strip()
    # Remove common trailing punctuation
    cleaned = re.sub(r"[\.,;:\s\)\]]+$", "", cleaned)
    return cleaned


def resolve_pmid_from_doi(doi: str) -> Optional[str]:
    """Look up PMID for a DOI via NCBI eutils esearch.

    Args:
        doi: DOI string (e.g. ``10.1038/s41586-023-05989-7``). Trailing
            punctuation is stripped before query.

    Returns:
        PMID string if exactly one (or first) hit found, else None.
    """
    cleaned = _clean_doi(doi)
    if not cleaned or not cleaned.startswith("10."):
        return None

    params = _ncbi_params({
        "db": "pubmed",
        "term": f"{cleaned}[doi]",
        "retmax": 1,
        "retmode": "json",
    })
    try:
        resp = requests.get(_EUTILS_ESEARCH, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.warning("resolve_pmid_from_doi: eutils query failed for %s: %s", cleaned, exc)
        return None

    ids = data.get("esearchresult", {}).get("idlist", []) or []
    if not ids:
        logger.info("resolve_pmid_from_doi: no PMID found for DOI %s", cleaned)
        return None
    pmid = str(ids[0]).strip()
    logger.info("resolve_pmid_from_doi: DOI %s -> PMID %s", cleaned, pmid)
    return pmid or None


def _is_real(value: Optional[str]) -> bool:
    """True iff ``value`` is non-empty and not a sentinel like ``UNKNOWN``."""
    if not value:
        return False
    return value.strip().upper() not in ("UNKNOWN", "NONE", "NULL", "N/A", "")


def resolve_identity(
    pdf_bytes: bytes,
    model: str = DEFAULT_GEMINI_MODEL,
) -> Tuple[Identity, str]:
    """End-to-end identity resolution for a manual-inbox PDF.

    Order of operations:
      1. Extract page-1 identity via Gemini.
      2. If the PDF already prints a PMID on page 1, keep it.
      3. Otherwise, if a DOI was extracted, look up PMID via eutils.
      4. Otherwise return Identity with PMID=``UNKNOWN`` and source_note
         ``no_pmid``.

    Args:
        pdf_bytes: Raw PDF content.
        model: Gemini model id for the page-1 call.

    Returns:
        Tuple ``(identity, source_note)`` where ``source_note`` is one of
        ``pdf_visible`` | ``doi_resolved`` | ``no_pmid``.
    """
    identity = extract_identity_from_pdf(pdf_bytes, model=model)

    # Normalize DOI (strip trailing punctuation) on the returned object
    if _is_real(identity.DOI):
        cleaned_doi = _clean_doi(identity.DOI)
        if cleaned_doi != identity.DOI:
            identity = identity.model_copy(update={"DOI": cleaned_doi})

    if _is_real(identity.PMID) and identity.PMID.isdigit():
        return identity, "pdf_visible"

    if _is_real(identity.DOI):
        pmid = resolve_pmid_from_doi(identity.DOI)
        if pmid:
            identity = identity.model_copy(update={"PMID": pmid})
            return identity, "doi_resolved"

    # Ensure PMID is the canonical "UNKNOWN" sentinel if we couldn't resolve
    if not _is_real(identity.PMID):
        identity = identity.model_copy(update={"PMID": "UNKNOWN"})
    return identity, "no_pmid"
