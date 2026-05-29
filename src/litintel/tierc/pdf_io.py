"""PDF I/O helpers for Tier C.

Provides:
  - load_pmc_pdf_bytes: thin wrapper around pubmed.client.fetch_pmc_pdf
  - build_multimodal_parts: assemble Gemini multimodal Part list (PDF + text)
  - pdf_size_mb: report PDF size in megabytes
  - split_pdf_by_pages: chunk an oversized PDF into smaller PDFs
  - downsample_pdf_images: best-effort JPEG re-encoding to shrink a PDF
"""

import io
import logging
from typing import List, Optional

from google.genai import types

from litintel.pubmed.client import fetch_pmc_pdf

logger = logging.getLogger(__name__)


def load_pmc_pdf_bytes(pmcid: str) -> Optional[bytes]:
    """Fetch PMC OA PDF bytes for a PMCID.

    Args:
        pmcid: PMCID with or without ``PMC`` prefix.

    Returns:
        Raw PDF bytes, or None if unavailable. Failures are logged; no raise.
    """
    if not pmcid:
        logger.warning("load_pmc_pdf_bytes called with empty pmcid")
        return None
    try:
        pdf_bytes = fetch_pmc_pdf(pmcid)
    except Exception as e:
        logger.warning("fetch_pmc_pdf raised for %s: %s", pmcid, e)
        return None

    if not pdf_bytes:
        logger.info("No PMC OA PDF available for %s", pmcid)
        return None

    logger.info("Loaded %d bytes of PDF for %s", len(pdf_bytes), pmcid)
    return pdf_bytes


def build_multimodal_parts(text_prompt: str, pdf_bytes: bytes) -> List[types.Part]:
    """Build a Gemini multimodal Content parts list.

    PDF first per Gemini convention, then the text prompt.

    Args:
        text_prompt: Plain-text user prompt.
        pdf_bytes: Raw PDF content (must start with ``%PDF``).

    Returns:
        List of two ``types.Part`` -- PDF bytes followed by text.
    """
    if not pdf_bytes:
        raise ValueError("build_multimodal_parts: pdf_bytes is empty")
    if not pdf_bytes.startswith(b"%PDF"):
        raise ValueError("build_multimodal_parts: pdf_bytes does not look like a PDF")

    return [
        types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
        types.Part.from_text(text=text_prompt),
    ]


def pdf_size_mb(pdf_bytes: bytes) -> float:
    """Return PDF size in megabytes.

    Args:
        pdf_bytes: Raw PDF content.

    Returns:
        Size in MB (binary megabyte = 1024*1024 bytes).
    """
    if not pdf_bytes:
        return 0.0
    return len(pdf_bytes) / (1024.0 * 1024.0)


def split_pdf_by_pages(
    pdf_bytes: bytes,
    chunk_pages: int = 25,
    max_chunks: int = 4,
) -> List[bytes]:
    """Split a PDF into sequential page chunks.

    Args:
        pdf_bytes: Raw PDF content.
        chunk_pages: Pages per chunk.
        max_chunks: Maximum number of chunks to emit; trailing pages beyond
            ``max_chunks * chunk_pages`` are dropped.

    Returns:
        List of PDF byte blobs. If the input has <= ``chunk_pages`` pages, the
        original bytes are returned in a single-element list unchanged.
    """
    from pypdf import PdfReader, PdfWriter

    if not pdf_bytes:
        return []

    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
    except Exception as e:
        logger.warning("split_pdf_by_pages: PdfReader failed (%s); returning original", e)
        return [pdf_bytes]

    n_pages = len(reader.pages)
    if n_pages <= chunk_pages:
        return [pdf_bytes]

    chunks: List[bytes] = []
    page_idx = 0
    while page_idx < n_pages and len(chunks) < max_chunks:
        writer = PdfWriter()
        end = min(page_idx + chunk_pages, n_pages)
        for i in range(page_idx, end):
            try:
                writer.add_page(reader.pages[i])
            except Exception as e:
                logger.warning("split_pdf_by_pages: failed to add page %d: %s", i, e)
        buf = io.BytesIO()
        try:
            writer.write(buf)
        except Exception as e:
            logger.warning("split_pdf_by_pages: writer.write failed: %s", e)
            page_idx = end
            continue
        chunks.append(buf.getvalue())
        page_idx = end

    if page_idx < n_pages:
        logger.info(
            "split_pdf_by_pages: capped at %d chunks (%d pages); dropped %d trailing pages",
            max_chunks, page_idx, n_pages - page_idx,
        )
    logger.info(
        "split_pdf_by_pages: %d pages -> %d chunks (chunk_pages=%d)",
        n_pages, len(chunks), chunk_pages,
    )
    return chunks


def downsample_pdf_images(pdf_bytes: bytes, jpeg_quality: int = 60) -> bytes:
    """Best-effort JPEG re-compression of all image objects in a PDF.

    Walks every page's image objects and re-encodes them at the given JPEG
    quality. Per-image errors are logged and skipped; if the overall pass
    fails, returns the input bytes unchanged.

    Args:
        pdf_bytes: Raw PDF content.
        jpeg_quality: JPEG quality (1-95) for re-encoded images.

    Returns:
        Possibly-smaller PDF bytes; never raises.
    """
    if not pdf_bytes:
        return pdf_bytes
    try:
        from pypdf import PdfReader, PdfWriter
    except Exception as e:
        logger.warning("downsample_pdf_images: pypdf import failed: %s", e)
        return pdf_bytes

    try:
        from PIL import Image  # noqa: F401
    except Exception as e:
        logger.warning("downsample_pdf_images: PIL not available (%s); skipping", e)
        return pdf_bytes

    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        writer = PdfWriter(clone_from=reader)
    except Exception as e:
        logger.warning("downsample_pdf_images: reader/writer init failed: %s", e)
        return pdf_bytes

    touched = 0
    for page_idx, page in enumerate(writer.pages):
        try:
            images = list(getattr(page, "images", []) or [])
        except Exception as e:
            logger.warning("downsample_pdf_images: list images failed page %d: %s", page_idx, e)
            continue
        for img in images:
            try:
                img.replace(img.image, quality=jpeg_quality)
                touched += 1
            except Exception as e:
                logger.warning(
                    "downsample_pdf_images: replace failed page %d image %r: %s",
                    page_idx, getattr(img, "name", "?"), e,
                )
                continue

    if touched == 0:
        logger.info("downsample_pdf_images: no images downsampled")
        return pdf_bytes

    buf = io.BytesIO()
    try:
        writer.write(buf)
    except Exception as e:
        logger.warning("downsample_pdf_images: final write failed: %s", e)
        return pdf_bytes

    out = buf.getvalue()
    logger.info(
        "downsample_pdf_images: re-encoded %d image(s); %.2fMB -> %.2fMB",
        touched, pdf_size_mb(pdf_bytes), pdf_size_mb(out),
    )
    return out
