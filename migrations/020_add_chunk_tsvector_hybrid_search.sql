-- Migration: Add ts_vector to semantic.chunks and create hybrid search function
-- Description: Enables hybrid search combining semantic similarity with keyword matching
--              using PostgreSQL full-text search. Implements Reciprocal Rank Fusion (RRF)
--              to combine results from both search strategies.
-- Author: BMLibrarian
-- Date: 2025-11-26

-- ============================================================================
-- Phase 1: Add ts_vector column to semantic.chunks
-- ============================================================================

-- Add ts_vector column for full-text search
ALTER TABLE semantic.chunks
ADD COLUMN IF NOT EXISTS ts_vector tsvector;

-- Create GIN index for fast full-text search
CREATE INDEX IF NOT EXISTS idx_semantic_chunks_ts_vector
ON semantic.chunks USING GIN(ts_vector);

COMMENT ON COLUMN semantic.chunks.ts_vector IS
'Full-text search vector for keyword-based search. Populated by trigger on insert/update.
Used in hybrid search to complement semantic vector similarity.';

-- ============================================================================
-- Phase 2: Create trigger to auto-populate ts_vector
-- ============================================================================

-- Trigger function to generate ts_vector from chunk text
-- Note: We need to extract text from document.full_text using start_pos/end_pos
CREATE OR REPLACE FUNCTION semantic.chunks_ts_vector_trigger()
RETURNS TRIGGER AS $$
DECLARE
    chunk_text TEXT;
    text_config REGCONFIG;
BEGIN
    -- Get text configuration (defaults to 'english', can be made configurable)
    text_config := COALESCE(
        current_setting('bmlibrarian.text_config', true)::REGCONFIG,
        'english'::REGCONFIG
    );

    -- Extract chunk text from document
    SELECT substr(d.full_text, NEW.start_pos + 1, NEW.end_pos - NEW.start_pos + 1)
    INTO chunk_text
    FROM public.document d
    WHERE d.id = NEW.document_id;

    -- Generate ts_vector from chunk text
    IF chunk_text IS NOT NULL AND chunk_text != '' THEN
        NEW.ts_vector := to_tsvector(text_config, chunk_text);
    ELSE
        NEW.ts_vector := NULL;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION semantic.chunks_ts_vector_trigger() IS
'Trigger function to auto-generate ts_vector from chunk text on insert/update.
Text is extracted from document.full_text using the chunk position references.
Uses bmlibrarian.text_config setting if set, defaults to ''english''.';

-- Create the trigger
DROP TRIGGER IF EXISTS trg_chunks_ts_vector ON semantic.chunks;

CREATE TRIGGER trg_chunks_ts_vector
BEFORE INSERT OR UPDATE OF start_pos, end_pos ON semantic.chunks
FOR EACH ROW
EXECUTE FUNCTION semantic.chunks_ts_vector_trigger();

-- ============================================================================
-- Phase 3: Populate ts_vector for existing chunks
-- ============================================================================

-- Update existing chunks with ts_vector
-- This extracts text from document.full_text and generates ts_vector
UPDATE semantic.chunks c
SET ts_vector = to_tsvector(
    'english',
    substr(d.full_text, c.start_pos + 1, c.end_pos - c.start_pos + 1)
)
FROM public.document d
WHERE c.document_id = d.id
  AND d.full_text IS NOT NULL
  AND c.ts_vector IS NULL;

-- ============================================================================
-- Phase 4: Create hybrid search function with Reciprocal Rank Fusion
-- ============================================================================

DROP FUNCTION IF EXISTS semantic.hybrid_chunksearch_document(INTEGER, TEXT, FLOAT, INTEGER, FLOAT, INTEGER);

CREATE OR REPLACE FUNCTION semantic.hybrid_chunksearch_document(
    p_document_id INTEGER,
    p_query_text TEXT,
    p_semantic_threshold FLOAT DEFAULT 0.3,
    p_max_results INTEGER DEFAULT 10,
    p_semantic_weight FLOAT DEFAULT 0.6,
    p_rrf_k INTEGER DEFAULT 60
)
RETURNS TABLE (
    chunk_id INTEGER,
    chunk_no INTEGER,
    score FLOAT,
    chunk_text TEXT,
    semantic_score FLOAT,
    keyword_score FLOAT,
    match_source TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    query_embedding vector(1024);
    ts_query tsquery;
    text_config REGCONFIG;
BEGIN
    -- Validate inputs
    IF p_document_id IS NULL THEN
        RAISE EXCEPTION 'document_id cannot be null';
    END IF;

    IF p_query_text IS NULL OR p_query_text = '' THEN
        RAISE EXCEPTION 'query_text cannot be null or empty';
    END IF;

    IF p_semantic_threshold < 0.0 OR p_semantic_threshold > 1.0 THEN
        RAISE EXCEPTION 'semantic_threshold must be between 0.0 and 1.0';
    END IF;

    IF p_semantic_weight < 0.0 OR p_semantic_weight > 1.0 THEN
        RAISE EXCEPTION 'semantic_weight must be between 0.0 and 1.0';
    END IF;

    IF p_max_results < 1 THEN
        RAISE EXCEPTION 'max_results must be at least 1';
    END IF;

    -- Get text configuration
    text_config := COALESCE(
        current_setting('bmlibrarian.text_config', true)::REGCONFIG,
        'english'::REGCONFIG
    );

    -- Generate embedding for semantic search
    query_embedding := ollama_embedding(p_query_text);

    IF query_embedding IS NULL THEN
        RAISE EXCEPTION 'Failed to generate embedding for query text';
    END IF;

    -- Generate tsquery for keyword search
    -- Use websearch_to_tsquery for natural language queries
    ts_query := websearch_to_tsquery(text_config, p_query_text);

    -- Perform hybrid search with Reciprocal Rank Fusion (RRF)
    RETURN QUERY
    WITH
    -- Semantic search results with ranking
    semantic_results AS (
        SELECT
            c.id AS chunk_id,
            c.chunk_no,
            (1 - (c.embedding <=> query_embedding))::FLOAT AS sem_score,
            ROW_NUMBER() OVER (ORDER BY c.embedding <=> query_embedding) AS sem_rank
        FROM semantic.chunks c
        WHERE c.document_id = p_document_id
          AND (1 - (c.embedding <=> query_embedding)) >= p_semantic_threshold
        ORDER BY c.embedding <=> query_embedding
        LIMIT p_max_results * 3  -- Get extra for fusion
    ),
    -- Keyword search results with ranking
    keyword_results AS (
        SELECT
            c.id AS chunk_id,
            c.chunk_no,
            ts_rank_cd(c.ts_vector, ts_query)::FLOAT AS kw_score,
            ROW_NUMBER() OVER (ORDER BY ts_rank_cd(c.ts_vector, ts_query) DESC) AS kw_rank
        FROM semantic.chunks c
        WHERE c.document_id = p_document_id
          AND c.ts_vector IS NOT NULL
          AND c.ts_vector @@ ts_query
        ORDER BY ts_rank_cd(c.ts_vector, ts_query) DESC
        LIMIT p_max_results * 3  -- Get extra for fusion
    ),
    -- Combine results using Reciprocal Rank Fusion
    -- RRF formula: score = 1/(k + rank)
    -- Combined score = semantic_weight * RRF_semantic + (1 - semantic_weight) * RRF_keyword
    combined AS (
        SELECT
            COALESCE(s.chunk_id, k.chunk_id) AS chunk_id,
            COALESCE(s.chunk_no, k.chunk_no) AS chunk_no,
            COALESCE(s.sem_score, 0.0) AS semantic_score,
            COALESCE(k.kw_score, 0.0) AS keyword_score,
            -- RRF combined score
            (
                CASE WHEN s.sem_rank IS NOT NULL
                     THEN p_semantic_weight * (1.0 / (p_rrf_k + s.sem_rank))
                     ELSE 0.0 END
                +
                CASE WHEN k.kw_rank IS NOT NULL
                     THEN (1.0 - p_semantic_weight) * (1.0 / (p_rrf_k + k.kw_rank))
                     ELSE 0.0 END
            )::FLOAT AS combined_score,
            -- Track match source for diagnostics
            CASE
                WHEN s.chunk_id IS NOT NULL AND k.chunk_id IS NOT NULL THEN 'both'
                WHEN s.chunk_id IS NOT NULL THEN 'semantic'
                ELSE 'keyword'
            END AS source
        FROM semantic_results s
        FULL OUTER JOIN keyword_results k ON s.chunk_id = k.chunk_id
    )
    -- Return final results with chunk text
    SELECT
        co.chunk_id,
        co.chunk_no,
        co.combined_score AS score,
        substr(d.full_text, c.start_pos + 1, c.end_pos - c.start_pos + 1) AS chunk_text,
        co.semantic_score,
        co.keyword_score,
        co.source AS match_source
    FROM combined co
    JOIN semantic.chunks c ON co.chunk_id = c.id
    JOIN public.document d ON c.document_id = d.id
    WHERE d.withdrawn_date IS NULL
      AND d.full_text IS NOT NULL
    ORDER BY co.combined_score DESC
    LIMIT p_max_results;
END;
$$;

COMMENT ON FUNCTION semantic.hybrid_chunksearch_document(INTEGER, TEXT, FLOAT, INTEGER, FLOAT, INTEGER) IS
'Hybrid search combining semantic similarity with keyword matching within a single document.

Uses Reciprocal Rank Fusion (RRF) to combine rankings from:
1. Semantic search (pgvector cosine similarity)
2. Keyword search (PostgreSQL ts_vector full-text search)

Parameters:
  - p_document_id: Document ID to search within (required)
  - p_query_text: Natural language search query
  - p_semantic_threshold: Minimum semantic similarity (0.0-1.0, default: 0.3)
  - p_max_results: Maximum results to return (default: 10)
  - p_semantic_weight: Weight for semantic vs keyword (0.0-1.0, default: 0.6)
  - p_rrf_k: RRF constant k (default: 60, lower = more weight on top ranks)

Returns: Table with chunk_id, chunk_no, combined score, chunk_text,
         individual scores, and match source (semantic/keyword/both)

Technical Details:
  - RRF formula: score = 1/(k + rank)
  - Semantic search uses pgvector HNSW index
  - Keyword search uses GIN index on ts_vector
  - websearch_to_tsquery handles natural language queries
  - Lower p_semantic_threshold than pure semantic search (0.3 vs 0.5)
    because keyword matches can boost otherwise low-scoring chunks

Example Usage:
  -- Basic hybrid search
  SELECT * FROM semantic.hybrid_chunksearch_document(12345, ''heart rate during exercise'');

  -- More weight on keyword matching (for factual lookups)
  SELECT * FROM semantic.hybrid_chunksearch_document(
    12345,
    ''89 beats per minute'',
    0.2,   -- lower threshold
    10,
    0.4    -- more keyword weight
  );';

-- ============================================================================
-- Phase 5: Grant permissions
-- ============================================================================

GRANT EXECUTE ON FUNCTION semantic.chunks_ts_vector_trigger() TO rwbadmin;
GRANT EXECUTE ON FUNCTION semantic.chunks_ts_vector_trigger() TO hherb;
GRANT EXECUTE ON FUNCTION semantic.chunks_ts_vector_trigger() TO postgres;

GRANT EXECUTE ON FUNCTION semantic.hybrid_chunksearch_document(INTEGER, TEXT, FLOAT, INTEGER, FLOAT, INTEGER) TO rwbadmin;
GRANT EXECUTE ON FUNCTION semantic.hybrid_chunksearch_document(INTEGER, TEXT, FLOAT, INTEGER, FLOAT, INTEGER) TO hherb;
GRANT EXECUTE ON FUNCTION semantic.hybrid_chunksearch_document(INTEGER, TEXT, FLOAT, INTEGER, FLOAT, INTEGER) TO postgres;
