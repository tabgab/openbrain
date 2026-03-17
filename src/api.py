import sys
import os
import warnings
# Suppress multiprocessing resource_tracker "leaked semaphore" warning on shutdown
# (caused by PyTorch/Whisper internals, harmless — OS reclaims semaphores on exit)
warnings.filterwarnings("ignore", message=".*resource_tracker.*", category=UserWarning)
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
    # Speech-to-text
    sttProvider: str = ""
    openaiApiKey: str = ""
    groqApiKey: str = ""
    whisperModelSize: str = ""

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

@app.get("/api/db/stats")
def get_db_stats():
    """Returns database metrics: memory count, DB size, source breakdown, etc."""
    try:
        from db import get_connection
        conn = get_connection()
        cur = conn.cursor()

        # Total memories
        cur.execute("SELECT COUNT(*) FROM memories")
        total_memories = cur.fetchone()[0]

        # Source type breakdown
        cur.execute("SELECT source_type, COUNT(*) FROM memories GROUP BY source_type ORDER BY COUNT(*) DESC")
        source_breakdown = {row[0]: row[1] for row in cur.fetchall()}

        # Category breakdown from metadata
        cur.execute("SELECT metadata->>'category', COUNT(*) FROM memories WHERE metadata->>'category' IS NOT NULL GROUP BY metadata->>'category' ORDER BY COUNT(*) DESC")
        category_breakdown = {row[0]: row[1] for row in cur.fetchall()}

        # Oldest & newest memory
        cur.execute("SELECT MIN(created_at), MAX(created_at) FROM memories")
        row = cur.fetchone()
        oldest = row[0].isoformat() if row[0] else None
        newest = row[1].isoformat() if row[1] else None

        # Database size
        cur.execute("SELECT pg_size_pretty(pg_database_size(current_database()))")
        db_size = cur.fetchone()[0]

        # memories table size (data + indexes)
        cur.execute("SELECT pg_size_pretty(pg_total_relation_size('memories'))")
        table_size = cur.fetchone()[0]

        # Index size
        cur.execute("SELECT pg_size_pretty(pg_indexes_size('memories'))")
        index_size = cur.fetchone()[0]

        # Embedding dimension (from first row)
        embedding_dim = None
        cur.execute("SELECT vector_dims(embedding) FROM memories LIMIT 1")
        dim_row = cur.fetchone()
        if dim_row:
            embedding_dim = dim_row[0]

        # Secrets count (vault may not exist)
        secrets_count = 0
        try:
            cur.execute("SELECT COUNT(*) FROM vault.secrets")
            secrets_count = cur.fetchone()[0]
        except Exception:
            conn.rollback()

        cur.close()
        conn.close()

        return {
            "total_memories": total_memories,
            "source_breakdown": source_breakdown,
            "category_breakdown": category_breakdown,
            "oldest_memory": oldest,
            "newest_memory": newest,
            "db_size": db_size,
            "table_size": table_size,
            "index_size": index_size,
            "embedding_dim": embedding_dim,
            "secrets_count": secrets_count,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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
    search_mode: str = "advanced"  # "memory_only" or "advanced"

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
        # Search brain and answer — with augmented Calendar/Gmail search
        try:
            embedding = get_embedding(text)
            results = query_memories(embedding=embedding, limit=5)
        except Exception as e:
            add_event("error", "chat", f"Brain search failed: {e}")
            return {"type": "answer", "content": f"Failed to search the brain: {e}", "sources": []}

        # Augmented search: also query Calendar and Gmail if relevant
        use_advanced = payload.search_mode != "memory_only"
        plan = {}
        try:
            if use_advanced:
                from smart_search import augmented_search
                search_result = augmented_search(text, results or [])
                context = search_result["combined_context"]
                sources = search_result["sources"]
                plan = search_result.get("search_plan", {})
            else:
                context = "\n\n".join(
                    f"- [{r['source_type']} · {r['created_at']}] {r['content']}" for r in results
                ) if results else ""
                sources = [{"id": r["id"], "source_type": r["source_type"], "summary": (r.get("metadata") or {}).get("summary", r["content"][:80])} for r in results] if results else []
                plan = {}
            extra_info = []
            if plan.get("search_calendar"):
                n_cal = len([s for s in sources if s["source_type"] == "google_calendar_live"])
                extra_info.append(f"calendar:{n_cal}")
            if plan.get("search_gmail"):
                n_mail = len([s for s in sources if s["source_type"] == "gmail_live"])
                extra_info.append(f"gmail:{n_mail}")
            if extra_info:
                add_event("info", "chat", f"Smart search: {', '.join(extra_info)}")
        except Exception as e:
            add_event("warning", "chat", f"Smart search fallback: {e}")
            context = "\n\n".join(
                f"- [{r['source_type']} · {r['created_at']}] {r['content']}" for r in results
            ) if results else ""
            sources = [{"id": r["id"], "source_type": r["source_type"], "summary": (r.get("metadata") or {}).get("summary", r["content"][:80])} for r in results] if results else []

        if not context:
            return {"type": "answer", "content": "No relevant memories or data found in your Open Brain.", "sources": []}

        try:
            reasoning_client, reasoning_model = get_client("reasoning")
            resp = reasoning_client.chat.completions.create(
                model=reasoning_model,
                messages=[
                    {"role": "system", "content": (
                        "You are the Open Brain assistant. Answer the user's question based on "
                        "ALL the information retrieved below — this includes stored memories AND "
                        "live data from Google Calendar and Gmail searches. "
                        "Use all available context to give the best possible answer. "
                        "If multiple sources help, synthesize them. Be concise and helpful."
                    )},
                    {"role": "user", "content": f"Retrieved information:\n{context}\n\nQuestion: {text}"},
                ],
            )
            answer = resp.choices[0].message.content
            n_mem = len([s for s in sources if s["source_type"] not in ("google_calendar_live", "gmail_live")])
            n_ext = len(sources) - n_mem
            add_event("success", "chat", f"Answered question (used {n_mem} memories + {n_ext} live sources)")

            # Build thinking steps for UI
            thinking_steps = []
            thinking_steps.append(f"Searched stored memories — found {len(results or [])} relevant results")
            if plan:
                if plan.get("reasoning"):
                    thinking_steps.append(f"Search reasoning: {plan['reasoning']}")
                if plan.get("search_calendar"):
                    cal_queries = plan.get("calendar_queries", [])
                    t_min = plan.get("calendar_time_min", "")[:10]
                    t_max = plan.get("calendar_time_max", "")[:10]
                    thinking_steps.append(f"Searched Google Calendar with queries: {cal_queries}" + (f" ({t_min} → {t_max})" if t_min else ""))
                    thinking_steps.append(f"Found {len([s for s in sources if s['source_type'] == 'google_calendar_live'])} calendar events")
                if plan.get("search_gmail"):
                    gmail_queries = plan.get("gmail_queries", [])
                    thinking_steps.append(f"Searched Gmail with queries: {gmail_queries}")
                    thinking_steps.append(f"Found {len([s for s in sources if s['source_type'] == 'gmail_live'])} emails")
            thinking_steps.append(f"Combined {n_mem} memories + {n_ext} live sources → sent to reasoning model")

            return {
                "type": "answer",
                "content": answer,
                "sources": sources,
                "thinking": thinking_steps,
            }
        except Exception as e:
            add_event("error", "chat", f"LLM answer failed: {e}")
            return {"type": "answer", "content": f"Failed to generate answer: {e}", "sources": []}

    else:
        # Store as memory
        from url_extract import enrich_text_with_urls, detect_urls
        if detect_urls(text):
            try:
                text = enrich_text_with_urls(text)
            except Exception:
                pass
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


@app.post("/api/chat/stream")
def chat_stream_endpoint(payload: ChatMessage):
    """Streaming chat — sends thinking steps as SSE events in real-time, then the final answer."""
    import json as _json
    import queue
    import threading
    from llm import get_embedding, categorize_and_extract, get_client
    from db import add_memory, query_memories
    from scrubber import scrub_text

    text = payload.message.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    mode = payload.force_mode
    if not mode:
        mode = _detect_intent(text)

    add_event("info", "chat", f"Chat stream ({mode}): '{text[:60]}'")

    def _generate_events():
        if mode == "question":
            step_q: queue.Queue = queue.Queue()

            def on_step(step_text: str):
                step_q.put(("thinking", step_text))

            use_advanced = payload.search_mode != "memory_only"
            result_holder: dict = {}

            def _do_search():
                try:
                    embedding = get_embedding(text)
                    results = query_memories(embedding=embedding, limit=5)
                except Exception as e:
                    result_holder["error"] = str(e)
                    step_q.put(("done", None))
                    return

                if use_advanced:
                    try:
                        from smart_search import augmented_search
                        search_result = augmented_search(text, results or [], on_step=on_step)
                        result_holder["search_result"] = search_result
                        result_holder["results"] = results
                    except Exception as e:
                        on_step(f"Smart search fallback: {e}")
                        ctx = "\n\n".join(
                            f"- [{r['source_type']} · {r['created_at']}] {r['content']}" for r in results
                        ) if results else ""
                        srcs = [{"id": r["id"], "source_type": r["source_type"], "summary": (r.get("metadata") or {}).get("summary", r["content"][:80])} for r in results] if results else []
                        result_holder["search_result"] = {"combined_context": ctx, "sources": srcs, "search_plan": {}}
                        result_holder["results"] = results
                else:
                    on_step(f"Memory-only mode — searching stored memories")
                    on_step(f"Found {len(results or [])} relevant memories")
                    ctx = "\n\n".join(
                        f"- [{r['source_type']} · {r['created_at']}] {r['content']}" for r in results
                    ) if results else ""
                    srcs = [{"id": r["id"], "source_type": r["source_type"], "summary": (r.get("metadata") or {}).get("summary", r["content"][:80])} for r in results] if results else []
                    result_holder["search_result"] = {"combined_context": ctx, "sources": srcs, "search_plan": {}}
                    result_holder["results"] = results
                step_q.put(("done", None))

            t = threading.Thread(target=_do_search, daemon=True)
            t.start()

            # Yield thinking steps as they arrive
            while True:
                try:
                    evt, data = step_q.get(timeout=120)
                except Exception:
                    break
                if evt == "done":
                    break
                yield f"data: {_json.dumps({'type': 'thinking', 'step': data})}\n\n"

            if "error" in result_holder:
                err = result_holder["error"]
                yield f"data: {_json.dumps({'type': 'answer', 'content': 'Failed to search: ' + err, 'sources': []})}\n\n"
                return

            search_result = result_holder["search_result"]
            context = search_result["combined_context"]
            sources = search_result["sources"]

            if not context:
                yield f"data: {_json.dumps({'type': 'answer', 'content': 'No relevant memories or data found in your Open Brain.', 'sources': []})}\n\n"
                return

            yield f"data: {_json.dumps({'type': 'thinking', 'step': 'Generating answer with reasoning model...'})}\n\n"

            try:
                reasoning_client, reasoning_model = get_client("reasoning")
                resp = reasoning_client.chat.completions.create(
                    model=reasoning_model,
                    messages=[
                        {"role": "system", "content": (
                            "You are the Open Brain assistant. Answer the user's question based on "
                            "ALL the information retrieved below — this includes stored memories AND "
                            "live data from Google Calendar and Gmail searches. "
                            "Use all available context to give the best possible answer. "
                            "If multiple sources help, synthesize them. Be concise and helpful."
                        )},
                        {"role": "user", "content": f"Retrieved information:\n{context}\n\nQuestion: {text}"},
                    ],
                )
                answer = resp.choices[0].message.content
                add_event("success", "chat", f"Stream answered question ({len(sources)} sources)")
                yield f"data: {_json.dumps({'type': 'answer', 'content': answer, 'sources': sources})}\n\n"
            except Exception as e:
                add_event("error", "chat", f"LLM answer failed: {e}")
                yield f"data: {_json.dumps({'type': 'answer', 'content': 'Failed to generate answer: ' + str(e), 'sources': []})}\n\n"

        else:
            # Store as memory
            from url_extract import enrich_text_with_urls, detect_urls
            store_text = text
            if detect_urls(store_text):
                try:
                    store_text = enrich_text_with_urls(store_text)
                except Exception:
                    pass
            scrubbed = scrub_text(store_text)
            try:
                extracted = categorize_and_extract(scrubbed)
            except Exception:
                extracted = {"category": "uncategorized"}
            try:
                embedding = get_embedding(scrubbed)
            except Exception:
                embedding = [0.0] * 1536
            metadata = dict(extracted)
            memory_id = add_memory(content=scrubbed, source_type="dashboard_chat", embedding=embedding, metadata=metadata)
            cat = extracted.get("category", "uncategorized")
            summ = extracted.get("summary", "")
            add_event("success", "chat", f"Stream stored memory {memory_id} (category: {cat})")
            yield f"data: {_json.dumps({'type': 'memory', 'content': 'Stored as memory (Category: ' + cat + ')', 'memory_id': memory_id, 'category': cat, 'summary': summ})}\n\n"

    return StreamingResponse(_generate_events(), media_type="text/event-stream")

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
        # Speech-to-text
        "sttProvider": os.getenv("STT_PROVIDER", "openai"),
        "openaiApiKey": mask(os.getenv("OPENAI_API_KEY", "")),
        "groqApiKey": mask(os.getenv("GROQ_API_KEY", "")),
        "whisperModelSize": os.getenv("WHISPER_MODEL_SIZE", "base"),
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
            "STT_PROVIDER": config.sttProvider,
            "OPENAI_API_KEY": config.openaiApiKey,
            "GROQ_API_KEY": config.groqApiKey,
            "WHISPER_MODEL_SIZE": config.whisperModelSize,
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

# --- Backend Restart ---

@app.post("/api/restart")
def restart_backend():
    """Restart Telegram bot and MCP server so they pick up new .env settings.
    The API server itself stays running (it reloads .env on each request).
    """
    import subprocess, signal
    restarted = []
    errors = []

    project_dir = os.path.dirname(os.path.dirname(__file__))
    venv_python = os.path.join(project_dir, "venv", "bin", "python")
    if not os.path.exists(venv_python):
        venv_python = "python"  # fallback

    # 1. Restart Telegram bot
    try:
        # Kill existing
        subprocess.run(["pkill", "-f", "python.*telegram_bot.py"], capture_output=True, timeout=5)
        import time; time.sleep(0.5)
        # Start new
        subprocess.Popen(
            [venv_python, "src/telegram_bot.py"],
            cwd=project_dir,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        restarted.append("telegram_bot")
    except Exception as e:
        errors.append(f"telegram_bot: {e}")

    # 2. Restart MCP server
    try:
        subprocess.run(["pkill", "-f", "python.*server.py"], capture_output=True, timeout=5)
        import time; time.sleep(0.5)
        env = os.environ.copy()
        env["MCP_TRANSPORT"] = "sse"
        subprocess.Popen(
            [venv_python, "src/server.py"],
            cwd=project_dir, env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        restarted.append("mcp_server")
    except Exception as e:
        errors.append(f"mcp_server: {e}")

    # 3. Reload .env in current process
    load_dotenv(override=True)

    msg = f"Restarted: {', '.join(restarted)}" if restarted else "No services restarted"
    if errors:
        msg += f". Errors: {'; '.join(errors)}"
    add_event("success" if not errors else "warning", "restart", msg)
    return {"success": len(errors) == 0, "restarted": restarted, "errors": errors}

# --- Speech-to-Text Utilities ---

@app.get("/api/stt/status")
def stt_status():
    """Check STT provider status and local Whisper installation."""
    load_dotenv(override=True)
    provider = os.getenv("STT_PROVIDER", "openai").strip("'\"")
    configured_model = os.getenv("WHISPER_MODEL_SIZE", "base").strip("'\"")
    result = {
        "provider": provider,
        "whisper_installed": False,
        "whisper_models": [],
        "configured_model": configured_model,
        "model_ready": False,
    }

    # Check if local whisper is installed
    try:
        import whisper
        result["whisper_installed"] = True
        # Check which config model sizes have their files downloaded
        # by resolving each size to its actual cache filename
        from transcribe import is_whisper_model_downloaded
        all_sizes = ["tiny", "base", "small", "medium", "large", "turbo"]
        result["whisper_models"] = [s for s in all_sizes if is_whisper_model_downloaded(s)]
        result["model_ready"] = configured_model in result["whisper_models"]
    except ImportError:
        pass

    # Check if groq is installed
    try:
        import groq
        result["groq_installed"] = True
    except ImportError:
        result["groq_installed"] = False

    return result

@app.post("/api/stt/install-whisper")
def install_whisper():
    """Install openai-whisper package for local transcription."""
    import subprocess
    try:
        add_event("info", "stt", "Installing openai-whisper (this may take a minute)...")
        proc = subprocess.run(
            ["pip", "install", "openai-whisper"],
            capture_output=True, text=True, timeout=300,
        )
        if proc.returncode == 0:
            add_event("success", "stt", "openai-whisper installed successfully")
            return {"success": True, "message": "openai-whisper installed successfully. You can now use STT_PROVIDER=local."}
        else:
            add_event("error", "stt", f"whisper install failed: {proc.stderr[:200]}")
            raise HTTPException(status_code=500, detail=f"Install failed: {proc.stderr[:500]}")
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=500, detail="Installation timed out (5 min). Try manually: pip install openai-whisper")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/stt/download-model")
def download_model(model_size: str = ""):
    """Pre-download a local Whisper model so it's ready for first use."""
    try:
        from transcribe import download_whisper_model
        if not model_size:
            model_size = os.getenv("WHISPER_MODEL_SIZE", "base").strip("'\"")
        add_event("info", "stt", f"Downloading Whisper model '{model_size}'...")
        result = download_whisper_model(model_size)
        if result["success"]:
            add_event("success", "stt", result["message"])
            return result
        else:
            add_event("error", "stt", result["message"])
            raise HTTPException(status_code=500, detail=result["message"])
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/stt/install-groq")
def install_groq():
    """Install groq SDK for Groq Whisper API."""
    import subprocess
    try:
        add_event("info", "stt", "Installing groq SDK...")
        proc = subprocess.run(
            ["pip", "install", "groq"],
            capture_output=True, text=True, timeout=120,
        )
        if proc.returncode == 0:
            add_event("success", "stt", "groq SDK installed successfully")
            return {"success": True, "message": "groq SDK installed. Set GROQ_API_KEY and STT_PROVIDER=groq."}
        else:
            raise HTTPException(status_code=500, detail=f"Install failed: {proc.stderr[:500]}")
    except Exception as e:
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

# --- Google Drive & Gmail (multi-account, search/preview/ingest) ---

@app.get("/api/google/status")
def google_status():
    """List all connected Google accounts and credentials file status."""
    from google_integration import get_status
    return get_status()

@app.post("/api/google/credentials/upload")
async def google_credentials_upload(file: UploadFile = File(...)):
    """Upload a Google OAuth credentials JSON file (any filename)."""
    try:
        content = await file.read()
        data = json.loads(content)
        # Validate it looks like a Google OAuth credentials file
        if "web" not in data and "installed" not in data:
            raise HTTPException(status_code=400, detail="Invalid credentials file. Must contain 'web' or 'installed' key from Google Cloud Console.")
        from google_integration import _CREDENTIALS_FILE
        _CREDENTIALS_FILE.write_bytes(content)
        add_event("success", "google", f"Google credentials uploaded ({file.filename})")
        return {"success": True, "filename": file.filename}
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="File is not valid JSON.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/google/connect")
def google_connect():
    """Start Google OAuth flow. Returns the auth URL."""
    from google_integration import start_oauth_flow
    result = start_oauth_flow()
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result

@app.get("/api/google/callback")
def google_callback(code: str = None, error: str = None, state: str = None):
    """OAuth callback — exchanges auth code for tokens."""
    if error:
        return {"error": error}
    if not code:
        raise HTTPException(status_code=400, detail="No authorization code received.")
    from google_integration import complete_oauth_flow
    result = complete_oauth_flow(code, state=state or "")
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    add_event("success", "google", f"Google account connected: {result.get('email')}")
    from fastapi.responses import HTMLResponse
    return HTMLResponse(f"""
        <html><body style="font-family:sans-serif;text-align:center;padding:3rem">
        <h2>Google Connected</h2>
        <p>Signed in as <strong>{result.get('email')}</strong></p>
        <p>You can close this tab and return to the Open Brain dashboard.</p>
        <script>setTimeout(()=>window.close(), 3000)</script>
        </body></html>
    """)

@app.post("/api/google/disconnect")
def google_disconnect(payload: dict):
    """Disconnect a specific Google account."""
    email = payload.get("email", "")
    if not email:
        raise HTTPException(status_code=400, detail="Email is required.")
    from google_integration import disconnect
    result = disconnect(email)
    add_event("info", "google", f"Google account disconnected: {email}")
    return result

# Drive: search/preview
@app.post("/api/google/drive/search")
def google_drive_search(payload: dict):
    """Search Google Drive files with filters. Returns preview list."""
    email = payload.get("email", "")
    if not email:
        raise HTTPException(status_code=400, detail="Email is required.")
    from google_integration import search_drive
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
@app.post("/api/google/drive/ingest")
def google_drive_ingest(payload: dict):
    """Ingest selected Google Drive files by their IDs."""
    email = payload.get("email", "")
    file_ids = payload.get("file_ids", [])
    if not email or not file_ids:
        raise HTTPException(status_code=400, detail="Email and file_ids are required.")
    from google_integration import ingest_drive_files
    add_event("info", "google", f"Ingesting {len(file_ids)} files from Drive ({email})...")
    result = ingest_drive_files(email, file_ids)
    if "error" in result:
        add_event("error", "google", f"Drive ingest failed: {result['error']}")
    else:
        add_event("success", "google", f"Drive: {len(result.get('ingested', []))} files ingested from {email}")
    return result

# Gmail: list labels (system + custom)
@app.get("/api/google/gmail/labels")
def google_gmail_labels(email: str):
    """List all Gmail labels (system + custom) for the given account."""
    if not email:
        raise HTTPException(status_code=400, detail="Email is required.")
    from google_integration import list_gmail_labels
    result = list_gmail_labels(email)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result

# Gmail: search/preview
@app.post("/api/google/gmail/search")
def google_gmail_search(payload: dict):
    """Search Gmail messages with filters. Returns preview list."""
    email = payload.get("email", "")
    if not email:
        raise HTTPException(status_code=400, detail="Email is required.")
    from google_integration import search_gmail
    result = search_gmail(
        email=email,
        query=payload.get("query", ""),
        from_filter=payload.get("from_filter", ""),
        subject_filter=payload.get("subject_filter", ""),
        label=payload.get("label", ""),
        newer_than=payload.get("newer_than", "7d"),
        max_results=payload.get("max_results", 25),
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result

# Gmail: ingest selected messages
@app.post("/api/google/gmail/ingest")
def google_gmail_ingest(payload: dict):
    """Ingest selected Gmail messages by their IDs."""
    email = payload.get("email", "")
    message_ids = payload.get("message_ids", [])
    if not email or not message_ids:
        raise HTTPException(status_code=400, detail="Email and message_ids are required.")
    include_images = payload.get("include_images", False)
    from google_integration import ingest_gmail_messages
    add_event("info", "google", f"Ingesting {len(message_ids)} emails from Gmail ({email}){' with images' if include_images else ''}...")
    result = ingest_gmail_messages(email, message_ids, include_images=include_images)
    if "error" in result:
        add_event("error", "google", f"Gmail ingest failed: {result['error']}")
    else:
        add_event("success", "google", f"Gmail: {len(result.get('ingested', []))} emails ingested from {email}")
    return result

# Gmail: preview full email body
@app.post("/api/google/gmail/preview")
def google_gmail_preview(payload: dict):
    """Fetch the full body of a single Gmail message for reading before ingest."""
    email = payload.get("email", "")
    message_id = payload.get("message_id", "")
    if not email or not message_id:
        raise HTTPException(status_code=400, detail="Email and message_id are required.")
    from google_integration import preview_gmail_message
    result = preview_gmail_message(email, message_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result

# Calendar: scan events
@app.post("/api/google/calendar/scan")
def google_calendar_scan(payload: dict):
    """Scan calendar events for a connected Google account."""
    email = payload.get("email", "")
    if not email:
        raise HTTPException(status_code=400, detail="Email is required.")
    from google_integration import scan_calendar_events
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
@app.post("/api/google/calendar/ingest")
def google_calendar_ingest(payload: dict):
    """Ingest selected calendar events as memories."""
    email = payload.get("email", "")
    event_ids = payload.get("event_ids", [])
    if not email or not event_ids:
        raise HTTPException(status_code=400, detail="Email and event_ids are required.")
    from google_integration import ingest_calendar_events
    add_event("info", "google", f"Ingesting {len(event_ids)} calendar events ({email})...")
    result = ingest_calendar_events(email, event_ids)
    if "error" in result:
        add_event("error", "google", f"Calendar ingest failed: {result['error']}")
    else:
        add_event("success", "google", f"Calendar: {len(result.get('ingested', []))} events ingested from {email}")
    return result

# --- Google Photos (Picker API) ---

@app.post("/api/google/photos/create-session")
def google_photos_create_session(payload: dict):
    """Create a Google Photos Picker session for the user to select photos."""
    email = payload.get("email", "")
    if not email:
        raise HTTPException(status_code=400, detail="Email is required.")
    from google_integration import create_photos_session
    result = create_photos_session(email)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    add_event("info", "google", f"Photos Picker session created for {email}")
    return result

@app.get("/api/google/photos/poll-session")
def google_photos_poll_session(email: str, session_id: str):
    """Poll a Photos Picker session to check if user finished selecting."""
    if not email or not session_id:
        raise HTTPException(status_code=400, detail="Email and session_id are required.")
    from google_integration import poll_photos_session
    result = poll_photos_session(email, session_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result

@app.get("/api/google/photos/media-items")
def google_photos_media_items(email: str, session_id: str):
    """List media items the user selected in the Picker."""
    if not email or not session_id:
        raise HTTPException(status_code=400, detail="Email and session_id are required.")
    from google_integration import list_photos_media_items
    result = list_photos_media_items(email, session_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result

@app.post("/api/google/photos/ingest")
def google_photos_ingest(payload: dict):
    """Download and ingest selected Google Photos via vision model."""
    email = payload.get("email", "")
    items = payload.get("items", [])
    if not email or not items:
        raise HTTPException(status_code=400, detail="Email and items are required.")
    from google_integration import ingest_photos
    add_event("info", "google", f"Ingesting {len(items)} photos from Google Photos ({email})...")
    result = ingest_photos(email, items)
    if "error" in result:
        add_event("error", "google", f"Photos ingest failed: {result['error']}")
    else:
        add_event("success", "google", f"Photos: {len(result.get('ingested', []))} photos ingested from {email}")
    return result

# --- WhatsApp Import ---

class WhatsAppImport(BaseModel):
    chat_name: str = "WhatsApp Chat"

@app.post("/api/whatsapp/import")
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
