"""Tier C three-stage runner.

Stages:
  1. run_evidence_map -- multimodal PDF -> EvidenceMap
  2. run_synthesis    -- EvidenceMap   -> Synthesis (text-only)
  3. run_verification -- EvidenceMap + Synthesis -> VerificationReport (text-only)

A convenience ``run_all_stages`` chains the three and returns a TierCArtifact
with aggregated usage. PMID / DOI on the artifact are left None at this layer;
the auto-path / inbox runner (Step 3) is responsible for filling them.

All three stages route through ``_call_gemini_multimodal`` for a uniform code
path: text-only stages simply pass a single text Part.
"""

import json
import logging
from typing import Dict, List, Tuple

from google.genai import types
from pydantic import ValidationError

from litintel.enrich.ai_client import _call_gemini_multimodal, _get_gemini_client
from litintel.tierc.pdf_io import (
    build_multimodal_parts,
    downsample_pdf_images,
    pdf_size_mb,
    split_pdf_by_pages,
)
from litintel.tierc.prompts import (
    EVIDENCE_MAP_SYSTEM,
    EVIDENCE_MAP_USER,
    SYNTHESIS_SYSTEM,
    SYNTHESIS_USER_TEMPLATE,
    VERIFICATION_SYSTEM,
    VERIFICATION_USER_TEMPLATE,
)
from litintel.tierc.schema import (
    Anchor,
    Biometrics,
    EvidenceMap,
    Methods,
    Synthesis,
    TierCArtifact,
    VerificationReport,
)

logger = logging.getLogger(__name__)


def _zero_usage() -> Dict[str, int]:
    return {"input": 0, "output": 0, "cached": 0, "thinking": 0}


def _add_usage(agg: Dict[str, int], new: Dict[str, int]) -> Dict[str, int]:
    for k in ("input", "output", "cached", "thinking"):
        agg[k] = agg.get(k, 0) + int(new.get(k, 0) or 0)
    return agg


def _run_evidence_map_single(
    pdf_bytes: bytes,
    model: str,
    thinking: str = "MEDIUM",
    chunk_label: str = "single",
) -> Tuple[EvidenceMap, Dict[str, int]]:
    """One Gemini multimodal call against a single (sub-)PDF.

    Args:
        pdf_bytes: Raw PDF content (must be within Gemini inline limits).
        model: Gemini model id.
        thinking: ThinkingConfig level.
        chunk_label: Human-readable tag used in log lines (e.g. "chunk 2/4").

    Returns:
        (EvidenceMap, usage dict). On schema validation failure returns a
        default EvidenceMap and logs the error.
    """
    client = _get_gemini_client()
    parts = build_multimodal_parts(EVIDENCE_MAP_USER, pdf_bytes)

    logger.info(
        "Tier C [Stage 1:%s] EvidenceMap with %s (thinking=%s)",
        chunk_label, model, thinking,
    )
    raw, usage = _call_gemini_multimodal(
        client=client,
        model=model,
        system_prompt=EVIDENCE_MAP_SYSTEM,
        parts=parts,
        schema=EvidenceMap.model_json_schema(),
        thinking_level=thinking,
    )
    logger.info(
        "Tier C [Stage 1:%s] Usage: In=%s, Out=%s, Cached=%s, Thinking=%s",
        chunk_label, usage.get("input"), usage.get("output"),
        usage.get("cached"), usage.get("thinking"),
    )

    try:
        evidence_map = EvidenceMap.model_validate(raw)
    except ValidationError as e:
        logger.error("Tier C [Stage 1:%s] EvidenceMap validation failed: %s", chunk_label, e)
        evidence_map = EvidenceMap()
    return evidence_map, usage


def merge_evidence_maps(maps: List[EvidenceMap]) -> EvidenceMap:
    """Merge EvidenceMaps from multiple chunks of the same paper.

    Merge rules:
      - identity: take from ``maps[0]``.
      - biometrics.cohorts / datasets: union preserving first-seen order.
      - figures: concat, dedup by ``id`` (first occurrence wins).
      - anchors: concat, then re-number sequentially as ``anc_001..anc_NNN``.
        ``Anchor.figure_id`` references remain valid because figures are
        deduped by ``id`` without renaming.
      - methods.BioinfoMethods: dedup by ``(method_name, tool_package)`` tuple,
        first-seen wins.
      - version: take from ``maps[0]``.

    Args:
        maps: Non-empty list of EvidenceMaps.

    Returns:
        Merged EvidenceMap. If ``maps`` is empty, returns a default EvidenceMap.
    """
    if not maps:
        return EvidenceMap()
    if len(maps) == 1:
        return maps[0]

    base = maps[0]

    # biometrics: dedup preserving order
    seen_cohorts: List[str] = []
    seen_datasets: List[str] = []
    for em in maps:
        for c in em.biometrics.cohorts:
            if c not in seen_cohorts:
                seen_cohorts.append(c)
        for d in em.biometrics.datasets:
            if d not in seen_datasets:
                seen_datasets.append(d)

    # figures: dedup by id, first-seen caption wins
    seen_fig_ids = set()
    merged_figures = []
    for em in maps:
        for fig in em.figures:
            if fig.id in seen_fig_ids:
                continue
            seen_fig_ids.add(fig.id)
            merged_figures.append(fig)

    # anchors: concat then re-number sequentially
    merged_anchors: List[Anchor] = []
    counter = 1
    for em in maps:
        for anc in em.anchors:
            new_anc = anc.model_copy(update={"id": f"anc_{counter:03d}"})
            merged_anchors.append(new_anc)
            counter += 1

    # methods: dedup by (method_name, tool_package)
    seen_methods = set()
    merged_methods = []
    for em in maps:
        for m in em.methods.BioinfoMethods:
            key = (m.method_name, m.tool_package)
            if key in seen_methods:
                continue
            seen_methods.add(key)
            merged_methods.append(m)

    return EvidenceMap(
        version=base.version,
        identity=base.identity,
        biometrics=Biometrics(cohorts=seen_cohorts, datasets=seen_datasets),
        figures=merged_figures,
        anchors=merged_anchors,
        methods=Methods(BioinfoMethods=merged_methods),
    )


def run_evidence_map(
    pdf_bytes: bytes,
    model: str,
    thinking: str = "MEDIUM",
    max_size_mb: float = 18.0,
    chunk_pages: int = 25,
    max_chunks: int = 4,
) -> Tuple[EvidenceMap, Dict[str, int], List[str]]:
    """Stage 1: multimodal PDF -> EvidenceMap, with chunk-and-merge fallback.

    Routing:
      1. If ``pdf_size_mb(pdf_bytes) <= max_size_mb`` -> single inline call.
      2. Else split into ``chunk_pages``-page chunks (capped at ``max_chunks``),
         run Stage 1 per chunk, merge results.
      3. For an oversized chunk: run ``downsample_pdf_images``; if still over
         ``max_size_mb`` append a warning and skip that chunk.

    Args:
        pdf_bytes: Raw PDF content.
        model: Gemini model id (e.g. ``gemini-3.1-pro-preview``).
        thinking: ThinkingConfig level.
        max_size_mb: Per-call inline-byte cap.
        chunk_pages: Pages per chunk when splitting.
        max_chunks: Maximum number of chunks to process.

    Returns:
        Tuple ``(EvidenceMap, aggregated_usage, warnings)``. ``warnings`` is a
        list of human-readable strings, empty when all chunks processed cleanly.
    """
    total_usage = _zero_usage()
    warnings: List[str] = []
    size_mb = pdf_size_mb(pdf_bytes)

    if size_mb <= max_size_mb:
        em, usage = _run_evidence_map_single(pdf_bytes, model=model, thinking=thinking, chunk_label="single")
        _add_usage(total_usage, usage)
        return em, total_usage, warnings

    logger.info(
        "Tier C [Stage 1] PDF %.2fMB > %.2fMB cap; splitting into %d-page chunks (max %d)",
        size_mb, max_size_mb, chunk_pages, max_chunks,
    )
    chunks = split_pdf_by_pages(pdf_bytes, chunk_pages=chunk_pages, max_chunks=max_chunks)
    # Adaptive subdivide: if the PDF has fewer pages than chunk_pages but is
    # still oversized (rare image-dense supplements), force a partition into
    # ``max_chunks`` roughly-equal pieces so per-chunk size has a chance to
    # fall below max_size_mb.
    if len(chunks) == 1 and pdf_size_mb(chunks[0]) > max_size_mb:
        try:
            import io as _io
            from pypdf import PdfReader as _Reader
            n_pages = len(_Reader(_io.BytesIO(pdf_bytes)).pages)
        except Exception:
            n_pages = chunk_pages
        if n_pages > 1:
            # Ceiling division so all pages fit within max_chunks
            # (e.g., 13 pages / 4 chunks -> 4 pages/chunk, not 3).
            adaptive = max(1, (n_pages + max_chunks - 1) // max_chunks)
            if adaptive < chunk_pages:
                logger.info(
                    "Tier C [Stage 1] adaptive subdivide: %d pages -> %d pages/chunk (covers all pages)",
                    n_pages, adaptive,
                )
                chunks = split_pdf_by_pages(pdf_bytes, chunk_pages=adaptive, max_chunks=max_chunks)
    if not chunks:
        msg = f"split_pdf_by_pages returned 0 chunks for {size_mb:.2f}MB PDF"
        logger.warning("Tier C [Stage 1] %s", msg)
        warnings.append(msg)
        return EvidenceMap(), total_usage, warnings

    maps: List[EvidenceMap] = []
    for idx, chunk in enumerate(chunks, start=1):
        label = f"chunk {idx}/{len(chunks)}"
        chunk_size = pdf_size_mb(chunk)
        if chunk_size > max_size_mb:
            logger.warning(
                "Tier C [Stage 1:%s] %.2fMB > %.2fMB; attempting image downsample",
                label, chunk_size, max_size_mb,
            )
            chunk = downsample_pdf_images(chunk)
            chunk_size = pdf_size_mb(chunk)
        if chunk_size > max_size_mb:
            msg = f"chunk {idx}/{len(chunks)} still {chunk_size:.2f}MB after downsample; skipped"
            logger.warning("Tier C [Stage 1] %s", msg)
            warnings.append(msg)
            continue

        em, usage = _run_evidence_map_single(chunk, model=model, thinking=thinking, chunk_label=label)
        _add_usage(total_usage, usage)
        maps.append(em)

    if not maps:
        warnings.append("no chunks produced an EvidenceMap")
        return EvidenceMap(), total_usage, warnings

    merged = merge_evidence_maps(maps)
    logger.info(
        "Tier C [Stage 1] merged %d chunk EvidenceMaps -> figures=%d anchors=%d methods=%d",
        len(maps), len(merged.figures), len(merged.anchors),
        len(merged.methods.BioinfoMethods),
    )
    return merged, total_usage, warnings


def run_synthesis(
    evidence_map: EvidenceMap,
    model: str,
    thinking: str = "MEDIUM",
) -> Tuple[Synthesis, Dict[str, int]]:
    """Stage 2: EvidenceMap -> Synthesis (text-only call via multimodal path)."""
    client = _get_gemini_client()
    em_json = json.dumps(evidence_map.model_dump(), ensure_ascii=True)
    user_text = SYNTHESIS_USER_TEMPLATE.format(evidence_map_json=em_json)
    parts = [types.Part.from_text(text=user_text)]

    logger.info("Tier C [Stage 2] Synthesis with %s (thinking=%s)", model, thinking)
    raw, usage = _call_gemini_multimodal(
        client=client,
        model=model,
        system_prompt=SYNTHESIS_SYSTEM,
        parts=parts,
        schema=Synthesis.model_json_schema(),
        thinking_level=thinking,
    )
    logger.info(
        "Tier C [Stage 2] Usage: In=%s, Out=%s, Cached=%s, Thinking=%s",
        usage.get("input"), usage.get("output"), usage.get("cached"), usage.get("thinking"),
    )

    try:
        synthesis = Synthesis.model_validate(raw)
    except ValidationError as e:
        logger.error("Tier C [Stage 2] Synthesis validation failed: %s", e)
        synthesis = Synthesis()
    return synthesis, usage


def run_verification(
    evidence_map: EvidenceMap,
    synthesis: Synthesis,
    model: str,
    thinking: str = "MEDIUM",
) -> Tuple[VerificationReport, Dict[str, int]]:
    """Stage 3: EvidenceMap + Synthesis -> VerificationReport (text-only)."""
    client = _get_gemini_client()
    em_json = json.dumps(evidence_map.model_dump(), ensure_ascii=True)
    syn_json = json.dumps(synthesis.model_dump(), ensure_ascii=True)
    user_text = VERIFICATION_USER_TEMPLATE.format(
        evidence_map_json=em_json,
        synthesis_json=syn_json,
    )
    parts = [types.Part.from_text(text=user_text)]

    logger.info("Tier C [Stage 3] Verification with %s (thinking=%s)", model, thinking)
    raw, usage = _call_gemini_multimodal(
        client=client,
        model=model,
        system_prompt=VERIFICATION_SYSTEM,
        parts=parts,
        schema=VerificationReport.model_json_schema(),
        thinking_level=thinking,
    )
    logger.info(
        "Tier C [Stage 3] Usage: In=%s, Out=%s, Cached=%s, Thinking=%s",
        usage.get("input"), usage.get("output"), usage.get("cached"), usage.get("thinking"),
    )

    try:
        verification = VerificationReport.model_validate(raw)
    except ValidationError as e:
        logger.error("Tier C [Stage 3] Verification validation failed: %s", e)
        verification = VerificationReport()
    return verification, usage


def run_all_stages(
    pdf_bytes: bytes,
    model: str,
    thinking: str = "MEDIUM",
    max_size_mb: float = 18.0,
    chunk_pages: int = 25,
    max_chunks: int = 4,
) -> Tuple[TierCArtifact, Dict[str, int], List[str]]:
    """Run Stages 1-3 sequentially and bundle outputs into a TierCArtifact.

    PMID / DOI fields on the returned artifact are left None; the caller
    (auto-path tier1 wiring or inbox runner) fills them.

    Stage 1 may run multiple multimodal calls if the PDF exceeds ``max_size_mb``
    -- see ``run_evidence_map``. Stages 2 and 3 always run once on the merged
    EvidenceMap. If Stage 1 yields zero figures (e.g. every chunk skipped),
    Stages 2 and 3 are short-circuited and empty placeholders are returned.

    Args:
        pdf_bytes: Raw PDF content for the paper.
        model: Gemini model id to use for all three stages.
        thinking: ThinkingConfig level passed through to each stage.
        max_size_mb: Per-call inline-byte cap forwarded to Stage 1.
        chunk_pages: Pages per chunk when Stage 1 must split.
        max_chunks: Cap on Stage 1 chunks.

    Returns:
        Tuple ``(TierCArtifact, aggregated_usage_dict, warnings_list)``.
    """
    total_usage = _zero_usage()
    warnings: List[str] = []

    evidence_map, u1, w1 = run_evidence_map(
        pdf_bytes,
        model=model,
        thinking=thinking,
        max_size_mb=max_size_mb,
        chunk_pages=chunk_pages,
        max_chunks=max_chunks,
    )
    _add_usage(total_usage, u1)
    warnings.extend(w1)

    if len(evidence_map.figures) == 0:
        msg = "EvidenceMap has zero figures; skipping Stages 2 and 3"
        logger.warning("Tier C %s", msg)
        warnings.append(msg)
        artifact = TierCArtifact(
            pmid=None,
            doi=None,
            source="PMC_OA",
            evidence_map=evidence_map,
            synthesis=Synthesis(),
            verification=VerificationReport(),
        )
        return artifact, total_usage, warnings

    synthesis, u2 = run_synthesis(evidence_map, model=model, thinking=thinking)
    _add_usage(total_usage, u2)

    verification, u3 = run_verification(evidence_map, synthesis, model=model, thinking=thinking)
    _add_usage(total_usage, u3)

    artifact = TierCArtifact(
        pmid=None,
        doi=None,
        source="PMC_OA",
        evidence_map=evidence_map,
        synthesis=synthesis,
        verification=verification,
    )
    logger.info(
        "Tier C complete. Total usage: In=%s, Out=%s, Cached=%s, Thinking=%s; warnings=%d",
        total_usage["input"], total_usage["output"], total_usage["cached"],
        total_usage["thinking"], len(warnings),
    )
    return artifact, total_usage, warnings
