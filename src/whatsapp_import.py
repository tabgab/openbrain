"""
Open Brain — WhatsApp Chat Export Importer
--------------------------------------------
Parses WhatsApp exported .txt chat files and ingests messages as memories.

WhatsApp export format (typical):
  [DD/MM/YYYY, HH:MM:SS] Sender Name: Message text
  or
  DD/MM/YYYY, HH:MM - Sender Name: Message text

Each message (or group of consecutive messages from the same sender) becomes
a separate memory with metadata (sender, timestamp, chat name).
"""

import re
import datetime
from typing import Optional

# Common WhatsApp timestamp patterns (varies by locale)
_PATTERNS = [
    # [DD/MM/YYYY, HH:MM:SS] Sender: msg
    re.compile(r"^\[(\d{1,2}/\d{1,2}/\d{2,4}),?\s+(\d{1,2}:\d{2}(?::\d{2})?)\]\s+(.+?):\s(.+)$"),
    # DD/MM/YYYY, HH:MM - Sender: msg
    re.compile(r"^(\d{1,2}/\d{1,2}/\d{2,4}),?\s+(\d{1,2}:\d{2}(?::\d{2})?)\s*[-–]\s*(.+?):\s(.+)$"),
    # MM/DD/YY, HH:MM AM/PM - Sender: msg (US format)
    re.compile(r"^(\d{1,2}/\d{1,2}/\d{2,4}),?\s+(\d{1,2}:\d{2}(?::\d{2})?\s*[APap][Mm])\s*[-–]\s*(.+?):\s(.+)$"),
]

# System messages to skip
_SYSTEM_PATTERNS = [
    "messages and calls are end-to-end encrypted",
    "created group",
    "added you",
    "changed the subject",
    "changed this group",
    "left",
    "removed",
    "changed the group description",
    "pinned a message",
    "deleted this message",
    "this message was deleted",
    "you deleted this message",
    "<media omitted>",
    "missed voice call",
    "missed video call",
    "null",
]


def parse_whatsapp_export(text: str, chat_name: str = "WhatsApp Chat") -> list[dict]:
    """
    Parse a WhatsApp .txt export into a list of message dicts.
    
    Returns list of:
      {"sender": str, "timestamp": str, "text": str, "chat_name": str}
    """
    messages = []
    current = None

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue

        parsed = _try_parse_line(line)
        if parsed:
            # Save previous message
            if current and current["text"].strip():
                messages.append(current)
            date_str, time_str, sender, msg_text = parsed
            current = {
                "sender": sender.strip(),
                "timestamp": f"{date_str} {time_str}",
                "text": msg_text.strip(),
                "chat_name": chat_name,
            }
        elif current:
            # Continuation of the previous message
            current["text"] += "\n" + line

    # Don't forget the last message
    if current and current["text"].strip():
        messages.append(current)

    # Filter out system messages
    messages = [m for m in messages if not _is_system_message(m["text"])]

    return messages


def _try_parse_line(line: str) -> Optional[tuple]:
    """Try to parse a line as a WhatsApp message. Returns (date, time, sender, text) or None."""
    for pattern in _PATTERNS:
        match = pattern.match(line)
        if match:
            return match.groups()
    return None


def _is_system_message(text: str) -> bool:
    """Check if a message is a WhatsApp system message."""
    lower = text.lower().strip()
    return any(p in lower for p in _SYSTEM_PATTERNS)


def group_messages(messages: list[dict], max_group: int = 10) -> list[dict]:
    """
    Group consecutive messages from the same sender into a single memory.
    This reduces noise and creates more meaningful memory chunks.
    
    Returns list of grouped messages with combined text.
    """
    if not messages:
        return []

    grouped = []
    current_group = {
        "sender": messages[0]["sender"],
        "timestamp_start": messages[0]["timestamp"],
        "timestamp_end": messages[0]["timestamp"],
        "texts": [messages[0]["text"]],
        "chat_name": messages[0]["chat_name"],
        "message_count": 1,
    }

    for msg in messages[1:]:
        if msg["sender"] == current_group["sender"] and current_group["message_count"] < max_group:
            current_group["texts"].append(msg["text"])
            current_group["timestamp_end"] = msg["timestamp"]
            current_group["message_count"] += 1
        else:
            grouped.append(_finalize_group(current_group))
            current_group = {
                "sender": msg["sender"],
                "timestamp_start": msg["timestamp"],
                "timestamp_end": msg["timestamp"],
                "texts": [msg["text"]],
                "chat_name": msg["chat_name"],
                "message_count": 1,
            }

    grouped.append(_finalize_group(current_group))
    return grouped


def _finalize_group(group: dict) -> dict:
    """Convert a message group into a memory-ready dict."""
    combined = "\n".join(group["texts"])
    return {
        "sender": group["sender"],
        "timestamp": group["timestamp_start"],
        "timestamp_end": group["timestamp_end"],
        "text": combined,
        "chat_name": group["chat_name"],
        "message_count": group["message_count"],
    }


def ingest_whatsapp_export(text: str, chat_name: str = "WhatsApp Chat") -> dict:
    """
    Full pipeline: parse WhatsApp export → group messages → ingest as memories.
    Returns summary of ingestion.
    """
    from llm import categorize_and_extract, get_embedding
    from scrubber import scrub_text
    from db import add_memory

    messages = parse_whatsapp_export(text, chat_name)
    if not messages:
        return {"error": "No messages found in the export. Check the file format.", "ingested": 0}

    grouped = group_messages(messages)
    ingested = 0
    errors = []

    for group in grouped:
        content = f"WhatsApp ({group['chat_name']})\nFrom: {group['sender']}\nTime: {group['timestamp']}\n\n{group['text']}"
        scrubbed = scrub_text(content)

        try:
            metadata = categorize_and_extract(scrubbed[:2000])
        except Exception:
            metadata = {"category": "communication"}

        metadata["whatsapp_chat"] = group["chat_name"]
        metadata["whatsapp_sender"] = group["sender"]
        metadata["whatsapp_timestamp"] = group["timestamp"]
        metadata["message_count"] = group["message_count"]

        try:
            embedding = get_embedding(scrubbed[:8000])
        except Exception:
            embedding = [0.0] * 1536

        try:
            add_memory(
                content=scrubbed,
                source_type="whatsapp",
                embedding=embedding,
                metadata=metadata,
            )
            ingested += 1
        except Exception as e:
            errors.append(str(e))

    return {
        "total_messages": len(messages),
        "grouped_into": len(grouped),
        "ingested": ingested,
        "errors": errors[:5] if errors else [],
        "chat_name": chat_name,
    }
