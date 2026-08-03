from __future__ import annotations

import re
from typing import Optional

from litintel.methodintel.schema import (
    ArtifactType,
    MethodIntelContext,
    RouterDecision,
    RouterMode,
)
from litintel.methodintel.source_plan import build_source_plan


METHOD_ALIASES: dict[str, str] = {
    "louvain": "Louvain",
    "leiden": "Leiden",
    "slm": "SLM",
    "limma": "limma",
    "deseq2": "DESeq2",
    "edger": "edgeR",
    "wilcoxon": "Wilcoxon",
    "cufflinks": "Cufflinks",
    "stringtie": "StringTie",
    "salmon": "Salmon",
    "kallisto": "kallisto",
}

IMPLEMENTATION_ALIASES: dict[str, str] = {
    "snapatac2": "SnapATAC2",
    "snapatac": "SnapATAC",
    "archr": "ArchR",
    "seurat": "Seurat",
    "scanpy": "Scanpy",
}

# Generated from dotfiles/skills/bioinfo-methods/LEXICON.md, not hand-maintained.
# Regenerate with: venv/bin/litintel methodintel sync-aliases
# Checked in rather than loaded at import time so the router keeps working with
# no knowledge base present -- Litintel must not hard-depend on dotfiles.
CONCEPT_ALIASES: dict[str, str] = {
    "cell grouping": "clustering",
    "cell-type identification": "cluster_annotation",
    "cellular neighborhoods": "neighborhood_analysis",
    "cluster annotation": "cluster_annotation",
    "clustering": "clustering",
    "clustering and annotation": "cluster_annotation",
    "community detection": "clustering",
    "dimension reduction": "dimensionality_reduction",
    "dimensionality reduction": "dimensionality_reduction",
    "gas calculation": "gene_activity_scoring",
    "gene-activity scoring": "gene_activity_scoring",
    "neighborhood analysis": "neighborhood_analysis",
    "niche identification": "neighborhood_analysis",
    "normalization": "normalization",
    "spatial co-occurrence": "neighborhood_analysis",
    "unsupervised cell type discovery": "clustering",
    "variance stabilization": "normalization",
}


STAGE_KEYWORDS: list[tuple[str, str]] = [
    ("cluster", "clustering"),
    ("cell type", "cell type annotation"),
    ("annotation", "cell type annotation"),
    ("integration", "batch correction / integration"),
    ("batch", "batch correction / integration"),
    ("differential", "differential expression / accessibility"),
    ("pseudo-bulk", "differential expression / accessibility"),
    ("pseudobulk", "differential expression / accessibility"),
    ("motif", "motif / TF activity"),
    ("trajectory", "trajectory / lineage"),
    ("velocity", "trajectory / lineage"),
    ("quantification", "alignment / quantification"),
    ("transcript assembly", "alignment / quantification"),
]


ARTIFACT_BY_MODE: dict[RouterMode, ArtifactType] = {
    RouterMode.LEARN_METHOD: ArtifactType.METHOD_CARD,
    RouterMode.COMPARE_METHODS: ArtifactType.DECISION_DOSSIER,
    RouterMode.CHOOSE_FOR_DATASET: ArtifactType.CONTEXT_RECOMMENDATION,
    RouterMode.STAGE_OVERVIEW: ArtifactType.STAGE_MAP,
    RouterMode.STALENESS_CHECK: ArtifactType.LIFECYCLE_REPORT,
}


def route_question(query: str) -> RouterDecision:
    """Route a natural-language MethodIntel question to an artifact plan."""
    normalized = query.lower()
    mode = _classify_mode(normalized)
    methods = _extract_methods(normalized)
    implementations = _extract_implementations(normalized)
    stage = _extract_stage(normalized, methods, implementations)
    context = _extract_context(normalized, implementations)
    missing_constraints = _missing_constraints(mode, context, implementations)
    verify_items = _verify_items(methods, implementations, context)

    return RouterDecision(
        query=query,
        mode=mode,
        artifact=ARTIFACT_BY_MODE[mode],
        stage=stage,
        methods=methods,
        implementations=implementations,
        context=context,
        missing_constraints=missing_constraints,
        source_plan=build_source_plan(mode),
        verify_items=verify_items,
        rationale=_rationale(mode, stage, methods, implementations),
    )


def _classify_mode(normalized: str) -> RouterMode:
    staleness_terms = ["outdated", "deprecated", "legacy", "still use", "current", "staleness"]
    if any(term in normalized for term in staleness_terms):
        return RouterMode.STALENESS_CHECK

    compare_terms = [" vs ", " versus ", "compare", "between ", "trade off", "trade-off"]
    if any(term in normalized for term in compare_terms):
        return RouterMode.COMPARE_METHODS

    choose_terms = ["should i use", "what should i use", "which should i use", "for my dataset"]
    if any(term in normalized for term in choose_terms):
        return RouterMode.CHOOSE_FOR_DATASET

    stage_terms = [
        "what methods",
        "common methods",
        "methods exist",
        "what happens",
        "pipeline stage",
        "what step",
    ]
    if any(term in normalized for term in stage_terms):
        return RouterMode.STAGE_OVERVIEW

    learn_terms = ["what is", "explain", "learn", "how does"]
    if any(term in normalized for term in learn_terms):
        return RouterMode.LEARN_METHOD

    if normalized.startswith("i have "):
        return RouterMode.CHOOSE_FOR_DATASET

    return RouterMode.CHOOSE_FOR_DATASET


def _extract_methods(normalized: str) -> list[str]:
    return _extract_aliases_in_query_order(normalized, METHOD_ALIASES)


def _extract_implementations(normalized: str) -> list[str]:
    return _extract_aliases_in_query_order(normalized, IMPLEMENTATION_ALIASES)


def _extract_aliases_in_query_order(normalized: str, aliases: dict[str, str]) -> list[str]:
    matches = []
    for alias, canonical in aliases.items():
        match = re.search(rf"\b{re.escape(alias)}\b", normalized)
        if match is not None:
            matches.append((match.start(), canonical))

    found = []
    for _, canonical in sorted(matches):
        if canonical not in found:
            found.append(canonical)
    return found


def _extract_stage(
    normalized: str,
    methods: list[str],
    implementations: list[str],
) -> Optional[str]:
    for keyword, stage in STAGE_KEYWORDS:
        if keyword in normalized:
            return stage

    if {"Louvain", "Leiden", "SLM"}.intersection(methods):
        return "clustering"
    if {"limma", "DESeq2", "edgeR", "Wilcoxon"}.intersection(methods):
        return "differential expression / accessibility"
    if {"Cufflinks", "StringTie", "Salmon", "kallisto"}.intersection(methods):
        return "alignment / quantification"
    if {"ArchR", "SnapATAC2", "SnapATAC", "Seurat", "Scanpy"}.intersection(implementations):
        if "cluster" in normalized:
            return "clustering"

    return None


def _extract_context(normalized: str, implementations: list[str]) -> MethodIntelContext:
    modality = None
    platform = None
    stack = None
    biological_goal = None
    compute_context = None
    design_context = None

    if "pseudo-bulk" in normalized or "pseudobulk" in normalized:
        modality = "pseudo-bulk"
    elif "spatial atac" in normalized:
        modality = "scATAC"
        platform = "spatial ATAC"
    elif "scatac" in normalized or "atac" in normalized:
        modality = "scATAC"
    elif "scrna" in normalized or "single-cell rna" in normalized:
        modality = "scRNA"
    elif "multiome" in normalized:
        modality = "multiome"
    elif "bulk" in normalized or "rna-seq" in normalized:
        modality = "bulk RNA-seq"

    if len(implementations) == 1:
        stack = implementations[0]

    if "substate" in normalized or "subclone" in normalized or "tumor state" in normalized:
        biological_goal = "substate/subclone discovery"
    elif "cell type" in normalized or "celltyping" in normalized or "cell typing" in normalized:
        biological_goal = "cell typing"
    elif "condition" in normalized or "differential" in normalized:
        biological_goal = "condition testing"

    if "biowulf" in normalized or "slurm" in normalized:
        compute_context = "Biowulf/SLURM"
    elif "gcp" in normalized or "cloud" in normalized:
        compute_context = "GCP/cloud"
    elif "local" in normalized:
        compute_context = "local"

    if "small sample" in normalized or "small n" in normalized:
        design_context = "small sample size"
    elif "replicate" in normalized:
        design_context = "replicated design"

    return MethodIntelContext(
        modality=modality,
        platform=platform,
        stack=stack,
        biological_goal=biological_goal,
        compute_context=compute_context,
        design_context=design_context,
    )


def _missing_constraints(
    mode: RouterMode,
    context: MethodIntelContext,
    implementations: list[str],
) -> list[str]:
    missing = []

    if mode in {RouterMode.COMPARE_METHODS, RouterMode.CHOOSE_FOR_DATASET, RouterMode.STAGE_OVERVIEW}:
        if context.modality is None:
            missing.append("modality")
        if context.biological_goal is None:
            missing.append("biological_goal")

    has_implementation_context = context.stack is not None or len(implementations) > 0
    if mode in {RouterMode.COMPARE_METHODS, RouterMode.CHOOSE_FOR_DATASET} and not has_implementation_context:
        missing.append("implementation_stack")

    if mode == RouterMode.CHOOSE_FOR_DATASET and context.compute_context is None:
        missing.append("compute_context")

    return missing


def _verify_items(
    methods: list[str],
    implementations: list[str],
    context: MethodIntelContext,
) -> list[str]:
    items = []

    if "ArchR" in implementations or context.stack == "ArchR":
        items.append("Confirm ArchR/Seurat parameter support for current installed versions.")
    if "SnapATAC2" in implementations or context.stack == "SnapATAC2":
        items.append("Confirm SnapATAC2 API and embedding export behavior against current docs.")
    if {"limma", "DESeq2", "edgeR"}.intersection(methods):
        items.append("Confirm design matrix, replicate count, and dispersion assumptions before recommending a DE method.")
    if "Cufflinks" in methods:
        items.append("Confirm current RNA-seq best-practice status and maintained successor workflows.")

    return items


def _rationale(
    mode: RouterMode,
    stage: Optional[str],
    methods: list[str],
    implementations: list[str],
) -> str:
    method_text = ", ".join(methods) if methods else "no explicit method"
    implementation_text = ", ".join(implementations) if implementations else "no explicit implementation"
    stage_text = stage or "no explicit stage"
    return (
        f"Selected {mode.value} because the query mentions {method_text} "
        f"with {implementation_text} in {stage_text} context."
    )
