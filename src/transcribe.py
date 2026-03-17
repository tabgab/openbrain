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
from dotenv import load_dotenv

load_dotenv()

STT_PROVIDER = os.getenv("STT_PROVIDER", "openai").strip("'\"").lower()

# Formats accepted natively by OpenAI Whisper API
_OPENAI_FORMATS = {".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".wav", ".webm"}


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
    """Transcribe using local openai-whisper model."""
    try:
        import whisper
    except ImportError:
        return {"text": "", "language": "", "provider": "local",
                "error": "Local Whisper not installed. Run: pip install openai-whisper"}

    # Write to temp file (whisper needs a file path)
    ext = os.path.splitext(filename)[1] or ".ogg"
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name

    try:
        model_size = os.getenv("WHISPER_MODEL_SIZE", "base").strip("'\"")
        model = whisper.load_model(model_size)
        result = model.transcribe(tmp_path)
        return {
            "text": result.get("text", ""),
            "language": result.get("language", "unknown"),
            "provider": "local",
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
