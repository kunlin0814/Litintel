import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from litintel.methodintel.lexicon import (
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
