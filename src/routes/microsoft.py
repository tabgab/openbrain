"""Microsoft 365 integration API routes — OneDrive, Outlook, Calendar via Graph API."""
import json
from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse

router = APIRouter()


@router.get("/api/microsoft/status")
def microsoft_status():
    from cloud_svc.microsoft_svc import get_status
    return get_status()


@router.post("/api/microsoft/credentials/upload")
async def microsoft_credentials_upload(file: UploadFile = File(...)):
    """Upload Microsoft app credentials JSON: {client_id, client_secret, redirect_uri}."""
    try:
        content = await file.read()
        data = json.loads(content)
        if "client_id" not in data:
            raise HTTPException(status_code=400, detail="JSON must contain 'client_id'.")
        from cloud_svc.common import save_credentials
        save_credentials("microsoft", data)
        return {"success": True}
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON file.")


@router.post("/api/microsoft/connect")
def microsoft_connect():
    from cloud_svc.microsoft_svc import start_oauth_flow
    result = start_oauth_flow()
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/api/microsoft/callback")
def microsoft_callback(code: str = "", state: str = "", error: str = ""):
    if error:
        return HTMLResponse(f"<h2>Authorization failed</h2><p>{error}</p>")
    from cloud_svc.microsoft_svc import complete_oauth_flow
    result = complete_oauth_flow(code, state)
    if "error" in result:
        return HTMLResponse(f"<h2>Error</h2><p>{result['error']}</p>")
    return HTMLResponse(
        f"<h2>✅ Connected: {result.get('email', '')}</h2>"
        "<p>You can close this window and return to Open Brain.</p>"
        "<script>setTimeout(()=>window.close(),2000)</script>"
    )


@router.post("/api/microsoft/disconnect")
def microsoft_disconnect(payload: dict):
    from cloud_svc.microsoft_svc import disconnect
    disconnect(payload.get("email", ""))
    return {"success": True}


# --- OneDrive ---

@router.post("/api/microsoft/onedrive/search")
def microsoft_onedrive_search(payload: dict):
    email = payload.get("email", "")
    if not email:
        raise HTTPException(status_code=400, detail="Email is required.")
    from cloud_svc.microsoft_svc import search_onedrive
    result = search_onedrive(
        email=email,
        query=payload.get("query", ""),
        file_type=payload.get("file_type", ""),
        max_results=payload.get("max_results", 30),
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/api/microsoft/onedrive/ingest")
def microsoft_onedrive_ingest(payload: dict):
    email = payload.get("email", "")
    file_ids = payload.get("file_ids", [])
    if not email or not file_ids:
        raise HTTPException(status_code=400, detail="Email and file_ids are required.")
    from cloud_svc.microsoft_svc import ingest_onedrive_files
    return ingest_onedrive_files(email, file_ids)


# --- Outlook ---

@router.post("/api/microsoft/outlook/search")
def microsoft_outlook_search(payload: dict):
    email = payload.get("email", "")
    if not email:
        raise HTTPException(status_code=400, detail="Email is required.")
    from cloud_svc.microsoft_svc import search_outlook
    result = search_outlook(
        email=email,
        query=payload.get("query", ""),
        from_filter=payload.get("from_filter", ""),
        subject_filter=payload.get("subject_filter", ""),
        folder=payload.get("folder", "inbox"),
        newer_than_days=payload.get("newer_than_days", 7),
        max_results=payload.get("max_results", 30),
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/api/microsoft/outlook/ingest")
def microsoft_outlook_ingest(payload: dict):
    email = payload.get("email", "")
    message_ids = payload.get("message_ids", [])
    if not email or not message_ids:
        raise HTTPException(status_code=400, detail="Email and message_ids are required.")
    from cloud_svc.microsoft_svc import ingest_outlook_messages
    return ingest_outlook_messages(email, message_ids)


# --- Calendar ---

@router.post("/api/microsoft/calendar/scan")
def microsoft_calendar_scan(payload: dict):
    email = payload.get("email", "")
    if not email:
        raise HTTPException(status_code=400, detail="Email is required.")
    from cloud_svc.microsoft_svc import scan_calendar
    result = scan_calendar(
        email=email,
        days_back=payload.get("days_back", 30),
        days_forward=payload.get("days_forward", 30),
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/api/microsoft/calendar/ingest")
def microsoft_calendar_ingest(payload: dict):
    email = payload.get("email", "")
    event_ids = payload.get("event_ids", [])
    if not email or not event_ids:
        raise HTTPException(status_code=400, detail="Email and event_ids are required.")
    from cloud_svc.microsoft_svc import ingest_calendar_events
    return ingest_calendar_events(email, event_ids)
