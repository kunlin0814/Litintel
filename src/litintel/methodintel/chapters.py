"""Deterministic assembly of a layer 2 chapter from its layer 1 records.

Everything here is pure: same records in, same bytes out, no network. That is
what makes a chapter's git diff mean "the evidence changed" rather than "the
model phrased it differently" (spec D5). The model's contribution enters only
as the `prose` dict, produced by synthesis.py (Task 8).
"""

from __future__ import annotations

from litintel.methodintel.records import ReferenceRecord


# Record kinds that ASSERT a new current status for a (method, modality) pair,
# so they belong in the "What changed" section rather than only in the
# bibliography. Checked against every kind records.py::ALLOWED_KINDS allows,
# not just the one a real record exposed as missing (Task 11 fix round 1):
#   deprecation    -- retires a method's status. Transition.
#   adaptation     -- sets a modality-specific correction to a borrowed
#                      method's status. Transition.
#   best_practice  -- asserts what the current default IS for a modality
#                      (e.g. "Leiden is the current default for spatial
#                      ATAC"). Transition -- this is the kind Task 11's
#                      acceptance run used and "What changed" missed it.
#   benchmark      -- comparative measurement supporting a status (e.g. a
#                      connectivity proof); it backs a recommendation but
#                      does not itself assert the new state. Not a
#                      transition.
#   personal       -- a hand-written observation from real pipeline work
#                      (spec Feed 3); evidentiary like benchmark, but not an
#                      assertion of a new status on its own. Not a
#                      transition.
#   usage          -- a real-run signal of what was actually used (spec Feed
#                      4); records a fact about a paper, not a status change.
#                      Not a transition.
#   seed           -- taxonomy provenance bookkeeping (`concept: null`);
#                      never about a method's status. Not a transition.
_TRANSITION_KINDS: frozenset[str] = frozenset({
    "deprecation", "adaptation", "best_practice",
})


def render_bibliography(
    records: list[ReferenceRecord],
) -> tuple[str, dict[str, int]]:
    """Numbered bibliography plus the record-id -> number map.

    Numbers are cosmetic and assigned here, at render time. The stable
    identifier is always the record id (spec 5.1). A record with no citation
    (e.g. kind="personal", source_ref.kind="personal_obs") never appears here
    -- it has nothing to cite.
    """
    cited = sorted(
        (r for r in records if r.citation is not None),
        key=lambda r: r.id,
    )

    numbers = {record.id: index for index, record in enumerate(cited, start=1)}
    lines = ["## References", ""]

    for record in cited:
        citation = record.citation
        lines.append(
            "%d. %s. %s (%d). %s:%s  [id: %s]"
            % (
                numbers[record.id],
                citation.first_author,
                citation.journal,
                citation.year,
                record.source_ref.kind.value,
                record.source_ref.value,
                record.id,
            )
        )

    return "\n".join(lines), numbers


def render_status_table(records: list[ReferenceRecord]) -> str:
    """One row per (method, implementation, modality) triple.

    Modality is a column rather than a separate chapter because a young field
    borrows its methods wholesale from a mature one, so per-modality chapters
    would be near-duplicates (spec 3.4.4). Method and implementation stay
    separate columns rather than one string -- one algorithm ships in several
    packages with different pipeline-fit consequences (spec 5.2).
    """
    rows: dict[tuple[str, str, str], str] = {}
    for record in records:
        implementations = ", ".join(record.implementations) or "-"
        for method in record.methods:
            for modality in record.modality or ["unspecified"]:
                rows.setdefault(
                    (method, implementations, modality),
                    record.recorded.isoformat(),
                )

    lines = [
        "## Status",
        "",
        "| Method | Implementation | Modality | Last reviewed |",
        "|---|---|---|---|",
    ]
    for (method, implementations, modality), reviewed in sorted(rows.items()):
        lines.append(
            "| %s | %s | %s | %s |" % (method, implementations, modality, reviewed)
        )

    return "\n".join(lines)


def render_borrowed_and_broken(records: list[ReferenceRecord]) -> str:
    """Per modality: where a borrowed method breaks, or that nobody checked.

    An absent adaptation record means unaudited, never clean. Rendering
    silence as an open question is the whole point (spec 3.4.4). This
    includes the degenerate case of zero records at all -- a concept that has
    not been populated yet (e.g. `load_concept_records` returned []) is "no
    evidence recorded yet", not a finished, clean chapter.
    """
    lines = ["## Borrowed and broken", ""]

    modalities = sorted({m for r in records for m in r.modality})
    if not modalities:
        lines.append(
            "- No records for this concept yet. This concept is **not "
            "audited** for any modality: it is an open question, not a "
            "clean chapter."
        )
        return "\n".join(lines).rstrip()

    adaptations: dict[str, list[ReferenceRecord]] = {m: [] for m in modalities}
    for record in records:
        if record.kind == "adaptation":
            for modality in record.modality:
                adaptations[modality].append(record)

    for modality in modalities:
        lines.append("### %s" % modality)
        lines.append("")
        if adaptations[modality]:
            for record in sorted(adaptations[modality], key=lambda r: r.id):
                lines.append("- %s  [id: %s]" % (record.body.strip(), record.id))
        else:
            lines.append(
                "- No adaptation record. This modality is **not audited** "
                "for whether the borrowed method's assumptions hold here."
            )
        lines.append("")

    return "\n".join(lines).rstrip()


def render_what_changed(records: list[ReferenceRecord]) -> str:
    """Status transitions, id order, each citing a record id.

    Cites ids and never bibliography numbers: inserting a claim renumbers the
    bibliography, and the changelog must survive that (spec 5.1). Records are
    sorted by id, which is date-prefixed and therefore chronological
    (records.py::load_concept_records docstring).
    """
    transitions = sorted(
        (r for r in records if r.kind in _TRANSITION_KINDS),
        key=lambda r: r.id,
    )

    lines = ["## What changed", ""]
    if not transitions:
        lines.append("- No status transitions recorded yet.")
    for record in transitions:
        lines.append(
            "- %s: %s  [id: %s]"
            % (record.recorded.isoformat(), record.body.strip(), record.id)
        )

    return "\n".join(lines)


def assemble_chapter(
    concept: str,
    records: list[ReferenceRecord],
    prose: dict[str, str],
) -> str:
    """Full chapter text. Deterministic given records and prose.

    `records` should already be scoped to `concept` (e.g. via
    `load_concept_records`); this function does not filter by
    `record.concept` itself, since Layer 1 explicitly allows `concept: null`
    for records not yet triaged (spec 3.4.2).
    """
    bibliography, _ = render_bibliography(records)

    return "\n\n".join([
        "# %s" % concept,
        "<!-- GENERATED from references/%s/. Do not hand-edit (spec D5). -->" % concept,
        "## Current recommendation",
        prose["recommendation"].strip(),
        render_status_table(records),
        render_borrowed_and_broken(records),
        "## Tradeoffs",
        prose["tradeoffs"].strip(),
        render_what_changed(records),
        bibliography,
        "## Open questions",
        prose["open_questions"].strip(),
        "",
    ])
