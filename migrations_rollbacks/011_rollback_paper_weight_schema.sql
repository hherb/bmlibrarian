-- Rollback: Paper Weight Assessment Schema
-- Description: Removes the paper_weights schema and all its objects
-- Author: BMLibrarian
-- Date: 2025-11-21
-- Version: 1.0.0
--
-- WARNING: This will permanently delete all paper weight assessment data!
-- Make sure to backup any important data before running this script.

BEGIN;

-- Drop functions first (they depend on tables)
DROP FUNCTION IF EXISTS paper_weights.calculate_replication_score(INTEGER) CASCADE;
DROP FUNCTION IF EXISTS paper_weights.get_replication_status(INTEGER) CASCADE;
DROP FUNCTION IF EXISTS paper_weights.get_complete_assessment(INTEGER, TEXT) CASCADE;

-- Drop views (they depend on tables)
DROP VIEW IF EXISTS paper_weights.v_dimension_breakdown CASCADE;
DROP VIEW IF EXISTS paper_weights.v_assessments_with_replications CASCADE;
DROP VIEW IF EXISTS paper_weights.v_latest_assessments CASCADE;

-- Drop tables (order matters for foreign key dependencies)
DROP TABLE IF EXISTS paper_weights.assessment_details CASCADE;
DROP TABLE IF EXISTS paper_weights.replications CASCADE;
DROP TABLE IF EXISTS paper_weights.assessments CASCADE;

-- Drop schema
DROP SCHEMA IF EXISTS paper_weights CASCADE;

COMMIT;

-- Log successful rollback
DO $$
BEGIN
    RAISE NOTICE 'Paper Weight Assessment schema rollback completed successfully';
    RAISE NOTICE 'Dropped schema: paper_weights';
    RAISE NOTICE 'Dropped tables: 3';
    RAISE NOTICE 'Dropped views: 3';
    RAISE NOTICE 'Dropped functions: 3';
END $$;
