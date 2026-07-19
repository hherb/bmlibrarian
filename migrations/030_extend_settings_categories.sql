-- Migration 030: Extend bmlsettings category whitelists
--
-- config.py's VALID_SETTINGS_CATEGORIES gained 'document_qa', 'discovery'
-- and 'embeddings', but the CHECK constraints created by migration 012 only
-- allowed the original ten categories, so syncing those three categories to
-- the database always failed. This migration replaces both CHECK
-- constraints with the full thirteen-category list.
--
-- Idempotent: DROP CONSTRAINT IF EXISTS + ADD runs safely any number of
-- times; guarded so it is a no-op on databases without the bmlsettings
-- schema. No migration-tracking statements (handled by MigrationManager).

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'bmlsettings' AND table_name = 'user_settings'
    ) THEN
        ALTER TABLE bmlsettings.user_settings
            DROP CONSTRAINT IF EXISTS user_settings_category_check;
        ALTER TABLE bmlsettings.user_settings
            ADD CONSTRAINT user_settings_category_check CHECK (category IN (
                'models',           -- Model assignments per agent
                'ollama',           -- Ollama server settings
                'agents',           -- Agent-specific parameters
                'database',         -- Database query settings
                'search',           -- Search settings
                'query_generation', -- Multi-model query settings
                'gui',              -- GUI-specific settings
                'openathens',       -- OpenAthens authentication settings
                'pdf',              -- PDF processing settings
                'general',          -- General/misc settings
                'document_qa',      -- Document interrogation settings
                'discovery',        -- Full-text PDF discovery settings
                'embeddings'        -- Document embedding settings
            ));
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'bmlsettings' AND table_name = 'default_settings'
    ) THEN
        ALTER TABLE bmlsettings.default_settings
            DROP CONSTRAINT IF EXISTS default_settings_category_check;
        ALTER TABLE bmlsettings.default_settings
            ADD CONSTRAINT default_settings_category_check CHECK (category IN (
                'models',
                'ollama',
                'agents',
                'database',
                'search',
                'query_generation',
                'gui',
                'openathens',
                'pdf',
                'general',
                'document_qa',
                'discovery',
                'embeddings'
            ));
    END IF;
END $$;
