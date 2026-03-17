"""Health check and database statistics endpoints."""
import os
import requests as http_requests
from fastapi import APIRouter, HTTPException
from dotenv import load_dotenv

router = APIRouter()


@router.get("/api/health")
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


@router.get("/api/db/stats")
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
