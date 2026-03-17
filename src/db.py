import os
import getpass
import psycopg2
from pgvector.psycopg2 import register_vector
from dotenv import load_dotenv
import uuid

load_dotenv()

DB_USER = os.getenv("POSTGRES_USER", "openbrain").strip("'\"")
DB_PASS = os.getenv("POSTGRES_PASSWORD", "openbrain_secret_pass").strip("'\"")
DB_NAME = os.getenv("POSTGRES_DB", "openbrain_db").strip("'\"")
DB_HOST = os.getenv("POSTGRES_HOST", "localhost").strip("'\"")
DB_PORT = os.getenv("POSTGRES_PORT", "5432").strip("'\"")

def get_connection():
    conn = psycopg2.connect(
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASS,
        host=DB_HOST,
        port=DB_PORT
    )
    register_vector(conn)
    return conn

def add_memory(content: str, source_type: str = "mcp_client", embedding: list[float] = None, metadata: dict = None):
    """
    Adds a new memory to the open brain.
    We assume the text has already been scrubbed for PII.
    """
    if metadata is None:
        metadata = {}
    if embedding is None:
        # Dummy embedding for testing purposes before OpenAI/OpenRouter Integration
        embedding = [0.0] * 1536 

    conn = get_connection()
    try:
        cur = conn.cursor()
        query = """
            INSERT INTO memories (content, source_type, embedding, metadata)
            VALUES (%s, %s, %s, %s)
            RETURNING id;
        """
        import json
        cur.execute(query, (content, source_type, embedding, json.dumps(metadata)))
        memory_id = cur.fetchone()[0]
        conn.commit()
        return str(memory_id)
    finally:
        conn.close()

def get_recent_memories(limit: int = 10):
    """
    Retrieves the most recent memories ordered by creation time.
    Used by the dashboard to display recent entries without requiring an embedding.
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        query = """
            SELECT id, content, source_type, created_at, metadata
            FROM memories
            ORDER BY created_at DESC
            LIMIT %s;
        """
        cur.execute(query, (limit,))
        results = []
        for row in cur.fetchall():
            results.append({
                "id": str(row[0]),
                "content": row[1],
                "source_type": row[2],
                "created_at": str(row[3]),
                "metadata": row[4]
            })
        return results
    finally:
        conn.close()

def query_memories(embedding: list[float], limit: int = 5):
    """
    Retrieves the most semantically relevant memories.
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        # Semantic search using pgvector's <=> (cosine distance) operator
        query = """
            SELECT id, content, source_type, created_at, metadata
            FROM memories
            ORDER BY embedding <=> %s
            LIMIT %s;
        """
        import numpy as np
        cur.execute(query, (np.array(embedding), limit))
        results = []
        for row in cur.fetchall():
            results.append({
                "id": str(row[0]),
                "content": row[1],
                "source_type": row[2],
                "created_at": str(row[3]),
                "metadata": row[4]
            })
        return results
    finally:
        conn.close()

def search_memories(query: str, limit: int = 20):
    """
    Full-text search across memory content and metadata.
    Uses PostgreSQL ILIKE for simple substring matching.
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        sql = """
            SELECT id, content, source_type, created_at, metadata
            FROM memories
            WHERE content ILIKE %s
               OR metadata::text ILIKE %s
            ORDER BY created_at DESC
            LIMIT %s;
        """
        pattern = f"%{query}%"
        cur.execute(sql, (pattern, pattern, limit))
        results = []
        for row in cur.fetchall():
            results.append({
                "id": str(row[0]),
                "content": row[1],
                "source_type": row[2],
                "created_at": str(row[3]),
                "metadata": row[4]
            })
        return results
    finally:
        conn.close()

def update_memory(memory_id: str, content: str):
    """Updates the content and re-generates the embedding for an existing memory."""
    from llm import get_embedding
    import numpy as np
    embedding = get_embedding(content[:8000])
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE memories SET content = %s, embedding = %s WHERE id = %s RETURNING id;",
            (content, np.array(embedding), memory_id)
        )
        row = cur.fetchone()
        conn.commit()
        return row is not None
    finally:
        conn.close()

def delete_memory(memory_id: str):
    """Deletes a memory by ID."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM memories WHERE id = %s RETURNING id;", (memory_id,))
        row = cur.fetchone()
        conn.commit()
        return row is not None
    finally:
        conn.close()

def store_secret(key: str, value: str, description: str = ""):
    """Stores a secret in the vault."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        query = """
            INSERT INTO vault (secret_key, secret_value, description)
            VALUES (%s, %s, %s)
            ON CONFLICT (secret_key) DO UPDATE
            SET secret_value = EXCLUDED.secret_value, description = EXCLUDED.description
            RETURNING id;
        """
        cur.execute(query, (key, value, description))
        vault_id = cur.fetchone()[0]
        conn.commit()
        return str(vault_id)
    except psycopg2.Error as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def search_vault(query: str):
    """Searches vault entries by keyword match on secret_key and description.
    Returns matching entries (key + description only, NOT the secret values)
    so the LLM can decide which to reveal."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        q = f"%{query.lower()}%"
        cur.execute(
            "SELECT secret_key, description FROM vault "
            "WHERE LOWER(secret_key) LIKE %s OR LOWER(description) LIKE %s "
            "ORDER BY secret_key LIMIT 20;",
            (q, q),
        )
        return [{"key": row[0], "description": row[1]} for row in cur.fetchall()]
    finally:
        conn.close()


def retrieve_secret(key: str):
    """Retrieves a secret from the vault."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        query = "SELECT secret_value, description FROM vault WHERE secret_key = %s;"
        cur.execute(query, (key,))
        row = cur.fetchone()
        if row:
            return {"value": row[0], "description": row[1]}
        return None
    finally:
        conn.close()
