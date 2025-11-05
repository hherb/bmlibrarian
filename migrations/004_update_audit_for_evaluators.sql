-- Migration: Update Audit Schema to Use Evaluators
-- Description: Revises audit.document_scores to use evaluator_id from public.evaluators
--              This ensures proper tracking of who (user/model/params) scored each document
-- Author: BMLibrarian
-- Date: 2025-11-05

-- ============================================================================
-- Drop old document_scores table and recreate with evaluator_id
-- ============================================================================

DROP TABLE IF EXISTS audit.extracted_citations CASCADE;
DROP TABLE IF EXISTS audit.document_scores CASCADE;

-- ============================================================================
-- 5. Document Scores - Relevance scoring (ONE per question+document+evaluator)
-- ============================================================================

CREATE TABLE audit.document_scores (
    scoring_id BIGSERIAL PRIMARY KEY,
    research_question_id BIGINT NOT NULL REFERENCES audit.research_questions(research_question_id) ON DELETE CASCADE,
    document_id INTEGER NOT NULL,  -- FK to public.document(id)
    session_id BIGINT NOT NULL REFERENCES audit.research_sessions(session_id) ON DELETE CASCADE,
    first_query_id BIGINT NOT NULL REFERENCES audit.generated_queries(query_id),
    evaluator_id INTEGER NOT NULL REFERENCES public.evaluators(id),  -- WHO scored this (user/model/params)
    relevance_score INTEGER NOT NULL CHECK (relevance_score BETWEEN 0 AND 5),
    reasoning TEXT,
    scored_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (research_question_id, document_id, evaluator_id)  -- ONE score per question+document+evaluator
);

CREATE INDEX idx_document_scores_question_evaluator ON audit.document_scores(research_question_id, evaluator_id, relevance_score DESC);
CREATE INDEX idx_document_scores_question_doc ON audit.document_scores(research_question_id, document_id);
CREATE INDEX idx_document_scores_session ON audit.document_scores(session_id);
CREATE INDEX idx_document_scores_evaluator ON audit.document_scores(evaluator_id);

COMMENT ON TABLE audit.document_scores IS 'ONE score per question+document+evaluator combination - enables multi-evaluator scoring and resumption';
COMMENT ON COLUMN audit.document_scores.evaluator_id IS 'References public.evaluators - identifies user/model/parameters combination';
COMMENT ON COLUMN audit.document_scores.first_query_id IS 'Which query first discovered this document';

-- ============================================================================
-- 6. Extracted Citations - Citations from documents (recreate with FK to new document_scores)
-- ============================================================================

CREATE TABLE audit.extracted_citations (
    citation_id BIGSERIAL PRIMARY KEY,
    research_question_id BIGINT NOT NULL REFERENCES audit.research_questions(research_question_id) ON DELETE CASCADE,
    document_id INTEGER NOT NULL,  -- FK to public.document(id)
    session_id BIGINT NOT NULL REFERENCES audit.research_sessions(session_id) ON DELETE CASCADE,
    scoring_id BIGINT NOT NULL REFERENCES audit.document_scores(scoring_id) ON DELETE CASCADE,
    evaluator_id INTEGER NOT NULL REFERENCES public.evaluators(id),  -- WHO extracted this citation
    passage TEXT NOT NULL,
    summary TEXT NOT NULL,
    relevance_confidence REAL CHECK (relevance_confidence BETWEEN 0.0 AND 1.0),
    human_review_status TEXT CHECK (human_review_status IN ('accepted', 'rejected', 'modified')),
    extracted_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_extracted_citations_question_status ON audit.extracted_citations(research_question_id, human_review_status);
CREATE INDEX idx_extracted_citations_question_doc ON audit.extracted_citations(research_question_id, document_id);
CREATE INDEX idx_extracted_citations_session ON audit.extracted_citations(session_id);
CREATE INDEX idx_extracted_citations_evaluator ON audit.extracted_citations(evaluator_id);

COMMENT ON TABLE audit.extracted_citations IS 'All citations extracted for a research question - can be reused across sessions';
COMMENT ON COLUMN audit.extracted_citations.passage IS 'Direct quote/passage from the document';
COMMENT ON COLUMN audit.extracted_citations.summary IS 'AI-generated summary of the passage';
COMMENT ON COLUMN audit.extracted_citations.relevance_confidence IS 'AI confidence in citation relevance (0.0-1.0)';
COMMENT ON COLUMN audit.extracted_citations.evaluator_id IS 'References public.evaluators - who extracted this citation';

-- ============================================================================
-- Update helper functions to use evaluator_id
-- ============================================================================

-- Drop old functions
DROP FUNCTION IF EXISTS audit.get_unscored_document_ids(BIGINT);
DROP FUNCTION IF EXISTS audit.is_document_scored(BIGINT, INTEGER);

-- Function: Get unscored documents for a question + evaluator combination
CREATE OR REPLACE FUNCTION audit.get_unscored_document_ids(
    p_research_question_id BIGINT,
    p_evaluator_id INTEGER
) RETURNS TABLE(document_id INTEGER) AS $$
BEGIN
    RETURN QUERY
    SELECT DISTINCT qd.document_id
    FROM audit.query_documents qd
    LEFT JOIN audit.document_scores ds
        ON qd.research_question_id = ds.research_question_id
        AND qd.document_id = ds.document_id
        AND ds.evaluator_id = p_evaluator_id
    WHERE qd.research_question_id = p_research_question_id
      AND ds.scoring_id IS NULL;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION audit.get_unscored_document_ids IS 'Returns document IDs that need scoring for a research question BY THIS EVALUATOR - critical for resumption';

-- Function: Check if document is already scored by specific evaluator
CREATE OR REPLACE FUNCTION audit.is_document_scored(
    p_research_question_id BIGINT,
    p_document_id INTEGER,
    p_evaluator_id INTEGER
) RETURNS BOOLEAN AS $$
DECLARE
    v_exists BOOLEAN;
BEGIN
    SELECT EXISTS(
        SELECT 1 FROM audit.document_scores
        WHERE research_question_id = p_research_question_id
          AND document_id = p_document_id
          AND evaluator_id = p_evaluator_id
    ) INTO v_exists;

    RETURN v_exists;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION audit.is_document_scored IS 'Fast check if document already scored for question BY THIS EVALUATOR - avoids re-processing';

-- ============================================================================
-- Update generated_queries to also use evaluator_id
-- ============================================================================

ALTER TABLE audit.generated_queries
    ADD COLUMN evaluator_id INTEGER REFERENCES public.evaluators(id);

CREATE INDEX idx_generated_queries_evaluator ON audit.generated_queries(evaluator_id);

COMMENT ON COLUMN audit.generated_queries.evaluator_id IS 'References public.evaluators - which model/params generated this query';

-- For backward compatibility, keep model_name/temperature/top_p but make them nullable
ALTER TABLE audit.generated_queries
    ALTER COLUMN model_name DROP NOT NULL,
    ALTER COLUMN temperature DROP NOT NULL,
    ALTER COLUMN top_p DROP NOT NULL;

COMMENT ON COLUMN audit.generated_queries.model_name IS 'DEPRECATED: Use evaluator_id instead. Kept for backward compatibility.';

-- ============================================================================
-- Update generated_reports to use evaluator_id
-- ============================================================================

ALTER TABLE audit.generated_reports
    ADD COLUMN evaluator_id INTEGER REFERENCES public.evaluators(id);

CREATE INDEX idx_generated_reports_evaluator ON audit.generated_reports(evaluator_id);

COMMENT ON COLUMN audit.generated_reports.evaluator_id IS 'References public.evaluators - which model/params generated this report';

ALTER TABLE audit.generated_reports
    ALTER COLUMN model_name DROP NOT NULL,
    ALTER COLUMN temperature DROP NOT NULL;

COMMENT ON COLUMN audit.generated_reports.model_name IS 'DEPRECATED: Use evaluator_id instead. Kept for backward compatibility.';

-- ============================================================================
-- Update counterfactual_analyses to use evaluator_id
-- ============================================================================

ALTER TABLE audit.counterfactual_analyses
    ADD COLUMN evaluator_id INTEGER REFERENCES public.evaluators(id);

CREATE INDEX idx_counterfactual_analyses_evaluator ON audit.counterfactual_analyses(evaluator_id);

COMMENT ON COLUMN audit.counterfactual_analyses.evaluator_id IS 'References public.evaluators - which model/params performed analysis';

ALTER TABLE audit.counterfactual_analyses
    ALTER COLUMN model_name DROP NOT NULL,
    ALTER COLUMN temperature DROP NOT NULL;

COMMENT ON COLUMN audit.counterfactual_analyses.model_name IS 'DEPRECATED: Use evaluator_id instead. Kept for backward compatibility.';

-- ============================================================================
-- Update views to include evaluator information
-- ============================================================================

DROP VIEW IF EXISTS audit.v_document_processing_status;
DROP VIEW IF EXISTS audit.v_model_performance;

-- View: Document processing status per question (with evaluator info)
CREATE VIEW audit.v_document_processing_status AS
SELECT
    qd.research_question_id,
    qd.document_id,
    qd.query_id,
    qd.discovered_at,
    ds.scoring_id,
    ds.evaluator_id,
    e.name as evaluator_name,
    ds.relevance_score,
    ds.scored_at,
    COUNT(ec.citation_id) as citation_count
FROM audit.query_documents qd
LEFT JOIN audit.document_scores ds
    ON qd.research_question_id = ds.research_question_id
    AND qd.document_id = ds.document_id
LEFT JOIN public.evaluators e
    ON ds.evaluator_id = e.id
LEFT JOIN audit.extracted_citations ec
    ON ds.scoring_id = ec.scoring_id
GROUP BY qd.research_question_id, qd.document_id, qd.query_id, qd.discovered_at,
         ds.scoring_id, ds.evaluator_id, e.name, ds.relevance_score, ds.scored_at;

COMMENT ON VIEW audit.v_document_processing_status IS 'Shows processing status (discovered, scored, citations extracted) with evaluator info';

-- View: Evaluator performance summary
CREATE VIEW audit.v_evaluator_performance AS
SELECT
    e.id as evaluator_id,
    e.name as evaluator_name,
    e.user_id,
    e.model_id,
    COUNT(DISTINCT gq.query_id) as queries_generated,
    COUNT(DISTINCT ds.scoring_id) as documents_scored,
    AVG(ds.relevance_score) as avg_relevance_score,
    COUNT(DISTINCT ec.citation_id) as citations_extracted,
    COUNT(DISTINCT gr.report_id) as reports_generated,
    COUNT(DISTINCT gq.research_question_id) as unique_questions
FROM public.evaluators e
LEFT JOIN audit.generated_queries gq ON e.id = gq.evaluator_id
LEFT JOIN audit.document_scores ds ON e.id = ds.evaluator_id
LEFT JOIN audit.extracted_citations ec ON e.id = ec.evaluator_id
LEFT JOIN audit.generated_reports gr ON e.id = gr.evaluator_id
GROUP BY e.id, e.name, e.user_id, e.model_id;

COMMENT ON VIEW audit.v_evaluator_performance IS 'Performance metrics for each evaluator (user/model/params combination)';

-- ============================================================================
-- Migration Complete
-- ============================================================================
