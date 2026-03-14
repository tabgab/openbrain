import os
import requests
import time
import sys
from dotenv import load_dotenv

load_dotenv()

from db import add_memory, query_memories
from llm import categorize_and_extract, get_embedding, get_client
from scrubber import scrub_text
from ingest import ingest_document

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip("'\"")
AUTHORIZED_CHAT_ID = os.getenv("TELEGRAM_AUTHORIZED_CHAT_ID", "").strip("'\"")
API_LOG_URL = "http://localhost:8000/api/logs"

def post_log(level: str, message: str):
    """Send a log event to the dashboard UI. Also always print to console."""
    print(f"[OpenBrain Telegram Bot] [{level.upper()}] {message}", flush=True)
    try:
        requests.post(API_LOG_URL, json={"level": level, "source": "telegram_bot", "message": message}, timeout=2)
    except Exception:
        pass  # If the API is down, the console log above is sufficient

def get_updates(offset=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
    params = {"timeout": 30, "offset": offset}
    try:
        response = requests.get(url, params=params, timeout=40)
        data = response.json()
        if not data.get("ok"):
            post_log("error", f"Telegram API rejected request: {data.get('description', 'Unknown error')}")
        return data
    except requests.exceptions.Timeout:
        post_log("warning", "Telegram long-poll timed out (normal), retrying...")
        return {"ok": False, "result": []}
    except Exception as e:
        post_log("error", f"Network error polling Telegram: {e}")
        return {"ok": False, "result": []}

def send_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        post_log("error", f"Failed to send reply to Telegram: {e}")

def download_telegram_file(file_id: str) -> tuple[bytes, str]:
    """Download a file from Telegram by file_id. Returns (file_bytes, filename)."""
    # Get file path from Telegram
    resp = requests.get(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getFile",
        params={"file_id": file_id}, timeout=10
    ).json()
    if not resp.get("ok"):
        raise Exception(f"Failed to get file info: {resp.get('description')}")
    file_path = resp["result"]["file_path"]
    filename = file_path.split("/")[-1]
    # Download the actual file
    file_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"
    file_resp = requests.get(file_url, timeout=60)
    file_resp.raise_for_status()
    return file_resp.content, filename


def handle_attachment(chat_id, message):
    """Process a document or photo attachment sent via Telegram."""
    caption = message.get("caption", "")

    # Determine the file_id and filename
    if "document" in message:
        doc = message["document"]
        file_id = doc["file_id"]
        filename = doc.get("file_name", "document")
        post_log("info", f"Received document: {filename} ({doc.get('file_size', '?')} bytes)")
    elif "photo" in message:
        # Telegram sends multiple sizes; use the largest
        photo = message["photo"][-1]
        file_id = photo["file_id"]
        filename = "telegram_photo.jpg"
        post_log("info", f"Received photo ({photo.get('file_size', '?')} bytes)")
    else:
        return False  # Not an attachment we handle

    send_message(chat_id, f"📄 Processing {filename}...")

    try:
        # Download from Telegram
        file_bytes, resolved_name = download_telegram_file(file_id)
        # Use the original filename if available, else the resolved one
        final_name = filename if filename != "document" else resolved_name

        # Run through ingestion pipeline
        result = ingest_document(final_name, file_bytes)
        extracted_text = result["text"]

        if not extracted_text or extracted_text.startswith("["):
            post_log("warning", f"Limited extraction from {final_name}: {extracted_text[:100]}")
            send_message(chat_id, f"⚠️ Could not extract much from {final_name}: {extracted_text[:200]}")
            return True

        # Prepend caption as context if provided
        if caption:
            extracted_text = f"[User note: {caption}]\n\n{extracted_text}"

        # Categorize
        metadata = categorize_and_extract(extracted_text[:2000])
        metadata["filename"] = final_name
        metadata["ingestion_method"] = result["method"]
        metadata["source"] = "telegram"

        # Embed and save
        embedding = get_embedding(extracted_text[:8000])
        memory_id = add_memory(
            content=extracted_text,
            source_type=result["source_type"],
            embedding=embedding,
            metadata=metadata,
        )

        category = metadata.get("category", "unknown")
        summary = metadata.get("summary", "")[:150]
        post_log("success", f"Document '{final_name}' ingested via Telegram as memory {memory_id}")
        send_message(chat_id, f"✅ Ingested: {final_name}\nCategory: {category}\nSummary: {summary}\nID: {memory_id}")
        return True

    except Exception as e:
        post_log("error", f"Failed to process attachment {filename}: {e}")
        send_message(chat_id, f"❌ Failed to process {filename}: {e}")
        return True


QUESTION_WORDS = {
    "who", "what", "when", "where", "why", "how",
    "do", "does", "did", "is", "are", "was", "were",
    "can", "could", "will", "would", "should", "shall",
    "have", "has", "had", "which", "whose", "whom",
    "tell", "explain", "describe", "show",
}

def is_question(text: str) -> bool:
    """Detect whether a message is a question (vs. a memory to store).
    Uses heuristics first, falls back to the text model for ambiguous cases."""
    stripped = text.strip()

    # Obvious: ends with question mark
    if stripped.endswith("?"):
        return True

    # Starts with a common question word
    first_word = stripped.split()[0].lower().rstrip(",:;") if stripped else ""
    if first_word in QUESTION_WORDS:
        return True

    # Short imperative that looks like a query (e.g. "find my dentist invoice")
    if first_word in {"find", "search", "look", "list", "get", "recall", "remember"}:
        return True

    # If it's very short and doesn't look like a note, probably a question
    # For anything ambiguous, ask the LLM (cheap & fast text model)
    if len(stripped.split()) >= 3:
        try:
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
            return "QUESTION" in answer
        except Exception as e:
            post_log("warning", f"Question detection LLM call failed: {e}")

    return False


def handle_ask(chat_id, question):
    """Search the brain for relevant memories and answer the question using the LLM."""
    post_log("info", f"Question from chat_id={chat_id}: '{question[:60]}...'")

    try:
        embedding = get_embedding(question)
        results = query_memories(embedding=embedding, limit=5)
    except Exception as e:
        post_log("error", f"Brain search failed: {e}")
        send_message(chat_id, "❌ Failed to search the brain.")
        return

    if not results:
        send_message(chat_id, "🤷 No relevant memories found in your Open Brain yet.")
        return

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
                    "say so honestly. Be concise."
                )},
                {"role": "user", "content": f"Memories:\n{context}\n\nQuestion: {question}"},
            ],
        )
        answer = resp.choices[0].message.content
        post_log("success", f"Answered question (used {len(results)} memories)")
        send_message(chat_id, f"🧠 {answer}")
    except Exception as e:
        post_log("error", f"LLM answer generation failed: {e}")
        send_message(chat_id, "❌ Could not generate an answer right now.")

def process_message(message):
    chat_id = str(message.get("chat", {}).get("id"))
    text = message.get("text") or message.get("caption")

    # Authorization guard (check early, before any processing)
    if AUTHORIZED_CHAT_ID and chat_id != AUTHORIZED_CHAT_ID:
        post_log("warning", f"Unauthorized access attempt from chat_id={chat_id}")
        send_message(chat_id, "❌ You are not authorized to write to this Open Brain.")
        return

    # Handle attachments (documents, photos)
    if "document" in message or "photo" in message:
        handle_attachment(chat_id, message)
        return

    if not text:
        post_log("info", "Received unsupported message type (sticker, voice, etc.), ignoring.")
        return

    # Handle questions — explicit prefixes (fast path)
    if text.startswith("/ask"):
        question = text[len("/ask"):].strip()
        if not question:
            send_message(chat_id, "Usage: /ask <your question>")
            return
        handle_ask(chat_id, question)
        return

    if text.lower().startswith("q:"):
        handle_ask(chat_id, text[2:].strip())
        return

    # Force-store prefix: user explicitly wants to save as memory
    if text.lower().startswith("m:") or text.lower().startswith("memo:"):
        text = text.split(":", 1)[1].strip()
        # fall through to memory storage below
    else:
        # Auto-detect questions
        if is_question(text):
            post_log("info", f"Auto-detected question from chat_id={chat_id}: '{text[:60]}'")
            handle_ask(chat_id, text)
            return

    post_log("info", f"Storing memory from chat_id={chat_id}: '{text[:60]}...'")

    # 0. Scrub for PII
    text = scrub_text(text)

    # 1. Categorize
    try:
        extracted = categorize_and_extract(text)
        post_log("info", f"Categorized as: {extracted.get('category')}")
    except Exception as e:
        post_log("error", f"Categorization failed: {e}")
        extracted = {"category": "uncategorized"}

    # 2. Embed
    try:
        embedding = get_embedding(text)
    except Exception as e:
        post_log("error", f"Embedding failed: {e}")
        embedding = [0.0] * 1536

    # 3. Save
    try:
        memory_id = add_memory(content=text, source_type="telegram", embedding=embedding, metadata=extracted)
        category = extracted.get("category", "unknown")
        post_log("success", f"Memory saved — ID: {memory_id}, Category: {category}")
        send_message(chat_id, f"✅ Logged to Open Brain.\nCategory: {category}\nID: {memory_id}")
    except Exception as e:
        post_log("error", f"Failed to save memory to database: {e}")
        send_message(chat_id, f"❌ Failed to save memory: {e}")

def validate_token() -> bool:
    """Verify the token is valid before starting the poll loop."""
    if not TELEGRAM_BOT_TOKEN:
        post_log("error", "TELEGRAM_BOT_TOKEN is not set. Telegram bot cannot start.")
        return False

    try:
        resp = requests.get(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getMe", timeout=10
        ).json()
        if resp.get("ok"):
            bot_name = resp["result"].get("username", "unknown")
            post_log("success", f"Telegram Bot authenticated successfully as @{bot_name}")
            return True
        else:
            post_log("error", f"Telegram token is INVALID: {resp.get('description')} — Please get a new token from @BotFather.")
            return False
    except Exception as e:
        post_log("error", f"Could not reach Telegram servers during auth: {e}")
        return False

def main():
    post_log("info", "Open Brain Telegram Capture Bot starting...")

    if not validate_token():
        post_log("error", "Bot startup aborted due to invalid token. Fix TELEGRAM_BOT_TOKEN in your .env and restart.")
        sys.exit(1)

    post_log("info", "Starting long-poll loop. Send a message to your bot to test.")
    update_id = None

    while True:
        try:
            updates = get_updates(offset=update_id)
            if updates.get("ok"):
                for item in updates["result"]:
                    update_id = item["update_id"] + 1
                    message = item.get("message") or item.get("edited_message")
                    if message:
                        process_message(message)
            else:
                time.sleep(5)  # back off on error
        except KeyboardInterrupt:
            post_log("info", "Bot shutting down.")
            break
        except Exception as e:
            post_log("error", f"Unexpected error in poll loop: {e}. Retrying in 10s...")
            time.sleep(10)

if __name__ == "__main__":
    main()
