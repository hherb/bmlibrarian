-- Rebuild HNSW Index with m=16 using CONCURRENT operations
-- This version doesn't block ongoing queries

-- ============================================================================
-- STEP 1: Drop Old Index CONCURRENTLY (non-blocking)
-- ============================================================================

\echo 'Dropping old index concurrently (queries can continue)...'

-- CONCURRENT drop doesn't block queries
DROP INDEX CONCURRENTLY IF EXISTS arctic_hnsw_idx_v2;
DROP INDEX CONCURRENTLY IF EXISTS arctic_hnsw_idx_v3;

\echo '✓ Old index dropped'

-- ============================================================================
-- STEP 2: Create New Index CONCURRENTLY (non-blocking)
-- ============================================================================

\echo ''
\echo '=========================================================================='
\echo 'Creating new HNSW index with m=16 CONCURRENTLY'
\echo '=========================================================================='
\echo ''
\echo 'Note: CONCURRENT builds are slower but allow queries to continue'
\echo 'Expected build time: 4-7 hours (vs 3-5 hours non-concurrent)'
\echo ''
\echo 'Monitor progress with:'
\echo '  ./monitor_index_build.sh'
\echo ''

\timing on

-- Note: CONCURRENT index creation takes longer but doesn't lock the table
CREATE INDEX CONCURRENTLY arctic_hnsw_idx_v4 ON emb_1024
USING hnsw (embedding vector_cosine_ops)
WITH (
    m = 16,
    ef_construction = 80
);

\timing off

\echo ''
\echo '✓ Index creation complete!'

-- ============================================================================
-- STEP 3: Verify
-- ============================================================================

SELECT
    indexname,
    pg_size_pretty(pg_relation_size(indexname::regclass)) as size
FROM pg_indexes
WHERE tablename = 'emb_1024' AND indexname LIKE '%hnsw%';

VACUUM ANALYZE emb_1024;

\echo ''
\echo '=========================================================================='
\echo 'INDEX REBUILD COMPLETE'
\echo '=========================================================================='
\echo ''
\echo 'Test performance:'
\echo '  uv run python semantic_search.py "your query"'
\echo ''
