-- Migration 029: Create transparency schema
--
-- Stores transparency assessments (LLM-generated) and structured metadata
-- from bulk imports (PubMed grants, ClinicalTrials.gov sponsors, Retraction Watch).
--
-- This migration is idempotent and safe to run multiple times.

-- Create schema
CREATE SCHEMA IF NOT EXISTS transparency;

-- ──────────────────────────────────────────────────────────────────────────────
-- Table 1: LLM-generated transparency assessments
-- ──────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS transparency.assessments (
    id SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES public.document(id),

    -- Funding disclosure
    has_funding_disclosure BOOLEAN DEFAULT FALSE,
    funding_statement TEXT,
    funding_sources TEXT[],
    is_industry_funded BOOLEAN,
    industry_funding_confidence FLOAT DEFAULT 0.0,
    funding_disclosure_quality FLOAT DEFAULT 0.0,

    -- Conflict of interest
    has_coi_disclosure BOOLEAN DEFAULT FALSE,
    coi_statement TEXT,
    conflicts_identified TEXT[],
    coi_disclosure_quality FLOAT DEFAULT 0.0,

    -- Data availability
    data_availability TEXT DEFAULT 'not_stated',
    data_availability_statement TEXT,

    -- Author contributions
    has_author_contributions BOOLEAN DEFAULT FALSE,
    contributions_statement TEXT,

    -- Trial registration
    has_trial_registration BOOLEAN DEFAULT FALSE,
    trial_registry_ids TEXT[],

    -- Overall assessment
    transparency_score FLOAT DEFAULT 0.0,
    overall_confidence FLOAT DEFAULT 0.0,
    risk_level TEXT DEFAULT 'unknown',
    risk_indicators TEXT[],
    strengths TEXT[],
    weaknesses TEXT[],

    -- Metadata from bulk imports (optional enrichment)
    is_retracted BOOLEAN,
    retraction_reason TEXT,
    trial_sponsor_class TEXT,

    -- Audit metadata
    assessed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    model_used TEXT,
    agent_version TEXT,

    CONSTRAINT unique_transparency_assessment UNIQUE (document_id)
);

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_transparency_assessments_document_id
    ON transparency.assessments(document_id);
CREATE INDEX IF NOT EXISTS idx_transparency_assessments_risk_level
    ON transparency.assessments(risk_level);
CREATE INDEX IF NOT EXISTS idx_transparency_assessments_score
    ON transparency.assessments(transparency_score);
CREATE INDEX IF NOT EXISTS idx_transparency_assessments_industry_funded
    ON transparency.assessments(is_industry_funded)
    WHERE is_industry_funded = TRUE;
CREATE INDEX IF NOT EXISTS idx_transparency_assessments_retracted
    ON transparency.assessments(is_retracted)
    WHERE is_retracted = TRUE;

-- ──────────────────────────────────────────────────────────────────────────────
-- Table 2: Structured metadata from bulk imports
-- ──────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS transparency.document_metadata (
    id SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES public.document(id),

    -- From PubMed <GrantList>
    -- Structure: [{"agency": "...", "grant_id": "...", "country": "..."}, ...]
    grants JSONB,

    -- From PubMed <PublicationTypeList>
    -- e.g., ["Clinical Trial", "Retracted Publication", "Randomized Controlled Trial"]
    publication_types TEXT[],

    -- Retraction info (from PubMed XML or Retraction Watch)
    is_retracted BOOLEAN DEFAULT FALSE,
    retraction_reason TEXT,
    retraction_date DATE,
    retraction_source TEXT,  -- 'pubmed', 'retraction_watch', etc.

    -- From PubMed <Author><AffiliationInfo>
    -- Structure: [{"author": "Smith J", "affiliations": ["Org1", "Org2"]}, ...]
    author_affiliations JSONB,

    -- From ClinicalTrials.gov bulk download
    clinical_trial_id TEXT,      -- NCT number
    trial_sponsor TEXT,
    trial_sponsor_class TEXT,    -- NIH, Industry, Other, FedGov
    trial_status TEXT,           -- Completed, Recruiting, etc.

    -- Provenance
    source TEXT,                  -- 'pubmed_bulk', 'clinicaltrials_bulk', 'retraction_watch'
    imported_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    CONSTRAINT unique_doc_metadata UNIQUE (document_id)
);

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_doc_metadata_document_id
    ON transparency.document_metadata(document_id);
CREATE INDEX IF NOT EXISTS idx_doc_metadata_retracted
    ON transparency.document_metadata(is_retracted)
    WHERE is_retracted = TRUE;
CREATE INDEX IF NOT EXISTS idx_doc_metadata_clinical_trial_id
    ON transparency.document_metadata(clinical_trial_id)
    WHERE clinical_trial_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_doc_metadata_sponsor_class
    ON transparency.document_metadata(trial_sponsor_class)
    WHERE trial_sponsor_class IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_doc_metadata_grants
    ON transparency.document_metadata USING GIN (grants)
    WHERE grants IS NOT NULL;

-- ──────────────────────────────────────────────────────────────────────────────
-- Views for convenient querying
-- ──────────────────────────────────────────────────────────────────────────────

-- Combined view joining assessments with metadata
CREATE OR REPLACE VIEW transparency.v_full_assessment AS
SELECT
    a.id AS assessment_id,
    a.document_id,
    d.title AS document_title,
    d.doi,
    d.authors,
    a.transparency_score,
    a.risk_level,
    a.has_funding_disclosure,
    a.is_industry_funded,
    a.has_coi_disclosure,
    a.data_availability,
    a.has_trial_registration,
    a.risk_indicators,
    a.strengths,
    a.weaknesses,
    COALESCE(a.is_retracted, m.is_retracted, FALSE) AS is_retracted,
    m.grants,
    m.publication_types,
    m.author_affiliations,
    m.clinical_trial_id,
    m.trial_sponsor,
    COALESCE(a.trial_sponsor_class, m.trial_sponsor_class) AS trial_sponsor_class,
    a.assessed_at,
    a.model_used
FROM transparency.assessments a
JOIN public.document d ON d.id = a.document_id
LEFT JOIN transparency.document_metadata m ON m.document_id = a.document_id;

-- Summary statistics view
CREATE OR REPLACE VIEW transparency.v_statistics AS
SELECT
    COUNT(*) AS total_assessed,
    COUNT(*) FILTER (WHERE risk_level = 'low') AS low_risk_count,
    COUNT(*) FILTER (WHERE risk_level = 'medium') AS medium_risk_count,
    COUNT(*) FILTER (WHERE risk_level = 'high') AS high_risk_count,
    COUNT(*) FILTER (WHERE risk_level = 'unknown') AS unknown_risk_count,
    AVG(transparency_score) AS avg_score,
    COUNT(*) FILTER (WHERE is_industry_funded = TRUE) AS industry_funded_count,
    COUNT(*) FILTER (WHERE has_funding_disclosure = TRUE) AS with_funding_count,
    COUNT(*) FILTER (WHERE has_coi_disclosure = TRUE) AS with_coi_count,
    COUNT(*) FILTER (WHERE has_trial_registration = TRUE) AS with_trial_reg_count,
    COUNT(*) FILTER (WHERE is_retracted = TRUE) AS retracted_count
FROM transparency.assessments;
