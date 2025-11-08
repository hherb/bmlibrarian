-- Switch to IVFFlat Index (faster build, smaller size)
-- Alternative to HNSW if you need a quicker solution

-- ============================================================================
-- IVFFlat vs HNSW Comparison
-- ============================================================================

-- HNSW (current):
--   - Size: 206 GB (m=6) or ~412 GB (m=12)
--   - Build time: 2-4 hours (m=12) or 4-8 hours (m=24)
--   - Query time: 263s (m=6) or ~30-60s (m=12)
--   - Best recall: Excellent with proper m value

-- IVFFlat (alternative):
--   - Size: 50-100 GB (much smaller)
--   - Build time: 30-60 minutes (much faster)
--   - Query time: ~10-30s (good but not as fast as HNSW m=12+)
--   - Recall: Good (adjustable with probes parameter)

-- ============================================================================
-- STEP 1: Drop Old HNSW Index
-- ============================================================================

\echo 'Dropping old HNSW index...'
DROP INDEX IF EXISTS arctic_hnsw_idx_v2;
DROP INDEX IF EXISTS arctic_hnsw_idx_v3;

-- ============================================================================
-- STEP 2: Create IVFFlat Index
-- ============================================================================

-- lists = 5000: Number of Voronoi cells (clusters)
--   Rule of thumb: sqrt(rows) ≈ sqrt(37M) ≈ 6000
--   5000 is a good compromise for speed vs accuracy

\echo 'Creating IVFFlat index...'
\echo 'This will take 30-60 minutes (much faster than HNSW)'

\timing on

CREATE INDEX arctic_ivfflat_idx ON emb_1024
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 5000);

\timing off

\echo 'Index creation complete!'

-- ============================================================================
-- STEP 3: Set Query-time Parameter
-- ============================================================================

-- probes: Number of lists to search (higher = better recall, slower)
-- Default: 1 (too low for good recall)
-- Recommended: 10-50 for good balance

\echo ''
\echo 'Setting optimal query parameter...'
\echo 'probes=50 means search 50 of 5000 lists (1% of total)'

-- This is set per session
SET ivfflat.probes = 50;

-- To make it permanent, add to postgresql.conf:
-- ivfflat.probes = 50

-- ============================================================================
-- STEP 4: Verify Index
-- ============================================================================

-- Check index size
SELECT
    indexname,
    pg_size_pretty(pg_relation_size(indexname::regclass)) as size
FROM pg_indexes
WHERE tablename = 'emb_1024' AND indexname LIKE '%ivf%';

-- Check statistics
SELECT
    schemaname,
    tablename,
    indexname,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch
FROM pg_stat_user_indexes
WHERE tablename = 'emb_1024';

-- ============================================================================
-- STEP 5: Test Performance
-- ============================================================================

\echo ''
\echo 'Test with different probe values to find optimal setting:'
\echo '  SET ivfflat.probes = 10;   -- Faster, lower recall'
\echo '  SET ivfflat.probes = 50;   -- Balanced (recommended)'
\echo '  SET ivfflat.probes = 100;  -- Slower, higher recall'
\echo ''
\echo 'Then run: uv run python semantic_search.py "your query"'

-- ============================================================================
-- STEP 6: Maintenance
-- ============================================================================

VACUUM ANALYZE emb_1024;

-- ============================================================================
-- Usage Notes
-- ============================================================================

\echo ''
\echo '============================================================================'
\echo 'IVFFlat INDEX SETUP COMPLETE'
\echo '============================================================================'
\echo ''
\echo 'Expected performance:'
\echo '  - Index size: ~50-100 GB (vs 206 GB HNSW m=6)'
\echo '  - Query time: ~10-30s (vs 263s with HNSW m=6)'
\echo '  - Build time: 30-60 min (vs 2-4 hours for HNSW m=12)'
\echo ''
\echo 'Query-time tuning:'
\echo '  - SET ivfflat.probes = 50;  -- Recommended starting point'
\echo '  - Higher probes = better recall but slower'
\echo '  - Lower probes = faster but may miss results'
\echo ''
\echo 'When to use IVFFlat vs HNSW:'
\echo '  - IVFFlat: Faster build, smaller size, good enough performance'
\echo '  - HNSW: Best query performance but larger and slower to build'
\echo ''
\echo 'Next steps:'
\echo '  1. Test with semantic_search.py'
\echo '  2. Experiment with different probe values (10, 50, 100)'
\echo '  3. Compare recall quality and speed'
\echo ''
