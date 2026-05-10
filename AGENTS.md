# Kun-Lin's Agent Configuration v7
# Goal-first, outcome-driven; Bioinformatics Architect / Methodology Lead
# HJF/CPDR | NIH Biowulf + GCP

## 0. Operating Goal For This Repo

LitIntel is a literature intelligence system, not just a paper summarizer.

The agent's job is to maintain a decision-ready literature memory for prostate
cancer, lineage plasticity, spatial omics, and related computational methods.
The output should help Kun-Lin decide:

- which papers are worth reading closely;
- which findings affect biological interpretation;
- which methods or datasets are reusable;
- which papers should change analysis plans, manuscript framing, or Notion
  tracking.

For LitIntel runs, "done" does not mean "the model produced text." Done means
the configured durable outputs are updated, especially Notion when enabled.

## 1. Definition Of Success: LitIntel

A LitIntel task is successful only when the requested literature workflow leaves
behind a reviewable artifact in the expected destination.

When Notion is enabled, success means:

- one Notion entry exists for every included paper;
- each entry has enough structured content to support later triage without
  rereading the whole paper;
- excluded or low-relevance papers have an explicit reason when the workflow
  tracks exclusions;
- ambiguous or high-impact papers are flagged for Kun-Lin review;
- the final response reports what changed in the literature memory, not just
  what the model thought.

Required Notion content for included lineage-plasticity papers:

- citation identifiers: title, PMID and/or DOI, journal, publication date when
  available;
- one-sentence verdict or role of the paper;
- relevance score with a short rationale;
- why Kun-Lin might care;
- study summary covering aim, cohort/system, and main result;
- key biological findings, prioritizing transition evidence and mechanism;
- methods and data types;
- plasticity themes and cell identity signatures when available;
- caveats: weak evidence, review-only status, bulk-only inference,
  unvalidated trajectory, missing perturbation, or unclear cohort relevance;
- next action when obvious: read closely, cite, dataset reuse, methods follow-up,
  ignore, or human review.

If the pipeline cannot update Notion because credentials, database IDs, schema,
or network access are missing, fail loud and report the blocker. Do not treat a
local summary as equivalent to a completed LitIntel run.

## 2. Highest-Priority Axioms

1. Match compute to workload. Pipelines, heavy processing, and multi-sample jobs
   default to GCP/Latch or Biowulf/SLURM when available. Lightweight analysis,
   visualization, and exploratory code default to local. When ambiguous, state
   the assumption and proceed.
2. Never invent functions. Unsure APIs get `# VERIFY`.
3. Never change behavior silently. Flag every behavioral change and distinguish
   it from style or documentation changes.
4. Correctness first. Never optimize or refactor unverified code.
5. Commit before agentic refactors. Remind Kun-Lin to commit and wait for
   confirmation before broad refactors.

## 3. Projects

Kun-Lin is a Bioinformatics Ph.D. and Bioinformatics Research Associate II
working toward a Bioinformatics Architect / Methodology Lead bar. Review both
scientific validity and engineering quality.

When reviewing code or analysis choices, push on:

- biological and statistical correctness: test choice, interpretation,
  biological plausibility, and hidden assumptions;
- engineering quality: structure, interfaces, readability, reproducibility,
  deliverability, and maintainability for a future collaborator.

Project defaults:

- Apollo: spatial ATAC/scRNA/scATAC/multiome. GCP/Latch primary; Biowulf
  pending. Differential motif analysis uses ArchR + chromVAR.
- LitIntel: literature triage using Gemini/OpenAI, Notion, Drive, and CSV.
  Currently local; GCP migration planned.

## 4. LitIntel Operating Rules

Prefer outcome-driven execution over rigid procedural narration.

For literature triage:

- optimize for decision-ready structured memory, not long prose;
- separate paper claims from agent interpretation;
- do not invent findings, cohorts, assays, accessions, or conclusions;
- preserve uncertainty explicitly;
- score based on evidence quality, not keyword density;
- distinguish original research, review, method paper, atlas, and commentary;
- prioritize lineage plasticity evidence involving transition, mechanism, and
  validation.

For lineage plasticity specifically, high-value evidence includes:

- demonstrated phenotype or lineage transition;
- neuroendocrine differentiation, AR-low or AR-indifferent states, EMT/MET,
  basal-luminal switching, histologic transformation, therapy-induced state
  change, or lineage infidelity;
- molecular mechanism: transcription factor, chromatin state, signaling pathway,
  enhancer rewiring, epigenetic reprogramming;
- validation: perturbation, lineage tracing, organoid/in vivo model, temporal
  sampling, or orthogonal multi-modal support;
- single-cell, spatial, chromatin, or multiome evidence that clarifies state
  transitions rather than only annotating static clusters.

Tier-4 or high-priority calls require concrete evidence. If transition,
mechanism, or validation is missing, say what is missing.

## 5. Defaults

Assume these unless explicitly overridden.

| Domain | Default | Avoid |
|---|---|---|
| Compute, pipelines | GCP / Latch | local execution for pipeline work |
| Compute, lightweight | local | cloud/SLURM for a single plot |
| HPC fallback | Biowulf + SLURM when available | assuming Biowulf is primary |
| Container | Docker build -> Apptainer run, per-process | monolithic containers |
| R environment | renv | ad hoc package state |
| Python environment | mamba | plain conda when solver speed matters |
| Interactive analysis | scripts | notebooks for pipeline modules |
| R wrangling | data.table | dplyr for new code unless already established |
| Omics workflow | Nextflow DSL2 | Prefect for omics compute |
| API automation | Prefect | Nextflow for API orchestration |
| scATAC | ArchR, SnapATAC2 | Signac unless requested |
| scRNA | Seurat v5 | unversioned assumptions |
| Batch correction | Harmony | hidden batch handling |
| Differential accessibility | ArchR Wilcoxon/binomial, edgeR pseudo-bulk | DESeq2 |
| Audience | one collaborator inheriting the code | "me only" shortcuts |
| Lifecycle | reproducible research code | SaaS patterns, throwaway scripts |

Pinned versions:

- R: 4.4.1, Bioconductor 3.19
- Python: 3.12
- R plotting: ggplot2, ComplexHeatmap

## 6. Code Style

All code and comments must be ASCII only. Use no emoji, Unicode arrows, Unicode
dashes, or decorative bullets.

General:

- fail loud with named errors;
- write one function for one job;
- prefer descriptive names over clever one-liners;
- use explicit input paths and output directories;
- no implicit current working directory assumptions in pipeline code;
- no hard-coded secrets or credentials;
- log timestamps, input counts, output counts, and skipped records.

R:

- put `library()` calls at the top of scripts only;
- use `<-`, not `=`, for assignment;
- always use braces;
- use one statement per line;
- name parameters explicitly for calls with 3 or more arguments;
- use `set.seed(42)` for stochastic steps;
- pipeline code should use explicit `tryCatch()` handlers;
- batch scripts should use
  `options(error=function(){traceback(2);quit(status=1)})`.

Python:

- use type hints on all function signatures;
- use Google-style docstrings for public functions;
- use `pathlib.Path` rather than raw path strings;
- use `logging`, not `print()`, for pipeline code;
- never use bare `except` or `except: pass`.

Shell and SLURM:

- start shell scripts with `#!/usr/bin/env bash`;
- use `set -eo pipefail` and an ERR trap;
- quote variables;
- for SLURM include `--job-name`, `--output`, `--error`, `--time`, `--mem`,
  and `--cpus-per-task`;
- never write to `$HOME` on Biowulf; use `$TMPDIR` and stage out explicitly.

## 7. ArchR Reference Rule

Before writing ArchR code, read the local ArchR reference:

1. Start with `~/.claude/skills/bioinfo-code/references/ArchR/INDEX.md`.
2. Read the relevant topic file.
3. If a function or parameter is not found, mark it with `# VERIFY`.

ArchR-specific guardrails:

- ArchR mutates projects: use `proj <- addX(ArchRProj = proj, ...)`;
- Arrow files are on disk, not purely in memory;
- capture `saveArchRProject(load=TRUE)` return values;
- chromVAR needs `addBgdPeaks()` before deviations;
- `filterDoublets()` uses `filterRatio`;
- motif deviations use `z` and `deviations`;
- spatial ATAC requires coordinate-space verification;
- no `reticulate` in pipelines unless explicitly requested.

## 8. Cloud And Workflow Rules

GCP / Latch:

- use explicit `gs://` URIs for pipeline I/O;
- stage in, compute, and stage out;
- credentials must come from environment variables or secret injection;
- use per-task Docker images pinned by `image:tag@sha256`;
- declare CPU and memory for each task;
- use platform-defined scratch paths, not assumed `$TMPDIR`;
- cache deterministic expensive steps when supported.

Nextflow DSL2:

- process per file;
- use `tuple val(meta), path(reads)` style channels;
- use explicit `publishDir`;
- keep params in schema or defaults block;
- configure resources via `withName:`;
- run with `-with-report -with-trace`.

Snakemake:

- non-trivial rules must include `input`, `output`, `log`, and `benchmark`;
- use consistent `{sample}` wildcards.

## 9. Module Definition Of Done

Any code, script, or module is complete only when:

- no hallucinated APIs are present, or unknowns are tagged `# VERIFY`;
- failure modes are loud;
- assumptions are stated explicitly;
- stochastic behavior is seeded;
- paths are explicit;
- provenance is captured where appropriate;
- reruns do not duplicate or corrupt outputs;
- scope is limited to the requested change;
- logs and output locations are documented;
- resource requirements are stated when relevant.

Every pipeline module should include:

- header: module name, purpose, input, output, dependencies, provenance, date;
- footer: QC checkpoint, expected values, edge cases;
- architect notes: modularity, reproducibility, scale, portability, limitations.

## 10. Skills

Prefer installed skills over ad hoc workflows:

- `bioinfo-code`: write, refactor, or review bioinformatics code;
- `bioinfo-doc`: document existing bioinformatics code;
- `bioinfo-analysis-plan`: convert biological questions into analysis plans;
- `bioinfo-plan-review`: critique drafted analysis plans;
- `debug`: reproduce, isolate, diagnose, and fix errors;
- `architecture`: evaluate project-level framework or infrastructure choices;
- `paper-biology-v2`: evaluate biological relevance of papers;
- `paper-methods-v2`: evaluate computational methods papers;
- `reflect`: summarize outcomes, decisions, TODOs, and Notion-ready logs.

Do not re-describe skill internals here. Read the skill file directly when a
skill applies.

## 11. Final Response Expectations

For LitIntel runs, final responses should be short and operational:

- state how many papers were added, updated, skipped, or flagged;
- state which durable outputs were updated: Notion, Drive, CSV, RAG corpus;
- list high-impact interpretation changes;
- list human-review items;
- report blockers clearly if Notion or another configured output was not
  updated.

Do not present a task as complete when the durable output was not written.
