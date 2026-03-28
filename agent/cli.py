"""LitIntel RAG Agent -- CLI interface.

Two-step approach:
  1. Retrieve relevant chunks from Vertex AI RAG Engine (requires gcloud auth)
  2. Generate answer with Gemini via Developer API (uses GOOGLE_API_KEY)

This lets us use gemini-3-flash-preview (available on Developer API)
while still querying the Vertex AI RAG corpus.

Usage:
    python agent/cli.py "What spatial ATAC papers cover CTCF in prostate cancer?"
    python agent/cli.py --interactive
    python agent/cli.py --thinking HIGH "summarize spatial omics papers"

Prerequisites:
    1. gcloud auth application-default login
    2. VERTEX_RAG_CORPUS_NAME, GCP_PROJECT_ID, GOOGLE_API_KEY set in .env
    3. pip install google-cloud-aiplatform>=1.49.0 google-genai
"""

import argparse
import os
import sys

from dotenv import load_dotenv

# Load .env from project root
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

from google import genai
from google.genai import types
from vertexai.preview import rag

# -----------------------------------------------------------------------
# Config from environment
# -----------------------------------------------------------------------
PROJECT_ID = os.environ.get('GCP_PROJECT_ID', '')
LOCATION = os.environ.get('GCP_LOCATION', 'us-east5')
CORPUS_NAME = os.environ.get('VERTEX_RAG_CORPUS_NAME', '')
MODEL = os.environ.get('RAG_AGENT_MODEL', 'gemini-3-flash-preview')

SYSTEM_INSTRUCTION = """\
You are LitIntel Assistant, a computational biology research agent.
You answer questions about prostate cancer, spatial omics, single-cell
genomics, and related computational methods by retrieving information
from an indexed corpus of peer-reviewed papers.

Below you will receive CONTEXT extracted from indexed papers. Use ONLY
this context to answer the user's question.

Behavior rules:
- Always cite the PMID when referencing a paper.
- If the context does not contain relevant papers, say so explicitly.
- Summarize key findings, methods, and data types from retrieved papers.
- When asked about datasets, include GEO/SRA accession IDs if available.
- Be concise and technical. Avoid filler.
- Use ASCII only. No emoji or non-ASCII characters.
"""


def retrieve_chunks(question: str, top_k: int = 10) -> str:
    """Retrieve relevant chunks from Vertex AI RAG corpus."""
    import vertexai
    vertexai.init(project=PROJECT_ID, location=LOCATION)

    response = rag.retrieval_query(
        rag_resources=[
            rag.RagResource(rag_corpus=CORPUS_NAME)
        ],
        text=question,
        similarity_top_k=top_k,
        vector_distance_threshold=0.5,
    )

    # Format retrieved chunks into context string
    chunks = []
    for ctx in response.contexts.contexts:
        source = getattr(ctx, 'source_display_name', 'unknown')
        text = ctx.text
        chunks.append(f"--- Source: {source} ---\n{text}")

    if not chunks:
        return "(No relevant documents found in the corpus.)"

    return "\n\n".join(chunks)


def query(client, question: str, thinking_level: str = 'LOW', top_k: int = 10) -> str:
    """Retrieve context from RAG, then generate answer with Gemini."""
    # Step 1: Retrieve from Vertex AI RAG
    context = retrieve_chunks(question, top_k=top_k)

    # Step 2: Build prompt with retrieved context
    augmented_prompt = f"CONTEXT:\n{context}\n\nQUESTION:\n{question}"

    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_INSTRUCTION,
    )

    # Add thinking config if requested
    if thinking_level and thinking_level.upper() != 'NONE':
        config.thinking_config = types.ThinkingConfig(
            include_thoughts=True,
            thinking_level=thinking_level.upper(),
        )

    response = client.models.generate_content(
        model=MODEL,
        contents=augmented_prompt,
        config=config,
    )
    return response.text


def interactive_loop(client, thinking_level: str, top_k: int):
    """Run an interactive REPL loop."""
    print()
    print(f'LitIntel RAG Agent (model={MODEL}, thinking={thinking_level})')
    print('Type your research question, or "quit" to exit.')
    print('-' * 50)

    while True:
        try:
            question = input('\n> ').strip()
        except (EOFError, KeyboardInterrupt):
            print('\nExiting.')
            break

        if not question:
            continue
        if question.lower() in ('quit', 'exit', 'q'):
            print('Exiting.')
            break

        try:
            answer = query(client, question, thinking_level, top_k)
            print()
            print(answer)
        except Exception as e:
            print(f'\nERROR: {e}')


def main():
    parser = argparse.ArgumentParser(
        description='Query the LitIntel paper corpus with natural language'
    )
    parser.add_argument(
        'query',
        nargs='?',
        default=None,
        help='Research question to answer',
    )
    parser.add_argument(
        '--interactive', '-i',
        action='store_true',
        help='Run in interactive REPL mode',
    )
    parser.add_argument(
        '--thinking',
        default='LOW',
        choices=['NONE', 'LOW', 'MEDIUM', 'HIGH'],
        help='Thinking level for reasoning (default: LOW)',
    )
    parser.add_argument(
        '--top-k',
        type=int,
        default=10,
        help='Number of RAG chunks to retrieve (default: 10)',
    )
    args = parser.parse_args()

    # Validate env
    if not CORPUS_NAME:
        print('ERROR: VERTEX_RAG_CORPUS_NAME not set.')
        print('Run scripts/create_rag_corpus.py first, then add to .env.')
        sys.exit(1)

    if not PROJECT_ID:
        print('ERROR: GCP_PROJECT_ID not set in .env.')
        sys.exit(1)

    api_key = os.environ.get('GOOGLE_API_KEY')
    if not api_key:
        print('ERROR: GOOGLE_API_KEY not set in .env.')
        sys.exit(1)

    # Initialize Gemini client via Developer API (has gemini-3 access)
    client = genai.Client(api_key=api_key)

    if args.interactive or args.query is None:
        interactive_loop(client, args.thinking, args.top_k)
    else:
        answer = query(client, args.query, args.thinking, args.top_k)
        print(answer)


if __name__ == '__main__':
    main()
