# Google Drive Integration Walkthrough (Batched Strategy)

I have implemented the **Batched** Google Drive integration. This optimizes your workflow for **NotebookLM** by maintaining a small set of high-density "Corpus Files" instead of thousands of individual files.

## What it does
Instead of creating `File_Per_Paper.md`, the pipeline now:
1.  Creates/Maintains a folder `NotebookLM_Corpus` in your Drive.
2.  **Appends** new papers to **`PCa_Literature_2025_Q1.md`** (All papers).
3.  **Appends** high-quality papers (Score ≥ 85) to **`HighConfidence_Analysis.md`**.
4.  Updates **`papers.jsonl`** for machine processing.

## Setup Instructions (Required)

To make this work, you need to provide Google Cloud credentials.

### 1. Create a Google Service Account
1. Go to [Google Cloud Console](https://console.cloud.google.com/).
2. Create a Project (or use existing).
3. Enable **Google Drive API**.
4. Go to **IAM & Admin** > **Service Accounts** > **Create Service Account**.
5. Click **Keys** > **Add Key** > **Create new key** > **JSON**.
6. Save this file to your local machine (e.g., `/Users/kun-linho/secrets/google_drive_creds.json`).

### 2. Share the Drive Folder
1. Open your Google Drive.
2. Create a new folder (e.g., `Literature_Search_Auto`).
3. Copy the **Folder ID** from the URL (the string after `folders/`).
4. **Share** this folder with the **Service Account Email** (found in the JSON file or Console) as an **Editor**.

### 3. Configure Environment
Update your `.env` file or environment variables:

```bash
export GOOGLE_CREDENTIALS_PATH="/path/to/your/google_drive_creds.json"
export GOOGLE_DRIVE_FOLDER_ID="your_folder_id_here"
```

## NotebookLM Usage
1. Go to NotebookLM.
2. Create `Prostate Cancer Literature`.
3. Add Source > Google Drive.
4. Navigate to `Literature_Search_Auto` > `NotebookLM_Corpus`.
5. Select **`HighConfidence_Analysis.md`** and/or the current **`PCa_Literature_YYYY_QX.md`**.
6. **Resync**: When new papers are added by the pipeline, just click "Sync" in NotebookLM to get the latest append!
