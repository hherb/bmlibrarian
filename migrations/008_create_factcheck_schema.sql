-- Migration: Create Factcheck Schema for Biomedical Statement Verification
-- Description: Creates factcheck schema for auditing biomedical statements against literature
-- Author: BMLibrarian
-- Date: 2025-11-12

-- ============================================================================
-- Create factcheck schema
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS factcheck;

-- ============================================================================
-- 1. Statements - Biomedical statements to be fact-checked
-- ============================================================================

CREATE TABLE factcheck.statements (
    statement_id BIGSERIAL PRIMARY KEY,
    statement_text TEXT NOT NULL UNIQUE,
    input_statement_id TEXT,  -- Original ID from training data (e.g., PMID)
    expected_answer TEXT CHECK (expected_answer IN ('yes', 'no', 'maybe')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_file TEXT,
    review_status TEXT NOT NULL DEFAULT 'pending' CHECK (review_status IN ('pending', 'in_review', 'completed', 'flagged'))
);

CREATE INDEX idx_factcheck_statements_text ON factcheck.statements USING hash(statement_text);
CREATE INDEX idx_factcheck_statements_input_id ON factcheck.statements(input_statement_id);
CREATE INDEX idx_factcheck_statements_review_status ON factcheck.statements(review_status);

COMMENT ON TABLE factcheck.statements IS 'Biomedical statements from LLM training data to be fact-checked';
COMMENT ON COLUMN factcheck.statements.statement_text IS 'The biomedical statement to verify (unique)';
COMMENT ON COLUMN factcheck.statements.input_statement_id IS 'Original ID from source data (e.g., PMID, dataset ID)';
COMMENT ON COLUMN factcheck.statements.expected_answer IS 'Ground truth label from training data (if available)';

-- ============================================================================
-- 2. Annotators - Human reviewers
-- ============================================================================

CREATE TABLE factcheck.annotators (
    annotator_id BIGSERIAL PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    full_name TEXT,
    email TEXT,
    expertise_level TEXT CHECK (expertise_level IN ('expert', 'intermediate', 'novice')),
    institution TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_factcheck_annotators_username ON factcheck.annotators(username);

COMMENT ON TABLE factcheck.annotators IS 'Human annotators who review fact-checking results';
COMMENT ON COLUMN factcheck.annotators.expertise_level IS 'Annotator expertise level for inter-rater reliability analysis';

-- ============================================================================
-- 3. AI Evaluations - AI-generated fact-check evaluations
-- ============================================================================

CREATE TABLE factcheck.ai_evaluations (
    evaluation_id BIGSERIAL PRIMARY KEY,
    statement_id BIGINT NOT NULL REFERENCES factcheck.statements(statement_id) ON DELETE CASCADE,
    evaluation TEXT NOT NULL CHECK (evaluation IN ('yes', 'no', 'maybe', 'error')),
    reason TEXT NOT NULL,
    confidence TEXT CHECK (confidence IN ('high', 'medium', 'low')),
    documents_reviewed INTEGER NOT NULL DEFAULT 0,
    supporting_citations INTEGER NOT NULL DEFAULT 0,
    contradicting_citations INTEGER NOT NULL DEFAULT 0,
    neutral_citations INTEGER NOT NULL DEFAULT 0,
    matches_expected BOOLEAN,
    evaluated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    model_used TEXT,
    model_version TEXT,
    agent_config JSONB,  -- Configuration snapshot for reproducibility
    session_id TEXT,
    version INTEGER NOT NULL DEFAULT 1,  -- Support multiple evaluations per statement
    UNIQUE (statement_id, version)
);

CREATE INDEX idx_factcheck_ai_eval_statement ON factcheck.ai_evaluations(statement_id, version DESC);
CREATE INDEX idx_factcheck_ai_eval_session ON factcheck.ai_evaluations(session_id);
CREATE INDEX idx_factcheck_ai_eval_evaluation ON factcheck.ai_evaluations(evaluation);
CREATE INDEX idx_factcheck_ai_eval_matches ON factcheck.ai_evaluations(matches_expected) WHERE matches_expected IS NOT NULL;

COMMENT ON TABLE factcheck.ai_evaluations IS 'AI-generated fact-check evaluations with versioning support';
COMMENT ON COLUMN factcheck.ai_evaluations.version IS 'Version number - allows re-evaluation with different models/configs';
COMMENT ON COLUMN factcheck.ai_evaluations.matches_expected IS 'Whether AI evaluation matches expected_answer (for accuracy analysis)';
COMMENT ON COLUMN factcheck.ai_evaluations.agent_config IS 'Complete agent configuration for reproducibility';

-- ============================================================================
-- 4. Evidence - Literature citations supporting evaluations
-- ============================================================================

CREATE TABLE factcheck.evidence (
    evidence_id BIGSERIAL PRIMARY KEY,
    evaluation_id BIGINT NOT NULL REFERENCES factcheck.ai_evaluations(evaluation_id) ON DELETE CASCADE,
    citation_text TEXT NOT NULL,
    document_id INTEGER NOT NULL REFERENCES document(id),  -- FK to public.document - NO DUPLICATION!
    pmid TEXT,  -- Denormalized from document for quick access
    doi TEXT,   -- Denormalized from document for quick access
    relevance_score REAL CHECK (relevance_score BETWEEN 0.0 AND 5.0),
    supports_statement TEXT CHECK (supports_statement IN ('supports', 'contradicts', 'neutral')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_factcheck_evidence_evaluation ON factcheck.evidence(evaluation_id);
CREATE INDEX idx_factcheck_evidence_document ON factcheck.evidence(document_id);
CREATE INDEX idx_factcheck_evidence_stance ON factcheck.evidence(supports_statement);

COMMENT ON TABLE factcheck.evidence IS 'Literature citations extracted as evidence - references public.document table';
COMMENT ON COLUMN factcheck.evidence.document_id IS 'FK to public.document(id) - ensures evidence links to real documents';
COMMENT ON COLUMN factcheck.evidence.citation_text IS 'Extracted passage from the document abstract';
COMMENT ON COLUMN factcheck.evidence.pmid IS 'Denormalized PMID for convenience (source: document.external_id)';
COMMENT ON COLUMN factcheck.evidence.supports_statement IS 'Whether citation supports, contradicts, or is neutral to statement';

-- ============================================================================
-- 5. Human Annotations - Human reviewer annotations
-- ============================================================================

CREATE TABLE factcheck.human_annotations (
    annotation_id BIGSERIAL PRIMARY KEY,
    statement_id BIGINT NOT NULL REFERENCES factcheck.statements(statement_id) ON DELETE CASCADE,
    annotator_id BIGINT NOT NULL REFERENCES factcheck.annotators(annotator_id) ON DELETE CASCADE,
    annotation TEXT NOT NULL CHECK (annotation IN ('yes', 'no', 'maybe', 'unclear')),
    explanation TEXT,
    confidence TEXT CHECK (confidence IN ('high', 'medium', 'low')),
    review_duration_seconds INTEGER,  -- Time spent reviewing (for quality metrics)
    review_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    session_id TEXT,
    UNIQUE (statement_id, annotator_id)  -- One annotation per annotator per statement
);

CREATE INDEX idx_factcheck_human_ann_statement ON factcheck.human_annotations(statement_id);
CREATE INDEX idx_factcheck_human_ann_annotator ON factcheck.human_annotations(annotator_id);
CREATE INDEX idx_factcheck_human_ann_annotation ON factcheck.human_annotations(annotation);

COMMENT ON TABLE factcheck.human_annotations IS 'Human annotations for inter-rater reliability and ground truth validation';
COMMENT ON COLUMN factcheck.human_annotations.review_duration_seconds IS 'Review time for quality analysis and fatigue detection';

-- ============================================================================
-- 6. Processing Metadata - Batch processing sessions
-- ============================================================================

CREATE TABLE factcheck.processing_metadata (
    metadata_id BIGSERIAL PRIMARY KEY,
    session_id TEXT UNIQUE NOT NULL,
    input_file TEXT NOT NULL,
    output_file TEXT,
    total_statements INTEGER NOT NULL,
    processed_statements INTEGER NOT NULL DEFAULT 0,
    start_time TIMESTAMPTZ NOT NULL,
    end_time TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'completed', 'failed', 'cancelled')),
    error_message TEXT,
    config_snapshot JSONB
);

CREATE INDEX idx_factcheck_processing_session ON factcheck.processing_metadata(session_id);
CREATE INDEX idx_factcheck_processing_status ON factcheck.processing_metadata(status);
CREATE INDEX idx_factcheck_processing_time ON factcheck.processing_metadata(start_time DESC);

COMMENT ON TABLE factcheck.processing_metadata IS 'Tracks batch processing sessions for monitoring and resumption';
COMMENT ON COLUMN factcheck.processing_metadata.config_snapshot IS 'Complete configuration snapshot for reproducibility';

-- ============================================================================
-- 7. Export History - Track data exports
-- ============================================================================

CREATE TABLE factcheck.export_history (
    export_id BIGSERIAL PRIMARY KEY,
    export_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    export_type TEXT NOT NULL CHECK (export_type IN ('full', 'ai_only', 'human_annotated', 'summary')),
    output_file TEXT,
    statement_count INTEGER NOT NULL,
    requested_by TEXT,
    filters_applied JSONB
);

CREATE INDEX idx_factcheck_export_date ON factcheck.export_history(export_date DESC);
CREATE INDEX idx_factcheck_export_type ON factcheck.export_history(export_type);

COMMENT ON TABLE factcheck.export_history IS 'Audit trail of data exports for compliance and tracking';

-- ============================================================================
-- Helper Views
-- ============================================================================

-- View: Complete fact-check results with AI and human annotations
CREATE VIEW factcheck.v_complete_results AS
SELECT
    s.statement_id,
    s.statement_text,
    s.input_statement_id,
    s.expected_answer,
    s.review_status,
    ae.evaluation_id,
    ae.evaluation as ai_evaluation,
    ae.reason as ai_reason,
    ae.confidence as ai_confidence,
    ae.documents_reviewed,
    ae.supporting_citations,
    ae.contradicting_citations,
    ae.neutral_citations,
    ae.matches_expected,
    ae.model_used,
    ae.evaluated_at,
    COUNT(DISTINCT ha.annotation_id) as human_annotation_count,
    ARRAY_AGG(DISTINCT ha.annotation) FILTER (WHERE ha.annotation IS NOT NULL) as human_annotations,
    COUNT(DISTINCT e.evidence_id) as evidence_count
FROM factcheck.statements s
LEFT JOIN factcheck.ai_evaluations ae ON s.statement_id = ae.statement_id AND ae.version = (
    SELECT MAX(version) FROM factcheck.ai_evaluations WHERE statement_id = s.statement_id
)
LEFT JOIN factcheck.human_annotations ha ON s.statement_id = ha.statement_id
LEFT JOIN factcheck.evidence e ON ae.evaluation_id = e.evaluation_id
GROUP BY s.statement_id, s.statement_text, s.input_statement_id, s.expected_answer, s.review_status,
         ae.evaluation_id, ae.evaluation, ae.reason, ae.confidence, ae.documents_reviewed,
         ae.supporting_citations, ae.contradicting_citations, ae.neutral_citations,
         ae.matches_expected, ae.model_used, ae.evaluated_at;

COMMENT ON VIEW factcheck.v_complete_results IS 'Complete view of fact-check results with AI and human annotations';

-- View: Statements needing AI evaluation
CREATE VIEW factcheck.v_statements_needing_evaluation AS
SELECT s.*
FROM factcheck.statements s
LEFT JOIN factcheck.ai_evaluations ae ON s.statement_id = ae.statement_id
WHERE ae.evaluation_id IS NULL;

COMMENT ON VIEW factcheck.v_statements_needing_evaluation IS 'Statements without AI evaluations - used for incremental processing';

-- View: Inter-annotator agreement analysis
CREATE VIEW factcheck.v_inter_annotator_agreement AS
SELECT
    ha1.statement_id,
    s.statement_text,
    ha1.annotator_id as annotator1_id,
    a1.username as annotator1_username,
    ha1.annotation as annotator1_annotation,
    ha2.annotator_id as annotator2_id,
    a2.username as annotator2_username,
    ha2.annotation as annotator2_annotation,
    CASE WHEN ha1.annotation = ha2.annotation THEN TRUE ELSE FALSE END as agreement
FROM factcheck.human_annotations ha1
JOIN factcheck.human_annotations ha2 ON ha1.statement_id = ha2.statement_id AND ha1.annotator_id < ha2.annotator_id
JOIN factcheck.statements s ON ha1.statement_id = s.statement_id
JOIN factcheck.annotators a1 ON ha1.annotator_id = a1.annotator_id
JOIN factcheck.annotators a2 ON ha2.annotator_id = a2.annotator_id;

COMMENT ON VIEW factcheck.v_inter_annotator_agreement IS 'Pairwise inter-annotator agreement for reliability analysis';

-- View: Model accuracy analysis
CREATE VIEW factcheck.v_model_accuracy AS
SELECT
    model_used,
    COUNT(*) as total_evaluations,
    SUM(CASE WHEN matches_expected = TRUE THEN 1 ELSE 0 END) as correct_evaluations,
    SUM(CASE WHEN matches_expected = FALSE THEN 1 ELSE 0 END) as incorrect_evaluations,
    ROUND(100.0 * SUM(CASE WHEN matches_expected = TRUE THEN 1 ELSE 0 END) / COUNT(*), 2) as accuracy_percentage,
    SUM(CASE WHEN evaluation = 'yes' THEN 1 ELSE 0 END) as yes_count,
    SUM(CASE WHEN evaluation = 'no' THEN 1 ELSE 0 END) as no_count,
    SUM(CASE WHEN evaluation = 'maybe' THEN 1 ELSE 0 END) as maybe_count,
    AVG(documents_reviewed) as avg_documents_reviewed,
    AVG(supporting_citations + contradicting_citations + neutral_citations) as avg_total_citations
FROM factcheck.ai_evaluations
WHERE matches_expected IS NOT NULL
GROUP BY model_used;

COMMENT ON VIEW factcheck.v_model_accuracy IS 'Model performance metrics for evaluation quality analysis';

-- ============================================================================
-- Helper Functions
-- ============================================================================

-- Function: Get or create statement (for upsert operations)
CREATE OR REPLACE FUNCTION factcheck.get_or_create_statement(
    p_statement_text TEXT,
    p_input_statement_id TEXT DEFAULT NULL,
    p_expected_answer TEXT DEFAULT NULL,
    p_source_file TEXT DEFAULT NULL
) RETURNS BIGINT AS $$
DECLARE
    v_statement_id BIGINT;
BEGIN
    -- Try to find existing statement
    SELECT statement_id INTO v_statement_id
    FROM factcheck.statements
    WHERE statement_text = p_statement_text;

    -- If not found, create new one
    IF v_statement_id IS NULL THEN
        INSERT INTO factcheck.statements (statement_text, input_statement_id, expected_answer, source_file)
        VALUES (p_statement_text, p_input_statement_id, p_expected_answer, p_source_file)
        RETURNING statement_id INTO v_statement_id;
    END IF;

    RETURN v_statement_id;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION factcheck.get_or_create_statement IS 'Upsert statement - returns existing or creates new statement';

-- Function: Check if statement has AI evaluation
CREATE OR REPLACE FUNCTION factcheck.has_ai_evaluation(
    p_statement_id BIGINT
) RETURNS BOOLEAN AS $$
DECLARE
    v_exists BOOLEAN;
BEGIN
    SELECT EXISTS(
        SELECT 1 FROM factcheck.ai_evaluations
        WHERE statement_id = p_statement_id
    ) INTO v_exists;

    RETURN v_exists;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION factcheck.has_ai_evaluation IS 'Check if statement already has AI evaluation - for incremental processing';

-- Function: Get statements needing evaluation
CREATE OR REPLACE FUNCTION factcheck.get_statements_needing_evaluation(
    p_statement_texts TEXT[]
) RETURNS TABLE(statement_text TEXT) AS $$
BEGIN
    RETURN QUERY
    SELECT s.statement_text
    FROM factcheck.statements s
    LEFT JOIN factcheck.ai_evaluations ae ON s.statement_id = ae.statement_id
    WHERE s.statement_text = ANY(p_statement_texts)
      AND ae.evaluation_id IS NULL;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION factcheck.get_statements_needing_evaluation IS 'Returns statements from list that need AI evaluation - for incremental mode';

-- Function: Calculate inter-annotator agreement
CREATE OR REPLACE FUNCTION factcheck.calculate_inter_annotator_agreement()
RETURNS TABLE(
    total_pairs INTEGER,
    agreements INTEGER,
    disagreements INTEGER,
    agreement_percentage NUMERIC
) AS $$
DECLARE
    v_total_pairs INTEGER;
    v_agreements INTEGER;
BEGIN
    -- Count total annotation pairs
    SELECT COUNT(*) INTO v_total_pairs
    FROM factcheck.v_inter_annotator_agreement;

    -- Count agreements
    SELECT COUNT(*) INTO v_agreements
    FROM factcheck.v_inter_annotator_agreement
    WHERE agreement = TRUE;

    RETURN QUERY
    SELECT
        v_total_pairs,
        v_agreements,
        v_total_pairs - v_agreements as disagreements,
        CASE
            WHEN v_total_pairs > 0 THEN ROUND(100.0 * v_agreements / v_total_pairs, 2)
            ELSE 0.0
        END as agreement_percentage;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION factcheck.calculate_inter_annotator_agreement IS 'Calculate inter-annotator agreement statistics';

-- ============================================================================
-- Resume Functionality Support
-- ============================================================================

-- Function: Get resume statistics for a session
CREATE OR REPLACE FUNCTION factcheck.get_resume_stats(
    p_session_id TEXT
) RETURNS TABLE(
    total_statements INTEGER,
    processed_statements INTEGER,
    remaining_statements INTEGER,
    completion_percentage NUMERIC
) AS $$
DECLARE
    v_total INTEGER;
    v_processed INTEGER;
BEGIN
    -- Get totals from processing_metadata
    SELECT
        pm.total_statements,
        pm.processed_statements
    INTO v_total, v_processed
    FROM factcheck.processing_metadata pm
    WHERE pm.session_id = p_session_id;

    RETURN QUERY
    SELECT
        v_total,
        v_processed,
        v_total - v_processed as remaining,
        CASE
            WHEN v_total > 0 THEN ROUND(100.0 * v_processed / v_total, 2)
            ELSE 0.0
        END as completion_pct;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION factcheck.get_resume_stats IS 'Get progress statistics for resume functionality';

-- ============================================================================
-- Grants (adjust based on your user setup)
-- ============================================================================

-- Grant usage on schema to your application user
-- GRANT USAGE ON SCHEMA factcheck TO your_app_user;
-- GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA factcheck TO your_app_user;
-- GRANT USAGE ON ALL SEQUENCES IN SCHEMA factcheck TO your_app_user;
-- GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA factcheck TO your_app_user;

-- ============================================================================
-- Migration Complete
-- ============================================================================
