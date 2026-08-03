import os
import sys
from datetime import date

import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from litintel.methodintel.chapters import (
    assemble_chapter,
    render_bibliography,
    render_borrowed_and_broken,
    render_status_table,
    render_what_changed,
)
from litintel.methodintel.modality import ModalityError
from litintel.methodintel.records import Citation, ReferenceRecord
from litintel.methodintel.schema import SourceRef


def _record(record_id, kind="benchmark", methods=None, modality=None, cited=True,
            body="Claim.", recorded=date(2026, 8, 2)):
    return ReferenceRecord(
        id=record_id,
        concept="clustering",
        # `is None`, not `or`: an explicitly EMPTY modality list is a real
        # state a test needs to be able to construct.
        modality=["scRNA"] if modality is None else modality,
        methods=methods or ["Leiden"],
        kind=kind,
        recorded=recorded,
        source_ref=SourceRef(kind="doi", value="10.1000/%s" % record_id),
        citation=Citation(first_author="Traag", journal="Sci Rep", year=2019) if cited else None,
        confidence="high",
        body=body,
    )


def test_bibliography_numbers_from_one_in_id_order():
    block, numbers = render_bibliography([_record("b"), _record("a")])

    assert numbers == {"a": 1, "b": 2}
    assert "1. Traag" in block


def test_bibliography_includes_journal_and_year():
    block, _ = render_bibliography([_record("a")])

    assert "Sci Rep" in block
    assert "2019" in block


def test_uncited_records_are_excluded_from_bibliography():
    _, numbers = render_bibliography([_record("a"), _record("b", cited=False)])

    assert numbers == {"a": 1}


def test_status_table_has_a_modality_column():
    table = render_status_table([_record("a", methods=["Leiden"], modality=["spatial_atac"])])

    assert "Modality" in table
    assert "spatial_atac" in table
    assert "Leiden" in table


def test_status_table_keeps_method_and_implementation_apart():
    """A chapter that says 'use Squidpy' without naming the method has
    flattened the axes this system exists to keep (spec 5.2)."""
    record = _record("a", methods=["Leiden"])
    record.implementations = ["ArchR"]

    table = render_status_table([record])

    assert "Implementation" in table
    assert "Leiden" in table
    assert "ArchR" in table


def test_borrowed_and_broken_lists_adaptation_records():
    block = render_borrowed_and_broken([
        _record("a", kind="adaptation", modality=["spatial_rna"],
                body="Spatial autocorrelation violates the independence assumption."),
    ])

    assert "spatial_rna" in block
    assert "independence assumption" in block


def test_modality_without_adaptation_renders_as_an_open_question():
    """Empty is 'unaudited', never 'clean' (spec 3.4.4)."""
    block = render_borrowed_and_broken([_record("a", modality=["spatial_atac"])])

    assert "spatial_atac" in block
    assert "not audited" in block


def test_empty_concept_borrowed_and_broken_reads_as_open_not_clean():
    """Zero records at all (Task 9 has not populated a concept dir yet) must
    still be legible as an open question, never as a silently clean chapter
    (spec 3.4.4; parent task context re: load_concept_records returning [])."""
    block = render_borrowed_and_broken([])

    assert "## Borrowed and broken" in block
    assert "not audited" in block
    assert "No records" in block


def test_empty_concept_status_table_has_no_rows():
    """No records means no rows, not a fabricated row."""
    table = render_status_table([])

    assert "Modality" in table
    lines = [line for line in table.splitlines() if line.startswith("|")]
    # only the header row and the separator row -- no data rows.
    assert len(lines) == 2


def test_assemble_chapter_has_every_required_section():
    prose = {
        "recommendation": "Use Leiden.",
        "tradeoffs": "Louvain is faster.",
        "open_questions": "Resolution selection is unresolved.",
    }

    chapter = assemble_chapter("clustering", [_record("a")], prose)

    for heading in (
        "# clustering",
        "## Current recommendation",
        "## Status",
        "## Borrowed and broken",
        "## Tradeoffs",
        "## What changed",
        "## References",
        "## Open questions",
    ):
        assert heading in chapter


def test_assemble_chapter_on_empty_concept_does_not_crash():
    prose = {"recommendation": "x", "tradeoffs": "y", "open_questions": "z"}

    chapter = assemble_chapter("clustering", [], prose)

    assert "## Borrowed and broken" in chapter
    assert "not audited" in chapter


def test_assembly_is_deterministic():
    prose = {"recommendation": "x", "tradeoffs": "y", "open_questions": "z"}
    records = [_record("b"), _record("a")]

    assert assemble_chapter("clustering", records, prose) == assemble_chapter(
        "clustering", records, prose
    )


def test_assembly_is_byte_identical_across_repeated_calls():
    """D5: same records in, same bytes out, not just == on this run's objects."""
    prose = {"recommendation": "x", "tradeoffs": "y", "open_questions": "z"}
    records = [
        _record("2026-08-02-b", modality=["scRNA", "spatial_rna"]),
        _record("2026-08-02-a", kind="adaptation", modality=["spatial_rna"]),
    ]

    first = assemble_chapter("clustering", records, prose).encode("utf-8")
    second = assemble_chapter("clustering", records, prose).encode("utf-8")

    assert first == second


def test_render_what_changed_with_no_transitions_says_so_exactly():
    """render_what_changed is public and called directly by Task 8, so it
    needs its own pinning test, not just indirect coverage via
    assemble_chapter."""
    block = render_what_changed([_record("a", kind="benchmark"), _record("b", kind="usage")])

    assert block == "## What changed\n\n- No status transitions recorded yet."


def test_render_what_changed_orders_mixed_kinds_by_id():
    """Only deprecation/adaptation/best_practice kinds are transitions;
    benchmark/usage are excluded; order is by record id (chronological), not
    input order."""
    block = render_what_changed([
        _record("2026-08-02-c", kind="benchmark", body="Not a transition."),
        _record("2026-08-02-b", kind="adaptation", body="Second transition."),
        _record("2026-08-02-a", kind="deprecation", body="First transition."),
    ])

    assert "Not a transition." not in block
    first_index = block.index("First transition.")
    second_index = block.index("Second transition.")
    assert first_index < second_index
    assert "[id: 2026-08-02-a]" in block
    assert "[id: 2026-08-02-b]" in block


def test_render_what_changed_includes_best_practice_transitions():
    """Task 11 fix round 1: a `kind: best_practice` record that sets a new
    current default (e.g. Leiden for spatial ATAC) is a status transition and
    must appear in "What changed" -- the acceptance run found this section
    blind to this kind entirely."""
    block = render_what_changed([
        _record("2026-08-02-a", kind="best_practice", body="New default set."),
        _record("2026-08-02-b", kind="benchmark", body="Not a transition."),
    ])

    assert "New default set." in block
    assert "[id: 2026-08-02-a]" in block
    assert "Not a transition." not in block


def test_what_changed_cites_record_ids_not_numbers():
    """Numbers renumber when a claim is inserted; ids never move (spec 5.1)."""
    chapter = assemble_chapter(
        "clustering",
        [_record("2026-08-02-traag2019-louvain-connectivity", kind="deprecation")],
        {"recommendation": "x", "tradeoffs": "y", "open_questions": "z"},
    )
    changed = chapter.split("## What changed")[1].split("## References")[0]

    assert "2026-08-02-traag2019-louvain-connectivity" in changed


# ---------------------------------------------------------------------------
# "Last reviewed" must report the NEWEST record on a row, not the oldest.
# ---------------------------------------------------------------------------

def test_last_reviewed_reports_the_newest_record_on_the_row():
    """load_concept_records returns ascending id order and ids are
    date-prefixed, so the FIRST record on a triple is the OLDEST. A
    setdefault here reported a January date for a triple that had an August
    record -- stale currency in the deterministic half of a base whose whole
    selling point is currency."""
    table = render_status_table([
        _record("2026-01-15-a", methods=["Leiden"], recorded=date(2026, 1, 15)),
        _record("2026-08-02-b", methods=["Leiden"], recorded=date(2026, 8, 2)),
    ])

    row = [line for line in table.splitlines() if line.startswith("| Leiden")][0]
    assert "2026-08-02" in row
    assert "2026-01-15" not in row


def test_last_reviewed_is_independent_of_input_order():
    """Same two records, newest first -- the answer must not depend on the
    order they happen to arrive in."""
    older = _record("2026-01-15-a", methods=["Leiden"], recorded=date(2026, 1, 15))
    newer = _record("2026-08-02-b", methods=["Leiden"], recorded=date(2026, 8, 2))

    assert render_status_table([older, newer]) == render_status_table([newer, older])
    assert "2026-08-02" in render_status_table([newer, older])


def test_distinct_triples_keep_their_own_dates():
    """Taking the newest date per ROW must not leak one row's date onto
    another row that genuinely was reviewed earlier."""
    table = render_status_table([
        _record("2026-01-15-a", methods=["Louvain"], recorded=date(2026, 1, 15)),
        _record("2026-08-02-b", methods=["Leiden"], recorded=date(2026, 8, 2)),
    ])

    louvain_row = [l for l in table.splitlines() if l.startswith("| Louvain")][0]
    leiden_row = [l for l in table.splitlines() if l.startswith("| Leiden")][0]
    assert "2026-01-15" in louvain_row
    assert "2026-08-02" in leiden_row


# ---------------------------------------------------------------------------
# The renderer shares one modality vocabulary with the writer.
# ---------------------------------------------------------------------------

def test_assemble_chapter_rejects_an_assay_name_as_a_modality():
    """The reproduced C2 shape: a record carrying "H&E" rendered a status row
    and a `### H&E` section reading "not audited". The renderer checks the
    same vocabulary the writer gates on (modality.py), so a poisoned record
    fails loudly at generation instead of quietly becoming a chapter section."""
    prose = {"recommendation": "x", "tradeoffs": "y", "open_questions": "z"}

    with pytest.raises(ModalityError) as excinfo:
        assemble_chapter("clustering", [_record("a", modality=["H&E"])], prose)

    assert "H&E" in str(excinfo.value)


# ---------------------------------------------------------------------------
# Section order is a containment decision: prose cannot suppress determinism.
# ---------------------------------------------------------------------------

def test_every_deterministic_section_precedes_every_prose_section():
    """Prose is inserted verbatim, so anything structural it opens propagates
    DOWNWARD. With prose last, the blast radius of a prose defect is prose."""
    prose = {"recommendation": "r", "tradeoffs": "t", "open_questions": "o"}

    chapter = assemble_chapter("clustering", [_record("a")], prose)

    deterministic = [
        chapter.index("## Status"),
        chapter.index("## Borrowed and broken"),
        chapter.index("## What changed"),
        chapter.index("## References"),
    ]
    model_authored = [
        chapter.index("## Current recommendation"),
        chapter.index("## Tradeoffs"),
        chapter.index("## Open questions"),
    ]

    assert deterministic == sorted(deterministic)
    assert model_authored == sorted(model_authored)
    assert max(deterministic) < min(model_authored)


def test_unclosed_html_block_in_prose_cannot_suppress_a_deterministic_heading():
    """The structural half of the C1 fix, measured with a real CommonMark
    renderer rather than by reading the text.

    An unclosed `<!--` runs to end of document -- a blank line does not end a
    CommonMark HTML block of type 2. validate_prose now rejects this shape,
    but enumeration has leaked six times, so the ORDER is what has to hold:
    even when the construct reaches assemble_chapter, every DETERMINISTIC
    heading must still render. Only prose headings below the defect are lost.

    markdown-it-py is a test-only oracle already present in this venv; it is
    imported through importorskip so it never becomes a shipped dependency."""
    markdown_it = pytest.importorskip("markdown_it")
    prose = {
        "recommendation": "Use Leiden.\n<!-- an opener the model never closed",
        "tradeoffs": "Louvain is faster.",
        "open_questions": "Resolution selection is unresolved.",
    }

    chapter = assemble_chapter("clustering", [_record("a")], prose)
    rendered = markdown_it.MarkdownIt("commonmark").render(chapter)

    for heading in ("Status", "Borrowed and broken", "What changed", "References"):
        assert ">%s<" % heading in rendered, heading
    # Prose headings below the unclosed opener are swallowed -- that is the
    # damage, and it is now confined to the model-authored half.
    assert ">Tradeoffs<" not in rendered
    assert ">Open questions<" not in rendered


def test_records_with_no_modality_are_not_reported_as_no_records():
    """Once map_data_types stopped guessing a modality from an assay name, a
    paper whose only assay was H&E started producing a real record with an
    empty modality list. Reporting that as "No records for this concept yet"
    would be false -- and this is the deterministic half."""
    block = render_borrowed_and_broken([_record("a", modality=[])])

    assert "not audited" in block
    assert "No records for this concept yet" not in block
    assert "1 record(s)" in block
