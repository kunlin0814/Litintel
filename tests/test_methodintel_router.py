import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from litintel.methodintel.router import route_question
from litintel.methodintel.schema import ArtifactType, RouterMode, SourceType


def test_route_louvain_vs_leiden_archr():
    decision = route_question("Louvain vs Leiden for ArchR clustering")

    assert decision.mode == RouterMode.COMPARE_METHODS
    assert decision.artifact == ArtifactType.DECISION_DOSSIER
    assert decision.stage == "clustering"
    assert decision.methods == ["Louvain", "Leiden"]
    assert decision.implementations == ["ArchR"]
    assert decision.context.stack == "ArchR"
    assert SourceType.BENCHMARK_PAPERS in decision.source_plan
    assert SourceType.OFFICIAL_DOCS in decision.source_plan
    assert "biological_goal" in decision.missing_constraints


def test_route_cufflinks_staleness():
    decision = route_question("Is Cufflinks outdated for RNA-seq analysis?")

    assert decision.mode == RouterMode.STALENESS_CHECK
    assert decision.artifact == ArtifactType.LIFECYCLE_REPORT
    assert decision.stage == "alignment / quantification"
    assert decision.methods == ["Cufflinks"]
    assert decision.context.modality == "bulk RNA-seq"
    assert SourceType.RECENT_REVIEWS in decision.source_plan
    assert SourceType.GITHUB_REPOS in decision.source_plan


def test_route_problem_first_spatial_atac_substates():
    decision = route_question("I have spatial ATAC and want to find tumor substates.")

    assert decision.mode == RouterMode.CHOOSE_FOR_DATASET
    assert decision.artifact == ArtifactType.CONTEXT_RECOMMENDATION
    assert decision.context.modality == "scATAC"
    assert decision.context.platform == "spatial ATAC"
    assert decision.context.biological_goal == "substate/subclone discovery"
    assert "implementation_stack" in decision.missing_constraints


def test_route_stage_overview():
    decision = route_question("What clustering methods exist for scATAC?")

    assert decision.mode == RouterMode.STAGE_OVERVIEW
    assert decision.artifact == ArtifactType.STAGE_MAP
    assert decision.stage == "clustering"
    assert decision.context.modality == "scATAC"
    assert SourceType.RECENT_REVIEWS in decision.source_plan


def test_route_pseudobulk_de_comparison():
    decision = route_question("limma vs DESeq2 for pseudo-bulk with small sample size")

    assert decision.mode == RouterMode.COMPARE_METHODS
    assert decision.stage == "differential expression / accessibility"
    assert decision.methods == ["limma", "DESeq2"]
    assert decision.implementations == []
    assert decision.context.design_context == "small sample size"
    assert any("dispersion" in item for item in decision.verify_items)


def test_route_archr_vs_snapatac2_as_implementations():
    decision = route_question("Should I use ArchR clustering or SnapATAC2 for tumor substates?")

    assert decision.mode == RouterMode.CHOOSE_FOR_DATASET
    assert decision.stage == "clustering"
    assert decision.methods == []
    assert decision.implementations == ["ArchR", "SnapATAC2"]
    assert decision.context.stack is None
    assert decision.context.biological_goal == "substate/subclone discovery"
    assert "implementation_stack" not in decision.missing_constraints
