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
    df.to_csv(filename, index=False, encoding='utf-8-sig')  # BOM for Excel
    logger.info(f"Saved {len(records)} records to {filename}")


def normalize_text(text) -> str:
    """Normalize Unicode characters for readability.
    
    Replaces curly quotes, fancy dashes, and special spaces with ASCII equivalents.
    Can be imported by other modules (e.g., drive.py).
    """
    if not isinstance(text, str):
        return str(text) if text else ""
    # Replace curly quotes and fancy chars with ASCII using escape sequences
    replacements = {
        '\u2018': "'", '\u2019': "'", '\u201c': '"', '\u201d': '"',
        '\u2013': '-', '\u2014': '-', '\u2026': '...',
        '\u2009': ' ', '\u00a0': ' ',  # thin/non-breaking spaces
        '\u2264': '<=', '\u2265': '>=', '\u00b1': '+/-',
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def save_markdown(records: List[Dict[str, Any]], filename: str):
    """Save records to Markdown format for human review."""
    if not records:
        return
    
    # Uses module-level normalize_text function
    lines = []
    lines.append(f"# Pipeline Output: {len(records)} Papers\n")
    lines.append(f"_Generated: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}_\n")
    lines.append("---\n")
    
    for i, rec in enumerate(records, 1):
        pmid = rec.get('PMID', 'N/A')
        title = normalize_text(rec.get('Title', 'No Title'))
        authors = normalize_text(rec.get('Authors', ''))
        score = rec.get('RelevanceScore', 0)
        why = normalize_text(rec.get('WhyRelevant', ''))
        summary = normalize_text(rec.get('StudySummary', ''))
        findings = normalize_text(rec.get('KeyFindings', ''))
        methods = normalize_text(rec.get('Methods', ''))
        escalation = rec.get('EscalationTriggered', False)
        esc_reason = normalize_text(rec.get('EscalationReason', ''))
        
        lines.append(f"## {i}. [{title}](https://pubmed.ncbi.nlm.nih.gov/{pmid}/)\n")
        lines.append(f"**PMID**: {pmid} | **Score**: {score}")
        if escalation:
            lines.append(f" | !! **Escalated**: {esc_reason[:50]}")
        lines.append("\n\n")
        
        lines.append(f"**Authors**: {authors[:100]}{'...' if len(authors) > 100 else ''}\n\n")
        lines.append(f"**Why Relevant**: {why}\n\n")
        lines.append(f"**Summary**: {summary}\n\n")
        
        if findings:
            lines.append(f"**Key Findings**: {findings}\n\n")
        if methods:
            lines.append(f"**Methods**: {methods}\n\n")
        
        lines.append("---\n")
    
    with open(filename, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    
    logger.info(f"Saved {len(records)} records to {filename}")
