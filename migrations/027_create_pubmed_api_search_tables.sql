-- Migration: Create PubMed API Search Tracking Tables
-- Description: Creates tables for tracking PubMed API search sessions and results
-- Author: BMLibrarian
-- Date: 2025-12-13

-- ============================================================================
-- PubMed API Search Session Tracking
-- ============================================================================
-- These tables track searches performed via the PubMed API, enabling:
-- - Search provenance and reproducibility
-- - Query history and analysis
-- - Document-to-search relationship tracking

-- ============================================================================
-- 1. Search Sessions - Track complete API search workflows
-- ============================================================================

CREATE TABLE IF NOT EXISTS pubmed_api_searches (
    id SERIAL PRIMARY KEY,
    session_id UUID NOT NULL DEFAULT gen_random_uuid(),
    research_question TEXT NOT NULL,
    pubmed_query TEXT NOT NULL,
    query_concepts JSONB,
    total_results INTEGER,
    results_retrieved INTEGER,
    results_imported INTEGER,
    results_duplicate INTEGER,
    search_timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    UNIQUE(session_id)
);

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_pubmed_api_searches_timestamp
    ON pubmed_api_searches(search_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_pubmed_api_searches_user
    ON pubmed_api_searches(user_id) WHERE user_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_pubmed_api_searches_session
    ON pubmed_api_searches(session_id);

-- Comments
COMMENT ON TABLE pubmed_api_searches IS
    'Tracks PubMed API search sessions for provenance and reproducibility';
COMMENT ON COLUMN pubmed_api_searches.session_id IS
    'Unique identifier for the search session (UUID)';
COMMENT ON COLUMN pubmed_api_searches.research_question IS
    'Original natural language research question';
COMMENT ON COLUMN pubmed_api_searches.pubmed_query IS
    'Generated PubMed query string with MeSH terms and filters';
COMMENT ON COLUMN pubmed_api_searches.query_concepts IS
    'JSON array of extracted concepts with MeSH terms and keywords';
COMMENT ON COLUMN pubmed_api_searches.total_results IS
    'Total number of results found in PubMed';
COMMENT ON COLUMN pubmed_api_searches.results_retrieved IS
    'Number of articles actually fetched from PubMed';
COMMENT ON COLUMN pubmed_api_searches.results_imported IS
    'Number of new articles imported to local database';
COMMENT ON COLUMN pubmed_api_searches.results_duplicate IS
    'Number of articles skipped (already in database)';

-- ============================================================================
-- 2. Search-Document Relationships - Track which documents came from which search
-- ============================================================================

CREATE TABLE IF NOT EXISTS pubmed_api_search_documents (
    search_id INTEGER NOT NULL REFERENCES pubmed_api_searches(id) ON DELETE CASCADE,
    document_id INTEGER NOT NULL REFERENCES document(id) ON DELETE CASCADE,
    relevance_rank INTEGER,
    PRIMARY KEY (search_id, document_id)
);

-- Indexes for efficient lookups
CREATE INDEX IF NOT EXISTS idx_pubmed_api_search_docs_search
    ON pubmed_api_search_documents(search_id);
CREATE INDEX IF NOT EXISTS idx_pubmed_api_search_docs_document
    ON pubmed_api_search_documents(document_id);

-- Comments
COMMENT ON TABLE pubmed_api_search_documents IS
    'Links documents to the PubMed API searches that found/imported them';
COMMENT ON COLUMN pubmed_api_search_documents.relevance_rank IS
    'Position in search results (1 = most relevant according to PubMed)';

-- ============================================================================
-- 3. Helper Views
-- ============================================================================

-- View: Recent search history with statistics
CREATE OR REPLACE VIEW v_pubmed_api_search_history AS
SELECT
    pas.id,
    pas.session_id,
    pas.research_question,
    LEFT(pas.pubmed_query, 200) AS query_preview,
    pas.total_results,
    pas.results_imported,
    pas.results_duplicate,
    COALESCE(pas.results_imported, 0) + COALESCE(pas.results_duplicate, 0) AS total_local,
    pas.search_timestamp,
    u.username AS searched_by,
    (SELECT COUNT(*) FROM pubmed_api_search_documents pasd
     WHERE pasd.search_id = pas.id) AS linked_documents
FROM pubmed_api_searches pas
LEFT JOIN users u ON pas.user_id = u.id
ORDER BY pas.search_timestamp DESC;

COMMENT ON VIEW v_pubmed_api_search_history IS
    'View of recent PubMed API searches with linked document counts';

-- View: Document provenance - which searches found each document
CREATE OR REPLACE VIEW v_document_search_provenance AS
SELECT
    d.id AS document_id,
    d.external_id AS pmid,
    d.title,
    pas.session_id,
    pas.research_question,
    pasd.relevance_rank,
    pas.search_timestamp
FROM document d
JOIN pubmed_api_search_documents pasd ON d.id = pasd.document_id
JOIN pubmed_api_searches pas ON pasd.search_id = pas.id
ORDER BY d.id, pas.search_timestamp DESC;

COMMENT ON VIEW v_document_search_provenance IS
    'Shows which PubMed API searches discovered each document';

-- ============================================================================
-- 4. Helper Functions
-- ============================================================================

-- Function: Get search statistics summary
CREATE OR REPLACE FUNCTION get_pubmed_api_search_stats()
RETURNS TABLE(
    total_searches BIGINT,
    total_documents_found BIGINT,
    total_documents_imported BIGINT,
    total_documents_duplicate BIGINT,
    avg_results_per_search NUMERIC,
    searches_last_7_days BIGINT,
    searches_last_30_days BIGINT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        COUNT(*)::BIGINT AS total_searches,
        COALESCE(SUM(total_results), 0)::BIGINT AS total_documents_found,
        COALESCE(SUM(results_imported), 0)::BIGINT AS total_documents_imported,
        COALESCE(SUM(results_duplicate), 0)::BIGINT AS total_documents_duplicate,
        COALESCE(AVG(total_results), 0)::NUMERIC AS avg_results_per_search,
        COUNT(*) FILTER (WHERE search_timestamp > NOW() - INTERVAL '7 days')::BIGINT AS searches_last_7_days,
        COUNT(*) FILTER (WHERE search_timestamp > NOW() - INTERVAL '30 days')::BIGINT AS searches_last_30_days
    FROM pubmed_api_searches;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION get_pubmed_api_search_stats IS
    'Returns summary statistics for PubMed API searches';

-- ============================================================================
-- Grants
-- ============================================================================

-- Grant permissions to PUBLIC (all database users)
-- Since this is a repository for publicly available documents with no confidential data,
-- we grant access to all users. User roles only exist to distinguish human evaluators.
GRANT SELECT, INSERT, UPDATE, DELETE ON pubmed_api_searches TO PUBLIC;
GRANT SELECT, INSERT, UPDATE, DELETE ON pubmed_api_search_documents TO PUBLIC;
GRANT USAGE ON SEQUENCE pubmed_api_searches_id_seq TO PUBLIC;

-- ============================================================================
-- Migration Complete
-- ============================================================================
