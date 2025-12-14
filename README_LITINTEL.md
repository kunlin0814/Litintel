# Literature Intelligence Pipeline

A production-grade, config-driven literature intelligence tool for computational oncology.

## Structure

- **Tier 1 (Prostate Cancer)**: Triage and enrichment for Gold Standard PCa papers.
- **Tier 2 (Methods)**: Discovery of computational tools and benchmarks, organized by Problem Area.

## Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   # Ensure dependencies match pyproject.toml
   ```

2. Set Environment Variables:
   - `OPENAI_API_KEY`: Required for AI enrichment.
   - `NOTION_TOKEN`: Required for Notion integration.
   - `NOTION_DB_ID`: For Tier 1.
   - `NOTION_METHODS_DB_ID`: For Tier 2.

## Usage

**Run Tier 1 (PCa Triage):**
```bash
python3 src/litintel/cli.py tier1 --config configs/tier1_pca.yaml
```

**Run Tier 2 (Methods Discovery):**
```bash
python3 src/litintel/cli.py tier2 --config configs/tier2_methods.yaml
```

**Validate Config:**
```bash
python3 src/litintel/cli.py validate --config configs/tier2_methods.yaml
```

## Configuration

Edit `configs/tier1_pca.yaml` or `configs/tier2_methods.yaml` to adjust queries, seed authors, models, or storage settings.

## Tests

Run acceptance tests:
```bash
python3 -m unittest discover tests
```
