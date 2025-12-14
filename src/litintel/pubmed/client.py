import time
import logging
import requests
from typing import List, Dict, Any
import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)

BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

def search_pubmed(query: str, retmax: int = 30, reldays: int = 365, email: str = "agent@deepmind.com") -> List[str]:
    # eSearch
    params = {
        "db": "pubmed",
        "term": query,
        "retmax": retmax,
        "reldate": reldays,
        "datetype": "pdat",
        "sort": "relevance",
        "email": email,
        "retmode": "json" # JSON is easier for ID list
    }
    
    try:
        resp = requests.get(f"{BASE_URL}/esearch.fcgi", params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        ids = data.get("esearchresult", {}).get("idlist", [])
        logger.info(f"Found {len(ids)} papers for query: {query[:50]}...")
        return ids
    except Exception as e:
        logger.error(f"ESearch failed for {query}: {e}")
        return []

def fetch_details(pmids: List[str], email: str = "agent@deepmind.com") -> str:
    if not pmids:
        return ""
    
    # EFetch
    ids_str = ",".join(pmids)
    params = {
        "db": "pubmed",
        "id": ids_str,
        "retmode": "xml",
        "email": email
    }
    
    try:
        resp = requests.post(f"{BASE_URL}/efetch.fcgi", data=params, timeout=60)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        logger.error(f"EFetch failed: {e}")
        return ""
