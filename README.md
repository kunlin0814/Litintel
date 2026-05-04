# Literature Intelligence (LitIntel)

**AI-Augmented Research Memory System** for spatial and single-cell cancer biology literature.

![Python](https://img.shields.io/badge/python-3.9%2B-blue) ![Prefect](https://img.shields.io/badge/prefect-3.x-orange) ![License](https://img.shields.io/badge/license-MIT-green)

---

## What is This?

This is not just a literature search script--it's a **Research Intelligence Layer**.

It continuously monitors PubMed, uses AI to understand and score each paper, and persists structured insights to Notion and Google Drive. Your research "memory" grows over time, queryable by humans and AI agents alike (e.g., NotebookLM).

**Key Capabilities:**
-   **Two-Pass AI Architecture**: Pass 1 (Scoring) uses evidence-appropriate models; Pass 2 (Methods) extracts computational workflows from high-scoring full-text papers.
-   **Cost-Optimized**: Automatic **Prompt Caching** reduces API costs by ~50% through cache-aware processing order (Abstract-only -> Full-text).
-   **Shadow Judge**: Heuristic-triggered secondary validation with evidence requirement (quote or self-contradiction must be cited).
-   **Smart Search**: Fetches papers in **batches of 200** to efficiently bypass duplicates and find new content using deep pagination (up to 1,000 papers).
-   **Provenance Tracking**: Know exactly what evidence the AI used (`AI_EvidenceLevel`: FullText or Abstract).
-   **Dual-Confidence Accession**: GEO/SRA candidates are regex-extracted, then AI-validated.
-   **Multi-Storage Sync**: Notion (human review), Google Drive JSONL/Markdown (machine ingestion), CSV (archival).
-   **Automated Scheduling**: Prefect Cloud runs every two weeks, hands-free.

---

## Quick Start

### 1. Install

```bash
git clone https://github.com/kunlin0814/internal_research_ops.git
cd internal_research_ops
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure `.env`

```env
NCBI_API_KEY=your_key
NCBI_EMAIL=your.email@institution.edu
NOTION_TOKEN=secret_xxx
NOTION_DB_ID=xxx

# AI Provider
OPENAI_API_KEY=sk-proj-xxx
# OR: GOOGLE_API_KEY=xxx

# Google Drive (optional; personal Drive uses OAuth)
GOOGLE_DRIVE_CLIENT_SECRET=/path/to/oauth-client-secret.json
GOOGLE_DRIVE_FOLDER_ID=xxx

# Optional but recommended: pin exact existing Drive targets to avoid duplicates
GOOGLE_DRIVE_PAPERS_JSONL_FILE_ID=xxx
GOOGLE_DRIVE_NOTEBOOKLM_FOLDER_ID=xxx
GOOGLE_DRIVE_COMP_METHODS_FOLDER_ID=xxx
GOOGLE_DRIVE_PDF_FOLDER_ID=xxx

# GCP / Vertex / RAG (separate from personal Drive OAuth)
GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
GCP_PROJECT_ID=your-gcp-project
VERTEX_RAG_CORPUS_NAME=projects/.../locations/.../ragCorpora/...
```

### 3. Run

```bash
# Run Tier 1 (Prostate Cancer Gold Standard)
python -m litintel.cli tier1

# Run Tier 2 (Methods Discovery)
python -m litintel.cli tier2

# Validate a config file
python -m litintel.cli validate configs/tier1_pca.yaml
```

---

## Google Auth Notes

LitIntel intentionally separates **GCP auth** from **personal Google Drive
auth**:

- `GOOGLE_APPLICATION_CREDENTIALS` / ADC is for Vertex AI, Gemini-on-GCP, and
  Vertex RAG.
- `GOOGLE_DRIVE_CLIENT_SECRET` plus the local `token_drive.json` OAuth cache is
  for writing to a personal Google Drive folder.

Do not assume a company GCP credential can write to personal Drive. Even when a
Drive folder is shared with a service account, the Drive API credential also
needs a Drive-capable scope. The current Drive sync uses full Drive OAuth scope
so it can append to existing/manual files by ID.

Reauthorize Drive only when needed:

- `token_drive.json` is missing or deleted.
- You switch Google accounts.
- Google access was revoked.
- Drive returns `File not found` for a file/folder you can open in the browser.
- The pipeline creates duplicate `NotebookLM_Corpus`, `PDFs`, or `papers.jsonl`
  instead of appending.

Use the dedicated auth helper:

```bash
venv/bin/python scripts/auth/auth_google_drive.py

# Optional: also write a tiny smoke-test file to Drive
venv/bin/python scripts/auth/auth_google_drive.py --write-smoke
```

To avoid duplicate Drive outputs, set exact IDs in `.env`:

```env
GOOGLE_DRIVE_FOLDER_ID="root-folder-id"
GOOGLE_DRIVE_PAPERS_JSONL_FILE_ID="papers-jsonl-file-id"
GOOGLE_DRIVE_NOTEBOOKLM_FOLDER_ID="notebooklm-folder-id"
GOOGLE_DRIVE_COMP_METHODS_FOLDER_ID="computational-methods-folder-id"
GOOGLE_DRIVE_PDF_FOLDER_ID="pdf-folder-id"
```

If these exact IDs are set, LitIntel updates those targets directly instead of
searching by name. See [docs/google_drive_setup.md](docs/google_drive_setup.md)
for details.

---

## Architecture

```
src/litintel/
├── cli.py              # Typer CLI entrypoint
├── config.py           # Pydantic configuration models
├── parsing.py          # PubMed XML and PMC parsing
├── pipeline/
│   ├── tier1.py        # Tier 1: Disease-focused pipeline (Two-Pass)
│   ├── tier2.py        # Tier 2: Methods-focused pipeline
│   └── shared.py       # Common utilities (dedup, save)
├── pubmed/
│   └── client.py       # NCBI E-Utilities integration
├── enrich/
│   ├── ai_client.py    # Dual-provider (Gemini SDK default / OpenAI fallback) With Two-Pass & Shadow Judge
│   ├── schema.py       # Pydantic models (Tier1Record, CompMethods)
│   ├── prompt_templates.py # System prompts (Scoring + Methods)
│   └── escalation_heuristics.py # H1-H4 heuristic checks
├── storage/
│   ├── notion.py       # Notion API sync
│   └── drive.py        # Google Drive JSONL/Markdown sync
└── utils/
    └── run_log.py      # Execution audit trail
```

---

## Two-Pass AI Architecture

The pipeline uses a cache-optimized two-pass system:

### Pass 1: Scoring & Metadata
- **Abstract-only papers** -> `gemini-3-flash-preview` with MEDIUM thinking (processed first to maximize cache hits)
- **Full-text papers** -> `gemini-3-flash-preview` with HIGH thinking (processed second, grouped together)

### Pass 2: Methods Extraction (Batched)
- Triggers only for papers with **Score >= 88** and full-text availability
- Uses `gemini-3.1-pro-preview` with LOW thinking for structured extraction
- Runs in **parallel** (ThreadPoolExecutor, max 3 workers) to keep prompt cache warm
- Extracts `comp_methods` with structured `analyses` blocks

**Config (`configs/tier1_pca.yaml`):**
```yaml
ai:
  pass1_model_fulltext: "gemini-3-flash-preview"   # Pass 1 if Full Text
  pass1_thinking_fulltext: "HIGH"                   # Thinking level for full-text scoring
  pass1_model_abstract: "gemini-3-flash-preview"   # Pass 1 if Abstract Only
  pass1_thinking_abstract: "MEDIUM"                 # Thinking level for abstract scoring
  pass2_model: "gemini-3.1-pro-preview"            # Pass 2 (Methods)
  pass2_thinking: "LOW"                             # Thinking level for methods extraction
  pass2_min_score: 88                 # Trigger threshold for Pass 2
```

---

## Data Schema

All AI-extracted fields are strictly typed:

| Field | Description |
|-------|-------------|
| `RelevanceScore` | 0-100. Tier 3 (80-89) = Solid, Tier 4 (90+) = Must Read. |
| `WhyRelevant` | 1-sentence justification. |
| `WhyYouMightCare` | Reusable insight (e.g., "Novel spatial CNV method"). |
| `StudySummary` | 2-3 sentences: aim, cohort, result. |
| `Methods` | Experimental + computational tools. |
| `KeyFindings` | Semicolon-separated discoveries. |
| `DataTypes` | Controlled vocab (scRNA-seq, Visium, etc.). |
| `AI_EvidenceLevel` | "FullText" or "Abstract". |
| `PipelineConfidence` | Low / Medium / High / Error. |
| `comp_methods` | Structured methods (Pass 2 only). |

---

## Scoring Rubric

| Score | Tier | Criteria |
|-------|------|----------|
| 0 | 0 | Not relevant |
| 30-69 | 1 | Weak relevance |
| 70-79 | 2 | Moderate / Ambiguous (Escalation Target) |
| 80-89 | 3 | High / Solid (PCa + 1 key tech) |
| 90-94 | 4 | Highest (Non-PCa + >=3 techs, PCa + Multiome + Bulk) |
| 95-100 | 4 | Must Read (PCa + Multiome + Spatial, >=100 samples) |

---

## Prefect Deployment

Automated serverless execution every two weeks.

**Trigger Manually:**
```bash
prefect deployment run 'PCa-Tier1-GoldStandard-Pipeline/tier1-pca-gold-standard'
```

**Manage:**
```bash
prefect deployment pause 'PCa-Tier1-GoldStandard-Pipeline/tier1-pca-gold-standard'
prefect deployment resume 'PCa-Tier1-GoldStandard-Pipeline/tier1-pca-gold-standard'
```

---

## License

MIT. See `LICENSE`.
