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
