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
# Task 11 fix round 1: analysis_name misses, tags fallback hits
# ---------------------------------------------------------------------------

def test_analysis_name_miss_resolves_via_tags_fallback(tmp_path, caplog):
    """analysis_name is free-form and misses CONCEPT_ALIASES entirely, but
    the paper's controlled-vocabulary `tags` carries a value that matches --
    this must count as RESOLVED, not unresolved, and must actually write a
    record (proving the fallback, not just the counter, works)."""
    rec = _rec(comp_methods={
        "summary_2to3_sentences": "Used Leiden via ArchR for clustering.",
        "tags": ["deconvolution", "clustering"],
        "analyses": [
            {
                "analysis_name": "Single-cell preprocessing and integration",
                "steps": [{"step": "Leiden clustering", "tool": "ArchR"}],
            },
        ],
    })
    stats = UsageFeedStats()

    with caplog.at_level(logging.INFO, logger="litintel.pipeline.tier1"):
        _emit_usage_records(tmp_path, rec, stats)

    assert stats.analyses_seen == 1
    assert stats.analyses_resolved == 1
    assert stats.unresolved_names == []
    written = list((tmp_path / "references" / "clustering").glob("*.md"))
    assert len(written) == 1
    assert any(
        "resolved via tag" in r.message and r.levelname == "INFO"
        for r in caplog.records
    )


# ---------------------------------------------------------------------------
# Task 11 fix round 2: the tags fallback must refuse to guess when ambiguous
# ---------------------------------------------------------------------------

def test_two_unresolved_blocks_with_one_tag_concept_stay_unresolved(tmp_path, caplog):
    """`tags` is paper-level, shared across every block. If TWO blocks both
    miss analysis_name, a single tag-derived concept cannot be attributed to
    either one safely -- both must stay unresolved, nothing gets written, and
    the ambiguity is logged distinctly from a plain no-match."""
    rec = _rec(comp_methods={
        "summary_2to3_sentences": "x",
        "tags": ["clustering"],
        "analyses": [
            {"analysis_name": "CNV inference and validation", "steps": []},
            {"analysis_name": "Single-cell preprocessing and integration", "steps": []},
        ],
    })
    stats = UsageFeedStats()

    with caplog.at_level(logging.INFO, logger="litintel.pipeline.tier1"):
        _emit_usage_records(tmp_path, rec, stats)

    assert stats.analyses_seen == 2
    assert stats.analyses_resolved == 0
    assert sorted(stats.unresolved_names) == sorted([
        "CNV inference and validation",
        "Single-cell preprocessing and integration",
    ])
    assert not (tmp_path / "references").exists() or not list((tmp_path / "references").rglob("*.md"))
    assert any(
        "ambiguous tag fallback" in r.message and r.levelname == "INFO"
        for r in caplog.records
    )


def test_tags_naming_two_concepts_stays_unresolved(tmp_path, caplog):
    """A single unresolved block is not enough on its own -- if the paper's
    `tags` name TWO known concepts, which one the block actually is about is
    unknowable, so it must stay unresolved rather than guess either one."""
    rec = _rec(comp_methods={
        "summary_2to3_sentences": "x",
        "tags": ["clustering", "normalization"],
        "analyses": [
            {"analysis_name": "Single-cell preprocessing and integration", "steps": []},
        ],
    })
    stats = UsageFeedStats()

    with caplog.at_level(logging.INFO, logger="litintel.pipeline.tier1"):
        _emit_usage_records(tmp_path, rec, stats)

    assert stats.analyses_seen == 1
    assert stats.analyses_resolved == 0
    assert stats.unresolved_names == ["Single-cell preprocessing and integration"]
    assert not (tmp_path / "references").exists() or not list((tmp_path / "references").rglob("*.md"))
    assert any(
        "ambiguous tag fallback" in r.message and r.levelname == "INFO"
        for r in caplog.records
    )


def test_four_outcomes_reconcile_with_ambiguous_case_in_the_mix(tmp_path):
    """The same reconciliation invariant as
    test_four_outcomes_reconcile_against_analyses_seen, but with an ambiguous
    tag-fallback paper mixed in -- an ambiguous block is not a fifth,
    unaccounted-for outcome, it is counted as unresolved like any other."""
    stats = UsageFeedStats()

    # Paper 1: one block resolves by analysis_name alone, one fresh write.
    _emit_usage_records(tmp_path, _rec(comp_methods={
        "summary_2to3_sentences": "x",
        "analyses": [
            {"analysis_name": "clustering", "steps": [{"step": "Leiden", "tool": "ArchR"}]},
        ],
    }), stats)

    # Paper 2: two blocks miss analysis_name, tags name exactly one concept
    # -- ambiguous (2+ blocks competing for it), both stay unresolved.
    _emit_usage_records(tmp_path, _rec(PMID="55555555", comp_methods={
        "summary_2to3_sentences": "x",
        "tags": ["clustering"],
        "analyses": [
            {"analysis_name": "Block A", "steps": []},
            {"analysis_name": "Block B", "steps": []},
        ],
    }), stats)

    written = stats.analyses_resolved - stats.skipped_existing
    assert stats.analyses_seen == written + stats.skipped_existing + len(stats.unresolved_names)
    assert written == 1
    assert stats.skipped_existing == 0
    assert len(stats.unresolved_names) == 2


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
# Fix round 1: the collision skip must not be the one silent outcome.
# ---------------------------------------------------------------------------

def test_collision_skip_is_counted_and_logged_by_name(tmp_path, caplog):
    """A same-day rerun on the same (paper, concept) is a correct no-op, but
    it must be COUNTED (skipped_existing) and LOGGED (naming the existing
    record id), same as the other two silent-zero-yield outcomes."""
    rec = _rec()
    _emit_usage_records(tmp_path, rec, UsageFeedStats())  # first write

    stats2 = UsageFeedStats()
    with caplog.at_level(logging.INFO, logger="litintel.pipeline.tier1"):
        _emit_usage_records(tmp_path, rec, stats2)  # same day, same pmid, same concept

    assert stats2.skipped_existing == 1
    assert stats2.analyses_resolved == 1
    assert stats2.analyses_seen == 1

    skip_logs = [r.message for r in caplog.records if "skipping write" in r.message]
    assert len(skip_logs) == 1
    assert "already exists" in skip_logs[0]
    assert "-clustering-usage.md" in skip_logs[0]  # names the record id


def test_log_summary_surfaces_skipped_existing(caplog):
    stats = UsageFeedStats(
        papers_eligible=1,
        analyses_seen=1,
        analyses_resolved=1,
        skipped_existing=1,
    )

    with caplog.at_level(logging.INFO, logger="litintel.pipeline.tier1"):
        stats.log_summary()

    [msg] = [r.message for r in caplog.records if "methods feed" in r.message]
    assert "already present" in msg
    assert "0 written" in msg
    assert "1 already present" in msg


def test_four_outcomes_reconcile_against_analyses_seen(tmp_path):
    """One summary line must let a reader account for every analysis block
    seen: written, already-present, or unresolved (papers_no_comp_methods is
    a separate, paper-level axis with zero analysis blocks by construction)."""
    stats = UsageFeedStats()

    # Paper 1: two resolvable concepts, both fresh writes.
    _emit_usage_records(tmp_path, _rec(comp_methods={
        "summary_2to3_sentences": "x",
        "analyses": [
            {"analysis_name": "clustering", "steps": [{"step": "Leiden", "tool": "ArchR"}]},
            {"analysis_name": "normalization", "steps": [{"step": "DESeq2 normalization", "tool": ""}]},
        ],
    }), stats)

    # Paper 2 (same day): re-derives the same clustering claim (collision
    # skip) plus one brand-new unresolved analysis name.
    _emit_usage_records(tmp_path, _rec(PMID="41234567", comp_methods={
        "summary_2to3_sentences": "x",
        "analyses": [
            {"analysis_name": "clustering", "steps": [{"step": "Leiden", "tool": "ArchR"}]},
            {"analysis_name": "a totally new stage", "steps": []},
        ],
    }), stats)

    # Paper 3: no comp_methods at all (paper-level, contributes 0 analyses).
    _emit_usage_records(tmp_path, _rec(PMID="99999999", comp_methods=None), stats)

    written = stats.analyses_resolved - stats.skipped_existing
    assert stats.analyses_seen == written + stats.skipped_existing + len(stats.unresolved_names)
    assert written == 2          # paper 1's clustering + normalization
    assert stats.skipped_existing == 1  # paper 2's repeat clustering claim
    assert len(stats.unresolved_names) == 1
    assert stats.papers_no_comp_methods == 1
    assert stats.papers_eligible == 3


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
    assert stats2.skipped_existing == 1
