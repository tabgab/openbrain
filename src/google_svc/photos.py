"""
Google Photos — Picker API Sessions / Download / Ingest via vision model
"""
import datetime
import requests as http_requests

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from google_svc.auth import get_credentials_for, _load_account, _save_account

_PHOTOS_PICKER_BASE = "https://photospicker.googleapis.com/v1"


def _photos_headers(creds: Credentials) -> dict:
    """Build auth headers for Photos Picker API (REST, not discovery-based)."""
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return {"Authorization": f"Bearer {creds.token}", "Content-Type": "application/json"}


def create_photos_session(email: str, max_items: int = 100) -> dict:
    """Create a Google Photos Picker session. Returns the picker URI for the user to open.

    The Picker API itself handles all filtering — the user searches and selects
    photos in Google's native picker UI. The only config option is maxItemCount.

    Args:
        max_items: maximum number of items the user can pick (default 100, max 2000)
    """
    creds = get_credentials_for(email)
    if not creds:
        return {"error": f"Account {email} not connected or token expired."}

    body: dict = {}
    if max_items and max_items > 0:
        body["pickingConfig"] = {"maxItemCount": str(min(max_items, 2000))}

    try:
        resp = http_requests.post(
            f"{_PHOTOS_PICKER_BASE}/sessions",
            headers=_photos_headers(creds),
            json=body,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        # Append /autoclose so the picker tab closes automatically when user is done
        picker_uri = data.get("pickerUri", "")
        if picker_uri:
            picker_uri = picker_uri.rstrip("/") + "/autoclose"
        return {
            "session_id": data.get("id", ""),
            "picker_uri": picker_uri,
            "expire_time": data.get("expireTime", ""),
            "media_items_set": data.get("mediaItemsSet", False),
        }
    except http_requests.exceptions.HTTPError as e:
        detail = ""
        if e.response is not None:
            try:
                detail = e.response.text
            except Exception:
                pass
            if e.response.status_code == 403:
                return {"error": "Photos Picker API returned 403 Forbidden. "
                        "Please: 1) Enable the 'Photos Picker API' in Google Cloud Console "
                        "(APIs & Services → Library), and 2) Disconnect and re-add your Google "
                        "account so the new Photos scope is authorized."}
        print(f"[Photos Picker] HTTP {e.response.status_code if e.response is not None else '?'}: {detail}", flush=True)
        return {"error": f"Photos Picker API error: {e}" + (f" — {detail}" if detail else "")}
    except Exception as e:
        return {"error": f"Photos Picker API error: {e}"}


def poll_photos_session(email: str, session_id: str) -> dict:
    """Poll a Photos Picker session to check if the user has finished selecting."""
    creds = get_credentials_for(email)
    if not creds:
        return {"error": f"Account {email} not connected."}

    try:
        resp = http_requests.get(
            f"{_PHOTOS_PICKER_BASE}/sessions/{session_id}",
            headers=_photos_headers(creds),
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "session_id": data.get("id", ""),
            "picker_uri": data.get("pickerUri", ""),
            "media_items_set": data.get("mediaItemsSet", False),
            "expire_time": data.get("expireTime", ""),
        }
    except Exception as e:
        return {"error": f"Photos Picker poll error: {e}"}


def list_photos_media_items(email: str, session_id: str) -> dict:
    """List media items the user selected in a completed Picker session."""
    creds = get_credentials_for(email)
    if not creds:
        return {"error": f"Account {email} not connected."}

    acct = _load_account(email)
    synced_ids = set(acct.get("photos_synced_ids", []))

    all_items: list[dict] = []
    page_token = ""
    try:
        while True:
            url = f"{_PHOTOS_PICKER_BASE}/mediaItems?sessionId={session_id}&pageSize=100"
            if page_token:
                url += f"&pageToken={page_token}"
            resp = http_requests.get(url, headers=_photos_headers(creds), timeout=30)
            resp.raise_for_status()
            data = resp.json()
            for item in data.get("mediaItems", []):
                mid = item.get("id", "")
                media_file = item.get("mediaFile", {}) or {}
                file_meta = media_file.get("mediaFileMetadata", {}) or {}
                all_items.append({
                    "id": mid,
                    "baseUrl": media_file.get("baseUrl", ""),
                    "mimeType": media_file.get("mimeType", "image/jpeg"),
                    "filename": media_file.get("filename", f"photo_{mid[:8]}.jpg"),
                    "width": str(file_meta.get("width", "")),
                    "height": str(file_meta.get("height", "")),
                    "creationTime": item.get("createTime", ""),
                    "cameraMake": file_meta.get("cameraMake", ""),
                    "cameraModel": file_meta.get("cameraModel", ""),
                    "already_synced": mid in synced_ids,
                })
            page_token = data.get("nextPageToken", "")
            if not page_token:
                break
    except Exception as e:
        return {"error": f"Photos list error: {e}"}

    return {"items": all_items, "total": len(all_items)}


def ingest_photos(email: str, items: list[dict]) -> dict:
    """Download and ingest selected Google Photos via the vision model.

    Args:
        items: list of dicts with at least {id, baseUrl, filename, mimeType, creationTime}
               (as returned by list_photos_media_items)
    """
    creds = get_credentials_for(email)
    if not creds:
        return {"error": f"Account {email} not connected."}

    from llm import describe_image, get_embedding
    from scrubber import scrub_text
    from db import add_memory

    acct = _load_account(email)
    synced_ids = set(acct.get("photos_synced_ids", []))

    ingested = []
    errors = []

    for item in items:
        mid = item.get("id", "")
        base_url = item.get("baseUrl", "")
        filename = item.get("filename", "photo.jpg")
        mime = item.get("mimeType", "image/jpeg")
        creation_time = item.get("creationTime", "")

        if not base_url:
            errors.append({"id": mid, "error": "No baseUrl"})
            continue

        try:
            # Download full-resolution image (=w0-h0 keeps original dimensions)
            download_url = f"{base_url}=w0-h0"
            img_resp = http_requests.get(download_url, headers=_photos_headers(creds), timeout=60)
            img_resp.raise_for_status()
            img_bytes = img_resp.content

            if len(img_bytes) == 0:
                errors.append({"id": mid, "filename": filename, "error": "Empty image"})
                continue

            # Use vision model to describe the image (expects raw bytes)
            description = describe_image(img_bytes, mime)

            # Build content
            parts = [f"Google Photos image: {filename}"]
            if creation_time:
                parts.append(f"Taken: {creation_time}")
            camera = item.get("cameraMake", "")
            model = item.get("cameraModel", "")
            if camera or model:
                parts.append(f"Camera: {' '.join(filter(None, [camera, model]))}")
            dims = ""
            if item.get("width") and item.get("height"):
                dims = f"{item['width']}×{item['height']}"
            if dims:
                parts.append(f"Resolution: {dims}")
            parts.append(f"\n{description}")

            content = "\n".join(parts)
            scrubbed = scrub_text(content)

            metadata = {
                "category": "photo",
                "filename": filename,
                "google_photos_id": mid,
                "google_account": email,
                "creation_time": creation_time,
                "mime_type": mime,
                "resolution": dims,
                "camera": f"{camera} {model}".strip(),
            }

            embedding = get_embedding(scrubbed[:8000])
            memory_id = add_memory(
                content=scrubbed, source_type="google_photos",
                embedding=embedding, metadata=metadata,
            )
            ingested.append({
                "id": mid, "filename": filename,
                "memory_id": memory_id, "description": description[:200],
            })
            synced_ids.add(mid)

        except Exception as e:
            errors.append({"id": mid, "filename": filename, "error": str(e)})

    acct["photos_synced_ids"] = list(synced_ids)[-5000:]
    acct["photos_last_sync"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    _save_account(email, acct)

    return {"ingested": ingested, "errors": errors}
