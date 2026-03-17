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

# Re-export from shared module so existing callers (telegram_bot etc.) still work
from event_log import event_log, add_event  # noqa: F401

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
