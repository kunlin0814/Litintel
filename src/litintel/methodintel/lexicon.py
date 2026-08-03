"""Parse LEXICON.md into concept entries and a label -> concept alias map.

The lexicon is authored by hand and read by machine, so parsing is deliberately
forgiving about prose and strict about structure: a level-2 heading opens a
concept, a "Question:" line (possibly wrapped across source lines) defines it,
and the first column of the following table holds its labels.

"Unplaced" is not a concept (spec 3.4.2: a null concept is legal and preferred
over a guess) -- its terms are known to the lexicon but deliberately carry no
concept yet. They are tracked by parse_unplaced_terms, a separate function,
rather than forced into ConceptEntry (whose `concept` field is non-optional):
that keeps "this term is unknown to the lexicon" and "this term is known but
deliberately unplaced" observably different states, which is the distinction
the design depends on (an unplaced term must never silently resolve through
CONCEPT_ALIASES to a concept it was parked for lacking).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List

from pydantic import BaseModel


# Sections that look like concepts but are not. "Unplaced" holds terms that are
# deliberately unattached (spec 3.4.2) -- an unplaced term must never become an
# alias, or it would silently acquire the meaning it was parked for lacking.
_NON_CONCEPT_HEADINGS: frozenset[str] = frozenset({"unplaced"})

_HEADING = re.compile(r"^##\s+(?P<name>.+?)\s*$")
_QUESTION = re.compile(r"^Question:\s*(?P<text>.+?)\s*$")
_TABLE_ROW = re.compile(r"^\|\s*(?P<first>[^|]+?)\s*\|")
_TABLE_DIVIDER = re.compile(r"^\|[\s:-]+\|")

# First-column header cells to skip. Concept tables head with "Label"; the
# Unplaced table heads with "Term" -- both are structure, not data.
_HEADER_CELLS: frozenset[str] = frozenset({"label", "term"})


class ConceptEntry(BaseModel):
    concept: str
    question: str
    labels: List[str]


def _parse(path: Path) -> "tuple[list[ConceptEntry], list[str]]":
    """Single pass over the file: (concept entries, unplaced terms).

    One pass rather than two separate scans because both readers below need
    the same section boundaries; splitting them would just re-detect the same
    headings and table rows twice.
    """
    entries: list[ConceptEntry] = []
    unplaced: list[str] = []
    current: dict | None = None
    in_unplaced = False
    accumulating_question = False

    for line in Path(path).read_text().splitlines():
        heading = _HEADING.match(line)
        if heading:
            if current is not None:
                entries.append(ConceptEntry(**current))
            name = heading.group("name")
            in_unplaced = name.strip().lower() in _NON_CONCEPT_HEADINGS
            current = None if in_unplaced else {
                "concept": name,
                "question": "",
                "labels": [],
            }
            accumulating_question = False
            continue

        if current is None and not in_unplaced:
            continue

        if accumulating_question:
            stripped = line.strip()
            is_continuation = bool(
                stripped
                and not _TABLE_DIVIDER.match(line)
                and not _TABLE_ROW.match(line)
            )
            if is_continuation:
                current["question"] = current["question"] + " " + stripped
                continue
            accumulating_question = False
            # Not a continuation line -- fall through and process it normally
            # (it may be the blank line before the table, or the table itself).

        question = _QUESTION.match(line)
        if question:
            if current is not None:
                current["question"] = question.group("text")
                accumulating_question = True
            continue

        if _TABLE_DIVIDER.match(line):
            continue

        row = _TABLE_ROW.match(line)
        if row:
            label = row.group("first").strip()
            if not label or label.lower() in _HEADER_CELLS:
                continue
            if in_unplaced:
                unplaced.append(label)
            elif current is not None:
                current["labels"].append(label)
            continue

    if current is not None:
        entries.append(ConceptEntry(**current))

    return entries, unplaced


def parse_lexicon(path: Path) -> list[ConceptEntry]:
    entries, _ = _parse(path)
    return entries


def parse_unplaced_terms(path: Path) -> list[str]:
    """Terms sitting under the Unplaced heading: known to the lexicon, but
    with no concept assigned yet (spec 3.4.2). Never returned by
    parse_lexicon and never a key in build_concept_aliases -- callers use
    this function to tell a deliberately-unplaced term apart from a term the
    lexicon has never seen at all.
    """
    _, unplaced = _parse(path)
    return unplaced


def build_concept_aliases(entries: list[ConceptEntry]) -> dict[str, str]:
    """Lowercased label -> concept name, for tier 1 (free) query resolution.

    Only concept entries feed this map. An Unplaced term never becomes a
    ConceptEntry (see parse_unplaced_terms), so it can never appear here --
    it cannot silently resolve to a concept it was deliberately not assigned
    to (spec 3.4.2).

    Tier 2 -- semantic match against ConceptEntry.question -- is what catches a
    question phrased in words no label uses, and is out of scope for v1.
    """
    return {
        label.lower(): entry.concept
        for entry in entries
        for label in entry.labels
    }
