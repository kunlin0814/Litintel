import os
import sys
import xml.etree.ElementTree as ET
from prefect import flow

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from modules.config import get_config
from modules.pubmed_tasks import pubmed_efetch_abstracts_by_ids, fetch_pmc_fulltext
from modules.enrichment import ai_enrich_records

@flow(log_prints=True)
def main_flow():
    pmids = ["40550901", "40675159", "40839986"]
    print(f"Checking PMIDs: {pmids}")
    
    # 1. Config
    try:
        cfg = get_config(dry_run=True)
    except Exception as e:
        print(f"Config error: {e}")
        # Proceeding might fail if keys are missing but let's try to proceed if possible or exit
        return
    
    # 2. Fetch Abstracts
    print("Fetching abstracts...")
    try:
        # Calling tasks directly within a flow
        efetch_out = pubmed_efetch_abstracts_by_ids(cfg, pmids)
        print(f"Fetched {len(efetch_out)} abstracts.")
    except Exception as e:
        print(f"Error fetching abstracts: {e}")
        return
    
    # 3. Fetch Full Text
    print("Fetching full texts...")
    try:
        pmc_map = fetch_pmc_fulltext(cfg, efetch_out)
        print(f"Fetched {len(pmc_map)} full texts.")
        for pmid, info in pmc_map.items():
            if info.get('used'):
                print(f"  PMID {pmid}: Full text found (PMCID: {info.get('pmcid')})")
    except Exception as e:
        print(f"Error fetching full texts: {e}")
        pmc_map = {}
    
    # 4. Prepare records
    records = []
    for pmid in pmids:
        data = efetch_out.get(pmid)
        if not data:
            print(f"Warning: No data found for {pmid}")
            records.append({"PMID": pmid})
            continue

        xml_str = data.get("ArticleXML", "") or data.get("RawXML", "")
        title = ""
        authors_str = ""
        
        if xml_str:
            try:
                try:
                    root = ET.fromstring(xml_str)
                except ET.ParseError:
                    root = ET.fromstring(f"<PubmedArticleSet>{xml_str}</PubmedArticleSet>")
                
                # Title
                title_elem = root.find(".//ArticleTitle")
                if title_elem is not None:
                    title = "".join(title_elem.itertext())
                
                # Authors
                authors = []
                for au in root.findall(".//Author"):
                    lname = au.find("LastName")
                    initials = au.find("Initials")
                    lname_text = lname.text if lname is not None else ""
                    initials_text = initials.text if initials is not None else ""
                    if lname_text:
                        authors.append(f"{lname_text} {initials_text}")
                authors_str = ", ".join(authors)
                
            except Exception as e:
                print(f"XML parse error for {pmid}: {e}")
        
        records.append({
            "PMID": pmid,
            "Title": title,
            "Authors": authors_str
        })
        
    print(f"Prepared {len(records)} records for enrichment.")
    
    # 5. Enrich
    print("Running AI enrichment...")
    try:
        enriched = ai_enrich_records(records, efetch_out, pmc_map, cfg=cfg)
        
        # 6. Report
        print("\n" + "="*60)
        print("RESULTS")
        print("="*60)
        for rec in enriched:
            print(f"PMID: {rec.get('PMID')}")
            print(f"Title: {rec.get('Title')}")
            print(f"RelevanceScore: {rec.get('RelevanceScore')}")
            print(f"WhyRelevant: {rec.get('WhyRelevant')}")
            print(f"PipelineConfidence: {rec.get('PipelineConfidence')}")
            print("-" * 60)
            
    except Exception as e:
        print(f"Error during enrichment: {e}")

if __name__ == "__main__":
    main_flow()
