"""Test that all API endpoints are registered on the FastAPI app after refactoring."""
import pytest


# Complete list of routes that must exist (method, path)
EXPECTED_ROUTES = [
    ("DELETE", "/api/memories/{memory_id}"),
    ("GET", "/api/config"),
    ("GET", "/api/db/stats"),
    ("GET", "/api/events"),
    ("GET", "/api/google/callback"),
    ("GET", "/api/google/gmail/labels"),
    ("GET", "/api/google/photos/media-items"),
    ("GET", "/api/google/photos/poll-session"),
    ("GET", "/api/google/status"),
    ("GET", "/api/health"),
    ("GET", "/api/logs"),
    ("GET", "/api/memories/search"),
    ("GET", "/api/stt/status"),
    ("POST", "/api/backup"),
    ("POST", "/api/chat"),
    ("POST", "/api/chat/stream"),
    ("POST", "/api/config"),
    ("POST", "/api/google/calendar/ingest"),
    ("POST", "/api/google/calendar/scan"),
    ("POST", "/api/google/connect"),
    ("POST", "/api/google/credentials/upload"),
    ("POST", "/api/google/disconnect"),
    ("POST", "/api/google/drive/ingest"),
    ("POST", "/api/google/drive/search"),
    ("POST", "/api/google/gmail/ingest"),
    ("POST", "/api/google/gmail/preview"),
    ("POST", "/api/google/gmail/search"),
    ("POST", "/api/google/photos/create-session"),
    ("POST", "/api/google/photos/ingest"),
    ("POST", "/api/ingest"),
    ("POST", "/api/logs"),
    ("POST", "/api/restart"),
    ("POST", "/api/restore"),
    ("POST", "/api/stt/download-model"),
    ("POST", "/api/stt/install-groq"),
    ("POST", "/api/stt/install-whisper"),
    ("POST", "/api/whatsapp/import"),
    ("PUT", "/api/memories/{memory_id}"),
]


@pytest.fixture(scope="module")
def registered_routes():
    """Extract all (method, path) tuples from the running FastAPI app."""
    from api import app
    from fastapi.routing import APIRoute

    routes = set()
    for route in app.routes:
        if isinstance(route, APIRoute):
            for method in route.methods:
                routes.add((method, route.path))
    return routes


@pytest.mark.parametrize("method,path", EXPECTED_ROUTES)
def test_route_exists(registered_routes, method, path):
    assert (method, path) in registered_routes, (
        f"Route {method} {path} not found in app"
    )
