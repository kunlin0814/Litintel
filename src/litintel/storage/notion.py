import os
import logging
from typing import Dict, Any, List

from litintel.enrich.schema import Tier1Record, Tier2Record

logger = logging.getLogger(__name__)

def get_notion_client(api_token: str = None):
    try:
        from notion_client import Client
    except ImportError:
        logger.error("notion-client package not installed.")
        raise ImportError("Please install notion-client")

    token = api_token or os.environ.get("NOTION_TOKEN")
    if not token:
        raise ValueError("NOTION_TOKEN not set")
    return Client(auth=token)

def truncate(text: str, limit: int = 2000) -> str:
    if not text:
        return ""
    return text[:limit]

def _build_tier1_properties(rec: Dict[str, Any]) -> Dict[str, Any]:
    # Maps Tier1Record to Notion Properties (Gold Standard)
    props = {
        "Name": {"title": [{"text": {"content": truncate(rec.get("Title", "Untitled"))}}]},
        "PMID": {"rich_text": [{"text": {"content": str(rec.get("PMID", ""))}}]},
        "DOI": {"rich_text": [{"text": {"content": str(rec.get("DOI", ""))}}]},
        "RelevanceScore": {"number": rec.get("RelevanceScore", 0)},
        "WhyRelevant": {"rich_text": [{"text": {"content": truncate(rec.get("WhyRelevant", ""))}}]},
        "StudySummary": {"rich_text": [{"text": {"content": truncate(rec.get("StudySummary", ""))}}]},
        "PaperRole": {"rich_text": [{"text": {"content": truncate(rec.get("PaperRole", ""))}}]},
        "Methods": {"rich_text": [{"text": {"content": truncate(rec.get("Methods", ""))}}]},
        "KeyFindings": {"rich_text": [{"text": {"content": truncate(rec.get("KeyFindings", ""))}}]},
        "Group": {"rich_text": [{"text": {"content": truncate(rec.get("Group", ""))}}]},
        "CellIdentitySignatures": {"rich_text": [{"text": {"content": truncate(rec.get("CellIdentitySignatures", ""))}}]},
        "PerturbationsUsed": {"rich_text": [{"text": {"content": truncate(rec.get("PerturbationsUsed", ""))}}]},
        "PipelineConfidence": {"select": {"name": rec.get("PipelineConfidence", "Low")}},
        "Year": {"number": int(rec.get("Year")) if rec.get("Year", "").isdigit() else None},
        "Journal": {"select": {"name": truncate(rec.get("Journal", "Unknown"), 100)}},
    }
    
    # Text Arrays (Multi-select)
    if rec.get("Theme"):
        props["Theme"] = {"multi_select": [{"name": t.strip()} for t in rec.get("Theme").split(";") if t.strip()]}
    
    if rec.get("DataTypes"):
        # Clean up types
        dts = [t.strip().replace(",", "-") for t in rec.get("DataTypes").split(",") if t.strip()]
        props["DataTypes"] = {"multi_select": [{"name": d} for d in dts[:10]]} # Limit 10

    return props

def _build_tier2_properties(rec: Dict[str, Any]) -> Dict[str, Any]:
    # Maps Tier2Record to Notion Properties (Methods Intelligence)
    props = {
        "Name": {"title": [{"text": {"content": truncate(rec.get("Title", "Untitled"))}}]},
        "PMID": {"rich_text": [{"text": {"content": str(rec.get("PMID", ""))}}]},
        "RelevanceScore": {"number": rec.get("RelevanceScore", 0)},
        "WhyRelevant": {"rich_text": [{"text": {"content": truncate(rec.get("WhyRelevant", ""))}}]},
        "StudySummary": {"rich_text": [{"text": {"content": truncate(rec.get("StudySummary", ""))}}]},
        
        # New Tier 2 Fields
        "PI_Group": {"rich_text": [{"text": {"content": truncate(rec.get("PI_Group", ""))}}]},
        "MethodName": {"rich_text": [{"text": {"content": truncate(rec.get("MethodName", ""))}}]},
        "MethodRole": {"rich_text": [{"text": {"content": truncate(rec.get("MethodRole", ""))}}]},
        "InputsRequired": {"rich_text": [{"text": {"content": truncate(rec.get("InputsRequired", ""))}}]},
        "KeyParameters": {"rich_text": [{"text": {"content": truncate(rec.get("KeyParameters", ""))}}]},
        "AssumptionsFailureModes": {"rich_text": [{"text": {"content": truncate(rec.get("AssumptionsFailureModes", ""))}}]},
        "EvidenceContext": {"rich_text": [{"text": {"content": truncate(rec.get("EvidenceContext", ""))}}]},
        
        "PipelineConfidence": {"select": {"name": rec.get("PipelineConfidence", "Low")}},
        "Year": {"number": int(rec.get("Year")) if rec.get("Year", "").isdigit() else None},
    }
    
    # Controlled Vocabs
    if rec.get("ProblemArea"):
        props["ProblemArea"] = {"multi_select": [{"name": t.strip()} for t in rec.get("ProblemArea").split(";") if t.strip()]}
        
    if rec.get("DataTypes"):
        dts = [t.strip().replace(",", "-") for t in rec.get("DataTypes").split(",") if t.strip()]
        props["DataTypes"] = {"multi_select": [{"name": d} for d in dts[:10]]}

    return props

def upsert_records(records: List[Dict[str, Any]], database_id: str, tier: int = 1):
    client = get_notion_client()
    
    for rec in records:
        if tier == 1:
            props = _build_tier1_properties(rec)
        else:
            props = _build_tier2_properties(rec)
            
        # Creating page (simplified: always create, no update check for now, can implement query check later)
        try:
            client.pages.create(
                parent={"database_id": database_id},
                properties=props
            )
            logger.info(f"Created Notion page for {rec.get('PMID')}")
        except Exception as e:
            logger.error(f"Failed to create Notion page for {rec.get('PMID')}: {e}")
