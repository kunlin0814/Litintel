"""LitIntel RAG Agent -- CLI interface.

A command-line tool to query the LitIntel paper corpus using natural
language. Uses the ADK agent with Vertex AI RAG Engine retrieval.

Usage:
    python agent/cli.py "What spatial ATAC papers cover CTCF in prostate cancer?"
    python agent/cli.py --interactive

Prerequisites:
    1. gcloud auth application-default login
    2. VERTEX_RAG_CORPUS_NAME and GCP_PROJECT_ID set in .env
    3. pip install google-cloud-aiplatform>=1.49.0 google-adk>=0.3.0
"""

import argparse
import asyncio
import os
import sys

from dotenv import load_dotenv

# Load .env from project root
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from agent import root_agent


APP_NAME = 'litintel_rag'
USER_ID = 'cli_user'


async def run_query(query: str, runner: Runner, session_id: str) -> str:
    """Send a query to the agent and return the final text response."""
    content = types.Content(
        role='user',
        parts=[types.Part.from_text(text=query)],
    )

    final_text = ''
    async for event in runner.run_async(
        user_id=USER_ID,
        session_id=session_id,
        new_message=content,
    ):
        if event.is_final_response():
            for part in event.content.parts:
                if part.text:
                    final_text += part.text
    return final_text


async def interactive_loop(runner: Runner, session_id: str):
    """Run an interactive REPL loop."""
    print()
    print('LitIntel RAG Agent -- Interactive Mode')
    print('Type your research question, or "quit" to exit.')
    print('-' * 50)

    while True:
        try:
            query = input('\n> ').strip()
        except (EOFError, KeyboardInterrupt):
            print('\nExiting.')
            break

        if not query:
            continue
        if query.lower() in ('quit', 'exit', 'q'):
            print('Exiting.')
            break

        response = await run_query(query, runner, session_id)
        print()
        print(response)


async def main():
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
    args = parser.parse_args()

    # Validate env
    corpus_name = os.environ.get('VERTEX_RAG_CORPUS_NAME')
    if not corpus_name:
        print('ERROR: VERTEX_RAG_CORPUS_NAME not set.')
        print('Run scripts/create_rag_corpus.py first, then add to .env.')
        sys.exit(1)

    project_id = os.environ.get('GCP_PROJECT_ID')
    if not project_id:
        print('ERROR: GCP_PROJECT_ID not set in .env.')
        sys.exit(1)

    # Create runner
    session_service = InMemorySessionService()
    runner = Runner(
        agent=root_agent,
        app_name=APP_NAME,
        session_service=session_service,
    )

    # Create session
    session = await session_service.create_session(
        app_name=APP_NAME,
        user_id=USER_ID,
    )

    if args.interactive or args.query is None:
        await interactive_loop(runner, session.id)
    else:
        response = await run_query(args.query, runner, session.id)
        print(response)


if __name__ == '__main__':
    asyncio.run(main())
