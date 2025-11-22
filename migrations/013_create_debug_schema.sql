-- Migration: Create Debug Schema for PDF Conversion Tracking
-- Description: Track PDF conversion attempts with quality ratings for testing different approaches
-- Author: BMLibrarian
-- Date: 2025-11-22
-- Version: 1.0.0

-- ============================================================================
-- Create debug schema
-- ============================================================================

BEGIN;

CREATE SCHEMA IF NOT EXISTS debug;

COMMENT ON SCHEMA debug IS 'BMLibrarian: Debug and development tracking tables';

-- ============================================================================
-- 1. pdf_conversions - Track PDF to markdown conversion attempts
-- ============================================================================

CREATE TABLE debug.pdf_conversions (
    id SERIAL PRIMARY KEY,

    -- PDF file information
    pdf_path TEXT NOT NULL,
    pdf_filename TEXT NOT NULL,

    -- Conversion strategy used
    conversion_strategy TEXT NOT NULL DEFAULT 'pymupdf4llm',

    -- Strategy options (JSONB for flexibility)
    strategy_options JSONB NOT NULL DEFAULT '{}'::jsonb,

    -- Quality rating: good, acceptable, fail
    rating TEXT NOT NULL CHECK (rating IN ('good', 'acceptable', 'fail')),

    -- Optional user comment (max 2 lines)
    comment TEXT CHECK (char_length(comment) <= 500),

    -- Metadata
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Indexes for efficient lookups
CREATE INDEX idx_pdf_conversions_path ON debug.pdf_conversions(pdf_path);
CREATE INDEX idx_pdf_conversions_filename ON debug.pdf_conversions(pdf_filename);
CREATE INDEX idx_pdf_conversions_rating ON debug.pdf_conversions(rating);
CREATE INDEX idx_pdf_conversions_strategy ON debug.pdf_conversions(conversion_strategy);
CREATE INDEX idx_pdf_conversions_created ON debug.pdf_conversions(created_at);

-- Comments
COMMENT ON TABLE debug.pdf_conversions IS 'Track PDF conversion attempts with quality ratings for testing different approaches';
COMMENT ON COLUMN debug.pdf_conversions.id IS 'Unique identifier for this conversion record';
COMMENT ON COLUMN debug.pdf_conversions.pdf_path IS 'Full path to the PDF file';
COMMENT ON COLUMN debug.pdf_conversions.pdf_filename IS 'Filename of the PDF (without path)';
COMMENT ON COLUMN debug.pdf_conversions.conversion_strategy IS 'Name of the conversion strategy used (e.g., pymupdf4llm)';
COMMENT ON COLUMN debug.pdf_conversions.strategy_options IS 'JSONB containing strategy-specific options (e.g., header/footer removal)';
COMMENT ON COLUMN debug.pdf_conversions.rating IS 'Quality rating: good, acceptable, or fail';
COMMENT ON COLUMN debug.pdf_conversions.comment IS 'Optional user comment about the conversion quality (max 500 chars)';
COMMENT ON COLUMN debug.pdf_conversions.created_at IS 'When this record was created';
COMMENT ON COLUMN debug.pdf_conversions.updated_at IS 'When this record was last updated';

-- ============================================================================
-- 2. Trigger for automatic updated_at timestamp
-- ============================================================================

CREATE OR REPLACE FUNCTION debug.update_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER pdf_conversions_updated
    BEFORE UPDATE ON debug.pdf_conversions
    FOR EACH ROW
    EXECUTE FUNCTION debug.update_timestamp();

-- ============================================================================
-- 3. Utility functions
-- ============================================================================

-- Function: Record a PDF conversion attempt
CREATE OR REPLACE FUNCTION debug.record_pdf_conversion(
    p_pdf_path TEXT,
    p_rating TEXT,
    p_conversion_strategy TEXT DEFAULT 'pymupdf4llm',
    p_strategy_options JSONB DEFAULT '{}'::jsonb,
    p_comment TEXT DEFAULT NULL
)
RETURNS INTEGER AS $$
DECLARE
    v_id INTEGER;
    v_filename TEXT;
BEGIN
    -- Extract filename from path
    v_filename := regexp_replace(p_pdf_path, '^.*/', '');

    -- Validate rating
    IF p_rating NOT IN ('good', 'acceptable', 'fail') THEN
        RAISE EXCEPTION 'Invalid rating: %. Must be good, acceptable, or fail', p_rating;
    END IF;

    -- Insert record
    INSERT INTO debug.pdf_conversions (
        pdf_path,
        pdf_filename,
        conversion_strategy,
        strategy_options,
        rating,
        comment
    ) VALUES (
        p_pdf_path,
        v_filename,
        p_conversion_strategy,
        p_strategy_options,
        p_rating,
        p_comment
    )
    RETURNING id INTO v_id;

    RETURN v_id;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION debug.record_pdf_conversion(TEXT, TEXT, TEXT, JSONB, TEXT)
    IS 'Record a PDF conversion attempt with rating and optional comment';

-- Function: Get conversion statistics by rating
CREATE OR REPLACE FUNCTION debug.get_conversion_stats()
RETURNS TABLE (
    rating TEXT,
    count BIGINT,
    percentage NUMERIC
) AS $$
DECLARE
    v_total BIGINT;
BEGIN
    SELECT COUNT(*) INTO v_total FROM debug.pdf_conversions;

    IF v_total = 0 THEN
        RETURN;
    END IF;

    RETURN QUERY
    SELECT
        pc.rating,
        COUNT(*) as count,
        ROUND((COUNT(*)::NUMERIC / v_total) * 100, 2) as percentage
    FROM debug.pdf_conversions pc
    GROUP BY pc.rating
    ORDER BY pc.rating;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION debug.get_conversion_stats()
    IS 'Get conversion statistics grouped by rating';

-- Function: Get failed conversions for retry
CREATE OR REPLACE FUNCTION debug.get_failed_conversions(
    p_limit INTEGER DEFAULT 100
)
RETURNS TABLE (
    id INTEGER,
    pdf_path TEXT,
    pdf_filename TEXT,
    conversion_strategy TEXT,
    strategy_options JSONB,
    comment TEXT,
    created_at TIMESTAMP
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        pc.id,
        pc.pdf_path,
        pc.pdf_filename,
        pc.conversion_strategy,
        pc.strategy_options,
        pc.comment,
        pc.created_at
    FROM debug.pdf_conversions pc
    WHERE pc.rating = 'fail'
    ORDER BY pc.created_at DESC
    LIMIT p_limit;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION debug.get_failed_conversions(INTEGER)
    IS 'Get failed conversions for retry with different strategies';

-- ============================================================================
-- 4. View for convenient access
-- ============================================================================

CREATE OR REPLACE VIEW debug.v_pdf_conversion_summary AS
SELECT
    pdf_filename,
    conversion_strategy,
    rating,
    comment,
    strategy_options,
    created_at
FROM debug.pdf_conversions
ORDER BY created_at DESC;

COMMENT ON VIEW debug.v_pdf_conversion_summary
    IS 'Summary view of PDF conversion attempts';

-- ============================================================================
-- Migration Complete
-- ============================================================================

COMMIT;

-- Log successful migration
DO $$
BEGIN
    RAISE NOTICE 'Debug schema migration completed successfully';
    RAISE NOTICE 'Created schema: debug';
    RAISE NOTICE 'Created tables: 1 (pdf_conversions)';
    RAISE NOTICE 'Created views: 1 (v_pdf_conversion_summary)';
    RAISE NOTICE 'Created functions: 3 (record_pdf_conversion, get_conversion_stats, get_failed_conversions)';
END $$;
