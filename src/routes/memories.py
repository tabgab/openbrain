"""Memory CRUD and document ingestion endpoints."""
from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel

from api import add_event

router = APIRouter()


@router.get("/api/events")
def get_recent_events():
    """Returns the last 10 memories saved to the DB."""
    try:
        from db import get_recent_memories
        results = get_recent_memories(limit=10)
        return {"memories": results}
    except Exception as e:
        return {"memories": [], "error": str(e)}


@router.get("/api/memories/search")
def search_memories_endpoint(q: str = "", limit: int = 20):
    """Search memories by text content or metadata."""
    if not q.strip():
        return {"memories": []}
    try:
        from db import search_memories
        results = search_memories(query=q.strip(), limit=limit)
        return {"memories": results}
    except Exception as e:
        return {"memories": [], "error": str(e)}


class MemoryUpdate(BaseModel):
    content: str


@router.put("/api/memories/{memory_id}")
def update_memory_endpoint(memory_id: str, payload: MemoryUpdate):
    """Update a memory's content."""
    try:
        from db import update_memory
        ok = update_memory(memory_id=memory_id, content=payload.content)
        if not ok:
            raise HTTPException(status_code=404, detail="Memory not found")
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/api/memories/{memory_id}")
def delete_memory_endpoint(memory_id: str):
    """Delete a memory by ID."""
    try:
        from db import delete_memory
        ok = delete_memory(memory_id=memory_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Memory not found")
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/ingest")
async def ingest_document_endpoint(file: UploadFile = File(...)):
    """Upload and ingest a document (PDF, image, Word, Excel, etc.)."""
    try:
        file_bytes = await file.read()
        filename = file.filename or "unknown"

        add_event("info", "ingest", f"Ingesting document: {filename} ({len(file_bytes)} bytes)")

        from ingest import ingest_document
        result = ingest_document(filename, file_bytes)

        extracted_text = result["text"]
        if not extracted_text or extracted_text.startswith("["):
            add_event("warning", "ingest", f"Limited extraction from {filename}: {extracted_text[:100]}")
            return {"success": False, "error": extracted_text, "filename": filename}

        # Categorize the extracted text
        from llm import categorize_and_extract, get_embedding
        metadata = categorize_and_extract(extracted_text[:2000])
        metadata["filename"] = filename
        metadata["ingestion_method"] = result["method"]

        # Generate embedding and save to DB
        embedding = get_embedding(extracted_text[:8000])
        from db import add_memory
        memory_id = add_memory(
            content=extracted_text,
            source_type=result["source_type"],
            embedding=embedding,
            metadata=metadata,
        )

        add_event("success", "ingest", f"Document '{filename}' ingested as memory {memory_id} (category: {metadata.get('category')})")
        return {
            "success": True,
            "memory_id": memory_id,
            "filename": filename,
            "method": result["method"],
            "category": metadata.get("category"),
            "summary": metadata.get("summary"),
            "content_length": len(extracted_text),
        }
    except Exception as e:
        add_event("error", "ingest", f"Ingestion failed for {file.filename}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
