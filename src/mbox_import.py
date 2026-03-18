"""
MBOX / EML email import module for Open Brain.
Parses standard MBOX and EML files into individual email memories.
Used by Proton Mail, Apple iCloud Mail, Tuta, and any service that exports MBOX.
"""
import mailbox
import email
import email.policy
import io
import os
import tempfile
from typing import Optional
from datetime import datetime

from db import add_memory, query_memories
from llm import get_embedding, categorize_and_extract
from scrubber import scrub_text
from event_log import add_event


def _extract_email_text(msg: email.message.EmailMessage) -> str:
    """Extract plain text body from an email message."""
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            if ct == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    body += payload.decode(charset, errors="replace")
            elif ct == "text/html" and not body:
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    html = payload.decode(charset, errors="replace")
                    # Simple HTML to text: strip tags
                    import re
                    body += re.sub(r"<[^>]+>", " ", html)
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            body = payload.decode(charset, errors="replace")
    return body.strip()


def _parse_date(date_str: str) -> str:
    """Parse email date to ISO format, fallback to raw string."""
    if not date_str:
        return ""
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(date_str)
        return dt.isoformat()
    except Exception:
        return date_str


def parse_mbox(file_bytes: bytes) -> list[dict]:
    """
    Parse an MBOX file into a list of email dicts.
    Returns: [{"from": str, "to": str, "subject": str, "date": str, "body": str}, ...]
    """
    emails = []
    # Write to temp file because mailbox.mbox needs a file path
    with tempfile.NamedTemporaryFile(suffix=".mbox", delete=False) as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name

    try:
        mbox = mailbox.mbox(tmp_path)
        for msg in mbox:
            em = email.message_from_bytes(
                msg.as_bytes(), policy=email.policy.default
            )
            body = _extract_email_text(em)
            if not body.strip():
                continue
            emails.append({
                "from": str(em.get("From", "")),
                "to": str(em.get("To", "")),
                "subject": str(em.get("Subject", "(no subject)")),
                "date": _parse_date(str(em.get("Date", ""))),
                "body": body[:8000],  # cap at 8k chars
            })
        mbox.close()
    finally:
        os.unlink(tmp_path)

    return emails


def parse_eml(file_bytes: bytes) -> list[dict]:
    """Parse a single EML file into a list with one email dict."""
    em = email.message_from_bytes(file_bytes, policy=email.policy.default)
    body = _extract_email_text(em)
    if not body.strip():
        return []
    return [{
        "from": str(em.get("From", "")),
        "to": str(em.get("To", "")),
        "subject": str(em.get("Subject", "(no subject)")),
        "date": _parse_date(str(em.get("Date", ""))),
        "body": body[:8000],
    }]


def ingest_emails(
    emails: list[dict],
    source_service: str = "email_import",
    chat_name: str = "Email Import",
) -> dict:
    """
    Ingest parsed emails into Open Brain as memories.
    Returns: {"ingested": int, "skipped": int, "total": int, "errors": []}
    """
    ingested = 0
    skipped = 0
    errors = []

    for em in emails:
        try:
            # Build memory content
            parts = []
            if em.get("subject"):
                parts.append(f"Subject: {em['subject']}")
            if em.get("from"):
                parts.append(f"From: {em['from']}")
            if em.get("to"):
                parts.append(f"To: {em['to']}")
            if em.get("date"):
                parts.append(f"Date: {em['date']}")
            parts.append("")
            parts.append(em.get("body", ""))
            content = "\n".join(parts)

            content = scrub_text(content)
            extracted = categorize_and_extract(content)
            embedding = get_embedding(content)

            metadata = {
                **extracted,
                "email_from": em.get("from", ""),
                "email_subject": em.get("subject", ""),
                "email_date": em.get("date", ""),
                "import_source": source_service,
                "chat_name": chat_name,
            }

            add_memory(
                content=content,
                source_type=source_service,
                embedding=embedding,
                metadata=metadata,
            )
            ingested += 1
        except Exception as e:
            errors.append({
                "subject": em.get("subject", "?"),
                "error": str(e),
            })

    add_event(
        "success" if not errors else "warning",
        source_service,
        f"Imported {ingested}/{len(emails)} emails from {chat_name}",
    )

    return {
        "ingested": ingested,
        "skipped": skipped,
        "total": len(emails),
        "errors": errors,
        "source": source_service,
    }
