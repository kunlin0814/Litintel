"""LitIntel RAG Agent -- ADK agent with Vertex AI RAG retrieval.

This module defines the ADK agent that answers natural language research
questions against the LitIntel paper corpus using Vertex AI RAG Engine.

Usage (ADK web UI):
    cd agent && adk web

Usage (CLI -- see cli.py):
    python agent/cli.py "What spatial ATAC papers cover CTCF in prostate cancer?"
"""

import os

from google.adk.agents import Agent
from google.adk.tools.retrieval.vertex_ai_rag_retrieval import VertexAiRagRetrieval

CORPUS_NAME = os.environ.get('VERTEX_RAG_CORPUS_NAME', '')
PROJECT_ID = os.environ.get('GCP_PROJECT_ID', '')
LOCATION = os.environ.get('GCP_LOCATION', 'us-central1')

SYSTEM_INSTRUCTION = """\
You are LitIntel Assistant, a computational biology research agent.
You answer questions about prostate cancer, spatial omics, single-cell
genomics, and related computational methods by retrieving information
from an indexed corpus of peer-reviewed papers.

Behavior rules:
- Always cite the PMID when referencing a paper.
- If the corpus does not contain relevant papers, say so explicitly.
- Summarize key findings, methods, and data types from retrieved papers.
- When asked about datasets, include GEO/SRA accession IDs if available.
- Be concise and technical. Avoid filler.
- Use ASCII only. No emoji or non-ASCII characters.
"""

litintel_retrieval = VertexAiRagRetrieval(
    name='litintel_paper_search',
    description=(
        'Searches the LitIntel indexed literature corpus of prostate cancer '
        'and spatial omics papers. Use this tool to find papers by topic, '
        'method, gene, cell type, dataset, or any research question.'
    ),
    rag_corpora=[CORPUS_NAME],
    similarity_top_k=10,
    vector_distance_threshold=0.5,
)

root_agent = Agent(
    name='litintel_agent',
    model='gemini-2.5-flash',
    description='Research assistant for prostate cancer and spatial omics literature',
    instruction=SYSTEM_INSTRUCTION,
    tools=[litintel_retrieval],
)
