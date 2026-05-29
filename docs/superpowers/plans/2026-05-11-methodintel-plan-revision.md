# MethodIntel Plan Revision Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Apply the 11 fixes from the 2026-05-11 plan review: reconcile the three MethodIntel design docs, shrink the Phase 1 schema to a thin Stage-5-only MVP, make evidence grounding structural via a typed `SourceRef`, and add the missing `MethodGraphEdge` model -- so MethodIntel Phase 1 hand-off is implementation-ready.

**Architecture:** Phase 1 is doc-only edits (no behavior change). Phase 2 is the thin dossier schema written TDD-first, appended to the existing `src/litintel/methodintel/schema.py`. Phase 3 adds an `EvidenceClaim` PMID verifier in a new `verify.py` that reuses the existing `litintel.pubmed.client.fetch_details` rather than re-implementing PubMed access.

**Tech Stack:** Python 3.12, Pydantic v2, pytest, existing `litintel.pubmed.client` for PMID resolution.

---

## Pre-flight check

Before starting, confirm these decisions (already endorsed by the user in the review reply):

- **D1.** Phase 0 Notion direction: **manual-input only for v1**. Automatic Notion fetch deferred to Phase 5.
- **D2.** Router code state: `src/litintel/methodintel/router.py` + `schema.py` + `source_plan.py` are already implemented, with 6 passing tests in `tests/test_methodintel_router.py`. Router Phase A in `methodintel_router_todo.md` is therefore **complete** -- the boxes will be checked in Task 2.

If either D1 or D2 changes, stop and re-review before continuing.

---

## File Structure

**Doc files modified (Phase 1):**
- `docs/methodintel_plan.md` -- mode taxonomy, vocabulary, schema scope, Stage 5 config sketch, lifecycle collapse, retrieval pattern, cost budget, Phase 0 resolution.
- `docs/methodintel_artifacts.md` -- `last_revised` date, cross-link to plan.md vocabulary.
- `docs/methodintel_router_todo.md` -- Phase A checkboxes marked done, `verify_items` typed, `last_revised` date.

**Code files added/modified (Phase 2-3):**
- Modify: `src/litintel/methodintel/schema.py` -- append thin dossier models + `MethodGraphEdge`. Router models above stay untouched.
- Create: `src/litintel/methodintel/verify.py` -- `verify_evidence_claims()` validator using PubMed client.
- Create: `tests/test_methodintel_dossier_schema.py` -- unit tests for the new models.
- Create: `tests/test_methodintel_verify.py` -- tests for evidence verifier with mocked PubMed.

**Out of scope (do not touch in this plan):**
- `router.py`, `source_plan.py`, existing `test_methodintel_router.py` -- already working.
- Phase 2+ build_dossier.py / prompts.py / notion_export.py -- those are downstream of this revision.

---

## Phase 1 -- Doc Revisions (no TDD, straight edits)

Doc tasks are single edit + commit pairs. Each task ends with a commit so plan progress is visible in git history.

### Task 1: Resolve Phase 0 Notion decision in plan.md

**Files:**
- Modify: `docs/methodintel_plan.md` (Phase 0 section, around line 293-298)

- [ ] **Step 1: Update Phase 0 checklist with the resolved decision**

In `docs/methodintel_plan.md`, replace the Phase 0 block:

```markdown
### Phase 0 - Design Contract

- [ ] Keep this plan as the working contract.
- [ ] Confirm MethodIntel stays inside the LitIntel repo for v1.
- [ ] Confirm Stage 5 clustering is the first MVP.
- [ ] Decide whether Notion pages are manual inputs for v1 or fetched automatically.
```

with:

```markdown
### Phase 0 - Design Contract

- [x] Keep this plan as the working contract.
- [x] Confirm MethodIntel stays inside the LitIntel repo for v1.
- [x] Confirm Stage 5 clustering is the first MVP.
- [x] Notion direction for v1: **manual-input only**. The user pastes or
      provides a Markdown export of the existing Notion Stage 5 page as
      the dossier's source-of-context. Automatic Notion fetch is deferred
      to Phase 5; the Notion client in this repo stays write-only until
      then.
```

- [ ] **Step 2: Commit**

```bash
git add docs/methodintel_plan.md
git commit -m "docs(methodintel): resolve Phase 0 Notion direction as manual-input for v1"
```

### Task 2: Mark router Phase A complete in router_todo.md

**Files:**
- Modify: `docs/methodintel_router_todo.md` (Phase A section, around lines 140-147)

- [ ] **Step 1: Check Phase A boxes and add an implementation note**

In `docs/methodintel_router_todo.md`, replace the Phase A block:

```markdown
### Phase A - Static Router

- [ ] Create `src/litintel/methodintel/router.py`.
- [ ] Implement rule-based routing for the five MVP modes.
- [ ] Add `RouterDecision` Pydantic model.
- [ ] Add tests with example user questions.
- [ ] Return `missing_constraints` instead of asking interactively at first.
```

with:

```markdown
### Phase A - Static Router (implemented 2026-05-11)

- [x] Create `src/litintel/methodintel/router.py`.
- [x] Implement rule-based routing for the five MVP modes.
- [x] Add `RouterDecision` Pydantic model (`src/litintel/methodintel/schema.py`).
- [x] Add tests with example user questions (`tests/test_methodintel_router.py`,
      6 cases covering all five modes plus implementation-only routing).
- [x] Return `missing_constraints` instead of asking interactively at first.
```

- [ ] **Step 2: Commit**

```bash
git add docs/methodintel_router_todo.md
git commit -m "docs(methodintel): mark router Phase A complete (router.py implemented with 6 tests)"
```

### Task 3: Add Vocabulary section to plan.md

**Files:**
- Modify: `docs/methodintel_plan.md` (insert before the "Purpose" section)

- [ ] **Step 1: Insert Vocabulary section near the top of plan.md**

After the file header (lines 1-6, the `# MethodIntel Plan` block plus Status/Date/Context lines), insert a new section before `## Purpose`:

```markdown
## Vocabulary

These distinctions are load-bearing for the schema. They are written here once
so every downstream document uses the same words.

- **Method / algorithm**: a procedure independent of any package -- Louvain,
  Leiden, SLM, Wilcoxon, edgeR-style negative-binomial dispersion modeling.
- **Implementation / package**: a piece of software that exposes one or more
  methods -- ArchR, Seurat, Scanpy, SnapATAC2. An implementation may expose
  several methods (Seurat `FindClusters(algorithm=)` covers Louvain, Leiden,
  SLM, Leiden-refined) and may call other packages under the hood.
- **Stack / ecosystem**: the set of implementations a project commits to --
  e.g. "ArchR-centered scATAC pipeline" implies fragment files, Arrow
  storage, ArchR-style peak sets, and ArchR-callable methods.
- **Dossier**: a structured comparison artifact for one decision question --
  e.g. "Stage 5 clustering: ArchR Louvain vs ArchR Leiden vs SnapATAC2
  transplant".
- **Decision** = method choice + implementation choice + ecosystem fit +
  validation burden. A dossier MUST keep these four axes separable. A
  recommendation that confuses "Leiden is better" with "SnapATAC2 is
  better" is a failure mode this system exists to prevent.
```

- [ ] **Step 2: Commit**

```bash
git add docs/methodintel_plan.md
git commit -m "docs(methodintel): add Vocabulary section pinning method/implementation/stack distinction"
```

### Task 4: Reconcile mode taxonomy across the three docs

**Files:**
- Modify: `docs/methodintel_plan.md` (Entry Modes section, lines 105-185)
- Modify: `docs/methodintel_artifacts.md` (add cross-reference to plan.md)

- [ ] **Step 1: Replace plan.md's three-mode Entry Modes section with the canonical 5-mode taxonomy**

In `docs/methodintel_plan.md`, replace the entire `## Entry Modes` section (the block describing method-first / stage-first / problem-first) with:

```markdown
## Entry Modes

MethodIntel supports **five internal modes**, matching the router
implementation in `src/litintel/methodintel/router.py` and the artifact
spec in `methodintel_artifacts.md`.

| Internal mode         | Artifact                       | User-facing mental model |
|-----------------------|--------------------------------|---------------------------|
| `learn_method`        | method card                    | method-first              |
| `compare_methods`     | decision dossier               | method-first or stage-first |
| `choose_for_dataset`  | context-specific recommendation| problem-first             |
| `stage_overview`      | stage map                      | stage-first               |
| `staleness_check`     | lifecycle report               | method-first (legacy lens)|

The three user-facing entry styles ("method-first", "stage-first",
"problem-first") are a *prompting affordance* -- they shape how the user
starts a question. The five internal modes are how the router and source
planner reason about the question after classification. Do not introduce
a fourth user-facing style or a sixth internal mode without revising this
table, `router.py::RouterMode`, and the artifacts doc together.

### Design rule

> Method cards prevent shallow learning. Stage maps prevent blind spots.
> Decision dossiers force concrete recommendations with trade-offs.
> Context recommendations bridge "I have a dataset" to a routed dossier.
> Lifecycle reports prevent training-era defaults from leaking into
> current advice.
```

- [ ] **Step 2: Add a one-line cross-reference at the top of methodintel_artifacts.md**

In `docs/methodintel_artifacts.md`, insert under the existing header block (after line 5, before `## Core Idea`):

```markdown
> **Cross-references:** Mode taxonomy is defined canonically in
> [`methodintel_plan.md` Entry Modes](methodintel_plan.md#entry-modes).
> Vocabulary (method vs implementation vs stack) lives in
> [`methodintel_plan.md` Vocabulary](methodintel_plan.md#vocabulary).
```

- [ ] **Step 3: Commit**

```bash
git add docs/methodintel_plan.md docs/methodintel_artifacts.md
git commit -m "docs(methodintel): unify mode taxonomy on the 5 internal modes across plan and artifacts docs"
```

### Task 5: Shrink Phase 1 schema scope in plan.md

**Files:**
- Modify: `docs/methodintel_plan.md` (Core Objects section + Phase 1 task list)

- [ ] **Step 1: Replace the Core Objects section with the thin v1 schema list**

In `docs/methodintel_plan.md`, replace the `## Core Objects` block (the unstructured 12-item list) with:

```markdown
## Core Objects

The Phase 1 schema ships only what one Stage 5 dossier needs. Graph nodes,
lifecycle nodes, and reusable heuristic nodes are deferred to Phase 4.5
(schema expansion) so the first dossier can validate the shape before the
schema sprawls.

### Phase 1 (thin -- ships with the MVP)

- `MethodDecisionDossier` -- top-level container for one decision question.
- `MethodOption` -- one candidate in the decision (e.g. "ArchR Louvain").
- `EvidenceClaim` -- one supported assertion, with a required `source_ref`.
- `SourceRef` -- typed union (PMID | DOI | URL | docs_url | github_url |
  personal_obs). Non-optional on every `EvidenceClaim`.
- `TradeoffDimension` -- one axis on the trade-off matrix (e.g. "reference
  frame consistency"), with per-option values.
- `ValidationExperiment` -- a concrete experiment that would resolve the
  decision.
- `MethodGraphEdge` -- `{src, dst, edge_type, evidence_ref?}`. v1 stores
  the graph as JSON only; the model exists now so the graph is queryable
  before a visual view is added.

### Phase 4.5 (deferred -- after one dossier validates Phase 1)

- `StageNode`, `MethodNode`, `ImplementationNode`, `EvidenceNode`,
  `DecisionDossierNode`, `HeuristicNode` -- graph-oriented node types.
- `DecisionHeuristic` and `FailureMode` -- promoted from inline fields to
  first-class nodes once we see how they cluster across multiple dossiers.
- Lifecycle taxonomy expansion (see Method Lifecycle section).

### Schema rules

- Every `EvidenceClaim` MUST carry a `source_ref`. A claim without a
  resolvable source is a schema violation, not a `# VERIFY` string.
- `MethodOption.benchmark_evidence: list[EvidenceClaim]` -- typed, not
  free-form prose.
- Implementation and algorithm are separate fields on `MethodOption`
  (`algorithm`, `implementation`, `version`) -- never merged into a
  single "method name" string.
```

- [ ] **Step 2: Update the Phase 1 task list to match**

In `docs/methodintel_plan.md`, replace the `### Phase 1 - Schema Draft` task block with:

```markdown
### Phase 1 - Schema Draft (thin)

- [ ] Append the v1 dossier models to
      `src/litintel/methodintel/schema.py` (router models already live
      there; appending keeps all MethodIntel data shapes co-located).
- [ ] Models: `SourceRef`, `EvidenceClaim`, `TradeoffDimension`,
      `MethodOption`, `ValidationExperiment`, `MethodDecisionDossier`,
      `MethodGraphEdge`.
- [ ] `EvidenceClaim.source_ref` is required, not optional.
- [ ] `MethodOption` keeps `algorithm`, `implementation`, and `version`
      as separate fields.
- [ ] Lifecycle status on `MethodOption` collapses to
      `{current, under_review, legacy}` + `last_reviewed: date` +
      `successor_methods: list[str]` for v1. The 6-tier enum is deferred
      to Phase 4.5.
- [ ] Add `src/litintel/methodintel/verify.py` with
      `verify_evidence_claims(claims)` that resolves each PMID
      `source_ref` against `litintel.pubmed.client.fetch_details` and
      sets a `verified=True/False` flag on the claim. Other source-ref
      types (DOI/URL/docs/github/personal_obs) are marked
      `verified=None` (out of scope for the PMID verifier).
- [ ] Add unit tests covering: required-field violations, JSON
      serialization round-trip, PMID verifier happy path with a mocked
      PubMed response, PMID verifier failure path when the PMID is not
      returned.
- [ ] Keep schema small enough to revise after one dossier.
```

- [ ] **Step 3: Commit**

```bash
git add docs/methodintel_plan.md
git commit -m "docs(methodintel): shrink Phase 1 schema to thin v1 set; defer graph/lifecycle nodes to Phase 4.5"
```

### Task 6: Sketch Stage 5 config field list in plan.md

**Files:**
- Modify: `docs/methodintel_plan.md` (Phase 2 section)

- [ ] **Step 1: Replace Phase 2 block with a concrete YAML sketch**

In `docs/methodintel_plan.md`, replace the `### Phase 2 - Stage 5 Config` task block with:

```markdown
### Phase 2 - Stage 5 Config

Concrete shape for `configs/methodintel_stage5_clustering.yaml`:

```yaml
stage: clustering
decision_question: >
  Should the Apollo spatial ATAC pipeline keep ArchR Louvain, switch to
  Leiden inside ArchR, transplant SnapATAC2 labels/embedding into ArchR,
  or migrate fully to SnapATAC2?
current_stack: ArchR
modality: scATAC
platform: spatial ATAC
biological_goal: cell typing  # or substate/subclone discovery
scale:
  samples_now: 10
  samples_target: 90
  cells_per_sample_estimate: TBD
candidate_options:
  - name: ArchR Louvain
    algorithm: Louvain
    implementation: ArchR
  - name: ArchR Leiden
    algorithm: Leiden
    implementation: ArchR
  - name: SnapATAC2 Leiden (transplant)
    algorithm: Leiden
    implementation: SnapATAC2
    transplant_into: ArchR
  - name: Full SnapATAC2 migration
    algorithm: Leiden
    implementation: SnapATAC2
source_hints:
  notion_export_path: <path to manually exported Stage 5 Notion page>
  benchmark_pmids: []      # filled by source planner during build
  original_pmids: []
constraints:
  - reference_frame_consistency: must be preserved end-to-end
  - downstream_validation_burden: stay minimal until Stage 5 is settled
```

Tasks:

- [ ] Add `configs/methodintel_stage5_clustering.yaml` with the shape above.
- [ ] Fill the four candidate options for the MVP.
- [ ] Leave `cells_per_sample_estimate` as `TBD` until Apollo confirms.
- [ ] Do not populate `benchmark_pmids` / `original_pmids` manually --
      the source planner fills them at build time.
```

- [ ] **Step 2: Commit**

```bash
git add docs/methodintel_plan.md
git commit -m "docs(methodintel): sketch Stage 5 config YAML shape with candidate options"
```

### Task 7: Add retrieval-then-synthesize pattern, lifecycle collapse, and cost budget

**Files:**
- Modify: `docs/methodintel_plan.md` (Phase 3, Method Lifecycle section, plus a new Cost section)

- [ ] **Step 1: Replace the Phase 3 block with the retrieval-then-synthesize pattern**

In `docs/methodintel_plan.md`, replace `### Phase 3 - Local Dossier Builder` with:

```markdown
### Phase 3 - Local Dossier Builder

The builder is **retrieval-then-synthesize**, not a single end-to-end LLM
call. This pattern is the structural defense against the failure mode
this system exists to prevent (LLM-generated dossiers with fabricated
benchmark numbers).

Pipeline:

```
config -> router_decision (already routed for Stage 5)
       -> source_planner -> SourceTask[]
       -> retrieve (PubMed / Notion file / docs / github metadata)
       -> assemble context bundle
       -> LLM synthesize -> MethodDecisionDossier JSON
       -> verify_evidence_claims (PubMed resolution for PMID refs)
       -> write JSON + Markdown
```

Tasks:

- [ ] Add `src/litintel/methodintel/build_dossier.py` implementing the
      pipeline above.
- [ ] Add prompt template in `src/litintel/methodintel/prompts.py`.
- [ ] Prompt MUST require every claim in the LLM output to carry a
      `source_ref` matching one of the retrieved sources.
- [ ] Run `verify_evidence_claims()` after parsing the LLM JSON. Claims
      that fail PMID resolution are kept in the dossier but flagged
      `verified=False`; the Markdown renderer surfaces them in a
      "Claims requiring follow-up" block.
- [ ] Generate JSON and Markdown outputs from the config.
- [ ] Do not write to Notion yet.
```

- [ ] **Step 2: Replace the Method Lifecycle section with the collapsed v1 enum**

In `docs/methodintel_plan.md`, replace the `## Method Lifecycle and Staleness` section's enum list (the six-tier `lifecycle_status` block plus the surrounding bullet list) with:

```markdown
## Method Lifecycle and Staleness

MethodIntel should track whether a method is current, under review, or
legacy. This matters because methods can stay familiar long after the
field moves on (e.g. Cufflinks for RNA-seq quantification).

### v1 (thin)

Each `MethodOption` carries:

- `lifecycle_status`: one of `{current, under_review, legacy}`.
- `last_reviewed`: ISO date the status was last confirmed.
- `successor_methods`: list of canonical method names that have
  largely replaced this method.

Assignment rule for v1: lifecycle status is **user-confirmed**, not
LLM-inferred. The LLM may propose a status with rationale, but the
final value in the persisted JSON is whatever the human reviewer
accepts during the Phase 4 review pass. This prevents training-era
defaults from masquerading as authoritative lifecycle data.

### Phase 4.5 (deferred)

Expand to the six-tier enum (`emerging`, `current_default`,
`established_alternative`, `legacy`, `deprecated`, `context_specific`)
plus the staleness-signal fields, only after the v1 enum proves too
coarse for at least two real dossiers.
```

- [ ] **Step 3: Add a new Cost & Cache Budget section**

In `docs/methodintel_plan.md`, insert a new section between `## Expected Outputs` and `## Phased Action Items`:

```markdown
## Cost and Cache Budget

MethodIntel hits Gemini Pro/Flash plus PubMed retrieval per dossier.
The MVP cadence is one dossier at a time, human-reviewed, so the
budget is small but should be explicit.

- Per dossier build: target <= 50k input tokens + <= 10k output tokens
  to Gemini, plus <= 20 PubMed `efetch` calls (batched).
- PubMed responses cached on disk keyed by PMID for 30 days. Cache
  invalidation on demand only -- no background refresh in v1.
- Source-plan dry-run mode (no LLM, no retrieval) is free and is the
  default before a paid build.
- Lifecycle re-checks reuse the same dossier path; the only delta is
  re-running `verify_evidence_claims()` against the existing JSON.
```

- [ ] **Step 4: Commit**

```bash
git add docs/methodintel_plan.md
git commit -m "docs(methodintel): retrieval-then-synthesize pipeline, v1 lifecycle enum, cost/cache budget"
```

### Task 8: Apply nits to plan.md and router_todo.md

**Files:**
- Modify: `docs/methodintel_plan.md` (Decision Heuristics section; add `last_revised` line)
- Modify: `docs/methodintel_router_todo.md` (Router Output Schema; add `last_revised` line)
- Modify: `docs/methodintel_artifacts.md` (add `last_revised` line)

- [ ] **Step 1: Tighten the limma/edgeR example in Decision Heuristics**

In `docs/methodintel_plan.md`, in the `## Decision Heuristics` section, replace the bullet that begins `- limma vs DESeq2 vs edgeR:` with:

```markdown
- limma vs DESeq2 vs edgeR: choice depends on data type, replicate
  structure, and dispersion modeling. For bulk RNA-seq, `limma-voom`,
  `edgeR`, and `DESeq2` are all defensible defaults. For single-cell
  pseudo-bulk DA/DE the practical ranking is roughly
  `edgeR ~= DESeq2 > limma-voom`, because the count distribution at
  small per-group replicate counts is better captured by NB-with-shrunk-
  dispersion than by voom's mean-variance trend. Cell-level Wilcoxon is
  useful only for cluster-marker discovery, not for replicated condition
  testing.
```

- [ ] **Step 2: Type the `verify_items` field in router_todo.md**

In `docs/methodintel_router_todo.md`, in the `## Router Output Schema` block, replace the `verify_items` line and add a new `VerifyItem` definition note. Locate:

```yaml
verify_items:
  - Confirm ArchR/Seurat parameter support for current installed versions.
```

Replace with:

```yaml
verify_items:
  - claim: ArchR/Seurat parameter support for current installed versions.
    why_uncertain: API drift between major releases.
    resolution_method: Pin versions and re-run the dossier with version-stamped sources.
```

And add this note immediately under the YAML block:

```markdown
> The router currently emits `verify_items` as a list of strings. Promoting
> the field to a `list[VerifyItem]` Pydantic model with `{claim, why_uncertain,
> resolution_method}` is a follow-up task tracked in Phase A.1 below.
```

Then append a new subsection right after `### Phase A - Static Router (implemented 2026-05-11)`:

```markdown
### Phase A.1 - VerifyItem typing follow-up

- [ ] Add `VerifyItem` Pydantic model to `src/litintel/methodintel/schema.py`.
- [ ] Change `RouterDecision.verify_items` from `list[str]` to `list[VerifyItem]`.
- [ ] Update `tests/test_methodintel_router.py` to assert the structured shape.
- [ ] Keep a backward-compat helper that accepts plain strings during transition.
```

- [ ] **Step 3: Add a `last_revised` line under each doc header**

In `docs/methodintel_plan.md`, under the `**Status:** Draft` / `**Date:** 2026-05-11` / `**Context:** ...` header block, add:

```markdown
**Last revised:** 2026-05-11 (post-review fixes from `docs/superpowers/plans/2026-05-11-methodintel-plan-revision.md`)
```

Do the same for `docs/methodintel_artifacts.md` and `docs/methodintel_router_todo.md`, placing the `**Last revised:**` line immediately after the existing `**Purpose:**` line.

- [ ] **Step 4: Commit**

```bash
git add docs/methodintel_plan.md docs/methodintel_router_todo.md docs/methodintel_artifacts.md
git commit -m "docs(methodintel): tighten limma/DE example, type verify_items, add last_revised stamps"
```

---

## Phase 2 -- Phase 1 Schema Implementation (TDD)

### Task 9: Write failing tests for the thin dossier schema

**Files:**
- Create: `tests/test_methodintel_dossier_schema.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_methodintel_dossier_schema.py`:

```python
import os
import sys
from datetime import date

import pytest
from pydantic import ValidationError

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from litintel.methodintel.schema import (
    EvidenceClaim,
    LifecycleStatus,
    MethodDecisionDossier,
    MethodGraphEdge,
    MethodOption,
    SourceRef,
    SourceRefKind,
    TradeoffDimension,
    ValidationExperiment,
)


def _pmid_source_ref() -> SourceRef:
    return SourceRef(kind=SourceRefKind.PMID, value="31178118")


def _evidence_claim() -> EvidenceClaim:
    return EvidenceClaim(
        statement="Leiden guarantees well-connected communities.",
        source_ref=_pmid_source_ref(),
    )


def _method_option() -> MethodOption:
    return MethodOption(
        name="ArchR Leiden",
        algorithm="Leiden",
        implementation="ArchR",
        version=None,
        lifecycle_status=LifecycleStatus.CURRENT,
        last_reviewed=date(2026, 5, 11),
        successor_methods=[],
        benchmark_evidence=[_evidence_claim()],
    )


def test_evidence_claim_requires_source_ref():
    with pytest.raises(ValidationError):
        EvidenceClaim(statement="Leiden is faster.")  # type: ignore[call-arg]


def test_source_ref_round_trip_json():
    ref = _pmid_source_ref()
    payload = ref.model_dump_json()
    restored = SourceRef.model_validate_json(payload)
    assert restored == ref


def test_method_option_keeps_algorithm_and_implementation_separate():
    option = _method_option()
    assert option.algorithm == "Leiden"
    assert option.implementation == "ArchR"
    assert option.benchmark_evidence[0].source_ref.kind == SourceRefKind.PMID


def test_method_option_rejects_unknown_lifecycle_status():
    with pytest.raises(ValidationError):
        MethodOption(
            name="ArchR Leiden",
            algorithm="Leiden",
            implementation="ArchR",
            lifecycle_status="emerging",  # not in the v1 enum
            last_reviewed=date(2026, 5, 11),
        )


def test_dossier_round_trip_json():
    dossier = MethodDecisionDossier(
        decision_question="ArchR Louvain vs ArchR Leiden vs SnapATAC2 transplant",
        stage="clustering",
        options=[_method_option()],
        tradeoffs=[
            TradeoffDimension(
                name="reference frame consistency",
                description="Embedding compatibility with ArchR downstream tools.",
                per_option={"ArchR Leiden": "preserved"},
            )
        ],
        validation_experiment=ValidationExperiment(
            summary="Compare cluster stability across the four options on 3 samples.",
            success_criterion="ARI >= 0.7 between ArchR Leiden and ArchR Louvain on cell typing.",
        ),
        recommendation="Adopt ArchR Leiden as the default; gate SnapATAC2 transplant on substate work.",
    )

    payload = dossier.model_dump_json()
    restored = MethodDecisionDossier.model_validate_json(payload)
    assert restored == dossier


def test_method_graph_edge_requires_known_edge_type():
    edge = MethodGraphEdge(src="Leiden", dst="Louvain", edge_type="competes_with")
    assert edge.evidence_ref is None

    with pytest.raises(ValidationError):
        MethodGraphEdge(src="Leiden", dst="Louvain", edge_type="frobnicates")
```

- [ ] **Step 2: Run the failing tests**

Run:

```bash
cd /Volumes/Research/GitHub/Litintel && python -m pytest tests/test_methodintel_dossier_schema.py -v
```

Expected: all tests fail with `ImportError: cannot import name 'EvidenceClaim' from 'litintel.methodintel.schema'` (or equivalent), because the models do not exist yet.

### Task 10: Implement the thin dossier schema

**Files:**
- Modify: `src/litintel/methodintel/schema.py` (append after existing router models, do not modify them)

- [ ] **Step 1: Append the new models to schema.py**

At the end of `src/litintel/methodintel/schema.py`, append:

```python
from datetime import date as _date


class SourceRefKind(str, Enum):
    """Where an EvidenceClaim's source lives."""

    PMID = "pmid"
    DOI = "doi"
    URL = "url"
    DOCS_URL = "docs_url"
    GITHUB_URL = "github_url"
    PERSONAL_OBS = "personal_obs"


class SourceRef(BaseModel):
    """Typed pointer to the evidence supporting a single claim."""

    kind: SourceRefKind
    value: str
    note: Optional[str] = None


class EvidenceClaim(BaseModel):
    """One supported assertion. source_ref is required by design.

    The whole point of this model is to make 'no claim without a source'
    a schema-level invariant, not a string convention.
    """

    statement: str
    source_ref: SourceRef
    verified: Optional[bool] = None


class LifecycleStatus(str, Enum):
    """v1 lifecycle taxonomy. Expanded to 6 tiers in Phase 4.5."""

    CURRENT = "current"
    UNDER_REVIEW = "under_review"
    LEGACY = "legacy"


class MethodOption(BaseModel):
    """One candidate inside a decision dossier.

    Algorithm vs implementation are kept separate fields because the same
    algorithm (e.g. Leiden) is exposed by multiple implementations
    (ArchR, Seurat, Scanpy, SnapATAC2) with materially different
    pipeline-fit consequences.
    """

    name: str
    algorithm: str
    implementation: str
    version: Optional[str] = None
    lifecycle_status: LifecycleStatus = LifecycleStatus.CURRENT
    last_reviewed: Optional[_date] = None
    successor_methods: List[str] = Field(default_factory=list)
    benchmark_evidence: List[EvidenceClaim] = Field(default_factory=list)
    notes: Optional[str] = None


class TradeoffDimension(BaseModel):
    """One axis in the trade-off matrix, with per-option values."""

    name: str
    description: str
    per_option: Dict[str, str] = Field(default_factory=dict)


class ValidationExperiment(BaseModel):
    """The concrete experiment that would resolve the decision."""

    summary: str
    success_criterion: str
    estimated_effort: Optional[str] = None


class MethodGraphEdge(BaseModel):
    """One edge in the v1 JSON-only method graph.

    The graph is stored as JSON for v1; this model exists so the graph is
    queryable before a visual view is added.
    """

    src: str
    dst: str
    edge_type: str
    evidence_ref: Optional[SourceRef] = None

    ALLOWED_EDGE_TYPES = frozenset({
        "competes_with",
        "replaces_or_modernizes",
        "implements",
        "requires",
        "feeds_into",
        "validated_by",
        "contradicted_by",
        "deprecated_by",
        "sensitive_to",
    })

    def model_post_init(self, __context) -> None:
        if self.edge_type not in self.ALLOWED_EDGE_TYPES:
            raise ValueError(
                f"edge_type {self.edge_type!r} not in allowed set "
                f"{sorted(self.ALLOWED_EDGE_TYPES)}"
            )


class MethodDecisionDossier(BaseModel):
    """Top-level container for one routed decision question."""

    decision_question: str
    stage: str
    options: List[MethodOption]
    tradeoffs: List[TradeoffDimension] = Field(default_factory=list)
    validation_experiment: Optional[ValidationExperiment] = None
    recommendation: Optional[str] = None
    open_questions: List[str] = Field(default_factory=list)
    graph_edges: List[MethodGraphEdge] = Field(default_factory=list)
```

- [ ] **Step 2: Run the tests and confirm they pass**

Run:

```bash
cd /Volumes/Research/GitHub/Litintel && python -m pytest tests/test_methodintel_dossier_schema.py -v
```

Expected: all six tests pass.

- [ ] **Step 3: Confirm the existing router tests still pass**

Run:

```bash
cd /Volumes/Research/GitHub/Litintel && python -m pytest tests/test_methodintel_router.py -v
```

Expected: all six router tests still pass (no regression -- the existing router models in `schema.py` are untouched).

- [ ] **Step 4: Commit**

```bash
git add src/litintel/methodintel/schema.py tests/test_methodintel_dossier_schema.py
git commit -m "feat(methodintel): add thin v1 dossier schema with structural evidence grounding"
```

### Task 11: Write a failing test for the evidence-claim verifier

**Files:**
- Create: `tests/test_methodintel_verify.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_methodintel_verify.py`:

```python
import os
import sys
from unittest.mock import patch

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from litintel.methodintel.schema import EvidenceClaim, SourceRef, SourceRefKind
from litintel.methodintel.verify import verify_evidence_claims


_FAKE_PUBMED_XML = """
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation>
      <PMID Version="1">31178118</PMID>
    </MedlineCitation>
  </PubmedArticle>
</PubmedArticleSet>
""".strip()


def test_pmid_claim_marked_verified_when_pubmed_returns_pmid():
    claim = EvidenceClaim(
        statement="Leiden guarantees well-connected communities.",
        source_ref=SourceRef(kind=SourceRefKind.PMID, value="31178118"),
    )

    with patch(
        "litintel.methodintel.verify.fetch_details",
        return_value=_FAKE_PUBMED_XML,
    ) as mock_fetch:
        verified = verify_evidence_claims([claim])

    assert verified[0].verified is True
    mock_fetch.assert_called_once_with(["31178118"])


def test_pmid_claim_marked_unverified_when_pubmed_omits_pmid():
    claim = EvidenceClaim(
        statement="Unsupported claim.",
        source_ref=SourceRef(kind=SourceRefKind.PMID, value="99999999"),
    )

    with patch(
        "litintel.methodintel.verify.fetch_details",
        return_value="<PubmedArticleSet></PubmedArticleSet>",
    ):
        verified = verify_evidence_claims([claim])

    assert verified[0].verified is False


def test_non_pmid_claim_left_unverified():
    claim = EvidenceClaim(
        statement="Personal observation from spatial ATAC pilot.",
        source_ref=SourceRef(kind=SourceRefKind.PERSONAL_OBS, value="2026-04 Apollo pilot"),
    )

    with patch("litintel.methodintel.verify.fetch_details") as mock_fetch:
        verified = verify_evidence_claims([claim])

    assert verified[0].verified is None
    mock_fetch.assert_not_called()
```

- [ ] **Step 2: Run the failing test**

Run:

```bash
cd /Volumes/Research/GitHub/Litintel && python -m pytest tests/test_methodintel_verify.py -v
```

Expected: tests fail with `ModuleNotFoundError: No module named 'litintel.methodintel.verify'`.

### Task 12: Implement the evidence-claim verifier

**Files:**
- Create: `src/litintel/methodintel/verify.py`

- [ ] **Step 1: Implement verify.py**

Create `src/litintel/methodintel/verify.py`:

```python
"""Evidence-claim verification for MethodIntel dossiers.

Resolves PMID `source_ref` values against the existing PubMed client and
sets the `verified` flag on each `EvidenceClaim`. Non-PMID source kinds
are left with `verified=None` -- their verification is out of scope for
this module.

The point of this verifier is structural: claims without a resolvable
source MUST be visible in the final dossier so a human reviewer can act
on them. Hallucinated benchmark numbers are the failure mode this
module exists to prevent.
"""

from __future__ import annotations

import re
from typing import Iterable, List

from litintel.methodintel.schema import EvidenceClaim, SourceRefKind
from litintel.pubmed.client import fetch_details


_PMID_TAG = re.compile(r"<PMID[^>]*>(\d+)</PMID>")


def verify_evidence_claims(claims: Iterable[EvidenceClaim]) -> List[EvidenceClaim]:
    """Return a list of EvidenceClaim copies with `verified` populated.

    PMID claims are batched into a single `fetch_details` call and each
    PMID is checked against the returned XML body. Non-PMID claims are
    not verified here and retain `verified=None`.
    """
    claims_list = list(claims)
    pmid_indexes = [
        idx for idx, claim in enumerate(claims_list)
        if claim.source_ref.kind == SourceRefKind.PMID
    ]

    if not pmid_indexes:
        return [claim.model_copy() for claim in claims_list]

    pmids = [claims_list[idx].source_ref.value for idx in pmid_indexes]
    xml_body = fetch_details(pmids)
    returned = set(_PMID_TAG.findall(xml_body or ""))

    out: List[EvidenceClaim] = []
    for idx, claim in enumerate(claims_list):
        if claim.source_ref.kind == SourceRefKind.PMID:
            out.append(claim.model_copy(update={
                "verified": claim.source_ref.value in returned,
            }))
        else:
            out.append(claim.model_copy())
    return out
```

- [ ] **Step 2: Run the tests and confirm they pass**

Run:

```bash
cd /Volumes/Research/GitHub/Litintel && python -m pytest tests/test_methodintel_verify.py -v
```

Expected: all three tests pass.

- [ ] **Step 3: Run the full methodintel test suite for regression**

Run:

```bash
cd /Volumes/Research/GitHub/Litintel && python -m pytest tests/test_methodintel_router.py tests/test_methodintel_dossier_schema.py tests/test_methodintel_verify.py -v
```

Expected: 6 router tests + 6 dossier schema tests + 3 verifier tests = 15 passing.

- [ ] **Step 4: Commit**

```bash
git add src/litintel/methodintel/verify.py tests/test_methodintel_verify.py
git commit -m "feat(methodintel): add PMID evidence verifier using existing PubMed client"
```

### Task 13: End-of-plan verification

**Files:**
- None (verification only)

- [ ] **Step 1: Confirm all 15 tests pass together**

Run:

```bash
cd /Volumes/Research/GitHub/Litintel && python -m pytest tests/ -v
```

Expected: at minimum the 15 methodintel tests pass. Pre-existing tests outside methodintel should also remain green (no files outside the methodintel paths were touched).

- [ ] **Step 2: Confirm doc-revision coverage**

Manually skim the three revised docs and confirm:

- `methodintel_plan.md` has a `## Vocabulary` section, a 5-mode `## Entry Modes` table, a shrunken `## Core Objects` block, a Phase 0 marked resolved, a sketched Stage 5 YAML, a v1 lifecycle enum, a retrieval-then-synthesize Phase 3, and a `## Cost and Cache Budget` section.
- `methodintel_artifacts.md` has a cross-reference to plan.md vocabulary and a `**Last revised:**` stamp.
- `methodintel_router_todo.md` has Phase A boxes checked, a typed `verify_items` example, a new Phase A.1 follow-up subsection, and a `**Last revised:**` stamp.

- [ ] **Step 3: Confirm git log shape**

Run:

```bash
git log --oneline -n 12
```

Expected: 12 distinct commits (8 doc commits + 4 code/test commits), each scoped to a single concern, in the order plan tasks were executed.

---

## Self-review (already applied)

- **Spec coverage:** Each of the 11 fixes from the review (C1-C4 + N1-N6 + nits) maps to a task: C1 -> Task 5, C2 -> Task 4, C3 -> Tasks 5, 10, 11, 12, C4 -> Task 1, N1 -> Task 6, N2 -> Task 2, N3 -> Task 7, N4 -> Task 10, N5 -> Task 7, N6 -> Task 7, nits -> Task 8. Vocabulary promotion (review nit) -> Task 3.
- **Placeholder scan:** No `TBD` / `TODO` left in plan steps. The single `TBD` inside the Stage 5 YAML sketch (`cells_per_sample_estimate: TBD`) is intentional content of the config example, not a plan placeholder.
- **Type consistency:** `MethodOption` uses `algorithm` / `implementation` / `version` consistently across plan.md doc text (Task 5) and the implementation code (Task 10). `EvidenceClaim.source_ref` is required in both the doc (Task 5) and the test/code (Tasks 9 and 10). `LifecycleStatus` enum values (`current`, `under_review`, `legacy`) match between plan.md doc text (Task 7), test (Task 9), and code (Task 10). `MethodGraphEdge` fields `{src, dst, edge_type, evidence_ref}` match across plan.md (Task 5), test (Task 9), and code (Task 10).

---

## Execution

After saving this plan, choose execution mode:

1. **Subagent-Driven** (recommended) -- fresh subagent per task, review between tasks.
2. **Inline Execution** -- execute tasks in this session using executing-plans, batch with checkpoints.
