-- Verification script for thesaurus schema migration
-- Run this after executing migration 021_create_thesaurus_schema.sql

-- ============================================================================
-- Verify schema exists
-- ============================================================================

SELECT
    schema_name,
    schema_owner
FROM information_schema.schemata
WHERE schema_name = 'thesaurus';

-- ============================================================================
-- Verify tables exist
-- ============================================================================

SELECT
    table_name,
    table_type
FROM information_schema.tables
WHERE table_schema = 'thesaurus'
ORDER BY table_name;

-- ============================================================================
-- Verify table row counts (should all be 0 initially)
-- ============================================================================

SELECT
    'concepts' AS table_name,
    COUNT(*) AS row_count
FROM thesaurus.concepts
UNION ALL
SELECT
    'terms' AS table_name,
    COUNT(*) AS row_count
FROM thesaurus.terms
UNION ALL
SELECT
    'concept_hierarchies' AS table_name,
    COUNT(*) AS row_count
FROM thesaurus.concept_hierarchies
UNION ALL
SELECT
    'import_history' AS table_name,
    COUNT(*) AS row_count
FROM thesaurus.import_history;

-- ============================================================================
-- Verify indexes exist
-- ============================================================================

SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'thesaurus'
ORDER BY tablename, indexname;

-- ============================================================================
-- Verify functions exist
-- ============================================================================

SELECT
    routine_name,
    routine_type,
    data_type AS return_type
FROM information_schema.routines
WHERE routine_schema = 'thesaurus'
ORDER BY routine_name;

-- ============================================================================
-- Test utility functions (should return 0 rows with empty database)
-- ============================================================================

-- Test get_all_synonyms
SELECT * FROM thesaurus.get_all_synonyms('test');

-- Test expand_term
SELECT * FROM thesaurus.expand_term('test');

-- Test get_broader_terms
SELECT * FROM thesaurus.get_broader_terms('test');

-- Test get_narrower_terms
SELECT * FROM thesaurus.get_narrower_terms('test');

-- Test search_concepts
SELECT * FROM thesaurus.search_concepts('test');

-- ============================================================================
-- Summary
-- ============================================================================

SELECT 'Thesaurus schema verification complete!' AS status;
