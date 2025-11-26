-- Migration: Create Paper Weight Assessment Schema
-- Description: Multi-dimensional paper weight assessment with full audit trail for reproducibility
-- Author: BMLibrarian
-- Date: 2025-11-21
-- Version: 1.0.0

-- ============================================================================
-- Create paper_weights schema
-- ============================================================================

BEGIN;

CREATE SCHEMA IF NOT EXISTS paper_weights;

-- Note: Schema permissions are managed at database level by the setup wizard.
-- The application user running migrations already has full privileges.

COMMENT ON SCHEMA paper_weights IS 'PaperWeightAssessment: Multi-dimensional paper quality assessment for evidence weighting';

-- ============================================================================
-- 1. assessments - Main table for paper weight assessments
-- ============================================================================

CREATE TABLE IF NOT EXISTS paper_weights.assessments (
    assessment_id SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES public.document(id),
    assessed_at TIMESTAMP NOT NULL DEFAULT NOW(),
    assessor_version TEXT NOT NULL,

    -- Multi-dimensional scores (0-10 scale)
    -- Each score represents an independent assessment dimension
    study_design_score NUMERIC(4,2) NOT NULL
        CHECK (study_design_score >= 0 AND study_design_score <= 10),
    sample_size_score NUMERIC(4,2) NOT NULL
        CHECK (sample_size_score >= 0 AND sample_size_score <= 10),
    methodological_quality_score NUMERIC(4,2) NOT NULL
        CHECK (methodological_quality_score >= 0 AND methodological_quality_score <= 10),
    risk_of_bias_score NUMERIC(4,2) NOT NULL
        CHECK (risk_of_bias_score >= 0 AND risk_of_bias_score <= 10),
    replication_status_score NUMERIC(4,2) NOT NULL
        CHECK (replication_status_score >= 0 AND replication_status_score <= 10),

    -- Final weighted score (calculated from dimension scores and weights)
    final_weight NUMERIC(5,2) NOT NULL
        CHECK (final_weight >= 0 AND final_weight <= 10),

    -- Dimension weights used for calculation (JSONB for flexibility)
    -- Example: {"study_design": 0.25, "sample_size": 0.15, ...}
    -- Required keys: study_design, sample_size, methodological_quality, risk_of_bias, replication_status
    dimension_weights JSONB NOT NULL
        CHECK (
            dimension_weights ? 'study_design' AND
            dimension_weights ? 'sample_size' AND
            dimension_weights ? 'methodological_quality' AND
            dimension_weights ? 'risk_of_bias' AND
            dimension_weights ? 'replication_status' AND
            -- Ensure values are numeric (between 0 and 1 for weights)
            (dimension_weights->>'study_design')::NUMERIC >= 0 AND
            (dimension_weights->>'study_design')::NUMERIC <= 1 AND
            (dimension_weights->>'sample_size')::NUMERIC >= 0 AND
            (dimension_weights->>'sample_size')::NUMERIC <= 1 AND
            (dimension_weights->>'methodological_quality')::NUMERIC >= 0 AND
            (dimension_weights->>'methodological_quality')::NUMERIC <= 1 AND
            (dimension_weights->>'risk_of_bias')::NUMERIC >= 0 AND
            (dimension_weights->>'risk_of_bias')::NUMERIC <= 1 AND
            (dimension_weights->>'replication_status')::NUMERIC >= 0 AND
            (dimension_weights->>'replication_status')::NUMERIC <= 1
        ),

    -- Extracted metadata from paper
    study_type TEXT,      -- e.g., "RCT", "cohort", "case-control"
    sample_size INTEGER   -- Extracted n value

    -- Note: Unique constraint handled via CREATE UNIQUE INDEX below for optimization
    -- This approach is more efficient than inline UNIQUE(document_id, assessor_version)
);

-- Composite unique index: enforces uniqueness AND provides efficient lookups
-- This replaces both the inline UNIQUE constraint and eliminates need for separate document_id index
-- One assessment per (document, version) combination - allows re-assessment when methodology improves
CREATE UNIQUE INDEX IF NOT EXISTS idx_assessments_doc_version
    ON paper_weights.assessments(document_id, assessor_version);

-- Additional indexes for common query patterns
-- Note: idx_assessments_document is NOT needed - covered by idx_assessments_doc_version (leftmost column)
CREATE INDEX IF NOT EXISTS idx_assessments_version ON paper_weights.assessments(assessor_version);
CREATE INDEX IF NOT EXISTS idx_assessments_final_weight ON paper_weights.assessments(final_weight DESC);
CREATE INDEX IF NOT EXISTS idx_assessments_study_type ON paper_weights.assessments(study_type);

COMMENT ON TABLE paper_weights.assessments IS 'Main table storing multi-dimensional paper weight assessments';
COMMENT ON COLUMN paper_weights.assessments.assessment_id IS 'Unique identifier for this assessment';
COMMENT ON COLUMN paper_weights.assessments.document_id IS 'Reference to the assessed document in public.document';
COMMENT ON COLUMN paper_weights.assessments.assessed_at IS 'Timestamp when assessment was performed';
COMMENT ON COLUMN paper_weights.assessments.assessor_version IS 'Version of assessment methodology (e.g., "1.0.0")';
COMMENT ON COLUMN paper_weights.assessments.study_design_score IS 'Score for study design quality (0-10)';
COMMENT ON COLUMN paper_weights.assessments.sample_size_score IS 'Score for sample size adequacy (0-10)';
COMMENT ON COLUMN paper_weights.assessments.methodological_quality_score IS 'Score for methodological quality (0-10)';
COMMENT ON COLUMN paper_weights.assessments.risk_of_bias_score IS 'Score for risk of bias (inverted: 10=low risk, 0=high risk)';
COMMENT ON COLUMN paper_weights.assessments.replication_status_score IS 'Score for replication status (0-10)';
COMMENT ON COLUMN paper_weights.assessments.final_weight IS 'Calculated weighted final score (0-10)';
COMMENT ON COLUMN paper_weights.assessments.dimension_weights IS 'Weights used for final score calculation';
COMMENT ON COLUMN paper_weights.assessments.study_type IS 'Extracted study type classification';
COMMENT ON COLUMN paper_weights.assessments.sample_size IS 'Extracted sample size (n)';

-- ============================================================================
-- 2. assessment_details - Audit trail for reproducibility
-- ============================================================================

CREATE TABLE IF NOT EXISTS paper_weights.assessment_details (
    detail_id SERIAL PRIMARY KEY,
    assessment_id INTEGER NOT NULL
        REFERENCES paper_weights.assessments(assessment_id) ON DELETE CASCADE,

    -- What was assessed
    dimension TEXT NOT NULL,  -- e.g., "study_design", "methodological_quality"
    component TEXT,           -- e.g., "randomization", "blinding_type"

    -- Assessment results
    extracted_value TEXT,     -- What was found in the paper
    score_contribution NUMERIC(4,2),  -- Contribution to dimension score
    evidence_text TEXT,       -- Relevant excerpt from paper
    reasoning TEXT,           -- LLM reasoning for this score

    -- Metadata
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Index for audit trail lookups
CREATE INDEX IF NOT EXISTS idx_details_assessment ON paper_weights.assessment_details(assessment_id);
CREATE INDEX IF NOT EXISTS idx_details_dimension ON paper_weights.assessment_details(dimension);

COMMENT ON TABLE paper_weights.assessment_details IS 'Granular audit trail for assessment reproducibility';
COMMENT ON COLUMN paper_weights.assessment_details.detail_id IS 'Unique identifier for this detail entry';
COMMENT ON COLUMN paper_weights.assessment_details.assessment_id IS 'Reference to parent assessment';
COMMENT ON COLUMN paper_weights.assessment_details.dimension IS 'Assessment dimension (e.g., study_design, risk_of_bias)';
COMMENT ON COLUMN paper_weights.assessment_details.component IS 'Specific component within dimension (e.g., randomization)';
COMMENT ON COLUMN paper_weights.assessment_details.extracted_value IS 'Value extracted from the paper';
COMMENT ON COLUMN paper_weights.assessment_details.score_contribution IS 'Points contributed to dimension score';
COMMENT ON COLUMN paper_weights.assessment_details.evidence_text IS 'Supporting text excerpt from paper';
COMMENT ON COLUMN paper_weights.assessment_details.reasoning IS 'LLM reasoning for score assignment';
COMMENT ON COLUMN paper_weights.assessment_details.created_at IS 'When this detail was recorded';

-- ============================================================================
-- 3. replications - Manual tracking of replication studies
-- ============================================================================

CREATE TABLE IF NOT EXISTS paper_weights.replications (
    replication_id SERIAL PRIMARY KEY,
    source_document_id INTEGER NOT NULL REFERENCES public.document(id),
    replication_document_id INTEGER NOT NULL REFERENCES public.document(id),

    -- Replication classification
    replication_type TEXT NOT NULL
        CHECK (replication_type IN ('confirms', 'contradicts', 'extends')),
    quality_comparison TEXT
        CHECK (quality_comparison IN ('lower', 'comparable', 'higher')),

    -- Assessment metadata
    assessed_at TIMESTAMP NOT NULL DEFAULT NOW(),
    assessed_by TEXT,  -- Username or system identifier
    confidence TEXT
        CHECK (confidence IN ('low', 'medium', 'high')),
    notes TEXT,

    -- One entry per source-replication pair
    UNIQUE(source_document_id, replication_document_id)
);

-- Indexes for replication lookups
CREATE INDEX IF NOT EXISTS idx_replications_source ON paper_weights.replications(source_document_id);
CREATE INDEX IF NOT EXISTS idx_replications_replication ON paper_weights.replications(replication_document_id);
CREATE INDEX IF NOT EXISTS idx_replications_type ON paper_weights.replications(replication_type);

COMMENT ON TABLE paper_weights.replications IS 'Manual tracking of replication relationships between studies';
COMMENT ON COLUMN paper_weights.replications.replication_id IS 'Unique identifier for this replication entry';
COMMENT ON COLUMN paper_weights.replications.source_document_id IS 'Original study being replicated';
COMMENT ON COLUMN paper_weights.replications.replication_document_id IS 'Study that replicates the source';
COMMENT ON COLUMN paper_weights.replications.replication_type IS 'Type: confirms, contradicts, or extends';
COMMENT ON COLUMN paper_weights.replications.quality_comparison IS 'Quality relative to source: lower, comparable, higher';
COMMENT ON COLUMN paper_weights.replications.assessed_at IS 'When this relationship was recorded';
COMMENT ON COLUMN paper_weights.replications.assessed_by IS 'Who recorded this relationship';
COMMENT ON COLUMN paper_weights.replications.confidence IS 'Confidence in replication classification';
COMMENT ON COLUMN paper_weights.replications.notes IS 'Additional notes about the replication';

-- ============================================================================
-- Views for Convenient Queries
-- ============================================================================

-- View: Latest assessment per document (most recent version)
CREATE OR REPLACE VIEW paper_weights.v_latest_assessments AS
SELECT DISTINCT ON (document_id)
    a.assessment_id,
    a.document_id,
    a.assessed_at,
    a.assessor_version,
    a.study_design_score,
    a.sample_size_score,
    a.methodological_quality_score,
    a.risk_of_bias_score,
    a.replication_status_score,
    a.final_weight,
    a.study_type,
    a.sample_size
FROM paper_weights.assessments a
ORDER BY document_id, assessed_at DESC;

COMMENT ON VIEW paper_weights.v_latest_assessments IS 'Most recent assessment for each document';

-- View: Assessment with replication count
CREATE OR REPLACE VIEW paper_weights.v_assessments_with_replications AS
SELECT
    a.assessment_id,
    a.document_id,
    a.final_weight,
    a.study_type,
    a.assessor_version,
    a.assessed_at,
    (SELECT COUNT(*) FROM paper_weights.replications r
     WHERE r.source_document_id = a.document_id) as replication_count,
    (SELECT COUNT(*) FROM paper_weights.replications r
     WHERE r.source_document_id = a.document_id
       AND r.replication_type = 'confirms') as confirming_replications,
    (SELECT COUNT(*) FROM paper_weights.replications r
     WHERE r.source_document_id = a.document_id
       AND r.replication_type = 'contradicts') as contradicting_replications
FROM paper_weights.assessments a;

COMMENT ON VIEW paper_weights.v_assessments_with_replications IS 'Assessments with replication statistics';

-- View: Assessment dimension breakdown
CREATE OR REPLACE VIEW paper_weights.v_dimension_breakdown AS
SELECT
    a.assessment_id,
    a.document_id,
    a.assessor_version,
    ad.dimension,
    ad.component,
    ad.extracted_value,
    ad.score_contribution,
    ad.reasoning
FROM paper_weights.assessments a
JOIN paper_weights.assessment_details ad ON ad.assessment_id = a.assessment_id
ORDER BY a.assessment_id, ad.dimension, ad.component;

COMMENT ON VIEW paper_weights.v_dimension_breakdown IS 'Detailed dimension breakdown for all assessments';

-- ============================================================================
-- Utility Functions
-- ============================================================================

-- Function: Get complete assessment with all details
CREATE OR REPLACE FUNCTION paper_weights.get_complete_assessment(p_document_id INTEGER, p_version TEXT DEFAULT NULL)
RETURNS TABLE (
    assessment_id INTEGER,
    document_id INTEGER,
    assessed_at TIMESTAMP,
    assessor_version TEXT,
    study_design_score NUMERIC,
    sample_size_score NUMERIC,
    methodological_quality_score NUMERIC,
    risk_of_bias_score NUMERIC,
    replication_status_score NUMERIC,
    final_weight NUMERIC,
    study_type TEXT,
    sample_size INTEGER,
    dimension_weights JSONB
) AS $$
BEGIN
    -- Validate input parameters
    IF p_document_id IS NULL THEN
        RAISE EXCEPTION 'p_document_id cannot be NULL';
    END IF;

    IF p_document_id <= 0 THEN
        RAISE EXCEPTION 'p_document_id must be a positive integer, got: %', p_document_id;
    END IF;

    RETURN QUERY
    SELECT
        a.assessment_id,
        a.document_id,
        a.assessed_at,
        a.assessor_version,
        a.study_design_score,
        a.sample_size_score,
        a.methodological_quality_score,
        a.risk_of_bias_score,
        a.replication_status_score,
        a.final_weight,
        a.study_type,
        a.sample_size,
        a.dimension_weights
    FROM paper_weights.assessments a
    WHERE a.document_id = p_document_id
      AND (p_version IS NULL OR a.assessor_version = p_version)
    ORDER BY a.assessed_at DESC
    LIMIT 1;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION paper_weights.get_complete_assessment(INTEGER, TEXT) IS 'Get complete assessment for a document (optionally by version)';

-- Function: Get replication status for a document
CREATE OR REPLACE FUNCTION paper_weights.get_replication_status(p_document_id INTEGER)
RETURNS TABLE (
    total_replications INTEGER,
    confirming INTEGER,
    contradicting INTEGER,
    extending INTEGER,
    highest_quality_comparison TEXT
) AS $$
BEGIN
    -- Validate input parameters
    IF p_document_id IS NULL THEN
        RAISE EXCEPTION 'p_document_id cannot be NULL';
    END IF;

    IF p_document_id <= 0 THEN
        RAISE EXCEPTION 'p_document_id must be a positive integer, got: %', p_document_id;
    END IF;

    RETURN QUERY
    SELECT
        COUNT(*)::INTEGER as total_replications,
        COALESCE(SUM(CASE WHEN replication_type = 'confirms' THEN 1 ELSE 0 END), 0)::INTEGER as confirming,
        COALESCE(SUM(CASE WHEN replication_type = 'contradicts' THEN 1 ELSE 0 END), 0)::INTEGER as contradicting,
        COALESCE(SUM(CASE WHEN replication_type = 'extends' THEN 1 ELSE 0 END), 0)::INTEGER as extending,
        -- Use explicit ordering for quality comparison to handle NULLs properly
        -- Returns NULL if no replications exist (no rows to aggregate)
        CASE
            WHEN MAX(CASE quality_comparison
                WHEN 'higher' THEN 3
                WHEN 'comparable' THEN 2
                WHEN 'lower' THEN 1
                ELSE NULL
            END) = 3 THEN 'higher'
            WHEN MAX(CASE quality_comparison
                WHEN 'higher' THEN 3
                WHEN 'comparable' THEN 2
                WHEN 'lower' THEN 1
                ELSE NULL
            END) = 2 THEN 'comparable'
            WHEN MAX(CASE quality_comparison
                WHEN 'higher' THEN 3
                WHEN 'comparable' THEN 2
                WHEN 'lower' THEN 1
                ELSE NULL
            END) = 1 THEN 'lower'
            ELSE NULL
        END as highest_quality_comparison
    FROM paper_weights.replications
    WHERE source_document_id = p_document_id;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION paper_weights.get_replication_status(INTEGER) IS 'Get replication statistics for a document';

-- Function: Calculate replication score based on replications table
CREATE OR REPLACE FUNCTION paper_weights.calculate_replication_score(p_document_id INTEGER)
RETURNS NUMERIC AS $$
DECLARE
    v_total INTEGER;
    v_confirming INTEGER;
    v_contradicting INTEGER;
    v_highest_quality_rank INTEGER;
    v_score NUMERIC;
BEGIN
    -- Validate input parameters
    IF p_document_id IS NULL THEN
        RAISE EXCEPTION 'p_document_id cannot be NULL';
    END IF;

    IF p_document_id <= 0 THEN
        RAISE EXCEPTION 'p_document_id must be a positive integer, got: %', p_document_id;
    END IF;

    SELECT
        COUNT(*),
        COALESCE(SUM(CASE WHEN replication_type = 'confirms' THEN 1 ELSE 0 END), 0),
        COALESCE(SUM(CASE WHEN replication_type = 'contradicts' THEN 1 ELSE 0 END), 0),
        -- Use numeric ranking to properly order quality comparisons
        -- (MAX on strings would give 'lower' > 'higher' due to alphabetical ordering)
        MAX(CASE quality_comparison
            WHEN 'higher' THEN 3
            WHEN 'comparable' THEN 2
            WHEN 'lower' THEN 1
            ELSE NULL
        END)
    INTO v_total, v_confirming, v_contradicting, v_highest_quality_rank
    FROM paper_weights.replications
    WHERE source_document_id = p_document_id;

    -- Default: not replicated = 0
    IF v_total IS NULL OR v_total = 0 THEN
        RETURN 0.0;
    END IF;

    -- Base score based on confirming replications
    IF v_confirming >= 2 THEN
        v_score := 8.0;
    ELSIF v_confirming >= 1 THEN
        v_score := 5.0;
    ELSE
        v_score := 0.0;
    END IF;

    -- Bonus for higher quality replication (rank 3 = 'higher')
    IF v_highest_quality_rank = 3 THEN
        v_score := v_score + 2.0;
    END IF;

    -- Penalty for contradicting replications
    IF v_contradicting > 0 THEN
        v_score := v_score - (v_contradicting * 2.0);
    END IF;

    -- Clamp to 0-10
    RETURN GREATEST(0.0, LEAST(10.0, v_score));
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION paper_weights.calculate_replication_score(INTEGER) IS 'Calculate replication status score (0-10) based on replications table';

-- ============================================================================
-- Migration Complete
-- ============================================================================

COMMIT;

-- Log successful migration
DO $$
BEGIN
    RAISE NOTICE 'Paper Weight Assessment schema migration completed successfully';
    RAISE NOTICE 'Created schema: paper_weights';
    RAISE NOTICE 'Created tables: 3 (assessments, assessment_details, replications)';
    RAISE NOTICE 'Created views: 3';
    RAISE NOTICE 'Created functions: 3';
END $$;
