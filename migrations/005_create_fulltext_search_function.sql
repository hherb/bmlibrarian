-- Migration: Create Full-Text Search Function
-- Description: Creates a reusable PostgreSQL function for searching documents using tsquery expressions
-- Author: BMLibrarian
-- Date: 2025-11-08

-- ============================================================================
-- Drop function if it exists (idempotent migration)
-- ============================================================================

DROP FUNCTION IF EXISTS fulltext_search(text, integer);

-- ============================================================================
-- Create the full-text search function
-- ============================================================================

CREATE OR REPLACE FUNCTION fulltext_search(
    ts_query_expression text,
    max_results integer DEFAULT 100
)
RETURNS TABLE (
    id integer,
    title text,
    abstract text,
    authors text[],
    publication text,
    publication_date date,
    doi text,
    url text,
    pdf_filename text,
    external_id text,
    source_id integer,
    rank real
)
LANGUAGE plpgsql
AS $$
DECLARE
    parsed_query tsquery;
BEGIN
    -- Convert the text query to a tsquery object
    -- This handles the parsing and validation
    BEGIN
        parsed_query := to_tsquery('english', ts_query_expression);
    EXCEPTION WHEN OTHERS THEN
        -- If query parsing fails, try using plainto_tsquery for simpler queries
        parsed_query := plainto_tsquery('english', ts_query_expression);
    END;

    -- Return matching documents ordered by relevance rank
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
        ts_rank(d.search_vector, parsed_query) AS rank
    FROM
        document d
    WHERE
        d.search_vector @@ parsed_query
        AND d.withdrawn_date IS NULL  -- Exclude withdrawn documents
    ORDER BY
        ts_rank(d.search_vector, parsed_query) DESC,
        d.publication_date DESC NULLS LAST
    LIMIT max_results;
END;
$$;

-- ============================================================================
-- Add function documentation
-- ============================================================================

COMMENT ON FUNCTION fulltext_search(text, integer) IS
'Performs full-text search on documents using PostgreSQL tsquery syntax.
Parameters:
  - ts_query_expression: A text string in tsquery format (e.g., ''exercise & cardiovascular'', ''diabetes | insulin'')
  - max_results: Maximum number of results to return (default: 100)
Returns: Table with document details ordered by relevance rank

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
  - Ranks results by relevance (title matches weighted higher than abstract)
  - Orders by rank DESC, then publication_date DESC';

-- ============================================================================
-- Grant appropriate permissions
-- ============================================================================

-- Grant execute permission to PUBLIC (all database users)
-- Since this is a repository for publicly available documents with no confidential data,
-- we grant access to all users. User roles only exist to distinguish human evaluators.
GRANT EXECUTE ON FUNCTION fulltext_search(text, integer) TO PUBLIC;

-- ============================================================================
-- Verify function creation
-- ============================================================================

-- This will display the function signature and description
-- Commented out for migration execution, uncomment for manual verification
-- \df+ fulltext_search

-- ============================================================================
-- Example usage (commented for migration)
-- ============================================================================

-- SELECT * FROM fulltext_search('exercise & cardiovascular', 10);
-- SELECT * FROM fulltext_search('diabetes | insulin', 50);
-- SELECT * FROM fulltext_search('(hypertension | ''high blood pressure'') & treatment', 25);
-- SELECT id, title, rank FROM fulltext_search('cancer immunotherapy', 15);
