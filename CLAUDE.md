# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Environment and commands

`pyproject.toml` is the **single source of dependency truth** (the old `requirements.txt` /
`requirements_litintel.txt` are gone -- they were mutually incomplete and pinned
`python-dotenv==0.21.0`, which `google-adk` rejects). Set up with:

```bash
python -m venv venv && venv/bin/pip install -e ".[dev]"
```

The editable install provides the `litintel` console script and makes `PYTHONPATH=src`
unnecessary. Note that **conda base cannot run the pipeline** -- it lacks `dotenv`,
`notion_client`, `openai`, `googleapiclient`, and `pypdf`, so `import litintel.cli` fails
there. It can still run the test suite via `PYTHONPATH=src`.

```bash
# Tests (46 pass, 3 integration skipped)
venv/bin/python -m pytest -q

# Single test file / single test
venv/bin/python -m pytest tests/test_methodintel_router.py -v
venv/bin/python -m pytest tests/test_schema_validation.py::test_ncbi_params_requires_email -v

# Integration tests hit real APIs and are skipped unless explicitly enabled (see tests/conftest.py)
venv/bin/python -m pytest -q --run-integration

# Pipeline / CLI
venv/bin/litintel tier1 --config configs/tier1_pca.yaml --limit 5
venv/bin/litintel validate configs/tier1_pca.yaml
venv/bin/litintel methodintel route "Leiden vs Louvain for spatial ATAC"
venv/bin/litintel tier-c inbox --dry-run
venv/bin/litintel tier-c pmid 12345678

# RAG query agent (separate entrypoint, needs gcloud ADC + GOOGLE_API_KEY)
venv/bin/python agent/cli.py "What spatial ATAC papers cover CTCF in prostate cancer?"
```

`pytest` config lives in `pyproject.toml` (`testpaths=["tests"]`, `norecursedirs` excludes
`legacy/`). Pre-commit runs `detect-secrets` against `.secrets.baseline`.

**Each worktree needs its own `venv/`** (it is gitignored). An editable install binds to the
source tree it was run from, so a venv built in one worktree will execute *that* worktree's
code no matter which directory you invoke it from.

## Architecture

LitIntel is a **tiered, YAML-driven literature enrichment pipeline**: PubMed discovery -> PMC
full-text -> multi-pass AI enrichment -> fan-out to Notion / Drive / CSV / Vertex RAG. The
single orchestration function is `run_tier1_pipeline()` in `src/litintel/pipeline/tier1.py`
(~440 lines); everything else is a module it calls. Read that file first to understand any
behavior change.

**Config is the contract.** `configs/*.yaml` -> `load_config_from_yaml()` -> Pydantic `AppConfig`
(`src/litintel/config.py`). The YAML is the **single source of truth for every model, thinking
level, and threshold** -- pipeline (`ai:`), figure enrichment (`tier_c:`), and the RAG corpus +
query agent (`rag_agent:`). There are deliberately **no env-var overrides**: an earlier
override block let `.env` silently win, so `tier1_pca.yaml` claimed `gemini-3.1-pro-preview`
for Pass 2 and Tier C while both actually ran on `gemini-3.6-flash`. Do not reintroduce it.
`load_config_from_yaml()` logs every resolved model on each run; that log is the authoritative
record of what executed.

**The `.env` / YAML split:** `.env` holds only credentials and resource identifiers
(`NCBI_*`, `NOTION_*`, `GOOGLE_*`, `GCP_PROJECT_ID`, `VERTEX_RAG_CORPUS_NAME`). Anything
naming a model or tuning a behavior belongs in the YAML. `agent/cli.py` and `agent/agent.py`
both read the `rag_agent` block rather than env.

The pipeline is **Gemini-only** in practice (`ai.provider: gemini`); the OpenAI key was revoked
2026-07-22. `enrich/ai_client.py` still carries an untested `AIProvider.OPENAI` branch and the
`model_default`/`model_escalate` Pydantic defaults are stale OpenAI ids -- always set both
explicitly in the YAML.

### The passes and their thresholds

| Stage | Trigger | Model role | Code |
|---|---|---|---|
| Pass 1 scoring | every record | `pass1_model_abstract` / `pass1_model_fulltext` | `enrich/ai_client.py::enrich_record` |
| Pass 2 methods | `RelevanceScore >= pass2_min_score` (88) + full-text | `pass2_model` | `enrich/ai_client.py::enrich_pass2_methods` |
| Tier C (figures) | auto: score `>= 90` + PMCID; or manual Drive inbox | `tier_c.model` (multimodal) | `tierc/engine.py` |
| Drive PDF upload | score `>= pdf_min_score` (88) | -- | `storage/drive.py` |
| RAG corpus sync | score `>= 85` (`DEFAULT_MIN_SCORE`) | -- | `storage/rag_corpus.py` |

**Processing order is load-bearing, not incidental.** Pass 1 deliberately processes
abstract-only records *first*, then full-text records grouped together, to keep the Gemini
prompt cache warm (~50% input-cost reduction). Pass 2 then runs as a parallel batch
(ThreadPoolExecutor, 3 workers). Do not reorder or interleave these without accounting for the
cost model.

**Escalation heuristics** (`enrich/escalation_heuristics.py::should_escalate`) emit signals
H1-H5 (short rationale, score-near-threshold, text/score mismatch, high-relevance/low-reuse,
direct high-score). They feed a Shadow Judge path in `ai_client.py` that is **only partially
implemented** -- treat it as scaffolding, not a working second opinion.

### Subsystems

- `pubmed/client.py` -- NCBI E-Utilities with rate limiting and retry. Search is paginated in
  batches of 200 (deep pagination up to ~1000) so already-seen PMIDs can be skipped cheaply.
- `storage/notion.py` -- `build_notion_index()` produces a `PMID -> page_id` map used as the
  **primary dedup gate before any AI spend**. All text properties are truncated to 2000 chars
  for the Notion API.
- `storage/drive.py` -- writes `papers.jsonl` plus score-bucketed Markdown for NotebookLM.
  Prefers exact file/folder IDs from `.env` over name lookup; without those IDs it will create
  duplicate folders/files.
- `tierc/` -- three-stage multimodal engine (Evidence Map -> Synthesis -> Verification), each
  stage anchored to figure IDs. Large PDFs are chunked (~25 pages). See `docs/tier_c_readme.md`.
- `methodintel/` -- deterministic (non-AI) router: question -> `RouterMode` -> `ArtifactType` +
  source plan + verify items. Alias tables in `router.py` are the extension point. Design docs
  in `docs/methodintel_plan.md`, `docs/methodintel_artifacts.md`.
- `agent/` -- separate ADK/CLI RAG agent over the Vertex RAG corpus. Not part of the pipeline.
- `utils/run_log.py` -- appends per-run audit rows to `run_history.csv`.
- `.deployment/` -- Prefect flow (`biweekly_flow.py`) wrapping the tier1 run for scheduling.

### Two independent Google credentials (recurring source of bugs)

- `GOOGLE_APPLICATION_CREDENTIALS` (service account / ADC) -> Vertex AI, Gemini-on-GCP, RAG.
- `GOOGLE_DRIVE_CLIENT_SECRET` + cached `token_drive.json` (user OAuth) -> personal Drive writes.

These are not interchangeable. A GCP service account cannot write to personal Drive even when
the folder is shared with it. Re-auth with `python scripts/auth/auth_google_drive.py`.
Details: `docs/gcp_credentials_guide.md`, `docs/google_drive_setup.md`.

## Conventions and gotchas

- **ASCII only** in code, comments, and AI prompt templates (the agent system prompts enforce
  this too). No emoji, no Unicode dashes/arrows.
- `legacy/` is the retired Prefect flat-file implementation, kept for reference only and
  excluded from pytest. Never import from it or "fix" it.
- **Tier 2 has been removed** from the pipeline (`pipeline/tier2.py` no longer exists) but
  `README.md` and the `PipelineTier` enum still mention it. Trust the CLI in `src/litintel/cli.py`
  over the README where they disagree.
- `.gitignore` swallows `*.csv`, `scripts/test_*.py`, `scripts/generate_*.py`, and `dev/*` --
  a new script matching those patterns will silently not be tracked.
- **NCBI credentials are env-only.** `pubmed/client.py::_ncbi_params()` is the single source for
  the `email` + `api_key` query params and **raises** if `NCBI_EMAIL` is unset -- never
  reintroduce a placeholder fallback, it misattributes NCBI traffic. `_rate_delay()` returns
  0.11s when `NCBI_API_KEY` is present (10 req/s) and 0.34s otherwise (3 req/s), and
  `_request_with_retry()` backs off on 429. Any new E-utilities call must go through these,
  not raw `requests.get`.
- Prompt behavior lives in `enrich/prompt_templates.py` (scoring + methods instructions,
  controlled `DataTypes` vocab, GEO/SRA "only if from THIS study" rule). Changing scoring
  behavior almost always means editing a prompt string, not Python logic.
- Schema changes ripple: `enrich/schema.py` (Pydantic) -> Gemini structured-output schema ->
  Notion property mapping in `storage/notion.py` -> CSV columns. Update all four.
