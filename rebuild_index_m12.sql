-- Rebuild HNSW Index with m=12 (compromise solution)
-- This script rebuilds your HNSW index with better parameters
-- while keeping disk space manageable

-- ============================================================================
-- PREPARATION: Check Current State
-- ============================================================================

-- Check current index
SELECT
    indexname,
    pg_size_pretty(pg_relation_size(indexname::regclass)) as size
FROM pg_indexes
WHERE tablename = 'emb_1024' AND indexname LIKE '%hnsw%';

-- Check available disk space
SELECT
    pg_size_pretty(pg_database_size(current_database())) as db_size,
    pg_size_pretty(sum(pg_total_relation_size(schemaname||'.'||tablename))::bigint) as total_size
FROM pg_tables
WHERE schemaname = 'public';

-- ============================================================================
-- STEP 1: Drop Old Index
-- ============================================================================

-- WARNING: This will make vector searches unavailable until the new index is built
-- Consider running during off-hours or maintenance window

\echo 'Dropping old HNSW index (arctic_hnsw_idx_v2)...'
DROP INDEX IF EXISTS arctic_hnsw_idx_v2;

-- Verify it's gone
SELECT
    indexname
FROM pg_indexes
WHERE tablename = 'emb_1024' AND indexname LIKE '%hnsw%';

-- ============================================================================
-- STEP 2: Create New Index with m=12
-- ============================================================================

-- m=12: 2x increase from current m=6 (compromise vs m=24)
-- ef_construction=64: Keep default for faster build
-- Expected build time: 2-4 hours for 37M rows
-- Expected index size: ~412 GB (2x current 206 GB)

\echo 'Creating new HNSW index with m=12...'
\echo 'This will take 2-4 hours. Do not interrupt!'
\echo 'Monitor progress with: SELECT * FROM pg_stat_progress_create_index;'

\timing on

CREATE INDEX arctic_hnsw_idx_v3 ON emb_1024
USING hnsw (embedding vector_cosine_ops)
WITH (
    m = 12,                -- 2x current m=6
    ef_construction = 64   -- Default value
);

\timing off

\echo 'Index creation complete!'

-- ============================================================================
-- STEP 3: Verify New Index
-- ============================================================================

-- Check new index size
SELECT
    indexname,
    pg_size_pretty(pg_relation_size(indexname::regclass)) as size
FROM pg_indexes
WHERE tablename = 'emb_1024' AND indexname LIKE '%hnsw%';

-- Check index statistics
SELECT
    schemaname,
    tablename,
    indexname,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch
FROM pg_stat_user_indexes
WHERE tablename = 'emb_1024' AND indexname LIKE '%hnsw%';

-- ============================================================================
-- STEP 4: Test Performance
-- ============================================================================

\echo 'Testing index performance with a sample query...'
\echo 'Note: You need to run this with an actual embedding vector'

-- Test query template (replace with actual embedding)
-- EXPLAIN ANALYZE
-- SELECT c.document_id,
--        e.embedding <=> '[0.1, 0.2, ...]'::vector AS distance
-- FROM emb_1024 e
-- JOIN chunks c ON e.chunk_id = c.id
-- WHERE e.model_id = 1
-- ORDER BY distance
-- LIMIT 10;

\echo 'Use test_ef_search.py or semantic_search.py to test actual performance'

-- ============================================================================
-- STEP 5: Set Optimal Query Parameter
-- ============================================================================

-- You can also tune ef_search for better recall
-- Default is 40, you can try 64, 100, or 200
-- This is set per session, not system-wide

-- Example: SET hnsw.ef_search = 100;

-- ============================================================================
-- CLEANUP & MAINTENANCE
-- ============================================================================

-- Vacuum analyze to update statistics
VACUUM ANALYZE emb_1024;

-- Check final disk usage
SELECT
    pg_size_pretty(pg_database_size(current_database())) as db_size,
    pg_size_pretty(pg_tablespace_size('pg_default')) as tablespace_size;

\echo ''
\echo '============================================================================'
\echo 'REBUILD COMPLETE'
\echo '============================================================================'
\echo ''
\echo 'Expected improvements:'
\echo '  - Query time: 263s → 30-60s (5-10x faster)'
\echo '  - Index size: 206 GB → ~412 GB (2x larger)'
\echo ''
\echo 'Next steps:'
\echo '  1. Test with: uv run python test_ef_search.py "your query"'
\echo '  2. Compare against old baseline (263s)'
\echo '  3. If still slow, consider m=16 or IVFFlat index'
\echo ''
