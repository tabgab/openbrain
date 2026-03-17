"""Test that the refactored module structure exists and exports the right symbols."""
import pytest


class TestGoogleSvcPackage:
    """Verify google_svc package and submodules exist with correct exports."""

    def test_google_svc_package_importable(self):
        import google_svc

    def test_google_svc_has_submodules(self):
        import google_svc
        assert hasattr(google_svc, "auth")
        assert hasattr(google_svc, "drive")
        assert hasattr(google_svc, "gmail")
        assert hasattr(google_svc, "calendar")
        assert hasattr(google_svc, "photos")

    def test_auth_exports(self):
        from google_svc.auth import (
            get_credentials_for,
            start_oauth_flow,
            complete_oauth_flow,
            list_accounts,
            get_all_accounts,
            get_status,
            disconnect,
            _CREDENTIALS_FILE,
        )

    def test_drive_exports(self):
        from google_svc.drive import search_drive, ingest_drive_files

    def test_gmail_exports(self):
        from google_svc.gmail import (
            list_gmail_labels,
            search_gmail,
            ingest_gmail_messages,
            preview_gmail_message,
        )

    def test_calendar_exports(self):
        from google_svc.calendar import scan_calendar_events, ingest_calendar_events

    def test_photos_exports(self):
        from google_svc.photos import (
            create_photos_session,
            poll_photos_session,
            list_photos_media_items,
            ingest_photos,
        )

    def test_google_svc_init_reexports(self):
        """__init__.py should re-export key public functions for convenience."""
        from google_svc import (
            get_credentials_for,
            start_oauth_flow,
            complete_oauth_flow,
            list_accounts,
            get_all_accounts,
            get_status,
            disconnect,
            search_drive,
            ingest_drive_files,
            list_gmail_labels,
            search_gmail,
            ingest_gmail_messages,
            preview_gmail_message,
            scan_calendar_events,
            ingest_calendar_events,
            create_photos_session,
            poll_photos_session,
            list_photos_media_items,
            ingest_photos,
            _CREDENTIALS_FILE,
        )


class TestRoutesPackage:
    """Verify routes package and submodules exist."""

    def test_routes_package_importable(self):
        import routes

    def test_routes_has_submodules(self):
        from routes import health
        from routes import memories
        from routes import chat
        from routes import config
        from routes import stt
        from routes import backup
        from routes import google
        from routes import whatsapp

    def test_each_route_module_has_router(self):
        """Each route module should export an APIRouter instance."""
        from fastapi import APIRouter
        from routes import health, memories, chat, config, stt, backup, google, whatsapp
        for mod in [health, memories, chat, config, stt, backup, google, whatsapp]:
            assert hasattr(mod, "router"), f"{mod.__name__} missing 'router'"
            assert isinstance(mod.router, APIRouter), f"{mod.__name__}.router is not an APIRouter"
