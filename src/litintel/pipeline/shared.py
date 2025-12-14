import logging
import pandas as pd
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

def deduplicate_records(records: List[Dict[str, Any]], keys: List[str] = ["DOI", "PMID"]) -> List[Dict[str, Any]]:
    """Deduplicates records based on priority keys (DOI > PMID)."""
    if not records:
        return []
    
    df = pd.DataFrame(records)
    
    # Ensure keys exist
    for k in keys:
        if k not in df.columns:
            df[k] = ""
            
    # Remove duplicates based on DOI first (if present)
    initial_len = len(df)
    
    # Helper to deduce uniqueness
    # We can just drop duplicates on subset.
    # But DOI might be empty.
    
    # Strategy: 
    # 1. Separate records with DOI from those without.
    # 2. Dedup DOI-records by DOI.
    # 3. Dedup remaining by PMID.
    # 4. Merge but check if PMID of remaining was already in DOI-records.

    # Simpler Pandas approach usually suffices for this scale:
    # Coalesce keys? No, strict priority.
    
    # 1. Dedup by DOI (ignoring empty DOIs)
    df_doi = df[df["DOI"].astype(bool) & (df["DOI"] != "")]
    df_no_doi = df[~(df["DOI"].astype(bool) & (df["DOI"] != ""))]
    
    df_doi_clean = df_doi.drop_duplicates(subset=["DOI"], keep="first")
    
    # 2. Dedup by PMID (ignoring empty PMIDs)
    # We also need to filter out PMIDs that are in df_doi_clean to avoid double counting
    existing_pmids = set(df_doi_clean["PMID"].tolist())
    
    # Filter df_no_doi to remove records where PMID is already covered
    df_no_doi_filtered = df_no_doi[~df_no_doi["PMID"].isin(existing_pmids)]
    
    df_pmid_clean = df_no_doi_filtered.drop_duplicates(subset=["PMID"], keep="first")
    
    # Combine
    final_df = pd.concat([df_doi_clean, df_pmid_clean])
    
    logger.info(f"Deduplication: {initial_len} -> {len(final_df)} records.")
    return final_df.to_dict(orient="records")

def save_csv(records: List[Dict[str, Any]], filename: str):
    if not records:
        return
    df = pd.DataFrame(records)
    df.to_csv(filename, index=False)
    logger.info(f"Saved {len(records)} records to {filename}")
