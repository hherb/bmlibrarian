-- Migration: Create Semantic Chunking Schema
-- Description: Creates semantic schema with chunks table for efficient full-text document chunking and embedding
-- Author: BMLibrarian
-- Date: 2025-11-23

-- ============================================================================
-- Create schema
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS semantic;

-- ============================================================================
-- Create chunks table
-- Stores chunk positions and embeddings, text extracted on-the-fly from document.full_text
-- ============================================================================

CREATE TABLE IF NOT EXISTS semantic.chunks (
    id SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES public.document(id) ON DELETE CASCADE,
    model_id INTEGER NOT NULL REFERENCES public.embedding_models(id),
    chunk_size INTEGER NOT NULL,       -- target chunk size parameter used (characters)
    chunk_overlap INTEGER NOT NULL,    -- overlap parameter used (characters)
    chunk_no INTEGER NOT NULL,         -- sequential chunk number (0-indexed)
    start_pos INTEGER NOT NULL,        -- start position in document.full_text
    end_pos INTEGER NOT NULL,          -- end position in document.full_text (inclusive)
    embedding vector(1024) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),

    -- Ensure unique chunks per document/model/chunking parameters
    CONSTRAINT uq_semantic_chunks_document_model_params_no
        UNIQUE(document_id, model_id, chunk_size, chunk_overlap, chunk_no),

    -- Validate positions
    CONSTRAINT chk_semantic_chunks_positions
        CHECK (start_pos >= 0 AND end_pos >= start_pos),

    -- Validate chunk parameters
    CONSTRAINT chk_semantic_chunks_params
        CHECK (chunk_size > 0 AND chunk_overlap >= 0 AND chunk_overlap < chunk_size)
);

-- Add table comment
COMMENT ON TABLE semantic.chunks IS
'Stores document chunk embeddings with position references to document.full_text.
Chunk text is extracted on-the-fly using substr(full_text, start_pos, end_pos - start_pos + 1).
This design avoids redundant text storage across 40M+ documents.';

-- Add column comments
COMMENT ON COLUMN semantic.chunks.chunk_size IS 'Target chunk size in characters used during chunking';
COMMENT ON COLUMN semantic.chunks.chunk_overlap IS 'Overlap between consecutive chunks in characters';
COMMENT ON COLUMN semantic.chunks.chunk_no IS 'Sequential chunk number within document (0-indexed)';
COMMENT ON COLUMN semantic.chunks.start_pos IS 'Start position in document.full_text (0-indexed)';
COMMENT ON COLUMN semantic.chunks.end_pos IS 'End position in document.full_text (inclusive)';

-- ============================================================================
-- Create chunk queue table for async processing
-- ============================================================================

CREATE TABLE IF NOT EXISTS semantic.chunk_queue (
    document_id INTEGER PRIMARY KEY REFERENCES public.document(id) ON DELETE CASCADE,
    queued_at TIMESTAMP NOT NULL DEFAULT NOW(),
    priority INTEGER NOT NULL DEFAULT 0,     -- higher = process first
    attempts INTEGER NOT NULL DEFAULT 0,     -- retry counter
    last_error TEXT,                         -- error message from last failed attempt
    last_attempt_at TIMESTAMP                -- timestamp of last processing attempt
);

-- Add table comment
COMMENT ON TABLE semantic.chunk_queue IS
'Queue for async chunk processing. Documents are queued when full_text is inserted/updated.
Background worker processes queue; GUI can bypass for immediate processing.';

-- Add column comments
COMMENT ON COLUMN semantic.chunk_queue.priority IS 'Processing priority (higher = sooner). Default 0, GUI immediate = 10';
COMMENT ON COLUMN semantic.chunk_queue.attempts IS 'Number of processing attempts (for retry logic)';
COMMENT ON COLUMN semantic.chunk_queue.last_error IS 'Error message from most recent failed attempt';

-- ============================================================================
-- Create HNSW index for fast approximate nearest neighbor search
-- ============================================================================

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_semantic_chunks_embedding_hnsw
ON semantic.chunks
USING hnsw (embedding vector_cosine_ops)
WITH (
    m = 16,
    ef_construction = 80
);

-- Create supporting indexes
CREATE INDEX IF NOT EXISTS idx_semantic_chunks_document_id
ON semantic.chunks(document_id);

CREATE INDEX IF NOT EXISTS idx_semantic_chunks_model_id
ON semantic.chunks(model_id);

CREATE INDEX IF NOT EXISTS idx_semantic_chunk_queue_priority
ON semantic.chunk_queue(priority DESC, queued_at ASC);

-- ============================================================================
-- Create semantic chunksearch function
-- ============================================================================

DROP FUNCTION IF EXISTS semantic.chunksearch(TEXT, FLOAT, INTEGER);

CREATE OR REPLACE FUNCTION semantic.chunksearch(
    query_text TEXT,
    threshold FLOAT DEFAULT 0.7,
    result_limit INTEGER DEFAULT 100
)
RETURNS TABLE (
    chunk_id INTEGER,
    document_id INTEGER,
    chunk_no INTEGER,
    score FLOAT,
    chunk_text TEXT,
    title TEXT,
    doi TEXT,
    external_id TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    query_embedding vector(1024);
BEGIN
    -- Validate inputs
    IF query_text IS NULL OR query_text = '' THEN
        RAISE EXCEPTION 'query_text cannot be null or empty';
    END IF;

    IF threshold < 0.0 OR threshold > 1.0 THEN
        RAISE EXCEPTION 'threshold must be between 0.0 and 1.0';
    END IF;

    IF result_limit < 1 THEN
        RAISE EXCEPTION 'result_limit must be at least 1';
    END IF;

    -- Generate embedding for the search text using ollama_embedding function
    query_embedding := ollama_embedding(query_text);

    -- Handle case where embedding generation fails
    IF query_embedding IS NULL THEN
        RAISE EXCEPTION 'Failed to generate embedding for query text';
    END IF;

    -- Search for similar embeddings using cosine similarity
    -- Extract chunk text on-the-fly from document.full_text
    RETURN QUERY
    SELECT
        c.id AS chunk_id,
        c.document_id,
        c.chunk_no,
        (1 - (c.embedding <=> query_embedding))::FLOAT AS score,
        substr(d.full_text, c.start_pos + 1, c.end_pos - c.start_pos + 1) AS chunk_text,
        d.title,
        d.doi,
        d.external_id
    FROM
        semantic.chunks c
        JOIN public.document d ON c.document_id = d.id
    WHERE
        (1 - (c.embedding <=> query_embedding)) >= threshold
        AND d.withdrawn_date IS NULL
        AND d.full_text IS NOT NULL
    ORDER BY
        c.embedding <=> query_embedding
    LIMIT result_limit;
END;
$$;

-- Add function comment
COMMENT ON FUNCTION semantic.chunksearch(TEXT, FLOAT, INTEGER) IS
'Search semantic chunks by similarity to query text.

Parameters:
  - query_text: Natural language search query
  - threshold: Minimum similarity score (0.0 to 1.0, default: 0.7)
  - result_limit: Maximum number of results to return (default: 100)

Returns: Table with chunk_id, document_id, chunk_no, similarity score,
         chunk_text (extracted on-the-fly), title, doi, external_id

Technical Details:
  - Uses ollama_embedding() to generate query embeddings at runtime
  - Chunk text extracted via substr() from document.full_text
  - Cosine similarity via pgvector <=> operator
  - HNSW index for fast approximate nearest neighbor search
  - Automatically excludes withdrawn documents

Example Usage:
  SELECT * FROM semantic.chunksearch(''cardiovascular benefits of exercise'', 0.75, 20);

  -- Get unique documents with best matching chunks
  SELECT DISTINCT ON (document_id) *
  FROM semantic.chunksearch(''CRISPR gene editing'', 0.7, 50)
  ORDER BY document_id, score DESC;';

-- ============================================================================
-- Create trigger function to queue documents for chunking
-- ============================================================================

CREATE OR REPLACE FUNCTION semantic.queue_for_chunking()
RETURNS TRIGGER AS $$
BEGIN
    -- Only queue if full_text is not null and not empty
    IF NEW.full_text IS NOT NULL AND NEW.full_text != '' THEN
        INSERT INTO semantic.chunk_queue(document_id, queued_at, priority)
        VALUES (NEW.id, NOW(), 0)
        ON CONFLICT (document_id)
        DO UPDATE SET
            queued_at = NOW(),
            attempts = 0,
            last_error = NULL;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Add function comment
COMMENT ON FUNCTION semantic.queue_for_chunking() IS
'Trigger function to queue documents for async chunking when full_text is inserted/updated.
Resets attempts and error on re-queue (e.g., when full_text is updated).';

-- ============================================================================
-- Create trigger on document table
-- ============================================================================

DROP TRIGGER IF EXISTS trg_queue_chunking ON public.document;

CREATE TRIGGER trg_queue_chunking
AFTER INSERT OR UPDATE OF full_text ON public.document
FOR EACH ROW
EXECUTE FUNCTION semantic.queue_for_chunking();

-- ============================================================================
-- Create helper view for documents needing chunks
-- ============================================================================

CREATE OR REPLACE VIEW semantic.documents_needing_chunks AS
SELECT
    d.id,
    d.title,
    length(d.full_text) as full_text_length,
    q.queued_at,
    q.priority,
    q.attempts,
    q.last_error
FROM public.document d
JOIN semantic.chunk_queue q ON d.id = q.document_id
WHERE d.full_text IS NOT NULL
  AND d.full_text != ''
ORDER BY q.priority DESC, q.queued_at ASC;

COMMENT ON VIEW semantic.documents_needing_chunks IS
'View showing documents in the chunk queue awaiting processing.
Ordered by priority (descending) and queue time (ascending).';

-- ============================================================================
-- Create helper function to check if document has chunks
-- ============================================================================

CREATE OR REPLACE FUNCTION semantic.has_chunks(
    p_document_id INTEGER,
    p_model_id INTEGER DEFAULT 1,
    p_chunk_size INTEGER DEFAULT 350,
    p_chunk_overlap INTEGER DEFAULT 50
)
RETURNS BOOLEAN
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN EXISTS (
        SELECT 1 FROM semantic.chunks
        WHERE document_id = p_document_id
          AND model_id = p_model_id
          AND chunk_size = p_chunk_size
          AND chunk_overlap = p_chunk_overlap
    );
END;
$$;

COMMENT ON FUNCTION semantic.has_chunks(INTEGER, INTEGER, INTEGER, INTEGER) IS
'Check if a document already has chunks with the specified parameters.
Used to avoid re-chunking documents that have already been processed.';

-- ============================================================================
-- Create function to delete chunks for a document
-- ============================================================================

CREATE OR REPLACE FUNCTION semantic.delete_chunks(
    p_document_id INTEGER,
    p_model_id INTEGER DEFAULT NULL,
    p_chunk_size INTEGER DEFAULT NULL,
    p_chunk_overlap INTEGER DEFAULT NULL
)
RETURNS INTEGER
LANGUAGE plpgsql
AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM semantic.chunks
    WHERE document_id = p_document_id
      AND (p_model_id IS NULL OR model_id = p_model_id)
      AND (p_chunk_size IS NULL OR chunk_size = p_chunk_size)
      AND (p_chunk_overlap IS NULL OR chunk_overlap = p_chunk_overlap);

    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$;

COMMENT ON FUNCTION semantic.delete_chunks(INTEGER, INTEGER, INTEGER, INTEGER) IS
'Delete chunks for a document. If model_id, chunk_size, or chunk_overlap are NULL,
deletes all chunks matching the non-NULL parameters.
Returns the number of chunks deleted.';

-- ============================================================================
-- Grant appropriate permissions
-- ============================================================================

GRANT USAGE ON SCHEMA semantic TO rwbadmin;
GRANT USAGE ON SCHEMA semantic TO hherb;
GRANT USAGE ON SCHEMA semantic TO postgres;

GRANT ALL ON ALL TABLES IN SCHEMA semantic TO rwbadmin;
GRANT ALL ON ALL TABLES IN SCHEMA semantic TO hherb;
GRANT ALL ON ALL TABLES IN SCHEMA semantic TO postgres;

GRANT ALL ON ALL SEQUENCES IN SCHEMA semantic TO rwbadmin;
GRANT ALL ON ALL SEQUENCES IN SCHEMA semantic TO hherb;
GRANT ALL ON ALL SEQUENCES IN SCHEMA semantic TO postgres;

GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA semantic TO rwbadmin;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA semantic TO hherb;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA semantic TO postgres;
