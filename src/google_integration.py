"""
Open Brain — Google Drive & Gmail Integration (Multi-Account)
--------------------------------------------------------------
Handles:
  - OAuth 2.0 flow with multiple Google accounts
  - Google Drive: search/filter files → preview → selective ingest
  - Gmail: search/filter emails → preview → selective ingest

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
