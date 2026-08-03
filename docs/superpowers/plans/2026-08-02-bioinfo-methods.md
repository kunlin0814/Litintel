# bioinfo-methods Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up a compounding, agent-queryable method knowledge base in
`dotfiles/skills/bioinfo-methods/`, with the `clustering` concept populated end
to end from curated evidence records to a generated, citable chapter.

**Architecture:** Two repos, one-way dependency. Knowledge (Markdown +
YAML frontmatter) lives in `dotfiles`; all code lives in `Litintel` under
`src/litintel/methodintel/`. Litintel reads a single config key,
`methods_repo_path`, writes records into that directory, and never commits
there -- the human commits in `dotfiles`, which is the D6 review gate. Layer 1
records are append-only; Layer 2 chapters are regenerated from them and never
hand-edited, so `git diff` on a chapter is the changelog.

**Tech Stack:** Python 3.12, Pydantic v2, Typer, PyYAML, pytest. Gemini via the
existing `enrich/ai_client.py` Vertex path for chapter prose only. No new
third-party dependency is added -- frontmatter is parsed with `yaml.safe_load`
on a manual `---` split.

**Spec:** `docs/superpowers/specs/2026-08-02-bioinfo-methods-design.md`
(read it before Task 1; every decision reference below is `D<n>` or a section
number from that file).

## Global Constraints

- **ASCII only** in all code, comments, Markdown, and prompt templates. No
  emoji, no Unicode dashes, arrows, or bullets. Use `->`, `>=`, `--`.
- **Fail loud.** Never `except: pass`. A malformed record raises; it is never
  skipped silently.
- **Never invent** a function, parameter, path, PMID, DOI, or heading. Anything
  unconfirmed gets a `# VERIFY: <what to confirm>` tag.
- **Worktree isolation.** Litintel work happens in `/Users/kun-linho/GitHub/Litintel-claude`
  (branch `claude`). Dotfiles work happens in `/Users/kun-linho/GitHub/dotfiles-claude`
  (branch `claude`). Never edit or commit in either trunk. Both worktrees
  already exist -- verified 2026-08-02.
- **Two repos, two commit streams.** A task touching both commits separately in
  each. Never try to commit across the boundary.
- **Layer 1 is append-only.** Records are never edited and never deleted. A
  superseded claim is contradicted by a newer record.
- **Layer 2 is never hand-edited.** If a chapter is wrong, fix a record or the
  generator and regenerate.
- **Test command:** `venv/bin/python -m pytest` from `/Users/kun-linho/GitHub/Litintel-claude`.
  Each worktree needs its own `venv/`; create with
  `python -m venv venv && venv/bin/pip install -e ".[dev]"` if absent.
- **Tests import via `sys.path`**, matching every existing file in `tests/`:
  ```python
  import os
  import sys
  sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))
  ```
- **Confirmed seed citations** (verified against PubMed 2026-08-02, do not
  re-verify, do not alter):

  | Modality | Rung | PMID | DOI |
  |---|---|---|---|
  | scRNA | 1 | 31217225 | 10.15252/msb.20188746 |
  | scRNA | 1 | 37002403 | 10.1038/s41576-023-00586-w |
  | scATAC | 2 | 41270791 | 10.1093/gpbjnl/qzaf115 |
  | multiome | 2 | 41987329 | 10.1186/s13059-026-04071-5 |
  | spatial RNA | 2 | 41332620 | 10.1101/2025.11.20.688607 |
  | spatial RNA | 2 | 35102346 | 10.1038/s41592-021-01358-2 |
  | spatial ATAC | 3 | 36922587 | 10.1038/s41586-023-05795-1 |

---

## File Structure

**In `dotfiles-claude` (knowledge, no code):**

| Path | Responsibility |
|---|---|
| `skills/bioinfo-methods/SKILL.md` | Trigger conditions and query protocol. Small -- loaded by default. |
| `skills/bioinfo-methods/INDEX.md` | Concept list + status-at-a-glance. Small -- loaded by default. |
| `skills/bioinfo-methods/LEXICON.md` | Every term ever seen, with its concept (nullable) and aliases. |
| `skills/bioinfo-methods/references/<concept>/*.md` | Layer 1 evidence records, append-only. Never bulk-loaded. |
| `skills/bioinfo-methods/chapters/<concept>.md` | Layer 2 generated chapters. Read on demand by name. |

**In `Litintel-claude` (code, no knowledge):**

| Path | Responsibility |
|---|---|
| `src/litintel/methodintel/records.py` | Layer 1 record model, frontmatter parser, validator. Pure -- no I/O beyond reading files. |
| `src/litintel/methodintel/lexicon.py` | Parse `LEXICON.md`; build `CONCEPT_ALIASES`. |
| `src/litintel/methodintel/chapters.py` | Deterministic chapter assembly: bibliography, status table, borrowed-and-broken block. |
| `src/litintel/methodintel/synthesis.py` | The one LLM call: records -> prose sections. Thin adapter. |
| `src/litintel/methodintel/writer.py` | Write records into `methods_repo_path`. Never commits. |
| `src/litintel/methodintel/schema.py` | MODIFY: four new edge types. |
| `src/litintel/methodintel/router.py` | MODIFY: `CONCEPT_ALIASES` wired in. |
| `src/litintel/config.py` | MODIFY: `methods_repo_path` key. |
| `src/litintel/cli.py` | MODIFY: `methodintel chapter` and `methodintel validate-records`. |
| `src/litintel/pipeline/tier1.py` | MODIFY: emit usage records at the Pass 2 fan-out. |

Split rationale: parsing (`records`), naming (`lexicon`), deterministic
rendering (`chapters`), and the model call (`synthesis`) change for different
reasons and are tested differently -- `chapters.py` must be fully deterministic
so its tests never touch a network.

---

## Task 1: Skill scaffold, deployed and verified

**Files:**
- Create: `~/GitHub/dotfiles-claude/skills/bioinfo-methods/SKILL.md`
- Create: `~/GitHub/dotfiles-claude/skills/bioinfo-methods/INDEX.md`
- Create: `~/GitHub/dotfiles-claude/skills/bioinfo-methods/chapters/.gitkeep`
- Create: `~/GitHub/dotfiles-claude/skills/bioinfo-methods/references/.gitkeep`

**Interfaces:**
- Consumes: nothing.
- Produces: the deployed skill directory. Task 2 writes into it; Task 8
  regenerates `INDEX.md`'s status table.

- [ ] **Step 1: Confirm the dotfiles agent worktree**

```bash
git -C ~/GitHub/dotfiles worktree list
```
Expected: a line reading `/Users/kun-linho/GitHub/dotfiles-claude  <sha> [claude]`.
If absent, STOP and ask -- do not create it and do not fall back to the trunk.

- [ ] **Step 2: Write `SKILL.md`**

Keep it under 60 lines. It is loaded into every session's catalog on three
harnesses (`setup.sh:120`), so length here is a permanent tax.

```markdown
---
name: bioinfo-methods
description: Use when choosing, comparing, or checking the currency of a computational method for single-cell, spatial, or multiome analysis - answers from a curated, citable knowledge base instead of a web search
---

# bioinfo-methods

A curated knowledge base of computational method decisions for single-cell,
spatial transcriptomics, spatial ATAC, and multiome analysis. Every claim
carries a citation. Prefer this over a web search.

## When to use

- "Which clustering method should I use for spatial ATAC?"
- "Is Louvain still current?"
- "What replaced X, and why?"
- Any question of the form "what is the right method for <analysis stage>".

## How to query

1. Read `INDEX.md`. It lists every concept and the current recommendation.
2. If the question's wording does not match a concept name, check `LEXICON.md`
   -- terms change over time and the same concept carries several labels.
3. Read the ONE chapter you need from `chapters/<concept>.md`. Do not read
   more than one unless the question spans concepts.
4. Answer from the chapter, citing its numbered references.

## What NOT to do

- Do NOT bulk-read `references/`. Those are evidence records, read only when
  auditing why a status changed or when regenerating a chapter.
- Do NOT hand-edit `chapters/`. They are generated from `references/`. To
  correct a chapter, add a reference record and regenerate.
- Do NOT answer from training memory when a chapter exists. The point of this
  base is that its answers are traceable.

## If the answer is not here

Say so plainly. A concept with no chapter, or a chapter whose modality section
is empty, is a known gap -- report it as a gap rather than filling it from
memory or from a search presented as equivalent.
```

- [ ] **Step 3: Write the `INDEX.md` skeleton**

```markdown
# Method concept index

Status-at-a-glance. One row per concept. Read the chapter for the reasoning.

| Concept | Current recommendation | Chapter | Last reviewed |
|---|---|---|---|
| _(populated by Task 2 and Task 8)_ | | | |

## Seeds

Concepts here were seeded from published field maps. Each seed is recorded as
a `kind: seed` reference record carrying its rung (D1b): 1 = consensus
best-practice review, 2 = benchmark or landscape review, 3 = high-impact
flagship method paper.
```

- [ ] **Step 4: Create the empty layer directories**

```bash
mkdir -p ~/GitHub/dotfiles-claude/skills/bioinfo-methods/references \
         ~/GitHub/dotfiles-claude/skills/bioinfo-methods/chapters
touch ~/GitHub/dotfiles-claude/skills/bioinfo-methods/references/.gitkeep \
      ~/GitHub/dotfiles-claude/skills/bioinfo-methods/chapters/.gitkeep
```

- [ ] **Step 5: Commit in dotfiles**

```bash
cd ~/GitHub/dotfiles-claude
git add skills/bioinfo-methods
git commit -m "feat: scaffold bioinfo-methods skill"
```

- [ ] **Step 6: Deploy and verify on all three harnesses**

```bash
cd ~/GitHub/dotfiles && ./setup.sh
ls -l ~/.claude/skills/bioinfo-methods/SKILL.md \
      ~/.codex/skills/bioinfo-methods/SKILL.md \
      ~/.gemini/skills/bioinfo-methods/SKILL.md
```
Expected: all three exist. Claude and Gemini are symlinks (`setup.sh:164`,
`:167`); Codex is a copy (`setup.sh:165`) -- this is the accepted consequence of
the owner's decision to leave Codex as-is, so Codex needs a `setup.sh` re-run to
see later chapter edits. Observe the real `ls` output; do not assume.

Note `setup.sh` deploys from the **trunk**, so it will not see the commit above
until it is landed. Land it first:
```bash
git -C ~/GitHub/dotfiles merge --ff-only claude
```

---

## Task 2: Seed the taxonomy from the confirmed field maps

**Files:**
- Create: `~/GitHub/dotfiles-claude/skills/bioinfo-methods/LEXICON.md`
- Create: `~/GitHub/dotfiles-claude/skills/bioinfo-methods/references/_seeds/*.md` (7 records)
- Modify: `~/GitHub/dotfiles-claude/skills/bioinfo-methods/INDEX.md`

**Interfaces:**
- Consumes: the directory from Task 1.
- Produces: `LEXICON.md`, whose format Task 5's `parse_lexicon()` reads; seven
  seed records, whose frontmatter Task 4's `parse_record()` must accept.

- [ ] **Step 1: Write the seven seed records**

One file per seed paper in `references/_seeds/`. `_seeds` is a concept-less
shard -- these records describe the taxonomy's provenance, not one concept.
Use the exact citations from Global Constraints. Full example, copy this shape
for all seven:

```markdown
<!-- references/_seeds/2026-08-02-luecken2019-scrna-field-map.md -->
---
id: 2026-08-02-luecken2019-scrna-field-map
concept: null
modality: ["scRNA"]
methods: []
kind: seed
recorded: 2026-08-02
seed_rung: 1
source_ref:
  kind: pmid
  value: "31217225"
  note: "Luecken & Theis, Mol Syst Biol 2019, tutorial"
citation:
  first_author: "Luecken"
  journal: "Mol Syst Biol"
  year: 2019
confidence: high
---

Rung 1 consensus best-practice review for scRNA-seq. Its section headings are
taken as the scRNA stage taxonomy.

Level-1 and level-2 headings, verbatim:
Pre-processing and visualization -- quality control; normalization; data
correction and integration (regressing out biological effects, regressing out
technical effects, batch effects and data integration); feature selection,
dimensionality reduction and visualization; stages of pre-processed data.
Downstream analysis -- cluster analysis (clustering, cluster annotation,
compositional analysis); trajectory analysis (trajectory inference, gene
expression dynamics, metastable states); cell-level analysis unification;
gene-level analysis (differential expression testing, gene set analysis, gene
regulatory networks).
```

The other six, with their `seed_rung`, `modality`, and the headings each
contributes:

| File id stem | PMID | rung | modality | Contributes |
|---|---|---|---|---|
| `heumos2023-multimodal-field-map` | 37002403 | 1 | scRNA, scATAC, spatial_rna | Transcriptome, chromatin accessibility, surface protein, AIRR, and spatial section headings |
| `wang2025-scatac-field-map` | 41270791 | 2 | scATAC | QC, alignment, peak calling, matrix construction, bias removal, iterative LSI, clustering, embedding, gene-activity scoring, motif and footprinting, trajectory, multiomics integration, spatial applications |
| `naqing2026-multiome-benchmark` | 41987329 | 2 | multiome | GAS calculation, graph-based feature linking, dimension reduction, clustering and label transfer |
| `crowell2025-osta-field-map` | 41332620 | 2 | spatial_rna | Reads to counts, QC, intermediate processing, deconvolution, segmentation, neighborhood analysis, cell-cell communication, subcellular analysis, normalization, dimensionality reduction, clustering and annotation, feature selection and testing, spatial statistics, image analysis, deep learning, differential spatial patterns, differential colocalization, registration, imputation |
| `palla2022-squidpy-field-map` | 35102346 | 2 | spatial_rna | Spatial graph, neighborhood enrichment, Ripley's statistics, co-occurrence, spatial autocorrelation, ligand-receptor, image processing, segmentation, image features |
| `zhang2023-spatial-epigenome-field-map` | 36922587 | 3 | spatial_atac | Data preprocessing, clustering and visualization, integrative analysis and cell-type identification, CSS/GAS-versus-expression correlation |

For `crowell2025-osta-field-map`, add this line to the body -- it is the
rung-2 caveat and must travel with the record:

> Unreviewed bioRxiv preprint and a Bioconductor ecosystem book, so it reflects
> one ecosystem's view. It out-enumerates every peer-reviewed spatial review
> because it is a tutorial table of contents, not a review (3.4, source class 2).
> Pair with Squidpy (PMID 35102346) for peer-reviewed citation weight.

- [ ] **Step 2: Write `LEXICON.md`**

The format is load-bearing -- Task 5 parses it. One level-2 heading per
concept; a `Question:` line; a `Labels:` table; an `Unplaced` section at the
foot for terms seen but not yet understood.

```markdown
# Lexicon

Every term ever seen, with the concept it labels. A concept is defined by the
QUESTION it answers, not by its name (D9). Terms are time-stamped labels; a
concept may carry several, and a term may sit unplaced.

## clustering

Question: Which cells or spots form a group, given their molecular profiles?

| Label | Since | Status |
|---|---|---|
| clustering | 2015 | dominant |
| community detection | 2008 | |
| cell grouping | | |
| unsupervised cell type discovery | | |

## neighborhood_analysis

Question: Do cell types co-occur in space more or less than expected by chance?

| Label | Since | Status |
|---|---|---|
| neighborhood analysis | 2021 | dominant |
| cellular neighborhoods | 2020 | |
| niche identification | | |
| spatial co-occurrence | | superseded |

## normalization

Question: How are counts made comparable across cells, spots, or samples?

| Label | Since | Status |
|---|---|---|
| normalization | | dominant |
| variance stabilization | 2023 | |

## Unplaced

Terms seen in a field map but not yet understood well enough to place. An
unplaced term costs nothing; a wrongly placed record costs judgment to repay
(3.4.2). Prefer this list over a guess.

| Term | First seen | Source |
|---|---|---|
| sepal | 2026-08-02 | PMID 35102346 |
| differential colocalization | 2026-08-02 | PMID 41332620 |
| mosaic integration | 2026-08-02 | PMID 37002403 |
```

`normalization` deliberately carries two labels -- that satisfies the
"two or more labels" acceptance criterion in spec section 8 and is drawn from
a real disagreement: Luecken 2019 says "Normalization", Heumos 2023 says
"Normalization and variance stabilization".

- [ ] **Step 3: Populate the `INDEX.md` concept table**

Replace the placeholder row with three rows -- `clustering`,
`neighborhood_analysis`, `normalization` -- with `Current recommendation` and
`Last reviewed` left as `_pending_`. Task 8 fills clustering's.

- [ ] **Step 4: Commit in dotfiles**

```bash
cd ~/GitHub/dotfiles-claude
git add skills/bioinfo-methods
git commit -m "feat: seed method taxonomy from seven confirmed field maps"
```

---

## Task 3: Config key `methods_repo_path`

**Files:**
- Modify: `src/litintel/config.py` (the `AppConfig` class)
- Modify: `configs/tier1_pca.yaml`
- Test: `tests/test_methodintel_records.py` (created here, extended in Task 4)

**Interfaces:**
- Consumes: nothing.
- Produces: `AppConfig.methods_repo_path: Optional[str]`, read by Tasks 7 and 9.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_methodintel_records.py
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

import pytest

from litintel.config import AppConfig


def _minimal_config_kwargs():
    """The smallest AppConfig that validates, so config tests stay focused."""
    return {
        "pipeline_tier": 1,
        "pipeline_name": "test",
        "discovery": {"mode": "keyword", "queries": ["test"]},
        "ai": {"provider": "gemini", "prompt_template": "x"},
        "storage": {},
        "dedup": {},
    }


def test_methods_repo_path_defaults_to_none():
    cfg = AppConfig(**_minimal_config_kwargs())
    assert cfg.methods_repo_path is None


def test_methods_repo_path_round_trips():
    kwargs = _minimal_config_kwargs()
    kwargs["methods_repo_path"] = "~/GitHub/dotfiles-claude/skills/bioinfo-methods"
    cfg = AppConfig(**kwargs)
    assert cfg.methods_repo_path.endswith("skills/bioinfo-methods")
```

- [ ] **Step 2: Run it and watch it fail**

```bash
venv/bin/python -m pytest tests/test_methodintel_records.py -v
```
Expected: FAIL. Pydantic v2 ignores unknown keys by default, so
`test_methods_repo_path_round_trips` fails on `AttributeError` and
`test_methods_repo_path_defaults_to_none` fails the same way.

If `_minimal_config_kwargs()` itself raises a `ValidationError`, the required
field set has drifted -- read `src/litintel/config.py` and fix the fixture, not
the model.

- [ ] **Step 3: Add the field**

In `src/litintel/config.py`, inside `class AppConfig`, after `rag_agent`:

```python
    # Path to the bioinfo-methods knowledge base (a directory in the dotfiles
    # repo). Litintel WRITES records here and never commits -- the human commits
    # in dotfiles, which is the review gate. None disables the methods feed.
    methods_repo_path: Optional[str] = None
```

- [ ] **Step 4: Run the tests**

```bash
venv/bin/python -m pytest tests/test_methodintel_records.py -v
```
Expected: 2 passed.

- [ ] **Step 5: Wire the real config**

In `configs/tier1_pca.yaml`, at top level (NOT nested under `storage:`):

```yaml
# Points at the agent worktree, not the trunk. Chapter generation is agent-driven
# and trunk_write_guard.sh blocks agent writes into a trunk; pointing here keeps
# one isolation rule instead of two. Land with:
#   git -C ~/GitHub/dotfiles merge --ff-only claude
methods_repo_path: "~/GitHub/dotfiles-claude/skills/bioinfo-methods"
```

- [ ] **Step 6: Verify the real config still loads**

```bash
venv/bin/litintel validate configs/tier1_pca.yaml
```
Expected: exit 0.

- [ ] **Step 7: Commit**

```bash
git add src/litintel/config.py configs/tier1_pca.yaml tests/test_methodintel_records.py
git commit -m "feat: add methods_repo_path config key"
```

---

## Task 4: Layer 1 record model and parser

**Files:**
- Create: `src/litintel/methodintel/records.py`
- Test: `tests/test_methodintel_records.py` (extend)

**Interfaces:**
- Consumes: `AppConfig.methods_repo_path` (Task 3); `SourceRef`, `SourceRefKind`
  from `schema.py`.
- Produces:
  - `class Citation(BaseModel)` with `first_author: str`, `journal: str`, `year: int`
  - `class ReferenceRecord(BaseModel)` with `id`, `concept: Optional[str]`,
    `modality: List[str]`, `methods: List[str]`, `implementations: List[str]`,
    `kind: str`, `recorded: date`, `seed_rung: Optional[int]`,
    `source_ref: SourceRef`, `citation: Optional[Citation]`, `confidence: str`,
    `body: str`

`methods` and `implementations` are separate fields because
`schema.py::MethodOption` already splits `algorithm` from `implementation`
(`:127-128`): one algorithm is exposed by several packages with different
pipeline-fit consequences. A chapter that says "use Squidpy" without naming
the method has flattened the axis this system exists to keep (spec 5.2).
  - `ALLOWED_KINDS: frozenset[str]`
  - `class RecordError(ValueError)`
  - `parse_record(path: Path) -> ReferenceRecord`
  - `load_concept_records(methods_root: Path, concept: str) -> list[ReferenceRecord]`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_methodintel_records.py`:

```python
from pathlib import Path

from litintel.methodintel.records import (
    RecordError,
    ReferenceRecord,
    load_concept_records,
    parse_record,
)

VALID = """---
id: 2026-08-02-traag2019-louvain-connectivity
concept: clustering
modality: ["scRNA"]
methods: ["Louvain", "Leiden"]
kind: benchmark
recorded: 2026-08-02
seed_rung: null
source_ref:
  kind: doi
  value: "10.1038/s41598-019-41695-z"
  note: "Traag, Waltman, van Eck 2019"
citation:
  first_author: "Traag"
  journal: "Sci Rep"
  year: 2019
confidence: high
---

Louvain can yield arbitrarily badly connected communities. Leiden guarantees
well-connected communities.
"""


def _write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text)
    return path


def test_parse_record_reads_frontmatter_and_body(tmp_path):
    record = parse_record(_write(tmp_path, "r.md", VALID))

    assert record.id == "2026-08-02-traag2019-louvain-connectivity"
    assert record.concept == "clustering"
    assert record.modality == ["scRNA"]
    assert record.kind == "benchmark"
    assert record.citation.journal == "Sci Rep"
    assert record.body.startswith("Louvain can yield")
    assert "---" not in record.body


def test_null_concept_is_legal(tmp_path):
    text = VALID.replace("concept: clustering", "concept: null")
    assert parse_record(_write(tmp_path, "r.md", text)).concept is None


def test_citation_required_for_doi_source(tmp_path):
    text = VALID.replace(
        'citation:\n  first_author: "Traag"\n  journal: "Sci Rep"\n  year: 2019\n', ""
    )
    with pytest.raises(RecordError, match="citation"):
        parse_record(_write(tmp_path, "r.md", text))


def test_citation_not_required_for_personal_obs(tmp_path):
    text = VALID.replace(
        'kind: doi\n  value: "10.1038/s41598-019-41695-z"',
        'kind: personal_obs\n  value: "Apollo Stage 5"',
    ).replace(
        'citation:\n  first_author: "Traag"\n  journal: "Sci Rep"\n  year: 2019\n', ""
    ).replace("kind: benchmark", "kind: personal")
    assert parse_record(_write(tmp_path, "r.md", text)).citation is None


def test_seed_rung_required_when_kind_is_seed(tmp_path):
    text = VALID.replace("kind: benchmark", "kind: seed")
    with pytest.raises(RecordError, match="seed_rung"):
        parse_record(_write(tmp_path, "r.md", text))


def test_seed_rung_rejected_when_kind_is_not_seed(tmp_path):
    text = VALID.replace("seed_rung: null", "seed_rung: 2")
    with pytest.raises(RecordError, match="seed_rung"):
        parse_record(_write(tmp_path, "r.md", text))


def test_unknown_kind_is_rejected(tmp_path):
    text = VALID.replace("kind: benchmark", "kind: gossip")
    with pytest.raises(RecordError, match="kind"):
        parse_record(_write(tmp_path, "r.md", text))


def test_adaptation_is_a_legal_kind(tmp_path):
    text = VALID.replace("kind: benchmark", "kind: adaptation")
    assert parse_record(_write(tmp_path, "r.md", text)).kind == "adaptation"


def test_implementations_are_kept_separate_from_methods(tmp_path):
    """Algorithm and package are different axes (spec 5.2)."""
    text = VALID.replace(
        'methods: ["Louvain", "Leiden"]',
        'methods: ["Louvain", "Leiden"]\nimplementations: ["ArchR", "Scanpy"]',
    )
    record = parse_record(_write(tmp_path, "r.md", text))

    assert record.methods == ["Louvain", "Leiden"]
    assert record.implementations == ["ArchR", "Scanpy"]


def test_implementations_default_to_empty(tmp_path):
    assert parse_record(_write(tmp_path, "r.md", VALID)).implementations == []


def test_missing_frontmatter_fails_loud(tmp_path):
    with pytest.raises(RecordError, match="frontmatter"):
        parse_record(_write(tmp_path, "r.md", "just prose, no fence\n"))


def test_load_concept_records_sorted_by_id(tmp_path):
    shard = tmp_path / "references" / "clustering"
    shard.mkdir(parents=True)
    (shard / "b.md").write_text(VALID.replace("2026-08-02-traag", "2026-08-03-zzz"))
    (shard / "a.md").write_text(VALID)

    records = load_concept_records(tmp_path, "clustering")

    assert [r.id for r in records] == [
        "2026-08-02-traag2019-louvain-connectivity",
        "2026-08-03-zzz2019-louvain-connectivity",
    ]


def test_load_concept_records_missing_shard_returns_empty(tmp_path):
    assert load_concept_records(tmp_path, "nonexistent") == []
```

- [ ] **Step 2: Run and watch them fail**

```bash
venv/bin/python -m pytest tests/test_methodintel_records.py -v
```
Expected: FAIL, `ModuleNotFoundError: No module named 'litintel.methodintel.records'`.

- [ ] **Step 3: Implement `records.py`**

```python
"""Layer 1 reference records: parse, validate, load.

A record is Markdown with YAML frontmatter. Frontmatter carries what a machine
indexes on; the claim itself is the body prose, so the file renders in a
Markdown preview and stays readable by a human.

Records are append-only by design (spec D4). Nothing here writes or mutates.
"""

from __future__ import annotations

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
    """Return (frontmatter_yaml, body). Raises if the fence is absent."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != _FENCE:
        raise RecordError("%s: missing opening frontmatter fence" % path)

    for index in range(1, len(lines)):
        if lines[index].strip() == _FENCE:
            return "\n".join(lines[1:index]), "\n".join(lines[index + 1:]).strip()

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
    raw, body = _split_frontmatter(Path(path).read_text(), Path(path))

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

    _validate(record, Path(path))
    return record


def load_concept_records(methods_root: Path, concept: str) -> list[ReferenceRecord]:
    """Every record in one concept shard, sorted by id.

    Sorted because ids are date-prefixed, so id order is chronological order,
    which is the order a chapter's history section wants.
    """
    shard = Path(methods_root) / "references" / concept
    if not shard.is_dir():
        return []

    return sorted(
        (parse_record(p) for p in shard.glob("*.md")),
        key=lambda r: r.id,
    )
```

- [ ] **Step 4: Run the tests**

```bash
venv/bin/python -m pytest tests/test_methodintel_records.py -v
```
Expected: all pass (2 from Task 3 + 11 here).

- [ ] **Step 5: Validate the real seed records**

```bash
venv/bin/python -c "
from pathlib import Path
from litintel.methodintel.records import parse_record
root = Path.home() / 'GitHub/dotfiles-claude/skills/bioinfo-methods/references/_seeds'
for p in sorted(root.glob('*.md')):
    r = parse_record(p)
    print(r.id, r.kind, 'rung', r.seed_rung, r.citation.journal if r.citation else '-')
"
```
Expected: seven lines, every one with `kind seed` and a rung of 1, 2, or 3.
This is the first real proof the Task 2 records and the Task 4 parser agree.
If any record fails, fix the RECORD (Task 2 output), not the validator.

- [ ] **Step 6: Commit**

```bash
git add src/litintel/methodintel/records.py tests/test_methodintel_records.py
git commit -m "feat: parse and validate layer 1 reference records"
```

---

## Task 5: Lexicon parsing and `CONCEPT_ALIASES`

**Files:**
- Create: `src/litintel/methodintel/lexicon.py`
- Modify: `src/litintel/methodintel/router.py`
- Test: `tests/test_methodintel_lexicon.py`

**Interfaces:**
- Consumes: `LEXICON.md` (Task 2).
- Produces:
  - `class ConceptEntry(BaseModel)` with `concept: str`, `question: str`,
    `labels: List[str]`
  - `parse_lexicon(path: Path) -> list[ConceptEntry]`
  - `build_concept_aliases(entries) -> dict[str, str]` -- lowercased label ->
    concept name
  - `router.CONCEPT_ALIASES: dict[str, str]` (a module-level constant, matching
    the shape of the existing `METHOD_ALIASES` at `router.py:15`)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_methodintel_lexicon.py
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from litintel.methodintel.lexicon import build_concept_aliases, parse_lexicon

LEXICON = """# Lexicon

Preamble prose that must be ignored.

## clustering

Question: Which cells or spots form a group, given their molecular profiles?

| Label | Since | Status |
|---|---|---|
| clustering | 2015 | dominant |
| community detection | 2008 | |
| cell grouping | | |

## neighborhood_analysis

Question: Do cell types co-occur in space more or less than expected by chance?

| Label | Since | Status |
|---|---|---|
| neighborhood analysis | 2021 | dominant |
| niche identification | | |

## Unplaced

| Term | First seen | Source |
|---|---|---|
| sepal | 2026-08-02 | PMID 35102346 |
"""


def test_parse_lexicon_finds_concepts(tmp_path):
    path = tmp_path / "LEXICON.md"
    path.write_text(LEXICON)

    entries = parse_lexicon(path)

    assert [e.concept for e in entries] == ["clustering", "neighborhood_analysis"]


def test_unplaced_section_is_not_a_concept(tmp_path):
    path = tmp_path / "LEXICON.md"
    path.write_text(LEXICON)

    assert "Unplaced" not in [e.concept for e in parse_lexicon(path)]


def test_question_and_labels_are_captured(tmp_path):
    path = tmp_path / "LEXICON.md"
    path.write_text(LEXICON)

    clustering = parse_lexicon(path)[0]

    assert clustering.question.startswith("Which cells or spots form a group")
    assert clustering.labels == ["clustering", "community detection", "cell grouping"]


def test_build_concept_aliases_maps_every_label(tmp_path):
    path = tmp_path / "LEXICON.md"
    path.write_text(LEXICON)

    aliases = build_concept_aliases(parse_lexicon(path))

    assert aliases["community detection"] == "clustering"
    assert aliases["niche identification"] == "neighborhood_analysis"
    assert aliases["clustering"] == "clustering"


def test_aliases_are_lowercased_for_lookup(tmp_path):
    path = tmp_path / "LEXICON.md"
    path.write_text(LEXICON.replace("| clustering |", "| Clustering |"))

    assert "clustering" in build_concept_aliases(parse_lexicon(path))


def test_router_exposes_concept_aliases():
    from litintel.methodintel.router import CONCEPT_ALIASES

    assert CONCEPT_ALIASES["community detection"] == "clustering"
    assert CONCEPT_ALIASES["niche identification"] == "neighborhood_analysis"
```

- [ ] **Step 2: Run and watch them fail**

```bash
venv/bin/python -m pytest tests/test_methodintel_lexicon.py -v
```
Expected: FAIL, `ModuleNotFoundError: No module named 'litintel.methodintel.lexicon'`.

- [ ] **Step 3: Implement `lexicon.py`**

```python
"""Parse LEXICON.md into concept entries and a label -> concept alias map.

The lexicon is authored by hand and read by machine, so parsing is deliberately
forgiving about prose and strict about structure: a level-2 heading opens a
concept, a "Question:" line defines it, and the first column of the following
table holds its labels.
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


class ConceptEntry(BaseModel):
    concept: str
    question: str
    labels: List[str]


def parse_lexicon(path: Path) -> list[ConceptEntry]:
    entries: list[ConceptEntry] = []
    current: dict | None = None

    for line in Path(path).read_text().splitlines():
        heading = _HEADING.match(line)
        if heading:
            if current is not None:
                entries.append(ConceptEntry(**current))
            name = heading.group("name")
            current = (
                None
                if name.strip().lower() in _NON_CONCEPT_HEADINGS
                else {"concept": name, "question": "", "labels": []}
            )
            continue

        if current is None:
            continue

        question = _QUESTION.match(line)
        if question:
            current["question"] = question.group("text")
            continue

        if _TABLE_DIVIDER.match(line):
            continue

        row = _TABLE_ROW.match(line)
        if row:
            label = row.group("first").strip()
            if label and label.lower() != "label":
                current["labels"].append(label)

    if current is not None:
        entries.append(ConceptEntry(**current))

    return entries


def build_concept_aliases(entries: list[ConceptEntry]) -> dict[str, str]:
    """Lowercased label -> concept name, for tier 1 (free) query resolution.

    Tier 2 -- semantic match against ConceptEntry.question -- is what catches a
    question phrased in words no label uses, and is out of scope for v1.
    """
    return {
        label.lower(): entry.concept
        for entry in entries
        for label in entry.labels
    }
```

- [ ] **Step 4: Wire `CONCEPT_ALIASES` into the router**

At the end of the alias block in `src/litintel/methodintel/router.py`, after
`IMPLEMENTATION_ALIASES` (`router.py:29`):

```python
# Generated from dotfiles/skills/bioinfo-methods/LEXICON.md, not hand-maintained.
# Regenerate with: venv/bin/litintel methodintel sync-aliases
# Checked in rather than loaded at import time so the router keeps working with
# no knowledge base present -- Litintel must not hard-depend on dotfiles.
CONCEPT_ALIASES: dict[str, str] = {
    "clustering": "clustering",
    "community detection": "clustering",
    "cell grouping": "clustering",
    "unsupervised cell type discovery": "clustering",
    "neighborhood analysis": "neighborhood_analysis",
    "cellular neighborhoods": "neighborhood_analysis",
    "niche identification": "neighborhood_analysis",
    "spatial co-occurrence": "neighborhood_analysis",
    "normalization": "normalization",
    "variance stabilization": "normalization",
}
```

- [ ] **Step 5: Add the `sync-aliases` command the comment promises**

In `src/litintel/cli.py`, after `methodintel_route` (`cli.py:99-103`):

```python
@methodintel_app.command("sync-aliases")
def methodintel_sync_aliases(config: str = "configs/tier1_pca.yaml"):
    """Print the CONCEPT_ALIASES literal generated from LEXICON.md.

    Prints rather than rewrites router.py: regenerating source in place would
    make a hand-reviewable constant into a build artifact.
    """
    import os
    from pathlib import Path

    from litintel.config import load_config_from_yaml
    from litintel.methodintel.lexicon import build_concept_aliases, parse_lexicon

    cfg = load_config_from_yaml(config)
    if not cfg.methods_repo_path:
        typer.secho("methods_repo_path is not set in %s" % config, fg=typer.colors.RED)
        raise typer.Exit(code=2)

    lexicon = Path(os.path.expanduser(cfg.methods_repo_path)) / "LEXICON.md"
    aliases = build_concept_aliases(parse_lexicon(lexicon))

    typer.echo("CONCEPT_ALIASES: dict[str, str] = {")
    for label, concept in sorted(aliases.items()):
        typer.echo('    "%s": "%s",' % (label, concept))
    typer.echo("}")
```

- [ ] **Step 6: Run the tests**

```bash
venv/bin/python -m pytest tests/test_methodintel_lexicon.py -v
```
Expected: 6 passed.

- [ ] **Step 7: Prove the checked-in constant matches the real lexicon**

```bash
venv/bin/litintel methodintel sync-aliases
```
Expected: output identical to the literal added in Step 4. If it differs, the
lexicon is the truth -- update `router.py` to match it.

- [ ] **Step 8: Run the full suite**

```bash
venv/bin/python -m pytest -q
```
Expected: all previously passing tests still pass. `test_methodintel_router.py`
must be unaffected -- `CONCEPT_ALIASES` is additive.

- [ ] **Step 9: Commit**

```bash
git add src/litintel/methodintel/lexicon.py src/litintel/methodintel/router.py \
        src/litintel/cli.py tests/test_methodintel_lexicon.py
git commit -m "feat: parse LEXICON.md and add CONCEPT_ALIASES to the router"
```

---

## Task 6: Four new edge types

**Files:**
- Modify: `src/litintel/methodintel/schema.py:154+` (`ALLOWED_EDGE_TYPES`)
- Test: `tests/test_methodintel_dossier_schema.py` (extend)

**Interfaces:**
- Consumes: nothing.
- Produces: `split_into`, `merged_from`, `shares_mechanism_with`, `adapted_from`
  accepted by `MethodGraphEdge`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_methodintel_dossier_schema.py`:

```python
import pytest

from litintel.methodintel.schema import MethodGraphEdge


@pytest.mark.parametrize("edge_type", [
    "split_into",
    "merged_from",
    "shares_mechanism_with",
    "adapted_from",
])
def test_new_edge_types_are_allowed(edge_type):
    """Concept history (split/merge), the mechanism relation, and cross-modality
    borrowing are unrepresentable without these -- see spec 3.4.2 and 3.4.4."""
    assert edge_type in MethodGraphEdge.ALLOWED_EDGE_TYPES


def test_existing_edge_types_are_untouched():
    for edge_type in ("competes_with", "replaces_or_modernizes", "deprecated_by"):
        assert edge_type in MethodGraphEdge.ALLOWED_EDGE_TYPES
```

- [ ] **Step 2: Run and watch it fail**

```bash
venv/bin/python -m pytest tests/test_methodintel_dossier_schema.py -v -k edge_type
```
Expected: the four parametrized cases FAIL; `test_existing_edge_types_are_untouched` passes.

- [ ] **Step 3: Extend the frozenset**

In `src/litintel/methodintel/schema.py`, inside `MethodGraphEdge.ALLOWED_EDGE_TYPES`,
after `"sensitive_to"`:

```python
        # Concept history. A concept that splits or merges must leave a trace,
        # or the chapter set's own evolution becomes unauditable (spec 3.4.2).
        "split_into",
        "merged_from",
        # Mechanism is a relation, not a key. Two methods can share machinery
        # while sitting in different chapters because nobody chooses between
        # them -- keying chapters on mechanism would group those and split the
        # pairs users actually compare (spec 3.4.2).
        "shares_mechanism_with",
        # Cross-modality borrowing. A young field inherits its methods from the
        # nearest mature one; the edge records where a method came from so the
        # adaptation records hang off something (spec 3.4.4).
        "adapted_from",
```

- [ ] **Step 4: Run the tests**

```bash
venv/bin/python -m pytest tests/test_methodintel_dossier_schema.py -v
```
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/litintel/methodintel/schema.py tests/test_methodintel_dossier_schema.py
git commit -m "feat: add split_into, merged_from, shares_mechanism_with, adapted_from edges"
```

---

## Task 7: Deterministic chapter assembly

**Files:**
- Create: `src/litintel/methodintel/chapters.py`
- Test: `tests/test_methodintel_chapters.py`

**Interfaces:**
- Consumes: `ReferenceRecord`, `load_concept_records` (Task 4).
- Produces:
  - `render_bibliography(records) -> tuple[str, dict[str, int]]` -- returns the
    Markdown block and an `id -> number` map
  - `render_status_table(records) -> str`
  - `render_borrowed_and_broken(records) -> str`
  - `assemble_chapter(concept, records, prose) -> str` where `prose` is a
    `dict[str, str]` with keys `recommendation`, `tradeoffs`, `open_questions`

This whole module must be **network-free and deterministic** -- same records in,
same bytes out. That is what makes `git diff` on a chapter mean "the evidence
changed" rather than "the model was in a different mood" (D5).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_methodintel_chapters.py
import os
import sys
from datetime import date

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from litintel.methodintel.chapters import (
    assemble_chapter,
    render_bibliography,
    render_borrowed_and_broken,
    render_status_table,
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


def test_assembly_is_deterministic():
    prose = {"recommendation": "x", "tradeoffs": "y", "open_questions": "z"}
    records = [_record("b"), _record("a")]

    assert assemble_chapter("clustering", records, prose) == assemble_chapter(
        "clustering", records, prose
    )


def test_what_changed_cites_record_ids_not_numbers():
    """Numbers renumber when a claim is inserted; ids never move (spec 5.1)."""
    chapter = assemble_chapter(
        "clustering",
        [_record("2026-08-02-traag2019-louvain-connectivity", kind="deprecation")],
        {"recommendation": "x", "tradeoffs": "y", "open_questions": "z"},
    )
    changed = chapter.split("## What changed")[1].split("## References")[0]

    assert "2026-08-02-traag2019-louvain-connectivity" in changed
```

- [ ] **Step 2: Run and watch them fail**

```bash
venv/bin/python -m pytest tests/test_methodintel_chapters.py -v
```
Expected: FAIL, `ModuleNotFoundError: No module named 'litintel.methodintel.chapters'`.

- [ ] **Step 3: Implement `chapters.py`**

```python
"""Deterministic assembly of a layer 2 chapter from its layer 1 records.

Everything here is pure: same records in, same bytes out, no network. That is
what makes a chapter's git diff mean "the evidence changed" rather than "the
model phrased it differently" (spec D5). The model's contribution enters only
as the `prose` dict, produced by synthesis.py.
"""

from __future__ import annotations

from litintel.methodintel.records import ReferenceRecord


# Record kinds that represent a status transition, so they belong in the
# "What changed" section rather than only in the bibliography.
_TRANSITION_KINDS: frozenset[str] = frozenset({"deprecation", "adaptation"})


def render_bibliography(
    records: list[ReferenceRecord],
) -> tuple[str, dict[str, int]]:
    """Numbered bibliography plus the record-id -> number map.

    Numbers are cosmetic and assigned here, at render time. The stable
    identifier is always the record id (spec 5.1).
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
    """One row per (method, modality) pair.

    Modality is a column rather than a separate chapter because a young field
    borrows its methods wholesale from a mature one, so per-modality chapters
    would be near-duplicates (spec 3.4.4).
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

    An absent adaptation record means unaudited, never clean. Rendering silence
    as an open question is the whole point (spec 3.4.4).
    """
    modalities = sorted({m for r in records for m in r.modality})
    adaptations: dict[str, list[ReferenceRecord]] = {m: [] for m in modalities}

    for record in records:
        if record.kind == "adaptation":
            for modality in record.modality:
                adaptations[modality].append(record)

    lines = ["## Borrowed and broken", ""]
    for modality in modalities:
        lines.append("### %s" % modality)
        lines.append("")
        if adaptations[modality]:
            for record in sorted(adaptations[modality], key=lambda r: r.id):
                lines.append("- %s  [id: %s]" % (record.body.strip(), record.id))
        else:
            lines.append(
                "- No adaptation record. This modality has **not audited** "
                "whether the borrowed method's assumptions hold here."
            )
        lines.append("")

    return "\n".join(lines).rstrip()


def render_what_changed(records: list[ReferenceRecord]) -> str:
    """Status transitions, newest last, each citing a record id.

    Cites ids and never bibliography numbers: inserting a claim renumbers the
    bibliography, and the changelog must survive that (spec 5.1).
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
    """Full chapter text. Deterministic given records and prose."""
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
```

- [ ] **Step 4: Run the tests**

```bash
venv/bin/python -m pytest tests/test_methodintel_chapters.py -v
```
Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add src/litintel/methodintel/chapters.py tests/test_methodintel_chapters.py
git commit -m "feat: deterministic chapter assembly from reference records"
```

---

## Task 8: Chapter synthesis and the `chapter` CLI command

**Files:**
- Create: `src/litintel/methodintel/synthesis.py`
- Modify: `src/litintel/cli.py`
- Test: `tests/test_methodintel_synthesis.py`

**Interfaces:**
- Consumes: `assemble_chapter` (Task 7), `load_concept_records` (Task 4),
  `AppConfig.methods_repo_path` (Task 3).
- Produces:
  - `PROSE_SCHEMA: dict` -- the Gemini `response_schema`
  - `build_prose_prompt(concept, records) -> str`
  - `validate_prose(payload: dict) -> dict[str, str]`
  - `synthesize_prose(concept, records, model, thinking) -> dict[str, str]`
  - `generate_chapter(methods_root, concept, model, thinking) -> str`
  - CLI: `litintel methodintel chapter <concept>`

**Verified against the real codebase, 2026-08-02.** There is no plain-text
Gemini helper. `enrich/ai_client.py` exposes `_call_gemini(client, model,
system_prompt, user_prompt, schema, thinking_level)` at `:135`, which is
JSON-mode only -- it sets `response_mime_type="application/json"` and passes
`response_schema`. So prose comes back as a **structured JSON object**, not as
labelled text. Reuse `_get_gemini_client()` (`:92`) rather than building a
second Vertex client (core directive A8).

- [ ] **Step 1: Write the failing tests**

Only the prompt builder and the response parser are unit-tested; the model call
itself is an integration concern (`tests/conftest.py` skips those unless
`--run-integration`).

```python
# tests/test_methodintel_synthesis.py
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
```

- [ ] **Step 2: Run and watch them fail**

```bash
venv/bin/python -m pytest tests/test_methodintel_synthesis.py -v
```
Expected: FAIL, `ModuleNotFoundError: No module named 'litintel.methodintel.synthesis'`.

- [ ] **Step 3: Implement `synthesis.py`**

```python
"""The one model call: reference records -> chapter prose.

Kept apart from chapters.py so the deterministic assembly stays testable
without a network, and so the prompt -- which is where chapter behavior
actually lives -- sits in one readable place.
"""

from __future__ import annotations

import os
from pathlib import Path

from litintel.methodintel.chapters import assemble_chapter
from litintel.methodintel.records import ReferenceRecord, load_concept_records


_SECTIONS = ("recommendation", "tradeoffs", "open_questions")

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
    "do not support."
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
    """Check the model's JSON object. Raises on a missing or empty section.

    Empty is rejected because assemble_chapter would otherwise emit a heading
    with nothing under it, which reads as "nothing to say here" rather than as
    the generation failure it is.
    """
    prose = {}
    for section in _SECTIONS:
        value = payload.get(section)
        if not isinstance(value, str) or not value.strip():
            raise ValueError("model response is missing or empty section %s" % section)
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


def generate_chapter(
    methods_root: Path,
    concept: str,
    model: str,
    thinking: str,
) -> str:
    """Full chapter text for one concept. Raises if the shard is empty."""
    root = Path(os.path.expanduser(str(methods_root)))
    records = load_concept_records(root, concept)
    if not records:
        raise ValueError(
            "no reference records for concept %r under %s" % (concept, root)
        )

    prose = synthesize_prose(concept, records, model, thinking)
    return assemble_chapter(concept, records, prose)
```

`_call_gemini` returns `(payload_dict, usage_dict)` -- see `ai_client.py:135-142`.
The usage dict is discarded here; if per-chapter cost tracking is wanted later
it is already available at this call site.

- [ ] **Step 4: Add the CLI command**

In `src/litintel/cli.py`, after `methodintel_sync_aliases`:

```python
@methodintel_app.command("chapter")
def methodintel_chapter(
    concept: str,
    config: str = "configs/tier1_pca.yaml",
    write: bool = typer.Option(False, help="Write chapters/<concept>.md instead of printing"),
):
    """Regenerate one chapter from its reference records.

    Writes into methods_repo_path but never commits -- the human reviews and
    commits in dotfiles, which is the D6 review gate.
    """
    import os
    from pathlib import Path

    from litintel.config import load_config_from_yaml
    from litintel.methodintel.synthesis import generate_chapter

    cfg = load_config_from_yaml(config)
    if not cfg.methods_repo_path:
        typer.secho("methods_repo_path is not set in %s" % config, fg=typer.colors.RED)
        raise typer.Exit(code=2)

    root = Path(os.path.expanduser(cfg.methods_repo_path))
    text = generate_chapter(root, concept, cfg.ai.pass2_model, cfg.ai.pass2_thinking)

    if not write:
        typer.echo(text)
        return

    target = root / "chapters" / ("%s.md" % concept)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text)
    typer.secho("wrote %s" % target, fg=typer.colors.GREEN)
    typer.echo("Review and commit in dotfiles -- this command does not commit.")
```

`AIConfig.pass2_model` and `AIConfig.pass2_thinking` are confirmed to exist
(`config.py:58-59`). Chapter synthesis reuses the Pass 2 model because a chapter
is the same kind of work -- long-context synthesis over method text.

- [ ] **Step 5: Run the tests**

```bash
venv/bin/python -m pytest tests/test_methodintel_synthesis.py -v
venv/bin/python -m pytest -q
```
Expected: 7 passed in the first, whole suite green in the second.

- [ ] **Step 6: Commit**

```bash
git add src/litintel/methodintel/synthesis.py src/litintel/cli.py \
        tests/test_methodintel_synthesis.py
git commit -m "feat: synthesize chapter prose and add the chapter CLI command"
```

---

## Task 9: Populate the clustering concept end to end

This is the first task that produces the actual deliverable rather than the
machinery for it. It runs entirely in `dotfiles-claude` plus one CLI call.

**Files:**
- Create: `~/GitHub/dotfiles-claude/skills/bioinfo-methods/references/clustering/` (4 records)
- Create: `~/GitHub/dotfiles-claude/skills/bioinfo-methods/chapters/clustering.md` (generated)
- Modify: `~/GitHub/dotfiles-claude/skills/bioinfo-methods/INDEX.md`

**Interfaces:**
- Consumes: everything from Tasks 1-8.
- Produces: the populated concept the acceptance criteria in Task 11 test.

- [ ] **Step 1: Write the benchmark record**

```markdown
<!-- references/clustering/2026-08-02-traag2019-louvain-connectivity.md -->
---
id: 2026-08-02-traag2019-louvain-connectivity
concept: clustering
modality: ["scRNA", "scATAC", "spatial_rna", "spatial_atac"]
methods: ["Louvain", "Leiden"]
kind: benchmark
recorded: 2026-08-02
source_ref:
  kind: doi
  value: "10.1038/s41598-019-41695-z"
  note: "Traag, Waltman, van Eck 2019"
citation:
  first_author: "Traag"
  journal: "Sci Rep"
  year: 2019
confidence: high
---

Louvain can yield arbitrarily badly connected, and in some cases disconnected,
communities. Leiden guarantees well-connected communities.

Bears on the ArchR Louvain -> Leiden decision at Apollo Stage 5.
```

`# VERIFY: confirm PMID/DOI 10.1038/s41598-019-41695-z resolves to Traag,`
`Waltman & van Eck, "From Louvain to Leiden", Sci Rep 2019 before committing.`
`This citation is carried from the spec's worked example and was NOT part of the`
`2026-08-02 seed verification.`

- [ ] **Step 2: Write the deprecation record**

```markdown
<!-- references/clustering/2026-08-02-louvain-legacy-status.md -->
---
id: 2026-08-02-louvain-legacy-status
concept: clustering
modality: ["scRNA"]
methods: ["Louvain"]
kind: deprecation
recorded: 2026-08-02
source_ref:
  kind: pmid
  value: "37002403"
  note: "Heumos et al. 2023, best practices across modalities"
citation:
  first_author: "Heumos"
  journal: "Nat Rev Genet"
  year: 2023
confidence: high
---

Leiden is the recommended default for scRNA-seq clustering; Louvain moves to
legacy status. Status set by owner confirmation, not inferred by a model (D6).
```

- [ ] **Step 3: Write the adaptation record**

This is the record type spec 3.4.4 calls the highest-value one, and the
acceptance criterion in section 8 requires it.

```markdown
<!-- references/clustering/2026-08-02-spatial-clustering-borrows-from-scrna.md -->
---
id: 2026-08-02-spatial-clustering-borrows-from-scrna
concept: clustering
modality: ["spatial_rna", "spatial_atac"]
methods: ["Leiden"]
implementations: ["Squidpy", "Scanpy"]
kind: adaptation
recorded: 2026-08-02
source_ref:
  kind: pmid
  value: "41332620"
  note: "OSTA, platform-independent analyses chapter"
citation:
  first_author: "Crowell"
  journal: "bioRxiv"
  year: 2025
confidence: medium
---

Spatial clustering borrows Leiden wholesale from scRNA-seq, but the borrowed
method assumes observations are independent given the latent space, and spatial
data violates that: neighbouring spots are autocorrelated by construction.
Spot-level assays compound this because a spot is a mixture of cells rather than
one cell.

The adaptation is to bring spatial position into the graph -- either by building
the neighbour graph on expression and position jointly, or by smoothing features
over spatial neighbours before clustering.

Recorded at medium confidence: the mechanism is well attested, but no benchmark
in this base yet quantifies how much the naive borrowing costs.
```

- [ ] **Step 4: Write the personal-observation record**

Feed 3 (spec 4.1) is the differentiator -- this record exists nowhere else.
Replace the body with a real Apollo observation before committing; do not
invent one.

```markdown
<!-- references/clustering/2026-08-02-apollo-archr-clustering-personal.md -->
---
id: 2026-08-02-apollo-archr-clustering-personal
concept: clustering
modality: ["spatial_atac"]
methods: ["Leiden", "Louvain"]
implementations: ["ArchR"]
kind: personal
recorded: 2026-08-02
source_ref:
  kind: personal_obs
  value: "Apollo Stage 5, ArchR spatial ATAC"
confidence: medium
---

# VERIFY: replace this body with the real Apollo Stage 5 observation before
# committing. Do not invent one -- an invented personal record poisons the one
# feed that cannot be reconstructed from public sources.
```

- [ ] **Step 5: Validate all four records parse**

```bash
cd ~/GitHub/Litintel-claude
venv/bin/python -c "
from pathlib import Path
from litintel.methodintel.records import load_concept_records
root = Path.home() / 'GitHub/dotfiles-claude/skills/bioinfo-methods'
for r in load_concept_records(root, 'clustering'):
    print(r.id, r.kind, r.modality)
"
```
Expected: four lines, kinds `adaptation`, `personal`, `deprecation`, `benchmark`
in id order.

- [ ] **Step 6: Generate the chapter**

```bash
venv/bin/litintel methodintel chapter clustering --write
```
Expected: `wrote /Users/kun-linho/GitHub/dotfiles-claude/skills/bioinfo-methods/chapters/clustering.md`

- [ ] **Step 7: Read the generated chapter and check it against its records**

Open `chapters/clustering.md`. Verify by eye:
- every factual sentence carries an `[id: ...]` marker;
- the References block lists only the three cited records (the personal one has
  no citation and must be absent);
- the Borrowed and broken section names `spatial_rna` and `spatial_atac` with
  the adaptation, and any modality lacking one says "not audited";
- no claim appears that no record supports.

If a claim has no record, that is a **generator or prompt defect**. Fix
`synthesis.py`'s prompt and regenerate. Do NOT hand-edit the chapter (D5).

- [ ] **Step 8: Update `INDEX.md`**

Fill the `clustering` row: current recommendation (one sentence, copied from
the chapter's Current recommendation), chapter link, and `2026-08-02` as last
reviewed.

- [ ] **Step 9: Commit in dotfiles**

```bash
cd ~/GitHub/dotfiles-claude
git add skills/bioinfo-methods
git commit -m "feat: populate the clustering concept end to end"
git -C ~/GitHub/dotfiles merge --ff-only claude
cd ~/GitHub/dotfiles && ./setup.sh
```

---

## Task 10: Tier 1 usage feed

**Files:**
- Create: `src/litintel/methodintel/writer.py`
- Modify: `src/litintel/pipeline/tier1.py`
- Test: `tests/test_methodintel_writer.py`

**Interfaces:**
- Consumes: `AppConfig.methods_repo_path` (Task 3), Pass 2 output.
- Produces: `write_usage_record(methods_root, concept, methods, implementations,
  modality, pmid, citation, body, recorded) -> Path`

**Verified against the real codebase, 2026-08-02.** `Tier1Record`
(`enrich/schema.py:54`) has no `FirstAuthor` and no `MethodsSummary`. The real
shape is `PMID: str`, `Authors: Optional[str]`, `Journal: Optional[str]`,
`Year: Optional[str]` (a **string**), `Methods: str`, `DataTypes: str`,
`RelevanceScore: int`, and `comp_methods: Optional[CompMethods]` (`:43`) whose
`analyses: List[AnalysisBlock]` (`:37`) each carry `analysis_name` and
`steps: List[AnalysisStep]` (`:31`) with `step`, `tool`, `rationale`. Records
flow through the pipeline as **dicts**, not model instances -- `tier1.py:264`
does `rec["comp_methods_error"] = ...`.

`analysis_name` is the concept handle, not the method name: `CONCEPT_ALIASES`
maps "clustering" -> `clustering`, and Leiden is a *method*, so looking a method
up in `CONCEPT_ALIASES` would always miss.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_methodintel_writer.py
import os
import sys
from datetime import date

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

import pytest

from litintel.methodintel.records import Citation, parse_record
from litintel.methodintel.writer import write_usage_record


def _citation():
    return Citation(first_author="Smith", journal="Nat Commun", year=2026)


def test_write_usage_record_produces_a_parseable_record(tmp_path):
    path = write_usage_record(
        tmp_path,
        concept="clustering",
        methods=["Leiden"],
        modality=["spatial_atac"],
        pmid="41234567",
        citation=_citation(),
        body="Used Leiden via ArchR for spatial ATAC clustering.",
        recorded=date(2026, 8, 2),
    )

    record = parse_record(path)
    assert record.kind == "usage"
    assert record.concept == "clustering"
    assert record.source_ref.value == "41234567"
    assert record.citation.journal == "Nat Commun"


def test_record_lands_in_the_concept_shard(tmp_path):
    path = write_usage_record(
        tmp_path, concept="clustering", methods=["Leiden"], modality=["scRNA"],
        pmid="1", citation=_citation(), body="x", recorded=date(2026, 8, 2),
    )

    assert path.parent == tmp_path / "references" / "clustering"


def test_implementations_are_recorded(tmp_path):
    path = write_usage_record(
        tmp_path, concept="clustering", methods=["Leiden"],
        implementations=["ArchR"], modality=["spatial_atac"],
        pmid="1", citation=_citation(), body="x", recorded=date(2026, 8, 2),
    )

    assert parse_record(path).implementations == ["ArchR"]


def test_one_paper_yields_one_record_per_concept(tmp_path):
    """pmid alone would collide: a study spans several concepts."""
    shared = dict(
        methods=["Leiden"], modality=["scRNA"], pmid="41234567",
        citation=_citation(), body="x", recorded=date(2026, 8, 2),
    )

    first = write_usage_record(tmp_path, concept="clustering", **shared)
    second = write_usage_record(tmp_path, concept="normalization", **shared)

    assert first != second
    assert first.exists() and second.exists()


def test_id_is_date_pmid_and_concept_so_reruns_do_not_duplicate(tmp_path):
    kwargs = dict(
        concept="clustering", methods=["Leiden"], modality=["scRNA"],
        pmid="41234567", citation=_citation(), body="x", recorded=date(2026, 8, 2),
    )

    first = write_usage_record(tmp_path, **kwargs)
    second = write_usage_record(tmp_path, **kwargs)

    assert first == second
    assert len(list((tmp_path / "references" / "clustering").glob("*.md"))) == 1


def test_existing_record_is_never_overwritten(tmp_path):
    """Layer 1 is append-only. A rerun must not rewrite history."""
    kwargs = dict(
        concept="clustering", methods=["Leiden"], modality=["scRNA"],
        pmid="41234567", citation=_citation(), recorded=date(2026, 8, 2),
    )

    path = write_usage_record(tmp_path, body="original", **kwargs)
    write_usage_record(tmp_path, body="changed", **kwargs)

    assert "original" in path.read_text()


def test_unknown_concept_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="concept"):
        write_usage_record(
            tmp_path, concept=None, methods=["Leiden"], modality=["scRNA"],
            pmid="1", citation=_citation(), body="x", recorded=date(2026, 8, 2),
        )
```

- [ ] **Step 2: Run and watch them fail**

```bash
venv/bin/python -m pytest tests/test_methodintel_writer.py -v
```
Expected: FAIL, `ModuleNotFoundError: No module named 'litintel.methodintel.writer'`.

- [ ] **Step 3: Implement `writer.py`**

```python
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
    contradicts the old one, never an overwrite.
    """
    if not concept:
        raise ValueError("concept is required; a usage record with no concept "
                         "cannot be filed into a shard")

    root = Path(os.path.expanduser(str(methods_root)))
    shard = root / "references" / concept
    shard.mkdir(parents=True, exist_ok=True)

    record_id = "%s-pmid%s-%s-usage" % (recorded.isoformat(), pmid, concept)
    path = shard / ("%s.md" % record_id)
    if path.exists():
        return path

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
```

- [ ] **Step 4: Run the tests**

```bash
venv/bin/python -m pytest tests/test_methodintel_writer.py -v
```
Expected: 7 passed.

- [ ] **Step 5: Wire it into Tier 1**

Read `src/litintel/pipeline/tier1.py` first and find where Pass 2 results are
fanned out to storage. Add the methods feed alongside the existing fan-out
targets, gated on config so a missing knowledge base is not an error:

```python
    # Usage feed (spec 4.1, feed 4): record which methods a high-scoring paper
    # actually used. Lagging signal -- it confirms adoption, it never discovers
    # a method. Guarded so Litintel keeps working with no knowledge base.
    if cfg.methods_repo_path and rec.get("RelevanceScore", 0) >= cfg.ai.pass2_min_score:
        _emit_usage_records(cfg, rec)
```

And the helpers, near the other per-record helpers in the same file:

```python
def _first_author_surname(authors: str) -> str:
    """'Smith J; Doe A' or 'Smith J, Doe A' -> 'Smith'. Best effort, never raises."""
    head = (authors or "").replace(";", ",").split(",")[0].strip()
    return head.split()[0] if head else "unknown"


def _emit_usage_records(cfg, rec):
    """One usage record per analysis block whose concept we recognize.

    A paper contributes to several concepts at once -- an scRNA study does
    clustering AND normalization AND annotation -- so this emits one record per
    resolvable analysis rather than picking a single winner.

    Never raises into the pipeline run: an unwritable knowledge base must not
    fail a literature run whose real outputs are Notion and Drive.
    """
    from litintel.methodintel.records import Citation
    from litintel.methodintel.router import (
        CONCEPT_ALIASES,
        IMPLEMENTATION_ALIASES,
        METHOD_ALIASES,
    )
    from litintel.methodintel.writer import write_usage_record

    comp = rec.get("comp_methods") or {}
    analyses = comp.get("analyses") or []
    if not analyses:
        return

    year_raw = (rec.get("Year") or "").strip()
    citation = Citation(
        first_author=_first_author_surname(rec.get("Authors", "")),
        journal=rec.get("Journal") or "unknown",
        year=int(year_raw) if year_raw.isdigit() else 0,
    )
    modality = [d.strip() for d in (rec.get("DataTypes") or "").split(";") if d.strip()]

    for block in analyses:
        name = (block.get("analysis_name") or "").strip().lower()
        concept = CONCEPT_ALIASES.get(name)
        if concept is None:
            # An unrecognized analysis name is a LEXICON gap, not an error. Log
            # it: these logs are the raw material for the next lexicon pass.
            logger.info(
                "methods feed: no concept for analysis %r (pmid %s)",
                block.get("analysis_name"), rec.get("PMID"),
            )
            continue

        steps = block.get("steps") or []
        text = " ".join(
            "%s %s" % (s.get("step", ""), s.get("tool", "")) for s in steps
        ).lower()
        methods = sorted({v for k, v in METHOD_ALIASES.items() if k in text})
        implementations = sorted(
            {v for k, v in IMPLEMENTATION_ALIASES.items() if k in text}
        )
        if not methods and not implementations:
            continue

        try:
            write_usage_record(
                cfg.methods_repo_path,
                concept=concept,
                methods=methods,
                implementations=implementations,
                modality=modality,
                pmid=str(rec["PMID"]),
                citation=citation,
                body=(comp.get("summary_2to3_sentences") or "").strip()
                     or "Methods extracted by Pass 2.",
                recorded=date.today(),
            )
        except OSError as exc:
            logger.warning("methods feed: could not write record: %s", exc)
```

The `pmid` alone is no longer unique -- one paper now yields several records --
so `write_usage_record` must fold `concept` into the id. Adjust the id line in
`writer.py` accordingly and update `test_id_is_date_and_pmid_so_reruns_do_not_duplicate`:

```python
    record_id = "%s-pmid%s-%s-usage" % (recorded.isoformat(), pmid, concept)
```

- [ ] **Step 6: Run Tier 1 against a small live batch**

```bash
venv/bin/litintel tier1 --config configs/tier1_pca.yaml --limit 5
ls -1 ~/GitHub/dotfiles-claude/skills/bioinfo-methods/references/*/*usage*.md
```
Expected: at least one usage record file exists. If the batch produced no paper
scoring `>= 88`, raise `--limit` and rerun -- do not lower the threshold.

- [ ] **Step 7: Run the full suite**

```bash
venv/bin/python -m pytest -q
```
Expected: all green.

- [ ] **Step 8: Commit both repos**

```bash
cd ~/GitHub/Litintel-claude
git add src/litintel/methodintel/writer.py src/litintel/pipeline/tier1.py \
        tests/test_methodintel_writer.py
git commit -m "feat: emit usage records from tier 1 pass 2"

cd ~/GitHub/dotfiles-claude
git add skills/bioinfo-methods/references
git commit -m "data: first tier 1 usage records"
```

---

## Task 11: Acceptance -- prove the base answers a question and records a change

No new production code. This task runs the spec's section 8 criteria and
records the result.

**Files:**
- Modify: `~/GitHub/dotfiles-claude/skills/bioinfo-methods/chapters/clustering.md` (regenerated)
- Create: `~/GitHub/dotfiles-claude/skills/bioinfo-methods/references/clustering/2026-08-02-leiden-current-spatial-atac.md`

- [ ] **Step 1: Prove the query path in the user's own words**

In a fresh Claude session, ask, verbatim:

> What method should I use for spatial region niche analysis?

Expected: the session reads `INDEX.md`, fails to match "spatial region niche
analysis" against a concept name, consults `LEXICON.md`, resolves it to
`neighborhood_analysis`, and reports that the chapter does not exist yet -- a
**gap**, correctly named. That is a pass: it proves the lexicon hop works and
that the skill refuses to fill a gap from memory.

Then ask:

> Should I use Louvain or Leiden?

Expected: an answer from `chapters/clustering.md`, with numbered citations, and
**no web search**. If it searches, `SKILL.md`'s "prefer this over a web search"
instruction is too weak -- strengthen it and retest.

- [ ] **Step 2: Add a record that changes a status**

```markdown
<!-- references/clustering/2026-08-02-leiden-current-spatial-atac.md -->
---
id: 2026-08-02-leiden-current-spatial-atac
concept: clustering
modality: ["spatial_atac"]
methods: ["Leiden"]
kind: best_practice
recorded: 2026-08-02
source_ref:
  kind: pmid
  value: "36922587"
  note: "Zhang et al. 2023, spatial epigenome-transcriptome co-profiling"
citation:
  first_author: "Zhang"
  journal: "Nature"
  year: 2023
confidence: medium
---

Spatial ATAC clustering in the flagship co-profiling assay uses per-modality
LSI plus joint clustering, with Leiden on the joint graph. Sets Leiden as the
current default for spatial ATAC, at medium confidence: this is one method
paper, not a benchmark.
```

- [ ] **Step 3: Regenerate and diff**

```bash
cd ~/GitHub/Litintel-claude
venv/bin/litintel methodintel chapter clustering --write
git -C ~/GitHub/dotfiles-claude diff -- skills/bioinfo-methods/chapters/clustering.md
```
Expected: a readable diff showing the spatial ATAC status change, with the new
record in the References block. **This diff is the changelog** -- it is what D5
buys, and seeing it is the acceptance criterion, not the commit.

- [ ] **Step 4: Walk the section 8 checklist**

Open the spec's section 8 and check each box against observed output, not
assumption. Every one must pass except those the owner has explicitly deferred.
Report any that fail rather than adjusting the criterion.

- [ ] **Step 5: Commit in dotfiles and land**

```bash
cd ~/GitHub/dotfiles-claude
git add skills/bioinfo-methods
git commit -m "feat: spatial ATAC clustering status, chapter regenerated"
git -C ~/GitHub/dotfiles merge --ff-only claude
cd ~/GitHub/dotfiles && ./setup.sh
```

- [ ] **Step 6: Land the Litintel branch**

```bash
git -C ~/GitHub/Litintel merge --ff-only claude
```

---

## Out of scope for this plan

Named so they are not silently attempted. All are from the spec's section 7 or
its open questions:

- **Notion methods DB.** Deferred (spec section 7). Git is the source of truth
  (D3); a Notion view can be added later without changing anything here.
- **Feed 2, targeted evidence retrieval.** Spec 4.1 defines it as agent
  retrieval for an already-named `(concept, method)` pair via
  `source_plan.py::build_source_plan()`. v1 populates layer 1 from feeds 1, 3
  and 4 only; feed 2 is what makes the base grow on demand and is the natural
  next plan.
- **Tier 2 semantic concept matching.** `build_concept_aliases()` is tier 1
  only. Semantic match against `ConceptEntry.question` needs the Vertex RAG
  corpus and is a separate plan.
- **The coverage audit as tooling.** Spec 3.4.1 defines it; whether it runs
  manually or as a `staleness_check` invocation is open question 2.
- **Chapter regeneration cost budget.** Open question 3, unestimated.
- **Backfilling concepts beyond clustering.** `neighborhood_analysis` and
  `normalization` are seeded in `LEXICON.md` and listed in `INDEX.md` with no
  chapter. That is the correct v1 state: a named gap beats a thin chapter.
- **The Shadow Judge path.** Untouched scaffolding in `ai_client.py`; not this
  plan's business.
