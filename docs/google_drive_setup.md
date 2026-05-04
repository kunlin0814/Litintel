# Google Drive Integration

## Overview

The pipeline syncs literature to Google Drive for AI ingestion (e.g., NotebookLM).

**Output Files:**
- `papers.jsonl`: Machine-readable log of all papers (root folder).
- `NotebookLM_Corpus/Literature_{Year}_Q{Q}.md`: All papers, sorted by relevance.
- `NotebookLM_Corpus/HighConfidence_Analysis.md`: Papers with `RelevanceScore >= 90`.
- `NotebookLM_Corpus/CompMethods_{Year}_Q{Q}.md`: Computational methods from full-text papers (Pass 2 output).

---

## Setup

> For the full credential architecture, troubleshooting, and multi-project
> CLI coexistence, see [gcp_credentials_guide.md](gcp_credentials_guide.md).

### 1. Create OAuth Client Secret (Desktop App)

1. Go to [GCP Console -> APIs & Services -> Credentials](https://console.cloud.google.com/apis/credentials).
2. Enable **Google Drive API** if not already enabled.
3. Click **+ Create Credentials -> OAuth client ID**.
4. Application type: **Desktop app**.
5. Download the JSON and save to `/Volumes/Research/gemini_credentials/`.

### 2. Set Up Drive Folder

1. Create a folder in Google Drive (e.g., `Literature_Auto`).
2. Copy the **Folder ID** from the URL (the long string after `/folders/`).
3. The OAuth flow uses your personal account -- no folder sharing needed.

### 3. Configure Environment

Add to `.env`:
```bash
GOOGLE_DRIVE_CLIENT_SECRET="/path/to/client_secret_*.json"
GOOGLE_DRIVE_FOLDER_ID="your_folder_id"

# Optional but recommended for stable appends to existing Drive targets
GOOGLE_DRIVE_PAPERS_JSONL_FILE_ID="your_papers_jsonl_file_id"
GOOGLE_DRIVE_NOTEBOOKLM_FOLDER_ID="your_notebooklm_folder_id"
GOOGLE_DRIVE_COMP_METHODS_FOLDER_ID="your_computational_methods_folder_id"
GOOGLE_DRIVE_PDF_FOLDER_ID="your_pdf_folder_id"
```

On first run, a browser window will open for one-time consent. After that,
a `token_drive.json` is cached locally (gitignored) and reused automatically.

### Drive Auth Boundary

`GOOGLE_APPLICATION_CREDENTIALS` is for GCP services such as Vertex AI and
Vertex RAG. Personal Google Drive sync uses OAuth through
`GOOGLE_DRIVE_CLIENT_SECRET` and `token_drive.json`.

Reauthorize Drive only when needed:

- `token_drive.json` is missing or deleted.
- You switch Google accounts.
- Google access was revoked.
- Drive returns `File not found` for a folder/file you can open in the browser.
- The pipeline creates duplicate `NotebookLM_Corpus`, `PDFs`, or `papers.jsonl`
  instead of appending.

The Drive sync uses full Drive OAuth scope because narrower `drive.file` scope
cannot reliably see older/manual folders and files. Exact IDs in `.env` are
preferred over name search for stable appends.

Use the dedicated auth helper instead of running the full pipeline just to
refresh auth:

```bash
venv/bin/python scripts/auth/auth_google_drive.py

# Optional: verify write access by appending one small test line
venv/bin/python scripts/auth/auth_google_drive.py --write-smoke
```

---

## Output Structure

```
Literature_Auto/                    # Root folder (GOOGLE_DRIVE_FOLDER_ID)
├── papers.jsonl                    # JSONL log (one line per paper)
├── PDFs/                           # Open-access PMC PDFs, score >= pdf_min_score
└── NotebookLM_Corpus/              # Markdown subfolder
    ├── Literature_2025_Q1.md       # All Q1 2025 papers
    ├── Literature_2025_Q2.md       # All Q2 2025 papers
    ├── HighConfidence_Analysis.md  # Score >= 90 papers (rolling)
    └── Computational_Methods/
        └── CompMethods_2025_Q1.md  # Methods from full-text papers
```

---

## Drive Sync Thresholds

The pipeline applies different thresholds for different outputs:

| Output | Threshold | Notes |
|--------|-----------|-------|
| `papers.jsonl` | All papers | Complete machine-readable log |
| `Literature_{Year}_Q{Q}.md` | Score >= 87 + Full-text | High-quality papers with full evidence |
| `HighConfidence_Analysis.md` | Score >= 90 + Full-text | "Must read" papers with full evidence |
| `CompMethods_{Year}_Q{Q}.md` | Score >= 85 + Full-text | Methods from high-quality full-text papers |
| `PDFs/*.pdf` | `pdf_min_score`, default 88 | PMC Open Access PDFs only |

> [!NOTE]
> - `Literature_Q.md` requires **both** Score >= 87 AND full-text to ensure high confidence.
> - The `pass2_min_score: 88` threshold only controls **Pass 2 methods extraction**, not Drive filtering.
> - `pdf_min_score: 88` controls PDF upload and is intentionally aligned with the Pass 2 threshold by default.


---

## NotebookLM Usage

1. Open [NotebookLM](https://notebooklm.google.com/).
2. Create a new notebook.
3. Add Source > Google Drive.
4. Select `HighConfidence_Analysis.md` or the quarterly file.
5. Ask questions across your literature corpus!

**Recommended Sources:**
- **HighConfidence_Analysis.md**: Best papers only (Score >= 90)
- **CompMethods_{Year}_Q{Q}.md**: Computational methods focus
- **Literature_{Year}_Q{Q}.md**: Complete quarterly coverage (Score >= 80)
