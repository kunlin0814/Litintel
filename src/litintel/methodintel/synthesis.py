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

# Every heading form CommonMark/GitHub will actually render, so a model
# response cannot fabricate a heading by switching syntax (fix round 1 caught
# ATX only; fix round 2 closes the setext and HTML bypasses the re-review
# found live). assemble_chapter trusts prose verbatim, so any of these would
# render as a second, fabricated heading ahead of the real deterministic
# section sharing its name -- the corruption the two-layer split exists to
# prevent.
_ATX_HEADING = re.compile(r"^\s*#")
# Deliberately BROAD: any '<h1'..'<h6' or '</h1'..'</h6' anywhere on a line,
# whatever follows it. The earlier precise form (`<h[1-6][^>]*>`) required the
# '>' on the same line, so '<h2\n>Status</h2>' -- which a CommonMark renderer
# turns into a real <h2>, because '<h2' at end of line opens an HTML block --
# walked straight through. That precise rule leaked twice, so the shape of the
# rule is the defect, not the pattern inside it: match the tag NAME and stop
# reasoning about tag syntax. The false-positive cost is ~nil -- prose about
# computational methods has no reason to contain '<h2' outside a code example,
# and code examples are inside a fence, where no heading check runs at all.
_HTML_HEADING = re.compile(r"</?h[1-6]", re.IGNORECASE)
# Setext underline: 0-3 leading spaces (CommonMark's own allowance -- 4+
# leading spaces makes it an indented code block, not a heading, so the cap
# is load-bearing, not cosmetic; fix round 3 finding 5), then a line of only
# '=' or only '-' characters. Whether it is a heading underline or a
# legitimate horizontal rule/prose divider depends entirely on what precedes
# it -- caught only when it directly follows a non-blank text line (checked
# at the call site, not in this regex), and never inside a fenced code block
# (also checked at the call site; fix round 3 finding 6).
_SETEXT_UNDERLINE = re.compile(r"^ {0,3}(=+|-+)\s*$")
# Fenced code block delimiters. This project takes no new dependency, so there
# is no real Markdown parser backing these; they are hand-rolled, but they
# follow CommonMark's two asymmetric rules exactly, because fix round 3's
# single on/off toggle got both wrong:
#
#   opening -- 0-3 leading spaces, then a run of 3+ backticks or 3+ tildes,
#              optionally followed by an info string (```python).
#   closing -- the SAME character as the opener, in a run at least as long,
#              and nothing after it but whitespace. A ``` run does not close
#              a ~~~ fence, and a shorter run does not close a longer one.
#
# Tracking the opening run (not a boolean) is what makes both rules
# expressible; an unclosed fence then falls out as "still holding a marker at
# end of section" (fix round 4).
_FENCE_OPEN = re.compile(r"^ {0,3}(?P<marker>`{3,}|~{3,})")
_FENCE_CLOSE = re.compile(r"^ {0,3}(?P<marker>`{3,}|~{3,})[ \t]*$")

# CommonMark HTML BLOCK types 2-5, as (opener, end condition). These are the
# other family of constructs that runs past a heading, and they are WORSE
# than an unclosed fence: a blank line ends HTML block types 6 and 7, but
# types 2-5 end ONLY at their own end condition, so an unclosed one runs to
# the end of the document. Measured on a real assembled chapter, a single
# unclosed '<!--' in prose left 2 of 9 headings standing.
#
# Order matters only for readability here, not for correctness: '<!--' and
# '<![CDATA[' both start '<!' but neither is followed by an ASCII letter, so
# the type-4 pattern cannot shadow them.
#
# The structural fix is chapters.py's section order (prose last, so a prose
# defect can only reach prose). This check is the defence in depth: it names
# the section and the opener at the point of generation, where the model
# output is still traceable to a section, rather than leaving a corrupted
# chapter to be diagnosed later.
_HTML_BLOCK_OPENERS: tuple[tuple[re.Pattern, str], ...] = (
    (re.compile(r"^ {0,3}<!--"), "-->"),          # type 2, comment
    (re.compile(r"^ {0,3}<\?"), "?>"),            # type 3, processing instruction
    (re.compile(r"^ {0,3}<!\[CDATA\["), "]]>"),   # type 5, CDATA
    (re.compile(r"^ {0,3}<![A-Za-z]"), ">"),      # type 4, declaration (<!DOCTYPE)
)

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
    "do not support. You never emit a heading of any kind -- not an ATX "
    "heading ('#' at the start of a line), not a setext heading (a text line "
    "followed by a line of only '=' or only '-' characters), and not an HTML "
    "heading tag ('<h1>' through '<h6>') -- because your prose is inserted "
    "directly into a chapter that already has its own headings; write plain "
    "prose paragraphs only. If you open a fenced code block you must close it "
    "with the same delimiter, because an unclosed fence hides the chapter's "
    "own headings below it. The same applies to an HTML comment or "
    "declaration ('<!--', '<?', '<!DOCTYPE', '<![CDATA['): close it on the "
    "same line or do not write one at all. Cite only the record ids you were "
    "given; never invent an id."
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

EVERY sentence must carry at least one [id: ...] marker. There is no exemption
for a framing or lead-in sentence. Do not open a field with a scene-setter such
as "The records leave several key questions unresolved." or "The following
tradeoffs apply." -- it states no claim, so it cannot cite one, and it will be
rejected. Begin each field with its first real, cited claim.

Where the records disagree by modality, say so rather than averaging them. A
method that is standard for scRNA may be untested for spatial ATAC, and that
distinction is the most valuable thing this chapter carries.

A record's `modality` list is a hard boundary on every attribute it carries,
including `implementations` and `methods`: an implementation or method named
on a record applies ONLY to that record's own modality list, never to a
modality the record does not list. Never attach an implementation named on a
spatial-only record (for example Squidpy or Scanpy on a record scoped to
spatial_rna/spatial_atac) to a sentence about scRNA or scATAC, or to a
sentence that spans all modalities, unless a DIFFERENT record actually names
that implementation for that modality too. When one sentence must cover
several modalities and their implementation evidence differs, either name the
implementation per modality (e.g. "for scRNA ...; for spatial data, Squidpy or
Scanpy ...") or drop implementation specifics from the modality-general
sentence entirely and let the modality-specific sentence carry them. A
composite sentence that is true of the world but not backed by any single
record's stated modality scope is exactly the unsupported claim this prompt
already forbids.

Return a JSON object with exactly these three string fields:

  recommendation  -- one method, one implementation, one sentence, plus at most
                     three sentences of justification. Name the method AND the
                     package; "use Squidpy" without naming the method is wrong.
                     If the implementation differs by modality, say so per
                     modality rather than naming one implementation for all.
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

    A heading of any kind -- ATX, setext, or HTML -- is rejected, never
    escaped or stripped (fix round 1 finding 1; setext/HTML closed in fix
    round 2 after the re-reviewer found them as live bypasses):
    assemble_chapter inserts prose verbatim, so any of these would render as
    a second, fabricated heading ahead of the real deterministic section
    sharing its name -- the one thing the two-layer split (chapters.py vs.
    this module) exists to prevent. Chapters are Layer 2 and regenerate on
    command (spec D5), so failing loud here costs one re-run, not a
    corrupted chapter. A setext underline (a line of only '=' or only '-',
    with 0-3 leading spaces per CommonMark) is flagged ONLY when it directly
    follows a non-blank text line -- the same line following a blank line,
    or opening the section, is a legitimate horizontal rule/divider and must
    stay legal prose.

    The HTML rule is deliberately the BROAD one (fix round 5): any '<h1'
    through '<h6' or '</h1' through '</h6' on a line, whatever follows it,
    rather than a pattern that models tag syntax. Two rounds of precise
    patterns each leaked a shape nobody had listed -- most recently
    '<h2\\n>Status</h2>', which a renderer turns into a real <h2> because
    '<h2' at end of line opens a CommonMark HTML block. Matching the tag name
    and refusing to reason further is what makes the rule stop leaking, and
    it costs nothing: an HTML heading tag has no legitimate place in prose,
    and the one real case for writing one -- documenting HTML in a code
    example -- lives inside a fence, where no heading check runs.

    No heading check applies inside a fenced code block (fix round 3,
    finding 6): a dash line in a code example is ordinary prose about
    computational methods, not a heading, and over-rejecting it would
    hard-fail chapter generation on entirely normal content -- worse than the
    bypass it would be closing, since the bypass needs the model to misbehave
    while this would fire on correct output.

    A CommonMark HTML BLOCK of type 2-5 (`<!--`, `<?`, `<!DOCTYPE`,
    `<![CDATA[`) that is never closed is rejected for the same reason, and
    it is the worse case: a blank line ends HTML block types 6 and 7 but not
    these, so an unclosed one runs to the end of the assembled chapter
    (measured: 2 of 9 headings survived a single unclosed `<!--`). This is
    defence in depth behind the structural fix -- chapters.py now places
    every prose section BELOW every deterministic section, so a prose defect
    can only reach prose. Enumerating bypasses has failed repeatedly; the
    order is what bounds the damage, this check is what names it early.

    A fence that is never closed is itself rejected (fix round 4). Round 3's
    boolean toggle read an unclosed fence as "checking is off from here on",
    which looks safe and is the opposite: assemble_chapter concatenates this
    prose into a chapter, and an open fence swallows every deterministic
    heading BELOW it into an inert code block (measured: 2 of 8 headings
    survived). That is suppression of the deterministic half by the model
    half -- the same corruption as a fabricated heading, arriving from the
    other direction -- so it is caught here, at the section that caused it,
    rather than downstream in a chapter no longer traceable to a section.

    Non-ASCII content is rejected (fix round 2, finding 4): the system
    prompt asks for ASCII, but this project's ASCII-only rule does not get
    to depend on the model choosing to comply, since this text is written
    into a committed Markdown file. This also closes the two Unicode
    heading-lookalikes (fullwidth '#', lookalike letters) the re-reviewer
    found -- neither renders as a real Markdown/HTML heading, but both are
    non-ASCII regardless.

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

        try:
            value.encode("ascii")
        except UnicodeEncodeError as exc:
            raise ValueError(
                "model response section %s contains non-ASCII character %r "
                "at position %d"
                % (section, value[exc.start], exc.start)
            )

        lines = value.splitlines()
        # The opening fence run while inside a fence, "" while outside.
        open_fence = ""
        # (opener text, end condition) while inside a CommonMark HTML block of
        # type 2-5, None while outside.
        open_html: tuple[str, str] | None = None
        # The paragraph line a setext underline would underline, "" when there
        # is none. A fence delimiter, any line inside a fence, and any line of
        # an HTML block are not paragraph text, so a '-----' directly below one
        # is a thematic break, not a heading (confirmed against a CommonMark
        # renderer). Always a str, never False -- it is interpolated with %r
        # into the setext error message below.
        text_above = ""

        for line in lines:
            if open_fence:
                closing = _FENCE_CLOSE.match(line)
                if closing:
                    marker = closing.group("marker")
                    if marker[0] == open_fence[0] and len(marker) >= len(open_fence):
                        open_fence = ""
                text_above = ""
                continue

            if open_html is not None:
                if open_html[1] in line:
                    open_html = None
                text_above = ""
                continue

            opening = _FENCE_OPEN.match(line)
            if opening:
                open_fence = opening.group("marker")
                text_above = ""
                continue

            # An HTML block opener is checked BEFORE the heading rules: its
            # own line is HTML, not paragraph text, and everything up to the
            # end condition is inert. The end condition may sit on the opener
            # line itself ('<!-- note -->'), which is the normal, legal case.
            html_opened = False
            for pattern, end_condition in _HTML_BLOCK_OPENERS:
                match = pattern.match(line)
                if match is None:
                    continue
                if end_condition not in line[match.end():]:
                    open_html = (match.group(0).strip(), end_condition)
                html_opened = True
                break
            if html_opened:
                text_above = ""
                continue

            if _ATX_HEADING.match(line):
                raise ValueError(
                    "model response section %s contains an ATX heading "
                    "line %r -- prose must not emit headings"
                    % (section, line.strip())
                )
            if _HTML_HEADING.search(line):
                raise ValueError(
                    "model response section %s contains an HTML heading tag "
                    "on line %r -- prose must not emit headings"
                    % (section, line.strip())
                )
            if _SETEXT_UNDERLINE.match(line) and text_above:
                raise ValueError(
                    "model response section %s contains a setext heading "
                    "underline %r beneath the text %r -- prose must not "
                    "emit headings"
                    % (section, line.strip(), text_above)
                )

            text_above = line.strip()

        if open_fence:
            raise ValueError(
                "model response section %s opens a fenced code block with %r "
                "that is never closed -- an unclosed fence swallows every "
                "deterministic heading after it in the assembled chapter"
                % (section, open_fence)
            )

        if open_html is not None:
            raise ValueError(
                "model response section %s opens an HTML block with %r that "
                "is never closed by %r -- unlike a fence, a blank line does "
                "not end this block, so it swallows every heading after it to "
                "the end of the chapter"
                % (section, open_html[0], open_html[1])
            )

        prose[section] = value.strip()

    return prose


# Sentence boundary for _check_prose_is_cited: a '.', '!' or '?' followed by
# whitespace. Not a real sentence parser (an "e.g." or a decimal would split
# wrong), which is an accepted gap (Task 9, fix round 1, finding 2) -- this
# lint only needs to catch a bare, unmarked sentence, not parse English.
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")

# One citation marker. The id is captured loosely (anything up to the closing
# bracket, empty included) so a MALFORMED marker is caught and named by the
# validity check below rather than skipped by a strict pattern that simply
# fails to see it.
_CITATION_MARKER = re.compile(r"\[id:(?P<record_id>[^\]]*)\]")

# A repeated 'id:' label inside a multi-id marker ('[id: a, id: b]').
_REPEATED_ID_LABEL = re.compile(r"^id:\s*", re.IGNORECASE)


def _strip_id_label(part: str) -> str:
    return _REPEATED_ID_LABEL.sub("", part.strip()).strip()


def _check_prose_is_cited(prose: dict[str, str], record_ids: set[str]) -> None:
    """Cheap post-validation lint: every prose sentence must carry [id: ...].

    The prompt only REQUESTS a citation on every claim; nothing enforced it,
    and Task 9's own generation shipped an opening recommendation sentence
    with no marker on the first attempt (caught only by an eyeball read).
    This closes that gap deterministically rather than relying on review to
    catch it every time.

    Deliberately NOT folded into validate_prose(): that function's own test
    suite exercises many marker-free fixtures to isolate the heading/fence/
    ASCII checks in isolation, and requiring a citation there would force
    every one of those fixtures to carry a marker for a property they are
    not testing. This runs once, after validate_prose has already passed,
    against real model output only.

    Fenced code blocks are skipped (same fence tracking as validate_prose):
    a code example has no claim to cite. Lines are joined with a space
    before sentence-splitting, not concatenated by newline, so a sentence
    the model wrapped across two lines is not mistaken for two sentences,
    one of which would then look unmarked.

    Every marker's id is also checked against `record_ids` -- the ids
    actually handed to the generation. Presence alone is not traceability:
    a marker citing a record that does not exist reads exactly like a real
    citation to a human and to the skill that consumes these chapters, and
    `[id: 2026-08-02-totally-made-up]` and a bare `[id: ]` both passed the
    presence-only check and would have been committed. `record_ids` is a
    required argument rather than an optional one: a default would let a
    caller silently keep the weaker check.
    """
    for section, text in prose.items():
        kept_lines = []
        open_fence = ""
        for line in text.splitlines():
            if open_fence:
                closing = _FENCE_CLOSE.match(line)
                if closing:
                    marker = closing.group("marker")
                    if marker[0] == open_fence[0] and len(marker) >= len(open_fence):
                        open_fence = ""
                continue

            opening = _FENCE_OPEN.match(line)
            if opening:
                open_fence = opening.group("marker")
                continue

            kept_lines.append(line)

        flattened = " ".join(kept_lines)
        for sentence in _SENTENCE_BOUNDARY.split(flattened):
            sentence = sentence.strip()
            if not sentence:
                continue
            if "[id:" not in sentence:
                raise ValueError(
                    "%s: sentence has no [id: ...] citation marker: %r"
                    % (section, sentence)
                )

        for match in _CITATION_MARKER.finditer(flattened):
            body = match.group("record_id")
            # One marker may carry several ids -- '[id: a, b]' and
            # '[id: a, id: b]' are both what the model actually writes when a
            # claim rests on two records (both forms appeared on live
            # regenerations), and either is the honest citation for such a
            # claim. Each id is validated separately, so a fabricated id
            # hiding in a comma list is caught exactly like a lone one; what
            # is NOT done is rejecting the FORM, which would hard-fail
            # generation on correct output. The repeated 'id:' label is
            # punctuation, not part of the id, so it is stripped per part.
            cited_ids = [
                _strip_id_label(part) for part in body.split(",")
            ]
            if not any(cited_ids) or not body.strip():
                raise ValueError(
                    "%s: empty citation marker %r -- a marker with no record "
                    "id traces to nothing" % (section, match.group(0))
                )
            for cited_id in cited_ids:
                if not cited_id:
                    raise ValueError(
                        "%s: citation marker %r has an empty id in its list"
                        % (section, match.group(0))
                    )
                if cited_id not in record_ids:
                    raise ValueError(
                        "%s: citation marker names record id %r, which was "
                        "not among the records supplied to this generation: %s"
                        % (section, cited_id, sorted(record_ids))
                    )


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
    prose = validate_prose(payload)
    _check_prose_is_cited(prose, {record.id for record in records})
    return prose


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
