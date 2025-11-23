-- Migration: Add source_metadata column to abstracts_checked
-- Description: Adds JSONB column to store complete source metadata for flexibility
-- Author: BMLibrarian
-- Date: 2025-11-23
-- Version: 016

-- Record this migration (idempotent - won't fail if re-run)
INSERT INTO public.schema_migrations (version, applied_at, description)
VALUES ('016_add_source_metadata_to_abstracts_checked', NOW(), 'PaperChecker: Add source_metadata JSONB column for flexible metadata storage')
ON CONFLICT (version) DO NOTHING;

-- ============================================================================
-- Add source_metadata column to abstracts_checked
-- ============================================================================

-- Add the column if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'papercheck'
        AND table_name = 'abstracts_checked'
        AND column_name = 'source_metadata'
    ) THEN
        ALTER TABLE papercheck.abstracts_checked
        ADD COLUMN source_metadata JSONB DEFAULT '{}'::jsonb;

        COMMENT ON COLUMN papercheck.abstracts_checked.source_metadata IS
            'Complete source metadata as JSONB for flexibility (complements individual source_* columns)';

        RAISE NOTICE 'Added source_metadata column to papercheck.abstracts_checked';
    ELSE
        RAISE NOTICE 'source_metadata column already exists in papercheck.abstracts_checked';
    END IF;
END $$;

-- ============================================================================
-- Migration Complete
-- ============================================================================

DO $$
BEGIN
    RAISE NOTICE 'Migration 016 completed: source_metadata column added to abstracts_checked';
END $$;
