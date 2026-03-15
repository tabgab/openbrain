"""
Open Brain — Google Drive & Gmail Integration
-----------------------------------------------
Handles:
  - OAuth 2.0 flow (authorization + token refresh)
  - Google Drive: list & download new/modified files → ingest
  - Gmail: fetch recent emails → ingest as memories

Requires a Google Cloud project with Drive API + Gmail API enabled,
and OAuth 2.0 credentials (Desktop app type) saved as google_credentials.json.
"""

import os
import io
import json
import datetime
import base64
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# Scopes needed for Drive (read-only) and Gmail (read-only)
SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/gmail.readonly",
]

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_CREDENTIALS_FILE = _PROJECT_ROOT / "google_credentials.json"
_TOKEN_FILE = _PROJECT_ROOT / "google_token.json"

# ---------------------------------------------------------------------------
# OAuth helpers
# ---------------------------------------------------------------------------

def get_credentials() -> Credentials | None:
    """Load stored OAuth credentials, refreshing if expired. Returns None if not authorized."""
    if not _TOKEN_FILE.exists():
        return None
    creds = Credentials.from_authorized_user_file(str(_TOKEN_FILE), SCOPES)
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            _save_token(creds)
        except Exception:
            return None
    return creds if (creds and creds.valid) else None


def _save_token(creds: Credentials):
    """Persist token to disk."""
    with open(_TOKEN_FILE, "w") as f:
        f.write(creds.to_json())


def start_oauth_flow(redirect_uri: str = None) -> dict:
    """
    Start the OAuth flow. Returns auth URL for the user to visit.
    For a local flow, uses InstalledAppFlow with a local redirect.
    """
    if not _CREDENTIALS_FILE.exists():
        return {"error": "google_credentials.json not found. Download OAuth credentials from Google Cloud Console."}

    flow = InstalledAppFlow.from_client_secrets_file(
        str(_CREDENTIALS_FILE), SCOPES,
    )
    # Use local server redirect for the OAuth callback
    flow.redirect_uri = redirect_uri or "http://localhost:8000/api/google/callback"

    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    return {"auth_url": auth_url}


def complete_oauth_flow(auth_code: str) -> dict:
    """Exchange the authorization code for tokens and save them."""
    if not _CREDENTIALS_FILE.exists():
        return {"error": "google_credentials.json not found."}

    flow = InstalledAppFlow.from_client_secrets_file(
        str(_CREDENTIALS_FILE), SCOPES,
    )
    flow.redirect_uri = "http://localhost:8000/api/google/callback"

    try:
        flow.fetch_token(code=auth_code)
        creds = flow.credentials
        _save_token(creds)
        return {"success": True, "email": _get_user_email(creds)}
    except Exception as e:
        return {"error": str(e)}


def get_connection_status() -> dict:
    """Check if Google is connected and return status info."""
    if not _CREDENTIALS_FILE.exists():
        return {"connected": False, "reason": "no_credentials_file"}
    creds = get_credentials()
    if not creds:
        return {"connected": False, "reason": "not_authorized"}
    try:
        email = _get_user_email(creds)
        return {"connected": True, "email": email}
    except Exception as e:
        return {"connected": False, "reason": str(e)}


def disconnect():
    """Remove stored token to disconnect Google account."""
    if _TOKEN_FILE.exists():
        _TOKEN_FILE.unlink()
    return {"success": True}


def _get_user_email(creds: Credentials) -> str:
    """Get the email of the authenticated user."""
    service = build("oauth2", "v2", credentials=creds)
    info = service.userinfo().get().execute()
    return info.get("email", "unknown")


# ---------------------------------------------------------------------------
# Google Drive — Sync
# ---------------------------------------------------------------------------

# Track last sync time in a simple JSON file
_DRIVE_STATE_FILE = _PROJECT_ROOT / "google_drive_state.json"

def _load_drive_state() -> dict:
    if _DRIVE_STATE_FILE.exists():
        return json.loads(_DRIVE_STATE_FILE.read_text())
    return {"last_sync": None, "synced_file_ids": []}


def _save_drive_state(state: dict):
    _DRIVE_STATE_FILE.write_text(json.dumps(state, indent=2))


def sync_drive(max_files: int = 20) -> dict:
    """
    Fetch new/modified files from Google Drive and ingest them.
    Returns a summary of ingested files.
    """
    creds = get_credentials()
    if not creds:
        return {"error": "Google not connected. Please authorize first."}

    from ingest import ingest_document
    from llm import categorize_and_extract, get_embedding
    from db import add_memory

    service = build("drive", "v3", credentials=creds)
    state = _load_drive_state()

    # Build query: files modified after last sync, only supported types
    query_parts = [
        "trashed = false",
        "mimeType != 'application/vnd.google-apps.folder'",
    ]
    if state["last_sync"]:
        query_parts.append(f"modifiedTime > '{state['last_sync']}'")

    query = " and ".join(query_parts)

    try:
        results = service.files().list(
            q=query,
            pageSize=max_files,
            fields="files(id, name, mimeType, modifiedTime, size)",
            orderBy="modifiedTime desc",
        ).execute()
    except Exception as e:
        return {"error": f"Drive API error: {e}"}

    files = results.get("files", [])
    ingested = []
    errors = []

    # Exportable Google Workspace MIME types → download format
    EXPORT_MIMES = {
        "application/vnd.google-apps.document": ("application/pdf", ".pdf"),
        "application/vnd.google-apps.spreadsheet": ("text/csv", ".csv"),
        "application/vnd.google-apps.presentation": ("application/pdf", ".pdf"),
    }

    for f in files:
        fid = f["id"]
        fname = f["name"]
        mime = f["mimeType"]

        # Skip already-synced files
        if fid in state.get("synced_file_ids", []):
            continue

        try:
            # Download file content
            if mime in EXPORT_MIMES:
                export_mime, ext = EXPORT_MIMES[mime]
                request = service.files().export_media(fileId=fid, mimeType=export_mime)
                if not fname.endswith(ext):
                    fname += ext
            else:
                request = service.files().get_media(fileId=fid)

            buf = io.BytesIO()
            downloader = MediaIoBaseDownload(buf, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()

            file_bytes = buf.getvalue()
            if len(file_bytes) == 0:
                continue

            # Ingest through existing pipeline
            result = ingest_document(fname, file_bytes)
            text = result.get("text", "")
            if not text or text.startswith("["):
                errors.append({"file": fname, "error": "No text extracted"})
                continue

            metadata = categorize_and_extract(text[:2000])
            metadata["filename"] = fname
            metadata["google_drive_id"] = fid
            metadata["ingestion_method"] = result["method"]

            embedding = get_embedding(text[:8000])
            memory_id = add_memory(
                content=text,
                source_type="google_drive",
                embedding=embedding,
                metadata=metadata,
            )

            ingested.append({"file": fname, "memory_id": memory_id, "category": metadata.get("category")})
            state.setdefault("synced_file_ids", []).append(fid)

        except Exception as e:
            errors.append({"file": fname, "error": str(e)})

    state["last_sync"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    _save_drive_state(state)

    return {"ingested": ingested, "errors": errors, "files_checked": len(files)}


# ---------------------------------------------------------------------------
# Gmail — Sync
# ---------------------------------------------------------------------------

_GMAIL_STATE_FILE = _PROJECT_ROOT / "google_gmail_state.json"

def _load_gmail_state() -> dict:
    if _GMAIL_STATE_FILE.exists():
        return json.loads(_GMAIL_STATE_FILE.read_text())
    return {"last_history_id": None, "synced_message_ids": []}


def _save_gmail_state(state: dict):
    _GMAIL_STATE_FILE.write_text(json.dumps(state, indent=2))


def sync_gmail(max_emails: int = 20) -> dict:
    """
    Fetch recent emails from Gmail and ingest them as memories.
    Returns a summary of ingested emails.
    """
    creds = get_credentials()
    if not creds:
        return {"error": "Google not connected. Please authorize first."}

    from llm import categorize_and_extract, get_embedding
    from scrubber import scrub_text
    from db import add_memory

    service = build("gmail", "v1", credentials=creds)
    state = _load_gmail_state()

    # Fetch recent messages (newer_than:1d if first sync, else incremental)
    query = "newer_than:1d" if not state.get("synced_message_ids") else "newer_than:3d"

    try:
        results = service.users().messages().list(
            userId="me", q=query, maxResults=max_emails
        ).execute()
    except Exception as e:
        return {"error": f"Gmail API error: {e}"}

    messages = results.get("messages", [])
    ingested = []
    errors = []

    for msg_ref in messages:
        msg_id = msg_ref["id"]

        if msg_id in state.get("synced_message_ids", []):
            continue

        try:
            msg = service.users().messages().get(
                userId="me", id=msg_id, format="full"
            ).execute()

            headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
            subject = headers.get("subject", "(no subject)")
            sender = headers.get("from", "unknown")
            date = headers.get("date", "")

            # Extract body text
            body = _extract_email_body(msg.get("payload", {}))
            if not body:
                continue

            # Compose the memory content
            content = f"Email from: {sender}\nSubject: {subject}\nDate: {date}\n\n{body}"
            scrubbed = scrub_text(content)

            metadata = categorize_and_extract(scrubbed[:2000])
            metadata["email_from"] = sender
            metadata["email_subject"] = subject
            metadata["email_date"] = date
            metadata["gmail_id"] = msg_id

            embedding = get_embedding(scrubbed[:8000])
            memory_id = add_memory(
                content=scrubbed,
                source_type="gmail",
                embedding=embedding,
                metadata=metadata,
            )

            ingested.append({"subject": subject, "from": sender, "memory_id": memory_id})
            state.setdefault("synced_message_ids", []).append(msg_id)

            # Keep the synced list from growing unbounded
            if len(state["synced_message_ids"]) > 1000:
                state["synced_message_ids"] = state["synced_message_ids"][-500:]

        except Exception as e:
            errors.append({"email": msg_id, "error": str(e)})

    _save_gmail_state(state)
    return {"ingested": ingested, "errors": errors, "emails_checked": len(messages)}


def _extract_email_body(payload: dict) -> str:
    """Recursively extract text body from Gmail message payload."""
    mime = payload.get("mimeType", "")
    body_data = payload.get("body", {}).get("data")

    if mime == "text/plain" and body_data:
        return base64.urlsafe_b64decode(body_data).decode("utf-8", errors="replace")

    # Multipart — recurse into parts, prefer text/plain
    parts = payload.get("parts", [])
    plain_text = ""
    html_text = ""
    for part in parts:
        part_mime = part.get("mimeType", "")
        part_data = part.get("body", {}).get("data")
        if part_mime == "text/plain" and part_data:
            plain_text += base64.urlsafe_b64decode(part_data).decode("utf-8", errors="replace")
        elif part_mime == "text/html" and part_data:
            html_text += base64.urlsafe_b64decode(part_data).decode("utf-8", errors="replace")
        elif "multipart" in part_mime:
            nested = _extract_email_body(part)
            if nested:
                plain_text += nested

    if plain_text:
        return plain_text

    # Fallback: strip HTML tags crudely
    if html_text:
        import re
        text = re.sub(r"<[^>]+>", " ", html_text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    return ""
