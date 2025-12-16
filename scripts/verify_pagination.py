
import logging
from litintel.pubmed.client import search_pubmed

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def verify_pagination():
    query = "prostate cancer"
    
    # Page 1
    logger.info("Fetching Page 1 (offset 0, limit 5)...")
    page1 = search_pubmed(query, retmax=5, retstart=0)
    logger.info(f"Page 1: {page1}")
    
    # Page 2
    logger.info("Fetching Page 2 (offset 5, limit 5)...")
    page2 = search_pubmed(query, retmax=5, retstart=5)
    logger.info(f"Page 2: {page2}")
    
    # Check intersection
    overlap = set(page1).intersection(set(page2))
    if overlap:
        logger.error(f"FAILURE: Found overlapping PMIDs: {overlap}")
        exit(1)
        
    if page1 == page2:
        logger.error("FAILURE: Page 1 and Page 2 are identical!")
        exit(1)
        
    logger.info("SUCCESS: Pagination works. Pages are distinct.")

if __name__ == "__main__":
    verify_pagination()
