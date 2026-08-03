import os
import sys
from datetime import date

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

import pytest

from litintel.methodintel.records import Citation, ReferenceRecord
from litintel.methodintel.schema import SourceRef
from litintel.methodintel.synthesis import (
    PROSE_SCHEMA,
    _check_prose_is_cited,
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


# --- Fix round 4: the fence toggle was wrong in two directions ---
#
# Round 3 tracked fences with a single boolean. That made an unclosed fence
# read as "checking is off from here on" -- which looks safe and is the
# opposite, because assemble_chapter concatenates this prose into a chapter
# and an open fence swallows every deterministic heading BELOW it into an
# inert code block (measured through a CommonMark renderer: 2 of 9 headings
# survived). It also let any fence marker close any other, so a ``` block
# "closed" by ~~~ resumed checking mid-code-block and rejected the code's own
# dash lines as fake setext headings.
#
# Both follow from tracking the opening run instead of a boolean: a fence is
# closed only by the SAME character in a run at least as long, and a section
# still holding a marker at the end never closed its fence.


def test_validate_prose_rejects_an_unclosed_backtick_fence():
    """Defect 1. The section that opens the fence is named, because the
    damage lands in a chapter assembled from three sections and the error
    has to point back at the one that caused it."""
    with pytest.raises(ValueError, match="never closed"):
        validate_prose({
            "recommendation": "Use Leiden.",
            "tradeoffs": "Example:\n```\nsc.tl.leiden(adata)\nno closing fence",
            "open_questions": "x",
        })


def test_validate_prose_rejects_an_unclosed_tilde_fence():
    with pytest.raises(ValueError, match="never closed"):
        validate_prose({
            "recommendation": "Use Leiden.",
            "tradeoffs": "Example:\n~~~\nsc.tl.leiden(adata)\nno closing fence",
            "open_questions": "x",
        })


def test_validate_prose_rejects_a_fence_a_shorter_run_cannot_close():
    """A ``` run does not close a ```` fence (CommonMark: the closing run must
    be at least as long), so this fence is open at the end of the section."""
    with pytest.raises(ValueError, match="never closed"):
        validate_prose({
            "recommendation": "Use Leiden.",
            "tradeoffs": "Example:\n````\ncode\n```\nstill inside the fence",
            "open_questions": "x",
        })


def test_validate_prose_rejects_a_closing_fence_carrying_an_info_string():
    """CommonMark forbids an info string on a CLOSING fence, so '```python'
    opens nothing and closes nothing -- the first fence stays open."""
    with pytest.raises(ValueError, match="never closed"):
        validate_prose({
            "recommendation": "Use Leiden.",
            "tradeoffs": "Example:\n```\ncode\n```python\nstill inside",
            "open_questions": "x",
        })


def test_unclosed_fence_error_names_the_section_and_the_marker():
    """The exact diagnostic, since it is what a failed chapter run prints."""
    with pytest.raises(ValueError) as excinfo:
        validate_prose({
            "recommendation": "Use Leiden.\n\n```\nsc.tl.leiden(adata)",
            "tradeoffs": "x",
            "open_questions": "y",
        })

    assert str(excinfo.value) == (
        "model response section recommendation opens a fenced code block "
        "with '```' that is never closed -- an unclosed fence swallows every "
        "deterministic heading after it in the assembled chapter"
    )


def test_unclosed_fence_is_rejected_before_it_can_reach_assemble_chapter():
    """The suppression case in full. This prose renders 2 of the chapter's 9
    headings (the two ABOVE the open fence); '## Status', '## Borrowed and
    broken', '## Tradeoffs', '## What changed', '## References' and
    '## Open questions' all vanish into the code block. Verified through a
    CommonMark renderer out of band -- no renderer is imported here, since
    the suite takes no Markdown-parser dependency."""
    from unittest.mock import patch

    payload = {
        "recommendation": "Use Leiden via leidenalg.\n\n```\nsc.tl.leiden(adata)",
        "tradeoffs": "Louvain is faster.",
        "open_questions": "Resolution selection.",
    }

    with patch(
        "litintel.enrich.ai_client._call_gemini",
        return_value=(payload, {"input": 1}),
    ), patch("litintel.enrich.ai_client._get_gemini_client", return_value="CLIENT"):
        with pytest.raises(ValueError, match="never closed"):
            synthesize_prose("clustering", [_record()], "gemini-x", "MEDIUM")


def test_validate_prose_rejects_an_html_heading_split_across_lines():
    """The tag opens its own line and the text sits below it -- still a real
    <h2> once rendered, so it must not pass just because the tag and its
    content are not on one line."""
    with pytest.raises(ValueError, match="heading"):
        validate_prose({
            "recommendation": "Use Leiden.",
            "tradeoffs": "<h2>\nStatus\n</h2>\nLouvain is faster.",
            "open_questions": "x",
        })


# The negative cases. Defect 2 is an OVER-rejection, and an over-rejection
# hard-fails chapter generation on correct model output -- prose about
# computational methods is full of code examples, so these matter at least as
# much as the rejections above.


def test_validate_prose_allows_a_tilde_line_inside_a_backtick_fence():
    """Defect 2, exactly. Round 3 let '~~~' close a '```' fence, which
    resumed heading checks in the middle of a code block and rejected the
    block's own dash line as a setext underline. CommonMark keeps the fence
    open here, so the whole thing is code and nothing in it is a heading."""
    prose = validate_prose({
        "recommendation": "Use Leiden.",
        "tradeoffs": "Example:\n```\nHeader\n~~~\nStatus\n-----\nMore\n```\nDone.",
        "open_questions": "x",
    })

    assert "-----" in prose["tradeoffs"]


def test_validate_prose_allows_a_backtick_line_inside_a_tilde_fence():
    prose = validate_prose({
        "recommendation": "Use Leiden.",
        "tradeoffs": "Example:\n~~~\nHeader\n```\nStatus\n-----\nMore\n~~~\nDone.",
        "open_questions": "x",
    })

    assert "-----" in prose["tradeoffs"]


def test_validate_prose_allows_a_shorter_fence_run_inside_a_longer_fence():
    prose = validate_prose({
        "recommendation": "Use Leiden.",
        "tradeoffs": "Example:\n````\nHeader\n```\nStatus\n-----\nMore\n````\nDone.",
        "open_questions": "x",
    })

    assert "-----" in prose["tradeoffs"]


def test_validate_prose_allows_a_fence_with_an_info_string():
    prose = validate_prose({
        "recommendation": "Use Leiden.",
        "tradeoffs": "Example:\n```python\nsc.tl.leiden(adata)\n# not a heading\n```\nDone.",
        "open_questions": "x",
    })

    assert "sc.tl.leiden(adata)" in prose["tradeoffs"]


def test_validate_prose_allows_an_indented_fence():
    prose = validate_prose({
        "recommendation": "Use Leiden.",
        "tradeoffs": "Example:\n   ```\n   Header\n   ----\n   ```\nDone.",
        "open_questions": "x",
    })

    assert "----" in prose["tradeoffs"]


def test_validate_prose_allows_a_dash_line_directly_after_a_closed_fence():
    """A closing fence line is not paragraph text, so a '-----' directly
    below it is a thematic break, not a setext underline (confirmed against a
    CommonMark renderer: it emits <hr />, no heading)."""
    prose = validate_prose({
        "recommendation": "Use Leiden.",
        "tradeoffs": "Example:\n```\ncode\n```\n-----\nMore prose.",
        "open_questions": "x",
    })

    assert "-----" in prose["tradeoffs"]


def test_validate_prose_allows_nested_indented_list_items():
    prose = validate_prose({
        "recommendation": "Use Leiden.",
        "tradeoffs": "Options:\n- Leiden\n  - leidenalg\n    - igraph backend\n- Louvain",
        "open_questions": "x",
    })

    assert "    - igraph backend" in prose["tradeoffs"]


# --- Fix round 5: the HTML heading rule is broadened to the whole family ---
#
# Rounds 2 and 4 each used a pattern that modelled tag SYNTAX
# (`<h[1-6][^>]*>`), which requires the '>' on the same line. Both times a
# shape nobody had enumerated walked through -- most recently '<h2\n>', which
# a CommonMark renderer turns into a real <h2> because '<h2' at end of line
# opens an HTML block. The rule now matches the tag NAME anywhere on a line
# ('<h1'..'<h6' or '</h1'..'</h6', case-insensitive) and reasons no further.
# Prose has no legitimate use for an HTML heading tag; the one real case,
# documenting HTML inside a code example, sits in a fence where no heading
# check runs at all.


@pytest.mark.parametrize(
    "label, text",
    [
        ("plain open tag", "<h2>Status</h2>\nMore."),
        ("uppercase", "<H2>Status</H2>\nMore."),
        ("attributes", '<h2 class="x" id="s">Status</h2>\nMore.'),
        ("split tag", "<h2\n>Status</h2>\nMore."),
        ("split tag with attributes", '<h2\n  class="x">Status</h2>\nMore.'),
        ("closing tag alone on its line", "Status\n</h2>\nMore."),
        ("indented open tag", "   <h3>Status</h3>\nMore."),
        ("indented split tag", "   <h3\n>Status</h3>\nMore."),
        ("h1", "<h1>Status</h1>\nMore."),
        ("h6", "<h6>Status</h6>\nMore."),
        ("whitespace inside the tag", "<h2 >Status</h2>\nMore."),
        ("tag mid-sentence", "See <h2>Status</h2> above.\nMore."),
    ],
)
def test_validate_prose_rejects_every_html_heading_tag_shape(label, text):
    with pytest.raises(ValueError, match="heading"):
        validate_prose({
            "recommendation": "Use Leiden.",
            "tradeoffs": text,
            "open_questions": "x",
        })


def test_validate_prose_allows_an_html_heading_inside_a_backtick_fence():
    """The fence exemption applies to HTML exactly as it does to '## Status':
    someone documenting HTML in a code example is a real case, and the tag is
    code content there, not a heading."""
    prose = validate_prose({
        "recommendation": "Use Leiden.",
        "tradeoffs": "Render it as:\n```html\n<h2>Status</h2>\n</h2>\n```\nDone.",
        "open_questions": "x",
    })

    assert "<h2>Status</h2>" in prose["tradeoffs"]


def test_validate_prose_allows_an_html_heading_inside_a_tilde_fence():
    prose = validate_prose({
        "recommendation": "Use Leiden.",
        "tradeoffs": "Render it as:\n~~~\n<h2\n>Status</h2>\n~~~\nDone.",
        "open_questions": "x",
    })

    assert "<h2" in prose["tradeoffs"]


def test_validate_prose_still_allows_prose_with_no_html_heading_tag():
    """The broad rule keys on '<h' + a digit, so ordinary prose -- other
    tags, and bare comparison operators -- is untouched."""
    prose = validate_prose({
        "recommendation": "Use Leiden.",
        "tradeoffs": "Leiden scales when n<half the cells, and hclust is slower.",
        "open_questions": "Is <b>resolution</b> stable? See harmony too.",
    })

    assert "n<half" in prose["tradeoffs"]
    assert "<b>resolution</b>" in prose["open_questions"]


# --- Fix round 1, finding 3: an unrecognised key must raise, not be dropped ---


def test_validate_prose_rejects_an_unexpected_key():
    with pytest.raises(ValueError, match="notes"):
        validate_prose({
            "recommendation": "Use Leiden.",
            "tradeoffs": "x",
            "open_questions": "y",
            "notes": "extra",
        })


# --- Task 9 fix round 1, finding 2: a citation lint enforced in code, not
# only requested in the prompt. Reproduces the exact defect an eyeball
# review caught once: an opening sentence with no [id: ...] marker while its
# neighbours carried one.


def test_check_prose_is_cited_passes_when_every_sentence_has_a_marker():
    """Marker sits BEFORE the terminal period, matching real generated
    prose (e.g. '... communities [id: traag2019].'), not after it -- that
    placement is what keeps the marker inside the same sentence chunk once
    split on sentence-ending punctuation."""
    _check_prose_is_cited({
        "recommendation": (
            "Use Leiden [id: a]. It guarantees connectivity [id: a]."
        ),
        "tradeoffs": "Louvain is faster [id: b].",
        "open_questions": "Resolution selection is unresolved [id: a].",
    })


def test_check_prose_is_cited_raises_on_the_historical_defect_shape():
    """The exact shape that shipped once: a topic sentence with no marker,
    directly followed by a cited sentence in the same paragraph."""
    with pytest.raises(ValueError, match=r"\[id: \.\.\.\] citation marker"):
        _check_prose_is_cited({
            "recommendation": (
                "Use the Leiden method implemented in Scanpy. "
                "Leiden guarantees well-connected communities [id: a]."
            ),
            "tradeoffs": "Louvain is faster [id: b].",
            "open_questions": "Resolution selection is unresolved [id: a].",
        })


def test_check_prose_is_cited_names_the_offending_section_and_sentence():
    with pytest.raises(ValueError) as excinfo:
        _check_prose_is_cited({
            "recommendation": "Use Leiden [id: a].",
            "tradeoffs": "Louvain is a legacy choice.",
            "open_questions": "Resolution selection [id: a].",
        })

    assert "tradeoffs" in str(excinfo.value)
    assert "Louvain is a legacy choice." in str(excinfo.value)


def test_check_prose_is_cited_allows_a_sentence_wrapped_across_two_lines():
    """A sentence the model happened to wrap at a line break is still one
    sentence with one trailing marker, not two sentences where the first
    looks unmarked."""
    _check_prose_is_cited({
        "recommendation": (
            "Leiden guarantees well-connected communities across every\n"
            "modality studied here [id: a]."
        ),
        "tradeoffs": "x [id: a].",
        "open_questions": "y [id: a].",
    })


def test_check_prose_is_cited_skips_fenced_code_blocks():
    """A code example has no claim to cite, same fence tracking as
    validate_prose."""
    _check_prose_is_cited({
        "recommendation": "Use Leiden [id: a].",
        "tradeoffs": "Example:\n```\nsc.tl.leiden(adata)\nno marker here\n```\nSee above [id: a].",
        "open_questions": "x [id: a].",
    })


def test_synthesize_prose_rejects_an_uncited_sentence_end_to_end():
    """The lint wired into the real pipeline: a payload that passes
    validate_prose (clean ASCII, no headings, closed fences) but leaves one
    sentence uncited must still be rejected by synthesize_prose."""
    from unittest.mock import patch

    payload = {
        "recommendation": "Use the Leiden method implemented in Scanpy.",
        "tradeoffs": "Louvain is faster [id: a].",
        "open_questions": "Resolution selection is unresolved [id: a].",
    }

    with patch(
        "litintel.enrich.ai_client._call_gemini",
        return_value=(payload, {"input": 1}),
    ), patch("litintel.enrich.ai_client._get_gemini_client", return_value="CLIENT"):
        with pytest.raises(ValueError, match="citation marker"):
            synthesize_prose("clustering", [_record()], "gemini-x", "MEDIUM")


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

    # Each sentence carries its own [id: ...] marker, placed before the
    # terminal period the way real generated prose does (fix round 1,
    # finding 2 added _check_prose_is_cited(), which now runs on every
    # synthesize_prose call and would otherwise reject this fixture as
    # uncited).
    fake_payload = {
        "recommendation": (
            "Use Leiden via leidenalg "
            "[id: 2026-08-02-traag2019-louvain-connectivity]."
        ),
        "tradeoffs": (
            "Louvain is faster but less reliably connected "
            "[id: 2026-08-02-traag2019-louvain-connectivity]."
        ),
        "open_questions": (
            "Resolution parameter selection is unresolved "
            "[id: 2026-08-02-traag2019-louvain-connectivity]."
        ),
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
    assert "Use Leiden via leidenalg" in text
    assert "Louvain is faster but less reliably connected" in text
    assert "Resolution parameter selection is unresolved" in text

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
