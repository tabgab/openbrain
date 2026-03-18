"""Email import API routes — MBOX/EML import for Proton, iCloud, Tuta, etc."""
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from typing import Optional

router = APIRouter()


@router.post("/api/email-import/mbox")
async def import_mbox(
    file: UploadFile = File(...),
    source_service: str = Form("email_import"),
    chat_name: str = Form("Email Import"),
):
    """Import an MBOX file — parses all emails and ingests them as memories."""
    from mbox_import import parse_mbox, ingest_emails
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")
    emails = parse_mbox(content)
    if not emails:
        return {"ingested": 0, "total": 0, "errors": [], "message": "No emails found in file."}
    result = ingest_emails(emails, source_service=source_service, chat_name=chat_name)
    return result


@router.post("/api/email-import/eml")
async def import_eml(
    file: UploadFile = File(...),
    source_service: str = Form("email_import"),
    chat_name: str = Form("Email Import"),
):
    """Import a single EML file."""
    from mbox_import import parse_eml, ingest_emails
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")
    emails = parse_eml(content)
    if not emails:
        return {"ingested": 0, "total": 0, "errors": [], "message": "Could not parse email."}
    result = ingest_emails(emails, source_service=source_service, chat_name=chat_name)
    return result


@router.post("/api/email-import/batch-eml")
async def import_batch_eml(
    files: list[UploadFile] = File(...),
    source_service: str = Form("email_import"),
    chat_name: str = Form("Email Import"),
):
    """Import multiple EML files at once."""
    from mbox_import import parse_eml, ingest_emails
    all_emails = []
    for f in files:
        content = await f.read()
        if content:
            all_emails.extend(parse_eml(content))
    if not all_emails:
        return {"ingested": 0, "total": 0, "errors": [], "message": "No emails found."}
    result = ingest_emails(all_emails, source_service=source_service, chat_name=chat_name)
    return result
