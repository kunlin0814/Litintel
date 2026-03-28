# Changelog

All notable changes to LitIntel are documented here.
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
