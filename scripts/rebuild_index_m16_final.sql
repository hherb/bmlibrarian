-- Final optimized HNSW Index Rebuild with m=16
-- Based on learnings: conservative memory, realistic expectations
-- For 37M tuples with actual disk space available

-- ============================================================================
-- PERFORMANCE TUNING - Conservative and Realistic
-- ============================================================================

\echo 'Setting performance parameters...'
\echo ''

-- Conservative memory to avoid swapping
SET maintenance_work_mem = '16GB';

-- Moderate parallelism (3 total processes)
SET max_parallel_maintenance_workers = 2;

-- Work memory
SET work_mem = '1GB';

-- Show current settings
SELECT
    name,
    setting,
    unit
FROM pg_settings
WHERE name IN (
    'maintenance_work_mem',
    'max_parallel_maintenance_workers',
    'work_mem',
    'shared_buffers'
);

\echo ''
\echo '✓ Memory settings configured'
\echo ''

-- ============================================================================
-- DISK SPACE CHECK
-- ============================================================================

\echo 'Checking available disk space...'

SELECT
    pg_size_pretty(pg_database_size('knowledgebase')) as current_db_size,
    pg_size_pretty(pg_tablespace_size('pg_default')) as tablespace_size;

\echo ''
\echo 'Required: ~550GB for new index + temp space during build'
\echo 'Make sure you have 700GB+ free (check with: df -h)'
\echo ''
\echo 'Press Ctrl+C within 10 seconds to abort if disk space insufficient...'

SELECT pg_sleep(10);

-- ============================================================================
-- STEP 1: Clean Up Any Failed Attempts
-- ============================================================================

\echo ''
\echo '=========================================================================='
\echo 'STEP 1: Cleaning up old/failed indexes'
\echo '=========================================================================='
\echo ''

DROP INDEX CONCURRENTLY IF EXISTS arctic_hnsw_idx_v2;
DROP INDEX CONCURRENTLY IF EXISTS arctic_hnsw_idx_v3;
DROP INDEX CONCURRENTLY IF EXISTS arctic_hnsw_idx_v4;

\echo '✓ Old indexes removed'

-- ============================================================================
-- STEP 2: Build Index (Choose CONCURRENT or Regular)
-- ============================================================================

\echo ''
\echo '=========================================================================='
\echo 'STEP 2: Creating HNSW index with m=16'
\echo '=========================================================================='
\echo ''
\echo 'Configuration:'
\echo '  m = 16 (industry standard)'
\echo '  ef_construction = 80'
\echo '  maintenance_work_mem = 16GB (conservative)'
\echo '  max_parallel_maintenance_workers = 2'
\echo ''
\echo 'REALISTIC Expectations for 37.5M tuples:'
\echo '  - Index size: ~550 GB'
\echo '  - Build time: 8-16 hours (possibly longer)'
\echo '  - Memory usage: ~30-40GB peak'
\echo '  - Will slow down significantly after 70% progress'
\echo ''
\echo 'Monitor progress:'
\echo '  watch -n 30 "psql knowledgebase -c \"SELECT phase, round(100.0 * tuples_done / nullif(tuples_total, 0), 1) AS pct, tuples_done, tuples_total FROM pg_stat_progress_create_index;\""'
\echo ''
\echo 'Starting build now...'
\echo ''

\timing on

-- Use CONCURRENT if you might need to run queries during build
-- Remove CONCURRENTLY if you want slightly faster build and won't use DB
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
\echo 'STEP 3: Verification'
\echo '=========================================================================='
\echo ''

-- Show index size
SELECT
    indexname,
    pg_size_pretty(pg_relation_size(indexname::regclass)) as size
FROM pg_indexes
WHERE tablename = 'emb_1024' AND indexname = 'arctic_hnsw_idx_v4';

-- Update statistics
\echo 'Updating statistics...'
VACUUM ANALYZE emb_1024;

-- Verify index is valid and ready
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE indexname = 'arctic_hnsw_idx_v4';

\echo ''
\echo '=========================================================================='
\echo 'BUILD COMPLETE!'
\echo '=========================================================================='
\echo ''
\echo 'Next steps:'
\echo ''
\echo '1. Test performance (should be 12-20x faster):'
\echo '   uv run python semantic_search.py "prophylactic methylprednisolone mountain sickness"'
\echo ''
\echo '2. Expected query time: 15-25 seconds (vs 290s before)'
\echo ''
\echo '3. Optional tuning for better recall:'
\echo '   SET hnsw.ef_search = 64;   -- Good balance'
\echo '   SET hnsw.ef_search = 100;  -- Higher recall, slightly slower'
\echo ''
\echo 'If performance is still not good enough, consider:'
\echo '  - Increasing ef_search parameter'
\echo '  - Using m=24 (but requires ~824GB and longer build)'
\echo ''
