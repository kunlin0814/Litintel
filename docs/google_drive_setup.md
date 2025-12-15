# Google Drive Integration

## Overview

The pipeline syncs literature to Google Drive for AI ingestion (e.g., NotebookLM).

**Output:**
- `papers.jsonl`: Machine-readable log of all papers.
- `NotebookLM_Corpus/Literature_{Year}_Q{Q}.md`: All papers, sorted by relevance.
- `NotebookLM_Corpus/HighConfidence_Analysis.md`: Papers with `RelevanceScore >= 90`.

---

## Setup

### 1. Create Google Service Account

1. Go to [Google Cloud Console](https://console.cloud.google.com/).
2. Create/select a project.
3. Enable **Google Drive API**.
4. Navigate to **IAM & Admin** > **Service Accounts** > **Create**.
5. Create a **JSON key** and download it.

### 2. Share Drive Folder

1. Create a folder in Google Drive (e.g., `Literature_Auto`).
2. Copy the **Folder ID** from the URL.
3. **Share** the folder with the Service Account email (Editor access).

### 3. Configure Environment

Add to `.env`:
```bash
GOOGLE_CREDENTIALS_PATH="/path/to/service-account.json"
GOOGLE_DRIVE_FOLDER_ID="your_folder_id"
```

Alternatively, use **Application Default Credentials** for local development:
```bash
gcloud auth application-default login
```

---

## NotebookLM Usage

1. Open [NotebookLM](https://notebooklm.google.com/).
2. Create a new notebook.
3. Add Source > Google Drive.
4. Select `HighConfidence_Analysis.md` or the quarterly file.
5. Ask questions across your literature corpus!
