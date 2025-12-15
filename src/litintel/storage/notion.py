import os
import logging
import time
import requests
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
    from datetime import datetime
    
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
        
        # NEW: Genomic Data Accessions (AI-Validated)
        "GEO_Validated": {"rich_text": [{"text": {"content": truncate(rec.get("GEO_Validated", ""))}}]},
        "SRA_Validated": {"rich_text": [{"text": {"content": truncate(rec.get("SRA_Validated", ""))}}]},
        
        # NEW: MeSH Terms
        "MeSH_Major": {"rich_text": [{"text": {"content": truncate(rec.get("MeSH_Major", ""))}}]},
        "MeSH_Terms": {"rich_text": [{"text": {"content": truncate(rec.get("MeSH_Terms", ""))}}]},
        "MeSH_Headings": {"rich_text": [{"text": {"content": truncate(rec.get("MeSH_Headings", ""))}}]},
        
        # Metadata
        "PipelineConfidence": {"select": {"name": rec.get("PipelineConfidence", "Low")}},
        "AI_EvidenceLevel": {"select": {"name": rec.get("AI_EvidenceLevel", "Abstract")}},
        "WhyYouMightCare": {"rich_text": [{"text": {"content": truncate(rec.get("WhyYouMightCare", ""))}}]},
        "Journal": {"select": {"name": truncate(rec.get("Journal", "Unknown"), 100)}},
        
        # Additional Useful Fields
        "FullTextUsed": {"checkbox": rec.get("FullTextUsed", False)},
        "Abstract": {"rich_text": [{"text": {"content": truncate(rec.get("Abstract", ""), 2000)}}]},
        "Authors": {"rich_text": [{"text": {"content": truncate(rec.get("Authors", ""), 2000)}}]},
        "LastChecked": {"date": {"start": datetime.now().date().isoformat()}},
    }
    
    # URL (PubMed link)
    pmid = rec.get("PMID")
    if pmid:
        props["URL"] = {"url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"}
    
    # PubDate (exact publication date if available, otherwise use Year as YYYY-01-01)
    year = rec.get("Year")
    if year and year.isdigit():
        props["PubDate"] = {"date": {"start": f"{year}-01-01"}}
    
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
    logger.info(f"Upserted {len(records)} records to Notion database {database_id}")


def build_notion_index(database_id: str) -> Dict[str, str]:
    """
    Build an index of existing papers in Notion database.
    
    Maps DedupeKey (PMID or DOI) to page_id for fast lookup.
    This enables smart pagination - we can check if a paper already exists
    before fetching/enriching it.
    
    Args:
        database_id: Notion database ID
        
    Returns:
        Dict mapping DedupeKey → page_id
    """
    token = os.environ.get("NOTION_TOKEN")
    if not token:
        logger.warning("NOTION_TOKEN not set; returning empty index")
        return {}
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }
    
    url = f"https://api.notion.com/v1/databases/{database_id}/query"
    index: Dict[str, str] = {}
    payload: Dict[str, Any] = {}
    has_more = True
    
    try:
        while has_more:
            resp = requests.post(url, headers=headers, json=payload, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            
            for page in data.get("results", []):
                props = page.get("properties", {})
                
                # Try DedupeKey field first
                dedupe_prop = props.get("DedupeKey")
                if dedupe_prop and dedupe_prop.get("rich_text"):
                    text = "".join(t["plain_text"] for t in dedupe_prop["rich_text"])
                    if text:
                        index[text] = page["id"]
                        continue
                
                # Fallback: try PMID field
                pmid_prop = props.get("PMID")
                if pmid_prop and pmid_prop.get("rich_text"):
                    pmid = "".join(t["plain_text"] for t in pmid_prop["rich_text"])
                    if pmid:
                        index[pmid] = page["id"]
            
            has_more = data.get("has_more", False)
            payload["start_cursor"] = data.get("next_cursor")
            
            # Rate limiting
            time.sleep(0.3)
        
        logger.info(f"Built Notion index with {len(index)} existing papers")
        return index
        
    except Exception as e:
        logger.error(f"Failed to build Notion index: {e}")
        return {}
