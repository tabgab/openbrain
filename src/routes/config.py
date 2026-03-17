"""Configuration, restart, and logs endpoints."""
import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from dotenv import set_key, load_dotenv

from api import add_event

router = APIRouter()


@router.get("/api/logs")
def get_logs():
    """Returns the in-memory system event log."""
    from api import event_log
    return {"logs": list(reversed(event_log))}


@router.post("/api/logs")
def post_log(payload: dict):
    """Allows background processes (telegram bot) to post events to the log."""
    add_event(
        payload.get("level", "info"),
        payload.get("source", "system"),
        payload.get("message", "")
    )
    return {"ok": True}


class ConfigUpdate(BaseModel):
    telegramToken: str = ""
    llmApiKey: str = ""
    dbPassword: str = ""
    dbUser: str = ""
    dbName: str = ""
    dbHost: str = ""
    llmBaseUrl: str = ""
    modelText: str = ""
    modelReasoning: str = ""
    modelCoding: str = ""
    modelVision: str = ""
    modelEmbedding: str = ""
    sttProvider: str = ""
    openaiApiKey: str = ""
    groqApiKey: str = ""
    whisperModelSize: str = ""


@router.get("/api/config")
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


@router.post("/api/config")
def update_config(config: ConfigUpdate):
    """Updates .env file with new credentials from the setup wizard or settings page."""
    env_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env")
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


@router.post("/api/restart")
def restart_backend():
    """Restart Telegram bot and MCP server so they pick up new .env settings.
    The API server itself stays running (it reloads .env on each request).
    """
    import subprocess, signal
    restarted = []
    errors = []

    project_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
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
