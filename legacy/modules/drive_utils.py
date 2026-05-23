import os
import io
import json
import datetime
import logging
from typing import Optional, List, Dict, Any, Union

from google.oauth2 import service_account
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload

# Define scopes
SCOPES = ['https://www.googleapis.com/auth/drive.file']

import google.auth

def get_drive_service(credentials_path: Optional[str] = None):
    """Authenticate and return the Drive service.
    
    Supports:
    1. Service Account Key (from GOOGLE_CREDENTIALS_PATH)
    2. Application Default Credentials (via gcloud auth application-default login)
    """
    creds = None
    
    # 1. Try Service Account (Explicit Path)
    if credentials_path and os.path.exists(credentials_path):
        try:
            creds = service_account.Credentials.from_service_account_file(
                credentials_path, scopes=SCOPES
            )
            # Verify if we can actually use these creds? 
            # We defer validation to the API call, but typically this succeeds locally.
        except Exception as e:
            logging.warning(f"Service Account load failed: {e}")
            pass

    # 2. Try Application Default Credentials (ADC)
    # This works if user ran `gcloud auth application-default login`
    if not creds:
        try:
            creds, project = google.auth.default(scopes=SCOPES)
            logging.info("Using Application Default Credentials (ADC).")
        except Exception as e:
            logging.warning(f"ADC load failed: {e}")
            pass

    if not creds:
        raise ValueError("No valid credentials found. Please set GOOGLE_CREDENTIALS_PATH or run 'gcloud auth application-default login'.")

    return build('drive', 'v3', credentials=creds)


def ensure_folder_exists(service, folder_name: str, parent_id: str) -> str:
    """Check if folder exists in parent; create if not. Return folder ID."""
    query = f"name = '{folder_name}' and '{parent_id}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    results = service.files().list(q=query, fields="files(id, name)").execute()
    files = results.get('files', [])
    
    if files:
        return files[0]['id']
    else:
        file_metadata = {
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder',
            'parents': [parent_id]
        }
        file = service.files().create(body=file_metadata, fields='id').execute()
        return file.get('id')


def upload_markdown_file(service, folder_id: str, file_name: str, content: str) -> str:
    """Upload (or overwrite) a Markdown file to Drive."""
    # Check if file exists to overwrite
    query = f"name = '{file_name}' and '{folder_id}' in parents and trashed = false"
    results = service.files().list(q=query, fields="files(id)").execute()
    files = results.get('files', [])
    
    file_metadata = {
        'name': file_name,
        # 'mimeType': 'application/vnd.google-apps.document' # Convert to Doc? 
        # NotebookLM supports .md and .txt. Let's stick to text/plain or text/markdown to avoid conversion errors.
        'mimeType': 'text/plain' 
    }
    
    media = MediaIoBaseUpload(io.BytesIO(content.encode('utf-8')), mimetype='text/plain', resumable=True)
    
    if files:
        # Update existing
        file_id = files[0]['id']
        updated_file = service.files().update(
            fileId=file_id,
            body=file_metadata, # Update metadata if needed
            media_body=media,
            fields='id'
        ).execute()
        return updated_file.get('id')
    else:
        # Create new
        file_metadata['parents'] = [folder_id]
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id'
        ).execute()
        return file.get('id')


def append_to_jsonl(service, folder_id: str, file_name: str, new_records: List[Dict[str, Any]]) -> str:
    """Append JSONL records to a file in Drive.
    
    Note: Google Drive API doesn't support 'append' operation directly on file content.
    We must download, append, and re-upload. This is inefficient for huge files but fine for <10MB.
    """
    if not new_records:
        return ""
        
    query = f"name = '{file_name}' and '{folder_id}' in parents and trashed = false"
    results = service.files().list(q=query, fields="files(id)").execute()
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
        """JSON serializer for objects not serializable by default json code"""
        if isinstance(obj, (datetime.datetime, datetime.date)):
            return obj.isoformat()
        raise TypeError (f"Type {type(obj)} not serializable")

    new_lines = "\n".join([json.dumps(r, default=json_serial) for r in new_records])
    if existing_content and not existing_content.endswith("\n"):
        full_content = existing_content + "\n" + new_lines
    else:
        full_content = existing_content + new_lines
        
    # Re-upload
    media = MediaIoBaseUpload(io.BytesIO(full_content.encode('utf-8')), mimetype='application/json', resumable=True)
    
    if file_id:
        service.files().update(
            fileId=file_id,
            media_body=media,
            fields='id'
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
            fields='id'
        ).execute()
        return file.get('id')

from googleapiclient.http import MediaIoBaseDownload


def append_text_to_file(service, folder_id: str, file_name: str, new_text: str) -> str:
    """Append text to a file in Drive (Download -> Append -> Upload)."""
    if not new_text:
        return ""

    query = f"name = '{file_name}' and '{folder_id}' in parents and trashed = false"
    results = service.files().list(q=query, fields="files(id)").execute()
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
            # If download fails (e.g. empty file), treat as empty
            existing_content = ""

    # Check if we need a separator
    if existing_content and not existing_content.endswith("\n\n"):
         full_content = existing_content + "\n\n" + new_text
    elif existing_content:
         full_content = existing_content + new_text
    else:
         full_content = new_text

    media = MediaIoBaseUpload(io.BytesIO(full_content.encode('utf-8')), mimetype='text/plain', resumable=True)

    if file_id:
        service.files().update(
            fileId=file_id,
            media_body=media,
            fields='id'
        ).execute()
        return file_id
    else:
        file_metadata = {
            'name': file_name,
            'parents': [folder_id],
            'mimeType': 'text/plain' # Keep generic text/plain for MD
        }
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id'
        ).execute()
        return file.get('id')

