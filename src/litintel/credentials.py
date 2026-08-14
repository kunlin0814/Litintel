"""
#================================================================
# Module: credentials.py
# Purpose: Resolve the three independent Google identity domains in one place
# Input:   Environment variables (see .env.example)
# Output:  Structured descriptions of what each subsystem will authenticate as
# Dependencies: google-auth (probe only), google-cloud-aiplatform (probe only)
# Date: 2026-07-22
# Context: Backs `litintel doctor`; the authoritative map of who-runs-where
#================================================================

LitIntel talks to Google under THREE separate identities that share no
credentials and, deliberately, no project:

  1. GEMINI  -- Vertex AI inference on the company project, ambient ADC.
  2. RAG     -- Vertex RAG corpus on a personal project, service-account key.
  3. DRIVE   -- personal Google Drive, user OAuth.

Anything naming an account, project, credential file, or resource ID belongs
here (via .env). Anything naming a model or tuning a behavior belongs in
configs/*.yaml. That is the whole split: this module answers WHERE and AS WHOM,
the YAML answers HOW.
"""

import os
from typing import Any, Dict, List, Optional

# Domain identifiers, used as stable keys by `litintel doctor`.
DOMAIN_GEMINI = "gemini"
DOMAIN_RAG = "rag"
DOMAIN_DRIVE = "drive"

_DEFAULT_DRIVE_TOKEN = "token_drive.json"


def _use_vertex_ai() -> bool:
    """Whether Gemini runs through Vertex AI (default) or the API-key path."""
    return os.environ.get("USE_VERTEX_AI", "true").lower() not in ("false", "0", "no")


# ===========================================================================
# 1. GEMINI -- Vertex AI inference (company project, ambient ADC)
# ===========================================================================

def gemini_target() -> Dict[str, Any]:
    """Describe the account and project Gemini inference will run against.

    Returns:
        Dict with keys: domain, mode, project, location, credential, ok, notes.
    """
    if not _use_vertex_ai():
        api_key = os.environ.get("GOOGLE_API_KEY")
        return {
            "domain": DOMAIN_GEMINI,
            "mode": "api_key",
            "project": None,
            "location": None,
            "credential": "GOOGLE_API_KEY",
            "ok": bool(api_key),
            "notes": [] if api_key else ["GOOGLE_API_KEY is unset (USE_VERTEX_AI=false)"],
        }

    project = os.environ.get("GCP_PROJECT_ID")
    notes: List[str] = []
    if not project:
        notes.append("GCP_PROJECT_ID is unset -- required for Vertex AI mode")

    key_path = os.environ.get("GEMINI_CREDENTIALS_JSON")
    if key_path:
        credential = "GEMINI_CREDENTIALS_JSON (%s)" % key_path
        if not os.path.exists(key_path):
            notes.append("GEMINI_CREDENTIALS_JSON points at a missing file: %s" % key_path)
    else:
        credential = "ambient ADC (gcloud auth application-default login)"

    return {
        "domain": DOMAIN_GEMINI,
        "mode": "vertex_ai",
        "project": project,
        "location": os.environ.get("GCP_LOCATION", "us-central1"),
        "credential": credential,
        "ok": bool(project) and not any("missing file" in n for n in notes),
        "notes": notes,
    }


# ===========================================================================
# 2. RAG -- Vertex RAG corpus (personal project, service-account key)
# ===========================================================================

def rag_target() -> Dict[str, Any]:
    """Describe the project and credential the RAG corpus will use.

    The project is parsed from VERTEX_RAG_CORPUS_NAME, never read from
    GCP_PROJECT_ID -- the corpus lives on a different account than Gemini.
    """
    from litintel.storage.rag_corpus import parse_corpus_name

    corpus = os.environ.get("VERTEX_RAG_CORPUS_NAME")
    notes: List[str] = []
    if not corpus:
        return {
            "domain": DOMAIN_RAG,
            "mode": "disabled",
            "project": None,
            "location": None,
            "credential": None,
            "corpus": None,
            "ok": True,
            "notes": ["VERTEX_RAG_CORPUS_NAME is unset -- RAG sync is skipped"],
        }

    try:
        project, location = parse_corpus_name(corpus)
    except ValueError as exc:
        return {
            "domain": DOMAIN_RAG,
            "mode": "vertex_rag",
            "project": None,
            "location": None,
            "credential": None,
            "corpus": corpus,
            "ok": False,
            "notes": [str(exc)],
        }

    key_path = os.environ.get("RAG_CREDENTIALS_JSON")
    if key_path:
        credential = "RAG_CREDENTIALS_JSON (%s)" % key_path
        if not os.path.exists(key_path):
            notes.append("RAG_CREDENTIALS_JSON points at a missing file: %s" % key_path)
    else:
        credential = "ambient ADC"
        notes.append(
            "RAG_CREDENTIALS_JSON is unset -- RAG will use the ambient ADC, which "
            "only works if it is authenticated against project %s" % project
        )

    return {
        "domain": DOMAIN_RAG,
        "mode": "vertex_rag",
        "project": project,
        "location": location,
        "credential": credential,
        "corpus": corpus,
        "ok": not any("missing file" in n for n in notes),
        "notes": notes,
    }


# ===========================================================================
# 3. DRIVE -- personal Google Drive (user OAuth)
# ===========================================================================

# Every Drive destination LitIntel writes to. Pinning exact IDs is what stops
# the pipeline creating duplicate folders/files by name lookup.
DRIVE_TARGET_VARS = (
    "GOOGLE_DRIVE_FOLDER_ID",
    "GOOGLE_DRIVE_PAPERS_JSONL_FILE_ID",
    "GOOGLE_DRIVE_NOTEBOOKLM_FOLDER_ID",
    "GOOGLE_DRIVE_COMP_METHODS_FOLDER_ID",
    "GOOGLE_DRIVE_PDF_FOLDER_ID",
    "GOOGLE_DRIVE_TIERC_INBOX_FOLDER_ID",
    "GOOGLE_DRIVE_TIERC_OUTPUT_FOLDER_ID",
)


def drive_target() -> Dict[str, Any]:
    """Describe the OAuth client and destination IDs for personal Drive."""
    client_secret = (
        os.environ.get("GOOGLE_DRIVE_CLIENT_SECRET")
        or os.environ.get("GOOGLE_CLIENT_SECRETS_PATH")
    )
    token_path = os.environ.get("GOOGLE_DRIVE_TOKEN_PATH", _DEFAULT_DRIVE_TOKEN)

    notes: List[str] = []
    if not client_secret:
        notes.append("GOOGLE_DRIVE_CLIENT_SECRET is unset -- Drive sync is skipped")
    elif not os.path.exists(client_secret):
        notes.append("GOOGLE_DRIVE_CLIENT_SECRET points at a missing file: %s" % client_secret)

    if client_secret and not os.path.exists(token_path):
        notes.append(
            "%s not found -- run scripts/auth/auth_google_drive.py to authorize" % token_path
        )

    unpinned = [v for v in DRIVE_TARGET_VARS if not os.environ.get(v)]
    if unpinned:
        notes.append(
            "Unpinned destinations (looked up by name, may create duplicates): %s"
            % ", ".join(unpinned)
        )

    return {
        "domain": DOMAIN_DRIVE,
        "mode": "user_oauth",
        "project": None,
        "location": None,
        "credential": client_secret or None,
        "token": token_path,
        "targets": {v: os.environ.get(v) for v in DRIVE_TARGET_VARS},
        "ok": not any("missing file" in n for n in notes),
        "notes": notes,
    }


# ===========================================================================
# Aggregate
# ===========================================================================

def describe_all() -> List[Dict[str, Any]]:
    """Resolve all three domains without making any network call."""
    return [gemini_target(), rag_target(), drive_target()]


def probe(domain: str) -> Dict[str, Any]:
    """Make one live call per domain to prove the credential actually works.

    Returns:
        Dict with keys: ok (bool) and detail (str). Never raises -- a failed
        probe is a reportable result, not a crash.
    """
    try:
        if domain == DOMAIN_GEMINI:
            return _probe_gemini()
        if domain == DOMAIN_RAG:
            return _probe_rag()
        if domain == DOMAIN_DRIVE:
            return _probe_drive()
    except Exception as exc:  # reported, never swallowed
        return {"ok": False, "detail": "%s: %s" % (type(exc).__name__, str(exc)[:200])}
    return {"ok": False, "detail": "unknown domain: %s" % domain}


def _probe_gemini() -> Dict[str, Any]:
    """Count models visible to the Gemini client -- cheapest authenticated call."""
    target = gemini_target()
    if not target["ok"]:
        return {"ok": False, "detail": "not configured"}
    from litintel.constants import DEFAULT_GEMINI_MODEL
    from litintel.enrich.ai_client import _get_gemini_client

    client = _get_gemini_client()
    resp = client.models.generate_content(
        model=DEFAULT_GEMINI_MODEL, contents="Reply with exactly: OK"
    )
    return {"ok": True, "detail": "generate_content -> %s" % (resp.text or "").strip()[:20]}


def _probe_rag() -> Dict[str, Any]:
    """List corpus files -- proves both the project and the credential."""
    target = rag_target()
    if target["mode"] == "disabled":
        return {"ok": True, "detail": "disabled"}
    from vertexai.preview import rag

    from litintel.storage.rag_corpus import init_rag

    init_rag(target["corpus"])
    files = list(rag.list_files(corpus_name=target["corpus"]))
    return {"ok": True, "detail": "%d documents in corpus" % len(files)}


def _probe_drive() -> Dict[str, Any]:
    """Fetch the authorized Drive user -- proves the OAuth token is live."""
    target = drive_target()
    if not target["credential"]:
        return {"ok": True, "detail": "disabled"}
    from litintel.storage.drive import get_drive_service

    service = get_drive_service()
    about = service.about().get(fields="user(emailAddress)").execute()
    return {"ok": True, "detail": "authorized as %s" % about["user"]["emailAddress"]}
