"""Backfill RAG corpus from Notion database.

Reads all pages from your Notion database, extracts paper metadata,
and uploads eligible papers to the Vertex AI RAG Engine corpus.
Skips papers already in the RAG corpus (by PMID dedup).

Usage:
    python scripts/backfill_rag_from_notion.py                 # default settings
    python scripts/backfill_rag_from_notion.py --min-score 80  # custom threshold
    python scripts/backfill_rag_from_notion.py --dry-run       # preview only
"""

import argparse
import logging
import os
import sys
import time

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

import requests

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s: %(message)s',
)
logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------
# Notion helpers
# -----------------------------------------------------------------------

def _extract_text(prop: dict) -> str:
    """Extract plain text from a Notion rich_text or title property."""
    if not prop:
        return ''
    prop_type = prop.get('type', '')
    items = prop.get(prop_type, [])
    if isinstance(items, list):
        return ''.join(item.get('plain_text', '') for item in items)
    return ''


def _extract_number(prop: dict):
    """Extract number from a Notion number property."""
    if not prop:
        return None
    return prop.get('number')


def _extract_select(prop: dict) -> str:
    """Extract name from a Notion select property."""
    if not prop:
        return ''
    sel = prop.get('select')
    if sel:
        return sel.get('name', '')
    return ''


def _extract_multi_select(prop: dict) -> str:
    """Extract semicolon-joined names from a Notion multi_select property."""
    if not prop:
        return ''
    items = prop.get('multi_select', [])
    return '; '.join(item.get('name', '') for item in items)


def _extract_date(prop: dict) -> str:
    """Extract start date from a Notion date property."""
    if not prop:
        return ''
    d = prop.get('date')
    if d:
        return d.get('start', '')
    return ''


def _extract_checkbox(prop: dict) -> bool:
    """Extract value from a Notion checkbox property."""
    if not prop:
        return False
    return prop.get('checkbox', False)


def notion_page_to_record(props: dict) -> dict:
    """Convert a Notion page's properties into a flat dict matching Tier1Record keys."""
    return {
        'Title': _extract_text(props.get('Name', {})),
        'PMID': _extract_text(props.get('PMID', {})),
        'DOI': _extract_text(props.get('DOI', {})),
        'RelevanceScore': _extract_number(props.get('RelevanceScore', {})),
        'WhyRelevant': _extract_text(props.get('WhyRelevant', {})),
        'StudySummary': _extract_text(props.get('StudySummary', {})),
        'PaperRole': _extract_text(props.get('PaperRole', {})),
        'Methods': _extract_text(props.get('Methods', {})),
        'KeyFindings': _extract_text(props.get('KeyFindings', {})),
        'Abstract': _extract_text(props.get('Abstract', {})),
        'Authors': _extract_text(props.get('Authors', {})),
        'Journal': _extract_select(props.get('Journal', {})),
        'PubDate': _extract_date(props.get('PubDate', {})),
        'Theme': _extract_multi_select(props.get('Theme', {})),
        'DataTypes': _extract_multi_select(props.get('DataTypes', {})),
        'Group': _extract_text(props.get('Group', {})),
        'CellIdentitySignatures': _extract_text(props.get('CellIdentitySignatures', {})),
        'PerturbationsUsed': _extract_text(props.get('PerturbationsUsed', {})),
        'GEO_Validated': _extract_text(props.get('GEO_Validated', {})),
        'SRA_Validated': _extract_text(props.get('SRA_Validated', {})),
        'MeSH_Major': _extract_text(props.get('MeSH_Major', {})),
        'MeSH_Terms': _extract_text(props.get('MeSH_Terms', {})),
        'AI_EvidenceLevel': _extract_select(props.get('AI_EvidenceLevel', {})),
        'WhyYouMightCare': _extract_text(props.get('WhyYouMightCare', {})),
        'FullTextUsed': _extract_checkbox(props.get('FullTextUsed', {})),
        'PipelineConfidence': _extract_select(props.get('PipelineConfidence', {})
                              ) or _extract_text(props.get('PipelineConfidence', {})),
    }


def fetch_all_notion_pages(database_id: str, token: str) -> list:
    """Paginate through entire Notion database and return all pages as records."""
    headers = {
        'Authorization': f'Bearer {token}',
        'Notion-Version': '2022-06-28',
        'Content-Type': 'application/json',
    }
    url = f'https://api.notion.com/v1/databases/{database_id}/query'
    all_records = []
    payload = {}
    has_more = True

    while has_more:
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        for page in data.get('results', []):
            props = page.get('properties', {})
            rec = notion_page_to_record(props)
            all_records.append(rec)

        has_more = data.get('has_more', False)
        next_cursor = data.get('next_cursor')
        if next_cursor:
            payload['start_cursor'] = next_cursor

        # Notion rate limit: ~3 requests/sec
        time.sleep(0.35)

    return all_records


# -----------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Backfill Vertex AI RAG corpus from Notion database'
    )
    parser.add_argument(
        '--min-score',
        type=int,
        default=80,
        help='Minimum RelevanceScore for RAG inclusion (default: 80)',
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview what would be uploaded without actually uploading',
    )
    args = parser.parse_args()

    # Validate env
    notion_token = os.environ.get('NOTION_TOKEN')
    notion_db_id = os.environ.get('NOTION_DB_ID')
    corpus_name = os.environ.get('VERTEX_RAG_CORPUS_NAME')
    project_id = os.environ.get('GCP_PROJECT_ID')
    location = os.environ.get('GCP_LOCATION', 'us-east5')

    missing = []
    if not notion_token:
        missing.append('NOTION_TOKEN')
    if not notion_db_id:
        missing.append('NOTION_DB_ID')
    if not corpus_name:
        missing.append('VERTEX_RAG_CORPUS_NAME')
    if not project_id:
        missing.append('GCP_PROJECT_ID')
    if missing:
        print(f'ERROR: Missing env vars: {", ".join(missing)}')
        sys.exit(1)

    # 1. Fetch all pages from Notion
    logger.info('Fetching all pages from Notion database %s ...', notion_db_id)
    records = fetch_all_notion_pages(notion_db_id, notion_token)
    logger.info('Fetched %d total pages from Notion', len(records))

    # 2. Filter by score
    eligible = []
    for rec in records:
        pmid = rec.get('PMID')
        score = rec.get('RelevanceScore')
        if not pmid:
            continue
        if score is None or score < args.min_score:
            continue
        eligible.append(rec)

    logger.info(
        'RAG eligible: %d papers (score >= %d) out of %d total',
        len(eligible), args.min_score, len(records),
    )

    if args.dry_run:
        logger.info('=== DRY RUN -- no uploads ===')
        for rec in eligible:
            logger.info(
                '  Would upload: PMID %s (score=%s) -- %s',
                rec.get('PMID'),
                rec.get('RelevanceScore'),
                (rec.get('Title', '')[:60] + '...') if len(rec.get('Title', '')) > 60 else rec.get('Title', ''),
            )
        return

    # 3. Upsert to RAG corpus (reuse existing function)
    from litintel.storage.rag_corpus import upsert_to_rag_corpus

    upsert_to_rag_corpus(
        records=eligible,
        corpus_name=corpus_name,
        project_id=project_id,
        location=location,
        min_score=args.min_score,
    )

    logger.info('Backfill from Notion complete.')


if __name__ == '__main__':
    main()
