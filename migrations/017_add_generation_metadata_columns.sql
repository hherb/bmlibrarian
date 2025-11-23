-- Migration: Add generation_metadata columns to papercheck tables
-- Description: Adds JSONB generation_metadata columns to counter_statements and counter_reports
--              for flexible metadata storage (aligns database.py with schema)
-- Author: BMLibrarian
-- Date: 2025-11-23
-- Version: 017

-- Record this migration (idempotent - won't fail if re-run)
INSERT INTO public.schema_migrations (version, applied_at, description)
VALUES ('017_add_generation_metadata_columns', NOW(), 'PaperChecker: Add generation_metadata JSONB columns')
ON CONFLICT (version) DO NOTHING;

-- ============================================================================
-- Add generation_metadata column to counter_statements
-- ============================================================================

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'papercheck'
        AND table_name = 'counter_statements'
        AND column_name = 'generation_metadata'
    ) THEN
        ALTER TABLE papercheck.counter_statements
        ADD COLUMN generation_metadata JSONB DEFAULT '{}'::jsonb;

        COMMENT ON COLUMN papercheck.counter_statements.generation_metadata IS
            'Generation metadata as JSONB (model, config, timestamp)';

        RAISE NOTICE 'Added generation_metadata column to papercheck.counter_statements';
    ELSE
        RAISE NOTICE 'generation_metadata column already exists in papercheck.counter_statements';
    END IF;
END $$;

-- ============================================================================
-- Add generation_metadata column to counter_reports (if missing)
-- ============================================================================

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'papercheck'
        AND table_name = 'counter_reports'
        AND column_name = 'generation_metadata'
    ) THEN
        ALTER TABLE papercheck.counter_reports
        ADD COLUMN generation_metadata JSONB DEFAULT '{}'::jsonb;

        COMMENT ON COLUMN papercheck.counter_reports.generation_metadata IS
            'Generation metadata as JSONB (model, config, timestamp)';

        RAISE NOTICE 'Added generation_metadata column to papercheck.counter_reports';
    ELSE
        RAISE NOTICE 'generation_metadata column already exists in papercheck.counter_reports';
    END IF;
END $$;

-- ============================================================================
-- Add search_stats column to counter_reports (if missing)
-- ============================================================================

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'papercheck'
        AND table_name = 'counter_reports'
        AND column_name = 'search_stats'
    ) THEN
        ALTER TABLE papercheck.counter_reports
        ADD COLUMN search_stats JSONB DEFAULT '{}'::jsonb;

        COMMENT ON COLUMN papercheck.counter_reports.search_stats IS
            'Search statistics as JSONB (counts by strategy, deduplication stats)';

        RAISE NOTICE 'Added search_stats column to papercheck.counter_reports';
    ELSE
        RAISE NOTICE 'search_stats column already exists in papercheck.counter_reports';
    END IF;
END $$;

-- ============================================================================
-- Add analysis_metadata column to verdicts (if missing)
-- ============================================================================

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'papercheck'
        AND table_name = 'verdicts'
        AND column_name = 'analysis_metadata'
    ) THEN
        ALTER TABLE papercheck.verdicts
        ADD COLUMN analysis_metadata JSONB DEFAULT '{}'::jsonb;

        COMMENT ON COLUMN papercheck.verdicts.analysis_metadata IS
            'Analysis metadata as JSONB (model, config, evidence summary)';

        RAISE NOTICE 'Added analysis_metadata column to papercheck.verdicts';
    ELSE
        RAISE NOTICE 'analysis_metadata column already exists in papercheck.verdicts';
    END IF;
END $$;

-- ============================================================================
-- Migration Complete
-- ============================================================================

DO $$
BEGIN
    RAISE NOTICE 'Migration 017 completed: generation_metadata and related JSONB columns added';
END $$;
