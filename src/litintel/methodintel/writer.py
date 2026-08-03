"""Write layer 1 records into the knowledge base. Never commits.

Litintel writes; the human reviews and commits in dotfiles. That repo boundary
IS the D6 review gate, enforced by structure instead of by convention -- so
nothing here should ever grow a git call.
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from typing import List, Optional

import yaml

from litintel.methodintel.records import Citation


def usage_record_path(methods_root: Path, concept: str, pmid: str, recorded: date) -> Path:
    """Compute the path write_usage_record would use, without touching disk.

    Exposed (not underscored) so a caller can tell, before calling
    write_usage_record, whether a given call will be a fresh write or a
    collision skip -- the tier1 usage feed uses this to count and log the
    skip outcome without duplicating the id-format string in two files.
    """
    root = Path(os.path.expanduser(str(methods_root)))
    record_id = "%s-pmid%s-%s-usage" % (recorded.isoformat(), pmid, concept)
    return root / "references" / concept / ("%s.md" % record_id)


def write_usage_record(
    methods_root: Path,
    concept: str,
    methods: List[str],
    modality: List[str],
    pmid: str,
    citation: Citation,
    body: str,
    recorded: date,
    implementations: Optional[List[str]] = None,
) -> Path:
    """Append one usage record. Idempotent: a rerun is a no-op.

    The id is date + pmid + concept, so the same paper on the same day maps to
    the same path per concept and an existing file is left alone. One paper
    yields several records because a study spans several concepts, so pmid
    alone would collide.

    Layer 1 is append-only (spec D4) -- a changed claim is a NEW record that
    contradicts the old one, never an overwrite. Collision behavior: SKIP, not
    raise -- a same-day rerun on the same (paper, concept) is expected and
    must be a no-op, not a pipeline failure; a genuine correction is filed as
    a new record on a later `recorded` date instead of mutating this one.
    """
    if not concept:
        raise ValueError("concept is required; a usage record with no concept "
                         "cannot be filed into a shard")

    path = usage_record_path(methods_root, concept, pmid, recorded)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return path

    record_id = path.stem
    frontmatter = {
        "id": record_id,
        "concept": concept,
        "modality": modality,
        "methods": methods,
        "implementations": implementations or [],
        "kind": "usage",
        "recorded": recorded.isoformat(),
        "source_ref": {"kind": "pmid", "value": pmid},
        "citation": {
            "first_author": citation.first_author,
            "journal": citation.journal,
            "year": citation.year,
        },
        "confidence": "medium",
    }

    path.write_text(
        "---\n%s---\n\n%s\n"
        % (yaml.safe_dump(frontmatter, sort_keys=False), body.strip())
    )
    return path
