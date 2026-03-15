import sys
import os
# Ensure src/ is in path so 'db', 'llm' etc. are importable when uvicorn runs from project root
sys.path.insert(0, os.path.dirname(__file__))

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse
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

class ChatMessage(BaseModel):
    message: str
    force_mode: str = ""  # "question", "memory", or "" for auto-detect

@app.post("/api/chat")
def chat_endpoint(payload: ChatMessage):
    """Chat with Open Brain — auto-detects questions vs memories, just like the Telegram bot."""
    from llm import get_embedding, categorize_and_extract, get_client
    from db import add_memory, query_memories
    from scrubber import scrub_text

    text = payload.message.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    mode = payload.force_mode

    # Auto-detect if not forced
    if not mode:
        mode = _detect_intent(text)

    add_event("info", "chat", f"Chat ({mode}): '{text[:60]}'")

    if mode == "question":
        # Search brain and answer
        try:
            embedding = get_embedding(text)
            results = query_memories(embedding=embedding, limit=5)
        except Exception as e:
            add_event("error", "chat", f"Brain search failed: {e}")
            return {"type": "answer", "content": f"Failed to search the brain: {e}", "sources": []}

        if not results:
            return {"type": "answer", "content": "No relevant memories found in your Open Brain yet.", "sources": []}

        context = "\n\n".join(
            f"- [{r['source_type']} · {r['created_at']}] {r['content']}" for r in results
        )

        try:
            reasoning_client, reasoning_model = get_client("reasoning")
            resp = reasoning_client.chat.completions.create(
                model=reasoning_model,
                messages=[
                    {"role": "system", "content": (
                        "You are the Open Brain assistant. Answer the user's question based ONLY on "
                        "the memories retrieved below. If the memories don't contain enough information, "
                        "say so honestly. Be concise and helpful."
                    )},
                    {"role": "user", "content": f"Memories:\n{context}\n\nQuestion: {text}"},
                ],
            )
            answer = resp.choices[0].message.content
            add_event("success", "chat", f"Answered question (used {len(results)} memories)")
            return {
                "type": "answer",
                "content": answer,
                "sources": [{"id": r["id"], "source_type": r["source_type"], "summary": (r.get("metadata") or {}).get("summary", r["content"][:80])} for r in results],
            }
        except Exception as e:
            add_event("error", "chat", f"LLM answer failed: {e}")
            return {"type": "answer", "content": f"Failed to generate answer: {e}", "sources": []}

    else:
        # Store as memory
        scrubbed = scrub_text(text)
        try:
            extracted = categorize_and_extract(scrubbed)
        except Exception:
            extracted = {"category": "uncategorized"}
        try:
            embedding = get_embedding(scrubbed)
        except Exception:
            embedding = [0.0] * 1536

        memory_id = add_memory(content=scrubbed, source_type="dashboard_chat", embedding=embedding, metadata=extracted)
        category = extracted.get("category", "unknown")
        summary = extracted.get("summary", "")
        add_event("success", "chat", f"Memory saved from chat — ID: {memory_id}, Category: {category}")
        return {
            "type": "memory",
            "content": f"Saved to Open Brain as **{category}**.",
            "memory_id": memory_id,
            "category": category,
            "summary": summary,
        }

def _detect_intent(text: str) -> str:
    """Detect whether a message is a question or a memory. Mirrors telegram_bot.is_question logic."""
    stripped = text.strip()
    if stripped.endswith("?"):
        return "question"

    QUESTION_WORDS = {
        "who", "what", "when", "where", "why", "how",
        "do", "does", "did", "is", "are", "was", "were",
        "can", "could", "will", "would", "should", "shall",
        "have", "has", "had", "which", "whose", "whom",
        "tell", "explain", "describe", "show",
    }
    first_word = stripped.split()[0].lower().rstrip(",:;") if stripped else ""
    if first_word in QUESTION_WORDS:
        return "question"
    if first_word in {"find", "search", "look", "list", "get", "recall", "remember"}:
        return "question"

    # LLM classification for ambiguous messages
    if len(stripped.split()) >= 3:
        try:
            from llm import get_client
            text_client, text_model = get_client("text")
            resp = text_client.chat.completions.create(
                model=text_model,
                messages=[
                    {"role": "system", "content": (
                        "Classify whether this message is a QUESTION (the user wants to retrieve/query information) "
                        "or a MEMORY (the user wants to store this as a note/fact/log). "
                        "Reply with exactly one word: QUESTION or MEMORY."
                    )},
                    {"role": "user", "content": stripped},
                ],
                max_tokens=5,
            )
            answer = resp.choices[0].message.content.strip().upper()
            if "QUESTION" in answer:
                return "question"
        except Exception:
            pass

    return "memory"

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

# --- Backup & Restore ---

class BackupRequest(BaseModel):
    password: str
    include_secrets: bool = True  # If False, LLM API key & Telegram token are excluded

@app.post("/api/backup")
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

        import io
        import datetime
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

@app.post("/api/restore")
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
