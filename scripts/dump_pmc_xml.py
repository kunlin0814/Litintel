
import sys
import os
import logging
from litintel.pubmed.client import fetch_pmc_fulltext

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

import xml.etree.ElementTree as ET

def dump_xml(pmcid: str):
    logger.info(f"Fetching XML for {pmcid}")
    pmc_map = fetch_pmc_fulltext([pmcid])
    
    if pmcid in pmc_map:
        xml_content = pmc_map[pmcid]
        root = ET.fromstring(xml_content)
        
        body = root.find(".//body")
        if body is not None:
            logger.info("--- SECTION TITLES IN BODY ---")
            for sec in body.findall(".//sec"):
                title_elem = sec.find("title")
                if title_elem is not None:
                    title = "".join(title_elem.itertext()).strip()
                    logger.info(f"Section: '{title}'")
                    # Check subsections
                    for sub in sec.findall(".//sec"):
                         sub_title = sub.find("title")
                         if sub_title is not None:
                             st = "".join(sub_title.itertext()).strip()
                             logger.info(f"  Subsection: '{st}'")
        else:
            logger.warning("No body element found")

        # Check back matter too
        back = root.find(".//back")
        if back is not None:
             logger.info("--- SECTION TITLES IN BACK ---")
             for sec in back.findall(".//sec"):
                title_elem = sec.find("title")
                if title_elem is not None:
                    title = "".join(title_elem.itertext()).strip()
                    logger.info(f"Back Section: '{title}'")

if __name__ == "__main__":
    dump_xml("PMC12630738")
