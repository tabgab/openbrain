import sys
import os
# Ensure src/ is in path so 'db', 'llm' etc. are importable when uvicorn runs from project root
sys.path.insert(0, os.path.dirname(__file__))

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests as http_requests
from dotenv import set_key, load_dotenv

load_dotenv()

app = FastAPI(title="Open Brain Dashboard API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory event log for the UI
event_log: list = []

def add_event(level: str, source: str, message: str):
    """Appends a system event to the in-memory log (last 100 events)."""
    import datetime
    event_log.append({
        "level": level,  # "info", "error", "warning", "success"
        "source": source,
        "message": message,
        "timestamp": datetime.datetime.now().isoformat()
    })
    if len(event_log) > 100:
        event_log.pop(0)

class ConfigUpdate(BaseModel):
    telegramToken: str = ""
    llmApiKey: str = ""
    dbPassword: str = ""
    dbUser: str = ""
    dbName: str = ""
    dbHost: str = ""
    llmBaseUrl: str = ""
    # Model roles
    modelText: str = ""
    modelReasoning: str = ""
    modelCoding: str = ""
    modelVision: str = ""
    modelEmbedding: str = ""

@app.get("/api/health")
def get_health():
    """Returns detailed system health status with real validation results."""
    load_dotenv(override=True)

    # 1. DB check
    db_ok = False
    db_error = ""
    try:
        from db import get_connection
        conn = get_connection()
        conn.close()
        db_ok = True
    except Exception as e:
        db_error = str(e)

    # 2. LLM check — use a cheap embedding call that works on both OpenAI and OpenRouter
    llm_ok = False
    llm_error = ""
    api_key = os.getenv("LLM_API_KEY", "").strip("'\"")
    # Default to OpenRouter; user must explicitly set base URL to use OpenAI directly
    base_url = os.getenv("LLM_BASE_URL", "https://openrouter.ai/api/v1").strip("'\"")
    if api_key:
        try:
            resp = http_requests.get(
                f"{base_url.rstrip('/')}/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=8,
            )
            if resp.status_code == 200:
                llm_ok = True
            else:
                llm_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
        except Exception as e:
            llm_error = str(e)
    else:
        llm_error = "LLM_API_KEY not set"

    # 3. Telegram check
    telegram_ok = False
    telegram_error = ""
    telegram_bot_name = ""
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip("'\"")
    if token:
        try:
            resp = http_requests.get(
                f"https://api.telegram.org/bot{token}/getMe", timeout=5
            ).json()
            if resp.get("ok"):
                telegram_ok = True
                telegram_bot_name = resp["result"].get("username", "")
            else:
                telegram_error = resp.get("description", "Unknown Telegram error")
        except Exception as e:
            telegram_error = str(e)
    else:
        telegram_error = "TELEGRAM_BOT_TOKEN not set"

    return {
        "db": {"ok": db_ok, "error": db_error},
        "llm": {"ok": llm_ok, "error": llm_error},
        "telegram": {"ok": telegram_ok, "error": telegram_error, "bot_name": telegram_bot_name},
    }

@app.get("/api/events")
def get_recent_events():
    """Returns the last 10 memories saved to the DB."""
    try:
        from db import get_recent_memories
        results = get_recent_memories(limit=10)
        return {"memories": results}
    except Exception as e:
        return {"memories": [], "error": str(e)}

@app.get("/api/memories/search")
def search_memories_endpoint(q: str = "", limit: int = 20):
    """Search memories by text content or metadata."""
    if not q.strip():
        return {"memories": []}
    try:
        from db import search_memories
        results = search_memories(query=q.strip(), limit=limit)
        return {"memories": results}
    except Exception as e:
        return {"memories": [], "error": str(e)}

class MemoryUpdate(BaseModel):
    content: str

@app.put("/api/memories/{memory_id}")
def update_memory_endpoint(memory_id: str, payload: MemoryUpdate):
    """Update a memory's content."""
    try:
        from db import update_memory
        ok = update_memory(memory_id=memory_id, content=payload.content)
        if not ok:
            raise HTTPException(status_code=404, detail="Memory not found")
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/ingest")
async def ingest_document_endpoint(file: UploadFile = File(...)):
    """Upload and ingest a document (PDF, image, Word, Excel, etc.)."""
    try:
        file_bytes = await file.read()
        filename = file.filename or "unknown"

        add_event("info", "ingest", f"Ingesting document: {filename} ({len(file_bytes)} bytes)")

        from ingest import ingest_document
        result = ingest_document(filename, file_bytes)

        extracted_text = result["text"]
        if not extracted_text or extracted_text.startswith("["):
            add_event("warning", "ingest", f"Limited extraction from {filename}: {extracted_text[:100]}")
            return {"success": False, "error": extracted_text, "filename": filename}

        # Categorize the extracted text
        from llm import categorize_and_extract, get_embedding
        metadata = categorize_and_extract(extracted_text[:2000])
        metadata["filename"] = filename
        metadata["ingestion_method"] = result["method"]

        # Generate embedding and save to DB
        embedding = get_embedding(extracted_text[:8000])
        from db import add_memory
        memory_id = add_memory(
            content=extracted_text,
            source_type=result["source_type"],
            embedding=embedding,
            metadata=metadata,
        )

        add_event("success", "ingest", f"Document '{filename}' ingested as memory {memory_id} (category: {metadata.get('category')})")
        return {
            "success": True,
            "memory_id": memory_id,
            "filename": filename,
            "method": result["method"],
            "category": metadata.get("category"),
            "summary": metadata.get("summary"),
            "content_length": len(extracted_text),
        }
    except Exception as e:
        add_event("error", "ingest", f"Ingestion failed for {file.filename}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/memories/{memory_id}")
def delete_memory_endpoint(memory_id: str):
    """Delete a memory by ID."""
    try:
        from db import delete_memory
        ok = delete_memory(memory_id=memory_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Memory not found")
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/logs")
def get_logs():
    """Returns the in-memory system event log."""
    return {"logs": list(reversed(event_log))}

@app.post("/api/logs")
def post_log(payload: dict):
    """Allows background processes (telegram bot) to post events to the log."""
    add_event(
        payload.get("level", "info"),
        payload.get("source", "system"),
        payload.get("message", "")
    )
    return {"ok": True}

@app.get("/api/config")
def get_config():
    """Returns current non-secret config settings (masks secrets)."""
    load_dotenv(override=True)
    def mask(val: str) -> str:
        v = val.strip("'\"")
        if not v:
            return ""
        return v[:4] + "..." + v[-4:] if len(v) > 12 else "****"

    return {
        "telegramToken": mask(os.getenv("TELEGRAM_BOT_TOKEN", "")),
        "llmApiKey": mask(os.getenv("LLM_API_KEY", "")),
        "dbPassword": mask(os.getenv("POSTGRES_PASSWORD", "")),
        "dbUser": os.getenv("POSTGRES_USER", "openbrain"),
        "dbName": os.getenv("POSTGRES_DB", "openbrain_db"),
        "dbHost": os.getenv("POSTGRES_HOST", "localhost"),
        "llmBaseUrl": os.getenv("LLM_BASE_URL", "https://openrouter.ai/api/v1"),
        # Model roles
        "modelText": os.getenv("MODEL_TEXT", "moonshotai/kimi-k2.5"),
        "modelReasoning": os.getenv("MODEL_REASONING", "anthropic/claude-sonnet-4.6"),
        "modelCoding": os.getenv("MODEL_CODING", "minimax/minimax-m2.5"),
        "modelVision": os.getenv("MODEL_VISION", "moonshotai/kimi-k2.5"),
        "modelEmbedding": os.getenv("MODEL_EMBEDDING", "openai/text-embedding-3-small"),
    }

@app.post("/api/config")
def update_config(config: ConfigUpdate):
    """Updates .env file with new credentials from the setup wizard or settings page."""
    env_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    if not os.path.exists(env_file):
        open(env_file, 'a').close()

    try:
        fields = {
            "TELEGRAM_BOT_TOKEN": config.telegramToken,
            "LLM_API_KEY": config.llmApiKey,
            "POSTGRES_PASSWORD": config.dbPassword,
            "POSTGRES_USER": config.dbUser,
            "POSTGRES_DB": config.dbName,
            "POSTGRES_HOST": config.dbHost,
            "LLM_BASE_URL": config.llmBaseUrl,
            "MODEL_TEXT": config.modelText,
            "MODEL_REASONING": config.modelReasoning,
            "MODEL_CODING": config.modelCoding,
            "MODEL_VISION": config.modelVision,
            "MODEL_EMBEDDING": config.modelEmbedding,
        }
        saved = []
        for key, value in fields.items():
            # Skip empty values OR masked values (e.g., "8717...aljw" from display)
            if value and "..." not in value and "****" not in value:
                set_key(env_file, key, value, quote_mode="never")
                saved.append(key)
        print(f"[Config] Saved keys: {saved}", flush=True)
        add_event("success", "config", f"Configuration updated: {', '.join(saved) if saved else 'no changes'}")
        return {"success": True, "updated": saved}
    except Exception as e:
        print(f"[Config] ERROR saving: {e}", flush=True)
        import traceback; traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
