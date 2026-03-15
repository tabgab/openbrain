from mcp.server.fastmcp import FastMCP
from typing import Optional, List, Dict, Any
from db import (
    add_memory, query_memories, get_recent_memories,
    update_memory, delete_memory as db_delete_memory,
    store_secret, retrieve_secret,
)
from llm import get_embedding, categorize_and_extract, get_client
from scrubber import scrub_text
import sys
import os
import json
import base64
import tempfile

# Create the MCP server named "Open Brain"
_mcp_port = int(os.getenv("MCP_PORT", "3100"))
mcp = FastMCP("Open Brain", host="0.0.0.0", port=_mcp_port)


# ---------------------------------------------------------------------------
# Memory tools
# ---------------------------------------------------------------------------

@mcp.tool()
def save_memory(content: str, source_type: str = "mcp_client", metadata: Optional[Dict[str, Any]] = None) -> str:
    """
    Saves a new memory or fact about the user into the Open Brain.
    Use this to persist important information, facts, or context you learn about the user.
    The content is automatically categorized, embedded for semantic search, and scrubbed for PII.
    """
    if metadata is None:
        metadata = {}

    content = scrub_text(content)
    extracted_data = categorize_and_extract(content)
    metadata.update(extracted_data)
    embedding = get_embedding(content)

    memory_id = add_memory(
        content=content,
        source_type=source_type,
        embedding=embedding,
        metadata=metadata
    )
    return f"Successfully saved memory (Category: {extracted_data.get('category')}) with ID: {memory_id}"


@mcp.tool()
def search_brain(query_concept: str, limit: int = 5) -> str:
    """
    Searches the Open Brain for relevant memories using semantic similarity.
    Use this to find information the user has previously stored — notes, invoices,
    ideas, tasks, documents, etc. Returns the most relevant matches.
    """
    embedding = get_embedding(query_concept)
    results = query_memories(embedding=embedding, limit=limit)

    if not results:
        return "No relevant memories found in the Open Brain."

    formatted_results = []
    for r in results:
        formatted_results.append(
            f"[{r['created_at']}] From {r['source_type']} (ID: {r['id']}):\n"
            f"{r['content']}\n(Meta: {json.dumps(r['metadata'])})"
        )
    return "\n\n---\n\n".join(formatted_results)


@mcp.tool()
def ask_brain(question: str) -> str:
    """
    Ask a question and get an AI-generated answer based on the user's stored memories.
    This performs semantic search, retrieves the most relevant context, and uses a
    reasoning model to synthesize an answer. Use this for complex queries.
    """
    embedding = get_embedding(question)
    results = query_memories(embedding=embedding, limit=5)

    if not results:
        return "No relevant memories found to answer this question."

    context = "\n\n".join(
        f"- [{r['source_type']} · {r['created_at']}] {r['content']}" for r in results
    )

    reasoning_client, reasoning_model = get_client("reasoning")
    resp = reasoning_client.chat.completions.create(
        model=reasoning_model,
        messages=[
            {"role": "system", "content": (
                "You are the Open Brain assistant. Answer the user's question based ONLY on "
                "the memories retrieved below. If the memories don't contain enough information, "
                "say so honestly. Be concise and factual."
            )},
            {"role": "user", "content": f"Memories:\n{context}\n\nQuestion: {question}"},
        ],
    )
    return resp.choices[0].message.content


@mcp.tool()
def list_memories(limit: int = 10) -> str:
    """
    Lists the most recent memories stored in the Open Brain, ordered by creation time.
    Useful for browsing what's been stored recently.
    """
    results = get_recent_memories(limit=limit)
    if not results:
        return "No memories stored yet."

    lines = []
    for r in results:
        meta = r.get("metadata") or {}
        cat = meta.get("category", "")
        summary = meta.get("summary", r["content"][:80])
        lines.append(f"- [{r['id']}] ({r['source_type']}, {cat}) {summary}")
    return "\n".join(lines)


@mcp.tool()
def edit_memory(memory_id: str, new_content: str) -> str:
    """
    Updates the content of an existing memory. The embedding is automatically
    re-generated to keep semantic search accurate.
    """
    ok = update_memory(memory_id, new_content)
    if ok:
        return f"Memory {memory_id} updated and re-embedded successfully."
    return f"Memory {memory_id} not found."


@mcp.tool()
def remove_memory(memory_id: str) -> str:
    """
    Permanently deletes a memory from the Open Brain by its ID.
    """
    ok = db_delete_memory(memory_id)
    if ok:
        return f"Memory {memory_id} deleted."
    return f"Memory {memory_id} not found."


# ---------------------------------------------------------------------------
# Document ingestion
# ---------------------------------------------------------------------------

@mcp.tool()
def ingest_document(filename: str, file_base64: str) -> str:
    """
    Ingest a document (PDF, image, Word, Excel, text) into the Open Brain.
    The file content must be provided as a base64-encoded string.
    The document is parsed, categorized, embedded, and saved as a searchable memory.
    """
    from ingest import ingest_document as do_ingest

    file_bytes = base64.b64decode(file_base64)
    result = do_ingest(filename, file_bytes)
    extracted_text = result["text"]

    if not extracted_text or extracted_text.startswith("["):
        return f"Could not extract useful text from {filename}: {extracted_text[:200]}"

    metadata = categorize_and_extract(extracted_text[:2000])
    metadata["filename"] = filename
    metadata["ingestion_method"] = result["method"]

    embedding = get_embedding(extracted_text[:8000])
    memory_id = add_memory(
        content=extracted_text,
        source_type=result["source_type"],
        embedding=embedding,
        metadata=metadata,
    )
    return (
        f"Document '{filename}' ingested successfully.\n"
        f"Memory ID: {memory_id}\n"
        f"Category: {metadata.get('category')}\n"
        f"Summary: {metadata.get('summary', '')[:200]}"
    )


# ---------------------------------------------------------------------------
# Vault tools
# ---------------------------------------------------------------------------

@mcp.tool()
def save_vault_secret(key: str, value: str, description: str = "") -> str:
    """
    Saves sensitive information (API keys, passwords, SSN) into the secure Vault.
    This information is NOT stored in the general searchable memory table.
    """
    vault_id = store_secret(key, value, description)
    return f"Successfully securely stored secret '{key}' in the Vault (ID: {vault_id})."


@mcp.tool()
def get_vault_secret(key: str) -> str:
    """
    Retrieves a specific secret from the secure Vault if explicitly needed.
    """
    secret = retrieve_secret(key)
    if secret:
        return f"Secret Value: {secret['value']}\nDescription: {secret['description']}"
    return f"No secret found for key: {key}"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    transport = os.getenv("MCP_TRANSPORT", "stdio")
    if transport == "sse":
        print(f"Starting Open Brain MCP server (SSE) on port {_mcp_port}...", flush=True)
        mcp.run(transport="sse")
    else:
        # Default: stdio transport for local MCP clients (Windsurf, Claude Desktop, etc.)
        mcp.run()
