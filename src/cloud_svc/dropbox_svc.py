"""
Dropbox integration — OAuth2, file search, and ingestion.
Uses Dropbox HTTP API v2 directly (no SDK dependency).
"""
import requests
import urllib.parse
import secrets
import datetime
from typing import Optional

from cloud_svc.common import (
    load_account, save_account, delete_account, list_accounts,
    load_credentials, save_credentials, has_credentials,
)
from event_log import add_event

SERVICE = "dropbox"
AUTH_URL = "https://www.dropbox.com/oauth2/authorize"
TOKEN_URL = "https://api.dropboxapi.com/oauth2/token"
API_BASE = "https://api.dropboxapi.com/2"
CONTENT_BASE = "https://content.dropboxapi.com/2"

# In-memory store for pending OAuth flows
_pending_oauth: dict[str, dict] = {}  # state -> {code_verifier, ...}


def get_status() -> dict:
    """Return credentials status and connected accounts."""
    creds = load_credentials(SERVICE)
    accounts = list_accounts(SERVICE)
    return {
        "has_credentials": creds is not None,
        "accounts": [
            {
                "email": a.get("email", a.get("account_id", "?")),
                "name": a.get("name", ""),
                "connected": bool(a.get("access_token")),
                "connected_at": a.get("connected_at", ""),
            }
            for a in accounts
        ],
    }


def start_oauth_flow() -> dict:
    """Start Dropbox OAuth2 flow. Returns auth_url for the user to visit."""
    creds = load_credentials(SERVICE)
    if not creds:
        return {"error": "No Dropbox app credentials configured. Upload them first."}

    app_key = creds.get("app_key", "")
    redirect_uri = creds.get("redirect_uri", "http://localhost:8000/api/dropbox/callback")

    state = secrets.token_urlsafe(32)
    # PKCE
    code_verifier = secrets.token_urlsafe(64)
    import hashlib, base64
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode()).digest()
    ).rstrip(b"=").decode()

    _pending_oauth[state] = {"code_verifier": code_verifier}

    params = {
        "client_id": app_key,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "token_access_type": "offline",
    }
    auth_url = f"{AUTH_URL}?{urllib.parse.urlencode(params)}"
    return {"auth_url": auth_url, "state": state}


def complete_oauth_flow(code: str, state: str) -> dict:
    """Complete OAuth2 flow with authorization code."""
    pending = _pending_oauth.pop(state, None)
    if not pending:
        return {"error": "Invalid or expired OAuth state."}

    creds = load_credentials(SERVICE)
    if not creds:
        return {"error": "No credentials configured."}

    app_key = creds.get("app_key", "")
    app_secret = creds.get("app_secret", "")
    redirect_uri = creds.get("redirect_uri", "http://localhost:8000/api/dropbox/callback")

    resp = requests.post(TOKEN_URL, data={
        "code": code,
        "grant_type": "authorization_code",
        "client_id": app_key,
        "client_secret": app_secret,
        "redirect_uri": redirect_uri,
        "code_verifier": pending["code_verifier"],
    })

    if resp.status_code != 200:
        return {"error": f"Token exchange failed: {resp.text}"}

    token_data = resp.json()
    account_id = token_data.get("account_id", "")

    # Get account info
    info_resp = requests.post(
        f"{API_BASE}/users/get_current_account",
        headers={"Authorization": f"Bearer {token_data['access_token']}"},
    )
    email = account_id
    name = ""
    if info_resp.status_code == 200:
        info = info_resp.json()
        email = info.get("email", account_id)
        name = info.get("name", {}).get("display_name", "")

    account_data = {
        "email": email,
        "name": name,
        "account_id": account_id,
        "access_token": token_data.get("access_token"),
        "refresh_token": token_data.get("refresh_token"),
        "expires_in": token_data.get("expires_in"),
        "connected_at": datetime.datetime.now().isoformat(),
    }
    save_account(SERVICE, email, account_data)
    add_event("success", "dropbox", f"Connected Dropbox account: {email}")
    return {"success": True, "email": email, "name": name}


def _get_token(email: str) -> Optional[str]:
    """Get a valid access token, refreshing if needed."""
    acct = load_account(SERVICE, email)
    token = acct.get("access_token")
    refresh = acct.get("refresh_token")
    if not token:
        return None

    # Try refreshing if we have a refresh token
    if refresh:
        creds = load_credentials(SERVICE)
        if creds:
            resp = requests.post(TOKEN_URL, data={
                "grant_type": "refresh_token",
                "refresh_token": refresh,
                "client_id": creds.get("app_key", ""),
                "client_secret": creds.get("app_secret", ""),
            })
            if resp.status_code == 200:
                new_data = resp.json()
                acct["access_token"] = new_data.get("access_token", token)
                save_account(SERVICE, email, acct)
                return acct["access_token"]

    return token


def disconnect(email: str):
    delete_account(SERVICE, email)
    add_event("info", "dropbox", f"Disconnected Dropbox: {email}")


def search_files(email: str, query: str = "", path: str = "",
                 file_type: str = "", max_results: int = 30) -> dict:
    """Search Dropbox files."""
    token = _get_token(email)
    if not token:
        return {"error": f"Account {email} not connected or token expired."}

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    if query:
        # Use search_v2
        payload: dict = {
            "query": query,
            "options": {"max_results": min(max_results, 100)},
        }
        if path:
            payload["options"]["path"] = path
        if file_type:
            ext_map = {
                "document": [".doc", ".docx", ".pdf", ".txt", ".md"],
                "spreadsheet": [".xls", ".xlsx", ".csv"],
                "image": [".jpg", ".jpeg", ".png", ".gif", ".webp"],
                "pdf": [".pdf"],
            }
            payload["options"]["file_extensions"] = ext_map.get(file_type, [])

        resp = requests.post(f"{API_BASE}/files/search_v2", headers=headers, json=payload)
        if resp.status_code != 200:
            return {"error": f"Dropbox search failed: {resp.text}"}
        data = resp.json()
        files = []
        for match in data.get("matches", []):
            meta = match.get("metadata", {}).get("metadata", {})
            if meta.get(".tag") == "file":
                files.append({
                    "id": meta.get("id", ""),
                    "name": meta.get("name", ""),
                    "path": meta.get("path_display", ""),
                    "size": str(meta.get("size", 0)),
                    "modifiedTime": meta.get("server_modified", ""),
                    "already_synced": False,
                })
        return {"files": files}
    else:
        # List folder
        folder_path = path or ""
        payload = {"path": folder_path, "limit": min(max_results, 100)}
        resp = requests.post(f"{API_BASE}/files/list_folder", headers=headers, json=payload)
        if resp.status_code != 200:
            return {"error": f"Dropbox list failed: {resp.text}"}
        data = resp.json()
        files = []
        for entry in data.get("entries", []):
            if entry.get(".tag") == "file":
                files.append({
                    "id": entry.get("id", ""),
                    "name": entry.get("name", ""),
                    "path": entry.get("path_display", ""),
                    "size": str(entry.get("size", 0)),
                    "modifiedTime": entry.get("server_modified", ""),
                    "already_synced": False,
                })
        return {"files": files}


def download_file(email: str, file_path: str) -> Optional[bytes]:
    """Download a file from Dropbox by path."""
    token = _get_token(email)
    if not token:
        return None
    import json as _json
    headers = {
        "Authorization": f"Bearer {token}",
        "Dropbox-API-Arg": _json.dumps({"path": file_path}),
    }
    resp = requests.post(f"{CONTENT_BASE}/files/download", headers=headers)
    if resp.status_code == 200:
        return resp.content
    return None


def ingest_files(email: str, file_paths: list[str]) -> dict:
    """Download and ingest files from Dropbox."""
    from ingest import ingest_document
    from db import add_memory
    from llm import get_embedding, categorize_and_extract
    from scrubber import scrub_text

    ingested = []
    errors = []

    for fpath in file_paths:
        try:
            content = download_file(email, fpath)
            if not content:
                errors.append({"path": fpath, "error": "Download failed"})
                continue
            filename = fpath.split("/")[-1]
            result = ingest_document(filename, content)
            text = scrub_text(result["text"])
            extracted = categorize_and_extract(text)
            embedding = get_embedding(text)
            metadata = {
                **extracted,
                "source_file": filename,
                "dropbox_path": fpath,
                "import_source": "dropbox",
            }
            mid = add_memory(content=text, source_type="dropbox", embedding=embedding, metadata=metadata)
            ingested.append({"path": fpath, "id": mid})
        except Exception as e:
            errors.append({"path": fpath, "error": str(e)})

    add_event(
        "success" if not errors else "warning",
        "dropbox",
        f"Ingested {len(ingested)}/{len(file_paths)} files from Dropbox",
    )
    return {"ingested": ingested, "errors": errors}
