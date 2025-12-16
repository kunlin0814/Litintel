import time
import logging
import requests
from typing import List, Dict, Any
import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)

BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

def search_pubmed(query: str, retmax: int = 30, reldays: int = 365, retstart: int = 0, email: str = "agent@deepmind.com") -> List[str]:
    # eSearch
    params = {
        "db": "pubmed",
        "term": query,
        "retmax": retmax,
        "retstart": retstart,
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

def fetch_details(pmids: List[str], email: str = "agent@deepmind.com", batch_size: int = 200) -> str:
    """Fetch PubMed article details in batches (NCBI recommends max 200 IDs per request)."""
    if not pmids:
        return ""
    
    all_xml_parts = []
    
    # Batch the PMIDs
    for i in range(0, len(pmids), batch_size):
        batch = pmids[i:i + batch_size]
        ids_str = ",".join(batch)
        
        params = {
            "db": "pubmed",
            "id": ids_str,
            "retmode": "xml",
            "email": email
        }
        
        try:
            resp = requests.post(f"{BASE_URL}/efetch.fcgi", data=params, timeout=60)
            resp.raise_for_status()
            all_xml_parts.append(resp.text)
            logger.info(f"Fetched batch {i // batch_size + 1} ({len(batch)} PMIDs)")
        except Exception as e:
            logger.error(f"EFetch failed for batch starting at {i}: {e}")
            # Continue with other batches instead of failing completely
        
        # Rate limiting: NCBI recommends max 3 requests/second
        if i + batch_size < len(pmids):
            time.sleep(0.34)
    
    if not all_xml_parts:
        return ""
    
    # Merge XML responses - combine all PubmedArticle elements
    if len(all_xml_parts) == 1:
        return all_xml_parts[0]
    
    # For multiple batches, merge the XML (extract articles from each and combine)
    try:
        combined_articles = []
        for xml_part in all_xml_parts:
            root = ET.fromstring(xml_part)
            for article in root.findall(".//PubmedArticle"):
                combined_articles.append(ET.tostring(article, encoding='unicode'))
        
        return f'<?xml version="1.0"?>\n<PubmedArticleSet>{"".join(combined_articles)}</PubmedArticleSet>'
    except ET.ParseError as e:
        logger.error(f"Failed to merge XML responses: {e}")
        # Fallback: return first valid response
        return all_xml_parts[0] if all_xml_parts else ""


def fetch_pmc_fulltext(pmcids: List[str], email: str = "agent@deepmind.com", batch_size: int = 50) -> Dict[str, str]:
    """
    Fetch PMC full-text XML for given PMCIDs.
    
    Args:
        pmcids: List of PMCIDs (with or without 'PMC' prefix)
        email: Email for E-utilities
        batch_size: Number of PMCIDs per batch
        
    Returns:
        Dict mapping PMCID to raw PMC XML string
    """
    if not pmcids:
        return {}
    
    results = {}
    
    for i in range(0, len(pmcids), batch_size):
        batch = pmcids[i:i + batch_size]
        # Strip 'PMC' prefix for the API
        ids_stripped = [p.replace("PMC", "") for p in batch]
        
        params = {
            "db": "pmc",
            "retmode": "xml",
            "id": ",".join(ids_stripped),
            "email": email
        }
        
        try:
            resp = requests.get(f"{BASE_URL}/efetch.fcgi", params=params, timeout=120)
            resp.raise_for_status()
            
            root = ET.fromstring(resp.text)
            for article in root.findall(".//article"):
                # Extract PMCID from article
                pmcid = None
                for aid in article.findall(".//article-id"):
                    if aid.attrib.get("pub-id-type") in ("pmc", "pmcid") and aid.text:
                        pmcid = aid.text.strip()
                        if not pmcid.startswith("PMC"):
                            pmcid = "PMC" + pmcid
                        break
                
                if pmcid:
                    results[pmcid] = ET.tostring(article, encoding='unicode')
            
            logger.info(f"Fetched PMC batch {i // batch_size + 1} ({len(batch)} PMCIDs)")
        except Exception as e:
            logger.error(f"PMC EFetch failed for batch starting at {i}: {e}")
        
        # Rate limiting
        if i + batch_size < len(pmcids):
            time.sleep(0.34)
    
    return results
