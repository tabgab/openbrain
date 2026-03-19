"""
MEGA integration — email/password login, file listing, and ingestion.
Uses the mega.py library. MEGA is end-to-end encrypted so there is no
OAuth flow; users authenticate with their MEGA email and password.
"""
import datetime
import io
import json
import tempfile
from typing import Optional

from mega import Mega

from cloud_svc.common import (
    load_account, save_account, delete_account, list_accounts,
)
from event_log import add_event

SERVICE = "mega"

# Cache logged-in Mega instances per email to avoid re-login on every call
_sessions: dict[str, object] = {}


def get_status() -> dict:
    accounts = list_accounts(SERVICE)
    return {
        "accounts": [
            {
                "email": a.get("email", "?"),
                "connected": True,
                "connected_at": a.get("connected_at", ""),
            }
            for a in accounts
        ],
    }


def connect(email: str, password: str) -> dict:
    """Log in to MEGA with email and password. Store session details."""
    if not email or not password:
        return {"error": "Email and password are required."}
    try:
        mega = Mega()
        m = mega.login(email, password)
        # Verify login worked by getting user info
        user = m.get_user()
        account_data = {
            "email": email,
            "password": password,  # needed for re-login (MEGA has no refresh tokens)
            "connected_at": datetime.datetime.now().isoformat(),
        }
        save_account(SERVICE, email, account_data)
        _sessions[email] = m
        add_event("success", "mega", f"Connected MEGA account: {email}")
        return {"success": True, "email": email}
    except json.JSONDecodeError:
        # MEGA returns HTTP 402 with empty body for wrong password
        return {"error": "Invalid email or password."}
    except Exception as e:
        msg = str(e)
        if "ENOENT" in msg or "-9" in msg:
            return {"error": "Invalid email or password."}
        if "-16" in msg:
            return {"error": "Account temporarily blocked. Try again later."}
        if "RequestError" in type(e).__name__:
            return {"error": "Invalid email or password."}
        return {"error": f"MEGA login failed: {msg}"}


def _get_session(email: str):
    """Return a logged-in Mega instance, re-authenticating if needed."""
    if email in _sessions:
        return _sessions[email]
    acct = load_account(SERVICE, email)
    if not acct.get("password"):
        return None
    try:
        mega = Mega()
        m = mega.login(acct["email"], acct["password"])
        _sessions[email] = m
        return m
    except Exception:
        return None


def disconnect(email: str):
    _sessions.pop(email, None)
    delete_account(SERVICE, email)
    add_event("info", "mega", f"Disconnected MEGA: {email}")


def list_files(email: str, query: str = "", file_type: str = "",
               max_results: int = 500) -> dict:
    """List files from MEGA. Client-side filtering (MEGA has no search API)."""
    m = _get_session(email)
    if not m:
        return {"error": f"Account {email} not connected or session expired."}

    try:
        all_files = m.get_files()
    except Exception as e:
        # Session may have expired — clear and retry once
        _sessions.pop(email, None)
        m = _get_session(email)
        if not m:
            return {"error": f"Session expired. Please reconnect. ({e})"}
        try:
            all_files = m.get_files()
        except Exception as e2:
            return {"error": f"Failed to list files: {e2}"}

    type_map = {
        "document": ["doc", "docx", "pdf", "txt", "md"],
        "spreadsheet": ["xls", "xlsx", "csv"],
        "image": ["jpg", "jpeg", "png", "gif", "webp"],
        "pdf": ["pdf"],
    }

    files = []
    for node_id, node in all_files.items():
        # Type 0 = file, 1 = folder, 2 = root, 3 = inbox, 4 = trash
        if node.get("t") != 0:
            continue
        name = node.get("a", {}).get("n", "")
        if not name:
            continue

        # Query filter
        if query and query.lower() not in name.lower():
            continue

        # File type filter
        if file_type:
            ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
            allowed = type_map.get(file_type, [])
            if allowed and ext not in allowed:
                continue

        files.append({
            "id": str(node_id),
            "name": name,
            "size": str(node.get("s", 0)),
            "modifiedTime": datetime.datetime.fromtimestamp(
                node.get("ts", 0)
            ).isoformat() if node.get("ts") else "",
            "already_synced": False,
        })
        if len(files) >= max_results:
            break

    return {"files": files}


def download_file(email: str, file_id: str) -> Optional[bytes]:
    """Download a file from MEGA by node ID."""
    m = _get_session(email)
    if not m:
        return None
    try:
        all_files = m.get_files()
        node = all_files.get(file_id)
        if not node:
            return None
        # mega.py download writes to a file; use a temp file
        with tempfile.TemporaryDirectory() as tmpdir:
            m.download((file_id, node), tmpdir)
            name = node.get("a", {}).get("n", "file")
            import os
            downloaded = os.path.join(tmpdir, name)
            if os.path.exists(downloaded):
                with open(downloaded, "rb") as f:
                    return f.read()
        return None
    except Exception:
        return None


def ingest_files(email: str, file_ids: list[str]) -> dict:
    from ingest import ingest_document
    from db import add_memory
    from llm import get_embedding, categorize_and_extract
    from scrubber import scrub_text

    m = _get_session(email)
    if not m:
        return {"error": f"Account {email} not connected."}

    ingested = []
    errors = []

    try:
        all_files = m.get_files()
    except Exception as e:
        return {"error": f"Failed to get file list: {e}"}

    for fid in file_ids:
        try:
            node = all_files.get(fid)
            if not node:
                errors.append({"id": fid, "error": "File not found"})
                continue
            filename = node.get("a", {}).get("n", f"mega_file_{fid}")

            content = download_file(email, fid)
            if not content:
                errors.append({"id": fid, "error": "Download failed"})
                continue

            result = ingest_document(filename, content)
            text = scrub_text(result["text"])
            extracted = categorize_and_extract(text)
            embedding = get_embedding(text)
            metadata = {
                **extracted,
                "source_file": filename,
                "mega_id": fid,
                "import_source": "mega",
            }
            mid = add_memory(
                content=text, source_type="mega",
                embedding=embedding, metadata=metadata,
            )
            ingested.append({"id": fid, "memory_id": mid, "name": filename})
        except Exception as e:
            errors.append({"id": fid, "error": str(e)})

    add_event(
        "success" if not errors else "warning", "mega",
        f"Ingested {len(ingested)}/{len(file_ids)} files from MEGA",
    )
    return {"ingested": ingested, "errors": errors}
