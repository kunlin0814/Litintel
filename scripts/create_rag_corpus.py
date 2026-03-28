"""One-time script to create a Vertex AI RAG corpus for LitIntel.

Usage:
    python scripts/create_rag_corpus.py

Prerequisites:
    1. gcloud auth application-default login
    2. Vertex AI API enabled on your GCP project
    3. GCP_PROJECT_ID set in .env or environment

Output:
    Prints the corpus resource name to copy into .env as VERTEX_RAG_CORPUS_NAME.
"""

import os
import sys

from dotenv import load_dotenv

load_dotenv()


def main():
    project_id = os.environ.get('GCP_PROJECT_ID')
    if not project_id:
        print('ERROR: GCP_PROJECT_ID not set. Add it to .env or export it.')
        sys.exit(1)

    location = os.environ.get('GCP_LOCATION', 'us-central1')

    print(f'Project:  {project_id}')
    print(f'Location: {location}')
    print()

    try:
        import vertexai
        from vertexai.preview import rag
    except ImportError:
        print('ERROR: google-cloud-aiplatform not installed.')
        print('  pip install google-cloud-aiplatform>=1.49.0')
        sys.exit(1)

    vertexai.init(project=project_id, location=location)

    print('Creating RAG corpus "litintel-papers"...')
    corpus = rag.create_corpus(display_name='litintel-papers')

    print()
    print('=' * 60)
    print('Corpus created successfully!')
    print(f'Resource name: {corpus.name}')
    print()
    print('Add this to your .env:')
    print(f'VERTEX_RAG_CORPUS_NAME={corpus.name}')
    print('=' * 60)


if __name__ == '__main__':
    main()
