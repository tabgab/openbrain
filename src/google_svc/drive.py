"""
Google Drive — Search / Preview / Ingest
"""
import io
import datetime

from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

from google_svc.auth import get_credentials_for, _load_account, _save_account

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
