"""
Google Calendar — Scan, Deduplicate, Ingest & helpers
"""
import datetime

from googleapiclient.discovery import build

from google_svc.auth import get_credentials_for, _load_account, _save_account


def scan_calendar_events(email: str, time_min: str = "", time_max: str = "",
                         max_results: int = 500) -> dict:
    """Scan calendar events for the given account.

    Returns a deduplicated list:
      - Recurring events are collapsed into a single entry with recurrence info.
      - Already-processed event IDs are flagged.

    Args:
        time_min: ISO datetime string for range start (default: 1 year ago on
                  first scan, start of current month on subsequent scans).
        time_max: ISO datetime string for range end (default: now + 30 days).
    """
    creds = get_credentials_for(email)
    if not creds:
        return {"error": f"Account {email} not connected."}

    service = build("calendar", "v3", credentials=creds)
    acct = _load_account(email)
    synced_ids = set(acct.get("calendar_synced_ids", []))
    is_first_scan = len(synced_ids) == 0

    now = datetime.datetime.now(datetime.timezone.utc)

    # Determine scan window
    if not time_min:
        if is_first_scan:
            time_min = (now - datetime.timedelta(days=365)).isoformat()
        else:
            # Start of current month
            time_min = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
    if not time_max:
        time_max = (now + datetime.timedelta(days=30)).isoformat()

    # Fetch events from all calendars
    all_events: list[dict] = []
    try:
        cal_list = service.calendarList().list().execute()
        calendars = cal_list.get("items", [])
    except Exception as e:
        return {"error": f"Calendar API error: {e}"}

    for cal in calendars:
        cal_id = cal["id"]
        cal_name = cal.get("summary", cal_id)
        try:
            page_token = None
            while True:
                resp = service.events().list(
                    calendarId=cal_id,
                    timeMin=time_min,
                    timeMax=time_max,
                    maxResults=min(max_results, 2500),
                    singleEvents=True,
                    orderBy="startTime",
                    pageToken=page_token,
                ).execute()
                for ev in resp.get("items", []):
                    ev["_calendar_name"] = cal_name
                    ev["_calendar_id"] = cal_id
                all_events.extend(resp.get("items", []))
                page_token = resp.get("nextPageToken")
                if not page_token or len(all_events) >= max_results:
                    break
        except Exception:
            continue

    # --- Deduplicate recurring events ---
    # Group by recurringEventId; standalone events get their own group.
    groups: dict[str, list[dict]] = {}
    for ev in all_events:
        recurring_id = ev.get("recurringEventId", "")
        key = recurring_id if recurring_id else ev.get("id", "")
        groups.setdefault(key, []).append(ev)

    events_out: list[dict] = []
    for key, evs in groups.items():
        first = evs[0]
        ev_id = first.get("id", key)
        start = _parse_event_datetime(first.get("start", {}))
        end = _parse_event_datetime(first.get("end", {}))
        summary = first.get("summary", "(no title)")
        location = first.get("location", "")
        description = first.get("description", "")
        cal_name = first.get("_calendar_name", "")

        is_recurring = bool(first.get("recurringEventId")) or len(evs) > 1
        recurrence_info = ""
        occurrence_count = len(evs)

        if is_recurring and occurrence_count > 1:
            # Derive recurrence pattern from instances
            dates = sorted([_parse_event_datetime(e.get("start", {})) for e in evs])
            recurrence_info = _infer_recurrence(dates, occurrence_count)

        already_synced = ev_id in synced_ids or key in synced_ids
        # For recurring, check if the base recurring ID was synced
        if not already_synced and first.get("recurringEventId"):
            already_synced = first["recurringEventId"] in synced_ids

        events_out.append({
            "id": ev_id,
            "recurring_id": first.get("recurringEventId", ""),
            "summary": summary,
            "start": start,
            "end": end,
            "location": location,
            "description": description[:500] if description else "",
            "calendar": cal_name,
            "calendar_id": first.get("_calendar_id", ""),
            "is_recurring": is_recurring,
            "occurrence_count": occurrence_count,
            "recurrence_info": recurrence_info,
            "already_synced": already_synced,
        })

    # Sort by start time
    events_out.sort(key=lambda e: e["start"] or "")

    calendars_info = [
        {
            "id": c["id"],
            "name": c.get("summary", c["id"]),
            "color": c.get("backgroundColor", "#3b82f6"),
        }
        for c in calendars
    ]

    return {
        "events": events_out,
        "total": len(events_out),
        "is_first_scan": is_first_scan,
        "time_min": time_min,
        "time_max": time_max,
        "calendars_scanned": len(calendars),
        "calendars": calendars_info,
    }


def ingest_calendar_events(email: str, event_ids: list[str]) -> dict:
    """Ingest selected calendar events as memories."""
    creds = get_credentials_for(email)
    if not creds:
        return {"error": f"Account {email} not connected."}

    from llm import categorize_and_extract, get_embedding
    from scrubber import scrub_text
    from db import add_memory

    service = build("calendar", "v3", credentials=creds)
    acct = _load_account(email)
    synced_ids = set(acct.get("calendar_synced_ids", []))

    ingested = []
    errors = []

    for ev_id in event_ids:
        if ev_id in synced_ids:
            continue
        try:
            # Try primary calendar first, then search all
            ev = _fetch_event(service, ev_id)
            if not ev:
                errors.append({"id": ev_id, "error": "Event not found"})
                continue

            summary = ev.get("summary", "(no title)")
            start = _parse_event_datetime(ev.get("start", {}))
            end = _parse_event_datetime(ev.get("end", {}))
            location = ev.get("location", "")
            description = ev.get("description", "")
            attendees = [a.get("email", "") for a in ev.get("attendees", [])]
            organizer = ev.get("organizer", {}).get("email", "")
            is_recurring = bool(ev.get("recurringEventId"))

            # Build content text
            parts = [f"Calendar Event: {summary}"]
            parts.append(f"When: {start} — {end}")
            if location:
                parts.append(f"Where: {location}")
            if organizer:
                parts.append(f"Organizer: {organizer}")
            if attendees:
                parts.append(f"Attendees: {', '.join(attendees[:20])}")
            if is_recurring:
                # Fetch recurrence rule from the parent
                try:
                    parent_id = ev.get("recurringEventId", ev_id)
                    parent = service.events().get(
                        calendarId="primary", eventId=parent_id
                    ).execute()
                    rules = parent.get("recurrence", [])
                    if rules:
                        parts.append(f"Recurrence: {'; '.join(rules)}")
                except Exception:
                    parts.append("Recurrence: recurring event")
            if description:
                parts.append(f"\n{description}")

            content = "\n".join(parts)
            scrubbed = scrub_text(content)

            metadata = categorize_and_extract(scrubbed[:2000])
            metadata["calendar_event_id"] = ev_id
            metadata["calendar_summary"] = summary
            metadata["calendar_start"] = start
            metadata["calendar_end"] = end
            metadata["calendar_location"] = location
            metadata["google_account"] = email
            metadata["is_recurring"] = is_recurring

            embedding = get_embedding(scrubbed[:8000])
            memory_id = add_memory(
                content=scrubbed, source_type="google_calendar",
                embedding=embedding, metadata=metadata,
            )
            ingested.append({"id": ev_id, "summary": summary, "start": start, "memory_id": memory_id})

            # Mark synced — also mark the recurring parent ID so future instances
            # of the same recurring event are flagged as already synced.
            synced_ids.add(ev_id)
            if ev.get("recurringEventId"):
                synced_ids.add(ev["recurringEventId"])

        except Exception as e:
            errors.append({"id": ev_id, "error": str(e)})

    acct["calendar_synced_ids"] = list(synced_ids)[-5000:]
    acct["calendar_last_sync"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    _save_account(email, acct)

    return {"ingested": ingested, "errors": errors}


# ---------------------------------------------------------------------------
# Calendar helpers
# ---------------------------------------------------------------------------

def _parse_event_datetime(dt_obj: dict) -> str:
    """Extract a readable datetime string from a Calendar event start/end."""
    if "dateTime" in dt_obj:
        return dt_obj["dateTime"]
    if "date" in dt_obj:
        return dt_obj["date"]  # all-day event
    return ""


def _fetch_event(service, ev_id: str) -> dict | None:
    """Try to fetch an event from primary, then from all calendars."""
    try:
        return service.events().get(calendarId="primary", eventId=ev_id).execute()
    except Exception:
        pass
    # Fall back: search all calendars
    try:
        cal_list = service.calendarList().list().execute()
        for cal in cal_list.get("items", []):
            try:
                return service.events().get(calendarId=cal["id"], eventId=ev_id).execute()
            except Exception:
                continue
    except Exception:
        pass
    return None


def _infer_recurrence(dates: list[str], count: int) -> str:
    """Infer a human-readable recurrence pattern from a list of instance dates."""
    if count < 2:
        return ""
    try:
        parsed = []
        for d in dates[:10]:  # Sample first 10
            if "T" in d:
                parsed.append(datetime.datetime.fromisoformat(d.replace("Z", "+00:00")))
            else:
                parsed.append(datetime.datetime.fromisoformat(d))

        if len(parsed) < 2:
            return f"Repeating ({count} occurrences)"

        deltas = [(parsed[i + 1] - parsed[i]).days for i in range(len(parsed) - 1)]
        avg_delta = sum(deltas) / len(deltas)

        if 0.8 <= avg_delta <= 1.2:
            return f"Daily ({count} occurrences)"
        elif 6 <= avg_delta <= 8:
            return f"Weekly ({count} occurrences)"
        elif 13 <= avg_delta <= 15:
            return f"Biweekly ({count} occurrences)"
        elif 28 <= avg_delta <= 32:
            return f"Monthly ({count} occurrences)"
        elif 360 <= avg_delta <= 370:
            return f"Yearly ({count} occurrences)"
        else:
            return f"Repeating every ~{int(avg_delta)} days ({count} occurrences)"
    except Exception:
        return f"Repeating ({count} occurrences)"
