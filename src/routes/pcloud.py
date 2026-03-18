"""pCloud integration API routes."""
import json
from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse

router = APIRouter()


@router.get("/api/pcloud/status")
def pcloud_status():
    from cloud_svc.pcloud_svc import get_status
    return get_status()


@router.post("/api/pcloud/credentials/upload")
async def pcloud_credentials_upload(file: UploadFile = File(...)):
    """Upload pCloud app credentials JSON: {client_id, client_secret, redirect_uri, region}."""
    try:
        content = await file.read()
        data = json.loads(content)
        if "client_id" not in data:
            raise HTTPException(status_code=400, detail="JSON must contain 'client_id'.")
        from cloud_svc.common import save_credentials
        save_credentials("pcloud", data)
        return {"success": True}
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON file.")


@router.post("/api/pcloud/connect")
def pcloud_connect():
    from cloud_svc.pcloud_svc import start_oauth_flow
    result = start_oauth_flow()
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/api/pcloud/callback")
def pcloud_callback(code: str = "", state: str = "", error: str = ""):
    if error:
        return HTMLResponse(f"<h2>Authorization failed</h2><p>{error}</p>")
    from cloud_svc.pcloud_svc import complete_oauth_flow
    result = complete_oauth_flow(code, state)
    if "error" in result:
        return HTMLResponse(f"<h2>Error</h2><p>{result['error']}</p>")
    return HTMLResponse(
        f"<h2>✅ Connected: {result.get('email', '')}</h2>"
        "<p>You can close this window and return to Open Brain.</p>"
        "<script>setTimeout(()=>window.close(),2000)</script>"
    )


@router.post("/api/pcloud/disconnect")
def pcloud_disconnect(payload: dict):
    from cloud_svc.pcloud_svc import disconnect
    disconnect(payload.get("email", ""))
    return {"success": True}


@router.post("/api/pcloud/search")
def pcloud_search(payload: dict):
    email = payload.get("email", "")
    if not email:
        raise HTTPException(status_code=400, detail="Email is required.")
    from cloud_svc.pcloud_svc import list_files
    result = list_files(
        email=email,
        query=payload.get("query", ""),
        file_type=payload.get("file_type", ""),
        max_results=payload.get("max_results", 30),
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/api/pcloud/ingest")
def pcloud_ingest(payload: dict):
    email = payload.get("email", "")
    file_ids = payload.get("file_ids", [])
    if not email or not file_ids:
        raise HTTPException(status_code=400, detail="Email and file_ids are required.")
    from cloud_svc.pcloud_svc import ingest_files
    return ingest_files(email, file_ids)
