import logging
import yaml
from typing import List, Dict, Any

from litintel.config import AppConfig, DiscoveryMode
from litintel.pubmed.client import search_pubmed, fetch_details
from litintel.parsing import parse_pubmed_xml_stream
from litintel.pipeline.shared import deduplicate_records, save_csv
from litintel.enrich.ai_client import enrich_record
from litintel.enrich.schema import Tier2Record
from litintel.enrich.prompt_templates import get_system_prompt
from litintel.storage.notion import upsert_records
from litintel.utils.vocab import VocabNormalizer

logger = logging.getLogger(__name__)

def run_tier2_pipeline(config: AppConfig):
    logger.info(f"Starting Tier 2 Pipeline: {config.pipeline_name}")
    
    # 1. Discovery
    pmids = set()
    queries = []
    
    # Author Seeded
    if config.discovery.mode in [DiscoveryMode.AUTHOR_SEEDED, DiscoveryMode.MIXED]:
        if config.discovery.seed_authors:
            # Build query: (Author[Au] OR Author[Full Author Name]) AND (method keywords)
            # Simplified method keywords for context
            context_query = '(spatial OR "single-cell" OR scRNA OR scATAC OR multiome OR transcriptomics OR chromatin)'
            for author in config.discovery.seed_authors:
                q = f'(("{author}"[Author] OR "{author}"[FAU]) AND {context_query})'
                queries.append(q)
    
    # Keyword
    if config.discovery.mode in [DiscoveryMode.KEYWORD, DiscoveryMode.MIXED]:
        if config.discovery.keyword_queries:
            queries.extend(config.discovery.keyword_queries)
            
    logger.info(f"Executing {len(queries)} discovery queries...")
    for i, q in enumerate(queries):
        ids = search_pubmed(q, retmax=config.discovery.retmax, reldays=config.discovery.reldays)
        pmids.update(ids)
        # Rate limiting: NCBI recommends max 3 requests/second
        if i < len(queries) - 1:
            import time
            time.sleep(0.34)
        
    unique_pmids = list(pmids)
    logger.info(f"Total Unique PMIDs found: {len(unique_pmids)}")
    
    if not unique_pmids:
        logger.warning("No papers found. Exiting.")
        return

    # 2. Fetch & Parse
    xml_data = fetch_details(unique_pmids)
    raw_records = parse_pubmed_xml_stream(xml_data)
    
    # 3. Dedup
    clean_records = deduplicate_records(raw_records, config.dedup.keys)
    logger.info(f"Processing {len(clean_records)} records after deduplication.")
    
    # Load controlled vocab using Util
    vocab_normalizer = VocabNormalizer("configs/controlled_vocab.yaml")
    problem_areas = vocab_normalizer.problem_areas

    # 4. Enrichment
    system_prompt = get_system_prompt(config.ai.prompt_template, problem_areas=problem_areas)
    
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
            json_schema=Tier2Record.model_json_schema(),
            pydantic_model=Tier2Record,
            group_fallback=group_fallback
        )
        
        # Post-Enrichment Normalization (MethodName)
        if "MethodName" in enrichment and enrichment["MethodName"]:
             enrichment["MethodName"] = vocab_normalizer.normalize_method_name(enrichment["MethodName"])
        
        full_rec = {**rec, **enrichment}
        enriched_records.append(full_rec)
        
    # 5. Output
    valid_records = [r for r in enriched_records if r.get("PipelineConfidence") != "Error"]
    failed_records = [r for r in enriched_records if r.get("PipelineConfidence") == "Error"]
    
    if failed_records:
        logger.warning(f"{len(failed_records)} records failed enrichment.")
        save_csv(failed_records, "failed_records.csv")

    if config.storage.csv and config.storage.csv.enabled:
        save_csv(valid_records, config.storage.csv.filename)
        
    if config.storage.notion and config.storage.notion.enabled:
        db_id = config.storage.notion.database_id_env
        import os
        real_db_id = os.environ.get(db_id)
        if real_db_id:
            upsert_records(valid_records, real_db_id, tier=2)
        else:
            logger.warning(f"Notion enabled but env var {db_id} not set.")

    logger.info("Pipeline Complete.")
