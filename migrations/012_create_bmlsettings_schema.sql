-- Migration: Create BMLibrarian User Settings Schema
-- Description: Per-user settings storage with database-backed configuration
-- Author: BMLibrarian
-- Date: 2025-11-22
-- Version: 1.0.0

-- ============================================================================
-- Create bmlsettings schema
-- ============================================================================

BEGIN;

CREATE SCHEMA IF NOT EXISTS bmlsettings;

COMMENT ON SCHEMA bmlsettings IS 'BMLibrarian: Per-user settings storage for multi-user support';

-- ============================================================================
-- 1. user_settings - Main settings table with JSONB for flexible storage
-- ============================================================================

CREATE TABLE bmlsettings.user_settings (
    setting_id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,

    -- Settings category (maps to config.json top-level keys)
    category TEXT NOT NULL CHECK (category IN (
        'models',           -- Model assignments per agent
        'ollama',           -- Ollama server settings
        'agents',           -- Agent-specific parameters
        'database',         -- Database query settings
        'search',           -- Search settings
        'query_generation', -- Multi-model query settings
        'gui',              -- GUI-specific settings
        'openathens',       -- OpenAthens authentication settings
        'pdf',              -- PDF processing settings
        'general'           -- General/misc settings
    )),

    -- JSONB for flexible settings storage
    -- This allows schema evolution without migrations
    settings JSONB NOT NULL DEFAULT '{}'::jsonb,

    -- Metadata
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),

    -- One settings record per user per category
    UNIQUE(user_id, category)
);

-- Indexes for efficient lookups
CREATE INDEX idx_user_settings_user ON bmlsettings.user_settings(user_id);
CREATE INDEX idx_user_settings_category ON bmlsettings.user_settings(category);
CREATE INDEX idx_user_settings_settings ON bmlsettings.user_settings USING GIN(settings);

COMMENT ON TABLE bmlsettings.user_settings IS 'Per-user configuration settings organized by category';
COMMENT ON COLUMN bmlsettings.user_settings.setting_id IS 'Unique identifier for this setting record';
COMMENT ON COLUMN bmlsettings.user_settings.user_id IS 'Reference to the user who owns these settings';
COMMENT ON COLUMN bmlsettings.user_settings.category IS 'Settings category (models, ollama, agents, etc.)';
COMMENT ON COLUMN bmlsettings.user_settings.settings IS 'JSONB containing the actual settings for this category';
COMMENT ON COLUMN bmlsettings.user_settings.created_at IS 'When this setting record was created';
COMMENT ON COLUMN bmlsettings.user_settings.updated_at IS 'When this setting record was last updated';

-- ============================================================================
-- 2. user_sessions - Track active user sessions
-- ============================================================================

CREATE TABLE bmlsettings.user_sessions (
    session_id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,

    -- Session token for authentication
    session_token TEXT NOT NULL UNIQUE,

    -- Session metadata
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMP NOT NULL,
    last_active TIMESTAMP NOT NULL DEFAULT NOW(),

    -- Client information
    client_type TEXT CHECK (client_type IN ('qt_gui', 'flet_gui', 'cli', 'api')),
    client_version TEXT,
    hostname TEXT
);

-- Indexes for session lookups
CREATE INDEX idx_sessions_user ON bmlsettings.user_sessions(user_id);
CREATE INDEX idx_sessions_token ON bmlsettings.user_sessions(session_token);
CREATE INDEX idx_sessions_expires ON bmlsettings.user_sessions(expires_at);

COMMENT ON TABLE bmlsettings.user_sessions IS 'Active user sessions for authentication';
COMMENT ON COLUMN bmlsettings.user_sessions.session_id IS 'Unique identifier for this session';
COMMENT ON COLUMN bmlsettings.user_sessions.user_id IS 'Reference to the authenticated user';
COMMENT ON COLUMN bmlsettings.user_sessions.session_token IS 'Unique session token for authentication';
COMMENT ON COLUMN bmlsettings.user_sessions.created_at IS 'When this session was created';
COMMENT ON COLUMN bmlsettings.user_sessions.expires_at IS 'When this session expires';
COMMENT ON COLUMN bmlsettings.user_sessions.last_active IS 'Last activity timestamp';
COMMENT ON COLUMN bmlsettings.user_sessions.client_type IS 'Type of client (qt_gui, flet_gui, cli, api)';

-- ============================================================================
-- 3. default_settings - System-wide default settings
-- ============================================================================

CREATE TABLE bmlsettings.default_settings (
    default_id SERIAL PRIMARY KEY,

    -- Settings category
    category TEXT NOT NULL CHECK (category IN (
        'models', 'ollama', 'agents', 'database', 'search',
        'query_generation', 'gui', 'openathens', 'pdf', 'general'
    )),

    -- Default settings (JSONB)
    settings JSONB NOT NULL DEFAULT '{}'::jsonb,

    -- Metadata
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_by INTEGER REFERENCES public.users(id),

    -- One default per category
    UNIQUE(category)
);

CREATE INDEX idx_default_settings_category ON bmlsettings.default_settings(category);

COMMENT ON TABLE bmlsettings.default_settings IS 'System-wide default settings that apply when user has no custom settings';
COMMENT ON COLUMN bmlsettings.default_settings.category IS 'Settings category';
COMMENT ON COLUMN bmlsettings.default_settings.settings IS 'Default JSONB settings for this category';
COMMENT ON COLUMN bmlsettings.default_settings.updated_by IS 'Admin user who last updated these defaults';

-- ============================================================================
-- 4. Trigger for automatic updated_at timestamp
-- ============================================================================

CREATE OR REPLACE FUNCTION bmlsettings.update_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER user_settings_updated
    BEFORE UPDATE ON bmlsettings.user_settings
    FOR EACH ROW
    EXECUTE FUNCTION bmlsettings.update_timestamp();

CREATE TRIGGER default_settings_updated
    BEFORE UPDATE ON bmlsettings.default_settings
    FOR EACH ROW
    EXECUTE FUNCTION bmlsettings.update_timestamp();

-- ============================================================================
-- Views for Convenient Access
-- ============================================================================

-- View: Complete user settings (merged with defaults)
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
        'query_generation', 'gui', 'openathens', 'pdf', 'general'
    ]) as category
) cat
LEFT JOIN bmlsettings.user_settings us ON us.user_id = u.id AND us.category = cat.category
LEFT JOIN bmlsettings.default_settings ds ON ds.category = cat.category;

COMMENT ON VIEW bmlsettings.v_user_complete_settings IS 'Complete settings for each user (user settings merged with defaults)';

-- View: Active sessions (non-expired)
CREATE OR REPLACE VIEW bmlsettings.v_active_sessions AS
SELECT
    s.session_id,
    s.user_id,
    u.username,
    s.session_token,
    s.created_at,
    s.expires_at,
    s.last_active,
    s.client_type,
    s.client_version,
    s.hostname
FROM bmlsettings.user_sessions s
JOIN public.users u ON u.id = s.user_id
WHERE s.expires_at > NOW();

COMMENT ON VIEW bmlsettings.v_active_sessions IS 'Currently active (non-expired) user sessions';

-- ============================================================================
-- Utility Functions
-- ============================================================================

-- Function: Get user settings for a category (with fallback to defaults)
CREATE OR REPLACE FUNCTION bmlsettings.get_user_settings(
    p_user_id INTEGER,
    p_category TEXT
)
RETURNS JSONB AS $$
DECLARE
    v_settings JSONB;
BEGIN
    -- Validate inputs
    IF p_user_id IS NULL OR p_user_id <= 0 THEN
        RAISE EXCEPTION 'Invalid user_id: %', p_user_id;
    END IF;

    IF p_category IS NULL OR p_category = '' THEN
        RAISE EXCEPTION 'Category cannot be NULL or empty';
    END IF;

    -- Try to get user-specific settings
    SELECT settings INTO v_settings
    FROM bmlsettings.user_settings
    WHERE user_id = p_user_id AND category = p_category;

    -- Fall back to defaults if no user settings
    IF v_settings IS NULL THEN
        SELECT settings INTO v_settings
        FROM bmlsettings.default_settings
        WHERE category = p_category;
    END IF;

    -- Return empty object if no settings found
    RETURN COALESCE(v_settings, '{}'::jsonb);
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION bmlsettings.get_user_settings(INTEGER, TEXT) IS 'Get settings for a user and category (falls back to defaults)';

-- Function: Get all user settings as single JSONB object
CREATE OR REPLACE FUNCTION bmlsettings.get_all_user_settings(p_user_id INTEGER)
RETURNS JSONB AS $$
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
            'query_generation', 'gui', 'openathens', 'pdf', 'general'
        ])
    LOOP
        v_settings := bmlsettings.get_user_settings(p_user_id, v_category);
        IF v_settings != '{}'::jsonb THEN
            v_result := v_result || jsonb_build_object(v_category, v_settings);
        END IF;
    END LOOP;

    RETURN v_result;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION bmlsettings.get_all_user_settings(INTEGER) IS 'Get all settings for a user as a single JSONB object';

-- Function: Save user settings for a category
CREATE OR REPLACE FUNCTION bmlsettings.save_user_settings(
    p_user_id INTEGER,
    p_category TEXT,
    p_settings JSONB
)
RETURNS BOOLEAN AS $$
BEGIN
    -- Validate inputs
    IF p_user_id IS NULL OR p_user_id <= 0 THEN
        RAISE EXCEPTION 'Invalid user_id: %', p_user_id;
    END IF;

    IF p_category IS NULL OR p_category = '' THEN
        RAISE EXCEPTION 'Category cannot be NULL or empty';
    END IF;

    -- Upsert the settings
    INSERT INTO bmlsettings.user_settings (user_id, category, settings)
    VALUES (p_user_id, p_category, COALESCE(p_settings, '{}'::jsonb))
    ON CONFLICT (user_id, category)
    DO UPDATE SET settings = COALESCE(EXCLUDED.settings, '{}'::jsonb);

    RETURN TRUE;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION bmlsettings.save_user_settings(INTEGER, TEXT, JSONB) IS 'Save settings for a user and category (upsert)';

-- Function: Create a new session
CREATE OR REPLACE FUNCTION bmlsettings.create_session(
    p_user_id INTEGER,
    p_client_type TEXT DEFAULT 'qt_gui',
    p_client_version TEXT DEFAULT NULL,
    p_hostname TEXT DEFAULT NULL,
    p_duration_hours INTEGER DEFAULT 24
)
RETURNS TEXT AS $$
DECLARE
    v_token TEXT;
BEGIN
    -- Validate input
    IF p_user_id IS NULL OR p_user_id <= 0 THEN
        RAISE EXCEPTION 'Invalid user_id: %', p_user_id;
    END IF;

    -- Generate secure session token
    v_token := encode(gen_random_bytes(32), 'hex');

    -- Insert session
    INSERT INTO bmlsettings.user_sessions (
        user_id, session_token, expires_at, client_type, client_version, hostname
    ) VALUES (
        p_user_id,
        v_token,
        NOW() + (p_duration_hours || ' hours')::INTERVAL,
        p_client_type,
        p_client_version,
        p_hostname
    );

    RETURN v_token;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION bmlsettings.create_session(INTEGER, TEXT, TEXT, TEXT, INTEGER) IS 'Create a new session for a user, returns session token';

-- Function: Validate session and update last_active
CREATE OR REPLACE FUNCTION bmlsettings.validate_session(p_session_token TEXT)
RETURNS INTEGER AS $$
DECLARE
    v_user_id INTEGER;
BEGIN
    -- Update last_active and return user_id if valid
    UPDATE bmlsettings.user_sessions
    SET last_active = NOW()
    WHERE session_token = p_session_token
      AND expires_at > NOW()
    RETURNING user_id INTO v_user_id;

    RETURN v_user_id;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION bmlsettings.validate_session(TEXT) IS 'Validate a session token and return user_id (NULL if invalid/expired)';

-- Function: Delete expired sessions (cleanup)
CREATE OR REPLACE FUNCTION bmlsettings.cleanup_expired_sessions()
RETURNS INTEGER AS $$
DECLARE
    v_deleted INTEGER;
BEGIN
    DELETE FROM bmlsettings.user_sessions
    WHERE expires_at < NOW();

    GET DIAGNOSTICS v_deleted = ROW_COUNT;
    RETURN v_deleted;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION bmlsettings.cleanup_expired_sessions() IS 'Delete expired sessions and return count of deleted sessions';

-- ============================================================================
-- Insert Default Settings
-- ============================================================================

-- Models defaults
INSERT INTO bmlsettings.default_settings (category, settings) VALUES
('models', '{
    "query_agent": "medgemma4B_it_q8:latest",
    "scoring_agent": "medgemma4B_it_q8:latest",
    "citation_agent": "medgemma-27b-text-it-Q8_0:latest",
    "reporting_agent": "gpt-oss:20b",
    "counterfactual_agent": "medgemma-27b-text-it-Q8_0:latest",
    "fact_checker_agent": "gpt-oss:20b",
    "pico_agent": "gpt-oss:20b",
    "study_assessment_agent": "gpt-oss:20b",
    "paper_weight_assessment_agent": "gpt-oss:20b",
    "fast_model": "medgemma4B_it_q8:latest",
    "complex_model": "gpt-oss:20b",
    "medical_model": "medgemma-27b-text-it-Q8_0:latest"
}'::jsonb);

-- Ollama defaults
INSERT INTO bmlsettings.default_settings (category, settings) VALUES
('ollama', '{
    "host": "http://localhost:11434",
    "timeout": 120,
    "max_retries": 3
}'::jsonb);

-- Agent defaults
INSERT INTO bmlsettings.default_settings (category, settings) VALUES
('agents', '{
    "query": {"temperature": 0.1, "top_p": 0.9, "max_tokens": 1000},
    "scoring": {"temperature": 0.1, "top_p": 0.9, "max_tokens": 1000, "min_relevance_score": 3},
    "citation": {"temperature": 0.2, "top_p": 0.9, "max_tokens": 1000, "min_relevance": 0.7},
    "reporting": {"temperature": 0.1, "top_p": 0.9, "max_tokens": 3000},
    "counterfactual": {"temperature": 0.2, "top_p": 0.9, "max_tokens": 4000, "retry_attempts": 3}
}'::jsonb);

-- Database defaults
INSERT INTO bmlsettings.default_settings (category, settings) VALUES
('database', '{
    "max_results_per_query": 10,
    "batch_size": 50,
    "use_ranking": false
}'::jsonb);

-- Search defaults
INSERT INTO bmlsettings.default_settings (category, settings) VALUES
('search', '{
    "max_results": 100,
    "score_threshold": 2.5,
    "max_documents_to_score": null,
    "max_documents_for_citations": null,
    "counterfactual_max_results": 10,
    "counterfactual_min_score": 3,
    "query_retry_attempts": 3,
    "auto_fix_tsquery_syntax": true,
    "min_relevant": 10,
    "max_retry": 3,
    "batch_size": 100
}'::jsonb);

-- Query generation defaults
INSERT INTO bmlsettings.default_settings (category, settings) VALUES
('query_generation', '{
    "multi_model_enabled": false,
    "models": ["medgemma-27b-text-it-Q8_0:latest"],
    "queries_per_model": 1,
    "execution_mode": "serial",
    "deduplicate_results": true,
    "show_all_queries_to_user": true,
    "allow_query_selection": true
}'::jsonb);

-- GUI defaults
INSERT INTO bmlsettings.default_settings (category, settings) VALUES
('gui', '{
    "theme": "default",
    "window": {"width": 1400, "height": 900, "remember_geometry": true}
}'::jsonb);

-- PDF defaults
INSERT INTO bmlsettings.default_settings (category, settings) VALUES
('pdf', '{
    "base_dir": "~/knowledgebase/pdf"
}'::jsonb);

-- General defaults (empty for now)
INSERT INTO bmlsettings.default_settings (category, settings) VALUES
('general', '{}'::jsonb);

-- OpenAthens defaults (empty - requires manual configuration)
INSERT INTO bmlsettings.default_settings (category, settings) VALUES
('openathens', '{
    "enabled": false
}'::jsonb);

-- ============================================================================
-- Migration Complete
-- ============================================================================

COMMIT;

-- Log successful migration
DO $$
BEGIN
    RAISE NOTICE 'BMLibrarian Settings schema migration completed successfully';
    RAISE NOTICE 'Created schema: bmlsettings';
    RAISE NOTICE 'Created tables: 3 (user_settings, user_sessions, default_settings)';
    RAISE NOTICE 'Created views: 2';
    RAISE NOTICE 'Created functions: 7';
    RAISE NOTICE 'Inserted default settings for all categories';
END $$;
