# MethodIntel Plan

**Status:** Draft  
**Date:** 2026-05-11  
**Context:** Build a method-decision assistant inside the LitIntel repo without mixing it into the existing paper-triage pipelines.

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

## Purpose

MethodIntel is a decision-support layer for single-cell and spatial omics methods. It should help answer questions like:

- Which method should I use for this analysis stage?
- What assumptions and failure modes matter?
- What evidence supports each option?
- What validation experiment would resolve the decision?

LitIntel is paper-centered. MethodIntel is decision-centered.

```text
LitIntel:
paper -> score -> summary -> methods extraction -> Notion/Drive

MethodIntel:
stage/question -> candidate methods -> evidence claims -> tradeoff matrix -> recommendation
```

## Boundary

MethodIntel should live in this repo first because LitIntel already has useful infrastructure:

- AI client and prompt handling
- PubMed/PMC retrieval
- structured Pydantic schemas
- Notion, Drive, and RAG storage paths
- config-driven CLI patterns
- existing methods-discovery Tier 2 pipeline

However, MethodIntel should be a separate subsystem, not a new Tier 1 or Tier 2 mode.

Proposed layout:

```text
src/litintel/methodintel/
  __init__.py
  schema.py
  prompts.py
  build_dossier.py
  notion_export.py

configs/methodintel_stage5_clustering.yaml
output/methodintel/
```

## MVP Use Case

Start with the existing Notion decision:

**Stage 5 - Clustering:** Leiden vs Louvain vs SnapATAC2 transplant.

Primary question:

> Should the Apollo spatial ATAC pipeline keep ArchR Louvain, switch to Leiden inside ArchR, transplant SnapATAC2 labels/embedding into ArchR, or migrate fully to SnapATAC2?

The MVP should reproduce the useful structure already present in Notion, but make it config-driven and reproducible.

## Core Objects

Initial schema candidates:

- `MethodDecisionDossier`
- `StageNode`
- `MethodNode`
- `ImplementationNode`
- `EvidenceNode`
- `MethodOption`
- `EvidenceClaim`
- `DecisionHeuristic`
- `TradeoffDimension`
- `FailureMode`
- `ImplementationPath`
- `ValidationExperiment`

The schema should prevent generic summarization. Every dossier should force a concrete recommendation, evidence grade, and validation path.

## Decision Heuristics

MethodIntel should capture reusable method-choice heuristics, but treat them as evidence-graded claims rather than permanent rules.

Examples:

- ArchR vs SnapATAC2: one tool may be more sensitive for broad cell typing, while another may better preserve sparse overlap structure or scale better. The dossier should state the biological regime where that claim applies, the trade-off, and the evidence level.
- limma vs DESeq2 vs edgeR: method choice depends on sample size, replicate structure, count depth, dispersion modeling, and whether the analysis is bulk, pseudo-bulk, or cell-level. Sensitivity claims should be tied to a specific design, not generalized globally.
- Wilcoxon vs pseudo-bulk: Wilcoxon can be useful for cluster marker discovery, but replicated condition testing should usually move toward pseudo-bulk models.

Each heuristic should include:

- the condition where it applies
- the expected advantage
- the trade-off or failure mode
- the evidence source
- whether it is a default, a warning, or a hypothesis to validate

This is the practical value of MethodIntel: not just "what does the method do?", but "when does this method become the better choice, and what do I pay for that choice?"

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

## Method Graph

Methods are interrelated, so MethodIntel should eventually expose a graph view, not only isolated pages.

Useful node types:

- `StageNode`: pipeline stage, such as clustering or differential accessibility
- `MethodNode`: method or algorithm, such as Louvain, Leiden, edgeR, or DESeq2
- `ImplementationNode`: package/function, such as ArchR `addClusters()` or Seurat `FindClusters()`
- `EvidenceNode`: benchmark paper, original paper, documentation, GitHub issue, or personal observation
- `DecisionDossier`: context-specific comparison, such as ArchR Leiden vs SnapATAC2 transplant
- `HeuristicNode`: reusable trade-off claim, such as "pseudo-bulk is preferred for replicated condition testing"

Useful edge types:

- `competes_with`
- `replaces_or_modernizes`
- `implements`
- `requires`
- `feeds_into`
- `validated_by`
- `contradicted_by`
- `deprecated_by`
- `sensitive_to`

Example:

```text
Stage: Clustering
  -> Method: Louvain
  -> Method: Leiden
  -> Method: SLM

Method: Leiden
  -> implements: Seurat FindClusters algorithm=4
  -> implements: scanpy.tl.leiden
  -> competes_with: Louvain
  -> validated_by: Traag et al. 2019

Decision: ArchR vs SnapATAC2 transplant
  -> compares: ArchR Louvain, ArchR Leiden, SnapATAC2 Leiden
  -> sensitive_to: embedding/reference-frame consistency
```

In this graph, ArchR and SnapATAC2 are implementation nodes, not method nodes. A decision can still compare "ArchR Louvain" with "SnapATAC2 Leiden", but that comparison should be represented as method plus implementation, not as a flat list of methods.

For v1, the graph can be stored as structured JSON/YAML plus Markdown links. A visual plot can come later after the schema stabilizes.

## Method Lifecycle and Staleness

MethodIntel should track whether a method is current, legacy, replaced, or context-specific. This matters because methods can stay familiar long after the field moves on.

Example motivation:

- Cufflinks may be remembered as a standard RNA-seq tool from an earlier training period, but current practice may favor other quantification and differential-expression workflows depending on the question. MethodIntel should make that shift visible instead of assuming the user's training-era default is still current.

Each `MethodNode` should eventually include:

- `lifecycle_status`: emerging, current_default, established_alternative, legacy, deprecated, context_specific
- `last_reviewed`
- `replacement_or_successor_methods`
- `current_common_use`
- `historical_common_use`
- `staleness_signals`
- `still_valid_when`

Possible staleness signals:

- newer benchmark papers no longer include the method
- package repository is archived or minimally maintained
- documentation recommends another method
- recent workflows use a successor method
- GitHub issues show unresolved compatibility problems
- method is still valid for a narrow legacy or reproducibility context

Design rule:

> MethodIntel should not only ask "what does this method do?" It should also ask "is this still a reasonable default today, and if not, when is it still acceptable?"

## Expected Outputs

For each decision dossier, produce:

- executive summary
- decision context
- option tree
- trade-off matrix
- per-option deep dive
- common misuses
- evidence table
- implementation notes
- pragmatic notes
- validation experiment
- recommendation
- open questions

Local outputs first:

```text
output/methodintel/stage5_clustering.json
output/methodintel/stage5_clustering.md
```

Notion export comes after local output is useful.

## Phased Action Items

### Phase 0 - Design Contract

- [x] Keep this plan as the working contract.
- [x] Confirm MethodIntel stays inside the LitIntel repo for v1.
- [x] Confirm Stage 5 clustering is the first MVP.
- [x] Notion direction for v1: **manual-input only**. The user pastes or
      provides a Markdown export of the existing Notion Stage 5 page as
      the dossier's source-of-context. Automatic Notion fetch is deferred
      to Phase 5; the Notion client in this repo stays write-only until
      then.

### Phase 1 - Schema Draft

- [ ] Add `src/litintel/methodintel/schema.py`.
- [ ] Define Pydantic models for the core objects.
- [ ] Include `DecisionHeuristic` for reusable but evidence-graded method-choice rules.
- [ ] Include graph-oriented nodes for stages, methods, implementations, and evidence.
- [ ] Include lifecycle/staleness fields for each method.
- [ ] Add unit tests for required fields and JSON serialization.
- [ ] Keep schema small enough to revise after one dossier.

### Phase 2 - Stage 5 Config

- [ ] Add `configs/methodintel_stage5_clustering.yaml`.
- [ ] Encode stage, decision question, current stack, modality, biological goal, options, and source hints.
- [ ] Include current assumptions: ArchR-centered pipeline, spatial ATAC, Apollo scaling from 10 to 90 samples.

### Phase 3 - Local Dossier Builder

- [ ] Add `src/litintel/methodintel/build_dossier.py`.
- [ ] Add prompt template in `src/litintel/methodintel/prompts.py`.
- [ ] Generate JSON and Markdown outputs from the config.
- [ ] Do not write to Notion yet.

### Phase 4 - Review Stage 5 Output

- [ ] Compare generated output against the current Notion Stage 5 page.
- [ ] Check whether the schema captures the most important reasoning:
  - algorithm choice vs tool choice
  - pipeline reference-frame consistency
  - downstream validation burden
  - biological goal: cell type discovery vs substate biology
  - reusable heuristics with explicit trade-offs and evidence grades
  - related methods and graph edges
  - lifecycle status: current default, legacy, deprecated, or context-specific
- [ ] Revise schema before adding another stage.

### Phase 5 - Notion Export

- [ ] Add `src/litintel/methodintel/notion_export.py`.
- [ ] Create or update a Notion page from the Markdown dossier.
- [ ] Preserve source links and last-reviewed metadata.
- [ ] Keep local JSON as the machine-readable source of truth.

### Phase 6 - Evidence Automation

- [ ] Reuse PubMed/PMC retrieval for benchmark papers.
- [ ] Reuse Tier 2 methods discovery to identify candidate method papers.
- [ ] Add evidence grading: benchmark, original paper, docs, GitHub issue, personal experience, speculative.
- [ ] Add a review cadence field so stale method claims are visible.

## First CLI Target

Target command:

```bash
litintel methodintel build configs/methodintel_stage5_clustering.yaml
```

Target behavior:

1. Load config.
2. Build a structured dossier.
3. Validate against MethodIntel schema.
4. Write JSON and Markdown outputs.
5. Log assumptions, source coverage, and unresolved `# VERIFY` items.

## Design Rules

- Do not make MethodIntel a generic chatbot.
- Do not bury decisions inside paper summaries.
- Do not treat newer tools as automatically better.
- Do not assume a familiar training-era method is still current.
- Separate algorithm choice, implementation choice, ecosystem choice, and validation burden.
- Support method-first, stage-first, and problem-first entry modes.
- Represent relationships as graph edges where possible, even if the v1 output is Markdown.
- Prefer benchmark-first evidence over broad PubMed search.
- Keep human review mandatory before writing final recommendations to Notion.
- Start narrow, validate on Stage 5, then expand.

## Expansion Candidates

After Stage 5 works, likely next dossiers:

1. Stage 4 - Batch correction / integration: Harmony vs scVI vs fastMNN vs Seurat CCA.
2. Stage 7 - Differential accessibility / expression: Wilcoxon vs pseudo-bulk edgeR/DESeq2.
3. Stage 6 - Cell annotation: manual markers vs SingleR/Azimuth/CellTypist/Cellcano.
4. Stage 8 - Motif / TF activity: chromVAR vs motif enrichment vs GRN tools.

## Definition of Done for v1

- [ ] Stage 5 dossier can be generated from config.
- [ ] Output includes a defensible recommendation and validation experiment.
- [ ] JSON schema is stable enough for one more stage.
- [ ] Markdown output is readable enough to paste into Notion.
- [ ] No Notion automation is added until the local artifact is useful.
