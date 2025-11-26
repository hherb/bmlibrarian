-- Migration: Create Quality Assessment Caching Schema
-- Description: Caching for study assessments, PICO extractions, and PRISMA evaluations with full audit trail
-- Author: BMLibrarian
-- Date: 2025-11-26
-- Version: 1.0.0

-- ============================================================================
-- Create quality_assessment schema
-- ============================================================================

BEGIN;

CREATE SCHEMA IF NOT EXISTS quality_assessment;

COMMENT ON SCHEMA quality_assessment IS 'Quality assessment caching: study assessments, PICO, and PRISMA evaluations';

-- ============================================================================
-- 1. study_assessments - Study design and quality assessments
-- ============================================================================

CREATE TABLE IF NOT EXISTS quality_assessment.study_assessments (
    assessment_id SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES public.document(id),
    assessed_at TIMESTAMP NOT NULL DEFAULT NOW(),

    -- Versioning metadata for reproducibility
    agent_version TEXT NOT NULL,
    model_name TEXT NOT NULL,
    model_parameters JSONB NOT NULL DEFAULT '{}'::JSONB,
    prompt_hash TEXT,  -- SHA256 hash of prompt template

    -- Study classification
    study_type TEXT NOT NULL,
    study_design TEXT NOT NULL,
    evidence_level TEXT,

    -- Quality scores
    quality_score NUMERIC(4,2) NOT NULL
        CHECK (quality_score >= 0 AND quality_score <= 10),
    overall_confidence NUMERIC(4,2) NOT NULL
        CHECK (overall_confidence >= 0 AND overall_confidence <= 1),

    -- Assessment details (JSONB for flexibility)
    strengths TEXT[],
    limitations TEXT[],
    confidence_explanation TEXT,

    -- Document metadata (denormalized for convenience)
    document_title TEXT,
    pmid TEXT,
    doi TEXT,

    -- One assessment per (document, agent_version, model_name, prompt_hash) combination
    UNIQUE(document_id, agent_version, model_name, prompt_hash)
);

-- Indexes for efficient lookups
CREATE INDEX IF NOT EXISTS idx_study_assessments_document ON quality_assessment.study_assessments(document_id);
CREATE INDEX IF NOT EXISTS idx_study_assessments_version ON quality_assessment.study_assessments(agent_version);
CREATE INDEX IF NOT EXISTS idx_study_assessments_study_type ON quality_assessment.study_assessments(study_type);
CREATE INDEX IF NOT EXISTS idx_study_assessments_evidence_level ON quality_assessment.study_assessments(evidence_level);
CREATE INDEX IF NOT EXISTS idx_study_assessments_quality ON quality_assessment.study_assessments(quality_score DESC);

COMMENT ON TABLE quality_assessment.study_assessments IS 'Cached study design and quality assessments';
COMMENT ON COLUMN quality_assessment.study_assessments.assessment_id IS 'Unique identifier for this assessment';
COMMENT ON COLUMN quality_assessment.study_assessments.document_id IS 'Reference to assessed document';
COMMENT ON COLUMN quality_assessment.study_assessments.agent_version IS 'Version of StudyAssessmentAgent';
COMMENT ON COLUMN quality_assessment.study_assessments.model_name IS 'LLM model used (e.g., gpt-oss:20b)';
COMMENT ON COLUMN quality_assessment.study_assessments.model_parameters IS 'Model parameters (temperature, top_p, etc.)';
COMMENT ON COLUMN quality_assessment.study_assessments.prompt_hash IS 'Hash of prompt template for cache invalidation';

-- ============================================================================
-- 2. pico_extractions - PICO component extractions
-- ============================================================================

CREATE TABLE IF NOT EXISTS quality_assessment.pico_extractions (
    extraction_id SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES public.document(id),
    extracted_at TIMESTAMP NOT NULL DEFAULT NOW(),

    -- Versioning metadata
    agent_version TEXT NOT NULL,
    model_name TEXT NOT NULL,
    model_parameters JSONB NOT NULL DEFAULT '{}'::JSONB,
    prompt_hash TEXT,

    -- Suitability assessment
    is_suitable BOOLEAN NOT NULL,
    suitability_rationale TEXT,

    -- PICO components (NULL if not suitable)
    population TEXT,
    population_confidence NUMERIC(3,2) CHECK (population_confidence >= 0 AND population_confidence <= 1),

    intervention TEXT,
    intervention_confidence NUMERIC(3,2) CHECK (intervention_confidence >= 0 AND intervention_confidence <= 1),

    comparison TEXT,
    comparison_confidence NUMERIC(3,2) CHECK (comparison_confidence >= 0 AND comparison_confidence <= 1),

    outcome TEXT,
    outcome_confidence NUMERIC(3,2) CHECK (outcome_confidence >= 0 AND outcome_confidence <= 1),

    -- Overall assessment
    overall_confidence NUMERIC(3,2) CHECK (overall_confidence >= 0 AND overall_confidence <= 1),
    interpretation TEXT,

    -- Document metadata
    document_title TEXT,
    pmid TEXT,
    doi TEXT,

    -- One extraction per (document, agent_version, model_name, prompt_hash) combination
    UNIQUE(document_id, agent_version, model_name, prompt_hash)
);

-- Indexes for efficient lookups
CREATE INDEX IF NOT EXISTS idx_pico_extractions_document ON quality_assessment.pico_extractions(document_id);
CREATE INDEX IF NOT EXISTS idx_pico_extractions_version ON quality_assessment.pico_extractions(agent_version);
CREATE INDEX IF NOT EXISTS idx_pico_extractions_suitable ON quality_assessment.pico_extractions(is_suitable);

COMMENT ON TABLE quality_assessment.pico_extractions IS 'Cached PICO component extractions for intervention studies';
COMMENT ON COLUMN quality_assessment.pico_extractions.extraction_id IS 'Unique identifier for this extraction';
COMMENT ON COLUMN quality_assessment.pico_extractions.document_id IS 'Reference to assessed document';
COMMENT ON COLUMN quality_assessment.pico_extractions.is_suitable IS 'Whether PICO extraction is applicable to this study';
COMMENT ON COLUMN quality_assessment.pico_extractions.suitability_rationale IS 'Explanation for suitability determination';

-- ============================================================================
-- 3. prisma_assessments - PRISMA 2020 compliance assessments
-- ============================================================================

CREATE TABLE IF NOT EXISTS quality_assessment.prisma_assessments (
    assessment_id SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES public.document(id),
    assessed_at TIMESTAMP NOT NULL DEFAULT NOW(),

    -- Versioning metadata
    agent_version TEXT NOT NULL,
    model_name TEXT NOT NULL,
    model_parameters JSONB NOT NULL DEFAULT '{}'::JSONB,
    prompt_hash TEXT,

    -- Suitability assessment
    is_suitable BOOLEAN NOT NULL,
    suitability_rationale TEXT,
    study_type TEXT,  -- Detected study type for suitability check

    -- PRISMA compliance (NULL if not suitable)
    items_assessed INTEGER CHECK (items_assessed >= 0 AND items_assessed <= 27),
    items_reported INTEGER CHECK (items_reported >= 0 AND items_reported <= 27),
    compliance_score NUMERIC(5,2) CHECK (compliance_score >= 0 AND compliance_score <= 100),

    -- Item-level assessments (JSONB array of {item_number, status, rationale})
    item_assessments JSONB,

    -- Overall assessment
    overall_assessment TEXT,
    strengths TEXT[],
    weaknesses TEXT[],

    -- Document metadata
    document_title TEXT,
    pmid TEXT,
    doi TEXT,

    -- One assessment per (document, agent_version, model_name, prompt_hash) combination
    UNIQUE(document_id, agent_version, model_name, prompt_hash)
);

-- Indexes for efficient lookups
CREATE INDEX IF NOT EXISTS idx_prisma_assessments_document ON quality_assessment.prisma_assessments(document_id);
CREATE INDEX IF NOT EXISTS idx_prisma_assessments_version ON quality_assessment.prisma_assessments(agent_version);
CREATE INDEX IF NOT EXISTS idx_prisma_assessments_suitable ON quality_assessment.prisma_assessments(is_suitable);
CREATE INDEX IF NOT EXISTS idx_prisma_assessments_compliance ON quality_assessment.prisma_assessments(compliance_score DESC);

COMMENT ON TABLE quality_assessment.prisma_assessments IS 'Cached PRISMA 2020 compliance assessments for systematic reviews';
COMMENT ON COLUMN quality_assessment.prisma_assessments.assessment_id IS 'Unique identifier for this assessment';
COMMENT ON COLUMN quality_assessment.prisma_assessments.document_id IS 'Reference to assessed document';
COMMENT ON COLUMN quality_assessment.prisma_assessments.is_suitable IS 'Whether PRISMA assessment is applicable (systematic review/meta-analysis)';
COMMENT ON COLUMN quality_assessment.prisma_assessments.items_assessed IS 'Number of PRISMA items assessed (out of 27)';
COMMENT ON COLUMN quality_assessment.prisma_assessments.compliance_score IS 'Overall compliance score (0-100%)';

-- ============================================================================
-- Views for Convenient Queries
-- ============================================================================

-- View: Latest study assessment per document
CREATE OR REPLACE VIEW quality_assessment.v_latest_study_assessments AS
SELECT DISTINCT ON (document_id)
    assessment_id,
    document_id,
    assessed_at,
    agent_version,
    model_name,
    study_type,
    study_design,
    quality_score,
    overall_confidence,
    evidence_level
FROM quality_assessment.study_assessments
ORDER BY document_id, assessed_at DESC;

COMMENT ON VIEW quality_assessment.v_latest_study_assessments IS 'Most recent study assessment for each document';

-- View: Latest PICO extraction per document
CREATE OR REPLACE VIEW quality_assessment.v_latest_pico_extractions AS
SELECT DISTINCT ON (document_id)
    extraction_id,
    document_id,
    extracted_at,
    agent_version,
    model_name,
    is_suitable,
    population,
    intervention,
    comparison,
    outcome,
    overall_confidence
FROM quality_assessment.pico_extractions
ORDER BY document_id, extracted_at DESC;

COMMENT ON VIEW quality_assessment.v_latest_pico_extractions IS 'Most recent PICO extraction for each document';

-- View: Latest PRISMA assessment per document
CREATE OR REPLACE VIEW quality_assessment.v_latest_prisma_assessments AS
SELECT DISTINCT ON (document_id)
    assessment_id,
    document_id,
    assessed_at,
    agent_version,
    model_name,
    is_suitable,
    compliance_score,
    items_reported,
    items_assessed
FROM quality_assessment.prisma_assessments
ORDER BY document_id, assessed_at DESC;

COMMENT ON VIEW quality_assessment.v_latest_prisma_assessments IS 'Most recent PRISMA assessment for each document';

-- View: Complete quality profile per document (joins latest assessments)
CREATE OR REPLACE VIEW quality_assessment.v_document_quality_profiles AS
SELECT
    d.id as document_id,
    d.title,
    d.external_id as pmid,
    d.doi,
    sa.study_type,
    sa.quality_score,
    sa.overall_confidence as study_confidence,
    pico.is_suitable as pico_applicable,
    pico.overall_confidence as pico_confidence,
    prisma.is_suitable as prisma_applicable,
    prisma.compliance_score as prisma_score
FROM public.document d
LEFT JOIN quality_assessment.v_latest_study_assessments sa ON sa.document_id = d.id
LEFT JOIN quality_assessment.v_latest_pico_extractions pico ON pico.document_id = d.id
LEFT JOIN quality_assessment.v_latest_prisma_assessments prisma ON prisma.document_id = d.id;

COMMENT ON VIEW quality_assessment.v_document_quality_profiles IS 'Complete quality profile combining all assessment types';

-- ============================================================================
-- Utility Functions
-- ============================================================================

-- Function: Get cached study assessment
CREATE OR REPLACE FUNCTION quality_assessment.get_study_assessment(
    p_document_id INTEGER,
    p_agent_version TEXT,
    p_model_name TEXT,
    p_prompt_hash TEXT DEFAULT NULL
)
RETURNS TABLE (
    assessment_id INTEGER,
    study_type TEXT,
    study_design TEXT,
    quality_score NUMERIC,
    overall_confidence NUMERIC,
    evidence_level TEXT,
    strengths TEXT[],
    limitations TEXT[],
    assessed_at TIMESTAMP
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        sa.assessment_id,
        sa.study_type,
        sa.study_design,
        sa.quality_score,
        sa.overall_confidence,
        sa.evidence_level,
        sa.strengths,
        sa.limitations,
        sa.assessed_at
    FROM quality_assessment.study_assessments sa
    WHERE sa.document_id = p_document_id
      AND sa.agent_version = p_agent_version
      AND sa.model_name = p_model_name
      AND (p_prompt_hash IS NULL OR sa.prompt_hash = p_prompt_hash)
    ORDER BY sa.assessed_at DESC
    LIMIT 1;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION quality_assessment.get_study_assessment IS 'Retrieve cached study assessment by document and version';

-- Function: Get cached PICO extraction
CREATE OR REPLACE FUNCTION quality_assessment.get_pico_extraction(
    p_document_id INTEGER,
    p_agent_version TEXT,
    p_model_name TEXT,
    p_prompt_hash TEXT DEFAULT NULL
)
RETURNS TABLE (
    extraction_id INTEGER,
    is_suitable BOOLEAN,
    population TEXT,
    intervention TEXT,
    comparison TEXT,
    outcome TEXT,
    overall_confidence NUMERIC,
    extracted_at TIMESTAMP
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        pe.extraction_id,
        pe.is_suitable,
        pe.population,
        pe.intervention,
        pe.comparison,
        pe.outcome,
        pe.overall_confidence,
        pe.extracted_at
    FROM quality_assessment.pico_extractions pe
    WHERE pe.document_id = p_document_id
      AND pe.agent_version = p_agent_version
      AND pe.model_name = p_model_name
      AND (p_prompt_hash IS NULL OR pe.prompt_hash = p_prompt_hash)
    ORDER BY pe.extracted_at DESC
    LIMIT 1;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION quality_assessment.get_pico_extraction IS 'Retrieve cached PICO extraction by document and version';

-- Function: Get cached PRISMA assessment
CREATE OR REPLACE FUNCTION quality_assessment.get_prisma_assessment(
    p_document_id INTEGER,
    p_agent_version TEXT,
    p_model_name TEXT,
    p_prompt_hash TEXT DEFAULT NULL
)
RETURNS TABLE (
    assessment_id INTEGER,
    is_suitable BOOLEAN,
    compliance_score NUMERIC,
    items_assessed INTEGER,
    items_reported INTEGER,
    item_assessments JSONB,
    assessed_at TIMESTAMP
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        pa.assessment_id,
        pa.is_suitable,
        pa.compliance_score,
        pa.items_assessed,
        pa.items_reported,
        pa.item_assessments,
        pa.assessed_at
    FROM quality_assessment.prisma_assessments pa
    WHERE pa.document_id = p_document_id
      AND pa.agent_version = p_agent_version
      AND pa.model_name = p_model_name
      AND (p_prompt_hash IS NULL OR pa.prompt_hash = p_prompt_hash)
    ORDER BY pa.assessed_at DESC
    LIMIT 1;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION quality_assessment.get_prisma_assessment IS 'Retrieve cached PRISMA assessment by document and version';

-- ============================================================================
-- Cache Statistics Functions
-- ============================================================================

-- Function: Get cache statistics
CREATE OR REPLACE FUNCTION quality_assessment.get_cache_stats()
RETURNS TABLE (
    assessment_type TEXT,
    total_cached INTEGER,
    unique_documents INTEGER,
    unique_versions INTEGER,
    avg_assessments_per_document NUMERIC
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        'study_assessment'::TEXT,
        COUNT(*)::INTEGER,
        COUNT(DISTINCT document_id)::INTEGER,
        COUNT(DISTINCT agent_version)::INTEGER,
        ROUND(COUNT(*)::NUMERIC / NULLIF(COUNT(DISTINCT document_id), 0), 2)
    FROM quality_assessment.study_assessments
    UNION ALL
    SELECT
        'pico_extraction'::TEXT,
        COUNT(*)::INTEGER,
        COUNT(DISTINCT document_id)::INTEGER,
        COUNT(DISTINCT agent_version)::INTEGER,
        ROUND(COUNT(*)::NUMERIC / NULLIF(COUNT(DISTINCT document_id), 0), 2)
    FROM quality_assessment.pico_extractions
    UNION ALL
    SELECT
        'prisma_assessment'::TEXT,
        COUNT(*)::INTEGER,
        COUNT(DISTINCT document_id)::INTEGER,
        COUNT(DISTINCT agent_version)::INTEGER,
        ROUND(COUNT(*)::NUMERIC / NULLIF(COUNT(DISTINCT document_id), 0), 2)
    FROM quality_assessment.prisma_assessments;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION quality_assessment.get_cache_stats IS 'Get caching statistics for all assessment types';

-- ============================================================================
-- Migration Complete
-- ============================================================================

COMMIT;

-- Log successful migration
DO $$
BEGIN
    RAISE NOTICE 'Quality Assessment Caching schema migration completed successfully';
    RAISE NOTICE 'Created schema: quality_assessment';
    RAISE NOTICE 'Created tables: 3 (study_assessments, pico_extractions, prisma_assessments)';
    RAISE NOTICE 'Created views: 4';
    RAISE NOTICE 'Created functions: 4';
END $$;
