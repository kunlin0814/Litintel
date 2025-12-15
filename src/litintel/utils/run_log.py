"""
Utility for appending structured run metadata to a CSV log.

This keeps a lightweight audit trail of which queries were executed and
how many records were created/updated in Notion.
"""

import csv
from datetime import datetime
from pathlib import Path
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)


def append_run_log(
    config_dict: Dict[str, Any],
    stats: Dict[str, Any],
    log_path: str = "run_history.csv"
) -> None:
    """
    Append a single run entry to the configured log file.
    
    Args:
        config_dict: Configuration dictionary with pipeline settings
        stats: Statistics dictionary with run results
        log_path: Path to CSV log file (relative or absolute)
    """
    log_file = Path(log_path).expanduser()
    log_file.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "timestamp_utc",
        "tier",
        "pipeline_name",
        "ai_provider",
        "ai_model",
        "total_searched",
        "records_processed",
        "records_enriched",
        "notion_created",
        "notion_updated",
        "notes",
    ]

    row = {
        "timestamp_utc": datetime.utcnow().isoformat(),
        "tier": config_dict.get("pipeline_tier"),
        "pipeline_name": config_dict.get("pipeline_name", ""),
        "ai_provider": config_dict.get("ai", {}).get("provider", ""),
        "ai_model": config_dict.get("ai", {}).get("model_default", ""),
        "total_searched": stats.get("total_searched", 0),
        "records_processed": stats.get("records_processed", 0),
        "records_enriched": stats.get("records_enriched", 0),
        "notion_created": stats.get("notion_created", 0),
        "notion_updated": stats.get("notion_updated", 0),
        "notes": stats.get("notes", ""),
    }

    write_header = not log_file.exists()

    try:
        with log_file.open("a", newline="", encoding="utf-8") as logfile:
            writer = csv.DictWriter(logfile, fieldnames=fieldnames)
            if write_header:
                writer.writeheader()
            writer.writerow(row)
        logger.info(f"Run log appended to {log_file}")
    except Exception as e:
        logger.error(f"Failed to append run log: {e}")
