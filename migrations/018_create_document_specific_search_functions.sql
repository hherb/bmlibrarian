-- Migration: Create Document-Specific Semantic Search Functions
-- Description: Creates functions for semantic search within a single document,
--              supporting both abstract chunks (emb_1024) and full-text chunks (semantic.chunks).
--              These functions accept document_id as a parameter to filter at the index level,
--              avoiding inefficient post-filtering of full-corpus search results.
-- Author: BMLibrarian
-- Date: 2025-11-24

-- ============================================================================
-- Drop functions if they exist (idempotent migration)
-- ============================================================================

DROP FUNCTION IF EXISTS semantic_search_document(INTEGER, TEXT, FLOAT, INTEGER);
DROP FUNCTION IF EXISTS semantic.chunksearch_document(INTEGER, TEXT, FLOAT, INTEGER);

-- ============================================================================
-- Create semantic_search_document for abstract chunks (emb_1024 table)
-- ============================================================================

CREATE OR REPLACE FUNCTION semantic_search_document(
    p_document_id INTEGER,
    query_text TEXT,
    threshold FLOAT DEFAULT 0.7,
    result_limit INTEGER DEFAULT 5
)
RETURNS TABLE (
    chunk_id INTEGER,
    chunk_no INTEGER,
    score FLOAT,
    chunk_text TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    query_embedding vector(1024);
BEGIN
    -- Validate inputs
    IF p_document_id IS NULL THEN
        RAISE EXCEPTION 'document_id cannot be null';
    END IF;

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

    -- Search for similar embeddings within the specific document
    -- Filter by document_id BEFORE similarity calculation for efficiency
    RETURN QUERY
    SELECT
        e.chunk_id,
        c.chunk_no,
        (1 - (e.embedding <=> query_embedding))::FLOAT AS similarity_score,
        c.text AS chunk_text
    FROM
        emb_1024 e
        JOIN chunks c ON e.chunk_id = c.id
    WHERE
        c.document_id = p_document_id
        AND (1 - (e.embedding <=> query_embedding)) >= threshold
    ORDER BY
        e.embedding <=> query_embedding
    LIMIT result_limit;
END;
$$;

-- Add function comment
COMMENT ON FUNCTION semantic_search_document(INTEGER, TEXT, FLOAT, INTEGER) IS
'Search abstract chunks by semantic similarity within a SINGLE document.

Unlike semantic_search() which searches the entire corpus, this function
filters by document_id at the query level for efficient single-document Q&A.

Parameters:
  - p_document_id: The document ID to search within (required)
  - query_text: Natural language search query
  - threshold: Minimum similarity score (0.0 to 1.0, default: 0.7)
  - result_limit: Maximum number of results to return (default: 5)

Returns: Table with chunk_id, chunk_no, similarity score, and chunk text

Technical Details:
  - Uses ollama_embedding() to generate query embeddings at runtime
  - Searches the emb_1024 table (abstract embeddings)
  - Cosine similarity via pgvector <=> operator
  - document_id filter applied before similarity calculation

Example Usage:
  -- Find relevant abstract chunks for a question
  SELECT * FROM semantic_search_document(12345, ''cardiovascular benefits'', 0.75, 5);

  -- Use in document Q&A workflow
  SELECT chunk_text, score
  FROM semantic_search_document(12345, ''What are the main findings?'', 0.7, 3)
  ORDER BY score DESC;';


-- ============================================================================
-- Create semantic.chunksearch_document for full-text chunks
-- ============================================================================

CREATE OR REPLACE FUNCTION semantic.chunksearch_document(
    p_document_id INTEGER,
    query_text TEXT,
    threshold FLOAT DEFAULT 0.7,
    result_limit INTEGER DEFAULT 5
)
RETURNS TABLE (
    chunk_id INTEGER,
    chunk_no INTEGER,
    score FLOAT,
    chunk_text TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    query_embedding vector(1024);
BEGIN
    -- Validate inputs
    IF p_document_id IS NULL THEN
        RAISE EXCEPTION 'document_id cannot be null';
    END IF;

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

    -- Search for similar embeddings within the specific document
    -- Filter by document_id BEFORE similarity calculation for efficiency
    -- Extract chunk text on-the-fly from document.full_text using stored positions
    RETURN QUERY
    SELECT
        c.id AS chunk_id,
        c.chunk_no,
        (1 - (c.embedding <=> query_embedding))::FLOAT AS similarity_score,
        substr(d.full_text, c.start_pos + 1, c.end_pos - c.start_pos + 1) AS chunk_text
    FROM
        semantic.chunks c
        JOIN public.document d ON c.document_id = d.id
    WHERE
        c.document_id = p_document_id
        AND d.withdrawn_date IS NULL
        AND d.full_text IS NOT NULL
        AND (1 - (c.embedding <=> query_embedding)) >= threshold
    ORDER BY
        c.embedding <=> query_embedding
    LIMIT result_limit;
END;
$$;

-- Add function comment
COMMENT ON FUNCTION semantic.chunksearch_document(INTEGER, TEXT, FLOAT, INTEGER) IS
'Search full-text chunks by semantic similarity within a SINGLE document.

Unlike semantic.chunksearch() which searches the entire corpus, this function
filters by document_id at the query level for efficient single-document Q&A.

Parameters:
  - p_document_id: The document ID to search within (required)
  - query_text: Natural language search query
  - threshold: Minimum similarity score (0.0 to 1.0, default: 0.7)
  - result_limit: Maximum number of results to return (default: 5)

Returns: Table with chunk_id, chunk_no, similarity score, and chunk text

Technical Details:
  - Uses ollama_embedding() to generate query embeddings at runtime
  - Searches the semantic.chunks table (full-text embeddings)
  - Chunk text extracted on-the-fly via substr() from document.full_text
  - Cosine similarity via pgvector <=> operator
  - document_id filter applied before similarity calculation
  - Automatically excludes withdrawn documents

Example Usage:
  -- Find relevant full-text chunks for a question
  SELECT * FROM semantic.chunksearch_document(12345, ''methodology'', 0.75, 5);

  -- Use in document Q&A workflow
  SELECT chunk_text, score
  FROM semantic.chunksearch_document(12345, ''What statistical methods were used?'', 0.7, 3)
  ORDER BY score DESC;';


-- ============================================================================
-- Create helper function to check if document has abstract embeddings
-- ============================================================================

CREATE OR REPLACE FUNCTION has_abstract_embeddings(
    p_document_id INTEGER,
    p_model_id INTEGER DEFAULT 1
)
RETURNS BOOLEAN
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN EXISTS (
        SELECT 1
        FROM chunks c
        JOIN emb_1024 e ON c.id = e.chunk_id
        WHERE c.document_id = p_document_id
          AND e.model_id = p_model_id
    );
END;
$$;

COMMENT ON FUNCTION has_abstract_embeddings(INTEGER, INTEGER) IS
'Check if a document has abstract embeddings in the emb_1024 table.
Used to determine if semantic_search_document() can be used for this document.

Parameters:
  - p_document_id: The document ID to check
  - p_model_id: Embedding model ID (default: 1 = snowflake-arctic-embed2)

Returns: TRUE if embeddings exist, FALSE otherwise';


-- ============================================================================
-- Create helper function to get document full-text status
-- ============================================================================

CREATE OR REPLACE FUNCTION get_document_text_status(
    p_document_id INTEGER
)
RETURNS TABLE (
    has_abstract BOOLEAN,
    has_fulltext BOOLEAN,
    has_abstract_embeddings BOOLEAN,
    has_fulltext_chunks BOOLEAN,
    abstract_length INTEGER,
    fulltext_length INTEGER
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        d.abstract IS NOT NULL AND d.abstract != '' AS has_abstract,
        d.full_text IS NOT NULL AND d.full_text != '' AS has_fulltext,
        has_abstract_embeddings(p_document_id) AS has_abstract_embeddings,
        semantic.has_chunks(p_document_id) AS has_fulltext_chunks,
        COALESCE(length(d.abstract), 0)::INTEGER AS abstract_length,
        COALESCE(length(d.full_text), 0)::INTEGER AS fulltext_length
    FROM public.document d
    WHERE d.id = p_document_id;
END;
$$;

COMMENT ON FUNCTION get_document_text_status(INTEGER) IS
'Get the text availability status for a document.
Useful for determining which Q&A strategy to use.

Returns:
  - has_abstract: TRUE if abstract exists and is non-empty
  - has_fulltext: TRUE if full_text exists and is non-empty
  - has_abstract_embeddings: TRUE if abstract embeddings exist in emb_1024
  - has_fulltext_chunks: TRUE if full-text chunks exist in semantic.chunks
  - abstract_length: Length of abstract in characters
  - fulltext_length: Length of full_text in characters

Example:
  SELECT * FROM get_document_text_status(12345);';


-- ============================================================================
-- Grant appropriate permissions
-- ============================================================================

-- semantic_search_document permissions
GRANT EXECUTE ON FUNCTION semantic_search_document(INTEGER, TEXT, FLOAT, INTEGER) TO rwbadmin;
GRANT EXECUTE ON FUNCTION semantic_search_document(INTEGER, TEXT, FLOAT, INTEGER) TO hherb;
GRANT EXECUTE ON FUNCTION semantic_search_document(INTEGER, TEXT, FLOAT, INTEGER) TO postgres;

-- semantic.chunksearch_document permissions
GRANT EXECUTE ON FUNCTION semantic.chunksearch_document(INTEGER, TEXT, FLOAT, INTEGER) TO rwbadmin;
GRANT EXECUTE ON FUNCTION semantic.chunksearch_document(INTEGER, TEXT, FLOAT, INTEGER) TO hherb;
GRANT EXECUTE ON FUNCTION semantic.chunksearch_document(INTEGER, TEXT, FLOAT, INTEGER) TO postgres;

-- Helper function permissions
GRANT EXECUTE ON FUNCTION has_abstract_embeddings(INTEGER, INTEGER) TO rwbadmin;
GRANT EXECUTE ON FUNCTION has_abstract_embeddings(INTEGER, INTEGER) TO hherb;
GRANT EXECUTE ON FUNCTION has_abstract_embeddings(INTEGER, INTEGER) TO postgres;

GRANT EXECUTE ON FUNCTION get_document_text_status(INTEGER) TO rwbadmin;
GRANT EXECUTE ON FUNCTION get_document_text_status(INTEGER) TO hherb;
GRANT EXECUTE ON FUNCTION get_document_text_status(INTEGER) TO postgres;
