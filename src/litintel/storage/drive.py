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

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload
import google.auth

logger = logging.getLogger(__name__)

# Define scopes
SCOPES = ['https://www.googleapis.com/auth/drive.file']


def get_drive_service(credentials_path: Optional[str] = None):
    """
    Authenticate and return the Drive service.
    
    Supports:
    1. Service Account Key (from GOOGLE_CREDENTIALS_PATH)
    2. Application Default Credentials (via gcloud auth application-default login)
    
    Args:
        credentials_path: Optional path to service account JSON
        
    Returns:
        Google Drive API service
    """
    creds = None
    
    # 1. Try Service Account (Explicit Path)
    if credentials_path and os.path.exists(credentials_path):
        try:
            creds = service_account.Credentials.from_service_account_file(
                credentials_path, scopes=SCOPES
            )
        except Exception as e:
            logger.warning(f"Service Account load failed: {e}")
    
    # 2. Try Application Default Credentials (ADC)
    if not creds:
        try:
            creds, project = google.auth.default(scopes=SCOPES)
            logger.info("Using Application Default Credentials (ADC)")
        except Exception as e:
            logger.warning(f"ADC load failed: {e}")
    
    if not creds:
        raise ValueError(
            "No valid credentials found. Please set GOOGLE_CREDENTIALS_PATH "
            "or run 'gcloud auth application-default login'"
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
    Append text to a markdown file in Drive (Download → Append → Upload).
    
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
    lines.append(f"## PMID: {rec.get('PMID')} — {rec.get('Journal', 'Unknown')} ({rec.get('Year', 'N/A')})")
    lines.append(f"**Title**: {rec.get('Title', 'Untitled')}")
    lines.append(f"**Group**: {rec.get('Group', '')}")
    lines.append(f"**RelevanceScore**: {rec.get('RelevanceScore')}")
    lines.append(f"**PipelineConfidence**: {rec.get('PipelineConfidence', 'N/A')}")
    lines.append("")
    lines.append(f"**PaperRole**: {rec.get('PaperRole', '')}")
    lines.append(f"**Theme**: {rec.get('Theme', '')}")
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
    lines.append(rec.get("WhyRelevant", ""))
    lines.append("")
    lines.append("### StudySummary")
    lines.append(rec.get("StudySummary", ""))
    lines.append("")
    lines.append("### Methods")
    methods = rec.get("Methods", "")
    if ";" in methods:
        for m in methods.split(";"):
            if m.strip():
                lines.append(f"- {m.strip()}")
    elif methods:
        lines.append(f"- {methods}")
    lines.append("")
    lines.append("### KeyFindings")
    findings = rec.get("KeyFindings", "")
    if ";" in findings:
        for f in findings.split(";"):
            if f.strip():
                lines.append(f"- {f.strip()}")
    else:
        lines.append(findings)
    
    return "\n".join(lines)


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
        md_text = format_markdown_entry(rec)
        
        quarterly_buffer.append(md_text)
        
        if score >= 90:
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
