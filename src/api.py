"""
Open Brain — Dashboard API
---------------------------
Core app setup, CORS, event logging, and router registration.
Route handlers live in the routes/ package.
"""
import sys
import os
import warnings
# Suppress multiprocessing resource_tracker "leaked semaphore" warning on shutdown
# (caused by PyTorch/Whisper internals, harmless — OS reclaims semaphores on exit)
warnings.filterwarnings("ignore", message=".*resource_tracker.*", category=UserWarning)
# Ensure src/ is in path so 'db', 'llm' etc. are importable when uvicorn runs from project root
sys.path.insert(0, os.path.dirname(__file__))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

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

# ---------------------------------------------------------------------------
# Register route modules
# ---------------------------------------------------------------------------
from routes.health import router as health_router
from routes.memories import router as memories_router
from routes.chat import router as chat_router
from routes.config import router as config_router
from routes.stt import router as stt_router
from routes.backup import router as backup_router
from routes.google import router as google_router
from routes.whatsapp import router as whatsapp_router

app.include_router(health_router)
app.include_router(memories_router)
app.include_router(chat_router)
app.include_router(config_router)
app.include_router(stt_router)
app.include_router(backup_router)
app.include_router(google_router)
app.include_router(whatsapp_router)
