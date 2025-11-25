-- Migration: Create PDF Download History Table
-- Description: Tracks the source and verification status of PDF downloads,
--              enabling audit trails and debugging of incorrect PDF matches.
-- Author: BMLibrarian
-- Date: 2025-11-25

-- ============================================================================
-- Create pdf_download_history table
-- ============================================================================

CREATE TABLE IF NOT EXISTS pdf_download_history (
    id SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES document(id) ON DELETE CASCADE,

    -- Download metadata
    downloaded_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    source_type VARCHAR(50) NOT NULL,  -- 'pmc', 'unpaywall', 'doi_redirect', 'direct_url', 'browser', etc.
    source_url TEXT,
    access_type VARCHAR(50),  -- 'open', 'institutional', 'subscription'

    -- File info
    pdf_filename VARCHAR(500),
    pdf_file_path TEXT,
    file_size_bytes INTEGER,

    -- Verification results
    verified BOOLEAN,  -- NULL=not checked, true=verified, false=mismatch
    verification_confidence FLOAT,
    verification_match_type VARCHAR(50),  -- 'doi', 'pmid', 'title', 'doi_mismatch', etc.
    extracted_doi VARCHAR(100),
    extracted_pmid VARCHAR(20),
    extracted_title TEXT,

    -- Status tracking
    status VARCHAR(50) DEFAULT 'active',  -- 'active', 'replaced', 'deleted', 'invalid'
    replaced_by INTEGER REFERENCES pdf_download_history(id),
    notes TEXT,

    -- Indexes for common queries
    CONSTRAINT valid_source_type CHECK (source_type IN (
        'pmc', 'pmc_package', 'unpaywall', 'doi_redirect', 'direct_url',
        'browser', 'openathens', 'manual', 'import', 'unknown'
    ))
);

-- Create indexes for efficient queries
CREATE INDEX IF NOT EXISTS idx_pdf_download_history_document_id
    ON pdf_download_history(document_id);

CREATE INDEX IF NOT EXISTS idx_pdf_download_history_source_type
    ON pdf_download_history(source_type);

CREATE INDEX IF NOT EXISTS idx_pdf_download_history_verified
    ON pdf_download_history(verified) WHERE verified IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_pdf_download_history_status
    ON pdf_download_history(status);

CREATE INDEX IF NOT EXISTS idx_pdf_download_history_downloaded_at
    ON pdf_download_history(downloaded_at);

-- ============================================================================
-- Create pdf_validation_issues table (for flagging problems)
-- ============================================================================

CREATE TABLE IF NOT EXISTS pdf_validation_issues (
    id SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES document(id) ON DELETE CASCADE,
    download_history_id INTEGER REFERENCES pdf_download_history(id) ON DELETE SET NULL,

    issue_type VARCHAR(50) NOT NULL,  -- 'content_mismatch', 'file_missing', 'corrupt', etc.
    details TEXT,
    severity VARCHAR(20) DEFAULT 'warning',  -- 'info', 'warning', 'error', 'critical'

    detected_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP WITH TIME ZONE,
    resolved_by VARCHAR(100),
    resolution_notes TEXT,

    UNIQUE (document_id, issue_type, download_history_id)
);

CREATE INDEX IF NOT EXISTS idx_pdf_validation_issues_document_id
    ON pdf_validation_issues(document_id);

CREATE INDEX IF NOT EXISTS idx_pdf_validation_issues_unresolved
    ON pdf_validation_issues(document_id) WHERE resolved_at IS NULL;

-- ============================================================================
-- Create view for current PDF status
-- ============================================================================

CREATE OR REPLACE VIEW v_document_pdf_status AS
SELECT
    d.id AS document_id,
    d.doi,
    d.pmid,
    d.title,
    d.pdf_filename,
    h.source_type AS last_download_source,
    h.source_url AS last_download_url,
    h.downloaded_at AS last_download_time,
    h.verified,
    h.verification_confidence,
    h.verification_match_type,
    CASE
        WHEN h.verified = false THEN 'MISMATCH'
        WHEN h.verified = true THEN 'VERIFIED'
        WHEN h.verified IS NULL AND d.pdf_filename IS NOT NULL THEN 'UNVERIFIED'
        WHEN d.pdf_filename IS NULL THEN 'NO_PDF'
        ELSE 'UNKNOWN'
    END AS pdf_status,
    (SELECT COUNT(*) FROM pdf_validation_issues i
     WHERE i.document_id = d.id AND i.resolved_at IS NULL) AS open_issues
FROM document d
LEFT JOIN LATERAL (
    SELECT * FROM pdf_download_history
    WHERE document_id = d.id AND status = 'active'
    ORDER BY downloaded_at DESC
    LIMIT 1
) h ON true;

-- ============================================================================
-- Create function to log PDF download
-- ============================================================================

CREATE OR REPLACE FUNCTION log_pdf_download(
    p_document_id INTEGER,
    p_source_type VARCHAR(50),
    p_source_url TEXT DEFAULT NULL,
    p_access_type VARCHAR(50) DEFAULT NULL,
    p_pdf_filename VARCHAR(500) DEFAULT NULL,
    p_pdf_file_path TEXT DEFAULT NULL,
    p_file_size_bytes INTEGER DEFAULT NULL,
    p_verified BOOLEAN DEFAULT NULL,
    p_verification_confidence FLOAT DEFAULT NULL,
    p_verification_match_type VARCHAR(50) DEFAULT NULL,
    p_extracted_doi VARCHAR(100) DEFAULT NULL,
    p_extracted_pmid VARCHAR(20) DEFAULT NULL,
    p_extracted_title TEXT DEFAULT NULL,
    p_notes TEXT DEFAULT NULL
)
RETURNS INTEGER AS $$
DECLARE
    v_history_id INTEGER;
BEGIN
    -- Mark previous active downloads as replaced
    UPDATE pdf_download_history
    SET status = 'replaced'
    WHERE document_id = p_document_id AND status = 'active';

    -- Insert new download record
    INSERT INTO pdf_download_history (
        document_id, source_type, source_url, access_type,
        pdf_filename, pdf_file_path, file_size_bytes,
        verified, verification_confidence, verification_match_type,
        extracted_doi, extracted_pmid, extracted_title, notes
    ) VALUES (
        p_document_id, p_source_type, p_source_url, p_access_type,
        p_pdf_filename, p_pdf_file_path, p_file_size_bytes,
        p_verified, p_verification_confidence, p_verification_match_type,
        p_extracted_doi, p_extracted_pmid, p_extracted_title, p_notes
    )
    RETURNING id INTO v_history_id;

    -- Auto-create validation issue if mismatch detected
    IF p_verified = false THEN
        INSERT INTO pdf_validation_issues (
            document_id, download_history_id, issue_type, details, severity
        ) VALUES (
            p_document_id, v_history_id, 'content_mismatch',
            COALESCE(p_notes, 'PDF content does not match expected document'),
            'error'
        )
        ON CONFLICT (document_id, issue_type, download_history_id) DO NOTHING;
    END IF;

    RETURN v_history_id;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- Create function to get download statistics
-- ============================================================================

CREATE OR REPLACE FUNCTION get_pdf_download_stats()
RETURNS TABLE (
    source_type VARCHAR(50),
    total_downloads BIGINT,
    verified_count BIGINT,
    mismatch_count BIGINT,
    unverified_count BIGINT,
    verification_rate NUMERIC
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        h.source_type,
        COUNT(*) AS total_downloads,
        COUNT(*) FILTER (WHERE h.verified = true) AS verified_count,
        COUNT(*) FILTER (WHERE h.verified = false) AS mismatch_count,
        COUNT(*) FILTER (WHERE h.verified IS NULL) AS unverified_count,
        ROUND(
            100.0 * COUNT(*) FILTER (WHERE h.verified = true) /
            NULLIF(COUNT(*) FILTER (WHERE h.verified IS NOT NULL), 0),
            2
        ) AS verification_rate
    FROM pdf_download_history h
    WHERE h.status = 'active'
    GROUP BY h.source_type
    ORDER BY total_downloads DESC;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- Grant permissions (adjust as needed for your setup)
-- ============================================================================

-- Grant select on view to all users
GRANT SELECT ON v_document_pdf_status TO PUBLIC;

COMMENT ON TABLE pdf_download_history IS 'Tracks PDF download sources and verification status for audit and debugging';
COMMENT ON TABLE pdf_validation_issues IS 'Tracks issues found during PDF validation';
COMMENT ON VIEW v_document_pdf_status IS 'Current PDF status for each document';
COMMENT ON FUNCTION log_pdf_download IS 'Logs a PDF download with optional verification results';
COMMENT ON FUNCTION get_pdf_download_stats IS 'Returns download statistics by source type';
