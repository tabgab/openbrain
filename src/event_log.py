"""
Shared event logging — used by api.py and all route modules.
Extracted to break the circular import between api.py ↔ routes/*.
"""

# In-memory event log for the UI
event_log: list = []


def add_event(level: str, source: str, message: str):
    """Appends a system event to the in-memory log (last 100 events)."""
    import datetime
    event_log.append({
        "level": level,  # "info", "error", "warning", "success"
        "source": source,
        "message": message,
        "timestamp": datetime.datetime.now().isoformat()
    })
    if len(event_log) > 100:
        event_log.pop(0)
