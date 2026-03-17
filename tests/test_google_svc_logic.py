"""Test pure helper functions from google_svc (no network/DB needed)."""
import pytest


class TestInferRecurrence:
    """Test the _infer_recurrence helper with known date patterns."""

    def _infer(self, dates, count):
        from google_svc.calendar import _infer_recurrence
        return _infer_recurrence(dates, count)

    def test_single_occurrence(self):
        result = self._infer(["2025-03-01T10:00:00Z"], 1)
        assert result == ""  # count < 2 returns empty string

    def test_daily(self):
        dates = [f"2025-03-{d:02d}T10:00:00Z" for d in range(1, 8)]
        result = self._infer(dates, 7)
        assert "Daily" in result
        assert "7" in result

    def test_weekly(self):
        dates = ["2025-03-01T10:00:00Z", "2025-03-08T10:00:00Z",
                 "2025-03-15T10:00:00Z", "2025-03-22T10:00:00Z"]
        result = self._infer(dates, 4)
        assert "Weekly" in result

    def test_biweekly(self):
        dates = ["2025-03-01T10:00:00Z", "2025-03-15T10:00:00Z",
                 "2025-03-29T10:00:00Z"]
        result = self._infer(dates, 3)
        assert "Biweekly" in result

    def test_monthly(self):
        dates = ["2025-01-15T10:00:00Z", "2025-02-15T10:00:00Z",
                 "2025-03-15T10:00:00Z"]
        result = self._infer(dates, 3)
        assert "Monthly" in result

    def test_yearly(self):
        dates = ["2023-06-15T10:00:00Z", "2024-06-15T10:00:00Z",
                 "2025-06-15T10:00:00Z"]
        result = self._infer(dates, 3)
        assert "Yearly" in result

    def test_irregular(self):
        dates = ["2025-03-01T10:00:00Z", "2025-03-10T10:00:00Z",
                 "2025-03-25T10:00:00Z"]
        result = self._infer(dates, 3)
        assert "every ~" in result or "Repeating" in result


class TestParseEventDatetime:
    """Test _parse_event_datetime with date and datetime inputs."""

    def _parse(self, dt_obj):
        from google_svc.calendar import _parse_event_datetime
        return _parse_event_datetime(dt_obj)

    def test_date_only(self):
        result = self._parse({"date": "2025-03-15"})
        assert "2025-03-15" in result

    def test_datetime(self):
        result = self._parse({"dateTime": "2025-03-15T10:30:00+02:00"})
        assert "2025-03-15" in result

    def test_empty(self):
        result = self._parse({})
        assert result == ""
