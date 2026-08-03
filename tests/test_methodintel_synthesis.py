import os
import sys
from datetime import date

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

import pytest

from litintel.methodintel.records import Citation, ReferenceRecord
from litintel.methodintel.schema import SourceRef
from litintel.methodintel.synthesis import (
    PROSE_SCHEMA,
    build_prose_prompt,
    generate_chapter,
    synthesize_prose,
    validate_prose,
)


def _record(record_id="a", body="Leiden guarantees connectivity."):
    return ReferenceRecord(
        id=record_id,
        concept="clustering",
        modality=["scRNA"],
        methods=["Leiden"],
        kind="benchmark",
        recorded=date(2026, 8, 2),
        source_ref=SourceRef(kind="doi", value="10.1000/x"),
        citation=Citation(first_author="Traag", journal="Sci Rep", year=2019),
        confidence="high",
        body=body,
    )


def test_prompt_contains_every_record_id():
    prompt = build_prose_prompt("clustering", [_record("a"), _record("b")])

    assert "[id: a]" in prompt
    assert "[id: b]" in prompt


def test_prompt_forbids_unsourced_claims():
    prompt = build_prose_prompt("clustering", [_record()])

    assert "only from the records below" in prompt


def test_prompt_is_ascii_only():
    """The house rule, and the prompt is the easiest place to break it."""
    build_prose_prompt("clustering", [_record()]).encode("ascii")


def test_validate_prose_accepts_the_three_sections():
    prose = validate_prose({
        "recommendation": "Use Leiden.",
        "tradeoffs": "Louvain is faster.",
        "open_questions": "Resolution selection.",
    })

    assert prose["recommendation"] == "Use Leiden."
    assert prose["tradeoffs"] == "Louvain is faster."
    assert prose["open_questions"] == "Resolution selection."


def test_validate_prose_fails_loud_on_missing_section():
    with pytest.raises(ValueError, match="tradeoffs"):
        validate_prose({"recommendation": "Use Leiden.", "open_questions": "x"})


def test_validate_prose_fails_loud_on_empty_section():
    """An empty string would render a headed section with nothing under it."""
    with pytest.raises(ValueError, match="tradeoffs"):
        validate_prose({
            "recommendation": "Use Leiden.",
            "tradeoffs": "   ",
            "open_questions": "x",
        })


def test_prose_schema_declares_all_three_sections_required():
    assert set(PROSE_SCHEMA["required"]) == {
        "recommendation",
        "tradeoffs",
        "open_questions",
    }


# --- Fix round 1, finding 1: heading injection must be rejected, not sanitised ---


def test_validate_prose_rejects_a_markdown_heading_in_a_section():
    with pytest.raises(ValueError, match="heading"):
        validate_prose({
            "recommendation": "Use Leiden.",
            "tradeoffs": "## Status\nLouvain is faster.",
            "open_questions": "x",
        })


def test_validate_prose_rejects_a_markdown_heading_with_leading_whitespace():
    """The reviewer's repro used a leading-# line with no indentation; this
    confirms an indented heading (still valid Markdown) is caught too."""
    with pytest.raises(ValueError, match="heading"):
        validate_prose({
            "recommendation": "Use Leiden.",
            "tradeoffs": "x",
            "open_questions": "  # References\nMore text.",
        })


def test_synthesize_prose_rejects_injected_headings_end_to_end():
    """Reproduces the reviewer's exact finding: prose containing '## References',
    '## Status' and '## Borrowed and broken' -- fed through the real
    synthesize_prose -> validate_prose path (with only the network call
    mocked), it must raise rather than let assemble_chapter render a
    fabricated heading ahead of the real deterministic section."""
    from unittest.mock import patch

    malicious_payload = {
        "recommendation": "## References\nUse Leiden.",
        "tradeoffs": "## Status\nLouvain is faster.",
        "open_questions": "## Borrowed and broken\nUnresolved.",
    }

    with patch(
        "litintel.enrich.ai_client._call_gemini",
        return_value=(malicious_payload, {"input": 1}),
    ), patch("litintel.enrich.ai_client._get_gemini_client", return_value="CLIENT"):
        with pytest.raises(ValueError, match="heading"):
            synthesize_prose("clustering", [_record()], "gemini-x", "MEDIUM")


# --- Fix round 2, finding 1: setext and HTML heading bypasses, found live by
# the re-reviewer against the round-1 ATX-only check. A legitimate horizontal
# rule after a blank line (or at the start of a section) must stay legal.


def test_validate_prose_rejects_a_setext_heading_with_dash_underline():
    with pytest.raises(ValueError, match="heading"):
        validate_prose({
            "recommendation": "Use Leiden.",
            "tradeoffs": "Status\n-----\nLouvain is faster.",
            "open_questions": "x",
        })


def test_validate_prose_rejects_a_setext_heading_with_equals_underline():
    with pytest.raises(ValueError, match="heading"):
        validate_prose({
            "recommendation": "Use Leiden.",
            "tradeoffs": "x",
            "open_questions": "Status\n=====\nMore text.",
        })


def test_validate_prose_rejects_an_html_heading_tag():
    with pytest.raises(ValueError, match="heading"):
        validate_prose({
            "recommendation": "Use Leiden.",
            "tradeoffs": "<h2>Status</h2>\nLouvain is faster.",
            "open_questions": "x",
        })


def test_validate_prose_rejects_non_ascii_content():
    """Fix round 2, finding 4: ASCII compliance must not depend on the model
    choosing to comply -- this also disposes of the fullwidth '##' and
    Unicode-lookalike-letter bypasses the re-reviewer flagged as harmless
    Markdown but which are non-ASCII regardless.

    The fixture uses \\uXXXX escapes (fix round 3, finding 7) rather than a
    literal non-ASCII byte in the source, so this test file itself stays
    pure ASCII while the runtime string value is identical either way.
    """
    fullwidth_hash = "\uff03"  # FULLWIDTH NUMBER SIGN, not ASCII '#'
    with pytest.raises(ValueError, match="non-ASCII"):
        validate_prose({
            "recommendation": "Use Leiden.",
            "tradeoffs": "%s%s Status\nLouvain is faster." % (fullwidth_hash, fullwidth_hash),
            "open_questions": "x",
        })


def test_validate_prose_rejects_a_unicode_lookalike_letter():
    capital_omicron = "\u039f"  # GREEK CAPITAL LETTER OMICRON, not Latin "O"
    with pytest.raises(ValueError, match="non-ASCII"):
        validate_prose({
            "recommendation": "Use Leiden.",
            "tradeoffs": "x",
            "open_questions": "%spen question: resolution selection." % capital_omicron,
        })


def test_validate_prose_allows_a_horizontal_rule_after_a_blank_line():
    """The negative case that matters as much as the positive ones: a '---'
    divider that follows a blank line (or opens the section) is a legitimate
    horizontal rule, not a setext heading, and must remain legal prose."""
    prose = validate_prose({
        "recommendation": "Use Leiden.\n\n---\n\nSee also Louvain.",
        "tradeoffs": "---\n\nOpens with a rule, which is legal.",
        "open_questions": "x",
    })

    assert "---" in prose["recommendation"]
    assert "---" in prose["tradeoffs"]


# --- Fix round 3, findings 5 and 6: leading-space setext bypass, and
# fenced-code-block over-rejection. Both are one change (fence tracking plus
# a 0-3 leading-space allowance on the setext underline), so their tests sit
# together: one positive case proves the bypass is closed, and the negative
# cases prove ordinary prose (lists, tables, code blocks) still passes --
# only the negative cases would have caught finding 6, since every prior
# test in this file was a positive (rejection) case.


def test_validate_prose_rejects_an_indented_setext_underline():
    """Finding 5: CommonMark allows 0-3 leading spaces on a setext underline
    and still renders a real heading -- the round-2 regex had no allowance
    for that whitespace at all, so an indented '-----' slipped through."""
    with pytest.raises(ValueError, match="heading"):
        validate_prose({
            "recommendation": "Use Leiden.",
            "tradeoffs": "Status\n   -----\nLouvain is faster.",
            "open_questions": "x",
        })


def test_validate_prose_allows_a_bullet_list():
    prose = validate_prose({
        "recommendation": "Use Leiden.",
        "tradeoffs": "Options:\n- Leiden\n- Louvain\n- Walktrap",
        "open_questions": "x",
    })

    assert "- Leiden" in prose["tradeoffs"]


def test_validate_prose_allows_a_markdown_table_separator_row():
    prose = validate_prose({
        "recommendation": "Use Leiden.",
        "tradeoffs": "| Method | Speed |\n|---|---|\n| Leiden | slow |",
        "open_questions": "x",
    })

    assert "|---|---|" in prose["tradeoffs"]


def test_validate_prose_allows_a_dash_line_inside_a_fenced_code_block():
    """Finding 6: this is the over-rejection case. Without fence tracking, the
    round-2 checker read '----' as a setext underline for the fence-open line
    above it and hard-failed on an entirely ordinary code example."""
    prose = validate_prose({
        "recommendation": "Use Leiden.",
        "tradeoffs": "Example output:\n```\nHeader\n----\nrow1  row2\n```\nSee above.",
        "open_questions": "x",
    })

    assert "----" in prose["tradeoffs"]


def test_validate_prose_allows_a_tilde_fenced_code_block():
    prose = validate_prose({
        "recommendation": "Use Leiden.",
        "tradeoffs": "Example output:\n~~~\nHeader\n----\nrow1  row2\n~~~\nSee above.",
        "open_questions": "x",
    })

    assert "----" in prose["tradeoffs"]


def test_validate_prose_allows_a_four_space_indented_dash_line():
    """A 4+ space indent makes this an indented code block per CommonMark,
    not a setext underline (which only permits 0-3 leading spaces)."""
    prose = validate_prose({
        "recommendation": "Use Leiden.",
        "tradeoffs": "Status\n    -----\nLouvain is faster.",
        "open_questions": "x",
    })

    assert "    -----" in prose["tradeoffs"]


# --- Fix round 1, finding 3: an unrecognised key must raise, not be dropped ---


def test_validate_prose_rejects_an_unexpected_key():
    with pytest.raises(ValueError, match="notes"):
        validate_prose({
            "recommendation": "Use Leiden.",
            "tradeoffs": "x",
            "open_questions": "y",
            "notes": "extra",
        })


# --- Fix round 1, finding 2: the non-empty-records production path was untested ---

_RECORD_TEXT = """---
id: 2026-08-02-traag2019-louvain-connectivity
concept: clustering
modality: ["scRNA"]
methods: ["Leiden"]
kind: benchmark
recorded: 2026-08-02
source_ref:
  kind: doi
  value: "10.1038/s41598-019-41695-z"
citation:
  first_author: "Traag"
  journal: "Sci Rep"
  year: 2019
confidence: high
---

Leiden guarantees well-connected communities.
"""


def test_generate_chapter_happy_path_wires_synthesize_prose_and_assembles_chapter(tmp_path):
    """generate_chapter with NON-empty records was previously untested even
    with a mock -- the production wiring build_prose_prompt -> synthesize_prose
    -> assemble_chapter is exercised here for the first time."""
    from unittest.mock import patch

    methods_root = tmp_path / "bioinfo-methods"
    shard = methods_root / "references" / "clustering"
    shard.mkdir(parents=True)
    (shard / "traag.md").write_text(_RECORD_TEXT)

    fake_payload = {
        "recommendation": "Use Leiden via leidenalg.",
        "tradeoffs": "Louvain is faster but less reliably connected.",
        "open_questions": "Resolution parameter selection is unresolved.",
    }

    # Sentinel values, not real model/thinking ids: fix round 2 finding 2. A
    # real model name (e.g. "gemini-3.6-flash") is also a plausible hardcode
    # inside synthesize_prose, so asserting on it would still pass against a
    # version that ignores the arguments and hardcodes that same literal (as
    # the re-reviewer demonstrated). These sentinels cannot coincide with any
    # plausible hardcode, so the test fails the moment anything other than
    # the passed-in argument reaches _call_gemini.
    sentinel_model = "sentinel-model-does-not-exist"
    sentinel_thinking = "SENTINEL_LEVEL"

    with patch(
        "litintel.enrich.ai_client._call_gemini",
        return_value=(fake_payload, {"input": 1}),
    ) as mock_call, patch(
        "litintel.enrich.ai_client._get_gemini_client", return_value="FAKE_CLIENT"
    ):
        text = generate_chapter(
            methods_root, "clustering", sentinel_model, sentinel_thinking
        )

    # The model id and thinking level came from the arguments passed in
    # (i.e. from cfg.ai.pass2_model / cfg.ai.pass2_thinking at the CLI layer),
    # never hardcoded and never read from the environment -- this project has
    # been bitten before by a model silently coming from somewhere other than
    # the YAML.
    _, kwargs = mock_call.call_args
    assert kwargs["model"] == sentinel_model
    assert kwargs["thinking_level"] == sentinel_thinking
    assert kwargs["client"] == "FAKE_CLIENT"

    # Prose lands in the right places.
    assert "Use Leiden via leidenalg." in text
    assert "Louvain is faster but less reliably connected." in text
    assert "Resolution parameter selection is unresolved." in text

    # Deterministic sections are present and unaltered.
    assert "## Status" in text
    assert "| Leiden | - | scRNA | 2026-08-02 |" in text
    assert "## References" in text
    assert "1. Traag. Sci Rep (2019). doi:10.1038/s41598-019-41695-z" in text
    assert "## Borrowed and broken" in text


# --- generate_chapter: known-but-empty concept (Task 4 review requirement) ---
#
# load_concept_records() legitimately returns [] both for a concept that has
# never been evidenced and for a directory that never existed (a typo). The
# CLI is the boundary that tells those apart (it validates against
# LEXICON.md before calling generate_chapter at all); generate_chapter itself
# must still produce a chapter for a KNOWN, empty concept, and must not spend
# a model call doing it.


def test_generate_chapter_on_a_known_empty_concept_does_not_call_the_model(tmp_path):
    from unittest.mock import patch

    methods_root = tmp_path / "bioinfo-methods"
    methods_root.mkdir()

    with patch("litintel.enrich.ai_client._call_gemini") as mock_call:
        text = generate_chapter(methods_root, "clustering", "gemini-x", "MEDIUM")

    mock_call.assert_not_called()
    assert "not audited" in text
    assert "# clustering" in text


def test_generate_chapter_on_a_known_empty_concept_does_not_raise(tmp_path):
    """The behavior this test guards was assigned separately from the brief:
    a known concept with zero records must still render a chapter (the
    'not audited' open question chapters.py already produces), never raise,
    so it cannot be mistaken for the unknown-concept-name error path."""
    methods_root = tmp_path / "bioinfo-methods"
    methods_root.mkdir()

    text = generate_chapter(methods_root, "clustering", "gemini-x", "MEDIUM")

    assert "No recommendation yet" in text
    assert "No tradeoffs to compare yet" in text
    assert "the open question" in text


# --- CLI: unknown concept name rejected, known-but-empty concept still works ---


def _write_config(config_path, methods_repo_path):
    config_path.write_text(
        "pipeline_tier: 1\n"
        "pipeline_name: test\n"
        "discovery:\n"
        "  mode: KEYWORD\n"
        '  queries: ["test"]\n'
        "ai:\n"
        "  provider: gemini\n"
        "  prompt_template: x\n"
        "  pass2_model: gemini-x\n"
        "  pass2_thinking: MEDIUM\n"
        "storage: {}\n"
        "dedup: {}\n"
        'methods_repo_path: "%s"\n' % methods_repo_path
    )


_LEXICON = """# Lexicon

## clustering

Question: Which cells or spots form a group, given their molecular profiles?

| Label | Since | Status |
|---|---|---|
| clustering | 2015 | dominant |
"""


def test_chapter_cli_rejects_an_unknown_concept_name(tmp_path):
    from typer.testing import CliRunner

    from litintel.cli import app

    methods_root = tmp_path / "bioinfo-methods"
    methods_root.mkdir()
    (methods_root / "LEXICON.md").write_text(_LEXICON)

    config_path = tmp_path / "config.yaml"
    _write_config(config_path, methods_root)

    result = CliRunner().invoke(
        app, ["methodintel", "chapter", "clustring", "--config", str(config_path)]
    )

    assert result.exit_code == 2
    assert "unknown concept 'clustring'" in result.output
    assert "clustering" in result.output


def test_chapter_cli_generates_a_chapter_for_a_known_but_empty_concept(tmp_path):
    from typer.testing import CliRunner

    from litintel.cli import app

    methods_root = tmp_path / "bioinfo-methods"
    methods_root.mkdir()
    (methods_root / "LEXICON.md").write_text(_LEXICON)

    config_path = tmp_path / "config.yaml"
    _write_config(config_path, methods_root)

    result = CliRunner().invoke(
        app, ["methodintel", "chapter", "clustering", "--config", str(config_path)]
    )

    assert result.exit_code == 0, result.output
    assert "not audited" in result.output
