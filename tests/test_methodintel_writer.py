import os
import sys
from datetime import date

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

import pytest

from litintel.methodintel.records import Citation, parse_record
from litintel.methodintel.writer import write_usage_record


def _citation():
    return Citation(first_author="Smith", journal="Nat Commun", year=2026)


def test_write_usage_record_produces_a_parseable_record(tmp_path):
    path = write_usage_record(
        tmp_path,
        concept="clustering",
        methods=["Leiden"],
        modality=["spatial_atac"],
        pmid="41234567",
        citation=_citation(),
        body="Used Leiden via ArchR for spatial ATAC clustering.",
        recorded=date(2026, 8, 2),
    )

    record = parse_record(path)
    assert record.kind == "usage"
    assert record.concept == "clustering"
    assert record.source_ref.value == "41234567"
    assert record.citation.journal == "Nat Commun"


def test_record_lands_in_the_concept_shard(tmp_path):
    path = write_usage_record(
        tmp_path, concept="clustering", methods=["Leiden"], modality=["scRNA"],
        pmid="1", citation=_citation(), body="x", recorded=date(2026, 8, 2),
    )

    assert path.parent == tmp_path / "references" / "clustering"


def test_implementations_are_recorded(tmp_path):
    path = write_usage_record(
        tmp_path, concept="clustering", methods=["Leiden"],
        implementations=["ArchR"], modality=["spatial_atac"],
        pmid="1", citation=_citation(), body="x", recorded=date(2026, 8, 2),
    )

    assert parse_record(path).implementations == ["ArchR"]


def test_one_paper_yields_one_record_per_concept(tmp_path):
    """pmid alone would collide: a study spans several concepts."""
    shared = dict(
        methods=["Leiden"], modality=["scRNA"], pmid="41234567",
        citation=_citation(), body="x", recorded=date(2026, 8, 2),
    )

    first = write_usage_record(tmp_path, concept="clustering", **shared)
    second = write_usage_record(tmp_path, concept="normalization", **shared)

    assert first != second
    assert first.exists() and second.exists()


def test_id_is_date_pmid_and_concept_so_reruns_do_not_duplicate(tmp_path):
    kwargs = dict(
        concept="clustering", methods=["Leiden"], modality=["scRNA"],
        pmid="41234567", citation=_citation(), body="x", recorded=date(2026, 8, 2),
    )

    first = write_usage_record(tmp_path, **kwargs)
    second = write_usage_record(tmp_path, **kwargs)

    assert first == second
    assert len(list((tmp_path / "references" / "clustering").glob("*.md"))) == 1


def test_existing_record_is_never_overwritten(tmp_path):
    """Layer 1 is append-only. A rerun must not rewrite history."""
    kwargs = dict(
        concept="clustering", methods=["Leiden"], modality=["scRNA"],
        pmid="41234567", citation=_citation(), recorded=date(2026, 8, 2),
    )

    path = write_usage_record(tmp_path, body="original", **kwargs)
    write_usage_record(tmp_path, body="changed", **kwargs)

    assert "original" in path.read_text()


def test_unknown_concept_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="concept"):
        write_usage_record(
            tmp_path, concept=None, methods=["Leiden"], modality=["scRNA"],
            pmid="1", citation=_citation(), body="x", recorded=date(2026, 8, 2),
        )
