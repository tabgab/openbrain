"""
Google OAuth 2.0 & multi-account management.
Handles token storage, refresh, OAuth flow, and account listing.
"""
import os
import json
import datetime
import re
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/photospicker.mediaitems.readonly",
]

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
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
                "photos_last_sync": data.get("photos_last_sync"),
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
