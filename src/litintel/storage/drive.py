"""
Google Drive sync module for uploading literature analysis to Drive.

Supports batched markdown files and JSONL exports for NotebookLM workflows.
"""

import os
import io
import json
import datetime
import logging
import math
from typing import Optional, List, Dict, Any

from google.oauth2.credentials import Credentials
from google.oauth2 import service_account
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload
import google.auth

from litintel.pipeline.shared import normalize_text

logger = logging.getLogger(__name__)

# Define scopes
SCOPES = ['https://www.googleapis.com/auth/drive.file']


def get_drive_service(credentials_path: Optional[str] = None):
    """
    Authenticate and return the Drive service.
    
    Supports:
    1. Service Account (if GOOGLE_CREDENTIALS_PATH matches a service account JSON)
    2. OAuth User Flow (if GOOGLE_CLIENT_SECRETS_PATH is set)
    3. Application Default Credentials (ADC) as fallback
    
    Args:
        credentials_path: Optional path to service account JSON OR client secrets JSON
        
    Returns:
        Google Drive API service
    """
    creds = None
    
    # 1. Try Service Account (Explicit Path)
    if credentials_path and os.path.exists(credentials_path):
        # Naive check: does it look like a service account?
        try:
            with open(credentials_path) as f:
                data = json.load(f)
                if data.get('type') == 'service_account':
                     creds = service_account.Credentials.from_service_account_file(
                        credentials_path, scopes=SCOPES
                    )
                     logger.info("Using Service Account")
        except Exception as e:
            logger.warning(f"Service Account check failed: {e}")

    # 2. Try User OAuth Flow (Client Secrets)
    client_secrets = os.environ.get("GOOGLE_CLIENT_SECRETS_PATH")
    if not creds and client_secrets and os.path.exists(client_secrets):
        token_path = 'token.json'
        
        # Load cached token
        if os.path.exists(token_path):
            creds = Credentials.from_authorized_user_file(token_path, SCOPES)
            
        # Refresh or Login
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception:
                    creds = None
            
            if not creds:
                flow = InstalledAppFlow.from_client_secrets_file(client_secrets, SCOPES)
                creds = flow.run_local_server(port=0)
            
            # Save token
            with open(token_path, 'w') as token:
                token.write(creds.to_json())
        
        logger.info("Using User OAuth Credentials")

    # 3. Try Application Default Credentials (ADC)
    if not creds:
        try:
            creds, project = google.auth.default(scopes=SCOPES)
            logger.info("Using Application Default Credentials (ADC)")
        except Exception as e:
            logger.warning(f"ADC load failed: {e}")
    
    if not creds:
        raise ValueError(
            "No valid credentials found. Please set GOOGLE_CLIENT_SECRETS_PATH "
            "(for personal accounts) or GOOGLE_CREDENTIALS_PATH (for service accounts)."
        )
    
    return build('drive', 'v3', credentials=creds)


def ensure_folder_exists(service, folder_name: str, parent_id: str) -> str:
    """Check if folder exists in parent; create if not. Return folder ID."""
    query = (
        f"name = '{folder_name}' and '{parent_id}' in parents "
        f"and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    )
    results = service.files().list(q=query, fields="files(id, name)", includeItemsFromAllDrives=True, supportsAllDrives=True).execute()
    files = results.get('files', [])
    
    if files:
        return files[0]['id']
    else:
        file_metadata = {
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder',
            'parents': [parent_id]
        }
        file = service.files().create(body=file_metadata, fields='id', supportsAllDrives=True).execute()
        return file.get('id')


def append_text_to_file(service, folder_id: str, file_name: str, new_text: str) -> str:
    """
    Append text to a markdown file in Drive (Download -> Append -> Upload).
    
    Args:
        service: Drive service
        folder_id: Parent folder ID
        file_name: Filename to append to
        new_text: Text to append
        
    Returns:
        File ID
    """
    if not new_text:
        return ""
    
    query = f"name = '{file_name}' and '{folder_id}' in parents and trashed = false"
    results = service.files().list(q=query, fields="files(id)", includeItemsFromAllDrives=True, supportsAllDrives=True).execute()
    files = results.get('files', [])
    
    existing_content = ""
    file_id = None
    
    if files:
        file_id = files[0]['id']
        # Download existing
        request = service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        try:
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while done is False:
                status, done = downloader.next_chunk()
            existing_content = fh.getvalue().decode('utf-8')
        except Exception:
            existing_content = ""
    
    # Check if we need a separator
    if existing_content and not existing_content.endswith("\n\n"):
        full_content = existing_content + "\n\n" + new_text
    elif existing_content:
        full_content = existing_content + new_text
    else:
        full_content = new_text
    
    media = MediaIoBaseUpload(
        io.BytesIO(full_content.encode('utf-8')),
        mimetype='text/plain',
        resumable=True
    )
    
    if file_id:
        service.files().update(
            fileId=file_id,
            media_body=media,
            fields='id',
            supportsAllDrives=True
        ).execute()
        return file_id
    else:
        file_metadata = {
            'name': file_name,
            'parents': [folder_id],
            'mimeType': 'text/plain'
        }
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id',
            supportsAllDrives=True
        ).execute()
        return file.get('id')


def append_to_jsonl(service, folder_id: str, file_name: str, new_records: List[Dict[str, Any]]) -> str:
    """
    Append JSONL records to a file in Drive.
    
    Note: Google Drive API doesn't support 'append' operation directly.
    We must download, append, and re-upload.
    
    Args:
        service: Drive service
        folder_id: Parent folder ID
        file_name: JSONL filename
        new_records: List of dict records to append
        
    Returns:
        File ID
    """
    if not new_records:
        return ""
    
    query = f"name = '{file_name}' and '{folder_id}' in parents and trashed = false"
    results = service.files().list(q=query, fields="files(id)", includeItemsFromAllDrives=True, supportsAllDrives=True).execute()
    files = results.get('files', [])
    
    existing_content = ""
    file_id = None
    
    if files:
        file_id = files[0]['id']
        # Download existing
        request = service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while done is False:
            status, done = downloader.next_chunk()
        existing_content = fh.getvalue().decode('utf-8')
    
    # Format new records
    def json_serial(obj):
        """JSON serializer for datetime objects"""
        if isinstance(obj, (datetime.datetime, datetime.date)):
            return obj.isoformat()
        raise TypeError(f"Type {type(obj)} not serializable")
    
    new_lines = "\n".join([json.dumps(r, default=json_serial) for r in new_records])
    if existing_content and not existing_content.endswith("\n"):
        full_content = existing_content + "\n" + new_lines
    else:
        full_content = existing_content + new_lines
    
    media = MediaIoBaseUpload(
        io.BytesIO(full_content.encode('utf-8')),
        mimetype='application/json',
        resumable=True
    )
    
    if file_id:
        service.files().update(
            fileId=file_id,
            media_body=media,
            fields='id',
            supportsAllDrives=True
        ).execute()
        return file_id
    else:
        file_metadata = {
            'name': file_name,
            'parents': [folder_id],
            'mimeType': 'application/json'
        }
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id',
            supportsAllDrives=True
        ).execute()
        return file.get('id')


def format_markdown_entry(rec: Dict[str, Any]) -> str:
    """
    Format a record into a markdown entry.
    
    Args:
        rec: Record dictionary
        
    Returns:
        Formatted markdown string
    """
    lines = []
    lines.append("---")
    lines.append(f"## PMID: {rec.get('PMID')} -- {rec.get('Journal', 'Unknown')} ({rec.get('Year', 'N/A')})")
    lines.append(f"**Title**: {normalize_text(rec.get('Title', 'Untitled'))}")
    lines.append(f"**Authors**: {normalize_text(rec.get('Authors', ''))}")
    lines.append(f"**Published**: {rec.get('PubDate', rec.get('Year', 'N/A'))}")
    lines.append(f"**Group**: {normalize_text(rec.get('Group', ''))}")
    lines.append(f"**RelevanceScore**: {rec.get('RelevanceScore')}")
    lines.append("")
    lines.append(f"**PaperRole**: {normalize_text(rec.get('PaperRole', ''))}")
    lines.append(f"**Theme**: {normalize_text(rec.get('Theme', ''))}")
    lines.append("")
    
    # GEO/SRA Data
    if rec.get("GEO_Validated") or rec.get("SRA_Validated"):
        lines.append("### Data Accessions")
        if rec.get("GEO_Validated"):
            lines.append(f"**GEO (Validated)**: {rec['GEO_Validated']}")
        if rec.get("SRA_Validated"):
            lines.append(f"**SRA (Validated)**: {rec['SRA_Validated']}")
        lines.append("")
    
    lines.append("### WhyRelevant")
    lines.append(normalize_text(rec.get("WhyRelevant", "")))
    lines.append("")
    lines.append("### StudySummary")
    lines.append(normalize_text(rec.get("StudySummary", "")))
    lines.append("")
    lines.append("### Methods")
    methods = normalize_text(rec.get("Methods", ""))
    if ";" in methods:
        for m in methods.split(";"):
            if m.strip():
                lines.append(f"- {m.strip()}")
    elif methods:
        lines.append(f"- {methods}")
    lines.append("")
    lines.append("### KeyFindings")
    findings = normalize_text(rec.get("KeyFindings", ""))
    if ";" in findings:
        for f in findings.split(";"):
            if f.strip():
                lines.append(f"- {f.strip()}")
    else:
        lines.append(findings)
    
    return "\n".join(lines)


def format_comp_methods_block(rec: Dict[str, Any]) -> str:
    """
    Format a computational methods block for quarterly append file.
    
    Each paper contributes one bounded block for NotebookLM/AI consumption.
    Only called for full-text papers with comp_methods data.
    
    Args:
        rec: Record dictionary with comp_methods field
        
    Returns:
        Formatted markdown block with delimiter
    """
    comp = rec.get("comp_methods") or {}
    if isinstance(comp, str):
        return ""
    
    pmid = rec.get("PMID", "")
    year = rec.get("Year", "")
    journal = rec.get("Journal", "")
    
    lines = []
    lines.append(f"## PMID: {pmid} | {year} | {journal}")
    lines.append("")
    lines.append(f"**Title:** {rec.get('Title', '')}")
    lines.append(f"**Lab / Corresponding:** {rec.get('Group', '')}")
    
    # Technologies from existing Methods field
    methods_str = rec.get("Methods", "")
    if methods_str:
        lines.append(f"**Technologies:** {methods_str}")
    lines.append("")
    
    # Summary
    summary = comp.get("summary_2to3_sentences", "")
    if summary:
        lines.append("### Summary")
        lines.append(summary)
        lines.append("")
    
    # Analysis Blocks (new structure)
    analyses = comp.get("analyses", [])
    if analyses:
        for i, analysis in enumerate(analyses, 1):
            analysis_name = analysis.get("analysis_name", f"Analysis {i}")
            purpose = analysis.get("purpose", "")
            steps = analysis.get("steps", [])
            
            lines.append(f"### {analysis_name}")
            if purpose:
                lines.append(f"**Purpose:** {purpose}")
            lines.append("")
            
            if steps:
                lines.append("| Step | Tool | Rationale |")
                lines.append("|------|------|-----------|")
                for s in steps[:6]:  # Max 6 steps per block
                    step_name = s.get("step", "")
                    tool = s.get("tool", "")
                    rationale = s.get("rationale", "")
                    lines.append(f"| {step_name} | {tool} | {rationale} |")
                lines.append("")
    
    # Fallback: Legacy workflow format (backward compatibility)
    elif comp.get("workflow"):
        lines.append("### Computational Workflow")
        for step in comp.get("workflow", [])[:10]:
            step_name = step.get("step", "")
            tool = step.get("tool", "")
            purpose = step.get("purpose", step.get("rationale", ""))
            lines.append(f"- **{step_name}** ({tool}): {purpose}")
        lines.append("")
    
    # Stats/Models (kept)
    stats = comp.get("stats_models", [])
    if stats:
        lines.append("### Statistical Models")
        for s in stats[:5]:
            lines.append(f"- {s}")
        lines.append("")
    
    # Tags
    tags = comp.get("tags", [])
    if tags:
        lines.append(f"**Tags:** {', '.join(tags)}")
        lines.append("")
    
    # Delimiter
    lines.append("---")
    
    return "\n".join(lines)


def write_methods_card(
    service,
    methods_folder_id: str,
    rec: Dict[str, Any]
) -> str:
    """
    Write a per-paper computational methods card to Drive.
    
    File: MethodsCards/{PMID}_{slug}.md
    
    Args:
        service: Drive service
        methods_folder_id: ID of MethodsCards folder
        rec: Record dictionary
        
    Returns:
        Drive file ID or web view link
    """
    pmid = rec.get("PMID", "unknown")
    title = rec.get("Title", "")
    # Create slug from title (first 30 chars, alphanumeric only)
    slug = "".join(c if c.isalnum() else "_" for c in title[:30]).strip("_").lower()
    filename = f"{pmid}_{slug}.md"
    
    content = format_methods_card(rec)
    if not content:
        return ""
    
    # Upload to Drive
    media = MediaIoBaseUpload(
        io.BytesIO(content.encode('utf-8')),
        mimetype='text/plain',
        resumable=True
    )
    
    file_metadata = {
        'name': filename,
        'parents': [methods_folder_id],
        'mimeType': 'text/plain'
    }
    
    try:
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, webViewLink',
            supportsAllDrives=True
        ).execute()
        logger.info(f"Created MethodsCard: {filename}")
        return file.get('webViewLink', file.get('id', ''))
    except Exception as e:
        logger.error(f"Failed to create MethodsCard {filename}: {e}")
        return ""


def update_methods_index(
    service,
    corpus_folder_id: str,
    records: List[Dict[str, Any]]
) -> None:
    """
    Update aggregate methods index file for the quarter.
    
    File: Computational_Methods_Index_{YYYY}_Q{Q}.md
    
    Args:
        service: Drive service
        corpus_folder_id: ID of NotebookLM_Corpus folder
        records: List of records with comp_methods
    """
    current_date = datetime.datetime.now()
    year = current_date.year
    quarter = math.ceil(current_date.month / 3)
    filename = f"Computational_Methods_Index_{year}_Q{quarter}.md"
    
    # Filter to records with comp_methods
    methods_records = [r for r in records if r.get("comp_methods") and r.get("FullTextUsed")]
    if not methods_records:
        return
    
    # Sort by reuse score desc, then relevance desc
    sorted_records = sorted(
        methods_records,
        key=lambda x: (
            (x.get("comp_methods") or {}).get("reuse_score_0to5", 0),
            x.get("RelevanceScore", 0)
        ),
        reverse=True
    )
    
    # Build index content
    lines = []
    lines.append(f"# Computational Methods Index -- {year} Q{quarter}")
    lines.append("")
    lines.append(f"*Last updated: {current_date.strftime('%Y-%m-%d %H:%M')}*")
    lines.append("")
    lines.append("| Title | PMID | Reuse Score | Tags | Summary |")
    lines.append("|-------|------|-------------|------|---------|")
    
    for rec in sorted_records:
        comp = rec.get("comp_methods") or {}
        title = rec.get("Title", "")[:50] + ("..." if len(rec.get("Title", "")) > 50 else "")
        pmid = rec.get("PMID", "")
        score = comp.get("reuse_score_0to5", 0)
        tags = ", ".join(comp.get("tags", [])[:3])
        summary = comp.get("summary_2to3_sentences", "")[:80] + ("..." if len(comp.get("summary_2to3_sentences", "")) > 80 else "")
        
        lines.append(f"| {title} | {pmid} | {score}/5 | {tags} | {summary} |")
    
    new_content = "\n".join(lines)
    
    try:
        append_text_to_file(service, corpus_folder_id, filename, new_content)
        logger.info(f"Updated methods index: {filename} with {len(sorted_records)} entries")
    except Exception as e:
        logger.error(f"Failed to update methods index: {e}")


def sync_to_drive(records: List[Dict[str, Any]], folder_id: str, credentials_path: Optional[str] = None) -> None:
    """
    Sync records to Google Drive with batched markdown + JSONL strategy.
    
    Creates:
    - papers.jsonl - machine-readable log
    - HighConfidence_Analysis.md - papers with score >= 90
    - Quarterly_Analysis_{Year}_Q{Q}.md - all papers
    
    Args:
        records: List of enriched records
        folder_id: Root Drive folder ID
        credentials_path: Optional service account credentials path
    """
    if not records:
        logger.info("No records to sync")
        return
    
    try:
        service = get_drive_service(credentials_path)
    except Exception as e:
        logger.error(f"Failed to authenticate with Google Drive: {e}")
        return
    
    # 1. JSONL Export (All records)
    try:
        append_to_jsonl(service, folder_id, "papers.jsonl", records)
        logger.info(f"Appended {len(records)} records to papers.jsonl")
    except Exception as e:
        logger.error(f"Failed to update papers.jsonl: {e}")
    
    # 2. Markdown Export (Thematic buckets)
    try:
        corpus_folder_id = ensure_folder_exists(service, "NotebookLM_Corpus", folder_id)
    except Exception as e:
        logger.error(f"Failed to ensure corpus folder: {e}")
        return
    
    # Prepare buckets
    current_date = datetime.datetime.now()
    year = current_date.year
    quarter = math.ceil(current_date.month / 3)
    quarterly_filename = f"Literature_{year}_Q{quarter}.md"
    high_conf_filename = "HighConfidence_Analysis.md"
    
    # Sort by score descending
    sorted_records = sorted(records, key=lambda x: x.get("RelevanceScore", 0), reverse=True)
    
    quarterly_buffer = []
    high_conf_buffer = []
    
    for rec in sorted_records:
        score = rec.get("RelevanceScore", 0)
        
        # Skip papers that don't meet quarterly criteria
        # Quarterly file: Score >= 87 AND Full-text required
        has_full_text = rec.get("FullTextUsed", False)
        
        md_text = format_markdown_entry(rec)
        
        # Literature_Q.md: Only high-quality full-text papers
        if score >= 87 and has_full_text:
            quarterly_buffer.append(md_text)
        
        # HighConfidence_Analysis.md: Score >= 90 AND full-text
        if score >= 90 and has_full_text:
            high_conf_buffer.append(md_text)
    
    # Upload quarterly
    if quarterly_buffer:
        try:
            full_text = "\n\n".join(quarterly_buffer)
            append_text_to_file(service, corpus_folder_id, quarterly_filename, full_text)
            logger.info(f"Appended {len(quarterly_buffer)} papers to {quarterly_filename}")
        except Exception as e:
            logger.error(f"Failed to append to {quarterly_filename}: {e}")
    
    # Upload high confidence
    if high_conf_buffer:
        try:
            full_text = "\n\n".join(high_conf_buffer)
            append_text_to_file(service, corpus_folder_id, high_conf_filename, full_text)
            logger.info(f"Appended {len(high_conf_buffer)} papers to {high_conf_filename}")
        except Exception as e:
            logger.error(f"Failed to append to {high_conf_filename}: {e}")
    
    # 3. Computational Methods (full-text papers with score >= 85 only -> quarterly append file)
    fulltext_records = [
        r for r in records 
        if r.get("FullTextUsed") and r.get("comp_methods") and r.get("RelevanceScore", 0) >= 85
    ]
    if fulltext_records:
        try:
            # Ensure Computational_Methods folder exists
            methods_folder_id = ensure_folder_exists(service, "Computational_Methods", corpus_folder_id)
            
            # Build quarterly filename
            comp_methods_filename = f"CompMethods_{year}_Q{quarter}.md"
            
            # Format each paper as a bounded block
            methods_buffer = []
            for rec in fulltext_records:
                block = format_comp_methods_block(rec)
                if block:
                    methods_buffer.append(block)
            
            # Append to quarterly file
            if methods_buffer:
                full_text = "\n\n".join(methods_buffer)
                append_text_to_file(service, methods_folder_id, comp_methods_filename, full_text)
                logger.info(f"Appended {len(methods_buffer)} comp methods to {comp_methods_filename}")
        except Exception as e:
            logger.error(f"Failed to append computational methods: {e}")
