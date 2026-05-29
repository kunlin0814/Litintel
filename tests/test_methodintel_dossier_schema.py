import os
import sys
from datetime import date

import pytest
from pydantic import ValidationError

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from litintel.methodintel.schema import (
    EvidenceClaim,
    LifecycleStatus,
    MethodDecisionDossier,
    MethodGraphEdge,
    MethodOption,
    SourceRef,
    SourceRefKind,
    TradeoffDimension,
    ValidationExperiment,
)


def _pmid_source_ref() -> SourceRef:
    return SourceRef(kind=SourceRefKind.PMID, value="31178118")


def _evidence_claim() -> EvidenceClaim:
    return EvidenceClaim(
        statement="Leiden guarantees well-connected communities.",
        source_ref=_pmid_source_ref(),
    )


def _method_option() -> MethodOption:
    return MethodOption(
        name="ArchR Leiden",
        algorithm="Leiden",
        implementation="ArchR",
        version=None,
        lifecycle_status=LifecycleStatus.CURRENT,
        last_reviewed=date(2026, 5, 11),
        successor_methods=[],
        benchmark_evidence=[_evidence_claim()],
    )


def test_evidence_claim_requires_source_ref():
    with pytest.raises(ValidationError):
        EvidenceClaim(statement="Leiden is faster.")  # type: ignore[call-arg]


def test_source_ref_round_trip_json():
    ref = _pmid_source_ref()
    payload = ref.model_dump_json()
    restored = SourceRef.model_validate_json(payload)
    assert restored == ref


def test_method_option_keeps_algorithm_and_implementation_separate():
    option = _method_option()
    assert option.algorithm == "Leiden"
    assert option.implementation == "ArchR"
    assert option.benchmark_evidence[0].source_ref.kind == SourceRefKind.PMID


def test_method_option_rejects_unknown_lifecycle_status():
    with pytest.raises(ValidationError):
        MethodOption(
            name="ArchR Leiden",
            algorithm="Leiden",
            implementation="ArchR",
            lifecycle_status="emerging",  # not in the v1 enum
            last_reviewed=date(2026, 5, 11),
        )


def test_dossier_round_trip_json():
    dossier = MethodDecisionDossier(
        decision_question="ArchR Louvain vs ArchR Leiden vs SnapATAC2 transplant",
        stage="clustering",
        options=[_method_option()],
        tradeoffs=[
            TradeoffDimension(
                name="reference frame consistency",
                description="Embedding compatibility with ArchR downstream tools.",
                per_option={"ArchR Leiden": "preserved"},
            )
        ],
        validation_experiment=ValidationExperiment(
            summary="Compare cluster stability across the four options on 3 samples.",
            success_criterion="ARI >= 0.7 between ArchR Leiden and ArchR Louvain on cell typing.",
        ),
        recommendation="Adopt ArchR Leiden as the default; gate SnapATAC2 transplant on substate work.",
    )

    payload = dossier.model_dump_json()
    restored = MethodDecisionDossier.model_validate_json(payload)
    assert restored == dossier


def test_method_graph_edge_requires_known_edge_type():
    edge = MethodGraphEdge(src="Leiden", dst="Louvain", edge_type="competes_with")
    assert edge.evidence_ref is None

    with pytest.raises(ValidationError):
        MethodGraphEdge(src="Leiden", dst="Louvain", edge_type="frobnicates")
