-- Migration: Create Benchmarking Schema for Model Performance Evaluation
-- Description: Creates benchmarking schema for evaluating and comparing document scoring models
-- Author: BMLibrarian
-- Date: 2025-11-28

-- ============================================================================
-- Create benchmarking schema
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS benchmarking;

-- ============================================================================
-- 1. Research Questions - Questions used for benchmarking
-- ============================================================================

CREATE TABLE IF NOT EXISTS benchmarking.research_questions (
    question_id BIGSERIAL PRIMARY KEY,
    question_text TEXT NOT NULL UNIQUE,
    semantic_threshold REAL NOT NULL DEFAULT 0.5 CHECK (semantic_threshold BETWEEN 0.0 AND 1.0),
    documents_found INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by TEXT,
    description TEXT
);

CREATE INDEX IF NOT EXISTS idx_benchmark_questions_text ON benchmarking.research_questions USING hash(question_text);
CREATE INDEX IF NOT EXISTS idx_benchmark_questions_created ON benchmarking.research_questions(created_at DESC);

COMMENT ON TABLE benchmarking.research_questions IS 'Research questions used for model benchmarking';
COMMENT ON COLUMN benchmarking.research_questions.question_text IS 'The research question used for semantic search and scoring';
COMMENT ON COLUMN benchmarking.research_questions.semantic_threshold IS 'Similarity threshold used for semantic search (default: 0.5)';
COMMENT ON COLUMN benchmarking.research_questions.documents_found IS 'Number of documents found by semantic search';

-- ============================================================================
-- 2. Evaluators - Models and their parameters used for scoring
-- ============================================================================

CREATE TABLE IF NOT EXISTS benchmarking.evaluators (
    evaluator_id BIGSERIAL PRIMARY KEY,
    model_name TEXT NOT NULL,
    temperature REAL NOT NULL DEFAULT 0.1 CHECK (temperature BETWEEN 0.0 AND 2.0),
    top_p REAL NOT NULL DEFAULT 0.9 CHECK (top_p BETWEEN 0.0 AND 1.0),
    is_authoritative BOOLEAN NOT NULL DEFAULT FALSE,
    ollama_host TEXT NOT NULL DEFAULT 'http://localhost:11434',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (model_name, temperature, top_p, ollama_host)
);

CREATE INDEX IF NOT EXISTS idx_benchmark_evaluators_model ON benchmarking.evaluators(model_name);
CREATE INDEX IF NOT EXISTS idx_benchmark_evaluators_auth ON benchmarking.evaluators(is_authoritative) WHERE is_authoritative = TRUE;

COMMENT ON TABLE benchmarking.evaluators IS 'Models and configuration used for document scoring';
COMMENT ON COLUMN benchmarking.evaluators.model_name IS 'Ollama model name (e.g., gpt-oss:20b, medgemma4B_it_q8:latest)';
COMMENT ON COLUMN benchmarking.evaluators.is_authoritative IS 'Whether this evaluator provides the authoritative/ground-truth scores';
COMMENT ON COLUMN benchmarking.evaluators.temperature IS 'Model temperature parameter';
COMMENT ON COLUMN benchmarking.evaluators.top_p IS 'Model top_p (nucleus sampling) parameter';

-- ============================================================================
-- 3. Scoring - Document scores from each evaluator
-- ============================================================================

CREATE TABLE IF NOT EXISTS benchmarking.scoring (
    scoring_id BIGSERIAL PRIMARY KEY,
    question_id BIGINT NOT NULL REFERENCES benchmarking.research_questions(question_id) ON DELETE CASCADE,
    evaluator_id BIGINT NOT NULL REFERENCES benchmarking.evaluators(evaluator_id) ON DELETE CASCADE,
    document_id INTEGER NOT NULL REFERENCES document(id) ON DELETE CASCADE,
    score INTEGER NOT NULL CHECK (score BETWEEN 0 AND 5),
    reasoning TEXT,
    scoring_time_ms REAL NOT NULL CHECK (scoring_time_ms >= 0),
    scored_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (question_id, evaluator_id, document_id)
);

CREATE INDEX IF NOT EXISTS idx_benchmark_scoring_question ON benchmarking.scoring(question_id);
CREATE INDEX IF NOT EXISTS idx_benchmark_scoring_evaluator ON benchmarking.scoring(evaluator_id);
CREATE INDEX IF NOT EXISTS idx_benchmark_scoring_document ON benchmarking.scoring(document_id);
CREATE INDEX IF NOT EXISTS idx_benchmark_scoring_qe ON benchmarking.scoring(question_id, evaluator_id);

COMMENT ON TABLE benchmarking.scoring IS 'Document relevance scores from each model evaluator';
COMMENT ON COLUMN benchmarking.scoring.score IS 'Relevance score from 0-5 (same scale as DocumentScoringAgent)';
COMMENT ON COLUMN benchmarking.scoring.scoring_time_ms IS 'Time taken to score this document in milliseconds';
COMMENT ON COLUMN benchmarking.scoring.reasoning IS 'Model reasoning for the score';

-- ============================================================================
-- 4. Benchmark Runs - Track benchmark sessions
-- ============================================================================

CREATE TABLE IF NOT EXISTS benchmarking.benchmark_runs (
    run_id BIGSERIAL PRIMARY KEY,
    question_id BIGINT NOT NULL REFERENCES benchmarking.research_questions(question_id) ON DELETE CASCADE,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'completed', 'failed', 'cancelled')),
    error_message TEXT,
    models_evaluated TEXT[] NOT NULL DEFAULT '{}',
    authoritative_model TEXT,
    total_documents INTEGER NOT NULL DEFAULT 0,
    config_snapshot JSONB
);

CREATE INDEX IF NOT EXISTS idx_benchmark_runs_question ON benchmarking.benchmark_runs(question_id);
CREATE INDEX IF NOT EXISTS idx_benchmark_runs_status ON benchmarking.benchmark_runs(status);
CREATE INDEX IF NOT EXISTS idx_benchmark_runs_started ON benchmarking.benchmark_runs(started_at DESC);

COMMENT ON TABLE benchmarking.benchmark_runs IS 'Tracks individual benchmark sessions';
COMMENT ON COLUMN benchmarking.benchmark_runs.models_evaluated IS 'Array of model names that were evaluated';
COMMENT ON COLUMN benchmarking.benchmark_runs.authoritative_model IS 'Model used as the authoritative reference';

-- ============================================================================
-- 5. Benchmark Results - Aggregated results per model per run
-- ============================================================================

CREATE TABLE IF NOT EXISTS benchmarking.benchmark_results (
    result_id BIGSERIAL PRIMARY KEY,
    run_id BIGINT NOT NULL REFERENCES benchmarking.benchmark_runs(run_id) ON DELETE CASCADE,
    evaluator_id BIGINT NOT NULL REFERENCES benchmarking.evaluators(evaluator_id) ON DELETE CASCADE,
    documents_scored INTEGER NOT NULL DEFAULT 0,
    total_scoring_time_ms REAL NOT NULL DEFAULT 0,
    avg_scoring_time_ms REAL GENERATED ALWAYS AS (
        CASE WHEN documents_scored > 0
        THEN total_scoring_time_ms / documents_scored
        ELSE 0 END
    ) STORED,
    mean_absolute_error REAL,  -- MAE vs authoritative scores
    root_mean_squared_error REAL,  -- RMSE vs authoritative scores
    score_correlation REAL,  -- Pearson correlation with authoritative
    exact_match_rate REAL,  -- % of scores exactly matching authoritative
    within_one_rate REAL,  -- % of scores within 1 point of authoritative
    alignment_rank INTEGER,  -- Rank by alignment (1 = best)
    performance_rank INTEGER,  -- Rank by speed (1 = fastest)
    final_rank INTEGER,  -- Combined rank (alignment first, then speed for ties)
    UNIQUE (run_id, evaluator_id)
);

CREATE INDEX IF NOT EXISTS idx_benchmark_results_run ON benchmarking.benchmark_results(run_id);
CREATE INDEX IF NOT EXISTS idx_benchmark_results_evaluator ON benchmarking.benchmark_results(evaluator_id);
CREATE INDEX IF NOT EXISTS idx_benchmark_results_rank ON benchmarking.benchmark_results(final_rank);

COMMENT ON TABLE benchmarking.benchmark_results IS 'Aggregated benchmark results per model per run';
COMMENT ON COLUMN benchmarking.benchmark_results.mean_absolute_error IS 'Mean absolute error compared to authoritative model';
COMMENT ON COLUMN benchmarking.benchmark_results.alignment_rank IS 'Rank by alignment with authoritative (lower is better)';
COMMENT ON COLUMN benchmarking.benchmark_results.final_rank IS 'Final rank: alignment first, speed as tiebreaker';

-- ============================================================================
-- Helper Views
-- ============================================================================

-- View: Scoring comparison with authoritative
CREATE OR REPLACE VIEW benchmarking.v_scoring_comparison AS
SELECT
    s.scoring_id,
    s.question_id,
    rq.question_text,
    s.document_id,
    d.title as document_title,
    s.evaluator_id,
    e.model_name,
    e.is_authoritative,
    s.score,
    s.scoring_time_ms,
    auth.score as authoritative_score,
    ABS(s.score - auth.score) as score_difference,
    s.scored_at
FROM benchmarking.scoring s
JOIN benchmarking.research_questions rq ON s.question_id = rq.question_id
JOIN benchmarking.evaluators e ON s.evaluator_id = e.evaluator_id
JOIN document d ON s.document_id = d.id
LEFT JOIN LATERAL (
    SELECT sc.score
    FROM benchmarking.scoring sc
    JOIN benchmarking.evaluators auth_e ON sc.evaluator_id = auth_e.evaluator_id
    WHERE auth_e.is_authoritative = TRUE
      AND sc.question_id = s.question_id
      AND sc.document_id = s.document_id
    LIMIT 1
) auth ON TRUE
WHERE e.is_authoritative = FALSE;

COMMENT ON VIEW benchmarking.v_scoring_comparison IS 'Compare non-authoritative scores with authoritative scores';

-- View: Model performance summary across all runs
CREATE OR REPLACE VIEW benchmarking.v_model_performance AS
SELECT
    e.model_name,
    e.temperature,
    e.top_p,
    COUNT(DISTINCT br.run_id) as total_runs,
    SUM(br.documents_scored) as total_documents_scored,
    AVG(br.avg_scoring_time_ms) as avg_time_per_doc_ms,
    AVG(br.mean_absolute_error) as avg_mae,
    AVG(br.exact_match_rate) as avg_exact_match_rate,
    AVG(br.within_one_rate) as avg_within_one_rate,
    AVG(br.final_rank) as avg_rank
FROM benchmarking.evaluators e
JOIN benchmarking.benchmark_results br ON e.evaluator_id = br.evaluator_id
WHERE e.is_authoritative = FALSE
GROUP BY e.model_name, e.temperature, e.top_p
ORDER BY AVG(br.mean_absolute_error) ASC NULLS LAST;

COMMENT ON VIEW benchmarking.v_model_performance IS 'Aggregate model performance across all benchmark runs';

-- View: Latest benchmark run results
CREATE OR REPLACE VIEW benchmarking.v_latest_run_results AS
SELECT
    br.run_id,
    rq.question_text,
    brun.started_at,
    brun.completed_at,
    brun.status,
    e.model_name,
    e.is_authoritative,
    br.documents_scored,
    br.avg_scoring_time_ms,
    br.mean_absolute_error,
    br.exact_match_rate,
    br.within_one_rate,
    br.alignment_rank,
    br.performance_rank,
    br.final_rank
FROM benchmarking.benchmark_results br
JOIN benchmarking.benchmark_runs brun ON br.run_id = brun.run_id
JOIN benchmarking.research_questions rq ON brun.question_id = rq.question_id
JOIN benchmarking.evaluators e ON br.evaluator_id = e.evaluator_id
WHERE brun.run_id = (
    SELECT MAX(run_id) FROM benchmarking.benchmark_runs WHERE status = 'completed'
)
ORDER BY br.final_rank ASC NULLS LAST;

COMMENT ON VIEW benchmarking.v_latest_run_results IS 'Results from the most recent completed benchmark run';

-- ============================================================================
-- Helper Functions
-- ============================================================================

-- Function: Get or create research question
CREATE OR REPLACE FUNCTION benchmarking.get_or_create_question(
    p_question_text TEXT,
    p_semantic_threshold REAL DEFAULT 0.5,
    p_created_by TEXT DEFAULT NULL,
    p_description TEXT DEFAULT NULL
) RETURNS BIGINT AS $$
DECLARE
    v_question_id BIGINT;
BEGIN
    -- Try to find existing question
    SELECT question_id INTO v_question_id
    FROM benchmarking.research_questions
    WHERE question_text = p_question_text;

    -- If not found, create new one
    IF v_question_id IS NULL THEN
        INSERT INTO benchmarking.research_questions (
            question_text, semantic_threshold, created_by, description
        )
        VALUES (p_question_text, p_semantic_threshold, p_created_by, p_description)
        RETURNING question_id INTO v_question_id;
    END IF;

    RETURN v_question_id;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION benchmarking.get_or_create_question IS 'Get existing or create new research question for benchmarking';

-- Function: Get or create evaluator
CREATE OR REPLACE FUNCTION benchmarking.get_or_create_evaluator(
    p_model_name TEXT,
    p_temperature REAL DEFAULT 0.1,
    p_top_p REAL DEFAULT 0.9,
    p_is_authoritative BOOLEAN DEFAULT FALSE,
    p_ollama_host TEXT DEFAULT 'http://localhost:11434'
) RETURNS BIGINT AS $$
DECLARE
    v_evaluator_id BIGINT;
BEGIN
    -- Try to find existing evaluator with same config
    SELECT evaluator_id INTO v_evaluator_id
    FROM benchmarking.evaluators
    WHERE model_name = p_model_name
      AND temperature = p_temperature
      AND top_p = p_top_p
      AND ollama_host = p_ollama_host;

    -- If not found, create new one
    IF v_evaluator_id IS NULL THEN
        INSERT INTO benchmarking.evaluators (
            model_name, temperature, top_p, is_authoritative, ollama_host
        )
        VALUES (p_model_name, p_temperature, p_top_p, p_is_authoritative, p_ollama_host)
        RETURNING evaluator_id INTO v_evaluator_id;
    ELSE
        -- Update is_authoritative if needed
        IF p_is_authoritative THEN
            UPDATE benchmarking.evaluators
            SET is_authoritative = TRUE
            WHERE evaluator_id = v_evaluator_id;
        END IF;
    END IF;

    RETURN v_evaluator_id;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION benchmarking.get_or_create_evaluator IS 'Get existing or create new evaluator for benchmarking';

-- Function: Calculate alignment metrics
CREATE OR REPLACE FUNCTION benchmarking.calculate_alignment_metrics(
    p_run_id BIGINT,
    p_evaluator_id BIGINT,
    p_authoritative_evaluator_id BIGINT
) RETURNS TABLE(
    mae REAL,
    rmse REAL,
    correlation REAL,
    exact_match REAL,
    within_one REAL
) AS $$
DECLARE
    v_run_question_id BIGINT;
BEGIN
    -- Get question_id for this run
    SELECT question_id INTO v_run_question_id
    FROM benchmarking.benchmark_runs WHERE run_id = p_run_id;

    RETURN QUERY
    WITH paired_scores AS (
        SELECT
            s.score as model_score,
            auth.score as auth_score,
            (s.score - auth.score) as diff
        FROM benchmarking.scoring s
        JOIN benchmarking.scoring auth ON
            auth.question_id = s.question_id
            AND auth.document_id = s.document_id
            AND auth.evaluator_id = p_authoritative_evaluator_id
        WHERE s.evaluator_id = p_evaluator_id
          AND s.question_id = v_run_question_id
    ),
    stats AS (
        SELECT
            AVG(ABS(diff))::REAL as mae,
            SQRT(AVG(diff * diff))::REAL as rmse,
            CORR(model_score, auth_score)::REAL as correlation,
            (100.0 * SUM(CASE WHEN diff = 0 THEN 1 ELSE 0 END) / COUNT(*))::REAL as exact_match,
            (100.0 * SUM(CASE WHEN ABS(diff) <= 1 THEN 1 ELSE 0 END) / COUNT(*))::REAL as within_one
        FROM paired_scores
    )
    SELECT s.mae, s.rmse, s.correlation, s.exact_match, s.within_one
    FROM stats s;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION benchmarking.calculate_alignment_metrics IS 'Calculate alignment metrics between model and authoritative scores';

-- Function: Update benchmark results rankings
CREATE OR REPLACE FUNCTION benchmarking.update_rankings(
    p_run_id BIGINT
) RETURNS VOID AS $$
BEGIN
    -- Update alignment rank (lower MAE = better rank)
    WITH ranked AS (
        SELECT
            result_id,
            RANK() OVER (ORDER BY mean_absolute_error ASC NULLS LAST) as a_rank
        FROM benchmarking.benchmark_results
        WHERE run_id = p_run_id
    )
    UPDATE benchmarking.benchmark_results br
    SET alignment_rank = r.a_rank
    FROM ranked r
    WHERE br.result_id = r.result_id;

    -- Update performance rank (lower time = better rank)
    WITH ranked AS (
        SELECT
            result_id,
            RANK() OVER (ORDER BY avg_scoring_time_ms ASC NULLS LAST) as p_rank
        FROM benchmarking.benchmark_results
        WHERE run_id = p_run_id
    )
    UPDATE benchmarking.benchmark_results br
    SET performance_rank = r.p_rank
    FROM ranked r
    WHERE br.result_id = r.result_id;

    -- Update final rank (alignment first, speed as tiebreaker)
    WITH ranked AS (
        SELECT
            result_id,
            RANK() OVER (
                ORDER BY mean_absolute_error ASC NULLS LAST,
                         avg_scoring_time_ms ASC NULLS LAST
            ) as f_rank
        FROM benchmarking.benchmark_results
        WHERE run_id = p_run_id
    )
    UPDATE benchmarking.benchmark_results br
    SET final_rank = r.f_rank
    FROM ranked r
    WHERE br.result_id = r.result_id;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION benchmarking.update_rankings IS 'Update all rankings for a benchmark run';

-- ============================================================================
-- Grants (adjust based on your user setup)
-- ============================================================================

GRANT USAGE ON SCHEMA benchmarking TO rwbadmin;
GRANT USAGE ON SCHEMA benchmarking TO hherb;
GRANT USAGE ON SCHEMA benchmarking TO postgres;

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA benchmarking TO rwbadmin;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA benchmarking TO hherb;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA benchmarking TO postgres;

GRANT USAGE ON ALL SEQUENCES IN SCHEMA benchmarking TO rwbadmin;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA benchmarking TO hherb;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA benchmarking TO postgres;

GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA benchmarking TO rwbadmin;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA benchmarking TO hherb;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA benchmarking TO postgres;

-- ============================================================================
-- Migration Complete
-- ============================================================================
