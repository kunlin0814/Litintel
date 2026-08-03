"""Tests for the Tier 1 usage feed (Task 10): _emit_usage_records, its per-run
counters, and _first_author_surname.

The whole point of this feed is that a silent zero-yield must never happen
unnoticed -- an analysis name that fails to resolve to a concept, or a paper
that arrives with no comp_methods block, must be COUNTED and SURFACED, not
just skipped. These tests exercise that directly, plus the concept-shard
fan-out (one paper spanning several concepts) and the append-only /
never-overwrite guarantee at this layer.

No test writes into the real knowledge repo (tmp_path only) and no test makes
a real network call.
"""

import logging
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from litintel.methodintel.records import parse_record
from litintel.pipeline.tier1 import UsageFeedStats, _emit_usage_records, _first_author_surname


def _rec(**overrides):
    base = {
        "PMID": "41234567",
        "Authors": "Smith J, Doe A",
        "Journal": "Nat Commun",
        "Year": "2026",
        "DataTypes": "scATAC-seq, Visium",
        "comp_methods": {
            "summary_2to3_sentences": "Used Leiden via ArchR for clustering.",
            "analyses": [
                {
                    "analysis_name": "clustering",
                    "steps": [{"step": "Leiden clustering", "tool": "ArchR"}],
                },
            ],
        },
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# _first_author_surname
# ---------------------------------------------------------------------------

def test_first_author_surname_handles_semicolon_list():
    assert _first_author_surname("Smith J; Doe A") == "Smith"


def test_first_author_surname_handles_comma_list():
    assert _first_author_surname("Smith J, Doe A") == "Smith"


def test_first_author_surname_falls_back_on_empty_string():
    assert _first_author_surname("") == "unknown"


# ---------------------------------------------------------------------------
# One paper spanning several concepts -> one record per concept, distinct ids
# ---------------------------------------------------------------------------

def test_one_paper_spanning_several_concepts_yields_one_record_per_concept(tmp_path):
    rec = _rec(comp_methods={
        "summary_2to3_sentences": "Clustered with Leiden then normalized with DESeq2.",
        "analyses": [
            {"analysis_name": "clustering", "steps": [{"step": "Leiden", "tool": "ArchR"}]},
            {"analysis_name": "normalization", "steps": [{"step": "DESeq2 normalization", "tool": ""}]},
        ],
    })
    stats = UsageFeedStats()

    _emit_usage_records(tmp_path, rec, stats)

    clustering_files = list((tmp_path / "references" / "clustering").glob("*.md"))
    normalization_files = list((tmp_path / "references" / "normalization").glob("*.md"))
    assert len(clustering_files) == 1
    assert len(normalization_files) == 1
    assert clustering_files[0] != normalization_files[0]

    assert stats.analyses_seen == 2
    assert stats.analyses_resolved == 2
    assert stats.unresolved_names == []


def test_written_records_carry_the_matched_methods_and_implementations(tmp_path):
    rec = _rec()
    stats = UsageFeedStats()

    _emit_usage_records(tmp_path, rec, stats)

    path = next((tmp_path / "references" / "clustering").glob("*.md"))
    record = parse_record(path)
    assert record.methods == ["Leiden"]
    assert record.implementations == ["ArchR"]
    assert record.citation.first_author == "Smith"
    assert record.citation.journal == "Nat Commun"
    assert record.citation.year == 2026
    assert record.modality == ["scATAC-seq", "Visium"]


# ---------------------------------------------------------------------------
# Silent zero-yield case 1: unresolved analysis name is counted, not dropped
# ---------------------------------------------------------------------------

def test_unresolved_analysis_name_is_counted_and_surfaced(tmp_path, caplog):
    rec = _rec(comp_methods={
        "summary_2to3_sentences": "x",
        "analyses": [
            {"analysis_name": "some brand new stage nobody named yet", "steps": []},
        ],
    })
    stats = UsageFeedStats()

    with caplog.at_level(logging.INFO, logger="litintel.pipeline.tier1"):
        _emit_usage_records(tmp_path, rec, stats)

    assert stats.analyses_seen == 1
    assert stats.analyses_resolved == 0
    assert stats.unresolved_names == ["some brand new stage nobody named yet"]
    assert not (tmp_path / "references").exists() or not list((tmp_path / "references").rglob("*.md"))
    assert any(
        "no concept for analysis" in r.message and r.levelname == "INFO"
        for r in caplog.records
    )


# ---------------------------------------------------------------------------
# Silent zero-yield case 2: empty/missing comp_methods is counted, not raised
# ---------------------------------------------------------------------------

def test_missing_comp_methods_is_counted_not_raised(tmp_path, caplog):
    rec = _rec(comp_methods=None)
    stats = UsageFeedStats()

    with caplog.at_level(logging.INFO, logger="litintel.pipeline.tier1"):
        _emit_usage_records(tmp_path, rec, stats)

    assert stats.papers_eligible == 1
    assert stats.papers_no_comp_methods == 1
    assert stats.analyses_seen == 0
    assert not (tmp_path / "references").exists()
    assert any("no comp_methods" in r.message or "no analyses" in r.message for r in caplog.records)


def test_empty_analyses_list_is_counted_the_same_as_missing(tmp_path):
    rec = _rec(comp_methods={"summary_2to3_sentences": "", "analyses": []})
    stats = UsageFeedStats()

    _emit_usage_records(tmp_path, rec, stats)

    assert stats.papers_no_comp_methods == 1


# ---------------------------------------------------------------------------
# UsageFeedStats.log_summary is where a person finds the counts after a run
# ---------------------------------------------------------------------------

def test_log_summary_reports_resolved_and_unresolved_counts(caplog):
    stats = UsageFeedStats(
        papers_eligible=3,
        papers_no_comp_methods=1,
        analyses_seen=4,
        analyses_resolved=2,
        unresolved_names=["foo stage", "bar stage"],
    )

    with caplog.at_level(logging.INFO, logger="litintel.pipeline.tier1"):
        stats.log_summary()

    [msg] = [r.message for r in caplog.records if "methods feed" in r.message]
    assert "3" in msg and "1" in msg and "4" in msg and "2" in msg
    assert "foo stage" in msg and "bar stage" in msg


# ---------------------------------------------------------------------------
# Idempotency / append-only at the fan-out layer (rerun same paper same day)
# ---------------------------------------------------------------------------

def test_rerun_on_the_same_paper_does_not_duplicate_or_overwrite(tmp_path):
    rec = _rec()
    stats = UsageFeedStats()
    _emit_usage_records(tmp_path, rec, stats)

    path = next((tmp_path / "references" / "clustering").glob("*.md"))
    original_text = path.read_text()

    rec2 = _rec(comp_methods={
        "summary_2to3_sentences": "A different summary text on rerun.",
        "analyses": [
            {"analysis_name": "clustering", "steps": [{"step": "Leiden", "tool": "ArchR"}]},
        ],
    })
    stats2 = UsageFeedStats()
    _emit_usage_records(tmp_path, rec2, stats2)

    files = list((tmp_path / "references" / "clustering").glob("*.md"))
    assert len(files) == 1
    assert files[0].read_text() == original_text
