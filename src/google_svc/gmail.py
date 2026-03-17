"""
Gmail — Labels, Search, Preview, Ingest & helpers
"""
import base64
import re
import datetime

from googleapiclient.discovery import build

from google_svc.auth import get_credentials_for, _load_account, _save_account


def list_gmail_labels(email: str) -> dict:
    """Return all Gmail labels (system + custom) for the given account."""
    creds = get_credentials_for(email)
    if not creds:
        return {"error": f"Account {email} not connected."}

    service = build("gmail", "v1", credentials=creds)
    try:
        results = service.users().labels().list(userId="me").execute()
        labels = []
        for lbl in results.get("labels", []):
            labels.append({
                "id": lbl["id"],
                "name": lbl["name"],
                "type": lbl.get("type", "user"),  # "system" or "user"
            })
        # Sort: system labels first, then user labels alphabetically
        labels.sort(key=lambda l: (0 if l["type"] == "system" else 1, l["name"].lower()))
        return {"labels": labels}
    except Exception as e:
        return {"error": str(e)}


def search_gmail(email: str, query: str = "", from_filter: str = "",
                 subject_filter: str = "", label: str = "",
                 newer_than: str = "7d", max_results: int = 25) -> dict:
    """
    Search/filter Gmail messages. Returns a preview list (no ingestion).
    
    Filters:
      query          — raw Gmail search query (full Gmail syntax)
      from_filter    — filter by sender email/name
      subject_filter — filter by subject text
      label          — Gmail label ID (system like 'INBOX' or custom like 'Label_123')
      newer_than     — e.g. '1d', '7d', '30d', '1y'
      max_results    — how many to return (max 50)
    """
    creds = get_credentials_for(email)
    if not creds:
        return {"error": f"Account {email} not connected or token expired."}

    service = build("gmail", "v1", credentials=creds)

    # Build Gmail search query
    q_parts = []
    if query:
        q_parts.append(query)
    if from_filter:
        q_parts.append(f"from:{from_filter}")
    if subject_filter:
        q_parts.append(f"subject:{subject_filter}")
    if newer_than:
        q_parts.append(f"newer_than:{newer_than}")
    q_str = " ".join(q_parts) if q_parts else "newer_than:7d"

    label_ids = []
    if label:
        label_ids = [label]  # Use label ID directly (works for both system and custom)

    max_results = min(max_results, 50)

    try:
        params = {"userId": "me", "q": q_str, "maxResults": max_results}
        if label_ids:
            params["labelIds"] = label_ids
        results = service.users().messages().list(**params).execute()
    except Exception as e:
        return {"error": f"Gmail API error: {e}"}

    msg_refs = results.get("messages", [])
    acct = _load_account(email)
    synced_ids = set(acct.get("gmail_synced_ids", []))

    messages = []
    for ref in msg_refs:
        try:
            msg = service.users().messages().get(
                userId="me", id=ref["id"], format="metadata",
                metadataHeaders=["From", "Subject", "Date"],
            ).execute()
            headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
            messages.append({
                "id": ref["id"],
                "from": headers.get("from", ""),
                "subject": headers.get("subject", "(no subject)"),
                "date": headers.get("date", ""),
                "snippet": msg.get("snippet", ""),
                "already_synced": ref["id"] in synced_ids,
            })
        except Exception:
            continue

    return {"messages": messages, "total": len(messages), "query": q_str}


def ingest_gmail_messages(email: str, message_ids: list[str], include_images: bool = False) -> dict:
    """Ingest specific Gmail messages by their IDs.

    If include_images is True, image attachments are extracted and processed
    through the vision model to generate text descriptions that are appended
    to the memory content.
    """
    creds = get_credentials_for(email)
    if not creds:
        return {"error": f"Account {email} not connected."}

    from llm import categorize_and_extract, get_embedding
    from scrubber import scrub_text
    from db import add_memory

    service = build("gmail", "v1", credentials=creds)
    acct = _load_account(email)
    synced_ids = set(acct.get("gmail_synced_ids", []))

    # Lazy-import vision capability only when needed
    describe_image = None
    if include_images:
        try:
            from llm import describe_image as _desc
            describe_image = _desc
        except ImportError:
            describe_image = None

    ingested = []
    errors = []

    for msg_id in message_ids:
        try:
            msg = service.users().messages().get(
                userId="me", id=msg_id, format="full"
            ).execute()

            headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
            subject = headers.get("subject", "(no subject)")
            sender = headers.get("from", "unknown")
            date = headers.get("date", "")
            payload = msg.get("payload", {})

            body = _extract_email_body(payload)
            if not body:
                errors.append({"id": msg_id, "error": "No body text"})
                continue

            content = f"Email from: {sender}\nSubject: {subject}\nDate: {date}\n\n{body}"

            # Process image attachments through vision model
            if include_images and describe_image:
                images = _get_image_attachments(service, msg_id, payload)
                for i, img in enumerate(images, 1):
                    try:
                        desc = describe_image(img["data_b64"], img["mime"])
                        content += f"\n\n[Image {i}: {img['filename']}]\n{desc}"
                    except Exception:
                        content += f"\n\n[Image {i}: {img['filename']}] (could not process)"

            scrubbed = scrub_text(content)

            metadata = categorize_and_extract(scrubbed[:2000])
            metadata["email_from"] = sender
            metadata["email_subject"] = subject
            metadata["email_date"] = date
            metadata["gmail_id"] = msg_id
            metadata["google_account"] = email
            metadata["include_images"] = include_images

            embedding = get_embedding(scrubbed[:8000])
            memory_id = add_memory(
                content=scrubbed, source_type="gmail",
                embedding=embedding, metadata=metadata,
            )
            ingested.append({"id": msg_id, "subject": subject, "from": sender, "memory_id": memory_id})
            synced_ids.add(msg_id)

        except Exception as e:
            errors.append({"id": msg_id, "error": str(e)})

    acct["gmail_synced_ids"] = list(synced_ids)[-2000:]
    acct["gmail_last_sync"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    _save_account(email, acct)

    return {"ingested": ingested, "errors": errors}


# ---------------------------------------------------------------------------
# Gmail — Preview (read full message before ingesting)
# ---------------------------------------------------------------------------

def preview_gmail_message(email: str, message_id: str) -> dict:
    """Fetch the full body of a single Gmail message for reading, including images."""
    creds = get_credentials_for(email)
    if not creds:
        return {"error": f"Account {email} not connected."}

    service = build("gmail", "v1", credentials=creds)
    try:
        msg = service.users().messages().get(
            userId="me", id=message_id, format="full"
        ).execute()
        headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
        payload = msg.get("payload", {})
        text_body = _extract_email_body(payload)
        html_body = _extract_html_body(payload)

        # Resolve inline cid: images to data URIs
        if html_body:
            cid_map = _extract_inline_images(service, message_id, payload)
            for cid, data_uri in cid_map.items():
                html_body = html_body.replace(f"cid:{cid}", data_uri)

        # Count image attachments
        image_count = _count_image_attachments(payload)

        return {
            "id": message_id,
            "from": headers.get("from", ""),
            "to": headers.get("to", ""),
            "subject": headers.get("subject", "(no subject)"),
            "date": headers.get("date", ""),
            "body": text_body or "(no body text)",
            "html_body": html_body or "",
            "image_count": image_count,
        }
    except Exception as e:
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Gmail — HTML body & inline image helpers
# ---------------------------------------------------------------------------

def _extract_html_body(payload: dict) -> str:
    """Extract raw HTML body from Gmail message payload."""
    html_parts: list[str] = []

    def _walk(node: dict):
        mime = node.get("mimeType", "")
        body_data = node.get("body", {}).get("data")
        if mime == "text/html" and body_data:
            html_parts.append(base64.urlsafe_b64decode(body_data).decode("utf-8", errors="replace"))
        for part in node.get("parts", []):
            _walk(part)

    _walk(payload)
    return "\n".join(html_parts) if html_parts else ""


def _extract_inline_images(service, message_id: str, payload: dict) -> dict[str, str]:
    """Walk MIME tree and resolve inline images (with Content-ID) to data URIs.

    Returns a dict mapping content_id -> data:image/...;base64,... URI.
    """
    cid_map: dict[str, str] = {}

    def _walk(node: dict):
        mime = node.get("mimeType", "")
        headers = {h["name"].lower(): h["value"] for h in node.get("headers", [])}
        attachment_id = node.get("body", {}).get("attachmentId")
        content_id = headers.get("content-id", "").strip("<>")

        if mime.startswith("image/") and attachment_id and content_id:
            try:
                att = service.users().messages().attachments().get(
                    userId="me", messageId=message_id, id=attachment_id
                ).execute()
                data = att.get("data", "")
                # Gmail returns url-safe base64; convert to standard base64 for data URI
                raw = base64.urlsafe_b64decode(data)
                std_b64 = base64.b64encode(raw).decode("ascii")
                cid_map[content_id] = f"data:{mime};base64,{std_b64}"
            except Exception:
                pass

        for part in node.get("parts", []):
            _walk(part)

    _walk(payload)
    return cid_map


def _count_image_attachments(payload: dict) -> int:
    """Count all image/* parts in the MIME tree."""
    count = 0

    def _walk(node: dict):
        nonlocal count
        mime = node.get("mimeType", "")
        if mime.startswith("image/") and node.get("body", {}).get("attachmentId"):
            count += 1
        for part in node.get("parts", []):
            _walk(part)

    _walk(payload)
    return count


def _get_image_attachments(service, message_id: str, payload: dict) -> list[dict]:
    """Extract all image attachments as {mime, filename, data_b64} dicts."""
    images: list[dict] = []

    def _walk(node: dict):
        mime = node.get("mimeType", "")
        attachment_id = node.get("body", {}).get("attachmentId")
        filename = node.get("filename", "")
        if mime.startswith("image/") and attachment_id:
            try:
                att = service.users().messages().attachments().get(
                    userId="me", messageId=message_id, id=attachment_id
                ).execute()
                raw = base64.urlsafe_b64decode(att.get("data", ""))
                images.append({
                    "mime": mime,
                    "filename": filename or f"image.{mime.split('/')[-1]}",
                    "data_b64": base64.b64encode(raw).decode("ascii"),
                })
            except Exception:
                pass
        for part in node.get("parts", []):
            _walk(part)

    _walk(payload)
    return images


# ---------------------------------------------------------------------------
# Gmail body extraction
# ---------------------------------------------------------------------------

def _extract_email_body(payload: dict) -> str:
    """Recursively extract text body from Gmail message payload.

    Traverses the entire MIME tree, collecting all text/plain and text/html
    parts, then returns plain text (preferred) or HTML-stripped text.
    """
    plain_parts: list[str] = []
    html_parts: list[str] = []

    def _walk(node: dict):
        mime = node.get("mimeType", "")
        body_data = node.get("body", {}).get("data")
        parts = node.get("parts", [])

        if body_data:
            decoded = base64.urlsafe_b64decode(body_data).decode("utf-8", errors="replace")
            if mime == "text/plain":
                plain_parts.append(decoded)
            elif mime == "text/html":
                html_parts.append(decoded)

        for part in parts:
            _walk(part)

    _walk(payload)

    if plain_parts:
        return "\n".join(plain_parts)

    if html_parts:
        combined = "\n".join(html_parts)
        text = re.sub(r"<style[^>]*>.*?</style>", "", combined, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL | re.IGNORECASE)
        # Preserve image references as [image] placeholders
        text = re.sub(r'<img[^>]*alt="([^"]+)"[^>]*/?\s*>', r' [\1] ', text, flags=re.IGNORECASE)
        text = re.sub(r"<img[^>]*/?\s*>", " [image] ", text, flags=re.IGNORECASE)
        # Preserve links
        text = re.sub(r'<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>', r'\2 (\1)', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
        text = re.sub(r"</(p|div|tr|li|h[1-6])>", "\n", text, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n\s*\n+", "\n\n", text).strip()
        return text

    return ""
