"""Layer 1 reference records: parse, validate, load.

A record is Markdown with YAML frontmatter. Frontmatter carries what a machine
indexes on; the claim itself is the body prose, so the file renders in a
Markdown preview and stays readable by a human.

Records are append-only by design (spec D4). Nothing here writes or mutates.
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from typing import List, Optional

import yaml
from pydantic import BaseModel, ValidationError

from litintel.methodintel.schema import SourceRef, SourceRefKind


ALLOWED_KINDS: frozenset[str] = frozenset({
    "benchmark",
    "usage",
    "deprecation",
    "best_practice",
    "personal",
    "seed",
    "adaptation",
})

# Citation is mandatory for these source kinds. A method recommendation whose
# evidence cannot name its venue is not defensible to a PI (spec section 4).
_CITED_SOURCE_KINDS: frozenset[SourceRefKind] = frozenset({
    SourceRefKind.PMID,
    SourceRefKind.DOI,
})

_FENCE = "---"


class RecordError(ValueError):
    """A record is malformed. Always raised, never swallowed."""


class Citation(BaseModel):
    first_author: str
    journal: str
    year: int


class ReferenceRecord(BaseModel):
    id: str
    concept: Optional[str] = None
    modality: List[str] = []
    methods: List[str] = []
    # Algorithm and package are separate axes: one algorithm ships in several
    # packages with different pipeline-fit consequences (spec 5.2), mirroring
    # MethodOption.algorithm / .implementation in schema.py:127-128.
    implementations: List[str] = []
    kind: str
    recorded: date
    seed_rung: Optional[int] = None
    source_ref: SourceRef
    citation: Optional[Citation] = None
    confidence: str
    body: str


def _split_frontmatter(text: str, path: Path) -> tuple[str, str]:
    """Return (frontmatter_yaml, body). Raises if the fence is absent.

    Real records on disk lead with a single-line `<!-- path -->` HTML comment
    before the frontmatter fence (a file-path breadcrumb for readability).
    Blank lines and that leading comment are skipped before the fence is
    required; anything else before the fence is a malformed record.
    """
    lines = text.splitlines()

    start = 0
    while start < len(lines):
        stripped = lines[start].strip()
        if not stripped:
            start += 1
            continue
        if stripped.startswith("<!--") and stripped.endswith("-->"):
            start += 1
            continue
        break

    if start >= len(lines) or lines[start].strip() != _FENCE:
        raise RecordError("%s: missing opening frontmatter fence" % path)

    for index in range(start + 1, len(lines)):
        if lines[index].strip() == _FENCE:
            return (
                "\n".join(lines[start + 1:index]),
                "\n".join(lines[index + 1:]).strip(),
            )

    raise RecordError("%s: unterminated frontmatter" % path)


def _validate(record: ReferenceRecord, path: Path) -> None:
    if record.kind not in ALLOWED_KINDS:
        raise RecordError(
            "%s: unknown kind %r, expected one of %s"
            % (path, record.kind, sorted(ALLOWED_KINDS))
        )

    if record.source_ref.kind in _CITED_SOURCE_KINDS and record.citation is None:
        raise RecordError(
            "%s: citation is required when source_ref.kind is %s"
            % (path, record.source_ref.kind.value)
        )

    if record.kind == "seed":
        if record.seed_rung not in (1, 2, 3):
            raise RecordError(
                "%s: seed_rung must be 1, 2 or 3 when kind is seed" % path
            )
    elif record.seed_rung is not None:
        raise RecordError("%s: seed_rung is only valid when kind is seed" % path)


def parse_record(path: Path) -> ReferenceRecord:
    """Parse one record file. Raises RecordError on any defect."""
    path = Path(path)
    raw, body = _split_frontmatter(path.read_text(), path)

    try:
        fields = yaml.safe_load(raw) or {}
    except yaml.YAMLError as exc:
        raise RecordError("%s: frontmatter is not valid YAML: %s" % (path, exc))

    if not isinstance(fields, dict):
        raise RecordError("%s: frontmatter must be a mapping" % path)

    try:
        record = ReferenceRecord(**fields, body=body)
    except ValidationError as exc:
        raise RecordError("%s: %s" % (path, exc))

    _validate(record, path)
    return record


def load_concept_records(methods_root: Path, concept: str) -> list[ReferenceRecord]:
    """Every record in one concept shard, sorted by id.

    Sorted because ids are date-prefixed, so id order is chronological order,
    which is the order a chapter's history section wants.

    A concept shard that does not exist yet returns []: a concept legitimately
    has no evidence before anyone has written to it (spec 3.4.2 -- a concept
    may have no canonical label, and by the same logic no records, yet). This
    is distinct from an invalid knowledge root, which is caught loudly by
    resolve_methods_root() before a path ever reaches here.
    """
    shard = Path(methods_root) / "references" / concept
    if not shard.is_dir():
        return []

    return sorted(
        (parse_record(p) for p in shard.glob("*.md")),
        key=lambda r: r.id,
    )


def resolve_methods_root(configured_path: Optional[str]) -> Path:
    """Resolve AppConfig.methods_repo_path to a usable knowledge-root directory.

    Raises RecordError, naming the `methods_repo_path` config key, when the
    value is None, when the expanded path does not exist, or when it is not a
    directory. Never returns None and never substitutes a default -- Task 3
    left this check unenforced at the config layer on purpose; this is the
    first consumer, so it is the enforcement point. Reused as-is by Tasks 7,
    8 and 10 rather than each re-implementing the same three checks.
    """
    if configured_path is None:
        raise RecordError(
            "methods_repo_path is not set in config; cannot resolve the "
            "bioinfo-methods knowledge root"
        )

    expanded = Path(os.path.expanduser(configured_path))

    if not expanded.exists():
        raise RecordError(
            "methods_repo_path %r (expanded to %s) does not exist"
            % (configured_path, expanded)
        )

    if not expanded.is_dir():
        raise RecordError(
            "methods_repo_path %r (expanded to %s) is not a directory"
            % (configured_path, expanded)
        )

    return expanded
