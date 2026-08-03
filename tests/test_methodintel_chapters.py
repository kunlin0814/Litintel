import os
import sys
from datetime import date

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from litintel.methodintel.chapters import (
    assemble_chapter,
    render_bibliography,
    render_borrowed_and_broken,
    render_status_table,
    render_what_changed,
)
from litintel.methodintel.records import Citation, ReferenceRecord
from litintel.methodintel.schema import SourceRef


def _record(record_id, kind="benchmark", methods=None, modality=None, cited=True, body="Claim."):
    return ReferenceRecord(
        id=record_id,
        concept="clustering",
        modality=modality or ["scRNA"],
        methods=methods or ["Leiden"],
        kind=kind,
        recorded=date(2026, 8, 2),
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
    """Only deprecation/adaptation kinds are transitions; benchmark/usage are
    excluded; order is by record id (chronological), not input order."""
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


def test_what_changed_cites_record_ids_not_numbers():
    """Numbers renumber when a claim is inserted; ids never move (spec 5.1)."""
    chapter = assemble_chapter(
        "clustering",
        [_record("2026-08-02-traag2019-louvain-connectivity", kind="deprecation")],
        {"recommendation": "x", "tradeoffs": "y", "open_questions": "z"},
    )
    changed = chapter.split("## What changed")[1].split("## References")[0]

    assert "2026-08-02-traag2019-louvain-connectivity" in changed
