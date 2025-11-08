-- HNSW Index Optimization Script for emb_1024
-- This script rebuilds your HNSW index with optimized parameters for 60M chunks

-- ============================================================================
-- STEP 1: Rebuild HNSW Index with Optimized Parameters
-- ============================================================================

-- Drop existing index (this will make searches unavailable temporarily)
--DROP INDEX IF EXISTS arctic_hnsw_idx_v2;

-- Create new index with optimized parameters for large dataset
-- m=24: More connections per layer for better recall (default: 16)
-- ef_construction=96: More candidates during build for better quality (default: 64)
-- WARNING: This will take significant time to build (possibly hours for 60M rows)
--CREATE INDEX arctic_hnsw_idx_v3 ON emb_1024
--USING hnsw (embedding vector_cosine_ops)
--WITH (
--    m = 24,              -- Increase from default 16
--    ef_construction = 96 -- Increase from default 64
--);

-- ============================================================================
-- STEP 2: Enable Full-Text Search for Hybrid Search (RECOMMENDED)
-- ============================================================================

-- Check if text_search column exists
-- If it doesn't exist, add it:
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS text_search tsvector;

-- Populate the text_search column
-- NOTE: Your chunks table has a 'text' column with content
-- WARNING: This will take time for 37M rows (possibly 30-60 minutes)
UPDATE chunks
SET text_search = to_tsvector('english', text)
WHERE text_search IS NULL;

-- Create GIN index for fast full-text search
-- This is crucial for hybrid search performance
CREATE INDEX IF NOT EXISTS idx_chunks_text_search
ON chunks USING GIN(text_search);

-- Create trigger to keep text_search updated automatically
-- (only if it doesn't exist)
CREATE OR REPLACE FUNCTION chunks_text_search_trigger() RETURNS trigger AS $$
BEGIN
    NEW.text_search := to_tsvector('english', NEW.text);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS chunks_text_search_update ON chunks;
CREATE TRIGGER chunks_text_search_update
BEFORE INSERT OR UPDATE OF text ON chunks
FOR EACH ROW
EXECUTE FUNCTION chunks_text_search_trigger();

-- ============================================================================
-- STEP 3: Query-time Parameter Tuning
-- ============================================================================

-- Set higher ef_search for better recall (can be set per session or globally)
-- Default is 40, try 100 for better recall
SET hnsw.ef_search = 100;

-- To make this permanent, add to postgresql.conf:
-- hnsw.ef_search = 100

-- ============================================================================
-- STEP 4: Test Queries
-- ============================================================================

-- Test pure vector search performance
EXPLAIN ANALYZE
SELECT d.title,
       1 - distance AS similarity
FROM (
    SELECT c.document_id,
           e.embedding <=> '[0.1, 0.2, ...]'::vector AS distance
    FROM emb_1024 e
    JOIN chunks c ON e.chunk_id = c.id
    WHERE e.model_id = 1
    ORDER BY distance
    LIMIT 30
) AS ranked
JOIN document d ON ranked.document_id = d.id;

-- Test hybrid search performance (if text_search column exists)
EXPLAIN ANALYZE
SELECT d.title,
       1 - distance AS similarity
FROM (
    SELECT c.document_id,
           e.embedding <=> '[0.1, 0.2, ...]'::vector AS distance
    FROM emb_1024 e
    JOIN chunks c ON e.chunk_id = c.id
    WHERE e.model_id = 1
      AND c.text_search @@ to_tsquery('english', 'mountain | sickness | prophylactic')
    ORDER BY distance
    LIMIT 10000
) AS ranked
JOIN document d ON ranked.document_id = d.id
LIMIT 30;

-- ============================================================================
-- STEP 5: Monitoring Queries
-- ============================================================================

-- Check index size
SELECT
    indexname,
    pg_size_pretty(pg_relation_size(indexname::regclass)) as size
FROM pg_indexes
WHERE tablename = 'emb_1024';

-- Check index usage statistics
SELECT
    indexname,
    idx_scan as scans,
    idx_tup_read as tuples_read,
    idx_tup_fetch as tuples_fetched
FROM pg_stat_user_indexes
WHERE tablename = 'emb_1024';

-- Check table size
SELECT
    pg_size_pretty(pg_total_relation_size('emb_1024')) as total_size,
    pg_size_pretty(pg_relation_size('emb_1024')) as table_size,
    pg_size_pretty(pg_total_relation_size('emb_1024') -
                   pg_relation_size('emb_1024')) as index_size;
