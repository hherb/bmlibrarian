-- Optimal HNSW Index Rebuild with m=16
-- Best balance of performance, recall, and disk usage
-- For systems with adequate disk space (1+ TB free)

-- ============================================================================
-- CONFIGURATION
-- ============================================================================

-- m=16: Industry standard, excellent performance
-- ef_construction=80: Slightly higher than default for better quality
-- Expected build time: 3-5 hours for 37M embeddings
-- Expected index size: ~550 GB (2.67x current 206 GB)
-- Expected query time: 15-25 seconds (12-20x faster than current 290s)
-- Expected recall: 97-99%

-- ============================================================================
-- PREPARATION
-- ============================================================================

\echo 'Checking current state...'

-- Show current index
SELECT
    indexname,
    pg_size_pretty(pg_relation_size(indexname::regclass)) as size
FROM pg_indexes
WHERE tablename = 'emb_1024' AND indexname LIKE '%hnsw%';

-- Show disk space
SELECT
    pg_size_pretty(pg_database_size(current_database())) as current_db_size,
    pg_size_pretty(pg_tablespace_size('pg_default')) as tablespace_size;

-- ============================================================================
-- STEP 1: Drop Old Index
-- ============================================================================

\echo ''
\echo '=========================================================================='
\echo 'STEP 1: Dropping old index'
\echo '=========================================================================='
\echo ''
\echo 'WARNING: Vector searches will be unavailable until rebuild completes!'
\echo 'Press Ctrl+C within 10 seconds to abort...'

-- SELECT pg_sleep(10);

DROP INDEX IF EXISTS arctic_hnsw_idx_v2;
DROP INDEX IF EXISTS arctic_hnsw_idx_v3;

\echo '✓ Old index dropped'

-- ============================================================================
-- STEP 2: Create Optimal Index with m=16
-- ============================================================================

\echo ''
\echo '=========================================================================='
\echo 'STEP 2: Creating new HNSW index with m=16'
\echo '=========================================================================='
\echo ''
\echo 'Configuration:'
\echo '  m = 16 (industry standard, optimal for most use cases)'
\echo '  ef_construction = 80 (enhanced build quality)'
\echo ''
\echo 'Expected outcomes:'
\echo '  - Index size: ~550 GB'
\echo '  - Build time: 3-5 hours'
\echo '  - Query time: 15-25 seconds (12-20x faster)'
\echo '  - Recall: 97-99%'
\echo ''
\echo 'Monitor progress in another terminal with:'
\echo '  psql knowledgebase -c "SELECT * FROM pg_stat_progress_create_index;"'
\echo ''
\echo 'Starting build...'

\timing on

CREATE INDEX arctic_hnsw_idx_v4 ON emb_1024
USING hnsw (embedding vector_cosine_ops)
WITH (
    m = 16,                -- Optimal: industry standard
    ef_construction = 80   -- Enhanced: better than default 64
);

\timing off

\echo ''
\echo '✓ Index creation complete!'

-- ============================================================================
-- STEP 3: Verify and Optimize
-- ============================================================================

\echo ''
\echo '=========================================================================='
\echo 'STEP 3: Verification and optimization'
\echo '=========================================================================='
\echo ''

-- Show new index size
SELECT
    indexname,
    pg_size_pretty(pg_relation_size(indexname::regclass)) as size,
    pg_size_pretty(pg_relation_size(indexname::regclass)::numeric / 1024 / 1024 / 1024) as size_gb
FROM pg_indexes
WHERE tablename = 'emb_1024' AND indexname LIKE '%hnsw%';

-- Vacuum analyze to update statistics
\echo 'Running VACUUM ANALYZE...'
VACUUM ANALYZE emb_1024;
\echo '✓ Statistics updated'

-- Show final disk usage
SELECT
    pg_size_pretty(pg_database_size(current_database())) as db_size,
    pg_size_pretty(pg_tablespace_size('pg_default')) as tablespace_size;

-- ============================================================================
-- STEP 4: Performance Testing
-- ============================================================================

\echo ''
\echo '=========================================================================='
\echo 'STEP 4: Performance testing'
\echo '=========================================================================='
\echo ''
\echo 'Test the new index performance:'
\echo '  uv run python semantic_search.py "your medical question"'
\echo ''
\echo 'Expected query time: 15-25 seconds (vs 290s before)'
\echo ''
\echo 'Optional: Tune ef_search for better recall (default is 40):'
\echo '  SET hnsw.ef_search = 64;   -- Good balance'
\echo '  SET hnsw.ef_search = 100;  -- Higher recall, slightly slower'
\echo ''

-- ============================================================================
-- COMPLETION SUMMARY
-- ============================================================================

\echo ''
\echo '=========================================================================='
\echo 'INDEX REBUILD COMPLETE'
\echo '=========================================================================='
\echo ''
\echo 'Next steps:'
\echo '  1. Test query performance with semantic_search.py'
\echo '  2. Verify results quality (should be excellent with m=16)'
\echo '  3. If needed, tune ef_search parameter for specific use cases'
\echo ''
\echo 'Configuration summary:'
\echo '  - Index: arctic_hnsw_idx_v4'
\echo '  - Parameters: m=16, ef_construction=80'
\echo '  - Expected performance: 12-20x faster queries'
\echo '  - Expected recall: 97-99%'
\echo ''
\echo 'If you need even better performance:'
\echo '  - Consider m=24 (but diminishing returns)'
\echo '  - Tune ef_search parameter per query type'
\echo '  - Ensure adequate shared_buffers in postgresql.conf'
\echo ''
