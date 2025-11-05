-- Migration: Create Audit Schema for Research Workflow Tracking
-- Description: Creates audit schema with research-question-centric design for complete workflow tracking
-- Author: BMLibrarian
-- Date: 2025-11-05

-- ============================================================================
-- Create audit schema
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS audit;

-- ============================================================================
-- 1. Research Questions - Central anchor table
-- ============================================================================

CREATE TABLE audit.research_questions (
    research_question_id BIGSERIAL PRIMARY KEY,
    question_text TEXT NOT NULL UNIQUE,
    question_hash TEXT NOT NULL,
    user_id INTEGER,  -- Optional FK to public.users
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_activity_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    total_sessions INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'archived', 'superseded')),
    notes TEXT
);

CREATE INDEX idx_research_questions_hash ON audit.research_questions(question_hash);
CREATE INDEX idx_research_questions_user_id ON audit.research_questions(user_id);
CREATE INDEX idx_research_questions_status ON audit.research_questions(status);

COMMENT ON TABLE audit.research_questions IS 'Central table for all research questions - enables resumption and deduplication';
COMMENT ON COLUMN audit.research_questions.question_hash IS 'MD5 hash of normalized question text for fast lookups';
COMMENT ON COLUMN audit.research_questions.total_sessions IS 'Number of research sessions conducted for this question';

-- ============================================================================
-- 2. Research Sessions - Multiple sessions per question
-- ============================================================================

CREATE TABLE audit.research_sessions (
    session_id BIGSERIAL PRIMARY KEY,
    research_question_id BIGINT NOT NULL REFERENCES audit.research_questions(research_question_id) ON DELETE CASCADE,
    session_type TEXT NOT NULL CHECK (session_type IN ('initial', 'expansion', 'reanalysis', 'counterfactual_only')),
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    workflow_status TEXT NOT NULL DEFAULT 'in_progress' CHECK (workflow_status IN ('in_progress', 'completed', 'failed', 'cancelled')),
    config_snapshot JSONB,
    user_notes TEXT
);

CREATE INDEX idx_research_sessions_question_id ON audit.research_sessions(research_question_id, started_at DESC);
CREATE INDEX idx_research_sessions_status ON audit.research_sessions(workflow_status);

COMMENT ON TABLE audit.research_sessions IS 'Tracks different research attempts for same question (e.g., add more documents, try different model)';
COMMENT ON COLUMN audit.research_sessions.session_type IS 'Type of research session: initial, expansion, reanalysis, or counterfactual_only';
COMMENT ON COLUMN audit.research_sessions.config_snapshot IS 'Complete configuration at session start for reproducibility';

-- ============================================================================
-- 3. Generated Queries - All database queries
-- ============================================================================

CREATE TABLE audit.generated_queries (
    query_id BIGSERIAL PRIMARY KEY,
    research_question_id BIGINT NOT NULL REFERENCES audit.research_questions(research_question_id) ON DELETE CASCADE,
    session_id BIGINT NOT NULL REFERENCES audit.research_sessions(session_id) ON DELETE CASCADE,
    model_name TEXT NOT NULL,
    temperature REAL NOT NULL,
    top_p REAL NOT NULL,
    attempt_number INTEGER NOT NULL,
    query_text TEXT NOT NULL,
    query_text_sanitized TEXT NOT NULL,
    human_edited BOOLEAN NOT NULL DEFAULT FALSE,
    original_ai_query TEXT,
    generation_time_ms REAL,
    execution_time_ms REAL,
    documents_found_count INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_generated_queries_question_id ON audit.generated_queries(research_question_id, created_at);
CREATE INDEX idx_generated_queries_session_id ON audit.generated_queries(session_id, attempt_number);
CREATE INDEX idx_generated_queries_model ON audit.generated_queries(model_name);

COMMENT ON TABLE audit.generated_queries IS 'All queries generated for research questions across all sessions';
COMMENT ON COLUMN audit.generated_queries.attempt_number IS '1st, 2nd, 3rd attempt for multi-model query generation';
COMMENT ON COLUMN audit.generated_queries.query_text_sanitized IS 'Query after syntax fixes applied';
COMMENT ON COLUMN audit.generated_queries.original_ai_query IS 'Original AI-generated query before human editing (if human_edited=true)';

-- ============================================================================
-- 4. Query Documents - Query → Document many-to-many relationship
-- ============================================================================

CREATE TABLE audit.query_documents (
    research_question_id BIGINT NOT NULL REFERENCES audit.research_questions(research_question_id) ON DELETE CASCADE,
    query_id BIGINT NOT NULL REFERENCES audit.generated_queries(query_id) ON DELETE CASCADE,
    document_id INTEGER NOT NULL,  -- FK to public.document(id)
    rank_in_results INTEGER,
    discovered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (query_id, document_id)
);

CREATE INDEX idx_query_documents_question_doc ON audit.query_documents(research_question_id, document_id);
CREATE INDEX idx_query_documents_doc_id ON audit.query_documents(document_id);

COMMENT ON TABLE audit.query_documents IS 'Tracks which queries found which documents - critical for resumption';

-- ============================================================================
-- 5. Document Scores - Relevance scoring (ONE per question+document)
-- ============================================================================

CREATE TABLE audit.document_scores (
    scoring_id BIGSERIAL PRIMARY KEY,
    research_question_id BIGINT NOT NULL REFERENCES audit.research_questions(research_question_id) ON DELETE CASCADE,
    document_id INTEGER NOT NULL,  -- FK to public.document(id)
    session_id BIGINT NOT NULL REFERENCES audit.research_sessions(session_id) ON DELETE CASCADE,
    first_query_id BIGINT NOT NULL REFERENCES audit.generated_queries(query_id),
    model_name TEXT NOT NULL,
    temperature REAL NOT NULL,
    relevance_score INTEGER NOT NULL CHECK (relevance_score BETWEEN 0 AND 5),
    reasoning TEXT,
    human_override_score INTEGER CHECK (human_override_score BETWEEN 0 AND 5),
    scored_by TEXT NOT NULL DEFAULT 'ai' CHECK (scored_by IN ('ai', 'human', 'hybrid')),
    scored_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (research_question_id, document_id)
);

CREATE INDEX idx_document_scores_question_score ON audit.document_scores(research_question_id, relevance_score DESC);
CREATE INDEX idx_document_scores_question_doc ON audit.document_scores(research_question_id, document_id);
CREATE INDEX idx_document_scores_session ON audit.document_scores(session_id);

COMMENT ON TABLE audit.document_scores IS 'ONE score per question+document combination - critical for resumption to avoid re-scoring';
COMMENT ON COLUMN audit.document_scores.first_query_id IS 'Which query first discovered this document';
COMMENT ON COLUMN audit.document_scores.human_override_score IS 'Human-adjusted relevance score (overrides AI score)';

-- ============================================================================
-- 6. Extracted Citations - Citations from documents
-- ============================================================================

CREATE TABLE audit.extracted_citations (
    citation_id BIGSERIAL PRIMARY KEY,
    research_question_id BIGINT NOT NULL REFERENCES audit.research_questions(research_question_id) ON DELETE CASCADE,
    document_id INTEGER NOT NULL,  -- FK to public.document(id)
    session_id BIGINT NOT NULL REFERENCES audit.research_sessions(session_id) ON DELETE CASCADE,
    scoring_id BIGINT NOT NULL REFERENCES audit.document_scores(scoring_id) ON DELETE CASCADE,
    model_name TEXT NOT NULL,
    temperature REAL NOT NULL,
    passage TEXT NOT NULL,
    summary TEXT NOT NULL,
    relevance_confidence REAL CHECK (relevance_confidence BETWEEN 0.0 AND 1.0),
    human_review_status TEXT CHECK (human_review_status IN ('accepted', 'rejected', 'modified')),
    extracted_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_extracted_citations_question_status ON audit.extracted_citations(research_question_id, human_review_status);
CREATE INDEX idx_extracted_citations_question_doc ON audit.extracted_citations(research_question_id, document_id);
CREATE INDEX idx_extracted_citations_session ON audit.extracted_citations(session_id);

COMMENT ON TABLE audit.extracted_citations IS 'All citations extracted for a research question - can be reused across sessions';
COMMENT ON COLUMN audit.extracted_citations.passage IS 'Direct quote/passage from the document';
COMMENT ON COLUMN audit.extracted_citations.summary IS 'AI-generated summary of the passage';
COMMENT ON COLUMN audit.extracted_citations.relevance_confidence IS 'AI confidence in citation relevance (0.0-1.0)';

-- ============================================================================
-- 7. Generated Reports - All reports for a question
-- ============================================================================

CREATE TABLE audit.generated_reports (
    report_id BIGSERIAL PRIMARY KEY,
    research_question_id BIGINT NOT NULL REFERENCES audit.research_questions(research_question_id) ON DELETE CASCADE,
    session_id BIGINT NOT NULL REFERENCES audit.research_sessions(session_id) ON DELETE CASCADE,
    report_type TEXT NOT NULL CHECK (report_type IN ('preliminary', 'comprehensive', 'counterfactual')),
    model_name TEXT NOT NULL,
    temperature REAL NOT NULL,
    citation_count INTEGER,
    report_text TEXT NOT NULL,
    report_format TEXT NOT NULL DEFAULT 'markdown',
    methodology_metadata JSONB,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    human_edited BOOLEAN NOT NULL DEFAULT FALSE,
    is_final BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX idx_generated_reports_question_date ON audit.generated_reports(research_question_id, generated_at DESC);
CREATE INDEX idx_generated_reports_question_final ON audit.generated_reports(research_question_id, is_final);
CREATE INDEX idx_generated_reports_type ON audit.generated_reports(report_type);

COMMENT ON TABLE audit.generated_reports IS 'Track report evolution for a research question over multiple sessions';
COMMENT ON COLUMN audit.generated_reports.methodology_metadata IS 'Stats about document counts, scores, processing details';
COMMENT ON COLUMN audit.generated_reports.is_final IS 'Mark the final/published version of the report';

-- ============================================================================
-- 8. Counterfactual Analyses - Contradictory evidence search
-- ============================================================================

CREATE TABLE audit.counterfactual_analyses (
    analysis_id BIGSERIAL PRIMARY KEY,
    research_question_id BIGINT NOT NULL REFERENCES audit.research_questions(research_question_id) ON DELETE CASCADE,
    session_id BIGINT NOT NULL REFERENCES audit.research_sessions(session_id) ON DELETE CASCADE,
    source_report_id BIGINT REFERENCES audit.generated_reports(report_id) ON DELETE SET NULL,
    model_name TEXT NOT NULL,
    temperature REAL NOT NULL,
    num_questions_generated INTEGER,
    num_queries_executed INTEGER,
    num_documents_found INTEGER,
    num_citations_extracted INTEGER,
    performed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_counterfactual_analyses_question ON audit.counterfactual_analyses(research_question_id, performed_at DESC);
CREATE INDEX idx_counterfactual_analyses_session ON audit.counterfactual_analyses(session_id);

COMMENT ON TABLE audit.counterfactual_analyses IS 'Track counterfactual analysis sessions for finding contradictory evidence';
COMMENT ON COLUMN audit.counterfactual_analyses.source_report_id IS 'Which report was analyzed to generate counterfactual questions';

-- ============================================================================
-- 9. Counterfactual Questions - Questions for contradictory evidence
-- ============================================================================

CREATE TABLE audit.counterfactual_questions (
    question_id BIGSERIAL PRIMARY KEY,
    research_question_id BIGINT NOT NULL REFERENCES audit.research_questions(research_question_id) ON DELETE CASCADE,
    analysis_id BIGINT NOT NULL REFERENCES audit.counterfactual_analyses(analysis_id) ON DELETE CASCADE,
    question_text TEXT NOT NULL,
    target_claim TEXT,
    priority TEXT CHECK (priority IN ('high', 'medium', 'low')),
    query_generated TEXT,
    documents_found_count INTEGER
);

CREATE INDEX idx_counterfactual_questions_question ON audit.counterfactual_questions(research_question_id, priority);
CREATE INDEX idx_counterfactual_questions_analysis ON audit.counterfactual_questions(analysis_id);

COMMENT ON TABLE audit.counterfactual_questions IS 'Individual questions generated to find contradictory evidence';
COMMENT ON COLUMN audit.counterfactual_questions.target_claim IS 'Specific claim from report this question targets';

-- ============================================================================
-- 10. Human Edits - All human interventions
-- ============================================================================

CREATE TABLE audit.human_edits (
    edit_id BIGSERIAL PRIMARY KEY,
    research_question_id BIGINT NOT NULL REFERENCES audit.research_questions(research_question_id) ON DELETE CASCADE,
    session_id BIGINT NOT NULL REFERENCES audit.research_sessions(session_id) ON DELETE CASCADE,
    edit_type TEXT NOT NULL CHECK (edit_type IN ('query_edit', 'score_override', 'citation_review', 'report_edit', 'other')),
    target_table TEXT NOT NULL,
    target_id BIGINT NOT NULL,
    original_value TEXT,
    edited_value TEXT,
    user_id INTEGER,  -- Optional FK to public.users
    edited_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    edit_reason TEXT
);

CREATE INDEX idx_human_edits_question ON audit.human_edits(research_question_id, edit_type, edited_at);
CREATE INDEX idx_human_edits_target ON audit.human_edits(target_table, target_id);
CREATE INDEX idx_human_edits_user ON audit.human_edits(user_id);

COMMENT ON TABLE audit.human_edits IS 'Complete audit trail of all human-in-the-loop edits and interventions';
COMMENT ON COLUMN audit.human_edits.target_table IS 'Name of audit table being edited (e.g., generated_queries, document_scores)';
COMMENT ON COLUMN audit.human_edits.target_id IS 'ID of the specific record being edited';

-- ============================================================================
-- 11. Workflow Steps - Workflow execution tracking
-- ============================================================================

CREATE TABLE audit.workflow_steps (
    step_id BIGSERIAL PRIMARY KEY,
    research_question_id BIGINT NOT NULL REFERENCES audit.research_questions(research_question_id) ON DELETE CASCADE,
    session_id BIGINT NOT NULL REFERENCES audit.research_sessions(session_id) ON DELETE CASCADE,
    step_name TEXT NOT NULL,
    step_status TEXT NOT NULL DEFAULT 'pending' CHECK (step_status IN ('pending', 'in_progress', 'completed', 'failed', 'skipped')),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    duration_ms REAL,
    error_message TEXT,
    execution_count INTEGER NOT NULL DEFAULT 1,
    step_data JSONB
);

CREATE INDEX idx_workflow_steps_session ON audit.workflow_steps(research_question_id, session_id, started_at);
CREATE INDEX idx_workflow_steps_status ON audit.workflow_steps(step_status);

COMMENT ON TABLE audit.workflow_steps IS 'Track execution of workflow steps (from WorkflowStep enum)';
COMMENT ON COLUMN audit.workflow_steps.step_name IS 'WorkflowStep enum value (e.g., SCORE_DOCUMENTS, EXTRACT_CITATIONS)';
COMMENT ON COLUMN audit.workflow_steps.execution_count IS 'For repeatable steps, track how many times executed';
COMMENT ON COLUMN audit.workflow_steps.step_data IS 'Custom data specific to each step type';

-- ============================================================================
-- Helper Views
-- ============================================================================

-- View: Latest session for each research question
CREATE VIEW audit.v_latest_sessions AS
SELECT DISTINCT ON (research_question_id)
    research_question_id,
    session_id,
    session_type,
    started_at,
    completed_at,
    workflow_status
FROM audit.research_sessions
ORDER BY research_question_id, started_at DESC;

COMMENT ON VIEW audit.v_latest_sessions IS 'Latest session for each research question - useful for resumption';

-- View: Document processing status per question
CREATE VIEW audit.v_document_processing_status AS
SELECT
    qd.research_question_id,
    qd.document_id,
    qd.query_id,
    qd.discovered_at,
    ds.scoring_id,
    ds.relevance_score,
    ds.scored_at,
    COUNT(ec.citation_id) as citation_count
FROM audit.query_documents qd
LEFT JOIN audit.document_scores ds
    ON qd.research_question_id = ds.research_question_id
    AND qd.document_id = ds.document_id
LEFT JOIN audit.extracted_citations ec
    ON ds.scoring_id = ec.scoring_id
GROUP BY qd.research_question_id, qd.document_id, qd.query_id, qd.discovered_at,
         ds.scoring_id, ds.relevance_score, ds.scored_at;

COMMENT ON VIEW audit.v_document_processing_status IS 'Shows processing status (discovered, scored, citations extracted) for each document per question';

-- View: Model performance summary
CREATE VIEW audit.v_model_performance AS
SELECT
    model_name,
    COUNT(DISTINCT query_id) as total_queries,
    AVG(documents_found_count) as avg_documents_per_query,
    AVG(execution_time_ms) as avg_execution_time_ms,
    SUM(CASE WHEN human_edited THEN 1 ELSE 0 END) as human_edited_count,
    COUNT(DISTINCT research_question_id) as unique_questions
FROM audit.generated_queries
GROUP BY model_name;

COMMENT ON VIEW audit.v_model_performance IS 'Performance metrics for each AI model used in query generation';

-- ============================================================================
-- Helper Functions
-- ============================================================================

-- Function: Get or create research question
CREATE OR REPLACE FUNCTION audit.get_or_create_research_question(
    p_question_text TEXT,
    p_user_id INTEGER DEFAULT NULL
) RETURNS BIGINT AS $$
DECLARE
    v_question_id BIGINT;
    v_question_hash TEXT;
BEGIN
    -- Generate hash
    v_question_hash := md5(lower(trim(p_question_text)));

    -- Try to find existing question
    SELECT research_question_id INTO v_question_id
    FROM audit.research_questions
    WHERE question_hash = v_question_hash;

    -- If not found, create new one
    IF v_question_id IS NULL THEN
        INSERT INTO audit.research_questions (question_text, question_hash, user_id)
        VALUES (p_question_text, v_question_hash, p_user_id)
        RETURNING research_question_id INTO v_question_id;
    ELSE
        -- Update last activity and increment session count
        UPDATE audit.research_questions
        SET last_activity_at = NOW(),
            total_sessions = total_sessions + 1
        WHERE research_question_id = v_question_id;
    END IF;

    RETURN v_question_id;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION audit.get_or_create_research_question IS 'Get existing or create new research question - handles deduplication';

-- Function: Get unscored documents for a question
CREATE OR REPLACE FUNCTION audit.get_unscored_document_ids(
    p_research_question_id BIGINT
) RETURNS TABLE(document_id INTEGER) AS $$
BEGIN
    RETURN QUERY
    SELECT DISTINCT qd.document_id
    FROM audit.query_documents qd
    LEFT JOIN audit.document_scores ds
        ON qd.research_question_id = ds.research_question_id
        AND qd.document_id = ds.document_id
    WHERE qd.research_question_id = p_research_question_id
      AND ds.scoring_id IS NULL;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION audit.get_unscored_document_ids IS 'Returns document IDs that need scoring for a research question - critical for resumption';

-- Function: Check if document is already scored
CREATE OR REPLACE FUNCTION audit.is_document_scored(
    p_research_question_id BIGINT,
    p_document_id INTEGER
) RETURNS BOOLEAN AS $$
DECLARE
    v_exists BOOLEAN;
BEGIN
    SELECT EXISTS(
        SELECT 1 FROM audit.document_scores
        WHERE research_question_id = p_research_question_id
          AND document_id = p_document_id
    ) INTO v_exists;

    RETURN v_exists;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION audit.is_document_scored IS 'Fast check if document already scored for question - avoids re-processing';

-- ============================================================================
-- Grants (adjust based on your user setup)
-- ============================================================================

-- Grant usage on schema to your application user
-- GRANT USAGE ON SCHEMA audit TO your_app_user;
-- GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA audit TO your_app_user;
-- GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA audit TO your_app_user;

-- ============================================================================
-- Migration Complete
-- ============================================================================
