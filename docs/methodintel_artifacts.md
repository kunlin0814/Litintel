# MethodIntel Artifacts and Control Model

**Status:** Draft  
**Date:** 2026-05-11  
**Purpose:** Define how a user controls MethodIntel and what artifacts it should return.

## Core Idea

MethodIntel should behave like guided research, not like a broad search bot.

```text
User gives MethodIntel an intent.
MethodIntel decides the mode.
MethodIntel searches only the sources needed for that mode.
MethodIntel returns a structured artifact.
```

The user controls the question and context. The system controls the evidence plan. Human review happens before durable Notion output.

## Start Prompt

Possible CLI or UI entry:

```text
What are you trying to do today?

1. Learn a method
2. Compare methods
3. Choose a method for my dataset
4. Understand a pipeline stage
5. Check whether a method is outdated
```

The user can then type naturally:

```text
I keep hearing about Louvain and Leiden. I want to know which one I should use for ArchR clustering.
```

MethodIntel should classify this as:

```yaml
mode: compare_methods
stage: clustering
methods:
  - Louvain
  - Leiden
context:
  stack: ArchR
  modality: scATAC
artifact: decision_dossier
```

If key context is missing, MethodIntel should ask only high-impact follow-up questions:

```text
- Is this scRNA, scATAC, spatial ATAC, or multiome?
- Are you staying inside ArchR?
- Is the goal broad cell typing or substate/subclone biology?
```

## Entry Modes and Artifacts

### 1. Learn a Method

Example:

```text
What is Louvain clustering?
```

Artifact:

```text
Method card
```

Expected sections:

- plain-language intuition
- algorithm summary
- common bioinformatics usage
- implementation table
- strengths
- weaknesses and failure modes
- benchmark evidence
- related alternatives
- lifecycle status
- open questions

### 2. Compare Methods

Example:

```text
Louvain vs Leiden for ArchR clustering.
```

Artifact:

```text
Decision dossier
```

Expected sections:

- executive summary
- decision context
- options considered
- trade-off matrix
- per-option deep dive
- common misuses
- evidence table
- implementation notes
- validation experiment
- recommendation

### 3. Choose a Method for My Dataset

Example:

```text
I have spatial ATAC data and want to identify tumor substates. Should I use ArchR clustering or SnapATAC2?
```

Artifact:

```text
Context-specific recommendation
```

Expected sections:

- interpreted biological goal
- inferred pipeline stage
- required constraints
- recommended default
- alternatives
- risks and assumptions
- validation experiment
- `# VERIFY` items

### 4. Understand a Pipeline Stage

Example:

```text
What happens during clustering in scATAC analysis?
```

Artifact:

```text
Stage map
```

Expected sections:

- what the stage solves
- when it happens
- prerequisite stages
- downstream stages
- method families
- decision axes
- common mistakes
- links to method cards and decision dossiers

### 5. Check Whether a Method Is Outdated

Example:

```text
Is Cufflinks outdated for RNA-seq analysis?
```

Artifact:

```text
Lifecycle report
```

Expected sections:

- historical role
- current common use
- successor or replacement methods
- staleness signals
- still-valid use cases
- recommendation
- evidence table

## Source Strategy

MethodIntel should not search every source every time. It should select sources based on the mode.

Preferred source order:

```text
1. Existing MethodIntel / Notion pages
2. Benchmark papers
3. Original method papers
4. Official docs
5. GitHub repos, issues, and discussions
6. Recent review papers
7. Broad web search only as fallback
```

Broad web search is useful for discovery, but final claims should be supported by stronger sources where possible.

## Example Routed Workflows

### Louvain vs Leiden in ArchR

```text
User question
  -> compare_methods
  -> clustering
  -> Louvain, Leiden
  -> ArchR/scATAC context
  -> sources: Notion Stage 5, Leiden paper, ArchR docs/source, Seurat docs/source
  -> artifact: decision dossier
```

### Cufflinks Staleness

```text
User question
  -> staleness_check
  -> RNA-seq quantification / transcript assembly
  -> Cufflinks
  -> sources: current reviews, workflow docs, package status, historical paper
  -> artifact: lifecycle report
```

### Unknown Stage

```text
User question
  -> problem_first routing
  -> infer possible stage
  -> ask minimal clarification if needed
  -> sources: stage map plus benchmark/review papers
  -> artifact: stage map or decision dossier
```

## Output Rule

Every MethodIntel artifact should include:

- what question was answered
- what mode was selected
- what sources were used
- what claims are evidence-backed
- what claims remain `# VERIFY`
- what the user should do next

The artifact should be good enough to paste into Notion, but local Markdown/JSON should be produced first.
