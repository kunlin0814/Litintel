
import os
import sys
import logging
from dotenv import load_dotenv

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from modules.drive_tasks import archive_to_drive

# Configure logging
logging.basicConfig(level=logging.INFO)

def verify_export_logic():
    load_dotenv()
    
    # Mock Config
    cfg = {
        "GOOGLE_CREDENTIALS_PATH": os.getenv("GOOGLE_CREDENTIALS_PATH"), # Should be commented out or None for ADC
        "GOOGLE_DRIVE_FOLDER_ID": os.getenv("GOOGLE_DRIVE_FOLDER_ID")
    }
    
    # Mock Enriched Records
    mock_records = [
        {
            "PMID": "TEST_LOW_85",
            "Title": "Test Paper Score 85 (Should NOT be in HighConfidence)",
            "Journal": "Journal of Testing",
            "PubDate": "2025-01-01",
            "RelevanceScore": 85,
            "PipelineConfidence": "Medium",
            "WhyRelevant": "Testing threshold.",
            "StudySummary": "Summary...",
            "KeyFindings": "Finding 1",
            "Methods": "Method 1"
        },
        {
            "PMID": "TEST_HIGH_90",
            "Title": "Test Paper Score 90 (SHOULD be in HighConfidence)",
            "Journal": "Journal of Testing",
            "PubDate": "2025-01-02",
            "RelevanceScore": 90,
            "PipelineConfidence": "High",
            "WhyRelevant": "Testing threshold.",
            "StudySummary": "Summary...",
            "KeyFindings": "Finding 1",
            "Methods": "Method 1"
        },
        {
            "PMID": "TEST_HIGH_95",
            "Title": "Test Paper Score 95 (SHOULD be in HighConfidence)",
            "Journal": "Journal of Testing",
            "PubDate": "2025-01-03",
            "RelevanceScore": 95,
            "PipelineConfidence": "High",
            "WhyRelevant": "Testing threshold.",
            "StudySummary": "Summary...",
            "KeyFindings": "Finding 1",
            "Methods": "Method 1"
        }
    ]
    
    print("Running archive_to_drive with mock data...")
    archive_to_drive(mock_records, cfg)
    print("Done! Please check Google Drive 'NotebookLM_Corpus/HighConfidence_Analysis.md'.")
    print("It should contain TEST_HIGH_90 and TEST_HIGH_95, but NOT TEST_LOW_85.")

if __name__ == "__main__":
    verify_export_logic()
