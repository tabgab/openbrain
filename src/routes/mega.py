"""MEGA cloud storage API routes."""
from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.get("/api/mega/status")
def mega_status():
    from cloud_svc.mega_svc import get_status
    return get_status()


@router.post("/api/mega/connect")
def mega_connect(payload: dict):
    email = payload.get("email", "").strip()
    password = payload.get("password", "")
    if not email or not password:
        raise HTTPException(status_code=400, detail="Email and password are required.")
    from cloud_svc.mega_svc import connect
    result = connect(email, password)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/api/mega/disconnect")
def mega_disconnect(payload: dict):
    from cloud_svc.mega_svc import disconnect
    disconnect(payload.get("email", ""))
    return {"success": True}


@router.post("/api/mega/search")
def mega_search(payload: dict):
    email = payload.get("email", "")
    if not email:
        raise HTTPException(status_code=400, detail="Email is required.")
    from cloud_svc.mega_svc import list_files
    result = list_files(
        email=email,
        query=payload.get("query", ""),
        file_type=payload.get("file_type", ""),
        max_results=payload.get("max_results", 500),
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/api/mega/ingest")
def mega_ingest(payload: dict):
    email = payload.get("email", "")
    file_ids = payload.get("file_ids", [])
    if not email or not file_ids:
        raise HTTPException(status_code=400, detail="Email and file_ids are required.")
    from cloud_svc.mega_svc import ingest_files
    return ingest_files(email, file_ids)
