# Literature Intelligence (LitIntel)

**AI-Augmented Research Memory System** for spatial and single-cell cancer biology literature.

![Python](https://img.shields.io/badge/python-3.9%2B-blue) ![Prefect](https://img.shields.io/badge/prefect-3.x-orange) ![License](https://img.shields.io/badge/license-MIT-green)

---

## What is This?

This is not just a literature search script—it's a **Research Intelligence Layer**.

It continuously monitors PubMed, uses AI to understand and score each paper, and persists structured insights to Notion and Google Drive. Your research "memory" grows over time, queryable by humans and AI agents alike (e.g., NotebookLM).

**Key Capabilities:**
-   **AI Enrichment**: OpenAI (GPT-5 Nano/Mini) or Gemini extract structured insights.
-   **Cost-Optimized**: Automatic **Prompt Caching** reduces API costs by ~50% for repetitive system instructions.
-   **Smart Search**: Fetches papers in **batches of 200** to efficiently bypass duplicates and find new content using deep pagination (up to 1,000 papers).
-   **Provenance Tracking**: Know exactly what evidence the AI used (`AI_EvidenceLevel`: FullText or Abstract).
-   **Dual-Confidence Accession**: GEO/SRA candidates are regex-extracted, then AI-validated.
-   **Multi-Storage Sync**: Notion (human review), Google Drive JSONL (machine ingestion), CSV (archival).
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
│   ├── tier1.py        # Tier 1: Disease-focused pipeline
│   └── tier2.py        # Tier 2: Methods-focused pipeline
├── pubmed/
│   └── client.py       # NCBI E-Utilities integration
├── enrich/
│   ├── ai_client.py    # OpenAI/Gemini abstraction
│   ├── schema.py       # Pydantic models (Tier1Record, Tier2Record)
│   └── prompt_templates.py # System prompts
└── storage/
    ├── notion.py       # Notion API sync
    └── drive.py        # Google Drive JSONL/Markdown sync
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
| `EscalationTriggered` | Boolean: Was Shadow Judge invoked? |
| `EscalationReason` | Why escalation occurred (heuristic or Shadow Judge result). |

---

## Escalation Logic (Shadow Judge)

Papers with **ambiguous scores (70-79)** or structural issues are validated by a second AI model:

1. **Deterministic Heuristics** (H1-H4) flag papers for review
2. **Shadow Judge** (`gpt-5-mini`) audits flagged papers with full-text evidence
3. **Evidence Requirement**: Mini must quote text to overturn Nano
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
