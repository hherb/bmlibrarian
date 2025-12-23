-- Migration: Create BM25 and Semantic Search Functions
-- Description: Creates BM25-ranked search and semantic search functions for enhanced document retrieval
-- Author: BMLibrarian
-- Date: 2025-11-09

-- ============================================================================
-- Drop functions if they exist (idempotent migration)
-- ============================================================================

DROP FUNCTION IF EXISTS bm25(text, integer);
DROP FUNCTION IF EXISTS semantic_search(text, float, integer);

-- ============================================================================
-- Create the BM25 search function
-- ============================================================================

CREATE OR REPLACE FUNCTION bm25(
    search_expression TEXT,
    max_results INTEGER DEFAULT 100
)
RETURNS TABLE (
    id INTEGER,
    title TEXT,
    abstract TEXT,
    authors TEXT[],
    publication TEXT,
    publication_date DATE,
    doi TEXT,
    url TEXT,
    pdf_filename TEXT,
    external_id TEXT,
    source_id INTEGER,
    rank REAL
)
LANGUAGE plpgsql
AS $$
DECLARE
    parsed_query tsquery;
    k1 CONSTANT REAL := 1.2;  -- BM25 k1 parameter (term frequency saturation)
    b CONSTANT REAL := 0.75;  -- BM25 b parameter (length normalization)
BEGIN
    -- Convert the text query to a tsquery object
    BEGIN
        parsed_query := to_tsquery('english', search_expression);
    EXCEPTION WHEN OTHERS THEN
        -- If query parsing fails, use plainto_tsquery for simpler queries
        parsed_query := plainto_tsquery('english', search_expression);
    END;

    -- Return matching documents ordered by BM25-like relevance rank
    -- Using ts_rank_cd with normalization flags for BM25-like behavior
    RETURN QUERY
    SELECT
        d.id,
        d.title,
        d.abstract,
        d.authors,
        d.publication,
        d.publication_date,
        d.doi,
        d.url,
        d.pdf_filename,
        d.external_id,
        d.source_id,
        -- ts_rank_cd with normalization: flag 1 (divide by document length)
        -- approximates BM25 better than ts_rank
        ts_rank_cd(
            d.search_vector,
            parsed_query,
            1  -- normalization flag: divide by length
        ) AS rank
    FROM
        document d
    WHERE
        d.search_vector @@ parsed_query
        AND d.withdrawn_date IS NULL  -- Exclude withdrawn documents
    ORDER BY
        ts_rank_cd(d.search_vector, parsed_query, 1) DESC,
        d.publication_date DESC NULLS LAST
    LIMIT max_results;
END;
$$;

-- ============================================================================
-- Create the semantic search function
-- ============================================================================

CREATE OR REPLACE FUNCTION semantic_search(
    search_text TEXT,
    threshold FLOAT DEFAULT 0.7,
    result_limit INTEGER DEFAULT 100
)
RETURNS TABLE (
    chunk_id INTEGER,
    document_id INTEGER,
    score FLOAT
)
LANGUAGE plpgsql
AS $$
DECLARE
    query_embedding vector(1024);
BEGIN
    -- Generate embedding for the search text using ollama_embedding function
    query_embedding := ollama_embedding(search_text);

    -- Handle case where embedding generation fails
    IF query_embedding IS NULL THEN
        RAISE EXCEPTION 'Failed to generate embedding for search text';
    END IF;

    -- Search for similar embeddings using cosine similarity
    -- Note: cosine similarity returns values from -1 to 1, where 1 is most similar
    -- We convert to distance (1 - cosine_similarity) for comparison with threshold
    RETURN QUERY
    SELECT
        e.chunk_id,
        c.document_id,
        (1 - (e.embedding <=> query_embedding))::FLOAT as similarity_score
    FROM
        emb_1024 e
        JOIN chunks c ON e.chunk_id = c.id
    WHERE
        (1 - (e.embedding <=> query_embedding)) >= threshold
    ORDER BY
        e.embedding <=> query_embedding
    LIMIT result_limit;
END;
$$;

-- ============================================================================
-- Add function documentation
-- ============================================================================

COMMENT ON FUNCTION bm25(TEXT, INTEGER) IS
'Performs BM25-like ranked full-text search on document abstracts and titles.
Uses PostgreSQL ts_rank_cd with length normalization for BM25-approximation.
Returns documents ordered by relevance score with complete metadata.

Parameters:
  - search_expression: A text string in tsquery format (e.g., ''exercise & cardiovascular'')
  - max_results: Maximum number of results to return (default: 100)

Returns: Table with document details ordered by BM25-like relevance rank

BM25 Advantages:
  - Superior ranking compared to ts_rank, especially for varying document lengths
  - Length normalization prevents bias toward longer or shorter documents
  - Better precision/recall balance for research queries

Query Syntax Examples:
  - AND operator: ''diabetes & treatment''
  - OR operator: ''diabetes | insulin''
  - NOT operator: ''diabetes & !type2''
  - Complex: ''(hypertension | "high blood pressure") & treatment''
  - Prefix match: ''cardio:*'' (matches cardiology, cardiovascular, etc.)

The function automatically:
  - Uses the idx_document_fts GIN index for fast searches
  - Excludes withdrawn documents
  - Falls back to plainto_tsquery if parsing fails
  - Applies BM25-like length normalization
  - Orders by rank DESC, then publication_date DESC';

COMMENT ON FUNCTION semantic_search(TEXT, FLOAT, INTEGER) IS
'Performs semantic search on chunk embeddings using cosine similarity.
Returns chunk IDs, document IDs, and similarity scores above the specified threshold.

Parameters:
  - search_text: Natural language search query
  - threshold: Minimum similarity score (0.0 to 1.0, default: 0.7)
  - result_limit: Maximum number of results to return (default: 100)

Returns: Table with chunk_id, document_id, and similarity score (0 to 1, where 1 is most similar)

Technical Details:
  - Uses ollama_embedding() to generate query embeddings
  - Embeddings model: snowflake-arctic-embed2:latest (1024 dimensions)
  - Similarity metric: Cosine similarity (pgvector <=> operator)
  - Index: HNSW for fast approximate nearest neighbor search
  - Searches at chunk level for precise passage retrieval

Use Cases:
  - Conceptual similarity search beyond keyword matching
  - Finding related research with different terminology
  - Question answering over document corpus
  - Discovering relevant passages for evidence synthesis

Performance Notes:
  - Embedding generation takes ~2-5 seconds per query
  - Sequential scan is used when HNSW index is rebuilding
  - Adjust threshold based on precision/recall needs:
    * 0.85+: High precision, narrow results
    * 0.70-0.85: Balanced (default)
    * 0.60-0.70: High recall, broader results

Example Usage:
  SELECT * FROM semantic_search(''cardiovascular benefits of exercise'', 0.75, 20);

  -- Join with chunks table to get text
  SELECT s.score, c.text, c.document_title
  FROM semantic_search(''CRISPR gene editing'', 0.75, 10) s
  JOIN chunks c ON s.chunk_id = c.id
  ORDER BY s.score DESC;';

-- ============================================================================
-- Grant appropriate permissions
-- ============================================================================

-- Grant execute permission to PUBLIC (all database users)
-- Since this is a repository for publicly available documents with no confidential data,
-- we grant access to all users. User roles only exist to distinguish human evaluators.
GRANT EXECUTE ON FUNCTION bm25(TEXT, INTEGER) TO PUBLIC;
GRANT EXECUTE ON FUNCTION semantic_search(TEXT, FLOAT, INTEGER) TO PUBLIC;

-- ============================================================================
-- Verify function creation
-- ============================================================================

-- This will display the function signatures and descriptions
-- Commented out for migration execution, uncomment for manual verification
-- \df+ bm25
-- \df+ semantic_search

-- ============================================================================
-- Example usage (commented for migration)
-- ============================================================================

-- BM25 Examples:
-- SELECT id, title, rank FROM bm25('cardiovascular exercise benefits', 20);
-- SELECT id, title, abstract, rank FROM bm25('diabetes & (treatment | therapy)', 50);
-- SELECT id, title, publication_date, rank FROM bm25('myocardial infarction', 100);

-- Semantic Search Examples:
-- SELECT * FROM semantic_search('What are the cardiovascular benefits of exercise?', 0.7, 20);
-- SELECT * FROM semantic_search('mechanisms of insulin resistance', 0.85, 50);
-- SELECT * FROM semantic_search('diabetes treatment options', 0.6, 100);

-- Hybrid Search Example (combining BM25 and semantic search):
-- WITH bm25_results AS (
--     SELECT id AS document_id, rank * 2 AS score
--     FROM bm25('cardiovascular exercise', 100)
-- ),
-- semantic_results AS (
--     SELECT DISTINCT document_id, AVG(score) AS score
--     FROM semantic_search('cardiovascular benefits of exercise', 0.7, 100)
--     GROUP BY document_id
-- )
-- SELECT
--     COALESCE(bm.document_id, sr.document_id) AS document_id,
--     COALESCE(bm.score, 0) + COALESCE(sr.score, 0) AS combined_score
-- FROM bm25_results bm
-- FULL OUTER JOIN semantic_results sr ON bm.document_id = sr.document_id
-- ORDER BY combined_score DESC
-- LIMIT 50;
