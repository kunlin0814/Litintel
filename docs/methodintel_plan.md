# MethodIntel Plan

**Status:** Draft  
**Date:** 2026-05-11  
**Context:** Build a method-decision assistant inside the LitIntel repo without mixing it into the existing paper-triage pipelines.
**Last revised:** 2026-05-11 (post-review fixes from `docs/superpowers/plans/2026-05-11-methodintel-plan-revision.md`)

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

## Decision Heuristics

MethodIntel should capture reusable method-choice heuristics, but treat them as evidence-graded claims rather than permanent rules.

Examples:

- ArchR vs SnapATAC2: one tool may be more sensitive for broad cell typing, while another may better preserve sparse overlap structure or scale better. The dossier should state the biological regime where that claim applies, the trade-off, and the evidence level.
- limma vs DESeq2 vs edgeR: choice depends on data type, replicate
  structure, and dispersion modeling. For bulk RNA-seq, `limma-voom`,
  `edgeR`, and `DESeq2` are all defensible defaults. For single-cell
  pseudo-bulk DA/DE the practical ranking is roughly
  `edgeR ~= DESeq2 > limma-voom`, because the count distribution at
  small per-group replicate counts is better captured by NB-with-shrunk-
  dispersion than by voom's mean-variance trend. Cell-level Wilcoxon is
  useful only for cluster-marker discovery, not for replicated condition
  testing.
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
