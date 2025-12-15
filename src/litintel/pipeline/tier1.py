import logging
import os
import time
import yaml
from typing import List, Dict, Any

from litintel.config import AppConfig
from litintel.pubmed.client import search_pubmed, fetch_details
from litintel.parsing import parse_pubmed_xml_stream
from litintel.pipeline.shared import deduplicate_records, save_csv
from litintel.enrich.ai_client import enrich_record
from litintel.enrich.schema import Tier1Record
from litintel.enrich.prompt_templates import get_system_prompt
from litintel.storage.notion import upsert_records
from litintel.utils.run_log import append_run_log

logger = logging.getLogger(__name__)

def run_tier1_pipeline(config: AppConfig):
    logger.info(f"Starting Tier 1 Pipeline: {config.pipeline_name}")
    
    logger.info("Starting Disease-Specific Pipeline...")
    
    # 0. Build Notion Index (for smart deduplication)
    notion_index = {}
    if config.storage.notion and config.storage.notion.enabled:
        db_id = config.storage.notion.database_id_env
        real_db_id = os.environ.get(db_id)
        if real_db_id:
            from litintel.storage.notion import build_notion_index
            logger.info("Building Notion index for deduplication...")
            notion_index = build_notion_index(real_db_id)
    
    # 1. Search
    unique_pmids = set()
    for query in config.discovery.queries:
        pmids = search_pubmed(
            query=query,
            retmax=config.discovery.retmax,
            reldays=config.discovery.reldays
        )
        unique_pmids.update(pmids)
    
    logger.info(f"Found {len(unique_pmids)} unique PMIDs from search")
    
    # Filter out papers already in Notion
    if notion_index:
        new_pmids = [p for p in unique_pmids if p not in notion_index]
        skipped = len(unique_pmids) - len(new_pmids)
        logger.info(f"Skipped {skipped} papers already in Notion, {len(new_pmids)} new")
        unique_pmids = new_pmids
    
    if not unique_pmids:
        logger.info("No new papers to process")
        return

    # 2. Fetch & Parse
    xml_data = fetch_details(list(unique_pmids))
    raw_records = parse_pubmed_xml_stream(xml_data)
    
    # 3. Dedup
    clean_records = deduplicate_records(raw_records, config.dedup.keys)
    
    # Initialize defaults
    for r in clean_records:
        r["AI_EvidenceLevel"] = "Abstract"
    
    # 3.5. PMC Full-Text Fetch (if available)
    logger.info("Checking for PMC full-text availability...")
    pmcids = [rec.get("PMCID") for rec in clean_records if rec.get("PMCID")]
    
    pmc_data = {}
    if pmcids:
        from litintel.pubmed.client import fetch_pmc_fulltext
        from litintel.parsing import extract_pmc_sections
        
        logger.info(f"Fetching full-text for {len(pmcids)} papers with PMCID...")
        pmc_xml_map = fetch_pmc_fulltext(pmcids)
        
        # Extract sections and GEO/SRA from PMC
        for pmcid, xml in pmc_xml_map.items():
            sections_text, geo_pmc, sra_pmc = extract_pmc_sections(xml)
            pmc_data[pmcid] = {
                "full_text": sections_text,
                "geo_pmc": geo_pmc,
                "sra_pmc": sra_pmc
            }
        
        logger.info(f"Extracted full-text from {len(pmc_data)} PMC articles")
    
    # Merge PMC data into records
    for rec in clean_records:
        pmcid = rec.get("PMCID")
        if pmcid and pmcid in pmc_data:
            rec["FullTextUsed"] = True
            rec["AI_EvidenceLevel"] = "FullText"
            rec["PMC_FullText"] = pmc_data[pmcid]["full_text"]
            
            # Merge PMC-found GEO/SRA with PubMed XML candidates
            if pmc_data[pmcid]["geo_pmc"]:
                existing = set(rec.get("GEO_Candidates", "").split(", ")) if rec.get("GEO_Candidates") else set()
                existing.update(pmc_data[pmcid]["geo_pmc"].split(", "))
                rec["GEO_Candidates"] = ", ".join(sorted(existing - {""}))
            
            if pmc_data[pmcid]["sra_pmc"]:
                existing = set(rec.get("SRA_Candidates", "").split(", ")) if rec.get("SRA_Candidates") else set()
                existing.update(pmc_data[pmcid]["sra_pmc"].split(", "))
                rec["SRA_Candidates"] = ", ".join(sorted(existing - {""}))
    
    # 4. Enrichment
    system_prompt = get_system_prompt(config.ai.prompt_template)
    
    enriched_records = []
    for rec in clean_records:
        authors_str = rec.get("Authors", "")
        group_fallback = ""
        if authors_str:
             parts = authors_str.split(",")
             if parts:
                 group_fallback = parts[-1].strip()
        
        # Build enrichment text: Title + Abstract + PMC (if available)
        enrich_text = f"Title: {rec['Title']}\nAbstract: {rec['Abstract']}"
        if rec.get("PMC_FullText"):
            enrich_text += f"\n\nFULL TEXT:\n{rec['PMC_FullText'][:8000]}"  # Limit to 8k chars

        enrichment = enrich_record(
            text=enrich_text,
            authors=rec.get("Authors", ""),
            pmid=rec.get("PMID"),
            config=config.ai,
            system_prompt=system_prompt,
            json_schema=Tier1Record.model_json_schema(),
            pydantic_model=Tier1Record,
            group_fallback=group_fallback,
            geo_candidates=rec.get("GEO_Candidates", ""),
            sra_candidates=rec.get("SRA_Candidates", "")
        )
        full_rec = {**rec, **enrichment}
        enriched_records.append(full_rec)

    # 5. Output
    valid_records = [r for r in enriched_records if r.get("PipelineConfidence") != "Error"]
    
    if config.storage.csv and config.storage.csv.enabled:
        save_csv(valid_records, config.storage.csv.filename)

    if config.storage.notion and config.storage.notion.enabled:
        db_id = config.storage.notion.database_id_env
        real_db_id = os.environ.get(db_id)
        if real_db_id:
            upsert_records(valid_records, real_db_id, tier=1)
        else:
            logger.warning(f"Notion env var {db_id} not set.")
            
    # Drive Sync (if enabled)
    if config.storage.drive and config.storage.drive.enabled:
        drive_folder = os.environ.get("GOOGLE_DRIVE_FOLDER_ID")
        creds_path = os.environ.get("GOOGLE_CREDENTIALS_PATH")
        
        if drive_folder:
            try:
                from litintel.storage.drive import sync_to_drive
                logger.info("Syncing to Google Drive...")
                sync_to_drive(valid_records, drive_folder, creds_path)
            except Exception as e:
                logger.error(f"Drive sync failed: {e}")
        else:
            logger.warning("GOOGLE_DRIVE_FOLDER_ID not set, skipping Drive sync")

    # Log execution
    append_run_log(
        config_dict=config.model_dump(),
        stats={
            "total_searched": len(unique_pmids) if 'unique_pmids' in locals() else 0,
            "records_processed": len(clean_records) if 'clean_records' in locals() else 0,
            "records_enriched": len(valid_records),
            "notion_created": 0,  # Would be populated if notion returns count
            "notes": "Tier 1 pipeline complete"
        }
    )

    logger.info("Tier 1 Pipeline Complete.")
