"""WhatsApp chat import endpoint."""
from fastapi import APIRouter, HTTPException, UploadFile, File, Form

from event_log import add_event

router = APIRouter()


@router.post("/api/whatsapp/import")
async def whatsapp_import(file: UploadFile = File(...), chat_name: str = Form("WhatsApp Chat")):
    """Import a WhatsApp chat export (.txt file)."""
    try:
        content = await file.read()
        text = content.decode("utf-8", errors="replace")
        from whatsapp_import import ingest_whatsapp_export
        add_event("info", "whatsapp", f"Importing WhatsApp chat: {chat_name} ({file.filename})")
        result = ingest_whatsapp_export(text, chat_name)
        if result.get("error"):
            add_event("error", "whatsapp", f"WhatsApp import failed: {result['error']}")
        else:
            add_event("success", "whatsapp", f"WhatsApp: {result['ingested']} message groups ingested from '{chat_name}' ({result['total_messages']} messages)")
        return result
    except Exception as e:
        add_event("error", "whatsapp", f"WhatsApp import failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
