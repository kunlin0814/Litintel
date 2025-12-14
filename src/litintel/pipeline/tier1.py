import logging
import os
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

logger = logging.getLogger(__name__)

def run_tier1_pipeline(config: AppConfig):
    logger.info(f"Starting Tier 1 Pipeline: {config.pipeline_name}")
    
    # 1. Discovery (Keyword only for Tier 1 usually)
    pmids = set()
    if config.discovery.queries:
        for q in config.discovery.queries:
            ids = search_pubmed(q, retmax=config.discovery.retmax, reldays=config.discovery.reldays)
            pmids.update(ids)
            
    unique_pmids = list(pmids)
    if not unique_pmids:
        logger.warning("No papers found.")
        return

    # 2. Fetch & Parse
    xml_data = fetch_details(unique_pmids)
    raw_records = parse_pubmed_xml_stream(xml_data)
    
    # 3. Dedup
    clean_records = deduplicate_records(raw_records, config.dedup.keys)
    
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

        enrichment = enrich_record(
            text=f"Title: {rec['Title']}\nAbstract: {rec['Abstract']}",
            authors=rec.get("Authors", ""),
            pmid=rec.get("PMID"),
            config=config.ai,
            system_prompt=system_prompt,
            json_schema=Tier1Record.model_json_schema(),
            pydantic_model=Tier1Record,
            group_fallback=group_fallback
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
            
    # Drive Sync (Optional implementation placeholder)
    if config.storage.drive and config.storage.drive.enabled:
        logger.info("Drive sync enabled - implement drive_sync module to upload Markdown/JSONL.")

    logger.info("Tier 1 Pipeline Complete.")
