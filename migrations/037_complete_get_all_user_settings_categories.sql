-- Migration 037: list every settings category in get_all_user_settings()
--
-- bmlsettings.get_all_user_settings() (migration 012) loops over its own
-- hard-coded category array, which still held only the original ten. It is
-- what UserSettingsManager.get_all() calls, so per-user 'document_qa',
-- 'discovery' and 'embeddings' settings were saved (030 extended the CHECK
-- constraints) but never loaded back (issue #231). This migration recreates
-- the function with all thirteen categories; body otherwise unchanged.
-- tests/test_settings_categories_sql_sync.py keeps this list in step with
-- config.VALID_SETTINGS_CATEGORIES.
--
-- Idempotent: CREATE OR REPLACE FUNCTION (same signature and return type)
-- runs safely any number of times; skipped on databases without the
-- bmlsettings schema. No migration-tracking statements (handled by
-- MigrationManager).

DO $$
BEGIN
    IF to_regprocedure('bmlsettings.get_user_settings(integer, text)') IS NOT NULL THEN
        CREATE OR REPLACE FUNCTION bmlsettings.get_all_user_settings(p_user_id INTEGER)
        RETURNS JSONB AS $fn$
        DECLARE
            v_result JSONB := '{}'::jsonb;
            v_category TEXT;
            v_settings JSONB;
        BEGIN
            -- Validate input
            IF p_user_id IS NULL OR p_user_id <= 0 THEN
                RAISE EXCEPTION 'Invalid user_id: %', p_user_id;
            END IF;

            -- Iterate over all categories
            FOR v_category IN
                SELECT unnest(ARRAY[
                    'models', 'ollama', 'agents', 'database', 'search',
                    'query_generation', 'gui', 'openathens', 'pdf', 'general',
                    'document_qa', 'discovery', 'embeddings'
                ])
            LOOP
                v_settings := bmlsettings.get_user_settings(p_user_id, v_category);
                IF v_settings != '{}'::jsonb THEN
                    v_result := v_result || jsonb_build_object(v_category, v_settings);
                END IF;
            END LOOP;

            RETURN v_result;
        END;
        $fn$ LANGUAGE plpgsql;

        COMMENT ON FUNCTION bmlsettings.get_all_user_settings(INTEGER) IS
            'Get all settings for a user as a single JSONB object';
    END IF;
END $$;
