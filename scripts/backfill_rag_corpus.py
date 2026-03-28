"""Backfill existing papers from CSV into the Vertex AI RAG corpus.

Reads papers_tier1.csv, filters to RelevanceScore >= 70 (configurable),
and uploads them to the RAG corpus using the same upsert logic as the
pipeline. Existing PMIDs are skipped (incremental).

Usage:
    python scripts/backfill_rag_corpus.py                    # upload eligible papers
    python scripts/backfill_rag_corpus.py --dry-run          # preview only
    python scripts/backfill_rag_corpus.py --min-score 80     # custom threshold
    python scripts/backfill_rag_corpus.py --force-update     # re-upload existing
    python scripts/backfill_rag_corpus.py --csv path/to.csv  # custom CSV path

Prerequisites:
    1. gcloud auth application-default login
    2. VERTEX_RAG_CORPUS_NAME and GCP_PROJECT_ID in .env
"""

import argparse
import csv
import logging
import os
import sys

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s: %(message)s',
)
logger = logging.getLogger(__name__)


def load_csv_records(csv_path: str) -> list:
    """Load records from CSV file."""
    records = []
    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Convert RelevanceScore to int
            try:
                row['RelevanceScore'] = int(row.get('RelevanceScore', 0))
            except (ValueError, TypeError):
                row['RelevanceScore'] = 0
            records.append(row)
    return records


def main():
    parser = argparse.ArgumentParser(
        description='Backfill existing papers into Vertex AI RAG corpus'
    )
    parser.add_argument(
        '--csv',
        default='papers_tier1.csv',
        help='Path to CSV file (default: papers_tier1.csv)',
    )
    parser.add_argument(
        '--min-score',
        type=int,
        default=80,
        help='Minimum RelevanceScore for RAG inclusion (default: 70)',
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview eligible papers without uploading',
    )
    parser.add_argument(
        '--force-update',
        action='store_true',
        help='Re-upload papers that already exist in the corpus',
    )
    args = parser.parse_args()

    # Validate env
    corpus_name = os.environ.get('VERTEX_RAG_CORPUS_NAME')
    project_id = os.environ.get('GCP_PROJECT_ID')
    location = os.environ.get('GCP_LOCATION', 'us-central1')

    if not corpus_name:
        print('ERROR: VERTEX_RAG_CORPUS_NAME not set.')
        print('Run scripts/create_rag_corpus.py first, then add to .env.')
        sys.exit(1)

    if not project_id:
        print('ERROR: GCP_PROJECT_ID not set in .env.')
        sys.exit(1)

    # Load CSV
    if not os.path.exists(args.csv):
        print(f'ERROR: CSV file not found: {args.csv}')
        sys.exit(1)

    logger.info('Loading records from %s ...', args.csv)
    records = load_csv_records(args.csv)
    logger.info('Loaded %d total records', len(records))

    # Filter by score
    eligible = [r for r in records if r['RelevanceScore'] >= args.min_score]
    logger.info(
        'Eligible for RAG (score >= %d): %d / %d',
        args.min_score,
        len(eligible),
        len(records),
    )

    if not eligible:
        logger.info('No eligible records. Nothing to do.')
        return

    if args.dry_run:
        print()
        print(f'DRY RUN -- {len(eligible)} papers would be uploaded:')
        print('-' * 60)
        for r in eligible[:20]:
            pmid = r.get('PMID', '?')
            score = r.get('RelevanceScore', 0)
            title = r.get('Title', '')[:60]
            print(f'  PMID {pmid:>10} | Score {score:>3} | {title}')
        if len(eligible) > 20:
            print(f'  ... and {len(eligible) - 20} more')
        print()
        print('Re-run without --dry-run to upload.')
        return

    # Upload
    from litintel.storage.rag_corpus import upsert_to_rag_corpus

    logger.info('Starting RAG corpus backfill...')
    logger.info('Corpus:  %s', corpus_name)
    logger.info('Project: %s', project_id)
    logger.info('Location:%s', location)

    upsert_to_rag_corpus(
        records=eligible,
        corpus_name=corpus_name,
        project_id=project_id,
        location=location,
        min_score=args.min_score,
        force_update=args.force_update,
    )

    logger.info('Backfill complete.')


if __name__ == '__main__':
    main()
