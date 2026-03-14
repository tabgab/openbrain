CREATE EXTENSION IF NOT EXISTS vector;

-- Core memories table
CREATE TABLE IF NOT EXISTS memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    content TEXT NOT NULL,
    embedding vector(1536), -- Defaulting to 1536 dims (e.g. text-embedding-ada-002, or text-embedding-3-small)
    metadata JSONB DEFAULT '{}'::jsonb,
    source_type VARCHAR(50) NOT NULL, -- e.g., 'telegram', 'local_file', 'gmail'
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Index for vector search (HNSW is recommended for pgvector)
-- Note: Requires some data to build effectively, but defining it here works for empty tables too
CREATE INDEX IF NOT EXISTS memories_embedding_idx ON memories USING hnsw (embedding vector_cosine_ops);

-- Secure Vault for secrets and PII extracted during ingestion
CREATE TABLE IF NOT EXISTS vault (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    secret_key VARCHAR(255) UNIQUE NOT NULL, -- e.g., 'SSN', 'API_KEY_1'
    secret_value TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
