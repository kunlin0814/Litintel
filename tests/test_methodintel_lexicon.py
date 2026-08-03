import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from litintel.methodintel.lexicon import (
    LexiconError,
    build_concept_aliases,
    parse_lexicon,
    parse_unplaced_terms,
)

LEXICON = """# Lexicon

Preamble prose that must be ignored.

## clustering

Question: Which cells or spots form a group, given their molecular profiles?

| Label | Since | Status |
|---|---|---|
| clustering | 2015 | dominant |
| community detection | 2008 | |
| cell grouping | | |

## neighborhood_analysis

Question: Do cell types co-occur in space more or less than expected by chance?

| Label | Since | Status |
|---|---|---|
| neighborhood analysis | 2021 | dominant |
| niche identification | | |

## Unplaced

| Term | First seen | Source |
|---|---|---|
| sepal | 2026-08-02 | PMID 35102346 |
"""


def test_parse_lexicon_finds_concepts(tmp_path):
    path = tmp_path / "LEXICON.md"
    path.write_text(LEXICON)

    entries = parse_lexicon(path)

    assert [e.concept for e in entries] == ["clustering", "neighborhood_analysis"]


def test_unplaced_section_is_not_a_concept(tmp_path):
    path = tmp_path / "LEXICON.md"
    path.write_text(LEXICON)

    assert "Unplaced" not in [e.concept for e in parse_lexicon(path)]


def test_question_and_labels_are_captured(tmp_path):
    path = tmp_path / "LEXICON.md"
    path.write_text(LEXICON)

    clustering = parse_lexicon(path)[0]

    assert clustering.question.startswith("Which cells or spots form a group")
    assert clustering.labels == ["clustering", "community detection", "cell grouping"]


def test_build_concept_aliases_maps_every_label(tmp_path):
    path = tmp_path / "LEXICON.md"
    path.write_text(LEXICON)

    aliases = build_concept_aliases(parse_lexicon(path))

    assert aliases["community detection"] == "clustering"
    assert aliases["niche identification"] == "neighborhood_analysis"
    assert aliases["clustering"] == "clustering"


def test_aliases_are_lowercased_for_lookup(tmp_path):
    path = tmp_path / "LEXICON.md"
    path.write_text(LEXICON.replace("| clustering |", "| Clustering |"))

    assert "clustering" in build_concept_aliases(parse_lexicon(path))


def test_router_exposes_concept_aliases():
    from litintel.methodintel.router import CONCEPT_ALIASES

    assert CONCEPT_ALIASES["community detection"] == "clustering"
    assert CONCEPT_ALIASES["niche identification"] == "neighborhood_analysis"


def test_unplaced_terms_are_known_but_carry_no_concept(tmp_path):
    """spec 3.4.2: a null concept is legal and preferred over a guess.

    parse_unplaced_terms is the only place "sepal" appears -- it must never
    surface in parse_lexicon's concept entries and must never resolve through
    build_concept_aliases, or an unplaced term would silently acquire a
    meaning it was deliberately parked for lacking.
    """
    path = tmp_path / "LEXICON.md"
    path.write_text(LEXICON)

    assert parse_unplaced_terms(path) == ["sepal"]
    assert "sepal" not in build_concept_aliases(parse_lexicon(path))


def test_unplaced_term_is_distinguishable_from_a_truly_unknown_term(tmp_path):
    """The design forbids a caller being unable to tell "unknown" apart from
    "known but deliberately unplaced" -- both are absent from CONCEPT_ALIASES,
    but only one of them shows up in parse_unplaced_terms.
    """
    path = tmp_path / "LEXICON.md"
    path.write_text(LEXICON)

    aliases = build_concept_aliases(parse_lexicon(path))
    unplaced = parse_unplaced_terms(path)

    assert "sepal" not in aliases and "sepal" in unplaced
    assert "never seen anywhere" not in aliases
    assert "never seen anywhere" not in unplaced


def test_multiline_question_is_joined(tmp_path):
    """The real LEXICON.md wraps some Question: lines across two source lines
    (e.g. cluster_annotation) -- a naive single-line capture would silently
    truncate the question that Tier 2 semantic match is meant to key on.
    """
    text = (
        "## cluster_annotation\n\n"
        "Question: What cell type or spatial-domain identity does a given cluster\n"
        "represent?\n\n"
        "| Label | Since | Status |\n"
        "|---|---|---|\n"
        "| cluster annotation | | |\n"
    )
    path = tmp_path / "LEXICON.md"
    path.write_text(text)

    entry = parse_lexicon(path)[0]

    assert entry.question == (
        "What cell type or spatial-domain identity does a given cluster represent?"
    )


def test_sources_prose_lines_are_ignored(tmp_path):
    """Some concept sections carry a "Sources:" prose line after the table and
    some do not -- the parser must tolerate both without treating the prose
    as another label row or letting it leak into the next concept.
    """
    text = (
        "## dimensionality_reduction\n\n"
        "Question: How is a high-dimensional profile projected down?\n\n"
        "| Label | Since | Status |\n"
        "|---|---|---|\n"
        "| dimensionality reduction | | |\n\n"
        "Sources: dimensionality reduction -- PMID 31217225 (Luecken 2019).\n"
        "Same operation, cosmetic spelling variant across seed papers.\n\n"
        "## normalization\n\n"
        "Question: How are counts made comparable?\n\n"
        "| Label | Since | Status |\n"
        "|---|---|---|\n"
        "| normalization | | dominant |\n"
    )
    path = tmp_path / "LEXICON.md"
    path.write_text(text)

    entries = parse_lexicon(path)

    assert [e.concept for e in entries] == ["dimensionality_reduction", "normalization"]
    assert entries[0].labels == ["dimensionality reduction"]
    assert entries[1].labels == ["normalization"]


def test_label_claimed_by_two_concepts_raises_naming_both(tmp_path):
    """Fix round 1, Finding 1: a label drifting under two concept headings is
    among the most likely authoring mistakes LEXICON.md will ever see (that
    is what the file is for), and a silent dict overwrite would route a
    paper's evidence to whichever concept happened to parse last. The error
    must name the label and both concepts so the owner can adjudicate.
    """
    text = (
        "## clustering\n\n"
        "Question: Which cells or spots form a group?\n\n"
        "| Label | Since | Status |\n"
        "|---|---|---|\n"
        "| shared term | | |\n\n"
        "## normalization\n\n"
        "Question: How are counts made comparable?\n\n"
        "| Label | Since | Status |\n"
        "|---|---|---|\n"
        "| shared term | | |\n"
    )
    path = tmp_path / "LEXICON.md"
    path.write_text(text)

    try:
        build_concept_aliases(parse_lexicon(path))
        assert False, "expected LexiconError"
    except LexiconError as exc:
        message = str(exc)
        assert "shared term" in message
        assert "clustering" in message
        assert "normalization" in message


def test_label_repeated_under_the_same_concept_is_deduped_silently(tmp_path):
    """A label listed twice under one concept table is a harmless duplicate
    (both occurrences already agree on the answer) -- it dedupes rather than
    raising, unlike a cross-concept collision.
    """
    text = (
        "## clustering\n\n"
        "Question: Which cells or spots form a group?\n\n"
        "| Label | Since | Status |\n"
        "|---|---|---|\n"
        "| clustering | 2015 | dominant |\n"
        "| clustering | 2015 | dominant |\n"
    )
    path = tmp_path / "LEXICON.md"
    path.write_text(text)

    aliases = build_concept_aliases(parse_lexicon(path))

    assert aliases == {"clustering": "clustering"}


def test_unrelated_prose_after_a_complete_question_is_not_absorbed(tmp_path):
    """Fix round 1, Finding 2: a Question: line that already ends in terminal
    punctuation is complete. Continuation must stop there rather than
    absorbing arbitrary prose that happens to follow with no blank-line
    separator.
    """
    text = (
        "## normalization\n\n"
        "Question: How are counts made comparable?\n"
        "This sentence is unrelated body prose, not part of the question.\n\n"
        "| Label | Since | Status |\n"
        "|---|---|---|\n"
        "| normalization | | dominant |\n"
    )
    path = tmp_path / "LEXICON.md"
    path.write_text(text)

    entry = parse_lexicon(path)[0]

    assert entry.question == "How are counts made comparable?"


def _write_minimal_config(config_path, methods_repo_path):
    config_path.write_text(
        "pipeline_tier: 1\n"
        "pipeline_name: test\n"
        "discovery:\n"
        "  mode: KEYWORD\n"
        '  queries: ["test"]\n'
        "ai:\n"
        "  provider: gemini\n"
        "  prompt_template: x\n"
        "storage: {}\n"
        "dedup: {}\n"
        'methods_repo_path: "%s"\n' % methods_repo_path
    )


def test_sync_aliases_cli_prints_generated_table_and_unplaced_terms(tmp_path):
    """Fix round 1, Finding 3: exercise the sync-aliases command itself
    (against a temp copy of a lexicon, never the real one) rather than only
    hand-verifying it -- Task 8 adds a second CLI command and Task 11's
    acceptance drives the CLI, so this establishes the pattern.
    """
    from typer.testing import CliRunner

    from litintel.cli import app

    methods_root = tmp_path / "bioinfo-methods"
    methods_root.mkdir()
    (methods_root / "LEXICON.md").write_text(LEXICON)

    config_path = tmp_path / "config.yaml"
    _write_minimal_config(config_path, methods_root)

    result = CliRunner().invoke(
        app, ["methodintel", "sync-aliases", "--config", str(config_path)]
    )

    assert result.exit_code == 0, result.output
    assert '"community detection": "clustering",' in result.output
    assert '"niche identification": "neighborhood_analysis",' in result.output
    assert "1 unplaced term(s) excluded" in result.output
    assert "sepal" in result.output


def test_sync_aliases_cli_reports_missing_methods_repo_path(tmp_path):
    """The command must fail loud (not print an empty/partial table) when
    methods_repo_path is unset, reusing records.resolve_methods_root's error.
    """
    from typer.testing import CliRunner

    from litintel.cli import app

    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "pipeline_tier: 1\n"
        "pipeline_name: test\n"
        "discovery:\n"
        "  mode: KEYWORD\n"
        '  queries: ["test"]\n'
        "ai:\n"
        "  provider: gemini\n"
        "  prompt_template: x\n"
        "storage: {}\n"
        "dedup: {}\n"
    )

    result = CliRunner().invoke(
        app, ["methodintel", "sync-aliases", "--config", str(config_path)]
    )

    assert result.exit_code == 2
    assert "methods_repo_path is not set" in result.output
