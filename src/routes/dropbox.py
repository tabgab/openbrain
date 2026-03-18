"""Dropbox integration API routes."""
import json
from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse

router = APIRouter()


@router.get("/api/dropbox/status")
def dropbox_status():
    from cloud_svc.dropbox_svc import get_status
    return get_status()


@router.post("/api/dropbox/credentials/upload")
async def dropbox_credentials_upload(file: UploadFile = File(...)):
    """Upload Dropbox app credentials JSON: {app_key, app_secret, redirect_uri}."""
    try:
        content = await file.read()
        data = json.loads(content)
        if "app_key" not in data:
            raise HTTPException(status_code=400, detail="JSON must contain 'app_key'.")
        from cloud_svc.common import save_credentials
        save_credentials("dropbox", data)
        return {"success": True}
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON file.")


@router.post("/api/dropbox/connect")
def dropbox_connect():
    from cloud_svc.dropbox_svc import start_oauth_flow
    result = start_oauth_flow()
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/api/dropbox/callback")
def dropbox_callback(code: str = "", state: str = "", error: str = ""):
    if error:
        return HTMLResponse(f"<h2>Authorization failed</h2><p>{error}</p>")
    from cloud_svc.dropbox_svc import complete_oauth_flow
    result = complete_oauth_flow(code, state)
    if "error" in result:
        return HTMLResponse(f"<h2>Error</h2><p>{result['error']}</p>")
    return HTMLResponse(
        f"<h2>✅ Connected: {result.get('email', '')}</h2>"
        "<p>You can close this window and return to Open Brain.</p>"
        "<script>setTimeout(()=>window.close(),2000)</script>"
    )


@router.post("/api/dropbox/disconnect")
def dropbox_disconnect(payload: dict):
    from cloud_svc.dropbox_svc import disconnect
    disconnect(payload.get("email", ""))
    return {"success": True}


@router.post("/api/dropbox/search")
def dropbox_search(payload: dict):
    email = payload.get("email", "")
    if not email:
        raise HTTPException(status_code=400, detail="Email is required.")
    from cloud_svc.dropbox_svc import search_files
    result = search_files(
        email=email,
        query=payload.get("query", ""),
        path=payload.get("path", ""),
        file_type=payload.get("file_type", ""),
        max_results=payload.get("max_results", 30),
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/api/dropbox/ingest")
def dropbox_ingest(payload: dict):
    email = payload.get("email", "")
    file_paths = payload.get("file_paths", [])
    if not email or not file_paths:
        raise HTTPException(status_code=400, detail="Email and file_paths are required.")
    from cloud_svc.dropbox_svc import ingest_files
    return ingest_files(email, file_paths)
