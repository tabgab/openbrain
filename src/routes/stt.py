"""Speech-to-text utility endpoints."""
import os
from fastapi import APIRouter, HTTPException
from dotenv import load_dotenv

from event_log import add_event

router = APIRouter()


@router.get("/api/stt/status")
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


@router.post("/api/stt/install-whisper")
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


@router.post("/api/stt/download-model")
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


@router.post("/api/stt/install-groq")
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
