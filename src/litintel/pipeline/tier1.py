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

def run_tier1_pipeline(config: AppConfig, limit: int = None):
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
    
    # 1. Search with Optimized Batching (Ordered + Deduplicated)
    # We fetch larger batches (200) to skip over duplicates quickly, but only analyze 'retmax' (e.g. 30)
    seen_pmids = set()
    ordered_pmids = []
    
    SEARCH_BATCH_SIZE = 200  
    MAX_PAGES = 5            # Fetch up to 1000 papers per query
    target_count = limit if limit else config.discovery.retmax
    
    for query in config.discovery.queries:
        # Check if we already have enough papers from previous queries
        if len(ordered_pmids) >= target_count:
            logger.info(f"Target of {target_count} papers reached before query: '{query[:20]}...'")
            break

        start_offset = 0
        page = 0
        
        while page < MAX_PAGES:
            params = {
                "query": query,
                "retmax": SEARCH_BATCH_SIZE,
                "reldays": config.discovery.reldays,
                "retstart": start_offset
            }
            logger.info(f"Searching PubMed (Page {page+1}): '{query[:40]}...' [limit={SEARCH_BATCH_SIZE}, offset={start_offset}]")
            
            batch_pmids = search_pubmed(**params)
            
            if not batch_pmids:
                break
                
            # Filter duplicates immediately while PRESERVING ORDER
            new_in_batch = 0
            for pmid in batch_pmids:
                if pmid not in seen_pmids:
                    # Check Notion Index
                    if notion_index and pmid in notion_index:
                        continue
                    
                    # It's new!
                    seen_pmids.add(pmid)
                    ordered_pmids.append(pmid)
                    new_in_batch += 1
                    
                    # Stop accumulating if we hit target
                    if len(ordered_pmids) >= target_count:
                        break
            
            logger.info(f"  - Hits: {len(batch_pmids)} | New added: {new_in_batch} | Total New: {len(ordered_pmids)}")

            # Stop conditions
            if len(ordered_pmids) >= target_count:
                logger.info(f"reached target of {target_count} new papers.")
                break
                
            if len(batch_pmids) < SEARCH_BATCH_SIZE:
                 logger.info("End of search results.")
                 break
                
            # Prepare next page
            start_offset += SEARCH_BATCH_SIZE
            page += 1
            
    # Final list is already limited by the loop logic, but safety slice just in case
    final_pmids = ordered_pmids[:target_count]
    logger.info(f"Final Selection: {len(final_pmids)} papers for analysis (Target: {target_count})")
    
    if not final_pmids:
        logger.info("No new papers to process")
        return

    # 2. Fetch & Parse
    xml_data = fetch_details(final_pmids)
    raw_records = parse_pubmed_xml_stream(xml_data)
    
    # 3. Dedup
    clean_records = deduplicate_records(raw_records, config.dedup.keys)
    
    # Initialize defaults
    for r in clean_records:
        r["AI_EvidenceLevel"] = "Abstract"
        r["FullTextUsed"] = False
    
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
            sections_text, geo_pmc, sra_pmc, pmc_methods, pmc_results = extract_pmc_sections(xml)
            pmc_data[pmcid] = {
                "full_text": sections_text,
                "geo_pmc": geo_pmc,
                "sra_pmc": sra_pmc,
                "methods": pmc_methods,
                "results": pmc_results
            }
        
        logger.info(f"Extracted full-text from {len(pmc_data)} PMC articles")
    
    # Merge PMC data into records
    for rec in clean_records:
        pmcid = rec.get("PMCID")
        if pmcid and pmcid in pmc_data:
            pmc_methods = pmc_data[pmcid]["methods"]
            pmc_results = pmc_data[pmcid]["results"]
            
            # Only mark as FullText if we actually have methods or results content
            has_content = bool(pmc_methods.strip() or pmc_results.strip())
            
            rec["FullTextUsed"] = has_content
            rec["AI_EvidenceLevel"] = "FullText" if has_content else "Abstract"
            rec["PMC_FullText"] = pmc_data[pmcid]["full_text"]
            rec["PMC_Methods"] = pmc_methods
            rec["PMC_Results"] = pmc_results
            
            # Merge PMC-found GEO/SRA with PubMed XML candidates
            if pmc_data[pmcid]["geo_pmc"]:
                existing = set(rec.get("GEO_Candidates", "").split(", ")) if rec.get("GEO_Candidates") else set()
                existing.update(pmc_data[pmcid]["geo_pmc"].split(", "))
                rec["GEO_Candidates"] = ", ".join(sorted(existing - {""}))
            
            if pmc_data[pmcid]["sra_pmc"]:
                existing = set(rec.get("SRA_Candidates", "").split(", ")) if rec.get("SRA_Candidates") else set()
                existing.update(pmc_data[pmcid]["sra_pmc"].split(", "))
                rec["SRA_Candidates"] = ", ".join(sorted(existing - {""}))
    
    # 4. Enrichment - OPTIMIZED FOR PROMPT CACHING
    # Sort papers by model type to maximize cache efficiency:
    # - Abstract-only papers use Nano (process first)
    # - Full-text papers use Mini (process second)
    # This avoids cache thrashing from model switching.
    
    system_prompt = get_system_prompt(config.ai.prompt_template)
    
    # Partition records
    abstract_only = [r for r in clean_records if not r.get("FullTextUsed")]
    full_text = [r for r in clean_records if r.get("FullTextUsed")]
    
    logger.info(f"Cache Optimization: Processing {len(abstract_only)} Abstract-only (Nano) first, then {len(full_text)} Full-text (Mini)")
    
    # Debug: Show actual order
    if abstract_only:
        logger.info(f"  Abstract-only PMIDs: {[r.get('PMID') for r in abstract_only]}")
    if full_text:
        logger.info(f"  Full-text PMIDs: {[r.get('PMID') for r in full_text]}")
    
    # Process in optimized order: Nano batch -> Mini batch
    ordered_records = abstract_only + full_text
    
    enriched_records = []
    for rec in ordered_records:
        authors_str = rec.get("Authors", "")
        group_fallback = ""
        if authors_str:
             parts = authors_str.split(",")
             if parts:
                 group_fallback = parts[-1].strip()
        
        # Build enrichment text: Title + Abstract + PMC (if available)
        enrich_text = f"Title: {rec['Title']}\nAbstract: {rec['Abstract']}"
        if rec.get("PMC_Methods") or rec.get("PMC_Results"):
            # Prioritize extracted sections if available
            # OpenAI 128k context ~ 500k chars. We use conservative limits to leave room for output.
            if rec.get("PMC_Methods"):
                enrich_text += f"\n\nMETHODS:\n{rec['PMC_Methods'][:100000]}"
            if rec.get("PMC_Results"):
                enrich_text += f"\n\nRESULTS:\n{rec['PMC_Results'][:100000]}"
        elif rec.get("PMC_FullText"):
            # Fallback to raw full text
            enrich_text += f"\n\nFULL TEXT:\n{rec['PMC_FullText'][:200000]}"  # 200k chars ~ 50k tokens

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
            sra_candidates=rec.get("SRA_Candidates", ""),
            abstract=rec.get("Abstract", ""),
            methods_text=rec.get("PMC_Methods", ""),
            results_text=rec.get("PMC_Results", "")
        )
        full_rec = {**rec, **enrichment}
        enriched_records.append(full_rec)

    # 4b. PHASE 2: BATCHED METHODS EXTRACTION (Cache Optimized)
    # Run all Pass 2 calls CONCURRENTLY to maximize prompt caching efficiency.
    # Sequential calls have 1+ minute gaps causing cache expiry.
    pass2_eligible = [r for r in enriched_records if r.get("_pass2_eligible")]
    
    if pass2_eligible:
        logger.info(f"Pass 2 Batch: Extracting methods for {len(pass2_eligible)} high-scoring papers (parallel)...")
        from litintel.enrich.ai_client import enrich_pass2_methods
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        def run_pass2(rec):
            pmid = rec.get("PMID")
            result = enrich_pass2_methods(
                pmid=pmid,
                methods_text=rec.get("PMC_Methods", ""),
                results_text=rec.get("PMC_Results", ""),
                config=config.ai
            )
            return pmid, result
        
        # Run Pass 2 calls in parallel (max 3 concurrent to avoid rate limits)
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {executor.submit(run_pass2, rec): rec for rec in pass2_eligible}
            
            for future in as_completed(futures):
                rec = futures[future]
                try:
                    pmid, methods_result = future.result()
                    rec.update(methods_result)
                except Exception as e:
                    logger.error(f"Pass 2 failed for {rec.get('PMID')}: {e}")
                    rec["comp_methods_error"] = str(e)
                
                # Clean up internal marker
                rec.pop("_pass2_eligible", None)
    
    # Clean up markers for non-eligible records too
    for rec in enriched_records:
        rec.pop("_pass2_eligible", None)

    # 4c. Tier C - Multimodal figure-grounded enrichment (auto path)
    # Gated on: tier_c.enabled, RelevanceScore >= tier_c.min_score, PMCID present.
    if config.tier_c and config.tier_c.enabled:
        from litintel.tierc.runner import run_tier_c_for_record

        tierc_candidates = [
            r for r in enriched_records
            if int(r.get("RelevanceScore", 0) or 0) >= config.tier_c.min_score
            and r.get("PMCID")
        ]
        logger.info(
            "Tier C [auto]: %d candidate(s) at score >= %d with PMCID",
            len(tierc_candidates), config.tier_c.min_score,
        )
        for rec in tierc_candidates:
            try:
                tc_fields = run_tier_c_for_record(rec, config.tier_c, source="PMC_OA")
                rec.update(tc_fields)
            except Exception:
                logger.exception(
                    "Tier C [auto]: unexpected error for PMID=%s (continuing)",
                    rec.get("PMID"),
                )

    # 5. Output
    valid_records = [r for r in enriched_records if r.get("PipelineConfidence") != "Error"]

    drive_folder = None
    creds_path = os.environ.get("GOOGLE_CREDENTIALS_PATH")
    if config.storage.drive and config.storage.drive.enabled:
        folder_env = config.storage.drive.folder_id_env or "GOOGLE_DRIVE_FOLDER_ID"
        drive_folder = os.environ.get(folder_env)

        if drive_folder and config.storage.drive.upload_pdfs:
            try:
                from litintel.storage.drive import upload_pmc_pdfs_to_drive
                logger.info(
                    "Uploading PMC PDFs to Google Drive for score >= %s...",
                    config.storage.drive.pdf_min_score,
                )
                upload_pmc_pdfs_to_drive(
                    records=valid_records,
                    folder_id=drive_folder,
                    credentials_path=creds_path,
                    min_score=config.storage.drive.pdf_min_score,
                    pdf_folder_name=config.storage.drive.pdf_folder_name,
                    pdf_folder_id=os.environ.get(
                        config.storage.drive.pdf_folder_id_env or ""
                    ),
                )
            except Exception as e:
                logger.error(f"Drive PDF upload failed: {e}")
        elif config.storage.drive.upload_pdfs:
            logger.warning("Drive folder env var not set, skipping PDF upload")
    
    if config.storage.csv and config.storage.csv.enabled:
        save_csv(valid_records, config.storage.csv.filename)
        
        # Save human-readable Markdown ONLY for papers validated by Shadow Judge
        # (Heuristics triggered AND Shadow Judge said PASS or DISAGREE)
        validated_records = [
            r for r in valid_records 
            if r.get("EscalationReason", "").startswith("SHADOW_JUDGE_PASS") or
               r.get("EscalationReason", "").startswith("SHADOW_JUDGE_DISAGREE")
        ]
        
        if validated_records:
            from litintel.pipeline.shared import save_markdown
            md_filename = config.storage.csv.filename.replace('.csv', '_validated.md')
            save_markdown(validated_records, md_filename)

    if config.storage.notion and config.storage.notion.enabled:
        db_id = config.storage.notion.database_id_env
        real_db_id = os.environ.get(db_id)
        if real_db_id:
            upsert_records(valid_records, real_db_id, tier=1)
        else:
            logger.warning(f"Notion env var {db_id} not set.")
            
    # Drive Sync (if enabled)
    if config.storage.drive and config.storage.drive.enabled:
        if drive_folder:
            try:
                from litintel.storage.drive import sync_to_drive
                logger.info("Syncing to Google Drive...")
                sync_to_drive(
                    valid_records,
                    drive_folder,
                    creds_path,
                    papers_jsonl_file_id=os.environ.get(
                        config.storage.drive.papers_jsonl_file_id_env or ""
                    ),
                    notebooklm_folder_id=os.environ.get(
                        config.storage.drive.notebooklm_folder_id_env or ""
                    ),
                    methods_folder_id=os.environ.get(
                        config.storage.drive.methods_folder_id_env or ""
                    ),
                )
            except Exception as e:
                logger.error(f"Drive sync failed: {e}")
        else:
            logger.warning("GOOGLE_DRIVE_FOLDER_ID not set, skipping Drive sync")

    # Tier C inbox pass (manual-PDF path), executed in the same cron when enabled.
    if (
        config.tier_c
        and config.tier_c.enabled
        and config.tier_c.process_inbox_in_cron
    ):
        inbox_env = config.tier_c.inbox_folder_id_env
        output_env = config.tier_c.output_folder_id_env
        inbox_id = os.environ.get(inbox_env) if inbox_env else None
        output_id = os.environ.get(output_env) if output_env else None

        if not inbox_id or not output_id:
            logger.warning(
                "Tier C [inbox]: skipping (env not set: %s=%s %s=%s)",
                inbox_env, bool(inbox_id), output_env, bool(output_id),
            )
        else:
            try:
                from litintel.storage.drive import get_drive_service
                from litintel.tierc.inbox import process_inbox

                service = get_drive_service(credentials_path=creds_path)
                inbox_records = process_inbox(
                    drive_service=service,
                    inbox_folder_id=inbox_id,
                    notion_index=notion_index,
                    output_folder_id=output_id,
                    engine_model=config.tier_c.model,
                    identity_model=config.tier_c.identity_model,
                )
                logger.info("Tier C [inbox]: processed %d file(s)", len(inbox_records))
            except Exception:
                logger.exception("Tier C [inbox]: failed (continuing)")

    # RAG Corpus Sync (if VERTEX_RAG_CORPUS_NAME is set).
    # The RAG project comes from the corpus name, not GCP_PROJECT_ID -- the
    # corpus lives in a personal project while Gemini runs on the company one.
    corpus_name = os.environ.get("VERTEX_RAG_CORPUS_NAME")
    if corpus_name:
        try:
            from litintel.storage.rag_corpus import upsert_to_rag_corpus
            logger.info("Syncing to Vertex AI RAG corpus...")
            upsert_to_rag_corpus(
                records=valid_records,
                corpus_name=corpus_name,
                min_score=config.rag_agent.min_score,
            )
        except Exception as e:
            logger.error(f"RAG corpus sync failed: {e}")

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
