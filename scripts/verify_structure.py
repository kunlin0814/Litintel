
import os
import sys
from typing import Dict, Any

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from modules.drive_tasks import _format_markdown_entry

def test_markdown_format():
    # Mock Record with new fields
    mock_rec = {
        "PMID": "12345678",
        "Title": "Spatial Chromatin Landscapes",
        "Journal": "Nature",
        "PubDate": "2024-01-01",
        "Authors": "Doe J et al.",
        "RelevanceScore": 95,
        "PipelineConfidence": "High",
        "FullTextUsed": True,
        "Group": "Charles Lab",
        "PaperRole": "Establishes spatial ATAC-based lineage framework.",
        "Theme": "Spatial lineage; Epigenetic heterogeneity",
        "WhyRelevant": "Key paper for spatial ATAC.",
        "StudySummary": "Summary of the study.",
        "Methods": "scATAC-seq; Visium; Custom Analysis",
        "KeyFindings": "Finding 1; Finding 2; Finding 3",
        "DataTypes": "scATAC, Visium"
    }

    print("--- GENERATED MARKDOWN START ---")
    output = _format_markdown_entry(mock_rec)
    print(output)
    print("--- GENERATED MARKDOWN END ---")
    
    # Assertions to verify structure
    errors = []
    if "**Group**: Charles Lab" not in output:
        errors.append("Missing Group field")
    if "**PaperRole**: Establishes spatial" not in output:
        errors.append("Missing PaperRole field")
    if "**Theme**: Spatial lineage" not in output:
        errors.append("Missing Theme field")
    if "- Visium" not in output:
        errors.append("Methods not bulleted correctly")
    if "- Finding 2" not in output:
        errors.append("KeyFindings not bulleted correctly")

    if errors:
        print("\n❌ FAILED Verification:")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
    else:
        print("\n✅ SUCCESS: Markdown structure matches Gold Standard.")

if __name__ == "__main__":
    test_markdown_format()
