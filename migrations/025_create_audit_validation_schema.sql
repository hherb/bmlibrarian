-- Migration: Create Human Validation Schema for Audit Trail
-- Description: Adds tables for human reviewers to validate/reject automated evaluations
--              with comments for benchmarking and fine-tuning purposes
-- Author: BMLibrarian
-- Date: 2025-11-28

-- ============================================================================
-- 1. Human Validations - Core validation table for all audited items
-- ============================================================================

CREATE TABLE IF NOT EXISTS audit.human_validations (
    validation_id BIGSERIAL PRIMARY KEY,
    research_question_id BIGINT NOT NULL REFERENCES audit.research_questions(research_question_id) ON DELETE CASCADE,
    session_id BIGINT REFERENCES audit.research_sessions(session_id) ON DELETE SET NULL,

    -- What was validated
    target_type TEXT NOT NULL CHECK (target_type IN (
        'query',           -- Generated query (audit.generated_queries)
        'score',           -- Document score (audit.document_scores)
        'citation',        -- Extracted citation (audit.extracted_citations)
        'report',          -- Generated report (audit.generated_reports)
        'counterfactual'   -- Counterfactual question (audit.counterfactual_questions)
    )),
    target_id BIGINT NOT NULL,                    -- ID in the target table

    -- Validation outcome
    validation_status TEXT NOT NULL CHECK (validation_status IN (
        'validated',     -- Human agrees with automated result
        'incorrect',     -- Human disagrees with automated result
        'uncertain',     -- Human cannot determine correctness
        'needs_review'   -- Flagged for additional review
    )),

    -- Details
    reviewer_id INTEGER REFERENCES public.users(id) ON DELETE SET NULL,
    reviewer_name TEXT NOT NULL,                  -- Denormalized for display
    comment TEXT,                                 -- Explanation of validation decision
    suggested_correction TEXT,                    -- What the correct value should be (optional)
    severity TEXT CHECK (severity IN ('minor', 'moderate', 'major', 'critical')),

    -- Metadata
    validated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    time_spent_seconds INTEGER,                   -- How long reviewer spent on this item

    -- Unique constraint: one validation per target per reviewer
    UNIQUE (target_type, target_id, reviewer_id)
);

CREATE INDEX IF NOT EXISTS idx_human_validations_question ON audit.human_validations(research_question_id);
CREATE INDEX IF NOT EXISTS idx_human_validations_target ON audit.human_validations(target_type, target_id);
CREATE INDEX IF NOT EXISTS idx_human_validations_status ON audit.human_validations(validation_status);
CREATE INDEX IF NOT EXISTS idx_human_validations_reviewer ON audit.human_validations(reviewer_id);
CREATE INDEX IF NOT EXISTS idx_human_validations_date ON audit.human_validations(validated_at DESC);

COMMENT ON TABLE audit.human_validations IS 'Human validation/rejection of automated audit trail items for benchmarking and fine-tuning';
COMMENT ON COLUMN audit.human_validations.target_type IS 'Type of item being validated (query, score, citation, report, counterfactual)';
COMMENT ON COLUMN audit.human_validations.target_id IS 'ID of the specific record in the target audit table';
COMMENT ON COLUMN audit.human_validations.suggested_correction IS 'What the reviewer believes the correct value should be';

-- ============================================================================
-- 2. Validation Categories - Predefined categories for incorrect items
-- ============================================================================

CREATE TABLE IF NOT EXISTS audit.validation_categories (
    category_id SERIAL PRIMARY KEY,
    target_type TEXT NOT NULL CHECK (target_type IN ('query', 'score', 'citation', 'report', 'counterfactual')),
    category_code TEXT NOT NULL,
    category_name TEXT NOT NULL,
    description TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (target_type, category_code)
);

CREATE INDEX IF NOT EXISTS idx_validation_categories_type ON audit.validation_categories(target_type, is_active);

COMMENT ON TABLE audit.validation_categories IS 'Predefined categories for classifying incorrect evaluations';

-- Insert default categories for each target type
INSERT INTO audit.validation_categories (target_type, category_code, category_name, description)
VALUES
    -- Query categories
    ('query', 'syntax_error', 'Syntax Error', 'Query has SQL syntax errors'),
    ('query', 'missing_terms', 'Missing Search Terms', 'Important search terms not included'),
    ('query', 'wrong_fields', 'Wrong Database Fields', 'Query targets incorrect database fields'),
    ('query', 'too_broad', 'Too Broad', 'Query returns too many irrelevant results'),
    ('query', 'too_narrow', 'Too Narrow', 'Query misses relevant documents'),
    ('query', 'logic_error', 'Logic Error', 'Boolean logic (AND/OR) is incorrect'),

    -- Score categories
    ('score', 'overscored', 'Overscored', 'Document scored too high for relevance'),
    ('score', 'underscored', 'Underscored', 'Document scored too low for relevance'),
    ('score', 'wrong_reasoning', 'Wrong Reasoning', 'Score reasoning does not match document content'),
    ('score', 'missed_relevance', 'Missed Relevance', 'Failed to identify key relevant content'),
    ('score', 'false_relevance', 'False Relevance', 'Incorrectly identified irrelevant content as relevant'),

    -- Citation categories
    ('citation', 'wrong_passage', 'Wrong Passage', 'Extracted passage does not support the claim'),
    ('citation', 'misinterpretation', 'Misinterpretation', 'Summary misinterprets the passage'),
    ('citation', 'out_of_context', 'Out of Context', 'Passage taken out of context'),
    ('citation', 'incomplete', 'Incomplete', 'Citation missing important qualifying information'),
    ('citation', 'fabricated', 'Fabricated', 'Citation does not exist in source document'),

    -- Report categories
    ('report', 'unsupported_claim', 'Unsupported Claim', 'Report contains claims not supported by citations'),
    ('report', 'misrepresentation', 'Misrepresentation', 'Report misrepresents cited evidence'),
    ('report', 'missing_evidence', 'Missing Evidence', 'Report omits important contradictory evidence'),
    ('report', 'logical_error', 'Logical Error', 'Report contains logical fallacies or errors'),
    ('report', 'poor_synthesis', 'Poor Synthesis', 'Evidence not properly synthesized'),

    -- Counterfactual categories
    ('counterfactual', 'irrelevant_question', 'Irrelevant Question', 'Question not relevant to finding contradictory evidence'),
    ('counterfactual', 'biased_framing', 'Biased Framing', 'Question biased toward particular answer'),
    ('counterfactual', 'too_vague', 'Too Vague', 'Question too vague to be useful'),
    ('counterfactual', 'missed_angle', 'Missed Angle', 'Important counterfactual angle not explored')
ON CONFLICT (target_type, category_code) DO NOTHING;

-- ============================================================================
-- 3. Validation Category Assignments - Link validations to categories
-- ============================================================================

CREATE TABLE IF NOT EXISTS audit.validation_category_assignments (
    assignment_id BIGSERIAL PRIMARY KEY,
    validation_id BIGINT NOT NULL REFERENCES audit.human_validations(validation_id) ON DELETE CASCADE,
    category_id INTEGER NOT NULL REFERENCES audit.validation_categories(category_id) ON DELETE CASCADE,
    UNIQUE (validation_id, category_id)
);

CREATE INDEX IF NOT EXISTS idx_validation_category_assignments_validation ON audit.validation_category_assignments(validation_id);
CREATE INDEX IF NOT EXISTS idx_validation_category_assignments_category ON audit.validation_category_assignments(category_id);

COMMENT ON TABLE audit.validation_category_assignments IS 'Links validations to one or more error categories';

-- ============================================================================
-- 4. Validation Statistics View
-- ============================================================================

CREATE OR REPLACE VIEW audit.v_validation_statistics AS
SELECT
    target_type,
    COUNT(*) as total_validations,
    COUNT(*) FILTER (WHERE validation_status = 'validated') as validated_count,
    COUNT(*) FILTER (WHERE validation_status = 'incorrect') as incorrect_count,
    COUNT(*) FILTER (WHERE validation_status = 'uncertain') as uncertain_count,
    COUNT(*) FILTER (WHERE validation_status = 'needs_review') as needs_review_count,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE validation_status = 'validated') / NULLIF(COUNT(*), 0),
        2
    ) as validation_rate_percent,
    COUNT(DISTINCT reviewer_id) as unique_reviewers,
    AVG(time_spent_seconds) as avg_review_time_seconds
FROM audit.human_validations
GROUP BY target_type;

COMMENT ON VIEW audit.v_validation_statistics IS 'Aggregated validation statistics by target type for benchmarking';

-- ============================================================================
-- 5. Validation Error Category Summary View
-- ============================================================================

CREATE OR REPLACE VIEW audit.v_validation_error_categories AS
SELECT
    vc.target_type,
    vc.category_code,
    vc.category_name,
    COUNT(vca.assignment_id) as error_count,
    ROUND(
        100.0 * COUNT(vca.assignment_id) / NULLIF(
            (SELECT COUNT(*) FROM audit.human_validations hv
             WHERE hv.target_type = vc.target_type AND hv.validation_status = 'incorrect'),
            0
        ),
        2
    ) as percentage_of_errors
FROM audit.validation_categories vc
LEFT JOIN audit.validation_category_assignments vca ON vc.category_id = vca.category_id
WHERE vc.is_active = TRUE
GROUP BY vc.target_type, vc.category_code, vc.category_name
ORDER BY vc.target_type, error_count DESC;

COMMENT ON VIEW audit.v_validation_error_categories IS 'Summary of error categories for incorrect validations';

-- ============================================================================
-- 6. Evaluator Performance View (with validation data)
-- ============================================================================

CREATE OR REPLACE VIEW audit.v_evaluator_validation_performance AS
SELECT
    e.id as evaluator_id,
    e.name as evaluator_name,
    e.model_id,

    -- Scoring validation stats
    COUNT(DISTINCT ds.scoring_id) as total_scores,
    COUNT(DISTINCT hv_score.validation_id) as scores_reviewed,
    COUNT(DISTINCT hv_score.validation_id) FILTER (WHERE hv_score.validation_status = 'validated') as scores_validated,
    COUNT(DISTINCT hv_score.validation_id) FILTER (WHERE hv_score.validation_status = 'incorrect') as scores_incorrect,

    -- Citation validation stats
    COUNT(DISTINCT ec.citation_id) as total_citations,
    COUNT(DISTINCT hv_cite.validation_id) as citations_reviewed,
    COUNT(DISTINCT hv_cite.validation_id) FILTER (WHERE hv_cite.validation_status = 'validated') as citations_validated,
    COUNT(DISTINCT hv_cite.validation_id) FILTER (WHERE hv_cite.validation_status = 'incorrect') as citations_incorrect

FROM public.evaluators e
LEFT JOIN audit.document_scores ds ON e.id = ds.evaluator_id
LEFT JOIN audit.human_validations hv_score
    ON hv_score.target_type = 'score'
    AND hv_score.target_id = ds.scoring_id
LEFT JOIN audit.extracted_citations ec ON e.id = ec.evaluator_id
LEFT JOIN audit.human_validations hv_cite
    ON hv_cite.target_type = 'citation'
    AND hv_cite.target_id = ec.citation_id
GROUP BY e.id, e.name, e.model_id;

COMMENT ON VIEW audit.v_evaluator_validation_performance IS 'Evaluator performance with human validation results';

-- ============================================================================
-- 7. Helper Functions
-- ============================================================================

-- Function: Get validation status for a specific item
CREATE OR REPLACE FUNCTION audit.get_validation_status(
    p_target_type TEXT,
    p_target_id BIGINT
) RETURNS TABLE(
    validation_id BIGINT,
    validation_status TEXT,
    reviewer_name TEXT,
    comment TEXT,
    validated_at TIMESTAMPTZ
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        hv.validation_id,
        hv.validation_status,
        hv.reviewer_name,
        hv.comment,
        hv.validated_at
    FROM audit.human_validations hv
    WHERE hv.target_type = p_target_type
      AND hv.target_id = p_target_id
    ORDER BY hv.validated_at DESC;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION audit.get_validation_status IS 'Get all human validations for a specific audit item';

-- Function: Check if item has been validated by a specific reviewer
CREATE OR REPLACE FUNCTION audit.is_validated_by_reviewer(
    p_target_type TEXT,
    p_target_id BIGINT,
    p_reviewer_id INTEGER
) RETURNS BOOLEAN AS $$
DECLARE
    v_exists BOOLEAN;
BEGIN
    SELECT EXISTS(
        SELECT 1 FROM audit.human_validations
        WHERE target_type = p_target_type
          AND target_id = p_target_id
          AND reviewer_id = p_reviewer_id
    ) INTO v_exists;

    RETURN v_exists;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION audit.is_validated_by_reviewer IS 'Check if item already validated by specific reviewer';

-- Function: Get unvalidated items count by type for a research question
CREATE OR REPLACE FUNCTION audit.get_unvalidated_counts(
    p_research_question_id BIGINT
) RETURNS TABLE(
    target_type TEXT,
    total_count BIGINT,
    validated_count BIGINT,
    unvalidated_count BIGINT
) AS $$
BEGIN
    RETURN QUERY
    WITH item_counts AS (
        -- Queries
        SELECT 'query'::TEXT as target_type, query_id::BIGINT as item_id
        FROM audit.generated_queries WHERE research_question_id = p_research_question_id
        UNION ALL
        -- Scores
        SELECT 'score'::TEXT, scoring_id FROM audit.document_scores
        WHERE research_question_id = p_research_question_id
        UNION ALL
        -- Citations
        SELECT 'citation'::TEXT, citation_id FROM audit.extracted_citations
        WHERE research_question_id = p_research_question_id
        UNION ALL
        -- Reports
        SELECT 'report'::TEXT, report_id FROM audit.generated_reports
        WHERE research_question_id = p_research_question_id
        UNION ALL
        -- Counterfactuals
        SELECT 'counterfactual'::TEXT, cq.question_id
        FROM audit.counterfactual_questions cq
        JOIN audit.counterfactual_analyses ca ON cq.analysis_id = ca.analysis_id
        WHERE ca.research_question_id = p_research_question_id
    )
    SELECT
        ic.target_type,
        COUNT(*)::BIGINT as total_count,
        COUNT(hv.validation_id)::BIGINT as validated_count,
        (COUNT(*) - COUNT(hv.validation_id))::BIGINT as unvalidated_count
    FROM item_counts ic
    LEFT JOIN audit.human_validations hv
        ON ic.target_type = hv.target_type
        AND ic.item_id = hv.target_id
    GROUP BY ic.target_type;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION audit.get_unvalidated_counts IS 'Get counts of validated vs unvalidated items per type';

-- ============================================================================
-- Migration Complete
-- ============================================================================
