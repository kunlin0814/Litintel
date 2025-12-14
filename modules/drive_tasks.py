from typing import Dict, Any, List
from prefect import task, get_run_logger
from modules.drive_utils import get_drive_service, append_to_jsonl, ensure_folder_exists, append_text_to_file
import json
import datetime
import math

@task
def archive_to_drive(enriched_records: List[Dict[str, Any]], cfg: Dict[str, Any]) -> None:
    """Archiving records to Google Drive using a Batched/Thematic Strategy.
    
    Strategy:
    1. 'HighConfidence_Analysis.md': Papers with Score >= 85
    2. 'Quarterly_Analysis_{Year}_Q{Q}.md': All papers, sorted by score.
    3. 'papers.jsonl': Machine-readable log of everything.
    """
    logger = get_run_logger()
    
    folder_id = cfg.get("GOOGLE_DRIVE_FOLDER_ID")
    creds_path = cfg.get("GOOGLE_CREDENTIALS_PATH")
    
    if not folder_id:
        logger.warning("GOOGLE_DRIVE_FOLDER_ID not set. Skipping Drive archive.")
        return
        
    try:
        service = get_drive_service(creds_path)
    except Exception as e:
        logger.error(f"Failed to authenticate with Google Drive: {e}. Skipping archive.")
        return

    # 1. JSONL Export (All records - Machine Layer)
    jsonl_filename = "papers.jsonl"
    try:
        append_id = append_to_jsonl(service, folder_id, jsonl_filename, enriched_records)
        logger.info(f"Appended {len(enriched_records)} records to {jsonl_filename}")
    except Exception as e:
        logger.error(f"Failed to update {jsonl_filename}: {e}")

    # 2. Markdown Export (Thematic Buckets - Reasoning Layer)
    # We create a subfolder for these to keep them organized, or put in root?
    # User example: /NotebookLM/PCa_Spatial_2024_Q4.md
    # Let's put them in 'NotebookLM_Corpus' folder.
    corpus_folder_name = "NotebookLM_Corpus"
    try:
        corpus_folder_id = ensure_folder_exists(service, corpus_folder_name, folder_id)
    except Exception as e:
        logger.error(f"Failed to ensure corpus folder: {e}")
        return

    # Prepare Buckets
    high_conf_papers = []
    current_date = datetime.datetime.now()
    year = current_date.year
    quarter = math.ceil(current_date.month / 3)
    quarterly_filename = f"PCa_Literature_{year}_Q{quarter}.md"
    high_conf_filename = "HighConfidence_Analysis.md"
    
    # Sort records by score descending for better readability in the file
    sorted_records = sorted(enriched_records, key=lambda x: x.get("RelevanceScore", 0), reverse=True)
    
    quarterly_text_buffer = []
    high_conf_text_buffer = []

    for rec in sorted_records:
        score = rec.get("RelevanceScore", 0)
        confidence = rec.get("PipelineConfidence", "Low")
        
        # Format text
        md_text = _format_markdown_entry(rec)
        
        # Add to Quarterly Buffer (All papers)
        quarterly_text_buffer.append(md_text)
        
        # Add to High Confidence Buffer
        # Logic: Score >= 90 OR (Score >= 80 AND Confidence == High)
        # Using User's logic: Score >= 85 (simple threshold from initial request, updated to 90 later)
        # Let's stick to a robust threshold: Score >= 85
        if score >= 85:
            high_conf_text_buffer.append(md_text)
            
    # Append to Quarterly File
    if quarterly_text_buffer:
        try:
            full_text = "\n\n".join(quarterly_text_buffer)
            append_text_to_file(service, corpus_folder_id, quarterly_filename, full_text)
            logger.info(f"Appended {len(quarterly_text_buffer)} papers to {quarterly_filename}")
        except Exception as e:
            logger.error(f"Failed to append to {quarterly_filename}: {e}")

    # Append to High Confidence File
    if high_conf_text_buffer:
        try:
            full_text = "\n\n".join(high_conf_text_buffer)
            append_text_to_file(service, corpus_folder_id, high_conf_filename, full_text)
            logger.info(f"Appended {len(high_conf_text_buffer)} papers to {high_conf_filename}")
        except Exception as e:
            logger.error(f"Failed to append to {high_conf_filename}: {e}")


def _format_markdown_entry(rec: Dict[str, Any]) -> str:
    """Format a record into a single Markdown entry block."""
    lines = []
    # Separator
    lines.append("---") 
    lines.append(f"## PMID: {rec.get('PMID')} — {rec.get('Journal', 'Unknown Journal')} ({rec.get('PubDate', 'N/A')})")
    lines.append(f"**Title**: {rec.get('Title', 'Untitled')}")
    lines.append(f"**RelevanceScore**: {rec.get('RelevanceScore')}")
    lines.append(f"**PipelineConfidence**: {rec.get('PipelineConfidence', 'N/A')}")
    lines.append(f"**FullTextUsed**: {'Yes' if rec.get('FullTextUsed') else 'No'}")
    lines.append(f"**Group**: {rec.get('Group', '')}")
    lines.append("")
    lines.append("### WhyRelevant")
    lines.append(rec.get("WhyRelevant", ""))
    lines.append("")
    lines.append("### StudySummary")
    lines.append(rec.get("StudySummary", ""))
    lines.append("")
    lines.append("### Methods")
    lines.append(rec.get("Methods", ""))
    lines.append("")
    lines.append("### Key Findings")
    findings = rec.get("KeyFindings", "")
    if ";" in findings:
        for f in findings.split(";"):
            if f.strip():
                lines.append(f"- {f.strip()}")
    else:
        lines.append(findings)
    lines.append("")
    lines.append("### Data Types")
    lines.append(rec.get("DataTypes", ""))
    
    return "\n".join(lines)
