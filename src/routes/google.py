"""Google integration API routes — thin wrappers around google_svc modules."""
import json
from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse

from event_log import add_event

router = APIRouter()


@router.get("/api/google/status")
def google_status():
    """List all connected Google accounts and credentials file status."""
    from google_svc import get_status
    return get_status()


@router.post("/api/google/credentials/upload")
async def google_credentials_upload(file: UploadFile = File(...)):
    """Upload a Google OAuth credentials JSON file (any filename)."""
    try:
        content = await file.read()
        data = json.loads(content)
        # Validate it looks like a Google OAuth credentials file
        if "web" not in data and "installed" not in data:
            raise HTTPException(status_code=400, detail="Invalid credentials file. Must contain 'web' or 'installed' key from Google Cloud Console.")
        from google_svc import _CREDENTIALS_FILE
        _CREDENTIALS_FILE.write_bytes(content)
        add_event("success", "google", f"Google credentials uploaded ({file.filename})")
        return {"success": True, "filename": file.filename}
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="File is not valid JSON.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/google/connect")
def google_connect():
    """Start Google OAuth flow. Returns the auth URL."""
    from google_svc import start_oauth_flow
    result = start_oauth_flow()
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/api/google/callback")
def google_callback(code: str = None, error: str = None, state: str = None):
    """OAuth callback — exchanges auth code for tokens."""
    if error:
        return {"error": error}
    if not code:
        raise HTTPException(status_code=400, detail="No authorization code received.")
    from google_svc import complete_oauth_flow
    result = complete_oauth_flow(code, state=state or "")
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    add_event("success", "google", f"Google account connected: {result.get('email')}")
    return HTMLResponse(f"""
        <html><body style="font-family:sans-serif;text-align:center;padding:3rem">
        <h2>Google Connected</h2>
        <p>Signed in as <strong>{result.get('email')}</strong></p>
        <p>You can close this tab and return to the Open Brain dashboard.</p>
        <script>setTimeout(()=>window.close(), 3000)</script>
        </body></html>
    """)


@router.post("/api/google/disconnect")
def google_disconnect(payload: dict):
    """Disconnect a specific Google account."""
    email = payload.get("email", "")
    if not email:
        raise HTTPException(status_code=400, detail="Email is required.")
    from google_svc import disconnect
    result = disconnect(email)
    add_event("info", "google", f"Google account disconnected: {email}")
    return result


# Drive: search/preview
@router.post("/api/google/drive/search")
def google_drive_search(payload: dict):
    """Search Google Drive files with filters. Returns preview list."""
    email = payload.get("email", "")
    if not email:
        raise HTTPException(status_code=400, detail="Email is required.")
    from google_svc import search_drive
    result = search_drive(
        email=email,
        query=payload.get("query", ""),
        folder_name=payload.get("folder_name", ""),
        file_type=payload.get("file_type", ""),
        max_results=payload.get("max_results", 25),
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


# Drive: ingest selected files
@router.post("/api/google/drive/ingest")
def google_drive_ingest(payload: dict):
    """Ingest selected Google Drive files by their IDs."""
    email = payload.get("email", "")
    file_ids = payload.get("file_ids", [])
    if not email or not file_ids:
        raise HTTPException(status_code=400, detail="Email and file_ids are required.")
    from google_svc import ingest_drive_files
    add_event("info", "google", f"Ingesting {len(file_ids)} files from Drive ({email})...")
    result = ingest_drive_files(email, file_ids)
    if "error" in result:
        add_event("error", "google", f"Drive ingest failed: {result['error']}")
    else:
        add_event("success", "google", f"Drive: {len(result.get('ingested', []))} files ingested from {email}")
    return result


# Gmail: list labels (system + custom)
@router.get("/api/google/gmail/labels")
def google_gmail_labels(email: str):
    """List all Gmail labels (system + custom) for the given account."""
    if not email:
        raise HTTPException(status_code=400, detail="Email is required.")
    from google_svc import list_gmail_labels
    result = list_gmail_labels(email)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


# Gmail: search/preview
@router.post("/api/google/gmail/search")
def google_gmail_search(payload: dict):
    """Search Gmail messages with filters. Returns preview list."""
    email = payload.get("email", "")
    if not email:
        raise HTTPException(status_code=400, detail="Email is required.")
    from google_svc import search_gmail
    result = search_gmail(
        email=email,
        query=payload.get("query", ""),
        from_filter=payload.get("from_filter", ""),
        subject_filter=payload.get("subject_filter", ""),
        label=payload.get("label", ""),
        newer_than=payload.get("newer_than", "7d"),
        max_results=payload.get("max_results", 25),
        page_token=payload.get("page_token", ""),
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


# Gmail: ingest selected messages
@router.post("/api/google/gmail/ingest")
def google_gmail_ingest(payload: dict):
    """Ingest selected Gmail messages by their IDs."""
    email = payload.get("email", "")
    message_ids = payload.get("message_ids", [])
    if not email or not message_ids:
        raise HTTPException(status_code=400, detail="Email and message_ids are required.")
    include_images = payload.get("include_images", False)
    from google_svc import ingest_gmail_messages
    add_event("info", "google", f"Ingesting {len(message_ids)} emails from Gmail ({email}){' with images' if include_images else ''}...")
    result = ingest_gmail_messages(email, message_ids, include_images=include_images)
    if "error" in result:
        add_event("error", "google", f"Gmail ingest failed: {result['error']}")
    else:
        add_event("success", "google", f"Gmail: {len(result.get('ingested', []))} emails ingested from {email}")
    return result


# Gmail: preview full email body
@router.post("/api/google/gmail/preview")
def google_gmail_preview(payload: dict):
    """Fetch the full body of a single Gmail message for reading before ingest."""
    email = payload.get("email", "")
    message_id = payload.get("message_id", "")
    if not email or not message_id:
        raise HTTPException(status_code=400, detail="Email and message_id are required.")
    from google_svc import preview_gmail_message
    result = preview_gmail_message(email, message_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


# Calendar: scan events
@router.post("/api/google/calendar/scan")
def google_calendar_scan(payload: dict):
    """Scan calendar events for a connected Google account."""
    email = payload.get("email", "")
    if not email:
        raise HTTPException(status_code=400, detail="Email is required.")
    from google_svc import scan_calendar_events
    result = scan_calendar_events(
        email=email,
        time_min=payload.get("time_min", ""),
        time_max=payload.get("time_max", ""),
        max_results=payload.get("max_results", 500),
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


# Calendar: ingest selected events
@router.post("/api/google/calendar/ingest")
def google_calendar_ingest(payload: dict):
    """Ingest selected calendar events as memories."""
    email = payload.get("email", "")
    event_ids = payload.get("event_ids", [])
    if not email or not event_ids:
        raise HTTPException(status_code=400, detail="Email and event_ids are required.")
    from google_svc import ingest_calendar_events
    add_event("info", "google", f"Ingesting {len(event_ids)} calendar events ({email})...")
    result = ingest_calendar_events(email, event_ids)
    if "error" in result:
        add_event("error", "google", f"Calendar ingest failed: {result['error']}")
    else:
        add_event("success", "google", f"Calendar: {len(result.get('ingested', []))} events ingested from {email}")
    return result


# --- Google Photos (Picker API) ---

@router.post("/api/google/photos/create-session")
def google_photos_create_session(payload: dict):
    """Create a Google Photos Picker session for the user to select photos."""
    email = payload.get("email", "")
    if not email:
        raise HTTPException(status_code=400, detail="Email is required.")
    from google_svc import create_photos_session
    result = create_photos_session(email)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    add_event("info", "google", f"Photos Picker session created for {email}")
    return result


@router.get("/api/google/photos/poll-session")
def google_photos_poll_session(email: str, session_id: str):
    """Poll a Photos Picker session to check if user finished selecting."""
    if not email or not session_id:
        raise HTTPException(status_code=400, detail="Email and session_id are required.")
    from google_svc import poll_photos_session
    result = poll_photos_session(email, session_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/api/google/photos/media-items")
def google_photos_media_items(email: str, session_id: str):
    """List media items the user selected in the Picker."""
    if not email or not session_id:
        raise HTTPException(status_code=400, detail="Email and session_id are required.")
    from google_svc import list_photos_media_items
    result = list_photos_media_items(email, session_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/api/google/photos/ingest")
def google_photos_ingest(payload: dict):
    """Download and ingest selected Google Photos via vision model."""
    email = payload.get("email", "")
    items = payload.get("items", [])
    if not email or not items:
        raise HTTPException(status_code=400, detail="Email and items are required.")
    from google_svc import ingest_photos
    add_event("info", "google", f"Ingesting {len(items)} photos from Google Photos ({email})...")
    result = ingest_photos(email, items)
    if "error" in result:
        add_event("error", "google", f"Photos ingest failed: {result['error']}")
    else:
        add_event("success", "google", f"Photos: {len(result.get('ingested', []))} photos ingested from {email}")
    return result
