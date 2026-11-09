-- Migration 036: list every settings category in v_user_complete_settings
--
-- Migration 030 extended the bmlsettings CHECK constraints to the thirteen
-- categories in config.py's VALID_SETTINGS_CATEGORIES, but the
-- v_user_complete_settings view (migration 012) still enumerated only the
-- original ten, so it never returned 'document_qa', 'discovery' or
-- 'embeddings' rows (issue #231). This migration recreates the view with the
-- full list. tests/test_settings_categories_sql_sync.py keeps the view and
-- both CHECK constraints in step with the Python constant.
--
-- Idempotent: CREATE OR REPLACE VIEW (same columns) runs safely any number
-- of times; skipped on databases without the bmlsettings schema. No
-- migration-tracking statements (handled by MigrationManager).

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'bmlsettings' AND table_name = 'user_settings'
    ) AND EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'bmlsettings' AND table_name = 'default_settings'
    ) THEN
        CREATE OR REPLACE VIEW bmlsettings.v_user_complete_settings AS
        SELECT
            u.id as user_id,
            u.username,
            cat.category,
            COALESCE(
                us.settings,
                ds.settings,
                '{}'::jsonb
            ) as settings,
            CASE WHEN us.settings IS NOT NULL THEN 'user' ELSE 'default' END as source
        FROM public.users u
        CROSS JOIN (
            SELECT unnest(ARRAY[
                'models', 'ollama', 'agents', 'database', 'search',
                'query_generation', 'gui', 'openathens', 'pdf', 'general',
                'document_qa', 'discovery', 'embeddings'
            ]) as category
        ) cat
        LEFT JOIN bmlsettings.user_settings us ON us.user_id = u.id AND us.category = cat.category
        LEFT JOIN bmlsettings.default_settings ds ON ds.category = cat.category;

        COMMENT ON VIEW bmlsettings.v_user_complete_settings IS
            'Complete settings for each user (user settings merged with defaults)';
    END IF;
END $$;
