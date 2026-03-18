"""
pCloud integration — OAuth2, file listing, and ingestion.
Uses pCloud HTTP API directly (no SDK dependency).
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

SERVICE = "pcloud"
# pCloud has two data centers — US and EU
AUTH_URL = "https://my.pcloud.com/oauth2/authorize"
TOKEN_URL_US = "https://api.pcloud.com/oauth2_token"
TOKEN_URL_EU = "https://eapi.pcloud.com/oauth2_token"
API_BASE_US = "https://api.pcloud.com"
API_BASE_EU = "https://eapi.pcloud.com"

_pending_oauth: dict[str, dict] = {}


def _api_base(region: str = "us") -> str:
    return API_BASE_EU if region == "eu" else API_BASE_US


def _token_url(region: str = "us") -> str:
    return TOKEN_URL_EU if region == "eu" else TOKEN_URL_US


def get_status() -> dict:
    creds = load_credentials(SERVICE)
    accounts = list_accounts(SERVICE)
    return {
        "has_credentials": creds is not None,
        "accounts": [
            {
                "email": a.get("email", a.get("userid", "?")),
                "connected": bool(a.get("access_token")),
                "connected_at": a.get("connected_at", ""),
            }
            for a in accounts
        ],
    }


def start_oauth_flow() -> dict:
    creds = load_credentials(SERVICE)
    if not creds:
        return {"error": "No pCloud app credentials configured. Upload them first."}

    client_id = creds.get("client_id", "")
    redirect_uri = creds.get("redirect_uri", "http://localhost:8000/api/pcloud/callback")

    state = secrets.token_urlsafe(32)
    _pending_oauth[state] = {"redirect_uri": redirect_uri}

    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "state": state,
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
    region = creds.get("region", "us")

    resp = requests.get(_token_url(region), params={
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
    })

    if resp.status_code != 200:
        return {"error": f"Token exchange failed: {resp.text}"}

    data = resp.json()
    if "error" in data:
        return {"error": data.get("error")}

    access_token = data.get("access_token", "")
    userid = str(data.get("userid", ""))

    # Get user info
    info_resp = requests.get(f"{_api_base(region)}/userinfo", params={"access_token": access_token})
    email = userid
    if info_resp.status_code == 200:
        info = info_resp.json()
        email = info.get("email", userid)

    account_data = {
        "email": email,
        "userid": userid,
        "access_token": access_token,
        "region": region,
        "connected_at": datetime.datetime.now().isoformat(),
    }
    save_account(SERVICE, email, account_data)
    add_event("success", "pcloud", f"Connected pCloud account: {email}")
    return {"success": True, "email": email}


def _get_token(email: str) -> tuple[Optional[str], str]:
    """Return (access_token, region)."""
    acct = load_account(SERVICE, email)
    return acct.get("access_token"), acct.get("region", "us")


def disconnect(email: str):
    delete_account(SERVICE, email)
    add_event("info", "pcloud", f"Disconnected pCloud: {email}")


def list_files(email: str, folder_id: int = 0, query: str = "",
               file_type: str = "", max_results: int = 30) -> dict:
    token, region = _get_token(email)
    if not token:
        return {"error": f"Account {email} not connected."}

    base = _api_base(region)

    if query:
        # pCloud doesn't have search API — list folder and filter client-side
        pass

    params = {"access_token": token, "folderid": folder_id}
    resp = requests.get(f"{base}/listfolder", params=params)

    if resp.status_code != 200:
        return {"error": f"pCloud list failed: {resp.text}"}

    data = resp.json()
    if data.get("error"):
        return {"error": data.get("error")}

    contents = data.get("metadata", {}).get("contents", [])
    files = []
    for item in contents:
        if item.get("isfolder"):
            continue
        name = item.get("name", "")
        # Apply filters
        if query and query.lower() not in name.lower():
            continue
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
            "id": str(item.get("fileid", "")),
            "name": name,
            "path": item.get("path", ""),
            "size": str(item.get("size", 0)),
            "modifiedTime": item.get("modified", ""),
            "already_synced": False,
        })
        if len(files) >= max_results:
            break

    return {"files": files}


def download_file(email: str, file_id: str) -> Optional[bytes]:
    token, region = _get_token(email)
    if not token:
        return None
    base = _api_base(region)
    # Get file link
    resp = requests.get(f"{base}/getfilelink", params={
        "access_token": token, "fileid": file_id,
    })
    if resp.status_code != 200:
        return None
    data = resp.json()
    hosts = data.get("hosts", [])
    path = data.get("path", "")
    if not hosts or not path:
        return None
    download_url = f"https://{hosts[0]}{path}"
    dl_resp = requests.get(download_url)
    if dl_resp.status_code == 200:
        return dl_resp.content
    return None


def ingest_files(email: str, file_ids: list[str]) -> dict:
    from ingest import ingest_document
    from db import add_memory
    from llm import get_embedding, categorize_and_extract
    from scrubber import scrub_text

    # Need file names too — get from listing
    token, region = _get_token(email)
    ingested = []
    errors = []

    for fid in file_ids:
        try:
            content = download_file(email, fid)
            if not content:
                errors.append({"id": fid, "error": "Download failed"})
                continue
            # Get file info for name
            base = _api_base(region)
            info = requests.get(f"{base}/stat", params={"access_token": token, "fileid": fid})
            filename = f"pcloud_file_{fid}"
            if info.status_code == 200:
                filename = info.json().get("metadata", {}).get("name", filename)

            result = ingest_document(filename, content)
            text = scrub_text(result["text"])
            extracted = categorize_and_extract(text)
            embedding = get_embedding(text)
            metadata = {**extracted, "source_file": filename, "pcloud_id": fid, "import_source": "pcloud"}
            mid = add_memory(content=text, source_type="pcloud", embedding=embedding, metadata=metadata)
            ingested.append({"id": fid, "memory_id": mid, "name": filename})
        except Exception as e:
            errors.append({"id": fid, "error": str(e)})

    add_event("success" if not errors else "warning", "pcloud",
              f"Ingested {len(ingested)}/{len(file_ids)} files from pCloud")
    return {"ingested": ingested, "errors": errors}
