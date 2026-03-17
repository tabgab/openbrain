"""Chat endpoints — sync and streaming SSE, with intent detection."""
import json as _json
import queue
import threading

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from event_log import add_event

router = APIRouter()


class ChatMessage(BaseModel):
    message: str
    force_mode: str = ""  # "question", "memory", or "" for auto-detect
    search_mode: str = "advanced"  # "memory_only" or "advanced"


@router.post("/api/chat")
def chat_endpoint(payload: ChatMessage):
    """Chat with Open Brain — auto-detects questions vs memories, just like the Telegram bot."""
    from llm import get_embedding, categorize_and_extract, get_client
    from db import add_memory, query_memories
    from scrubber import scrub_text

    text = payload.message.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    mode = payload.force_mode

    # Auto-detect if not forced
    if not mode:
        mode = _detect_intent(text)

    add_event("info", "chat", f"Chat ({mode}): '{text[:60]}'")

    if mode == "question":
        # Search brain and answer — with augmented Calendar/Gmail search
        try:
            embedding = get_embedding(text)
            results = query_memories(embedding=embedding, limit=5)
        except Exception as e:
            add_event("error", "chat", f"Brain search failed: {e}")
            return {"type": "answer", "content": f"Failed to search the brain: {e}", "sources": []}

        # Augmented search: also query Calendar and Gmail if relevant
        use_advanced = payload.search_mode != "memory_only"
        plan = {}
        try:
            if use_advanced:
                from smart_search import augmented_search
                search_result = augmented_search(text, results or [])
                context = search_result["combined_context"]
                sources = search_result["sources"]
                plan = search_result.get("search_plan", {})
            else:
                context = "\n\n".join(
                    f"- [{r['source_type']} · {r['created_at']}] {r['content']}" for r in results
                ) if results else ""
                sources = [{"id": r["id"], "source_type": r["source_type"], "summary": (r.get("metadata") or {}).get("summary", r["content"][:80])} for r in results] if results else []
                plan = {}
            extra_info = []
            if plan.get("search_calendar"):
                n_cal = len([s for s in sources if s["source_type"] == "google_calendar_live"])
                extra_info.append(f"calendar:{n_cal}")
            if plan.get("search_gmail"):
                n_mail = len([s for s in sources if s["source_type"] == "gmail_live"])
                extra_info.append(f"gmail:{n_mail}")
            if extra_info:
                add_event("info", "chat", f"Smart search: {', '.join(extra_info)}")
        except Exception as e:
            add_event("warning", "chat", f"Smart search fallback: {e}")
            context = "\n\n".join(
                f"- [{r['source_type']} · {r['created_at']}] {r['content']}" for r in results
            ) if results else ""
            sources = [{"id": r["id"], "source_type": r["source_type"], "summary": (r.get("metadata") or {}).get("summary", r["content"][:80])} for r in results] if results else []

        if not context:
            return {"type": "answer", "content": "No relevant memories or data found in your Open Brain.", "sources": []}

        try:
            reasoning_client, reasoning_model = get_client("reasoning")
            resp = reasoning_client.chat.completions.create(
                model=reasoning_model,
                messages=[
                    {"role": "system", "content": (
                        "You are the Open Brain assistant. Answer the user's question based on "
                        "ALL the information retrieved below — this includes stored memories AND "
                        "live data from Google Calendar and Gmail searches. "
                        "Use all available context to give the best possible answer. "
                        "If multiple sources help, synthesize them. Be concise and helpful."
                    )},
                    {"role": "user", "content": f"Retrieved information:\n{context}\n\nQuestion: {text}"},
                ],
            )
            answer = resp.choices[0].message.content
            n_mem = len([s for s in sources if s["source_type"] not in ("google_calendar_live", "gmail_live")])
            n_ext = len(sources) - n_mem
            add_event("success", "chat", f"Answered question (used {n_mem} memories + {n_ext} live sources)")

            # Build thinking steps for UI
            thinking_steps = []
            thinking_steps.append(f"Searched stored memories — found {len(results or [])} relevant results")
            if plan:
                if plan.get("reasoning"):
                    thinking_steps.append(f"Search reasoning: {plan['reasoning']}")
                if plan.get("search_calendar"):
                    cal_queries = plan.get("calendar_queries", [])
                    t_min = plan.get("calendar_time_min", "")[:10]
                    t_max = plan.get("calendar_time_max", "")[:10]
                    thinking_steps.append(f"Searched Google Calendar with queries: {cal_queries}" + (f" ({t_min} → {t_max})" if t_min else ""))
                    thinking_steps.append(f"Found {len([s for s in sources if s['source_type'] == 'google_calendar_live'])} calendar events")
                if plan.get("search_gmail"):
                    gmail_queries = plan.get("gmail_queries", [])
                    thinking_steps.append(f"Searched Gmail with queries: {gmail_queries}")
                    thinking_steps.append(f"Found {len([s for s in sources if s['source_type'] == 'gmail_live'])} emails")
            thinking_steps.append(f"Combined {n_mem} memories + {n_ext} live sources → sent to reasoning model")

            return {
                "type": "answer",
                "content": answer,
                "sources": sources,
                "thinking": thinking_steps,
            }
        except Exception as e:
            add_event("error", "chat", f"LLM answer failed: {e}")
            return {"type": "answer", "content": f"Failed to generate answer: {e}", "sources": []}

    else:
        # Store as memory
        from url_extract import enrich_text_with_urls, detect_urls
        if detect_urls(text):
            try:
                text = enrich_text_with_urls(text)
            except Exception:
                pass
        scrubbed = scrub_text(text)
        try:
            extracted = categorize_and_extract(scrubbed)
        except Exception:
            extracted = {"category": "uncategorized"}
        try:
            embedding = get_embedding(scrubbed)
        except Exception:
            embedding = [0.0] * 1536

        memory_id = add_memory(content=scrubbed, source_type="dashboard_chat", embedding=embedding, metadata=extracted)
        category = extracted.get("category", "unknown")
        summary = extracted.get("summary", "")
        add_event("success", "chat", f"Memory saved from chat — ID: {memory_id}, Category: {category}")
        return {
            "type": "memory",
            "content": f"Saved to Open Brain as **{category}**.",
            "memory_id": memory_id,
            "category": category,
            "summary": summary,
        }


@router.post("/api/chat/stream")
def chat_stream_endpoint(payload: ChatMessage):
    """Streaming chat — sends thinking steps as SSE events in real-time, then the final answer."""
    from llm import get_embedding, categorize_and_extract, get_client
    from db import add_memory, query_memories
    from scrubber import scrub_text

    text = payload.message.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    mode = payload.force_mode
    if not mode:
        mode = _detect_intent(text)

    add_event("info", "chat", f"Chat stream ({mode}): '{text[:60]}'")

    def _generate_events():
        if mode == "question":
            step_q: queue.Queue = queue.Queue()

            def on_step(step_text: str):
                step_q.put(("thinking", step_text))

            use_advanced = payload.search_mode != "memory_only"
            result_holder: dict = {}

            def _do_search():
                try:
                    embedding = get_embedding(text)
                    results = query_memories(embedding=embedding, limit=5)
                except Exception as e:
                    result_holder["error"] = str(e)
                    step_q.put(("done", None))
                    return

                if use_advanced:
                    try:
                        from smart_search import augmented_search
                        search_result = augmented_search(text, results or [], on_step=on_step)
                        result_holder["search_result"] = search_result
                        result_holder["results"] = results
                    except Exception as e:
                        on_step(f"Smart search fallback: {e}")
                        ctx = "\n\n".join(
                            f"- [{r['source_type']} · {r['created_at']}] {r['content']}" for r in results
                        ) if results else ""
                        srcs = [{"id": r["id"], "source_type": r["source_type"], "summary": (r.get("metadata") or {}).get("summary", r["content"][:80])} for r in results] if results else []
                        result_holder["search_result"] = {"combined_context": ctx, "sources": srcs, "search_plan": {}}
                        result_holder["results"] = results
                else:
                    on_step(f"Memory-only mode — searching stored memories")
                    on_step(f"Found {len(results or [])} relevant memories")
                    ctx = "\n\n".join(
                        f"- [{r['source_type']} · {r['created_at']}] {r['content']}" for r in results
                    ) if results else ""
                    srcs = [{"id": r["id"], "source_type": r["source_type"], "summary": (r.get("metadata") or {}).get("summary", r["content"][:80])} for r in results] if results else []
                    result_holder["search_result"] = {"combined_context": ctx, "sources": srcs, "search_plan": {}}
                    result_holder["results"] = results
                step_q.put(("done", None))

            t = threading.Thread(target=_do_search, daemon=True)
            t.start()

            # Yield thinking steps as they arrive
            while True:
                try:
                    evt, data = step_q.get(timeout=120)
                except Exception:
                    break
                if evt == "done":
                    break
                yield f"data: {_json.dumps({'type': 'thinking', 'step': data})}\n\n"

            if "error" in result_holder:
                err = result_holder["error"]
                yield f"data: {_json.dumps({'type': 'answer', 'content': 'Failed to search: ' + err, 'sources': []})}\n\n"
                return

            search_result = result_holder["search_result"]
            context = search_result["combined_context"]
            sources = search_result["sources"]

            if not context:
                yield f"data: {_json.dumps({'type': 'answer', 'content': 'No relevant memories or data found in your Open Brain.', 'sources': []})}\n\n"
                return

            yield f"data: {_json.dumps({'type': 'thinking', 'step': 'Generating answer with reasoning model...'})}\n\n"

            try:
                reasoning_client, reasoning_model = get_client("reasoning")
                resp = reasoning_client.chat.completions.create(
                    model=reasoning_model,
                    messages=[
                        {"role": "system", "content": (
                            "You are the Open Brain assistant. Answer the user's question based on "
                            "ALL the information retrieved below — this includes stored memories AND "
                            "live data from Google Calendar and Gmail searches. "
                            "Use all available context to give the best possible answer. "
                            "If multiple sources help, synthesize them. Be concise and helpful."
                        )},
                        {"role": "user", "content": f"Retrieved information:\n{context}\n\nQuestion: {text}"},
                    ],
                )
                answer = resp.choices[0].message.content
                add_event("success", "chat", f"Stream answered question ({len(sources)} sources)")
                yield f"data: {_json.dumps({'type': 'answer', 'content': answer, 'sources': sources})}\n\n"
            except Exception as e:
                add_event("error", "chat", f"LLM answer failed: {e}")
                yield f"data: {_json.dumps({'type': 'answer', 'content': 'Failed to generate answer: ' + str(e), 'sources': []})}\n\n"

        else:
            # Store as memory
            from url_extract import enrich_text_with_urls, detect_urls
            store_text = text
            if detect_urls(store_text):
                try:
                    store_text = enrich_text_with_urls(store_text)
                except Exception:
                    pass
            scrubbed = scrub_text(store_text)
            try:
                extracted = categorize_and_extract(scrubbed)
            except Exception:
                extracted = {"category": "uncategorized"}
            try:
                embedding = get_embedding(scrubbed)
            except Exception:
                embedding = [0.0] * 1536
            metadata = dict(extracted)
            memory_id = add_memory(content=scrubbed, source_type="dashboard_chat", embedding=embedding, metadata=metadata)
            cat = extracted.get("category", "uncategorized")
            summ = extracted.get("summary", "")
            add_event("success", "chat", f"Stream stored memory {memory_id} (category: {cat})")
            yield f"data: {_json.dumps({'type': 'memory', 'content': 'Stored as memory (Category: ' + cat + ')', 'memory_id': memory_id, 'category': cat, 'summary': summ})}\n\n"

    return StreamingResponse(_generate_events(), media_type="text/event-stream")


def _detect_intent(text: str) -> str:
    """Detect whether a message is a question or a memory. Mirrors telegram_bot.is_question logic."""
    stripped = text.strip()
    if stripped.endswith("?"):
        return "question"

    QUESTION_WORDS = {
        "who", "what", "when", "where", "why", "how",
        "do", "does", "did", "is", "are", "was", "were",
        "can", "could", "will", "would", "should", "shall",
        "have", "has", "had", "which", "whose", "whom",
        "tell", "explain", "describe", "show",
    }
    first_word = stripped.split()[0].lower().rstrip(",:;") if stripped else ""
    if first_word in QUESTION_WORDS:
        return "question"
    if first_word in {"find", "search", "look", "list", "get", "recall", "remember"}:
        return "question"

    # LLM classification for ambiguous messages
    if len(stripped.split()) >= 3:
        try:
            from llm import get_client
            text_client, text_model = get_client("text")
            resp = text_client.chat.completions.create(
                model=text_model,
                messages=[
                    {"role": "system", "content": (
                        "Classify whether this message is a QUESTION (the user wants to retrieve/query information) "
                        "or a MEMORY (the user wants to store this as a note/fact/log). "
                        "Reply with exactly one word: QUESTION or MEMORY."
                    )},
                    {"role": "user", "content": stripped},
                ],
                max_tokens=5,
            )
            answer = resp.choices[0].message.content.strip().upper()
            if "QUESTION" in answer:
                return "question"
        except Exception:
            pass

    return "memory"
