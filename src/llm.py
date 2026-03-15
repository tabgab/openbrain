import os
import json
import base64
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Model role definitions
# Each role has: env var for model name, optional per-role API key & base URL
# ---------------------------------------------------------------------------
MODEL_ROLES = {
    "text":      {"env": "MODEL_TEXT",      "default": "moonshotai/kimi-k2.5",          "desc": "Categorization, extraction, simple chat"},
    "reasoning": {"env": "MODEL_REASONING", "default": "anthropic/claude-sonnet-4.6",   "desc": "Complex analysis, research, nuanced Q&A"},
    "coding":    {"env": "MODEL_CODING",    "default": "minimax/minimax-m2.5",          "desc": "Code generation, debugging, technical analysis"},
    "vision":    {"env": "MODEL_VISION",    "default": "moonshotai/kimi-k2.5",          "desc": "Image recognition, OCR, invoice parsing"},
    "embedding": {"env": "MODEL_EMBEDDING", "default": "openai/text-embedding-3-small","desc": "Vector embeddings for semantic search"},
}

# Shared defaults
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://openrouter.ai/api/v1").strip("'\"")
LLM_API_KEY = os.getenv("LLM_API_KEY", os.getenv("OPENAI_API_KEY", "")).strip("'\"")

OPENROUTER_HEADERS = {
    "HTTP-Referer": "https://github.com/openbrain",
    "X-Title": "Open Brain",
}

def _get_role_config(role: str) -> tuple[str, str, str]:
    """Returns (model_name, api_key, base_url) for a given role, with fallback to shared config."""
    role_def = MODEL_ROLES.get(role, MODEL_ROLES["text"])
    env_prefix = role_def["env"]
    model = os.getenv(env_prefix, role_def["default"]).strip("'\"")
    api_key = os.getenv(f"{env_prefix}_API_KEY", "").strip("'\"") or LLM_API_KEY
    base_url = os.getenv(f"{env_prefix}_BASE_URL", "").strip("'\"") or LLM_BASE_URL
    return model, api_key, base_url

def get_client(role: str = "text") -> tuple[OpenAI, str]:
    """Returns an (OpenAI client, model_name) tuple configured for the given role."""
    model, api_key, base_url = _get_role_config(role)
    client = OpenAI(api_key=api_key, base_url=base_url, default_headers=OPENROUTER_HEADERS)
    return client, model

# Convenience: default client + model names for backward compatibility
client, TEXT_MODEL = get_client("text")
EMBEDDING_MODEL, _, _ = _get_role_config("embedding")

def get_embedding(text: str) -> list[float]:
    """
    Generates a 1536-dimensional vector embedding for the given text.
    """
    if not LLM_API_KEY:
        print("Warning: No LLM_API_KEY set. Using mock embedding.", flush=True)
        return [0.0] * 1536
    try:
        embed_client, embed_model = get_client("embedding")
        response = embed_client.embeddings.create(input=text, model=embed_model)
        return response.data[0].embedding
    except Exception as e:
        print(f"Error generating embedding: {e}", flush=True)
        return [0.0] * 1536

def categorize_and_extract(text: str) -> dict:
    """
    Uses an LLM to categorize the incoming raw text (e.g. invoice, idea, task, note)
    and extract relevant metadata.
    """
    if not LLM_API_KEY:
        return {"category": "uncategorized", "summary": text[:50]}
        
    system_prompt = """
You are the Open Brain formatting module.
Your job is to read raw incoming text (which could be an email, a chat message, a receipt OCR, or a personal thought),
categorize it, and extract key metadata into a rigid JSON structure.
Extract things like cost (if it's a purchase), date referenced, or names involved.

Respond strictly with valid JSON using the following structure:
{
    "category": "<one of: invoice, idea, task, note, reference, communication, other>",
    "summary": "<a 1-sentence summary of the content>",
    "extracted_entities": {
        "dates": ["list of dates mentioned"],
        "cost": "any monetary value",
        "people": ["names of people mentioned"]
    }
}
"""
    VALID_CATEGORIES = {"invoice", "idea", "task", "note", "reference", "communication", "other"}
    try:
        text_client, text_model = get_client("text")
        response = text_client.chat.completions.create(
            model=text_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text}
            ],
            response_format={ "type": "json_object" }
        )
        result = json.loads(response.choices[0].message.content)
        # Validate and sanitize the category
        cat = str(result.get("category", "")).strip().lower()
        if cat not in VALID_CATEGORIES:
            result["category"] = "other"
        else:
            result["category"] = cat
        if not result.get("summary"):
            result["summary"] = text[:80]
        return result
    except Exception as e:
        print(f"Error categorizing text: {e}", flush=True)
        return {"category": "other", "summary": text[:80]}

def describe_image(image_bytes: bytes, mime_type: str = "image/png", prompt: str = None) -> str:
    """
    Uses a vision model to describe / OCR an image.
    Returns the extracted text content.
    """
    if not LLM_API_KEY:
        return "[Vision model unavailable — no API key configured]"

    if prompt is None:
        prompt = (
            "Extract ALL text and information from this image. If it's an invoice or receipt, "
            "extract every line item, date, total, vendor name, and any other details. "
            "If it's a document, transcribe the full content. If it's a photo, describe what you see in detail."
        )

    b64 = base64.b64encode(image_bytes).decode("utf-8")
    vision_client, vision_model = get_client("vision")

    try:
        response = vision_client.chat.completions.create(
            model=vision_model,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{b64}"}},
                ],
            }],
            max_tokens=4096,
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"Error in vision model: {e}", flush=True)
        return f"[Vision extraction failed: {e}]"
