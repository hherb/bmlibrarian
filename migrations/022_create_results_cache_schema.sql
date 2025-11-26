-- Migration: Create Results Cache Schema
-- Description: Persistent storage for quality assessment results with versioning for reproducibility
-- Author: BMLibrarian
-- Date: 2025-11-26
-- Version: 1.0.0
--
-- Purpose: Store quality assessment results (study assessment, PICO, PRISMA, paper weight)
--          with versioning to enable:
--          - Reproducibility (track what model/parameters generated each assessment)
--          - Quality control (compare assessments across model versions)
--          - Model training (collect data for fine-tuning)
--          - Performance optimization (skip re-assessment when cached result exists)

-- ============================================================================
-- Create results_cache schema
-- ============================================================================

BEGIN;

CREATE SCHEMA IF NOT EXISTS results_cache;

COMMENT ON SCHEMA results_cache IS 'Quality assessment results cache with versioning for reproducibility and performance';

-- ============================================================================
-- 1. assessment_versions - Track assessment methodology versions
-- ============================================================================

CREATE TABLE results_cache.assessment_versions (
    version_id SERIAL PRIMARY KEY,
    assessment_type TEXT NOT NULL,  -- 'study_assessment', 'pico', 'prisma', 'paper_weight'
    model_name TEXT NOT NULL,       -- e.g., 'gpt-oss:20b'
    agent_version TEXT NOT NULL,    -- e.g., '1.0.0'
    parameters JSONB NOT NULL,      -- temperature, top_p, etc.
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),

    -- Unique constraint: one version per (type, model, agent_version, parameters)
    CONSTRAINT uq_assessment_version UNIQUE (assessment_type, model_name, agent_version, parameters)
);

CREATE INDEX idx_assessment_versions_type ON results_cache.assessment_versions(assessment_type);
CREATE INDEX idx_assessment_versions_model ON results_cache.assessment_versions(model_name);

COMMENT ON TABLE results_cache.assessment_versions IS 'Track assessment methodology versions for reproducibility';
COMMENT ON COLUMN results_cache.assessment_versions.assessment_type IS 'Type of assessment (study_assessment, pico, prisma, paper_weight)';
COMMENT ON COLUMN results_cache.assessment_versions.model_name IS 'Ollama model name used';
COMMENT ON COLUMN results_cache.assessment_versions.agent_version IS 'Agent version number';
COMMENT ON COLUMN results_cache.assessment_versions.parameters IS 'JSON object with model parameters (temperature, top_p, etc.)';

-- ============================================================================
-- 2. study_assessments - Cache study quality assessments
-- ============================================================================

CREATE TABLE results_cache.study_assessments (
    cache_id SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES public.document(id),
    version_id INTEGER NOT NULL REFERENCES results_cache.assessment_versions(version_id),
    assessed_at TIMESTAMP NOT NULL DEFAULT NOW(),

    -- Assessment results (stored as JSONB for flexibility)
    result JSONB NOT NULL,

    -- Metadata
    execution_time_ms INTEGER,  -- Time taken to generate assessment

    CONSTRAINT uq_study_assessment UNIQUE (document_id, version_id)
);

CREATE INDEX idx_study_assessments_document ON results_cache.study_assessments(document_id);
CREATE INDEX idx_study_assessments_version ON results_cache.study_assessments(version_id);
CREATE INDEX idx_study_assessments_assessed_at ON results_cache.study_assessments(assessed_at DESC);

COMMENT ON TABLE results_cache.study_assessments IS 'Cached study quality assessment results';
COMMENT ON COLUMN results_cache.study_assessments.result IS 'Study assessment result as JSON (study_type, quality_score, strengths, limitations, etc.)';

-- ============================================================================
-- 3. pico_extractions - Cache PICO component extractions
-- ============================================================================

CREATE TABLE results_cache.pico_extractions (
    cache_id SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES public.document(id),
    version_id INTEGER NOT NULL REFERENCES results_cache.assessment_versions(version_id),
    extracted_at TIMESTAMP NOT NULL DEFAULT NOW(),

    -- PICO components
    population TEXT,
    intervention TEXT,
    comparison TEXT,
    outcome TEXT,

    -- Metadata
    study_type TEXT,
    sample_size TEXT,
    extraction_confidence NUMERIC(3,2) CHECK (extraction_confidence >= 0 AND extraction_confidence <= 1),
    result JSONB NOT NULL,  -- Full extraction result with confidence scores
    execution_time_ms INTEGER,

    CONSTRAINT uq_pico_extraction UNIQUE (document_id, version_id)
);

CREATE INDEX idx_pico_extractions_document ON results_cache.pico_extractions(document_id);
CREATE INDEX idx_pico_extractions_version ON results_cache.pico_extractions(version_id);
CREATE INDEX idx_pico_extractions_confidence ON results_cache.pico_extractions(extraction_confidence DESC);

COMMENT ON TABLE results_cache.pico_extractions IS 'Cached PICO component extractions';
COMMENT ON COLUMN results_cache.pico_extractions.result IS 'Full PICO extraction result as JSON';

-- ============================================================================
-- 4. prisma_assessments - Cache PRISMA 2020 compliance assessments
-- ============================================================================

CREATE TABLE results_cache.prisma_assessments (
    cache_id SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES public.document(id),
    version_id INTEGER NOT NULL REFERENCES results_cache.assessment_versions(version_id),
    assessed_at TIMESTAMP NOT NULL DEFAULT NOW(),

    -- Overall scores
    is_suitable BOOLEAN NOT NULL,  -- Is this a systematic review/meta-analysis?
    overall_score NUMERIC(4,2),
    reporting_completeness NUMERIC(3,2),  -- Percentage of items reported

    -- Assessment results
    result JSONB NOT NULL,  -- Full PRISMA checklist results
    execution_time_ms INTEGER,

    CONSTRAINT uq_prisma_assessment UNIQUE (document_id, version_id)
);

CREATE INDEX idx_prisma_assessments_document ON results_cache.prisma_assessments(document_id);
CREATE INDEX idx_prisma_assessments_version ON results_cache.prisma_assessments(version_id);
CREATE INDEX idx_prisma_assessments_suitable ON results_cache.prisma_assessments(is_suitable);
CREATE INDEX idx_prisma_assessments_score ON results_cache.prisma_assessments(overall_score DESC);

COMMENT ON TABLE results_cache.prisma_assessments IS 'Cached PRISMA 2020 compliance assessments';
COMMENT ON COLUMN results_cache.prisma_assessments.is_suitable IS 'Whether document is suitable for PRISMA assessment';
COMMENT ON COLUMN results_cache.prisma_assessments.result IS 'Full PRISMA assessment result as JSON';

-- ============================================================================
-- 5. paper_weight_cache - Cache paper weight assessments (references paper_weights schema)
-- ============================================================================

CREATE TABLE results_cache.paper_weight_cache (
    cache_id SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES public.document(id),
    version_id INTEGER NOT NULL REFERENCES results_cache.assessment_versions(version_id),
    assessed_at TIMESTAMP NOT NULL DEFAULT NOW(),

    -- Reference to paper_weights.assessments if stored there
    paper_weight_assessment_id INTEGER REFERENCES paper_weights.assessments(assessment_id),

    -- Quick access fields
    composite_score NUMERIC(5,2),
    result JSONB NOT NULL,
    execution_time_ms INTEGER,

    CONSTRAINT uq_paper_weight_cache UNIQUE (document_id, version_id)
);

CREATE INDEX idx_paper_weight_cache_document ON results_cache.paper_weight_cache(document_id);
CREATE INDEX idx_paper_weight_cache_version ON results_cache.paper_weight_cache(version_id);
CREATE INDEX idx_paper_weight_cache_score ON results_cache.paper_weight_cache(composite_score DESC);

COMMENT ON TABLE results_cache.paper_weight_cache IS 'Cached paper weight assessment results';
COMMENT ON COLUMN results_cache.paper_weight_cache.result IS 'Full paper weight assessment result as JSON';

-- ============================================================================
-- 6. suitability_checks - Cache PICO/PRISMA suitability checks
-- ============================================================================

CREATE TABLE results_cache.suitability_checks (
    cache_id SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES public.document(id),
    check_type TEXT NOT NULL CHECK (check_type IN ('pico', 'prisma')),
    version_id INTEGER NOT NULL REFERENCES results_cache.assessment_versions(version_id),
    checked_at TIMESTAMP NOT NULL DEFAULT NOW(),

    -- Suitability result
    is_suitable BOOLEAN NOT NULL,
    confidence NUMERIC(3,2) CHECK (confidence >= 0 AND confidence <= 1),
    rationale TEXT NOT NULL,
    study_type TEXT,
    result JSONB NOT NULL,  -- Full suitability check result
    execution_time_ms INTEGER,

    CONSTRAINT uq_suitability_check UNIQUE (document_id, check_type, version_id)
);

CREATE INDEX idx_suitability_checks_document ON results_cache.suitability_checks(document_id);
CREATE INDEX idx_suitability_checks_type ON results_cache.suitability_checks(check_type);
CREATE INDEX idx_suitability_checks_suitable ON results_cache.suitability_checks(is_suitable);
CREATE INDEX idx_suitability_checks_version ON results_cache.suitability_checks(version_id);

COMMENT ON TABLE results_cache.suitability_checks IS 'Cached PICO/PRISMA suitability check results';
COMMENT ON COLUMN results_cache.suitability_checks.check_type IS 'Type of suitability check (pico or prisma)';
COMMENT ON COLUMN results_cache.suitability_checks.is_suitable IS 'Whether document is suitable for the assessment type';
COMMENT ON COLUMN results_cache.suitability_checks.result IS 'Full suitability check result as JSON';

-- ============================================================================
-- Helper Functions
-- ============================================================================

-- Function to get or create an assessment version
CREATE OR REPLACE FUNCTION results_cache.get_or_create_version(
    p_assessment_type TEXT,
    p_model_name TEXT,
    p_agent_version TEXT,
    p_parameters JSONB
) RETURNS INTEGER AS $$
DECLARE
    v_version_id INTEGER;
BEGIN
    -- Try to find existing version
    SELECT version_id INTO v_version_id
    FROM results_cache.assessment_versions
    WHERE assessment_type = p_assessment_type
      AND model_name = p_model_name
      AND agent_version = p_agent_version
      AND parameters = p_parameters;

    -- If not found, create new version
    IF v_version_id IS NULL THEN
        INSERT INTO results_cache.assessment_versions (
            assessment_type, model_name, agent_version, parameters
        ) VALUES (
            p_assessment_type, p_model_name, p_agent_version, p_parameters
        ) RETURNING version_id INTO v_version_id;
    END IF;

    RETURN v_version_id;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION results_cache.get_or_create_version IS 'Get existing version ID or create new version entry';

-- ============================================================================
-- Views for easy querying
-- ============================================================================

-- View: Latest assessments (most recent version for each document)
CREATE VIEW results_cache.v_latest_study_assessments AS
SELECT
    sa.document_id,
    sa.assessed_at,
    sa.result,
    av.model_name,
    av.agent_version,
    av.parameters
FROM results_cache.study_assessments sa
JOIN results_cache.assessment_versions av ON sa.version_id = av.version_id
WHERE (sa.document_id, sa.assessed_at) IN (
    SELECT document_id, MAX(assessed_at)
    FROM results_cache.study_assessments
    GROUP BY document_id
);

COMMENT ON VIEW results_cache.v_latest_study_assessments IS 'Most recent study assessment for each document';

-- Similar views for other assessment types
CREATE VIEW results_cache.v_latest_pico_extractions AS
SELECT
    pe.document_id,
    pe.extracted_at,
    pe.population,
    pe.intervention,
    pe.comparison,
    pe.outcome,
    pe.extraction_confidence,
    pe.result,
    av.model_name,
    av.agent_version
FROM results_cache.pico_extractions pe
JOIN results_cache.assessment_versions av ON pe.version_id = av.version_id
WHERE (pe.document_id, pe.extracted_at) IN (
    SELECT document_id, MAX(extracted_at)
    FROM results_cache.pico_extractions
    GROUP BY document_id
);

COMMENT ON VIEW results_cache.v_latest_pico_extractions IS 'Most recent PICO extraction for each document';

-- ============================================================================
-- Cleanup function for old cached results
-- ============================================================================

CREATE OR REPLACE FUNCTION results_cache.cleanup_old_versions(
    p_keep_latest_n INTEGER DEFAULT 3,
    p_older_than_days INTEGER DEFAULT 90
) RETURNS TABLE (
    deleted_study_assessments INTEGER,
    deleted_pico_extractions INTEGER,
    deleted_prisma_assessments INTEGER,
    deleted_suitability_checks INTEGER
) AS $$
DECLARE
    v_deleted_study INTEGER := 0;
    v_deleted_pico INTEGER := 0;
    v_deleted_prisma INTEGER := 0;
    v_deleted_suitability INTEGER := 0;
BEGIN
    -- Delete old study assessments (keep latest N per document)
    WITH ranked AS (
        SELECT cache_id,
               ROW_NUMBER() OVER (PARTITION BY document_id ORDER BY assessed_at DESC) as rn
        FROM results_cache.study_assessments
        WHERE assessed_at < NOW() - (p_older_than_days || ' days')::INTERVAL
    )
    DELETE FROM results_cache.study_assessments
    WHERE cache_id IN (SELECT cache_id FROM ranked WHERE rn > p_keep_latest_n);

    GET DIAGNOSTICS v_deleted_study = ROW_COUNT;

    -- Similar cleanup for other tables
    WITH ranked AS (
        SELECT cache_id,
               ROW_NUMBER() OVER (PARTITION BY document_id ORDER BY extracted_at DESC) as rn
        FROM results_cache.pico_extractions
        WHERE extracted_at < NOW() - (p_older_than_days || ' days')::INTERVAL
    )
    DELETE FROM results_cache.pico_extractions
    WHERE cache_id IN (SELECT cache_id FROM ranked WHERE rn > p_keep_latest_n);

    GET DIAGNOSTICS v_deleted_pico = ROW_COUNT;

    WITH ranked AS (
        SELECT cache_id,
               ROW_NUMBER() OVER (PARTITION BY document_id ORDER BY assessed_at DESC) as rn
        FROM results_cache.prisma_assessments
        WHERE assessed_at < NOW() - (p_older_than_days || ' days')::INTERVAL
    )
    DELETE FROM results_cache.prisma_assessments
    WHERE cache_id IN (SELECT cache_id FROM ranked WHERE rn > p_keep_latest_n);

    GET DIAGNOSTICS v_deleted_prisma = ROW_COUNT;

    WITH ranked AS (
        SELECT cache_id,
               ROW_NUMBER() OVER (PARTITION BY document_id, check_type ORDER BY checked_at DESC) as rn
        FROM results_cache.suitability_checks
        WHERE checked_at < NOW() - (p_older_than_days || ' days')::INTERVAL
    )
    DELETE FROM results_cache.suitability_checks
    WHERE cache_id IN (SELECT cache_id FROM ranked WHERE rn > p_keep_latest_n);

    GET DIAGNOSTICS v_deleted_suitability = ROW_COUNT;

    RETURN QUERY SELECT v_deleted_study, v_deleted_pico, v_deleted_prisma, v_deleted_suitability;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION results_cache.cleanup_old_versions IS 'Delete old cached results, keeping latest N versions per document';

COMMIT;
