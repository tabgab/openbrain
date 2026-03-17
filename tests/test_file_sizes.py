"""Test that no single file exceeds the 400-line threshold after refactoring."""
import os
import pytest

SRC_DIR = os.path.join(os.path.dirname(__file__), "..", "src")
MAX_LINES = 400


def _count_lines(filepath):
    with open(filepath, "r") as f:
        return sum(1 for _ in f)


def test_api_py_size():
    path = os.path.join(SRC_DIR, "api.py")
    lines = _count_lines(path)
    assert lines <= MAX_LINES, f"src/api.py is {lines} lines (max {MAX_LINES})"


@pytest.mark.parametrize("filename", [
    "auth.py", "drive.py", "gmail.py", "calendar.py", "photos.py",
])
def test_google_svc_file_sizes(filename):
    path = os.path.join(SRC_DIR, "google_svc", filename)
    assert os.path.exists(path), f"src/google_svc/{filename} does not exist"
    lines = _count_lines(path)
    assert lines <= MAX_LINES, f"src/google_svc/{filename} is {lines} lines (max {MAX_LINES})"


@pytest.mark.parametrize("filename", [
    "health.py", "memories.py", "chat.py", "config.py",
    "stt.py", "backup.py", "google.py", "whatsapp.py",
])
def test_routes_file_sizes(filename):
    path = os.path.join(SRC_DIR, "routes", filename)
    assert os.path.exists(path), f"src/routes/{filename} does not exist"
    lines = _count_lines(path)
    assert lines <= MAX_LINES, f"src/routes/{filename} is {lines} lines (max {MAX_LINES})"
