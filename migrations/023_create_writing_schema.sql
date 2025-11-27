-- Migration: Create Writing Schema
-- Description: Schema for the citation-aware markdown editor with autosave and versioning
-- Author: BMLibrarian
-- Date: 2025-11-27
-- Version: 1.0.0
--
-- Purpose: Store documents being written/drafted with:
--          - Autosave functionality with version history
--          - Citation tracking
--          - User association for multi-user support

-- ============================================================================
-- Create writing schema
-- ============================================================================

BEGIN;

CREATE SCHEMA IF NOT EXISTS writing;

COMMENT ON SCHEMA writing IS 'Citation-aware markdown editor with autosave and versioning';

-- ============================================================================
-- 1. documents - Main document storage
-- ============================================================================

CREATE TABLE IF NOT EXISTS writing.documents (
    id SERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL DEFAULT 'Untitled Document',
    content TEXT NOT NULL DEFAULT '',
    metadata JSONB DEFAULT '{}',  -- Store settings, last cursor position, etc.
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    user_id INTEGER REFERENCES public.users(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_writing_documents_user
    ON writing.documents(user_id);
CREATE INDEX IF NOT EXISTS idx_writing_documents_updated
    ON writing.documents(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_writing_documents_title
    ON writing.documents(title);

COMMENT ON TABLE writing.documents IS 'Documents being written/drafted in the citation editor';
COMMENT ON COLUMN writing.documents.title IS 'Document title';
COMMENT ON COLUMN writing.documents.content IS 'Markdown content with citation markers';
COMMENT ON COLUMN writing.documents.metadata IS 'JSON object with editor state (cursor position, settings, etc.)';
COMMENT ON COLUMN writing.documents.user_id IS 'Optional user association for multi-user support';

-- ============================================================================
-- 2. document_versions - Autosave version history
-- ============================================================================

CREATE TABLE IF NOT EXISTS writing.document_versions (
    id SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES writing.documents(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    title VARCHAR(255),
    version_type VARCHAR(20) NOT NULL DEFAULT 'autosave',  -- 'autosave', 'manual', 'export'
    saved_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_version_type CHECK (version_type IN ('autosave', 'manual', 'export'))
);

CREATE INDEX IF NOT EXISTS idx_writing_versions_document
    ON writing.document_versions(document_id);
CREATE INDEX IF NOT EXISTS idx_writing_versions_saved
    ON writing.document_versions(document_id, saved_at DESC);
CREATE INDEX IF NOT EXISTS idx_writing_versions_type
    ON writing.document_versions(version_type);

COMMENT ON TABLE writing.document_versions IS 'Version history for autosave and manual saves';
COMMENT ON COLUMN writing.document_versions.version_type IS 'Type of save: autosave (automatic), manual (user-initiated), export (before export)';
COMMENT ON COLUMN writing.document_versions.content IS 'Full document content at time of save';
COMMENT ON COLUMN writing.document_versions.title IS 'Document title at time of save';

-- ============================================================================
-- Helper Functions
-- ============================================================================

-- Function to update the updated_at timestamp
CREATE OR REPLACE FUNCTION writing.update_document_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to auto-update timestamp
DROP TRIGGER IF EXISTS trg_document_updated ON writing.documents;
CREATE TRIGGER trg_document_updated
    BEFORE UPDATE ON writing.documents
    FOR EACH ROW
    EXECUTE FUNCTION writing.update_document_timestamp();

-- Function to cleanup old autosave versions (keep latest N per document)
CREATE OR REPLACE FUNCTION writing.cleanup_old_versions(
    p_document_id INTEGER,
    p_max_versions INTEGER DEFAULT 10
) RETURNS INTEGER AS $$
DECLARE
    v_deleted INTEGER := 0;
BEGIN
    -- Delete autosave versions beyond the max, keeping the most recent
    WITH ranked AS (
        SELECT id,
               ROW_NUMBER() OVER (ORDER BY saved_at DESC) as rn
        FROM writing.document_versions
        WHERE document_id = p_document_id
          AND version_type = 'autosave'
    )
    DELETE FROM writing.document_versions
    WHERE id IN (SELECT id FROM ranked WHERE rn > p_max_versions);

    GET DIAGNOSTICS v_deleted = ROW_COUNT;
    RETURN v_deleted;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION writing.cleanup_old_versions IS 'Delete old autosave versions, keeping the most recent N versions';

-- Function to get document with version count
CREATE OR REPLACE FUNCTION writing.get_document_summary(p_document_id INTEGER)
RETURNS TABLE (
    id INTEGER,
    title VARCHAR(255),
    content_length INTEGER,
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ,
    version_count BIGINT,
    last_autosave TIMESTAMPTZ
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        d.id,
        d.title,
        LENGTH(d.content)::INTEGER as content_length,
        d.created_at,
        d.updated_at,
        COUNT(v.id) as version_count,
        MAX(CASE WHEN v.version_type = 'autosave' THEN v.saved_at END) as last_autosave
    FROM writing.documents d
    LEFT JOIN writing.document_versions v ON d.id = v.document_id
    WHERE d.id = p_document_id
    GROUP BY d.id, d.title, d.content, d.created_at, d.updated_at;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION writing.get_document_summary IS 'Get document summary with version statistics';

-- ============================================================================
-- Views
-- ============================================================================

-- View: Recent documents with statistics
CREATE OR REPLACE VIEW writing.v_recent_documents AS
SELECT
    d.id,
    d.title,
    LENGTH(d.content) as content_length,
    d.created_at,
    d.updated_at,
    d.user_id,
    u.username,
    COUNT(v.id) as version_count,
    MAX(v.saved_at) as last_version_saved
FROM writing.documents d
LEFT JOIN public.users u ON d.user_id = u.id
LEFT JOIN writing.document_versions v ON d.id = v.document_id
GROUP BY d.id, d.title, d.content, d.created_at, d.updated_at, d.user_id, u.username
ORDER BY d.updated_at DESC;

COMMENT ON VIEW writing.v_recent_documents IS 'Recent documents with version statistics';

COMMIT;
