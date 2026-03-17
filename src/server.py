from mcp.server.fastmcp import FastMCP
from typing import Optional, List, Dict, Any
from db import (
    add_memory, query_memories, get_recent_memories,
    update_memory, delete_memory as db_delete_memory,
    store_secret, retrieve_secret,
)
from llm import get_embedding, categorize_and_extract, get_client
from scrubber import scrub_text
import sys
import os
import json
import base64
import tempfile

# Create the MCP server named "Open Brain"
_mcp_port = int(os.getenv("MCP_PORT", "3100"))
mcp = FastMCP("Open Brain", host="0.0.0.0", port=_mcp_port)


# ---------------------------------------------------------------------------
# Memory tools
# ---------------------------------------------------------------------------

@mcp.tool()
def save_memory(content: str, source_type: str = "mcp_client", metadata: Optional[Dict[str, Any]] = None) -> str:
    """
    Saves a new memory or fact about the user into the Open Brain.
    Use this to persist important information, facts, or context you learn about the user.
    The content is automatically categorized, embedded for semantic search, and scrubbed for PII.
    """
    if metadata is None:
        metadata = {}

    content = scrub_text(content)
    extracted_data = categorize_and_extract(content)
    metadata.update(extracted_data)
    embedding = get_embedding(content)

    memory_id = add_memory(
        content=content,
        source_type=source_type,
        embedding=embedding,
        metadata=metadata
    )
    return f"Successfully saved memory (Category: {extracted_data.get('category')}) with ID: {memory_id}"


@mcp.tool()
def search_brain(query_concept: str, limit: int = 5) -> str:
    """
    Searches the Open Brain for relevant memories using semantic similarity.
    Use this to find information the user has previously stored — notes, invoices,
    ideas, tasks, documents, etc. Returns the most relevant matches.
    """
    embedding = get_embedding(query_concept)
    results = query_memories(embedding=embedding, limit=limit)

    if not results:
        return "No relevant memories found in the Open Brain."

    formatted_results = []
    for r in results:
        formatted_results.append(
            f"[{r['created_at']}] From {r['source_type']} (ID: {r['id']}):\n"
            f"{r['content']}\n(Meta: {json.dumps(r['metadata'])})"
        )
    return "\n\n---\n\n".join(formatted_results)


@mcp.tool()
def ask_brain(question: str) -> str:
    """
    Ask a question and get an AI-generated answer based on your stored memories,
    Google Calendar events, and Gmail messages. The system intelligently decides
    which sources to search and expands queries with common sense.
    """
    embedding = get_embedding(question)
    results = query_memories(embedding=embedding, limit=5)

    # Use augmented search to also query Calendar/Gmail if relevant
    try:
        from smart_search import augmented_search
        search_result = augmented_search(question, results or [])
        context = search_result["combined_context"]
    except Exception:
        context = "\n\n".join(
            f"- [{r['source_type']} · {r['created_at']}] {r['content']}" for r in results
        ) if results else ""

    if not context:
        return "No relevant memories or data found to answer this question."

    reasoning_client, reasoning_model = get_client("reasoning")
    resp = reasoning_client.chat.completions.create(
        model=reasoning_model,
        messages=[
            {"role": "system", "content": (
                "You are the Open Brain assistant. Answer the user's question based on "
                "ALL the information retrieved below — this includes stored memories AND "
                "live data from Google Calendar and Gmail searches. "
                "Use all available context to give the best possible answer. "
                "If multiple sources help, synthesize them. Be concise and factual."
            )},
            {"role": "user", "content": f"Retrieved information:\n{context}\n\nQuestion: {question}"},
        ],
    )
    return resp.choices[0].message.content


@mcp.tool()
def list_memories(limit: int = 10) -> str:
    """
    Lists the most recent memories stored in the Open Brain, ordered by creation time.
    Useful for browsing what's been stored recently.
    """
    results = get_recent_memories(limit=limit)
    if not results:
        return "No memories stored yet."

    lines = []
    for r in results:
        meta = r.get("metadata") or {}
        cat = meta.get("category", "")
        summary = meta.get("summary", r["content"][:80])
        lines.append(f"- [{r['id']}] ({r['source_type']}, {cat}) {summary}")
    return "\n".join(lines)


@mcp.tool()
def edit_memory(memory_id: str, new_content: str) -> str:
    """
    Updates the content of an existing memory. The embedding is automatically
    re-generated to keep semantic search accurate.
    """
    ok = update_memory(memory_id, new_content)
    if ok:
        return f"Memory {memory_id} updated and re-embedded successfully."
    return f"Memory {memory_id} not found."


@mcp.tool()
def remove_memory(memory_id: str) -> str:
    """
    Permanently deletes a memory from the Open Brain by its ID.
    """
    ok = db_delete_memory(memory_id)
    if ok:
        return f"Memory {memory_id} deleted."
    return f"Memory {memory_id} not found."


# ---------------------------------------------------------------------------
# Document ingestion
# ---------------------------------------------------------------------------

@mcp.tool()
def ingest_document(filename: str, file_base64: str) -> str:
    """
    Ingest a document (PDF, image, Word, Excel, text) into the Open Brain.
    The file content must be provided as a base64-encoded string.
    The document is parsed, categorized, embedded, and saved as a searchable memory.
    """
    from ingest import ingest_document as do_ingest

    file_bytes = base64.b64decode(file_base64)
    result = do_ingest(filename, file_bytes)
    extracted_text = result["text"]

    if not extracted_text or extracted_text.startswith("["):
        return f"Could not extract useful text from {filename}: {extracted_text[:200]}"

    metadata = categorize_and_extract(extracted_text[:2000])
    metadata["filename"] = filename
    metadata["ingestion_method"] = result["method"]

    embedding = get_embedding(extracted_text[:8000])
    memory_id = add_memory(
        content=extracted_text,
        source_type=result["source_type"],
        embedding=embedding,
        metadata=metadata,
    )
    return (
        f"Document '{filename}' ingested successfully.\n"
        f"Memory ID: {memory_id}\n"
        f"Category: {metadata.get('category')}\n"
        f"Summary: {metadata.get('summary', '')[:200]}"
    )


# ---------------------------------------------------------------------------
# URL ingestion
# ---------------------------------------------------------------------------

@mcp.tool()
def ingest_url(url: str, user_note: str = "") -> str:
    """
    Fetch content from a URL (web page, X/Twitter post, YouTube video, etc.)
    and store it as a searchable memory in the Open Brain.
    Optionally add a user_note for extra context.
    """
    from url_extract import extract_url_content

    result = extract_url_content(url)
    if result.get("error") and not result.get("content"):
        return f"Could not extract content from {url}: {result['error']}"

    # Build memory content
    parts = []
    platform = result.get("platform", "web")
    title = result.get("title", "")
    author = result.get("author", "")
    content = result.get("content", "")

    header = f"[{platform}]"
    if title:
        header += f" {title}"
    if author:
        header += f" by {author}"
    parts.append(header)

    if user_note:
        parts.append(f"Note: {user_note}")
    parts.append(content)
    parts.append(f"Source: {url}")

    full_text = "\n".join(parts)

    metadata = categorize_and_extract(full_text[:2000])
    metadata["source_url"] = url
    metadata["platform"] = platform

    embedding = get_embedding(full_text[:8000])
    memory_id = add_memory(
        content=full_text,
        source_type=f"url_{platform}",
        embedding=embedding,
        metadata=metadata,
    )
    return (
        f"URL content ingested successfully.\n"
        f"Memory ID: {memory_id}\n"
        f"Platform: {platform}\n"
        f"Title: {title}\n"
        f"Category: {metadata.get('category')}\n"
        f"Summary: {metadata.get('summary', '')[:200]}"
    )


# ---------------------------------------------------------------------------
# Vault tools
# ---------------------------------------------------------------------------

@mcp.tool()
def save_vault_secret(key: str, value: str, description: str = "") -> str:
    """
    Saves sensitive information (API keys, passwords, SSN) into the secure Vault.
    This information is NOT stored in the general searchable memory table.
    """
    vault_id = store_secret(key, value, description)
    return f"Successfully securely stored secret '{key}' in the Vault (ID: {vault_id})."


@mcp.tool()
def get_vault_secret(key: str) -> str:
    """
    Retrieves a specific secret from the secure Vault if explicitly needed.
    """
    secret = retrieve_secret(key)
    if secret:
        return f"Secret Value: {secret['value']}\nDescription: {secret['description']}"
    return f"No secret found for key: {key}"


# ---------------------------------------------------------------------------
# Gmail tools
# ---------------------------------------------------------------------------

@mcp.tool()
def search_gmail(query: str, account_email: str = "", label: str = "", newer_than: str = "30d", limit: int = 10) -> str:
    """
    Search Gmail messages across connected Google accounts.
    Returns matching emails with sender, subject, date, and snippet.
    Use label to filter by Gmail label (e.g. 'INBOX', 'STARRED', or a custom label ID).
    Use newer_than for time range (e.g. '7d', '30d', '1y').
    If account_email is empty, uses the first connected account.
    """
    from google_svc import get_all_accounts, search_gmail as _search

    accounts = get_all_accounts()
    if not accounts:
        return "No Google accounts connected. Connect an account via the dashboard first."

    email = account_email or accounts[0]["email"]
    result = _search(email=email, query=query, label=label, newer_than=newer_than, max_results=limit)
    if "error" in result:
        return f"Gmail search error: {result['error']}"

    messages = result.get("messages", [])
    if not messages:
        return f"No emails found matching '{query}'."

    lines = []
    for m in messages:
        synced = " [in brain]" if m.get("already_synced") else ""
        lines.append(f"- [{m['date']}] From: {m['from']} — {m['subject']}{synced}\n  {m['snippet'][:120]}  (ID: {m['id']})")
    return f"Found {len(messages)} emails:\n\n" + "\n".join(lines)


@mcp.tool()
def read_gmail(message_id: str, account_email: str = "") -> str:
    """
    Read the full content of a specific Gmail message by its ID.
    Returns sender, recipient, subject, date, and body text.
    If account_email is empty, uses the first connected account.
    """
    from google_svc import get_all_accounts, preview_gmail_message

    accounts = get_all_accounts()
    if not accounts:
        return "No Google accounts connected."

    email = account_email or accounts[0]["email"]
    result = preview_gmail_message(email, message_id)
    if "error" in result:
        return f"Error reading email: {result['error']}"

    return (
        f"From: {result['from']}\n"
        f"To: {result['to']}\n"
        f"Subject: {result['subject']}\n"
        f"Date: {result['date']}\n"
        f"Images: {result.get('image_count', 0)}\n\n"
        f"{result['body']}"
    )


@mcp.tool()
def ingest_gmail(message_ids: List[str], account_email: str = "", include_images: bool = False) -> str:
    """
    Ingest one or more Gmail messages into the Open Brain by their IDs.
    Set include_images=True to run vision OCR on image attachments.
    If account_email is empty, uses the first connected account.
    """
    from google_svc import get_all_accounts, ingest_gmail_messages

    accounts = get_all_accounts()
    if not accounts:
        return "No Google accounts connected."

    email = account_email or accounts[0]["email"]
    result = ingest_gmail_messages(email, message_ids, include_images=include_images)
    if "error" in result:
        return f"Gmail ingest error: {result['error']}"

    n = len(result.get("ingested", []))
    e = len(result.get("errors", []))
    return f"Ingested {n} email(s){f', {e} error(s)' if e else ''} into the Open Brain."


# ---------------------------------------------------------------------------
# Calendar tools
# ---------------------------------------------------------------------------

@mcp.tool()
def search_calendar(query: str = "", account_email: str = "", time_min: str = "", time_max: str = "", limit: int = 20) -> str:
    """
    Search calendar events across connected Google accounts.
    Returns upcoming and recent events with time, location, and calendar name.
    Recurring events are deduplicated and shown once with recurrence info.
    If account_email is empty, uses the first connected account.
    """
    from google_svc import get_all_accounts, scan_calendar_events

    accounts = get_all_accounts()
    if not accounts:
        return "No Google accounts connected. Connect an account via the dashboard first."

    email = account_email or accounts[0]["email"]
    result = scan_calendar_events(email=email, time_min=time_min, time_max=time_max, max_results=limit)
    if "error" in result:
        return f"Calendar error: {result['error']}"

    events = result.get("events", [])
    if query:
        q = query.lower()
        events = [e for e in events if q in e["summary"].lower() or q in e.get("location", "").lower() or q in e.get("description", "").lower()]

    if not events:
        return f"No calendar events found{f' matching {query!r}' if query else ''}."

    lines = []
    for ev in events:
        synced = " [in brain]" if ev.get("already_synced") else ""
        recurring = f" [{ev['recurrence_info']}]" if ev.get("is_recurring") and ev.get("recurrence_info") else ""
        loc = f" @ {ev['location']}" if ev.get("location") else ""
        lines.append(f"- {ev['start'][:16]} — {ev['summary']}{loc}{recurring}{synced}\n  Calendar: {ev['calendar']}  (ID: {ev['id']})")
    return f"Found {len(events)} events:\n\n" + "\n".join(lines)


@mcp.tool()
def read_calendar_event(event_id: str, account_email: str = "") -> str:
    """
    Read the full details of a specific calendar event by its ID.
    Returns time, location, attendees, description, and recurrence info.
    If account_email is empty, uses the first connected account.
    """
    from google_svc import get_all_accounts, get_credentials_for
    from google_svc.calendar import _fetch_event, _parse_event_datetime
    from googleapiclient.discovery import build

    accounts = get_all_accounts()
    if not accounts:
        return "No Google accounts connected."

    email = account_email or accounts[0]["email"]
    creds = get_credentials_for(email)
    if not creds:
        return f"Account {email} not connected."

    service = build("calendar", "v3", credentials=creds)
    ev = _fetch_event(service, event_id)
    if not ev:
        return f"Event {event_id} not found."

    start = _parse_event_datetime(ev.get("start", {}))
    end = _parse_event_datetime(ev.get("end", {}))
    summary = ev.get("summary", "(no title)")
    location = ev.get("location", "")
    description = ev.get("description", "")
    organizer = ev.get("organizer", {}).get("email", "")
    attendees = [a.get("email", "") for a in ev.get("attendees", [])]
    recurrence = ev.get("recurrence", [])

    parts = [f"Event: {summary}", f"When: {start} — {end}"]
    if location:
        parts.append(f"Where: {location}")
    if organizer:
        parts.append(f"Organizer: {organizer}")
    if attendees:
        parts.append(f"Attendees: {', '.join(attendees[:20])}")
    if recurrence:
        parts.append(f"Recurrence: {'; '.join(recurrence)}")
    if description:
        parts.append(f"\n{description}")
    return "\n".join(parts)


@mcp.tool()
def ingest_calendar_events(event_ids: List[str], account_email: str = "") -> str:
    """
    Ingest one or more calendar events into the Open Brain by their IDs.
    Events are saved as searchable memories with metadata.
    If account_email is empty, uses the first connected account.
    """
    from google_svc import get_all_accounts, ingest_calendar_events as _ingest

    accounts = get_all_accounts()
    if not accounts:
        return "No Google accounts connected."

    email = account_email or accounts[0]["email"]
    result = _ingest(email, event_ids)
    if "error" in result:
        return f"Calendar ingest error: {result['error']}"

    n = len(result.get("ingested", []))
    e = len(result.get("errors", []))
    return f"Ingested {n} calendar event(s){f', {e} error(s)' if e else ''} into the Open Brain."


@mcp.tool()
def list_google_accounts() -> str:
    """
    Lists all connected Google accounts with their email addresses.
    Useful to know which account_email to use with Gmail and Calendar tools.
    """
    from google_svc import get_all_accounts
    accounts = get_all_accounts()
    if not accounts:
        return "No Google accounts connected. Connect one via the dashboard."
    lines = [f"- {a['email']} (connected {a.get('connected_at', 'unknown')})" for a in accounts]
    return f"{len(accounts)} connected account(s):\n" + "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    transport = os.getenv("MCP_TRANSPORT", "stdio")
    if transport == "sse":
        print(f"Starting Open Brain MCP server (SSE) on port {_mcp_port}...", flush=True)
        mcp.run(transport="sse")
    else:
        # Default: stdio transport for local MCP clients (Windsurf, Claude Desktop, etc.)
        mcp.run()
