"""
Microsoft 365 integration — OAuth2, OneDrive, Outlook, Calendar via Microsoft Graph API.
Uses HTTP API directly (no SDK dependency).
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

SERVICE = "microsoft"
AUTH_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
GRAPH_BASE = "https://graph.microsoft.com/v1.0"

SCOPES = "offline_access User.Read Files.Read Mail.Read Calendars.Read"

_pending_oauth: dict[str, dict] = {}


def get_status() -> dict:
    creds = load_credentials(SERVICE)
    accounts = list_accounts(SERVICE)
    return {
        "has_credentials": creds is not None,
        "accounts": [
            {
                "email": a.get("email", "?"),
                "name": a.get("name", ""),
                "connected": bool(a.get("access_token")),
                "connected_at": a.get("connected_at", ""),
            }
            for a in accounts
        ],
    }


def start_oauth_flow() -> dict:
    creds = load_credentials(SERVICE)
    if not creds:
        return {"error": "No Microsoft app credentials configured. Upload them first."}

    client_id = creds.get("client_id", "")
    redirect_uri = creds.get("redirect_uri", "http://localhost:8000/api/microsoft/callback")

    state = secrets.token_urlsafe(32)
    # PKCE
    code_verifier = secrets.token_urlsafe(64)
    import hashlib, base64
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode()).digest()
    ).rstrip(b"=").decode()

    _pending_oauth[state] = {"code_verifier": code_verifier}

    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": SCOPES,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    auth_url = f"{AUTH_URL}?{urllib.parse.urlencode(params)}"
    return {"auth_url": auth_url, "state": state}


def complete_oauth_flow(code: str, state: str) -> dict:
    pending = _pending_oauth.pop(state, None)
    if not pending:
        return {"error": "Invalid or expired OAuth state."}

    creds = load_credentials(SERVICE)
    if not creds:
        return {"error": "No credentials configured."}

    client_id = creds.get("client_id", "")
    client_secret = creds.get("client_secret", "")
    redirect_uri = creds.get("redirect_uri", "http://localhost:8000/api/microsoft/callback")

    resp = requests.post(TOKEN_URL, data={
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
        "code_verifier": pending["code_verifier"],
    })

    if resp.status_code != 200:
        return {"error": f"Token exchange failed: {resp.text}"}

    token_data = resp.json()

    # Get user info
    headers = {"Authorization": f"Bearer {token_data['access_token']}"}
    me_resp = requests.get(f"{GRAPH_BASE}/me", headers=headers)
    email = ""
    name = ""
    if me_resp.status_code == 200:
        me = me_resp.json()
        email = me.get("mail") or me.get("userPrincipalName", "")
        name = me.get("displayName", "")

    account_data = {
        "email": email,
        "name": name,
        "access_token": token_data.get("access_token"),
        "refresh_token": token_data.get("refresh_token"),
        "expires_in": token_data.get("expires_in"),
        "connected_at": datetime.datetime.now().isoformat(),
    }
    save_account(SERVICE, email, account_data)
    add_event("success", "microsoft", f"Connected Microsoft account: {email}")
    return {"success": True, "email": email, "name": name}


def _refresh_token(email: str) -> Optional[str]:
    """Refresh and return a valid access token."""
    acct = load_account(SERVICE, email)
    refresh = acct.get("refresh_token")
    if not refresh:
        return acct.get("access_token")

    creds = load_credentials(SERVICE)
    if not creds:
        return acct.get("access_token")

    resp = requests.post(TOKEN_URL, data={
        "client_id": creds.get("client_id", ""),
        "client_secret": creds.get("client_secret", ""),
        "refresh_token": refresh,
        "grant_type": "refresh_token",
        "scope": SCOPES,
    })
    if resp.status_code == 200:
        new_data = resp.json()
        acct["access_token"] = new_data.get("access_token", acct.get("access_token"))
        if new_data.get("refresh_token"):
            acct["refresh_token"] = new_data["refresh_token"]
        save_account(SERVICE, email, acct)
        return acct["access_token"]
    return acct.get("access_token")


def _headers(email: str) -> dict:
    token = _refresh_token(email)
    return {"Authorization": f"Bearer {token}"} if token else {}


def disconnect(email: str):
    delete_account(SERVICE, email)
    add_event("info", "microsoft", f"Disconnected Microsoft: {email}")


# --- OneDrive ---

def search_onedrive(email: str, query: str = "", file_type: str = "",
                    max_results: int = 30) -> dict:
    """Search OneDrive files."""
    h = _headers(email)
    if not h:
        return {"error": f"Account {email} not connected."}

    if query:
        url = f"{GRAPH_BASE}/me/drive/root/search(q='{urllib.parse.quote(query)}')"
        params = {"$top": min(max_results, 50)}
    else:
        url = f"{GRAPH_BASE}/me/drive/root/children"
        params = {"$top": min(max_results, 50)}

    resp = requests.get(url, headers=h, params=params)
    if resp.status_code != 200:
        return {"error": f"OneDrive search failed: {resp.text}"}

    data = resp.json()
    files = []
    for item in data.get("value", []):
        if "folder" in item:
            continue  # skip folders
        name = item.get("name", "")
        if file_type:
            ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
            type_map = {
                "document": ["doc", "docx", "pdf", "txt", "md"],
                "spreadsheet": ["xls", "xlsx", "csv"],
                "image": ["jpg", "jpeg", "png", "gif", "webp"],
                "pdf": ["pdf"],
            }
            allowed = type_map.get(file_type, [])
            if allowed and ext not in allowed:
                continue
        files.append({
            "id": item.get("id", ""),
            "name": name,
            "size": str(item.get("size", 0)),
            "modifiedTime": item.get("lastModifiedDateTime", ""),
            "mimeType": item.get("file", {}).get("mimeType", ""),
            "already_synced": False,
        })
    return {"files": files}


def download_onedrive_file(email: str, file_id: str) -> Optional[bytes]:
    h = _headers(email)
    if not h:
        return None
    resp = requests.get(f"{GRAPH_BASE}/me/drive/items/{file_id}/content", headers=h, allow_redirects=True)
    if resp.status_code == 200:
        return resp.content
    return None


def ingest_onedrive_files(email: str, file_ids: list[str]) -> dict:
    from ingest import ingest_document
    from db import add_memory
    from llm import get_embedding, categorize_and_extract
    from scrubber import scrub_text

    h = _headers(email)
    ingested = []
    errors = []

    for fid in file_ids:
        try:
            # Get file metadata for name
            meta_resp = requests.get(f"{GRAPH_BASE}/me/drive/items/{fid}", headers=h)
            filename = f"onedrive_{fid}"
            if meta_resp.status_code == 200:
                filename = meta_resp.json().get("name", filename)

            content = download_onedrive_file(email, fid)
            if not content:
                errors.append({"id": fid, "error": "Download failed"})
                continue

            result = ingest_document(filename, content)
            text = scrub_text(result["text"])
            extracted = categorize_and_extract(text)
            embedding = get_embedding(text)
            metadata = {**extracted, "source_file": filename, "onedrive_id": fid, "import_source": "microsoft_onedrive"}
            mid = add_memory(content=text, source_type="microsoft_onedrive", embedding=embedding, metadata=metadata)
            ingested.append({"id": fid, "memory_id": mid, "name": filename})
        except Exception as e:
            errors.append({"id": fid, "error": str(e)})

    add_event("success" if not errors else "warning", "microsoft",
              f"Ingested {len(ingested)}/{len(file_ids)} OneDrive files")
    return {"ingested": ingested, "errors": errors}


# --- Outlook ---

def search_outlook(email: str, query: str = "", from_filter: str = "",
                   subject_filter: str = "", folder: str = "inbox",
                   newer_than_days: int = 7, max_results: int = 30) -> dict:
    """Search Outlook messages via Microsoft Graph."""
    h = _headers(email)
    if not h:
        return {"error": f"Account {email} not connected."}

    # Build $filter
    filters = []
    cutoff = (datetime.datetime.now() - datetime.timedelta(days=newer_than_days)).isoformat() + "Z"
    filters.append(f"receivedDateTime ge {cutoff}")
    if from_filter:
        filters.append(f"contains(from/emailAddress/address, '{from_filter}')")
    if subject_filter:
        filters.append(f"contains(subject, '{subject_filter}')")

    params: dict = {
        "$top": min(max_results, 50),
        "$orderby": "receivedDateTime desc",
        "$select": "id,subject,from,receivedDateTime,bodyPreview,isRead",
    }
    if filters:
        params["$filter"] = " and ".join(filters)
    if query:
        params["$search"] = f'"{query}"'
        params.pop("$filter", None)  # $search and $filter can't combine

    url = f"{GRAPH_BASE}/me/mailFolders/{folder}/messages"
    resp = requests.get(url, headers=h, params=params)
    if resp.status_code != 200:
        return {"error": f"Outlook search failed: {resp.text}"}

    data = resp.json()
    messages = []
    for msg in data.get("value", []):
        messages.append({
            "id": msg.get("id", ""),
            "from": msg.get("from", {}).get("emailAddress", {}).get("address", ""),
            "from_name": msg.get("from", {}).get("emailAddress", {}).get("name", ""),
            "subject": msg.get("subject", "(no subject)"),
            "date": msg.get("receivedDateTime", ""),
            "snippet": msg.get("bodyPreview", "")[:200],
            "already_synced": False,
        })
    return {"messages": messages, "total": len(messages)}


def ingest_outlook_messages(email: str, message_ids: list[str]) -> dict:
    from db import add_memory
    from llm import get_embedding, categorize_and_extract
    from scrubber import scrub_text

    h = _headers(email)
    ingested = []
    errors = []

    for mid_str in message_ids:
        try:
            resp = requests.get(
                f"{GRAPH_BASE}/me/messages/{mid_str}",
                headers=h,
                params={"$select": "id,subject,from,toRecipients,receivedDateTime,body"},
            )
            if resp.status_code != 200:
                errors.append({"id": mid_str, "error": "Fetch failed"})
                continue

            msg = resp.json()
            from_addr = msg.get("from", {}).get("emailAddress", {}).get("address", "")
            subject = msg.get("subject", "")
            date = msg.get("receivedDateTime", "")
            body_content = msg.get("body", {}).get("content", "")
            body_type = msg.get("body", {}).get("contentType", "text")

            if body_type == "html":
                import re
                body_content = re.sub(r"<[^>]+>", " ", body_content)

            parts = [f"Subject: {subject}", f"From: {from_addr}", f"Date: {date}", "", body_content[:8000]]
            content = "\n".join(parts)
            content = scrub_text(content)
            extracted = categorize_and_extract(content)
            embedding = get_embedding(content)
            metadata = {
                **extracted,
                "email_from": from_addr,
                "email_subject": subject,
                "email_date": date,
                "import_source": "microsoft_outlook",
            }
            mem_id = add_memory(content=content, source_type="microsoft_outlook", embedding=embedding, metadata=metadata)
            ingested.append({"id": mid_str, "memory_id": mem_id, "subject": subject})
        except Exception as e:
            errors.append({"id": mid_str, "error": str(e)})

    add_event("success" if not errors else "warning", "microsoft",
              f"Ingested {len(ingested)}/{len(message_ids)} Outlook emails")
    return {"ingested": ingested, "errors": errors}


# --- Calendar ---

def scan_calendar(email: str, days_back: int = 30, days_forward: int = 30) -> dict:
    """Fetch calendar events from Microsoft 365."""
    h = _headers(email)
    if not h:
        return {"error": f"Account {email} not connected."}

    start = (datetime.datetime.now() - datetime.timedelta(days=days_back)).isoformat() + "Z"
    end = (datetime.datetime.now() + datetime.timedelta(days=days_forward)).isoformat() + "Z"

    url = f"{GRAPH_BASE}/me/calendarView"
    params = {
        "startDateTime": start,
        "endDateTime": end,
        "$top": 100,
        "$orderby": "start/dateTime",
        "$select": "id,subject,start,end,location,body,organizer,isAllDay,recurrence",
    }
    resp = requests.get(url, headers=h, params=params)
    if resp.status_code != 200:
        return {"error": f"Calendar fetch failed: {resp.text}"}

    data = resp.json()
    events = []
    for ev in data.get("value", []):
        events.append({
            "id": ev.get("id", ""),
            "summary": ev.get("subject", ""),
            "start": ev.get("start", {}).get("dateTime", ""),
            "end": ev.get("end", {}).get("dateTime", ""),
            "location": ev.get("location", {}).get("displayName", ""),
            "description": ev.get("body", {}).get("content", "")[:500],
            "is_all_day": ev.get("isAllDay", False),
            "is_recurring": ev.get("recurrence") is not None,
            "already_synced": False,
        })
    return {"events": events, "total": len(events)}


def ingest_calendar_events(email: str, event_ids: list[str]) -> dict:
    from db import add_memory
    from llm import get_embedding, categorize_and_extract
    from scrubber import scrub_text

    h = _headers(email)
    ingested = []
    errors = []

    for eid in event_ids:
        try:
            resp = requests.get(f"{GRAPH_BASE}/me/events/{eid}", headers=h)
            if resp.status_code != 200:
                errors.append({"id": eid, "error": "Fetch failed"})
                continue
            ev = resp.json()
            parts = [
                f"Calendar Event: {ev.get('subject', '')}",
                f"Start: {ev.get('start', {}).get('dateTime', '')}",
                f"End: {ev.get('end', {}).get('dateTime', '')}",
            ]
            loc = ev.get("location", {}).get("displayName", "")
            if loc:
                parts.append(f"Location: {loc}")
            body = ev.get("body", {}).get("content", "")
            if body:
                import re
                body = re.sub(r"<[^>]+>", " ", body)[:2000]
                parts.append(f"\n{body}")

            content = scrub_text("\n".join(parts))
            extracted = categorize_and_extract(content)
            embedding = get_embedding(content)
            metadata = {**extracted, "event_id": eid, "import_source": "microsoft_calendar"}
            mem_id = add_memory(content=content, source_type="microsoft_calendar", embedding=embedding, metadata=metadata)
            ingested.append({"id": eid, "memory_id": mem_id})
        except Exception as e:
            errors.append({"id": eid, "error": str(e)})

    add_event("success" if not errors else "warning", "microsoft",
              f"Ingested {len(ingested)}/{len(event_ids)} calendar events")
    return {"ingested": ingested, "errors": errors}
