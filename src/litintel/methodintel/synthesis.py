"""The one model call: reference records -> chapter prose.

Kept apart from chapters.py so the deterministic assembly stays testable
without a network, and so the prompt -- which is where chapter behavior
actually lives -- sits in one readable place.
"""

from __future__ import annotations

import re
from pathlib import Path

from litintel.methodintel.chapters import assemble_chapter
from litintel.methodintel.records import ReferenceRecord, load_concept_records


_SECTIONS = ("recommendation", "tradeoffs", "open_questions")

# A Markdown heading line (leading whitespace allowed) inside model prose.
# assemble_chapter trusts prose verbatim, so a stray '#' line would render as
# a second, fabricated heading ahead of the real deterministic section that
# shares its name -- exactly the corruption the two-layer split exists to
# prevent (fix round 1, finding 1).
_HEADING_LINE = re.compile(r"^\s*#")

# Gemini runs in JSON mode here (ai_client._call_gemini is JSON-only), so the
# section split is enforced by the schema rather than by parsing labelled text.
PROSE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "recommendation": {"type": "string"},
        "tradeoffs": {"type": "string"},
        "open_questions": {"type": "string"},
    },
    "required": list(_SECTIONS),
}

_SYSTEM_PROMPT = (
    "You write chapters for a curated bioinformatics method knowledge base. "
    "You write ASCII only and you never assert anything the supplied records "
    "do not support. You never emit Markdown headings -- no line may start "
    "with '#', with or without leading whitespace -- because your prose is "
    "inserted directly into a chapter that already has its own headings; "
    "write plain prose paragraphs only."
)

_PROMPT_HEADER = """You are writing one chapter of a curated bioinformatics
method knowledge base. The chapter answers: which computational method is
currently correct for the '%s' analysis concept, and why.

Write ASCII only. No emoji, no Unicode dashes or arrows. Use -> and >= and --.

Write only from the records below. Every factual claim must be traceable to a
record; append the record's id in square brackets after the claim, like
[id: 2026-08-02-traag2019-louvain-connectivity]. If the records do not support
a claim, do not make it -- say the evidence is absent instead. Do not add
knowledge from your training data; an unsupported sentence is a defect, not a
helpful addition.

Where the records disagree by modality, say so rather than averaging them. A
method that is standard for scRNA may be untested for spatial ATAC, and that
distinction is the most valuable thing this chapter carries.

Return a JSON object with exactly these three string fields:

  recommendation  -- one method, one implementation, one sentence, plus at most
                     three sentences of justification. Name the method AND the
                     package; "use Squidpy" without naming the method is wrong.
  tradeoffs       -- when each option becomes the better choice and what it costs.
  open_questions  -- what these records leave unresolved.

RECORDS
=======
"""


def build_prose_prompt(concept: str, records: list[ReferenceRecord]) -> str:
    blocks = []
    for record in records:
        modality = ", ".join(record.modality) or "unspecified"
        methods = ", ".join(record.methods) or "none named"
        implementations = ", ".join(record.implementations) or "none named"
        blocks.append(
            "[id: %s] kind=%s modality=%s methods=%s implementations=%s confidence=%s\n%s"
            % (record.id, record.kind, modality, methods, implementations,
               record.confidence, record.body.strip())
        )

    return (_PROMPT_HEADER % concept) + "\n\n".join(blocks) + "\n"


def validate_prose(payload: dict) -> dict[str, str]:
    """Check the model's JSON object. Raises on anything short of clean prose.

    Empty is rejected because assemble_chapter would otherwise emit a heading
    with nothing under it, which reads as "nothing to say here" rather than as
    the generation failure it is.

    A Markdown heading line inside a section is rejected, never escaped or
    stripped (fix round 1, finding 1): assemble_chapter inserts prose
    verbatim, so a model-emitted '#' line would render as a second,
    fabricated heading ahead of the real deterministic section sharing its
    name -- the one thing the two-layer split (chapters.py vs. this module)
    exists to prevent. Chapters are Layer 2 and regenerate on command (spec
    D5), so failing loud here costs one re-run, not a corrupted chapter.

    An unrecognised key is also rejected -- same fail-loud posture as
    records.py's `extra="forbid"`. PROSE_SCHEMA already constrains what the
    model may return; an extra key means schema drift or the model ignoring
    the schema, and either should surface rather than pass through silently.
    """
    unexpected = set(payload) - set(_SECTIONS)
    if unexpected:
        raise ValueError(
            "model response has unexpected key(s): %s" % ", ".join(sorted(unexpected))
        )

    prose = {}
    for section in _SECTIONS:
        value = payload.get(section)
        if not isinstance(value, str) or not value.strip():
            raise ValueError("model response is missing or empty section %s" % section)
        for line in value.splitlines():
            if _HEADING_LINE.match(line):
                raise ValueError(
                    "model response section %s contains a Markdown heading "
                    "line %r -- prose must not emit headings"
                    % (section, line.strip())
                )
        prose[section] = value.strip()

    return prose


def synthesize_prose(
    concept: str,
    records: list[ReferenceRecord],
    model: str,
    thinking: str,
) -> dict[str, str]:
    """Call Gemini through the existing Vertex path and validate the result.

    Reuses ai_client's client factory and call wrapper rather than building a
    second Vertex client -- one auth path, one retry policy, one place to fix.
    """
    from litintel.enrich.ai_client import _call_gemini, _get_gemini_client

    payload, _usage = _call_gemini(
        client=_get_gemini_client(),
        model=model,
        system_prompt=_SYSTEM_PROMPT,
        user_prompt=build_prose_prompt(concept, records),
        schema=PROSE_SCHEMA,
        thinking_level=thinking,
    )
    return validate_prose(payload)


# Used only when a KNOWN concept (validated by the caller against LEXICON.md)
# has zero records yet -- a legitimate state (spec 3.4.2), not a defect. There
# is nothing in the records to synthesize prose from, so the model is never
# called for it: an empty-record prompt would ask the model to write from no
# evidence, which is exactly the hallucination risk this whole design exists
# to avoid. Phrasing is distinct from, and does not contradict,
# chapters.py::render_borrowed_and_broken's "not audited" wording -- that
# substring is asserted on by existing tests and must survive untouched.
_NO_EVIDENCE_PROSE: dict[str, str] = {
    "recommendation": (
        "No recommendation yet -- no records are recorded for this concept "
        "(see Borrowed and broken)."
    ),
    "tradeoffs": (
        "No tradeoffs to compare yet -- no records are recorded for this concept."
    ),
    "open_questions": (
        "Whether any method is validated for this concept at all is itself "
        "the open question -- no records are recorded yet."
    ),
}


def generate_chapter(
    methods_root: Path,
    concept: str,
    model: str,
    thinking: str,
) -> str:
    """Full chapter text for one concept.

    `methods_root` is expected already-resolved (records.py::resolve_methods_root)
    -- this function does not re-expand or re-validate the path, that check has
    exactly one home (core directive A8).

    A KNOWN concept with zero records (see caller: the CLI validates the
    concept name against LEXICON.md before this is ever called) still
    produces a chapter -- chapters.py already renders the deterministic
    sections' "not audited" state for it, so this only needs to supply
    placeholder prose instead of calling the model. This is deliberately
    different from an UNKNOWN concept name, which the CLI rejects before
    reaching this function at all; conflating the two states here would
    erase the distinction the design depends on.
    """
    records = load_concept_records(Path(methods_root), concept)
    if records:
        prose = synthesize_prose(concept, records, model, thinking)
    else:
        prose = dict(_NO_EVIDENCE_PROSE)

    return assemble_chapter(concept, records, prose)
