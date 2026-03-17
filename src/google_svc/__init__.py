"""
Google Services — OAuth, Drive, Gmail, Calendar & Photos integration.
Re-exports all public symbols for convenience.
"""
from google_svc.auth import (
    get_credentials_for,
    start_oauth_flow,
    complete_oauth_flow,
    list_accounts,
    get_all_accounts,
    get_status,
    disconnect,
    _CREDENTIALS_FILE,
    _load_account,
    _save_account,
)
from google_svc.drive import search_drive, ingest_drive_files
from google_svc.gmail import (
    list_gmail_labels,
    search_gmail,
    ingest_gmail_messages,
    preview_gmail_message,
)
from google_svc.calendar import scan_calendar_events, ingest_calendar_events
from google_svc.photos import (
    create_photos_session,
    poll_photos_session,
    list_photos_media_items,
    ingest_photos,
)
