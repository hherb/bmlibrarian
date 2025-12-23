-- Migration: Create Unified Evaluations Schema
-- Description: Creates a unified evaluation tracking system for all agent types
--              (scoring, quality assessment, PRISMA, PICO, paper weight, etc.)
--              Replaces in-memory state tracking with database-backed persistence.
-- Author: BMLibrarian
-- Date: 2025-12-07

-- ============================================================================
-- Create evaluations schema
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS evaluations;

-- ============================================================================
-- 1. Evaluation Runs - Central registry of evaluation sessions
-- ============================================================================

CREATE TABLE IF NOT EXISTS evaluations.evaluation_runs (
    run_id BIGSERIAL PRIMARY KEY,

    -- Run type determines evaluation_data structure
    run_type VARCHAR(50) NOT NULL CHECK (run_type IN (
        'relevance_scoring',      -- DocumentScoringAgent (1-5 score)
        'quality_assessment',     -- StudyAssessmentAgent (composite quality)
        'prisma_assessment',      -- PRISMA2020Agent (27-item checklist)
        'pico_extraction',        -- PICOAgent (PICO components)
        'paper_weight',           -- PaperWeightAssessmentAgent (evidential weight)
        'systematic_review'       -- SystematicReviewAgent (full workflow)
    )),

    -- Research question context (optional FK to audit.research_questions)
    research_question_id BIGINT,
    research_question_text TEXT,  -- Stored directly for runs without audit tracking

    -- Link to audit session if applicable
    session_id BIGINT,

    -- WHO performed this evaluation run
    evaluator_id INTEGER REFERENCES public.evaluators(id),

    -- Run status
    status VARCHAR(20) NOT NULL DEFAULT 'in_progress' CHECK (status IN (
        'in_progress', 'completed', 'failed', 'cancelled', 'paused'
    )),

    -- Configuration snapshot for reproducibility
    config_snapshot JSONB,

    -- Progress tracking
    documents_total INTEGER NOT NULL DEFAULT 0,
    documents_processed INTEGER NOT NULL DEFAULT 0,

    -- Timing
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,

    -- Error tracking
    error_message TEXT,

    -- Metadata
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for common access patterns
CREATE INDEX IF NOT EXISTS idx_eval_runs_type ON evaluations.evaluation_runs(run_type);
CREATE INDEX IF NOT EXISTS idx_eval_runs_status ON evaluations.evaluation_runs(status);
CREATE INDEX IF NOT EXISTS idx_eval_runs_question_id ON evaluations.evaluation_runs(research_question_id);
CREATE INDEX IF NOT EXISTS idx_eval_runs_evaluator ON evaluations.evaluation_runs(evaluator_id);
CREATE INDEX IF NOT EXISTS idx_eval_runs_started ON evaluations.evaluation_runs(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_eval_runs_session ON evaluations.evaluation_runs(session_id);

COMMENT ON TABLE evaluations.evaluation_runs IS 'Central registry of evaluation sessions across all agent types';
COMMENT ON COLUMN evaluations.evaluation_runs.run_type IS 'Type of evaluation - determines structure of evaluation_data in document_evaluations';
COMMENT ON COLUMN evaluations.evaluation_runs.evaluator_id IS 'References public.evaluators - identifies model/user/params combination';
COMMENT ON COLUMN evaluations.evaluation_runs.config_snapshot IS 'Full configuration at run start for reproducibility';

-- ============================================================================
-- 2. Document Evaluations - Individual document evaluation results
-- ============================================================================

CREATE TABLE IF NOT EXISTS evaluations.document_evaluations (
    evaluation_id BIGSERIAL PRIMARY KEY,

    -- Parent run
    run_id BIGINT NOT NULL REFERENCES evaluations.evaluation_runs(run_id) ON DELETE CASCADE,

    -- Document being evaluated
    document_id BIGINT NOT NULL,  -- FK to public.document(id)

    -- WHO evaluated (may differ from run evaluator for multi-model runs)
    evaluator_id INTEGER REFERENCES public.evaluators(id),

    -- Evaluation type (allows multiple evaluation types per run)
    evaluation_type VARCHAR(50) NOT NULL CHECK (evaluation_type IN (
        'relevance_score',        -- 1-5 relevance scoring
        'quality_assessment',     -- Study quality composite
        'prisma_suitability',     -- Is this a systematic review?
        'prisma_assessment',      -- 27-item PRISMA checklist
        'pico_extraction',        -- PICO component extraction
        'paper_weight',           -- Evidential weight assessment
        'inclusion_decision'      -- Include/exclude decision with rationale
    )),

    -- Universal score fields (normalized for cross-type comparison)
    primary_score DECIMAL(6,3),  -- Main score (1-5 for relevance, 0-100 for composite, etc.)
    confidence DECIMAL(4,3) CHECK (confidence IS NULL OR (confidence >= 0.0 AND confidence <= 1.0)),

    -- Type-specific structured data (JSON schema varies by evaluation_type)
    evaluation_data JSONB NOT NULL,

    -- Reasoning and audit
    reasoning TEXT,

    -- Performance metrics
    processing_time_ms INTEGER CHECK (processing_time_ms IS NULL OR processing_time_ms >= 0),

    -- Timing
    evaluated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Prevent duplicate evaluations for same document+run+type
    UNIQUE(run_id, document_id, evaluation_type)
);

-- Indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_doc_eval_run_id ON evaluations.document_evaluations(run_id);
CREATE INDEX IF NOT EXISTS idx_doc_eval_document_id ON evaluations.document_evaluations(document_id);
CREATE INDEX IF NOT EXISTS idx_doc_eval_type ON evaluations.document_evaluations(evaluation_type);
CREATE INDEX IF NOT EXISTS idx_doc_eval_score ON evaluations.document_evaluations(primary_score DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS idx_doc_eval_evaluator ON evaluations.document_evaluations(evaluator_id);
CREATE INDEX IF NOT EXISTS idx_doc_eval_run_type ON evaluations.document_evaluations(run_id, evaluation_type);
CREATE INDEX IF NOT EXISTS idx_doc_eval_run_score ON evaluations.document_evaluations(run_id, primary_score DESC NULLS LAST);

-- GIN index for JSONB queries
CREATE INDEX IF NOT EXISTS idx_doc_eval_data ON evaluations.document_evaluations USING gin(evaluation_data);

COMMENT ON TABLE evaluations.document_evaluations IS 'Individual document evaluation results - replaces in-memory lists like _scored_papers';
COMMENT ON COLUMN evaluations.document_evaluations.evaluation_type IS 'Type of evaluation - determines structure of evaluation_data';
COMMENT ON COLUMN evaluations.document_evaluations.primary_score IS 'Normalized primary score for cross-type comparison';
COMMENT ON COLUMN evaluations.document_evaluations.evaluation_data IS 'Full evaluation details - structure varies by evaluation_type';

-- ============================================================================
-- 3. Run Checkpoints - Replaces JSON checkpoint files
-- ============================================================================

CREATE TABLE IF NOT EXISTS evaluations.run_checkpoints (
    checkpoint_id BIGSERIAL PRIMARY KEY,

    -- Parent run
    run_id BIGINT NOT NULL REFERENCES evaluations.evaluation_runs(run_id) ON DELETE CASCADE,

    -- Checkpoint type (determines what state is being saved)
    checkpoint_type VARCHAR(50) NOT NULL CHECK (checkpoint_type IN (
        'search_planning',        -- After search plan created
        'search_execution',       -- After queries executed
        'initial_filtering',      -- After initial title/abstract filter
        'relevance_scoring',      -- After relevance scoring complete
        'quality_assessment',     -- After quality assessment complete
        'citation_extraction',    -- After citations extracted
        'report_generation',      -- After report generated
        'counterfactual_search',  -- After counterfactual evidence search
        'final_review',           -- Before final export
        'custom'                  -- Agent-specific checkpoint
    )),

    -- Minimal state data (IDs and counts, not full objects)
    checkpoint_data JSONB NOT NULL DEFAULT '{}',

    -- User interaction
    user_decision VARCHAR(50) CHECK (user_decision IN (
        'continue', 'pause', 'abort', 'adjust_parameters', 'request_more'
    )),
    user_feedback TEXT,

    -- Timing
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_checkpoints_run ON evaluations.run_checkpoints(run_id);
CREATE INDEX IF NOT EXISTS idx_checkpoints_type ON evaluations.run_checkpoints(checkpoint_type);
CREATE INDEX IF NOT EXISTS idx_checkpoints_run_created ON evaluations.run_checkpoints(run_id, created_at DESC);

COMMENT ON TABLE evaluations.run_checkpoints IS 'Checkpoint data for run resumability - replaces JSON checkpoint files';
COMMENT ON COLUMN evaluations.run_checkpoints.checkpoint_data IS 'Minimal state: document IDs, counts, parameters - NOT full paper objects';
COMMENT ON COLUMN evaluations.run_checkpoints.user_decision IS 'User decision at checkpoint (continue, pause, etc.)';

-- ============================================================================
-- 4. Evaluation Comparisons - Track multi-evaluator comparisons
-- ============================================================================

CREATE TABLE IF NOT EXISTS evaluations.evaluation_comparisons (
    comparison_id BIGSERIAL PRIMARY KEY,

    -- Research question being compared
    research_question_id BIGINT,
    research_question_text TEXT,

    -- Runs being compared
    run_ids BIGINT[] NOT NULL,

    -- Comparison results
    comparison_type VARCHAR(50) NOT NULL CHECK (comparison_type IN (
        'evaluator_agreement',    -- Compare different evaluators
        'temporal_stability',     -- Compare same evaluator over time
        'parameter_sensitivity'   -- Compare different parameters
    )),

    -- Metrics
    metrics JSONB NOT NULL DEFAULT '{}',

    -- Timing
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_comparisons_question ON evaluations.evaluation_comparisons(research_question_id);
CREATE INDEX IF NOT EXISTS idx_comparisons_type ON evaluations.evaluation_comparisons(comparison_type);

COMMENT ON TABLE evaluations.evaluation_comparisons IS 'Stores results of multi-evaluator comparison analyses';

-- ============================================================================
-- Helper Views
-- ============================================================================

-- View: Scored documents with full context
CREATE OR REPLACE VIEW evaluations.v_scored_documents AS
SELECT
    de.evaluation_id,
    de.document_id,
    er.run_id,
    er.research_question_id,
    er.research_question_text,
    de.primary_score as relevance_score,
    de.confidence,
    de.reasoning,
    de.evaluation_data,
    de.processing_time_ms,
    e.name as evaluator_name,
    e.model_id as model_name,
    COALESCE(e.parameters->>'temperature', '0.0')::REAL as temperature,
    de.evaluated_at,
    er.status as run_status
FROM evaluations.document_evaluations de
JOIN evaluations.evaluation_runs er ON de.run_id = er.run_id
LEFT JOIN public.evaluators e ON de.evaluator_id = e.id
WHERE de.evaluation_type = 'relevance_score';

COMMENT ON VIEW evaluations.v_scored_documents IS 'Convenience view for accessing relevance-scored documents with full context';

-- View: Quality-assessed documents
CREATE OR REPLACE VIEW evaluations.v_quality_assessed_documents AS
SELECT
    de.evaluation_id,
    de.document_id,
    er.run_id,
    er.research_question_id,
    de.primary_score as composite_score,
    de.confidence,
    (de.evaluation_data->>'methodology_score')::DECIMAL as methodology_score,
    (de.evaluation_data->>'bias_risk_score')::DECIMAL as bias_risk_score,
    (de.evaluation_data->>'sample_size_score')::DECIMAL as sample_size_score,
    de.evaluation_data->>'study_design' as study_design,
    de.evaluation_data,
    e.model_id as model_name,
    de.evaluated_at
FROM evaluations.document_evaluations de
JOIN evaluations.evaluation_runs er ON de.run_id = er.run_id
LEFT JOIN public.evaluators e ON de.evaluator_id = e.id
WHERE de.evaluation_type = 'quality_assessment';

COMMENT ON VIEW evaluations.v_quality_assessed_documents IS 'Convenience view for accessing quality-assessed documents';

-- View: PRISMA assessments
CREATE OR REPLACE VIEW evaluations.v_prisma_assessments AS
SELECT
    de.evaluation_id,
    de.document_id,
    er.run_id,
    (de.evaluation_data->>'is_suitable')::BOOLEAN as is_suitable,
    de.primary_score as compliance_percentage,
    de.confidence as suitability_confidence,
    de.evaluation_data->'item_scores' as item_scores,
    de.evaluation_data->'item_explanations' as item_explanations,
    e.model_id as model_name,
    de.evaluated_at
FROM evaluations.document_evaluations de
JOIN evaluations.evaluation_runs er ON de.run_id = er.run_id
LEFT JOIN public.evaluators e ON de.evaluator_id = e.id
WHERE de.evaluation_type = 'prisma_assessment';

COMMENT ON VIEW evaluations.v_prisma_assessments IS 'Convenience view for PRISMA 2020 compliance assessments';

-- View: Run progress summary
CREATE OR REPLACE VIEW evaluations.v_run_progress AS
SELECT
    er.run_id,
    er.run_type,
    er.status,
    er.research_question_text,
    er.documents_total,
    er.documents_processed,
    CASE WHEN er.documents_total > 0
         THEN ROUND(100.0 * er.documents_processed / er.documents_total, 1)
         ELSE 0
    END as progress_percent,
    e.name as evaluator_name,
    e.model_id as model_name,
    er.started_at,
    er.completed_at,
    EXTRACT(EPOCH FROM (COALESCE(er.completed_at, NOW()) - er.started_at)) as elapsed_seconds,
    (SELECT checkpoint_type FROM evaluations.run_checkpoints
     WHERE run_id = er.run_id ORDER BY created_at DESC LIMIT 1) as latest_checkpoint
FROM evaluations.evaluation_runs er
LEFT JOIN public.evaluators e ON er.evaluator_id = e.id;

COMMENT ON VIEW evaluations.v_run_progress IS 'Real-time progress view for all evaluation runs';

-- View: Unevaluated documents for a run
CREATE OR REPLACE VIEW evaluations.v_run_document_status AS
SELECT
    er.run_id,
    er.run_type,
    d.id as document_id,
    d.title,
    CASE WHEN de.evaluation_id IS NOT NULL THEN TRUE ELSE FALSE END as is_evaluated,
    de.evaluation_type,
    de.primary_score,
    de.evaluated_at
FROM evaluations.evaluation_runs er
CROSS JOIN public.document d  -- Note: This is a template - actual usage should filter documents
LEFT JOIN evaluations.document_evaluations de
    ON er.run_id = de.run_id AND d.id = de.document_id;

COMMENT ON VIEW evaluations.v_run_document_status IS 'Template view showing document evaluation status per run';

-- ============================================================================
-- Helper Functions
-- ============================================================================

-- Function: Get or create evaluation run
CREATE OR REPLACE FUNCTION evaluations.get_or_create_run(
    p_run_type VARCHAR(50),
    p_research_question_text TEXT,
    p_evaluator_id INTEGER,
    p_config_snapshot JSONB DEFAULT NULL,
    p_research_question_id BIGINT DEFAULT NULL,
    p_session_id BIGINT DEFAULT NULL
) RETURNS BIGINT AS $$
DECLARE
    v_run_id BIGINT;
BEGIN
    -- Try to find existing in-progress run for same question+evaluator+type
    SELECT run_id INTO v_run_id
    FROM evaluations.evaluation_runs
    WHERE run_type = p_run_type
      AND research_question_text = p_research_question_text
      AND evaluator_id = p_evaluator_id
      AND status = 'in_progress'
    ORDER BY created_at DESC
    LIMIT 1;

    -- If not found, create new run
    IF v_run_id IS NULL THEN
        INSERT INTO evaluations.evaluation_runs (
            run_type, research_question_text, research_question_id,
            evaluator_id, config_snapshot, session_id
        )
        VALUES (
            p_run_type, p_research_question_text, p_research_question_id,
            p_evaluator_id, p_config_snapshot, p_session_id
        )
        RETURNING run_id INTO v_run_id;
    END IF;

    RETURN v_run_id;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION evaluations.get_or_create_run IS 'Get existing in-progress run or create new one';

-- Function: Get unevaluated document IDs for a run
CREATE OR REPLACE FUNCTION evaluations.get_unevaluated_documents(
    p_run_id BIGINT,
    p_document_ids BIGINT[],
    p_evaluation_type VARCHAR(50)
) RETURNS TABLE(document_id BIGINT) AS $$
BEGIN
    RETURN QUERY
    SELECT unnest(p_document_ids) AS document_id
    EXCEPT
    SELECT de.document_id
    FROM evaluations.document_evaluations de
    WHERE de.run_id = p_run_id
      AND de.evaluation_type = p_evaluation_type;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION evaluations.get_unevaluated_documents IS 'Returns document IDs from input that have not been evaluated in this run';

-- Function: Save evaluation (upsert)
CREATE OR REPLACE FUNCTION evaluations.save_evaluation(
    p_run_id BIGINT,
    p_document_id BIGINT,
    p_evaluation_type VARCHAR(50),
    p_primary_score DECIMAL(6,3),
    p_evaluation_data JSONB,
    p_evaluator_id INTEGER DEFAULT NULL,
    p_confidence DECIMAL(4,3) DEFAULT NULL,
    p_reasoning TEXT DEFAULT NULL,
    p_processing_time_ms INTEGER DEFAULT NULL
) RETURNS BIGINT AS $$
DECLARE
    v_evaluation_id BIGINT;
BEGIN
    INSERT INTO evaluations.document_evaluations (
        run_id, document_id, evaluation_type, primary_score,
        evaluation_data, evaluator_id, confidence, reasoning, processing_time_ms
    )
    VALUES (
        p_run_id, p_document_id, p_evaluation_type, p_primary_score,
        p_evaluation_data, p_evaluator_id, p_confidence, p_reasoning, p_processing_time_ms
    )
    ON CONFLICT (run_id, document_id, evaluation_type)
    DO UPDATE SET
        primary_score = EXCLUDED.primary_score,
        evaluation_data = EXCLUDED.evaluation_data,
        confidence = EXCLUDED.confidence,
        reasoning = EXCLUDED.reasoning,
        processing_time_ms = EXCLUDED.processing_time_ms,
        evaluated_at = NOW()
    RETURNING evaluation_id INTO v_evaluation_id;

    -- Update run progress
    UPDATE evaluations.evaluation_runs
    SET documents_processed = (
        SELECT COUNT(DISTINCT document_id)
        FROM evaluations.document_evaluations
        WHERE run_id = p_run_id
    ),
    updated_at = NOW()
    WHERE run_id = p_run_id;

    RETURN v_evaluation_id;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION evaluations.save_evaluation IS 'Save or update document evaluation with automatic progress tracking';

-- Function: Complete evaluation run
CREATE OR REPLACE FUNCTION evaluations.complete_run(
    p_run_id BIGINT,
    p_status VARCHAR(20) DEFAULT 'completed'
) RETURNS VOID AS $$
BEGIN
    UPDATE evaluations.evaluation_runs
    SET status = p_status,
        completed_at = NOW(),
        updated_at = NOW()
    WHERE run_id = p_run_id;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION evaluations.complete_run IS 'Mark evaluation run as completed or failed';

-- Function: Save checkpoint
CREATE OR REPLACE FUNCTION evaluations.save_checkpoint(
    p_run_id BIGINT,
    p_checkpoint_type VARCHAR(50),
    p_checkpoint_data JSONB DEFAULT '{}',
    p_user_decision VARCHAR(50) DEFAULT NULL,
    p_user_feedback TEXT DEFAULT NULL
) RETURNS BIGINT AS $$
DECLARE
    v_checkpoint_id BIGINT;
BEGIN
    INSERT INTO evaluations.run_checkpoints (
        run_id, checkpoint_type, checkpoint_data, user_decision, user_feedback
    )
    VALUES (
        p_run_id, p_checkpoint_type, p_checkpoint_data, p_user_decision, p_user_feedback
    )
    RETURNING checkpoint_id INTO v_checkpoint_id;

    -- Update run status if paused
    IF p_user_decision = 'pause' THEN
        UPDATE evaluations.evaluation_runs
        SET status = 'paused', updated_at = NOW()
        WHERE run_id = p_run_id;
    END IF;

    RETURN v_checkpoint_id;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION evaluations.save_checkpoint IS 'Save checkpoint for run resumability';

-- Function: Get latest checkpoint for run
CREATE OR REPLACE FUNCTION evaluations.get_latest_checkpoint(
    p_run_id BIGINT,
    p_checkpoint_type VARCHAR(50) DEFAULT NULL
) RETURNS TABLE(
    checkpoint_id BIGINT,
    checkpoint_type VARCHAR(50),
    checkpoint_data JSONB,
    user_decision VARCHAR(50),
    created_at TIMESTAMPTZ
) AS $$
BEGIN
    RETURN QUERY
    SELECT rc.checkpoint_id, rc.checkpoint_type, rc.checkpoint_data, rc.user_decision, rc.created_at
    FROM evaluations.run_checkpoints rc
    WHERE rc.run_id = p_run_id
      AND (p_checkpoint_type IS NULL OR rc.checkpoint_type = p_checkpoint_type)
    ORDER BY rc.created_at DESC
    LIMIT 1;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION evaluations.get_latest_checkpoint IS 'Get most recent checkpoint for a run';

-- Function: Get scored documents for run
CREATE OR REPLACE FUNCTION evaluations.get_scored_documents(
    p_run_id BIGINT,
    p_min_score DECIMAL(6,3) DEFAULT NULL,
    p_evaluation_type VARCHAR(50) DEFAULT 'relevance_score',
    p_limit INTEGER DEFAULT NULL
) RETURNS TABLE(
    document_id BIGINT,
    primary_score DECIMAL(6,3),
    confidence DECIMAL(4,3),
    reasoning TEXT,
    evaluation_data JSONB
) AS $$
BEGIN
    RETURN QUERY
    SELECT de.document_id, de.primary_score, de.confidence, de.reasoning, de.evaluation_data
    FROM evaluations.document_evaluations de
    WHERE de.run_id = p_run_id
      AND de.evaluation_type = p_evaluation_type
      AND (p_min_score IS NULL OR de.primary_score >= p_min_score)
    ORDER BY de.primary_score DESC NULLS LAST
    LIMIT p_limit;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION evaluations.get_scored_documents IS 'Get evaluated documents for a run, optionally filtered by minimum score';

-- Function: Compare evaluators on same documents
CREATE OR REPLACE FUNCTION evaluations.compare_evaluators(
    p_document_ids BIGINT[],
    p_research_question_text TEXT,
    p_evaluation_type VARCHAR(50) DEFAULT 'relevance_score'
) RETURNS TABLE(
    document_id BIGINT,
    evaluator_id INTEGER,
    evaluator_name TEXT,
    model_name TEXT,
    primary_score DECIMAL(6,3),
    evaluated_at TIMESTAMPTZ
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        de.document_id,
        de.evaluator_id,
        e.name as evaluator_name,
        e.model_id as model_name,
        de.primary_score,
        de.evaluated_at
    FROM evaluations.document_evaluations de
    JOIN evaluations.evaluation_runs er ON de.run_id = er.run_id
    LEFT JOIN public.evaluators e ON de.evaluator_id = e.id
    WHERE de.document_id = ANY(p_document_ids)
      AND er.research_question_text = p_research_question_text
      AND de.evaluation_type = p_evaluation_type
    ORDER BY de.document_id, de.evaluator_id;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION evaluations.compare_evaluators IS 'Compare evaluations from different evaluators for the same documents and question';

-- ============================================================================
-- Grants
-- ============================================================================

-- Grant permissions to PUBLIC (all database users)
-- Since this is a repository for publicly available documents with no confidential data,
-- we grant access to all users. User roles only exist to distinguish human evaluators.
GRANT USAGE ON SCHEMA evaluations TO PUBLIC;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA evaluations TO PUBLIC;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA evaluations TO PUBLIC;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA evaluations TO PUBLIC;

-- ============================================================================
-- Migration Complete
-- ============================================================================
