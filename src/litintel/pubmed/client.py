import os
import time
import logging
import requests
from typing import List, Dict, Any, Optional
import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)

BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
PMC_OA_URL = "https://www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi"

# With API key: 10 req/s -> 0.11s sleep; without: 3 req/s -> 0.34s
_RATE_LIMIT_DELAY_WITH_KEY = 0.11
_RATE_LIMIT_DELAY_NO_KEY = 0.34
_MAX_RETRIES = 3


def _ncbi_params(extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Build base params dict with email and api_key from env vars."""
    params: Dict[str, Any] = {
        "email": os.environ.get("NCBI_EMAIL", "agent@deepmind.com"),
    }
    api_key = os.environ.get("NCBI_API_KEY")
    if api_key:
        params["api_key"] = api_key
    if extra:
        params.update(extra)
    return params


def _rate_delay() -> float:
    """Return inter-request sleep in seconds based on API key presence."""
    if os.environ.get("NCBI_API_KEY"):
        return _RATE_LIMIT_DELAY_WITH_KEY
    return _RATE_LIMIT_DELAY_NO_KEY


def _request_with_retry(
    method: str,
    url: str,
    *,
    max_retries: int = _MAX_RETRIES,
    **kwargs: Any,
) -> requests.Response:
    """HTTP request with exponential-backoff retry on 429.

    Raises the last exception if all retries are exhausted.
    """
    for attempt in range(max_retries + 1):
        resp = requests.request(method, url, **kwargs)
        if resp.status_code != 429:
            resp.raise_for_status()
            return resp
        if attempt < max_retries:
            wait = 2 ** attempt  # 1s, 2s, 4s
            logger.warning(
                "NCBI 429 rate limit on %s -- retry %d/%d in %ds",
                url.split("?")[0], attempt + 1, max_retries, wait,
            )
            time.sleep(wait)
    # Final attempt was also 429 -- raise
    resp.raise_for_status()
    return resp  # unreachable, but keeps type checker happy

def search_pubmed(query: str, retmax: int = 30, reldays: int = 365, retstart: int = 0, email: str = "agent@deepmind.com") -> List[str]:
    # eSearch
    params = _ncbi_params({
        "db": "pubmed",
        "term": query,
        "retmax": retmax,
        "retstart": retstart,
        "reldate": reldays,
        "datetype": "pdat",
        "sort": "relevance",
        "retmode": "json",  # JSON is easier for ID list
    })

    try:
        resp = _request_with_retry("GET", f"{BASE_URL}/esearch.fcgi", params=params, timeout=30)
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
    delay = _rate_delay()

    # Batch the PMIDs
    for i in range(0, len(pmids), batch_size):
        batch = pmids[i:i + batch_size]
        ids_str = ",".join(batch)

        params = _ncbi_params({
            "db": "pubmed",
            "id": ids_str,
            "retmode": "xml",
        })

        try:
            resp = _request_with_retry("POST", f"{BASE_URL}/efetch.fcgi", data=params, timeout=60)
            all_xml_parts.append(resp.text)
            logger.info(f"Fetched batch {i // batch_size + 1} ({len(batch)} PMIDs)")
        except Exception as e:
            logger.error(f"EFetch failed for batch starting at {i}: {e}")
            # Continue with other batches instead of failing completely

        if i + batch_size < len(pmids):
            time.sleep(delay)
    
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
    delay = _rate_delay()

    for i in range(0, len(pmcids), batch_size):
        batch = pmcids[i:i + batch_size]
        # Strip 'PMC' prefix for the API
        ids_stripped = [p.replace("PMC", "") for p in batch]

        params = _ncbi_params({
            "db": "pmc",
            "retmode": "xml",
            "id": ",".join(ids_stripped),
        })

        try:
            resp = _request_with_retry("GET", f"{BASE_URL}/efetch.fcgi", params=params, timeout=120)

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

        if i + batch_size < len(pmcids):
            time.sleep(delay)

    return results


def _normalize_pmcid(pmcid: str) -> str:
    """Normalize a PMCID to the PMC-prefixed form used by NCBI services."""
    clean = str(pmcid or "").strip()
    if not clean:
        return ""
    if clean.upper().startswith("PMC"):
        return "PMC" + clean[3:]
    return f"PMC{clean}"


def _download_url_from_oa_href(href: str) -> str:
    """Convert PMC OA FTP links to HTTPS so requests can download them."""
    if href.startswith("ftp://ftp.ncbi.nlm.nih.gov/"):
        return "https://ftp.ncbi.nlm.nih.gov/" + href.removeprefix(
            "ftp://ftp.ncbi.nlm.nih.gov/"
        )
    return href


def _pmc_pdf_download_urls(primary_url: str) -> List[str]:
    """Return current and migration fallback URLs for a PMC OA PDF."""
    urls = [primary_url]
    legacy_prefix = "https://ftp.ncbi.nlm.nih.gov/pub/pmc/"
    deprecated_prefix = "https://ftp.ncbi.nlm.nih.gov/pub/pmc/deprecated/"
    if primary_url.startswith(legacy_prefix) and not primary_url.startswith(deprecated_prefix):
        urls.append(primary_url.replace(legacy_prefix, deprecated_prefix, 1))
    return urls


def fetch_pmc_pdf_url(
    pmcid: str,
    timeout: int = 30,
) -> Optional[str]:
    """
    Resolve an open-access PMC PDF URL for a PMCID.

    Uses the official PMC OA Web Service. Only papers in the PMC Open Access
    Subset with a PDF resource will return a URL.

    Args:
        pmcid: PMCID with or without the "PMC" prefix.
        timeout: Request timeout in seconds.

    Returns:
        Downloadable HTTPS URL, or None if no OA PDF is available.
    """
    normalized_pmcid = _normalize_pmcid(pmcid)
    if not normalized_pmcid:
        return None

    params = {"id": normalized_pmcid, "format": "pdf"}

    try:
        resp = requests.get(PMC_OA_URL, params=params, timeout=timeout)
        resp.raise_for_status()
        root = ET.fromstring(resp.text)
    except Exception as e:
        logger.warning("Failed to resolve PMC PDF URL for %s: %s", normalized_pmcid, e)
        return None

    error = root.find(".//error")
    if error is not None:
        logger.info("No PMC OA PDF for %s: %s", normalized_pmcid, error.text or "")
        return None

    for link in root.findall(".//link"):
        if link.attrib.get("format", "").lower() != "pdf":
            continue
        href = link.attrib.get("href", "").strip()
        if href:
            return _download_url_from_oa_href(href)

    logger.info("No PMC OA PDF link found for %s", normalized_pmcid)
    return None


def fetch_pmc_pdf(
    pmcid: str,
    email: str = "agent@deepmind.com",
    timeout: int = 120,
) -> Optional[bytes]:
    """
    Download an open-access PMC PDF for a PMCID.

    Args:
        pmcid: PMCID with or without the "PMC" prefix.
        email: Contact email included in the user agent.
        timeout: Request timeout in seconds.

    Returns:
        Raw PDF bytes, or None if unavailable or invalid.
    """
    normalized_pmcid = _normalize_pmcid(pmcid)
    pdf_url = fetch_pmc_pdf_url(normalized_pmcid)
    if not pdf_url:
        return None

    headers = {"User-Agent": f"LitIntel/0.1 ({email})"}

    content = b""
    last_error = None
    for candidate_url in _pmc_pdf_download_urls(pdf_url):
        try:
            resp = requests.get(candidate_url, headers=headers, timeout=timeout)
            resp.raise_for_status()
            content = resp.content
            break
        except Exception as e:
            last_error = e

    if not content:
        logger.warning("Failed to download PMC PDF for %s: %s", normalized_pmcid, last_error)
        return None

    if not content.startswith(b"%PDF"):
        logger.warning("Downloaded content for %s is not a PDF", normalized_pmcid)
        return None

    return content
