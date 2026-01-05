# Literature Intelligence (LitIntel)

**AI-Augmented Research Memory System** for spatial and single-cell cancer biology literature.

![Python](https://img.shields.io/badge/python-3.9%2B-blue) ![Prefect](https://img.shields.io/badge/prefect-3.x-orange) ![License](https://img.shields.io/badge/license-MIT-green)

---

## What is This?

This is not just a literature search script—it's a **Research Intelligence Layer**.

It continuously monitors PubMed, uses AI to understand and score each paper, and persists structured insights to Notion and Google Drive. Your research "memory" grows over time, queryable by humans and AI agents alike (e.g., NotebookLM).

**Key Capabilities:**
-   **Two-Pass AI Architecture**: Pass 1 (Scoring) uses evidence-appropriate models; Pass 2 (Methods) extracts computational workflows from high-scoring full-text papers.
-   **Cost-Optimized**: Automatic **Prompt Caching** reduces API costs by ~50% through cache-aware processing order (Abstract-only → Full-text).
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

# Google Drive (optional)
GOOGLE_DRIVE_FOLDER_ID=xxx
GOOGLE_CREDENTIALS_PATH=/path/to/service-account.json
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
│   ├── ai_client.py    # OpenAI/Gemini with Two-Pass & Shadow Judge
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
- **Abstract-only papers** → `gpt-5-nano` (processed first to maximize cache hits)
- **Full-text papers** → `gpt-5-mini` (processed second, grouped together)

### Pass 2: Methods Extraction (Batched)
- Triggers only for papers with **Score ≥ 88** and full-text availability
- Runs in **parallel** (ThreadPoolExecutor, max 3 workers) to keep prompt cache warm
- Extracts `comp_methods` with structured `analyses` blocks

**Config (`configs/tier1_pca.yaml`):**
```yaml
ai:
  pass1_model_fulltext: "gpt-5-mini"  # Pass 1 if Full Text
  pass1_model_abstract: "gpt-5-nano"  # Pass 1 if Abstract Only
  pass2_model: "gpt-5-mini"           # Pass 2 (Methods)
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
| `PipelineConfidence` | Low / Medium / Medium-Ambiguous / High / Error. |
| `EscalationTriggered` | Boolean: Were heuristics flagged? |
| `EscalationReason` | Why escalation occurred (heuristic or Shadow Judge result). |
| `comp_methods` | Structured methods (Pass 2 only). |

---

## Escalation Logic (Shadow Judge)

Papers flagged by **heuristics (H1-H4)** are validated by Shadow Judge:

### Heuristics
- **H1**: Short rationale (< 50 chars)
- **H2**: Ambiguous score range [70-79]
- **H3**: Text/score mismatch (high language, low score OR vice versa)
- **H4**: High relevance but low reuse score

### Shadow Judge Rules
1. **OVERTURN** only for material factual errors (must cite evidence)
2. **DISAGREE** if concerns exist but no proof
3. **PASS** if Nano's assessment is acceptable
4. **25% Guardrail**: Pipeline halts if overturn rate exceeds threshold

**Output:**
- `papers_tier1_validated.md`: Only Shadow Judge validated papers (human QA)
- `ESCALATION_COUNTERFACTUALS`: Logged overturns for rubric tuning

---

## Scoring Rubric

| Score | Tier | Criteria |
|-------|------|----------|
| 0 | 0 | Not relevant |
| 30-69 | 1 | Weak relevance |
| 70-79 | 2 | Moderate / Ambiguous (Escalation Target) |
| 80-89 | 3 | High / Solid (PCa + 1 key tech) |
| 90-94 | 4 | Highest (Non-PCa + ≥3 techs, PCa + Multiome + Bulk) |
| 95-100 | 4 | Must Read (PCa + Multiome + Spatial, ≥100 samples) |

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
