"""Backup and restore endpoints."""
import io
import datetime
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api import add_event

router = APIRouter()


class BackupRequest(BaseModel):
    password: str
    include_secrets: bool = True  # If False, LLM API key & Telegram token are excluded


@router.post("/api/backup")
def backup_endpoint(payload: BackupRequest):
    """Create an encrypted backup of the entire Open Brain system."""
    if len(payload.password) < 4:
        raise HTTPException(status_code=400, detail="Password must be at least 4 characters.")
    try:
        from backup import create_backup
        secrets_label = "with" if payload.include_secrets else "without"
        add_event("info", "backup", f"Creating encrypted backup ({secrets_label} API secrets)...")
        encrypted_data, manifest = create_backup(payload.password, include_secrets=payload.include_secrets)
        add_event("success", "backup",
            f"Backup created: {manifest.get('memory_count', '?')} memories, "
            f"{manifest.get('vault_count', '?')} vault entries, "
            f"{len(encrypted_data)} bytes encrypted")

        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"openbrain_backup_{ts}.obk"

        return StreamingResponse(
            io.BytesIO(encrypted_data),
            media_type="application/octet-stream",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    except Exception as e:
        add_event("error", "backup", f"Backup failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/restore")
async def restore_endpoint(file: UploadFile = File(...), password: str = Form(...)):
    """Restore the Open Brain system from an encrypted .obk backup."""
    if len(password) < 4:
        raise HTTPException(status_code=400, detail="Password must be at least 4 characters.")
    try:
        from backup import restore_backup
        add_event("info", "restore", f"Restoring from backup: {file.filename}")
        encrypted_data = await file.read()
        summary = restore_backup(encrypted_data, password)
        add_event("success", "restore",
            f"Restore complete: {summary}")
        return {"success": True, "summary": summary}
    except ValueError as e:
        add_event("error", "restore", f"Restore failed: {e}")
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        add_event("error", "restore", f"Restore failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
