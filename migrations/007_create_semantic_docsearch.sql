-- Migration: Create Semantic Document Search Convenience Function
-- Description: Creates semantic_docsearch function that extends semantic_search with document metadata
-- Author: BMLibrarian
-- Date: 2025-11-10

-- ============================================================================
-- Drop function if it exists (idempotent migration)
-- ============================================================================

DROP FUNCTION IF EXISTS semantic_docsearch(text, float, integer);

-- ============================================================================
-- Create the semantic document search convenience function
-- ============================================================================

CREATE OR REPLACE FUNCTION semantic_docsearch(
    search_text TEXT,
    threshold FLOAT DEFAULT 0.7,
    result_limit INTEGER DEFAULT 100
)
RETURNS TABLE (
    chunk_id INTEGER,
    document_id INTEGER,
    score FLOAT,
    doi TEXT,
    source_id INTEGER,
    external_id TEXT,
    title TEXT,
    publication_date DATE,
    authors TEXT[],
    abstract TEXT
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
    -- Join with document table to return comprehensive metadata
    RETURN QUERY
    SELECT
        e.chunk_id,
        c.document_id,
        (1 - (e.embedding <=> query_embedding))::FLOAT as similarity_score,
        d.doi,
        d.source_id,
        d.external_id,
        d.title,
        d.publication_date,
        d.authors,
        d.abstract
    FROM
        emb_1024 e
        JOIN chunks c ON e.chunk_id = c.id
        JOIN document d ON c.document_id = d.id
    WHERE
        (1 - (e.embedding <=> query_embedding)) >= threshold
        AND d.withdrawn_date IS NULL  -- Exclude withdrawn documents
    ORDER BY
        e.embedding <=> query_embedding
    LIMIT result_limit;
END;
$$;

-- ============================================================================
-- Add function documentation
-- ============================================================================

COMMENT ON FUNCTION semantic_docsearch(TEXT, FLOAT, INTEGER) IS
'Convenience wrapper for semantic_search that includes complete document metadata.
Returns chunk IDs, document IDs, similarity scores, and all key document fields.

Parameters:
  - search_text: Natural language search query
  - threshold: Minimum similarity score (0.0 to 1.0, default: 0.7)
  - result_limit: Maximum number of results to return (default: 100)

Returns: Table with chunk_id, document_id, similarity score, and document metadata:
  - doi: Document DOI identifier
  - source_id: Reference to source database
  - external_id: External database identifier (e.g., PubMed ID)
  - title: Document title
  - publication_date: Publication date
  - authors: Array of author names
  - abstract: Document abstract text

Technical Details:
  - Uses ollama_embedding() to generate query embeddings
  - Embeddings model: snowflake-arctic-embed2:latest (1024 dimensions)
  - Similarity metric: Cosine similarity (pgvector <=> operator)
  - Index: HNSW for fast approximate nearest neighbor search
  - Searches at chunk level for precise passage retrieval
  - Automatically excludes withdrawn documents

Use Cases:
  - One-stop semantic search with complete document context
  - Building document libraries with semantic search
  - Citation extraction with full bibliographic information
  - Research applications requiring both chunk and document data

Example Usage:
  -- Basic search with document metadata
  SELECT document_id, title, authors, score
  FROM semantic_docsearch(''cardiovascular benefits of exercise'', 0.75, 20)
  ORDER BY score DESC;

  -- Get unique documents with best matching chunks
  SELECT DISTINCT ON (document_id)
    document_id, title, doi, publication_date, score
  FROM semantic_docsearch(''CRISPR gene editing mechanisms'', 0.7, 50)
  ORDER BY document_id, score DESC;

  -- Search with full metadata for citation building
  SELECT
    title,
    array_to_string(authors, '', '') as author_list,
    publication_date,
    doi,
    score
  FROM semantic_docsearch(''insulin resistance pathophysiology'', 0.8, 10)
  ORDER BY score DESC;

Performance Notes:
  - Embedding generation takes ~2-5 seconds per query
  - Document JOIN adds minimal overhead (~5-10ms for 100 results)
  - HNSW index provides fast similarity search
  - Adjust threshold based on precision/recall needs';

-- ============================================================================
-- Grant appropriate permissions
-- ============================================================================

-- Grant execute permission to PUBLIC (all database users)
-- Since this is a repository for publicly available documents with no confidential data,
-- we grant access to all users. User roles only exist to distinguish human evaluators.
GRANT EXECUTE ON FUNCTION semantic_docsearch(TEXT, FLOAT, INTEGER) TO PUBLIC;

-- ============================================================================
-- Example usage (commented for migration)
-- ============================================================================

-- Basic Examples:
-- SELECT * FROM semantic_docsearch('cardiovascular exercise benefits', 0.7, 20);
-- SELECT document_id, title, score FROM semantic_docsearch('diabetes treatment', 0.75, 50);

-- Get unique documents (best matching chunk per document):
-- SELECT DISTINCT ON (document_id)
--   document_id, title, doi, score
-- FROM semantic_docsearch('myocardial infarction mechanisms', 0.7, 100)
-- ORDER BY document_id, score DESC;

-- Citation-ready format:
-- SELECT
--   title,
--   array_to_string(authors, ', ') as authors,
--   to_char(publication_date, 'YYYY-MM-DD') as pub_date,
--   doi,
--   round(score::numeric, 3) as relevance
-- FROM semantic_docsearch('inflammatory markers in atherosclerosis', 0.8, 15)
-- ORDER BY score DESC;
