"""
Smart Search — Augmented question answering for Open Brain.

When a user asks a question, this module analyzes it and decides whether
to also search Google Calendar and/or Gmail (in addition to stored memories).
It uses the LLM to generate expanded search queries with "common sense"
(e.g., "dentist" → also try clinic names found in memories).
"""

import json
from typing import Optional


def _plan_searches(question: str, memory_context: str) -> dict:
    """
    Use the text LLM to decide which external sources to search
    and what queries to use (with common-sense expansion).

    Returns a dict like:
    {
        "search_calendar": true/false,
        "search_gmail": true/false,
        "calendar_queries": ["dentist", "dental", "Nánási Dent"],
        "gmail_queries": ["dentist appointment"],
        "calendar_time_min": "2024-01-01T00:00:00Z",
        "calendar_time_max": "2024-12-31T23:59:59Z",
        "gmail_newer_than": "365d",
        "reasoning": "User asks about dentist in 2024..."
    }
    """
    from llm import get_client

    text_client, text_model = get_client("text")

    system_prompt = """You are a search planning assistant for Open Brain, a personal knowledge base.
Given a user's question and some context from their stored memories, decide:
1. Should we search Google Calendar for relevant events? (true/false)
2. Should we search Gmail for relevant emails? (true/false)
3. What search queries should we use? Generate MULTIPLE queries using common sense:
   - The literal terms from the question
   - Synonyms and related terms
   - Any specific names, places, or providers you can infer from the memory context
   - For example: if asking about "dentist" and memories mention "Nánási Dent" or "Dentideal", include those as queries too
4. What time ranges to search?

IMPORTANT: Be generous with searches. If there's any chance Calendar or Gmail could help answer the question, search them.
If the question mentions dates, time periods, appointments, meetings, events, schedules → search Calendar.
If the question mentions emails, messages, correspondence, invoices, receipts → search Gmail.

Respond with ONLY a valid JSON object (no markdown, no explanation):
{
    "search_calendar": true,
    "search_gmail": false,
    "calendar_queries": ["query1", "query2", "query3"],
    "gmail_queries": [],
    "calendar_time_min": "2024-01-01T00:00:00Z",
    "calendar_time_max": "2024-12-31T23:59:59Z",
    "gmail_newer_than": "365d",
    "reasoning": "brief explanation of why"
}"""

    try:
        resp = text_client.chat.completions.create(
            model=text_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": (
                    f"User question: {question}\n\n"
                    f"Context from stored memories (use this to infer related search terms):\n"
                    f"{memory_context[:3000] if memory_context else '(no memories found)'}"
                )},
            ],
            temperature=0.1,
        )
        raw = resp.choices[0].message.content.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
            if raw.endswith("```"):
                raw = raw[:-3]
            raw = raw.strip()
        return json.loads(raw)
    except Exception as e:
        print(f"[smart_search] Search planning failed: {e}", flush=True)
        # Fallback: search everything if the question seems calendar/email related
        q_lower = question.lower()
        search_cal = any(w in q_lower for w in [
            "calendar", "appointment", "meeting", "event", "schedule",
            "when", "dentist", "doctor", "flight", "travel", "birthday",
        ])
        search_mail = any(w in q_lower for w in [
            "email", "mail", "message", "invoice", "receipt", "sent", "received",
        ])
        return {
            "search_calendar": search_cal,
            "search_gmail": search_mail,
            "calendar_queries": [question],
            "gmail_queries": [question] if search_mail else [],
            "calendar_time_min": "",
            "calendar_time_max": "",
            "gmail_newer_than": "365d",
            "reasoning": "fallback heuristic",
        }


def _search_calendar(queries: list[str], time_min: str = "", time_max: str = "",
                     email: str = "") -> list[dict]:
    """Search calendar with multiple queries and merge results."""
    try:
        from google_svc import get_all_accounts, scan_calendar_events
    except ImportError:
        return []

    accounts = get_all_accounts()
    if not accounts:
        return []

    target_email = email or accounts[0]["email"]
    all_events = {}

    for q in queries:
        try:
            result = scan_calendar_events(
                email=target_email,
                time_min=time_min,
                time_max=time_max,
                max_results=100,
            )
            if "error" in result:
                continue
            for ev in result.get("events", []):
                # Filter by query terms
                q_lower = q.lower()
                searchable = f"{ev['summary']} {ev.get('description', '')} {ev.get('location', '')}".lower()
                if q_lower in searchable:
                    all_events[ev["id"]] = ev
        except Exception:
            continue

    return list(all_events.values())


def _search_gmail(queries: list[str], newer_than: str = "365d",
                  email: str = "") -> list[dict]:
    """Search Gmail with multiple queries and merge results."""
    try:
        from google_svc import get_all_accounts, search_gmail
    except ImportError:
        return []

    accounts = get_all_accounts()
    if not accounts:
        return []

    target_email = email or accounts[0]["email"]
    all_messages = {}

    for q in queries:
        try:
            result = search_gmail(
                email=target_email,
                query=q,
                newer_than=newer_than,
                max_results=10,
            )
            if "error" in result:
                continue
            for msg in result.get("messages", []):
                all_messages[msg["id"]] = msg
        except Exception:
            continue

    return list(all_messages.values())


def augmented_search(question: str, memory_results: list[dict],
                     account_email: str = "",
                     on_step: Optional[callable] = None) -> dict:
    """
    Given a question and initial memory search results, intelligently
    search Calendar and Gmail if relevant, and return combined context.

    on_step: optional callback(step_text: str) called as each thinking step happens.

    Returns:
    {
        "memory_context": "...",
        "calendar_context": "...",
        "gmail_context": "...",
        "combined_context": "...",
        "sources": [...],
        "search_plan": {...},
    }
    """
    def _emit(text: str):
        if on_step:
            on_step(text)

    # Build memory context string
    memory_context = "\n\n".join(
        f"- [{r['source_type']} · {r['created_at']}] {r['content']}"
        for r in memory_results
    ) if memory_results else ""

    _emit(f"Searched stored memories — found {len(memory_results)} relevant results")

    # Plan the searches
    _emit("Analyzing question to plan searches...")
    plan = _plan_searches(question, memory_context)
    print(f"[smart_search] Plan: calendar={plan.get('search_calendar')}, "
          f"gmail={plan.get('search_gmail')}, "
          f"cal_queries={plan.get('calendar_queries')}, "
          f"gmail_queries={plan.get('gmail_queries')}, "
          f"reason={plan.get('reasoning', '')}", flush=True)

    if plan.get("reasoning"):
        _emit(f"Search reasoning: {plan['reasoning']}")

    calendar_context = ""
    gmail_context = ""
    extra_sources = []

    # Search Calendar if planned
    if plan.get("search_calendar"):
        cal_queries = plan.get("calendar_queries", [question])
        t_min = plan.get("calendar_time_min", "")[:10]
        t_max = plan.get("calendar_time_max", "")[:10]
        _emit(f"Searching Google Calendar with queries: {cal_queries}" + (f" ({t_min} → {t_max})" if t_min else ""))
        cal_events = _search_calendar(
            queries=cal_queries,
            time_min=plan.get("calendar_time_min", ""),
            time_max=plan.get("calendar_time_max", ""),
            email=account_email,
        )
        _emit(f"Found {len(cal_events)} calendar events")
        if cal_events:
            cal_lines = []
            for ev in cal_events:
                recurring = f" [{ev['recurrence_info']}]" if ev.get("is_recurring") and ev.get("recurrence_info") else ""
                loc = f" at {ev['location']}" if ev.get("location") else ""
                desc = f" — {ev['description'][:200]}" if ev.get("description") else ""
                cal_lines.append(
                    f"- Calendar event: \"{ev['summary']}\"{loc}{recurring} "
                    f"on {ev['start'][:16]} (calendar: {ev['calendar']}){desc}"
                )
                extra_sources.append({
                    "id": ev["id"],
                    "source_type": "google_calendar_live",
                    "summary": f"Calendar event: {ev['summary']} on {ev['start'][:16]}",
                })
            calendar_context = "\n".join(cal_lines)

    # Search Gmail if planned
    if plan.get("search_gmail"):
        gmail_queries = plan.get("gmail_queries", [question])
        _emit(f"Searching Gmail with queries: {gmail_queries}")
        gmail_msgs = _search_gmail(
            queries=gmail_queries,
            newer_than=plan.get("gmail_newer_than", "365d"),
            email=account_email,
        )
        _emit(f"Found {len(gmail_msgs)} emails")
        if gmail_msgs:
            mail_lines = []
            for m in gmail_msgs:
                mail_lines.append(
                    f"- Email from {m['from']} — \"{m['subject']}\" ({m['date']}): {m['snippet'][:150]}"
                )
                extra_sources.append({
                    "id": m["id"],
                    "source_type": "gmail_live",
                    "summary": f"Email: {m['subject']} from {m['from']}",
                })
            gmail_context = "\n".join(mail_lines)

    # Combine all context
    n_mem = len(memory_results)
    n_ext = len(extra_sources)
    _emit(f"Combining {n_mem} memories + {n_ext} live sources → sending to reasoning model")
    parts = []
    if memory_context:
        parts.append(f"STORED MEMORIES:\n{memory_context}")
    if calendar_context:
        parts.append(f"GOOGLE CALENDAR EVENTS (live search):\n{calendar_context}")
    if gmail_context:
        parts.append(f"GMAIL MESSAGES (live search):\n{gmail_context}")

    combined = "\n\n".join(parts) if parts else ""

    memory_sources = [
        {
            "id": r["id"],
            "source_type": r["source_type"],
            "summary": (r.get("metadata") or {}).get("summary", r["content"][:80]),
        }
        for r in memory_results
    ] if memory_results else []

    return {
        "memory_context": memory_context,
        "calendar_context": calendar_context,
        "gmail_context": gmail_context,
        "combined_context": combined,
        "sources": memory_sources + extra_sources,
        "search_plan": plan,
    }
