"""
Open Brain — Google Drive, Gmail & Calendar Integration (Multi-Account)
------------------------------------------------------------------------
Handles:
  - OAuth 2.0 flow with multiple Google accounts
  - Google Drive: search/filter files → preview → selective ingest
  - Gmail: search/filter emails → preview → selective ingest
  - Google Calendar: scan events → deduplicate recurring → selective ingest

Accounts are stored in google_accounts/<email>.json with tokens and sync state.
Requires google_credentials.json (OAuth 2.0 Web credentials) from Google Cloud Console.
"""

import os
import io
import json
import datetime
import base64
import re
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.readonly",
]

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_CREDENTIALS_FILE = _PROJECT_ROOT / "google_credentials.json"
_ACCOUNTS_DIR = _PROJECT_ROOT / "google_accounts"

# Temporary in-memory store for PKCE code_verifiers keyed by OAuth state
_pending_oauth: dict[str, str] = {}  # state -> code_verifier

# ---------------------------------------------------------------------------
# Multi-account storage  (google_accounts/<email>.json)
# ---------------------------------------------------------------------------

def _ensure_accounts_dir():
    _ACCOUNTS_DIR.mkdir(exist_ok=True)


def _account_file(email: str) -> Path:
    safe = re.sub(r"[^a-zA-Z0-9@._-]", "_", email)
    return _ACCOUNTS_DIR / f"{safe}.json"


def _load_account(email: str) -> dict:
    f = _account_file(email)
    if f.exists():
        return json.loads(f.read_text())
    return {}


def _save_account(email: str, data: dict):
    _ensure_accounts_dir()
    _account_file(email).write_text(json.dumps(data, indent=2))


def _delete_account(email: str):
    f = _account_file(email)
    if f.exists():
        f.unlink()


# ---------------------------------------------------------------------------
# OAuth helpers (multi-account)
# ---------------------------------------------------------------------------

def get_credentials_for(email: str) -> Credentials | None:
    """Load stored OAuth credentials for a specific account."""
    acct = _load_account(email)
    token_data = acct.get("token")
    if not token_data:
        return None
    creds = Credentials.from_authorized_user_info(token_data, SCOPES)
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            acct["token"] = json.loads(creds.to_json())
            _save_account(email, acct)
        except Exception:
            return None
    return creds if (creds and creds.valid) else None


def start_oauth_flow() -> dict:
    """Start the OAuth flow. Returns auth URL for the user to visit."""
    if not _CREDENTIALS_FILE.exists():
        return {"error": "google_credentials.json not found. Download OAuth credentials from Google Cloud Console."}

    flow = Flow.from_client_secrets_file(str(_CREDENTIALS_FILE), scopes=SCOPES,
                                         redirect_uri="http://localhost:8000/api/google/callback")

    auth_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    # Persist the code_verifier so the callback can use it
    _pending_oauth[state] = flow.code_verifier or ""
    return {"auth_url": auth_url}


def complete_oauth_flow(auth_code: str, state: str = "") -> dict:
    """Exchange the authorization code for tokens and save under the account's email."""
    if not _CREDENTIALS_FILE.exists():
        return {"error": "google_credentials.json not found."}

    flow = Flow.from_client_secrets_file(str(_CREDENTIALS_FILE), scopes=SCOPES,
                                         redirect_uri="http://localhost:8000/api/google/callback")

    # Restore PKCE code_verifier from the original auth request
    code_verifier = _pending_oauth.pop(state, None) if state else None
    if code_verifier:
        flow.code_verifier = code_verifier

    try:
        flow.fetch_token(code=auth_code)
        creds = flow.credentials
        email = _get_user_email(creds)
        acct = _load_account(email)
        acct["token"] = json.loads(creds.to_json())
        acct["email"] = email
        acct["connected_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        _save_account(email, acct)
        return {"success": True, "email": email}
    except Exception as e:
        return {"error": str(e)}


def list_accounts() -> list[dict]:
    """Return a list of all connected Google accounts."""
    _ensure_accounts_dir()
    accounts = []
    for f in sorted(_ACCOUNTS_DIR.glob("*.json")):
        try:
            data = json.loads(f.read_text())
            email = data.get("email", f.stem)
            creds = get_credentials_for(email)
            accounts.append({
                "email": email,
                "connected": creds is not None and creds.valid,
                "connected_at": data.get("connected_at"),
                "drive_last_sync": data.get("drive_last_sync"),
                "gmail_last_sync": data.get("gmail_last_sync"),
            })
        except Exception:
            continue
    return accounts


def get_all_accounts() -> list[dict]:
    """Alias for list_accounts — used by MCP server tools."""
    return list_accounts()


def get_status() -> dict:
    """Overall status: credentials file exists + list of accounts."""
    has_creds = _CREDENTIALS_FILE.exists()
    accounts = list_accounts() if has_creds else []
    return {"has_credentials_file": has_creds, "accounts": accounts}


def disconnect(email: str) -> dict:
    """Remove a single Google account."""
    _delete_account(email)
    return {"success": True, "email": email}


def _get_user_email(creds: Credentials) -> str:
    """Get the email of the authenticated user via the Gmail API (already scoped)."""
    service = build("gmail", "v1", credentials=creds)
    profile = service.users().getProfile(userId="me").execute()
    return profile.get("emailAddress", "unknown")


# ---------------------------------------------------------------------------
# Google Drive — Search / Preview / Ingest
# ---------------------------------------------------------------------------

EXPORT_MIMES = {
    "application/vnd.google-apps.document": ("application/pdf", ".pdf"),
    "application/vnd.google-apps.spreadsheet": ("text/csv", ".csv"),
    "application/vnd.google-apps.presentation": ("application/pdf", ".pdf"),
}


def search_drive(email: str, query: str = "", folder_name: str = "",
                 file_type: str = "", max_results: int = 25) -> dict:
    """
    Search/filter Google Drive files. Returns a preview list (no ingestion).
    
    Filters:
      query      — free-text search (file name contains)
      folder_name— restrict to a specific folder name
      file_type  — 'document', 'spreadsheet', 'pdf', 'image', or '' for all
      max_results— how many to return (max 50)
    """
    creds = get_credentials_for(email)
    if not creds:
        return {"error": f"Account {email} not connected or token expired."}

    service = build("drive", "v3", credentials=creds)

    q_parts = ["trashed = false", "mimeType != 'application/vnd.google-apps.folder'"]

    if query:
        q_parts.append(f"name contains '{query}'")

    mime_map = {
        "document": "application/vnd.google-apps.document",
        "spreadsheet": "application/vnd.google-apps.spreadsheet",
        "pdf": "application/pdf",
        "image": "image/",
    }
    if file_type and file_type in mime_map:
        if file_type == "image":
            q_parts.append("mimeType contains 'image/'")
        else:
            q_parts.append(f"mimeType = '{mime_map[file_type]}'")

    # Folder filter — resolve folder name to ID first
    if folder_name:
        try:
            folders = service.files().list(
                q=f"name = '{folder_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false",
                fields="files(id)", pageSize=1,
            ).execute().get("files", [])
            if folders:
                q_parts.append(f"'{folders[0]['id']}' in parents")
        except Exception:
            pass

    q_str = " and ".join(q_parts)
    max_results = min(max_results, 50)

    try:
        results = service.files().list(
            q=q_str, pageSize=max_results,
            fields="files(id, name, mimeType, modifiedTime, size)",
            orderBy="modifiedTime desc",
        ).execute()
    except Exception as e:
        return {"error": f"Drive API error: {e}"}

    files = []
    acct = _load_account(email)
    synced_ids = set(acct.get("drive_synced_ids", []))
    for f in results.get("files", []):
        files.append({
            "id": f["id"],
            "name": f["name"],
            "mimeType": f["mimeType"],
            "modifiedTime": f.get("modifiedTime", ""),
            "size": f.get("size", "0"),
            "already_synced": f["id"] in synced_ids,
        })

    return {"files": files, "total": len(files), "query": q_str}


def ingest_drive_files(email: str, file_ids: list[str]) -> dict:
    """Ingest specific files from Google Drive by their IDs."""
    creds = get_credentials_for(email)
    if not creds:
        return {"error": f"Account {email} not connected."}

    from ingest import ingest_document
    from llm import categorize_and_extract, get_embedding
    from db import add_memory

    service = build("drive", "v3", credentials=creds)
    acct = _load_account(email)
    synced_ids = set(acct.get("drive_synced_ids", []))

    ingested = []
    errors = []

    for fid in file_ids:
        try:
            meta = service.files().get(fileId=fid, fields="id,name,mimeType").execute()
            fname = meta["name"]
            mime = meta["mimeType"]

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
                errors.append({"id": fid, "file": fname, "error": "Empty file"})
                continue

            result = ingest_document(fname, file_bytes)
            text = result.get("text", "")
            if not text or text.startswith("["):
                errors.append({"id": fid, "file": fname, "error": "No text extracted"})
                continue

            metadata = categorize_and_extract(text[:2000])
            metadata["filename"] = fname
            metadata["google_drive_id"] = fid
            metadata["google_account"] = email
            metadata["ingestion_method"] = result["method"]

            embedding = get_embedding(text[:8000])
            memory_id = add_memory(
                content=text, source_type="google_drive",
                embedding=embedding, metadata=metadata,
            )
            ingested.append({"id": fid, "file": fname, "memory_id": memory_id, "category": metadata.get("category")})
            synced_ids.add(fid)

        except Exception as e:
            errors.append({"id": fid, "error": str(e)})

    acct["drive_synced_ids"] = list(synced_ids)[-2000:]  # cap at 2000
    acct["drive_last_sync"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    _save_account(email, acct)

    return {"ingested": ingested, "errors": errors}


# ---------------------------------------------------------------------------
# Gmail — Search / Preview / Ingest
# ---------------------------------------------------------------------------

def list_gmail_labels(email: str) -> dict:
    """Return all Gmail labels (system + custom) for the given account."""
    creds = get_credentials_for(email)
    if not creds:
        return {"error": f"Account {email} not connected."}

    service = build("gmail", "v1", credentials=creds)
    try:
        results = service.users().labels().list(userId="me").execute()
        labels = []
        for lbl in results.get("labels", []):
            labels.append({
                "id": lbl["id"],
                "name": lbl["name"],
                "type": lbl.get("type", "user"),  # "system" or "user"
            })
        # Sort: system labels first, then user labels alphabetically
        labels.sort(key=lambda l: (0 if l["type"] == "system" else 1, l["name"].lower()))
        return {"labels": labels}
    except Exception as e:
        return {"error": str(e)}


def search_gmail(email: str, query: str = "", from_filter: str = "",
                 subject_filter: str = "", label: str = "",
                 newer_than: str = "7d", max_results: int = 25) -> dict:
    """
    Search/filter Gmail messages. Returns a preview list (no ingestion).
    
    Filters:
      query          — raw Gmail search query (full Gmail syntax)
      from_filter    — filter by sender email/name
      subject_filter — filter by subject text
      label          — Gmail label ID (system like 'INBOX' or custom like 'Label_123')
      newer_than     — e.g. '1d', '7d', '30d', '1y'
      max_results    — how many to return (max 50)
    """
    creds = get_credentials_for(email)
    if not creds:
        return {"error": f"Account {email} not connected or token expired."}

    service = build("gmail", "v1", credentials=creds)

    # Build Gmail search query
    q_parts = []
    if query:
        q_parts.append(query)
    if from_filter:
        q_parts.append(f"from:{from_filter}")
    if subject_filter:
        q_parts.append(f"subject:{subject_filter}")
    if newer_than:
        q_parts.append(f"newer_than:{newer_than}")
    q_str = " ".join(q_parts) if q_parts else "newer_than:7d"

    label_ids = []
    if label:
        label_ids = [label]  # Use label ID directly (works for both system and custom)

    max_results = min(max_results, 50)

    try:
        params = {"userId": "me", "q": q_str, "maxResults": max_results}
        if label_ids:
            params["labelIds"] = label_ids
        results = service.users().messages().list(**params).execute()
    except Exception as e:
        return {"error": f"Gmail API error: {e}"}

    msg_refs = results.get("messages", [])
    acct = _load_account(email)
    synced_ids = set(acct.get("gmail_synced_ids", []))

    messages = []
    for ref in msg_refs:
        try:
            msg = service.users().messages().get(
                userId="me", id=ref["id"], format="metadata",
                metadataHeaders=["From", "Subject", "Date"],
            ).execute()
            headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
            messages.append({
                "id": ref["id"],
                "from": headers.get("from", ""),
                "subject": headers.get("subject", "(no subject)"),
                "date": headers.get("date", ""),
                "snippet": msg.get("snippet", ""),
                "already_synced": ref["id"] in synced_ids,
            })
        except Exception:
            continue

    return {"messages": messages, "total": len(messages), "query": q_str}


def ingest_gmail_messages(email: str, message_ids: list[str], include_images: bool = False) -> dict:
    """Ingest specific Gmail messages by their IDs.

    If include_images is True, image attachments are extracted and processed
    through the vision model to generate text descriptions that are appended
    to the memory content.
    """
    creds = get_credentials_for(email)
    if not creds:
        return {"error": f"Account {email} not connected."}

    from llm import categorize_and_extract, get_embedding
    from scrubber import scrub_text
    from db import add_memory

    service = build("gmail", "v1", credentials=creds)
    acct = _load_account(email)
    synced_ids = set(acct.get("gmail_synced_ids", []))

    # Lazy-import vision capability only when needed
    describe_image = None
    if include_images:
        try:
            from llm import describe_image as _desc
            describe_image = _desc
        except ImportError:
            describe_image = None

    ingested = []
    errors = []

    for msg_id in message_ids:
        try:
            msg = service.users().messages().get(
                userId="me", id=msg_id, format="full"
            ).execute()

            headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
            subject = headers.get("subject", "(no subject)")
            sender = headers.get("from", "unknown")
            date = headers.get("date", "")
            payload = msg.get("payload", {})

            body = _extract_email_body(payload)
            if not body:
                errors.append({"id": msg_id, "error": "No body text"})
                continue

            content = f"Email from: {sender}\nSubject: {subject}\nDate: {date}\n\n{body}"

            # Process image attachments through vision model
            if include_images and describe_image:
                images = _get_image_attachments(service, msg_id, payload)
                for i, img in enumerate(images, 1):
                    try:
                        desc = describe_image(img["data_b64"], img["mime"])
                        content += f"\n\n[Image {i}: {img['filename']}]\n{desc}"
                    except Exception:
                        content += f"\n\n[Image {i}: {img['filename']}] (could not process)"

            scrubbed = scrub_text(content)

            metadata = categorize_and_extract(scrubbed[:2000])
            metadata["email_from"] = sender
            metadata["email_subject"] = subject
            metadata["email_date"] = date
            metadata["gmail_id"] = msg_id
            metadata["google_account"] = email
            metadata["include_images"] = include_images

            embedding = get_embedding(scrubbed[:8000])
            memory_id = add_memory(
                content=scrubbed, source_type="gmail",
                embedding=embedding, metadata=metadata,
            )
            ingested.append({"id": msg_id, "subject": subject, "from": sender, "memory_id": memory_id})
            synced_ids.add(msg_id)

        except Exception as e:
            errors.append({"id": msg_id, "error": str(e)})

    acct["gmail_synced_ids"] = list(synced_ids)[-2000:]
    acct["gmail_last_sync"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    _save_account(email, acct)

    return {"ingested": ingested, "errors": errors}


# ---------------------------------------------------------------------------
# Gmail — Preview (read full message before ingesting)
# ---------------------------------------------------------------------------

def preview_gmail_message(email: str, message_id: str) -> dict:
    """Fetch the full body of a single Gmail message for reading, including images."""
    creds = get_credentials_for(email)
    if not creds:
        return {"error": f"Account {email} not connected."}

    service = build("gmail", "v1", credentials=creds)
    try:
        msg = service.users().messages().get(
            userId="me", id=message_id, format="full"
        ).execute()
        headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
        payload = msg.get("payload", {})
        text_body = _extract_email_body(payload)
        html_body = _extract_html_body(payload)

        # Resolve inline cid: images to data URIs
        if html_body:
            cid_map = _extract_inline_images(service, message_id, payload)
            for cid, data_uri in cid_map.items():
                html_body = html_body.replace(f"cid:{cid}", data_uri)

        # Count image attachments
        image_count = _count_image_attachments(payload)

        return {
            "id": message_id,
            "from": headers.get("from", ""),
            "to": headers.get("to", ""),
            "subject": headers.get("subject", "(no subject)"),
            "date": headers.get("date", ""),
            "body": text_body or "(no body text)",
            "html_body": html_body or "",
            "image_count": image_count,
        }
    except Exception as e:
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Gmail — HTML body & inline image helpers
# ---------------------------------------------------------------------------

def _extract_html_body(payload: dict) -> str:
    """Extract raw HTML body from Gmail message payload."""
    html_parts: list[str] = []

    def _walk(node: dict):
        mime = node.get("mimeType", "")
        body_data = node.get("body", {}).get("data")
        if mime == "text/html" and body_data:
            html_parts.append(base64.urlsafe_b64decode(body_data).decode("utf-8", errors="replace"))
        for part in node.get("parts", []):
            _walk(part)

    _walk(payload)
    return "\n".join(html_parts) if html_parts else ""


def _extract_inline_images(service, message_id: str, payload: dict) -> dict[str, str]:
    """Walk MIME tree and resolve inline images (with Content-ID) to data URIs.

    Returns a dict mapping content_id -> data:image/...;base64,... URI.
    """
    cid_map: dict[str, str] = {}

    def _walk(node: dict):
        mime = node.get("mimeType", "")
        headers = {h["name"].lower(): h["value"] for h in node.get("headers", [])}
        attachment_id = node.get("body", {}).get("attachmentId")
        content_id = headers.get("content-id", "").strip("<>")

        if mime.startswith("image/") and attachment_id and content_id:
            try:
                att = service.users().messages().attachments().get(
                    userId="me", messageId=message_id, id=attachment_id
                ).execute()
                data = att.get("data", "")
                # Gmail returns url-safe base64; convert to standard base64 for data URI
                raw = base64.urlsafe_b64decode(data)
                std_b64 = base64.b64encode(raw).decode("ascii")
                cid_map[content_id] = f"data:{mime};base64,{std_b64}"
            except Exception:
                pass

        for part in node.get("parts", []):
            _walk(part)

    _walk(payload)
    return cid_map


def _count_image_attachments(payload: dict) -> int:
    """Count all image/* parts in the MIME tree."""
    count = 0

    def _walk(node: dict):
        nonlocal count
        mime = node.get("mimeType", "")
        if mime.startswith("image/") and node.get("body", {}).get("attachmentId"):
            count += 1
        for part in node.get("parts", []):
            _walk(part)

    _walk(payload)
    return count


def _get_image_attachments(service, message_id: str, payload: dict) -> list[dict]:
    """Extract all image attachments as {mime, filename, data_b64} dicts."""
    images: list[dict] = []

    def _walk(node: dict):
        mime = node.get("mimeType", "")
        attachment_id = node.get("body", {}).get("attachmentId")
        filename = node.get("filename", "")
        if mime.startswith("image/") and attachment_id:
            try:
                att = service.users().messages().attachments().get(
                    userId="me", messageId=message_id, id=attachment_id
                ).execute()
                raw = base64.urlsafe_b64decode(att.get("data", ""))
                images.append({
                    "mime": mime,
                    "filename": filename or f"image.{mime.split('/')[-1]}",
                    "data_b64": base64.b64encode(raw).decode("ascii"),
                })
            except Exception:
                pass
        for part in node.get("parts", []):
            _walk(part)

    _walk(payload)
    return images


# ---------------------------------------------------------------------------
# Gmail body extraction
# ---------------------------------------------------------------------------

def _extract_email_body(payload: dict) -> str:
    """Recursively extract text body from Gmail message payload.

    Traverses the entire MIME tree, collecting all text/plain and text/html
    parts, then returns plain text (preferred) or HTML-stripped text.
    """
    plain_parts: list[str] = []
    html_parts: list[str] = []

    def _walk(node: dict):
        mime = node.get("mimeType", "")
        body_data = node.get("body", {}).get("data")
        parts = node.get("parts", [])

        if body_data:
            decoded = base64.urlsafe_b64decode(body_data).decode("utf-8", errors="replace")
            if mime == "text/plain":
                plain_parts.append(decoded)
            elif mime == "text/html":
                html_parts.append(decoded)

        for part in parts:
            _walk(part)

    _walk(payload)

    if plain_parts:
        return "\n".join(plain_parts)

    if html_parts:
        combined = "\n".join(html_parts)
        text = re.sub(r"<style[^>]*>.*?</style>", "", combined, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL | re.IGNORECASE)
        # Preserve image references as [image] placeholders
        text = re.sub(r'<img[^>]*alt="([^"]+)"[^>]*/?\s*>', r' [\1] ', text, flags=re.IGNORECASE)
        text = re.sub(r"<img[^>]*/?\s*>", " [image] ", text, flags=re.IGNORECASE)
        # Preserve links
        text = re.sub(r'<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>', r'\2 (\1)', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
        text = re.sub(r"</(p|div|tr|li|h[1-6])>", "\n", text, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n\s*\n+", "\n\n", text).strip()
        return text

    return ""


# ---------------------------------------------------------------------------
# Google Calendar — Scan / Deduplicate / Ingest
# ---------------------------------------------------------------------------

def scan_calendar_events(email: str, time_min: str = "", time_max: str = "",
                         max_results: int = 500) -> dict:
    """Scan calendar events for the given account.

    Returns a deduplicated list:
      - Recurring events are collapsed into a single entry with recurrence info.
      - Already-processed event IDs are flagged.

    Args:
        time_min: ISO datetime string for range start (default: 1 year ago on
                  first scan, start of current month on subsequent scans).
        time_max: ISO datetime string for range end (default: now + 30 days).
    """
    creds = get_credentials_for(email)
    if not creds:
        return {"error": f"Account {email} not connected."}

    service = build("calendar", "v3", credentials=creds)
    acct = _load_account(email)
    synced_ids = set(acct.get("calendar_synced_ids", []))
    is_first_scan = len(synced_ids) == 0

    now = datetime.datetime.now(datetime.timezone.utc)

    # Determine scan window
    if not time_min:
        if is_first_scan:
            time_min = (now - datetime.timedelta(days=365)).isoformat()
        else:
            # Start of current month
            time_min = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
    if not time_max:
        time_max = (now + datetime.timedelta(days=30)).isoformat()

    # Fetch events from all calendars
    all_events: list[dict] = []
    try:
        cal_list = service.calendarList().list().execute()
        calendars = cal_list.get("items", [])
    except Exception as e:
        return {"error": f"Calendar API error: {e}"}

    for cal in calendars:
        cal_id = cal["id"]
        cal_name = cal.get("summary", cal_id)
        try:
            page_token = None
            while True:
                resp = service.events().list(
                    calendarId=cal_id,
                    timeMin=time_min,
                    timeMax=time_max,
                    maxResults=min(max_results, 2500),
                    singleEvents=True,
                    orderBy="startTime",
                    pageToken=page_token,
                ).execute()
                for ev in resp.get("items", []):
                    ev["_calendar_name"] = cal_name
                    ev["_calendar_id"] = cal_id
                all_events.extend(resp.get("items", []))
                page_token = resp.get("nextPageToken")
                if not page_token or len(all_events) >= max_results:
                    break
        except Exception:
            continue

    # --- Deduplicate recurring events ---
    # Group by recurringEventId; standalone events get their own group.
    groups: dict[str, list[dict]] = {}
    for ev in all_events:
        recurring_id = ev.get("recurringEventId", "")
        key = recurring_id if recurring_id else ev.get("id", "")
        groups.setdefault(key, []).append(ev)

    events_out: list[dict] = []
    for key, evs in groups.items():
        first = evs[0]
        ev_id = first.get("id", key)
        start = _parse_event_datetime(first.get("start", {}))
        end = _parse_event_datetime(first.get("end", {}))
        summary = first.get("summary", "(no title)")
        location = first.get("location", "")
        description = first.get("description", "")
        cal_name = first.get("_calendar_name", "")

        is_recurring = bool(first.get("recurringEventId")) or len(evs) > 1
        recurrence_info = ""
        occurrence_count = len(evs)

        if is_recurring and occurrence_count > 1:
            # Derive recurrence pattern from instances
            dates = sorted([_parse_event_datetime(e.get("start", {})) for e in evs])
            recurrence_info = _infer_recurrence(dates, occurrence_count)

        already_synced = ev_id in synced_ids or key in synced_ids
        # For recurring, check if the base recurring ID was synced
        if not already_synced and first.get("recurringEventId"):
            already_synced = first["recurringEventId"] in synced_ids

        events_out.append({
            "id": ev_id,
            "recurring_id": first.get("recurringEventId", ""),
            "summary": summary,
            "start": start,
            "end": end,
            "location": location,
            "description": description[:500] if description else "",
            "calendar": cal_name,
            "calendar_id": first.get("_calendar_id", ""),
            "is_recurring": is_recurring,
            "occurrence_count": occurrence_count,
            "recurrence_info": recurrence_info,
            "already_synced": already_synced,
        })

    # Sort by start time
    events_out.sort(key=lambda e: e["start"] or "")

    calendars_info = [
        {
            "id": c["id"],
            "name": c.get("summary", c["id"]),
            "color": c.get("backgroundColor", "#3b82f6"),
        }
        for c in calendars
    ]

    return {
        "events": events_out,
        "total": len(events_out),
        "is_first_scan": is_first_scan,
        "time_min": time_min,
        "time_max": time_max,
        "calendars_scanned": len(calendars),
        "calendars": calendars_info,
    }


def ingest_calendar_events(email: str, event_ids: list[str]) -> dict:
    """Ingest selected calendar events as memories."""
    creds = get_credentials_for(email)
    if not creds:
        return {"error": f"Account {email} not connected."}

    from llm import categorize_and_extract, get_embedding
    from scrubber import scrub_text
    from db import add_memory

    service = build("calendar", "v3", credentials=creds)
    acct = _load_account(email)
    synced_ids = set(acct.get("calendar_synced_ids", []))

    ingested = []
    errors = []

    for ev_id in event_ids:
        if ev_id in synced_ids:
            continue
        try:
            # Try primary calendar first, then search all
            ev = _fetch_event(service, ev_id)
            if not ev:
                errors.append({"id": ev_id, "error": "Event not found"})
                continue

            summary = ev.get("summary", "(no title)")
            start = _parse_event_datetime(ev.get("start", {}))
            end = _parse_event_datetime(ev.get("end", {}))
            location = ev.get("location", "")
            description = ev.get("description", "")
            attendees = [a.get("email", "") for a in ev.get("attendees", [])]
            organizer = ev.get("organizer", {}).get("email", "")
            is_recurring = bool(ev.get("recurringEventId"))

            # Build content text
            parts = [f"Calendar Event: {summary}"]
            parts.append(f"When: {start} — {end}")
            if location:
                parts.append(f"Where: {location}")
            if organizer:
                parts.append(f"Organizer: {organizer}")
            if attendees:
                parts.append(f"Attendees: {', '.join(attendees[:20])}")
            if is_recurring:
                # Fetch recurrence rule from the parent
                try:
                    parent_id = ev.get("recurringEventId", ev_id)
                    parent = service.events().get(
                        calendarId="primary", eventId=parent_id
                    ).execute()
                    rules = parent.get("recurrence", [])
                    if rules:
                        parts.append(f"Recurrence: {'; '.join(rules)}")
                except Exception:
                    parts.append("Recurrence: recurring event")
            if description:
                parts.append(f"\n{description}")

            content = "\n".join(parts)
            scrubbed = scrub_text(content)

            metadata = categorize_and_extract(scrubbed[:2000])
            metadata["calendar_event_id"] = ev_id
            metadata["calendar_summary"] = summary
            metadata["calendar_start"] = start
            metadata["calendar_end"] = end
            metadata["calendar_location"] = location
            metadata["google_account"] = email
            metadata["is_recurring"] = is_recurring

            embedding = get_embedding(scrubbed[:8000])
            memory_id = add_memory(
                content=scrubbed, source_type="google_calendar",
                embedding=embedding, metadata=metadata,
            )
            ingested.append({"id": ev_id, "summary": summary, "start": start, "memory_id": memory_id})

            # Mark synced — also mark the recurring parent ID so future instances
            # of the same recurring event are flagged as already synced.
            synced_ids.add(ev_id)
            if ev.get("recurringEventId"):
                synced_ids.add(ev["recurringEventId"])

        except Exception as e:
            errors.append({"id": ev_id, "error": str(e)})

    acct["calendar_synced_ids"] = list(synced_ids)[-5000:]
    acct["calendar_last_sync"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    _save_account(email, acct)

    return {"ingested": ingested, "errors": errors}


# ---------------------------------------------------------------------------
# Calendar helpers
# ---------------------------------------------------------------------------

def _parse_event_datetime(dt_obj: dict) -> str:
    """Extract a readable datetime string from a Calendar event start/end."""
    if "dateTime" in dt_obj:
        return dt_obj["dateTime"]
    if "date" in dt_obj:
        return dt_obj["date"]  # all-day event
    return ""


def _fetch_event(service, ev_id: str) -> dict | None:
    """Try to fetch an event from primary, then from all calendars."""
    try:
        return service.events().get(calendarId="primary", eventId=ev_id).execute()
    except Exception:
        pass
    # Fall back: search all calendars
    try:
        cal_list = service.calendarList().list().execute()
        for cal in cal_list.get("items", []):
            try:
                return service.events().get(calendarId=cal["id"], eventId=ev_id).execute()
            except Exception:
                continue
    except Exception:
        pass
    return None


def _infer_recurrence(dates: list[str], count: int) -> str:
    """Infer a human-readable recurrence pattern from a list of instance dates."""
    if count < 2:
        return ""
    try:
        parsed = []
        for d in dates[:10]:  # Sample first 10
            if "T" in d:
                parsed.append(datetime.datetime.fromisoformat(d.replace("Z", "+00:00")))
            else:
                parsed.append(datetime.datetime.fromisoformat(d))

        if len(parsed) < 2:
            return f"Repeating ({count} occurrences)"

        deltas = [(parsed[i + 1] - parsed[i]).days for i in range(len(parsed) - 1)]
        avg_delta = sum(deltas) / len(deltas)

        if 0.8 <= avg_delta <= 1.2:
            return f"Daily ({count} occurrences)"
        elif 6 <= avg_delta <= 8:
            return f"Weekly ({count} occurrences)"
        elif 13 <= avg_delta <= 15:
            return f"Biweekly ({count} occurrences)"
        elif 28 <= avg_delta <= 32:
            return f"Monthly ({count} occurrences)"
        elif 360 <= avg_delta <= 370:
            return f"Yearly ({count} occurrences)"
        else:
            return f"Repeating every ~{int(avg_delta)} days ({count} occurrences)"
    except Exception:
        return f"Repeating ({count} occurrences)"
