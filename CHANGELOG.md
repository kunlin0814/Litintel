# Changelog

All notable changes to LitIntel are documented here.
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - 2026-04-25

### Added
- **GCP credentials guide** (`docs/gcp_credentials_guide.md`) -- comprehensive troubleshooting reference covering credential types, multi-project CLI coexistence, OAuth consent screen issues, and company GCP migration checklist
- **Service Account isolation** -- Vertex AI now authenticates via `GOOGLE_APPLICATION_CREDENTIALS` (Service Account JSON), fully decoupled from the `gcloud` CLI project context
- **Drive OAuth refactor** -- new `GOOGLE_DRIVE_CLIENT_SECRET` env var separates Drive authentication from Vertex AI credentials; falls back to legacy `GOOGLE_CLIENT_SECRETS_PATH` for backward compatibility
- **Drive sync test script** (`scripts/test_drive_sync.py`) -- single-PMID end-to-end test for Google Drive upload

### Changed
- Vertex AI endpoint switched to `global` location for broader model availability (Gemini 3 Preview)
- `_call_gemini()` now retries without `ThinkingConfig` if the model/region rejects thinking parameters, preventing hard failures on preview models
- Updated `docs/google_drive_setup.md` to reflect OAuth Client Secret flow (replacing outdated Service Account instructions)

### Fixed
- **"Client secrets must be for a web or installed app"** -- Drive auth no longer accidentally uses ADC or Service Account files for OAuth
- **"Access blocked: has not completed verification" (403)** -- documented fix (publish OAuth consent screen) in credentials guide

---

## [0.2.0] - 2026-03-28

### Added
- **Vertex AI RAG Engine integration** -- pipeline auto-syncs high-scoring papers to a RAG corpus (`rag_corpus.py`)
- **CLI research agent** (`agent/cli.py`) -- natural language queries over indexed papers using Gemini 3 Flash with configurable thinking levels (`--thinking LOW/MEDIUM/HIGH`)
- Two-step architecture: Vertex AI retrieval + Developer API generation (bypasses Gemini 3 preview API restrictions on Vertex AI)
- `scripts/create_rag_corpus.py` -- one-time corpus setup
- `scripts/backfill_rag_corpus.py` -- backfill from local CSV
- `scripts/backfill_rag_from_notion.py` -- backfill from Notion DB (full history, recommended)
- 14 unit tests for RAG module (`tests/test_rag_corpus.py`)

### Changed
- Default RAG minimum score threshold set to 85
- Error logging in `rag_corpus.py` uses `logger.error` instead of `logger.exception` for cleaner output on transient API failures

### Fixed

- **CSV now appends across runs** instead of overwriting -- `save_csv()` merges new records with existing ones, deduplicating by PMID/DOI
- CSV encoding updated to `utf-8-sig` in backfill script to handle BOM

---

## [0.1.0] - 2026-03-27

### Added
- **Two-pass AI architecture** -- Pass 1 (scoring) + Pass 2 (methods extraction) with configurable Gemini models and thinking levels
- Gemini 3.1 Pro/Flash support with thinking mode (`LOW`/`MEDIUM`/`HIGH`)
- Full-text PDF ingestion via PMC with automatic fallback to abstract-only
- Notion, Google Drive, and CSV storage backends
- PubMed keyword-based discovery with MeSH term enrichment
- Deduplication by DOI/PMID across Notion and pipeline runs
- Shadow Judge escalation heuristics (later removed in refactor)
- Tier 2 methods intelligence pipeline
- GEO/SRA accession validation
- Configurable YAML-based pipeline profiles (`configs/tier1_pca.yaml`, `configs/tier2_methods.yaml`)
