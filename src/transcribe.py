"""
Speech-to-text transcription module for Open Brain.
Configurable via STT_PROVIDER env var.

Supported providers:
- openai   (default) — OpenAI Whisper API, fast, auto-detects language
- local    — Local openai-whisper model, fully private, requires `pip install openai-whisper`
- groq     — Groq Whisper API (free tier), requires GROQ_API_KEY
"""
import os
import io
import tempfile
import subprocess
import warnings
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

STT_PROVIDER = os.getenv("STT_PROVIDER", "openai").strip("'\"").lower()

# Formats accepted natively by OpenAI Whisper API
_OPENAI_FORMATS = {".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".wav", ".webm"}

# Cache for loaded local whisper model (avoid reloading on every call)
_local_model_cache: dict = {}


def _get_device() -> str:
    """Detect best available device: cuda > mps > cpu. Works on Linux, macOS, Windows."""
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda"
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
    except ImportError:
        pass
    return "cpu"


def _resolve_whisper_filename(model_size: str) -> str:
    """Resolve the actual cache filename for a Whisper model size.
    e.g. 'large' -> 'large-v3.pt', 'base' -> 'base.pt', 'turbo' -> 'large-v3-turbo.pt'
    """
    try:
        import whisper
        url = whisper._MODELS.get(model_size, "")
        if url:
            # URL ends with e.g. .../large-v3.pt — extract the filename
            return url.split("/")[-1]
    except (ImportError, AttributeError):
        pass
    # Fallback: assume model_size.pt
    return f"{model_size}.pt"


def is_whisper_model_downloaded(model_size: str = "") -> bool:
    """Check if a local Whisper model has already been downloaded."""
    if not model_size:
        model_size = os.getenv("WHISPER_MODEL_SIZE", "base").strip("'\"")
    whisper_dir = Path.home() / ".cache" / "whisper"
    filename = _resolve_whisper_filename(model_size)
    return (whisper_dir / filename).exists()


def download_whisper_model(model_size: str = "") -> dict:
    """Pre-download a local Whisper model so it's ready for first use. Returns status dict."""
    if not model_size:
        model_size = os.getenv("WHISPER_MODEL_SIZE", "base").strip("'\"")

    if is_whisper_model_downloaded(model_size):
        return {"success": True, "message": f"Model '{model_size}' is already downloaded.", "already_cached": True}

    try:
        import whisper
    except ImportError:
        return {"success": False, "message": "openai-whisper is not installed. Install it first."}

    try:
        device = _get_device()
        # This triggers the download
        whisper.load_model(model_size, device=device)
        _local_model_cache.clear()  # Clear cache so next transcribe picks up fresh
        return {"success": True, "message": f"Model '{model_size}' downloaded successfully.", "already_cached": False}
    except Exception as e:
        return {"success": False, "message": f"Failed to download model '{model_size}': {e}"}


def transcribe_audio(file_bytes: bytes, filename: str = "audio.ogg") -> dict:
    """
    Transcribe audio bytes to text. Returns:
    {
        "text": str,         # Transcribed text
        "language": str,     # Detected language code (e.g. "en", "hu")
        "provider": str,     # Which STT provider was used
        "error": str | None,
    }
    """
    provider = STT_PROVIDER
    try:
        if provider == "openai":
            return _transcribe_openai(file_bytes, filename)
        elif provider == "local":
            return _transcribe_local(file_bytes, filename)
        elif provider == "groq":
            return _transcribe_groq(file_bytes, filename)
        else:
            return {"text": "", "language": "", "provider": provider,
                    "error": f"Unknown STT_PROVIDER: {provider}. Use 'openai', 'local', or 'groq'."}
    except Exception as e:
        return {"text": "", "language": "", "provider": provider, "error": str(e)}


def _convert_to_mp3(file_bytes: bytes, filename: str) -> tuple[bytes, str]:
    """Convert audio to mp3 using ffmpeg if the format isn't natively supported."""
    ext = os.path.splitext(filename)[1].lower()
    if ext in _OPENAI_FORMATS:
        return file_bytes, filename

    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as src:
        src.write(file_bytes)
        src_path = src.name

    dst_path = src_path.rsplit(".", 1)[0] + ".mp3"
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", src_path, "-vn", "-acodec", "libmp3lame",
             "-ar", "16000", "-ac", "1", "-q:a", "4", dst_path],
            capture_output=True, check=True, timeout=30,
        )
        with open(dst_path, "rb") as f:
            mp3_bytes = f.read()
        return mp3_bytes, os.path.basename(dst_path)
    finally:
        for p in (src_path, dst_path):
            try:
                os.unlink(p)
            except OSError:
                pass


def _transcribe_openai(file_bytes: bytes, filename: str) -> dict:
    """Transcribe using OpenAI Whisper API."""
    from openai import OpenAI

    api_key = os.getenv("OPENAI_API_KEY", "").strip("'\"")
    if not api_key:
        # Fall back to LLM_API_KEY if it looks like an OpenAI key
        llm_key = os.getenv("LLM_API_KEY", "").strip("'\"")
        if llm_key.startswith("sk-") and "or-" not in llm_key:
            api_key = llm_key

    if not api_key:
        return {"text": "", "language": "", "provider": "openai",
                "error": "No OPENAI_API_KEY set. Whisper API requires a direct OpenAI key (not OpenRouter)."}

    # Convert format if needed
    audio_bytes, audio_name = _convert_to_mp3(file_bytes, filename)

    client = OpenAI(api_key=api_key)
    audio_file = io.BytesIO(audio_bytes)
    audio_file.name = audio_name

    # Use verbose_json to get language detection
    resp = client.audio.transcriptions.create(
        model="whisper-1",
        file=audio_file,
        response_format="verbose_json",
    )

    return {
        "text": resp.text,
        "language": getattr(resp, "language", "unknown"),
        "provider": "openai",
        "error": None,
    }


def _transcribe_local(file_bytes: bytes, filename: str) -> dict:
    """Transcribe using local openai-whisper model.
    Detects GPU (CUDA/MPS) and uses it if available; uses fp16=False on CPU
    to avoid the 'FP16 is not supported on CPU' warning.
    Caches the loaded model to avoid reloading on every call.
    """
    try:
        import whisper
    except ImportError:
        return {"text": "", "language": "", "provider": "local",
                "error": "Local Whisper not installed. Run: pip install openai-whisper"}

    model_size = os.getenv("WHISPER_MODEL_SIZE", "base").strip("'\"")
    device = _get_device()
    use_fp16 = device in ("cuda",)  # fp16 only on CUDA; False for cpu and mps

    # Check if model needs downloading (warn caller this may take a while)
    needs_download = not is_whisper_model_downloaded(model_size)

    # Write to temp file (whisper needs a file path)
    ext = os.path.splitext(filename)[1] or ".ogg"
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name

    try:
        # Load model (cached across calls)
        cache_key = f"{model_size}_{device}"
        if cache_key not in _local_model_cache:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                _local_model_cache[cache_key] = whisper.load_model(model_size, device=device)
        model = _local_model_cache[cache_key]

        result = model.transcribe(tmp_path, fp16=use_fp16)
        text = result.get("text", "")
        language = result.get("language", "unknown")

        # If model was just downloaded, note it in the response
        extra = ""
        if needs_download:
            extra = " (model was downloaded on first use)"

        return {
            "text": text,
            "language": language,
            "provider": f"local ({model_size}, {device}){extra}",
            "error": None,
        }
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def _transcribe_groq(file_bytes: bytes, filename: str) -> dict:
    """Transcribe using Groq Whisper API."""
    try:
        from groq import Groq
    except ImportError:
        return {"text": "", "language": "", "provider": "groq",
                "error": "Groq SDK not installed. Run: pip install groq"}

    api_key = os.getenv("GROQ_API_KEY", "").strip("'\"")
    if not api_key:
        return {"text": "", "language": "", "provider": "groq",
                "error": "No GROQ_API_KEY set."}

    # Convert format if needed (Groq accepts same formats as OpenAI)
    audio_bytes, audio_name = _convert_to_mp3(file_bytes, filename)

    client = Groq(api_key=api_key)
    audio_file = io.BytesIO(audio_bytes)
    audio_file.name = audio_name

    resp = client.audio.transcriptions.create(
        model="whisper-large-v3-turbo",
        file=audio_file,
        response_format="verbose_json",
    )

    return {
        "text": resp.text,
        "language": getattr(resp, "language", "unknown"),
        "provider": "groq",
        "error": None,
    }
