# MethodIntel Router TODO

**Status:** Draft  
**Date:** 2026-05-11  
**Purpose:** Track decisions and implementation tasks for the MethodIntel router and source planner.
**Last revised:** 2026-05-11 (post-review fixes from `docs/superpowers/plans/2026-05-11-methodintel-plan-revision.md`)

## Router Goal

The router converts a natural-language question into a controlled research plan.

```text
question
  -> mode
  -> stage/method/context extraction
  -> source plan
  -> artifact type
```

It should prevent MethodIntel from becoming "search everything and summarize." The router decides what evidence is needed before retrieval begins.

## MVP Router Modes

- [ ] `learn_method`
- [ ] `compare_methods`
- [ ] `choose_for_dataset`
- [ ] `stage_overview`
- [ ] `staleness_check`

## Router Output Schema

Draft fields:

```yaml
mode: compare_methods
artifact: decision_dossier
stage: clustering
methods:
  - Louvain
  - Leiden
implementations:
  - ArchR
context:
  modality: scATAC
  platform: spatial ATAC
  stack: ArchR
  biological_goal: cell typing
  compute_context: local
missing_constraints:
  - dataset scale
source_plan:
  - existing_methodintel
  - benchmark_papers
  - original_papers
  - official_docs
verify_items:
  - claim: ArchR/Seurat parameter support for current installed versions.
    why_uncertain: API drift between major releases.
    resolution_method: Pin versions and re-run the dossier with version-stamped sources.
```

> The router currently emits `verify_items` as a list of strings. Promoting
> the field to a `list[VerifyItem]` Pydantic model with `{claim, why_uncertain,
> resolution_method}` is a follow-up task tracked in Phase A.1 below.

## Source Planner

The source planner decides where to search based on mode.

### Source Types

- [ ] Existing MethodIntel JSON/Markdown
- [ ] Notion pages
- [ ] PubMed benchmark/review search
- [ ] PubMed original method paper search
- [ ] Official documentation
- [ ] GitHub repository metadata
- [ ] GitHub issues/discussions
- [ ] Broad web search fallback

### Source Rules

- [ ] Search existing MethodIntel/Notion first to avoid rediscovering known decisions.
- [ ] Prefer benchmark papers for stage-level comparisons.
- [ ] Prefer original papers for algorithm intuition.
- [ ] Prefer official docs/source for implementation claims.
- [ ] Use GitHub issues for practical failure modes, not primary scientific claims.
- [ ] Use broad web search only to find better sources or detect staleness signals.
- [ ] Mark unsupported or unstable claims as `# VERIFY`.

## Mode-Specific Source Plans

### `learn_method`

- [ ] Existing method card
- [ ] Original method paper
- [ ] Benchmark/review paper mentioning the method
- [ ] Official docs for common implementations
- [ ] Related alternatives from graph edges

### `compare_methods`

- [ ] Existing decision dossier
- [ ] Benchmark papers comparing the options
- [ ] Original papers for each method
- [ ] Official docs/source for implementation differences
- [ ] GitHub issues only for practical or installation risks

### `choose_for_dataset`

- [ ] Existing decision dossier
- [ ] Stage map
- [ ] Benchmark evidence
- [ ] Context constraints: modality, scale, stack, biological goal, compute
- [ ] Validation experiment template

### `stage_overview`

- [ ] Benchmark/review papers first
- [ ] Stage map
- [ ] Method families
- [ ] Common decision axes
- [ ] Links to method cards

### `staleness_check`

- [ ] Current reviews or best-practice papers
- [ ] Current official workflow docs
- [ ] Package/repository maintenance status
- [ ] Recent benchmark inclusion/exclusion
- [ ] Historical original paper
- [ ] Successor or replacement methods

## Questions the Router May Ask

Ask only when the answer changes the source plan or recommendation.

- [ ] What modality is this? scRNA, scATAC, spatial ATAC, multiome, bulk RNA-seq?
- [ ] What is the biological goal? cell typing, substate discovery, condition testing, trajectory, annotation?
- [ ] What stack must this stay in? ArchR, Seurat, Scanpy, SnapATAC2, Nextflow, other?
- [ ] What is the scale? samples, cells/tixels, features, expected runtime?
- [ ] Is this for learning, a live project decision, or publication-grade documentation?
- [ ] Is the goal to check current default status or understand historical usage?

## Implementation TODO

### Phase A - Static Router (implemented 2026-05-11)

- [x] Create `src/litintel/methodintel/router.py`.
- [x] Implement rule-based routing for the five MVP modes.
- [x] Add `RouterDecision` Pydantic model (`src/litintel/methodintel/schema.py`).
- [x] Add tests with example user questions (`tests/test_methodintel_router.py`,
      6 cases covering all five modes plus implementation-only routing).
- [x] Return `missing_constraints` instead of asking interactively at first.

### Phase A.1 - VerifyItem typing follow-up

- [ ] Add `VerifyItem` Pydantic model to `src/litintel/methodintel/schema.py`.
- [ ] Change `RouterDecision.verify_items` from `list[str]` to `list[VerifyItem]`.
- [ ] Update `tests/test_methodintel_router.py` to assert the structured shape.
- [ ] Keep a backward-compat helper that accepts plain strings during transition.

### Phase B - Config Integration

- [ ] Allow router output to seed a MethodIntel config.
- [ ] Save routed configs under `output/methodintel/routed_configs/`.
- [ ] Add a dry-run command that prints the source plan without searching.

Target command:

```bash
litintel methodintel route "Louvain vs Leiden for ArchR clustering"
```

Expected output:

```text
mode: compare_methods
artifact: decision_dossier
source_plan: existing_methodintel, benchmark_papers, original_papers, official_docs
missing_constraints: modality, biological_goal
```

### Phase C - Source Planner

- [ ] Add `src/litintel/methodintel/source_plan.py`.
- [ ] Convert router decisions into source tasks.
- [ ] Keep source tasks explicit and auditable.
- [ ] Support manual source URLs before automatic web/GitHub/PubMed search.

### Phase D - Interactive Ask

- [ ] Add `litintel methodintel ask`.
- [ ] Present the five entry modes when routing confidence is low.
- [ ] Ask minimal clarification questions.
- [ ] Produce local Markdown/JSON first.

## Router Design Rules

- Do not search before mode classification.
- Do not search all sources by default.
- Do not treat broad web search as evidence.
- Do not hide missing context.
- Do not write to Notion automatically.
- Always expose the selected mode, artifact, source plan, and `# VERIFY` gaps.

## First Test Cases

- [ ] "What is Louvain clustering?"
- [ ] "Louvain vs Leiden for ArchR clustering."
- [ ] "I have spatial ATAC and want to find tumor substates."
- [ ] "What clustering methods exist for scATAC?"
- [ ] "Is Cufflinks outdated?"
- [ ] "limma vs DESeq2 for pseudo-bulk with small sample size."
