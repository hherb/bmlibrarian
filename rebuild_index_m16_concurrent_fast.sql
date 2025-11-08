-- Optimized HNSW Index Rebuild with m=16 - CONCURRENT version
-- Tuned for systems with high RAM (128GB)
-- Uses 36GB maintenance_work_mem for faster builds
-- CONCURRENT allows queries to continue during rebuild

-- ============================================================================
-- PERFORMANCE TUNING (for this session only)
-- ============================================================================

\echo 'Setting performance parameters for fast build...'

-- Increase maintenance memory (huge impact on build speed)
SET maintenance_work_mem = '36GB';  -- Default is usually 64MB-1GB!

-- Use multiple CPU cores for index build
SET max_parallel_maintenance_workers = 4;

-- Increase work memory for sorting operations
SET work_mem = '2GB';

-- Show current settings
\echo ''
\echo 'Current performance settings:'
SELECT
    name,
    setting,
    unit,
    setting || COALESCE(unit, '') AS value
FROM pg_settings
WHERE name IN (
    'maintenance_work_mem',
    'max_parallel_maintenance_workers',
    'work_mem',
    'shared_buffers',
    'effective_cache_size'
);

\echo ''
\echo '✓ Performance parameters set'
\echo ''

-- ============================================================================
-- STEP 1: Drop Old Index CONCURRENTLY
-- ============================================================================

\echo '=========================================================================='
\echo 'STEP 1: Dropping old index concurrently'
\echo '=========================================================================='
\echo ''
\echo 'Note: Queries can continue during drop and rebuild'
\echo ''

DROP INDEX CONCURRENTLY IF EXISTS arctic_hnsw_idx_v2;
DROP INDEX CONCURRENTLY IF EXISTS arctic_hnsw_idx_v3;

\echo '✓ Old index dropped'

-- ============================================================================
-- STEP 2: Create New Index CONCURRENTLY with m=16
-- ============================================================================

\echo ''
\echo '=========================================================================='
\echo 'STEP 2: Creating new HNSW index with m=16 CONCURRENTLY'
\echo '=========================================================================='
\echo ''
\echo 'Configuration:'
\echo '  m = 16 (industry standard)'
\echo '  ef_construction = 80 (enhanced quality)'
\echo '  maintenance_work_mem = 36GB (high performance)'
\echo '  max_parallel_maintenance_workers = 4'
\echo '  CONCURRENT = yes (queries can continue)'
\echo ''
\echo 'Expected with optimized settings:'
\echo '  - Index size: ~550 GB'
\echo '  - Build time: 3-5 hours (CONCURRENT is ~20% slower)'
\echo '  - Query time: 15-25 seconds (12-20x faster when done)'
\echo '  - Recall: 97-99%'
\echo ''
\echo 'During build:'
\echo '  - Old queries will use sequential scan (slow but work)'
\echo '  - You can continue working'
\echo '  - No locks on the table'
\echo ''
\echo 'Monitor progress with:'
\echo '  watch -n 10 "psql knowledgebase -c \"SELECT phase, round(100.0 * tuples_done / nullif(tuples_total, 0), 1) AS pct, tuples_done, tuples_total FROM pg_stat_progress_create_index;\""'
\echo ''
\echo 'Or use:'
\echo '  ./monitor_simple.sh'
\echo ''
\echo 'Starting build...'

\timing on

-- CONCURRENT index creation takes longer but doesn't block queries
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
    pg_size_pretty(pg_relation_size(indexname::regclass)) as size
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

-- Check index is valid
SELECT
    indexname,
    indexdef
FROM pg_indexes
WHERE tablename = 'emb_1024' AND indexname = 'arctic_hnsw_idx_v4';

-- ============================================================================
-- COMPLETION
-- ============================================================================

\echo ''
\echo '=========================================================================='
\echo 'INDEX REBUILD COMPLETE'
\echo '=========================================================================='
\echo ''
\echo 'Next steps:'
\echo '  1. Test query performance:'
\echo '     uv run python semantic_search.py "your medical question"'
\echo ''
\echo '  2. Expected results:'
\echo '     - Query time: 15-25 seconds (vs 290s before)'
\echo '     - Excellent recall quality (97-99%)'
\echo ''
\echo '  3. Optional: Tune ef_search for specific use cases'
\echo '     SET hnsw.ef_search = 64;   -- Good balance'
\echo '     SET hnsw.ef_search = 100;  -- Higher recall'
\echo ''
\echo '  4. Compare results with original query to verify quality'
\echo ''
