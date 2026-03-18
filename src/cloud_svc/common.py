"""
Shared utilities for cloud service integrations.
Token storage, account management, and OAuth helpers.
"""
import json
import re
import os
from pathlib import Path
from typing import Optional

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _accounts_dir(service: str) -> Path:
    """Return the accounts directory for a cloud service."""
    d = _PROJECT_ROOT / f"{service}_accounts"
    d.mkdir(exist_ok=True)
    return d


def _credentials_file(service: str) -> Path:
    """Return the credentials file path for a service."""
    return _PROJECT_ROOT / f"{service}_credentials.json"


def _account_file(service: str, email_or_id: str) -> Path:
    safe = re.sub(r"[^a-zA-Z0-9@._-]", "_", email_or_id)
    return _accounts_dir(service) / f"{safe}.json"


def load_account(service: str, email_or_id: str) -> dict:
    f = _account_file(service, email_or_id)
    if f.exists():
        return json.loads(f.read_text())
    return {}


def save_account(service: str, email_or_id: str, data: dict):
    _account_file(service, email_or_id).write_text(json.dumps(data, indent=2))


def delete_account(service: str, email_or_id: str):
    f = _account_file(service, email_or_id)
    if f.exists():
        f.unlink()


def list_accounts(service: str) -> list[dict]:
    d = _accounts_dir(service)
    accounts = []
    for f in sorted(d.glob("*.json")):
        try:
            data = json.loads(f.read_text())
            accounts.append(data)
        except Exception:
            continue
    return accounts


def load_credentials(service: str) -> Optional[dict]:
    f = _credentials_file(service)
    if f.exists():
        try:
            return json.loads(f.read_text())
        except Exception:
            return None
    return None


def save_credentials(service: str, data: dict):
    _credentials_file(service).write_text(json.dumps(data, indent=2))


def has_credentials(service: str) -> bool:
    return _credentials_file(service).exists()
