"""
Database Operations for Model Benchmarking

Provides database access for the benchmarking schema including
research questions, evaluators, scores, and benchmark results.
"""

import logging
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple

import psycopg
from psycopg.rows import dict_row

from .data_types import (
    EvaluatorConfig,
    DocumentScore,
    AlignmentMetrics,
    ModelBenchmarkResult,
    BenchmarkRun,
    BenchmarkStatus,
    BenchmarkSummary,
    SEMANTIC_THRESHOLD,
    DEFAULT_DOCUMENT_LIMIT,
)


logger = logging.getLogger(__name__)


class BenchmarkDatabase:
    """
    Database operations for the benchmarking schema.

    Handles all CRUD operations for research questions, evaluators,
    scores, and benchmark results.
    """

    def __init__(self, conn: psycopg.Connection):
        """
        Initialize with database connection.

        Args:
            conn: Active psycopg connection
        """
        self.conn = conn

    # =========================================================================
    # Research Questions
    # =========================================================================

    def get_or_create_question(
        self,
        question_text: str,
        semantic_threshold: float = SEMANTIC_THRESHOLD,
        created_by: Optional[str] = None,
        description: Optional[str] = None
    ) -> int:
        """
        Get existing or create new research question.

        Args:
            question_text: The research question text
            semantic_threshold: Threshold for semantic search
            created_by: Username of creator
            description: Optional description

        Returns:
            question_id of the existing or new question
        """
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT benchmarking.get_or_create_question(%s, %s, %s, %s)
                """,
                (question_text, semantic_threshold, created_by, description)
            )
            result = cur.fetchone()
            self.conn.commit()
            return result[0]

    def update_question_documents_found(
        self,
        question_id: int,
        documents_found: int
    ) -> None:
        """
        Update the documents_found count for a question.

        Args:
            question_id: ID of the question
            documents_found: Number of documents found
        """
        with self.conn.cursor() as cur:
            cur.execute(
                """
                UPDATE benchmarking.research_questions
                SET documents_found = %s
                WHERE question_id = %s
                """,
                (documents_found, question_id)
            )
            self.conn.commit()

    def get_question(self, question_id: int) -> Optional[Dict[str, Any]]:
        """
        Get question details by ID.

        Args:
            question_id: ID of the question

        Returns:
            Question details dict or None
        """
        with self.conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT question_id, question_text, semantic_threshold,
                       documents_found, created_at, created_by, description
                FROM benchmarking.research_questions
                WHERE question_id = %s
                """,
                (question_id,)
            )
            return cur.fetchone()

    # =========================================================================
    # Evaluators
    # =========================================================================

    def get_or_create_evaluator(
        self,
        config: EvaluatorConfig
    ) -> int:
        """
        Get existing or create new evaluator.

        Args:
            config: Evaluator configuration

        Returns:
            evaluator_id of the existing or new evaluator
        """
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT benchmarking.get_or_create_evaluator(%s, %s, %s, %s, %s)
                """,
                (
                    config.model_name,
                    config.temperature,
                    config.top_p,
                    config.is_authoritative,
                    config.ollama_host
                )
            )
            result = cur.fetchone()
            self.conn.commit()
            return result[0]

    def get_authoritative_evaluator(self) -> Optional[Dict[str, Any]]:
        """
        Get the authoritative evaluator if one exists.

        Returns:
            Evaluator details dict or None
        """
        with self.conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT evaluator_id, model_name, temperature, top_p,
                       is_authoritative, ollama_host, created_at
                FROM benchmarking.evaluators
                WHERE is_authoritative = TRUE
                ORDER BY created_at DESC
                LIMIT 1
                """
            )
            return cur.fetchone()

    def set_authoritative_evaluator(self, evaluator_id: int) -> None:
        """
        Set an evaluator as authoritative (clears others).

        Args:
            evaluator_id: ID of the evaluator to make authoritative
        """
        with self.conn.cursor() as cur:
            # Clear existing authoritative flags
            cur.execute(
                """
                UPDATE benchmarking.evaluators
                SET is_authoritative = FALSE
                WHERE is_authoritative = TRUE
                """
            )
            # Set new authoritative
            cur.execute(
                """
                UPDATE benchmarking.evaluators
                SET is_authoritative = TRUE
                WHERE evaluator_id = %s
                """,
                (evaluator_id,)
            )
            self.conn.commit()

    # =========================================================================
    # Scoring
    # =========================================================================

    def record_score(
        self,
        question_id: int,
        evaluator_id: int,
        document_id: int,
        score: int,
        reasoning: str,
        scoring_time_ms: float
    ) -> int:
        """
        Record a document score.

        Args:
            question_id: ID of the research question
            evaluator_id: ID of the evaluator
            document_id: ID of the document
            score: Relevance score (0-5)
            reasoning: Reasoning for the score
            scoring_time_ms: Time taken to score in milliseconds

        Returns:
            scoring_id of the new record
        """
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO benchmarking.scoring
                    (question_id, evaluator_id, document_id, score, reasoning, scoring_time_ms)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (question_id, evaluator_id, document_id)
                DO UPDATE SET
                    score = EXCLUDED.score,
                    reasoning = EXCLUDED.reasoning,
                    scoring_time_ms = EXCLUDED.scoring_time_ms,
                    scored_at = NOW()
                RETURNING scoring_id
                """,
                (question_id, evaluator_id, document_id, score, reasoning, scoring_time_ms)
            )
            result = cur.fetchone()
            self.conn.commit()
            return result[0]

    def get_scores_for_evaluator(
        self,
        question_id: int,
        evaluator_id: int
    ) -> List[DocumentScore]:
        """
        Get all scores for an evaluator on a question.

        Args:
            question_id: ID of the research question
            evaluator_id: ID of the evaluator

        Returns:
            List of DocumentScore objects
        """
        with self.conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT s.document_id, s.score, s.reasoning, s.scoring_time_ms,
                       s.scored_at, d.title as document_title
                FROM benchmarking.scoring s
                JOIN document d ON s.document_id = d.id
                WHERE s.question_id = %s AND s.evaluator_id = %s
                ORDER BY s.document_id
                """,
                (question_id, evaluator_id)
            )
            rows = cur.fetchall()
            return [
                DocumentScore(
                    document_id=row["document_id"],
                    score=row["score"],
                    reasoning=row["reasoning"],
                    scoring_time_ms=row["scoring_time_ms"],
                    scored_at=row["scored_at"],
                    document_title=row["document_title"]
                )
                for row in rows
            ]

    def get_score_count(self, question_id: int, evaluator_id: int) -> int:
        """
        Get count of scores for an evaluator on a question.

        Args:
            question_id: ID of the research question
            evaluator_id: ID of the evaluator

        Returns:
            Count of scores
        """
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*)
                FROM benchmarking.scoring
                WHERE question_id = %s AND evaluator_id = %s
                """,
                (question_id, evaluator_id)
            )
            return cur.fetchone()[0]

    # =========================================================================
    # Benchmark Runs
    # =========================================================================

    def create_benchmark_run(
        self,
        question_id: int,
        models: List[str],
        authoritative_model: str,
        total_documents: int,
        config_snapshot: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        Create a new benchmark run.

        Args:
            question_id: ID of the research question
            models: List of model names being evaluated
            authoritative_model: Name of the authoritative model
            total_documents: Number of documents to score
            config_snapshot: Optional configuration snapshot

        Returns:
            run_id of the new benchmark run
        """
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO benchmarking.benchmark_runs
                    (question_id, models_evaluated, authoritative_model,
                     total_documents, config_snapshot)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING run_id
                """,
                (question_id, models, authoritative_model, total_documents,
                 psycopg.types.json.Json(config_snapshot) if config_snapshot else None)
            )
            result = cur.fetchone()
            self.conn.commit()
            return result[0]

    def update_benchmark_run_status(
        self,
        run_id: int,
        status: BenchmarkStatus,
        error_message: Optional[str] = None
    ) -> None:
        """
        Update benchmark run status.

        Args:
            run_id: ID of the benchmark run
            status: New status
            error_message: Optional error message
        """
        with self.conn.cursor() as cur:
            if status in (BenchmarkStatus.COMPLETED, BenchmarkStatus.FAILED):
                cur.execute(
                    """
                    UPDATE benchmarking.benchmark_runs
                    SET status = %s, completed_at = NOW(), error_message = %s
                    WHERE run_id = %s
                    """,
                    (status.value, error_message, run_id)
                )
            else:
                cur.execute(
                    """
                    UPDATE benchmarking.benchmark_runs
                    SET status = %s, error_message = %s
                    WHERE run_id = %s
                    """,
                    (status.value, error_message, run_id)
                )
            self.conn.commit()

    def get_benchmark_run(self, run_id: int) -> Optional[Dict[str, Any]]:
        """
        Get benchmark run details.

        Args:
            run_id: ID of the benchmark run

        Returns:
            Run details dict or None
        """
        with self.conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT br.run_id, br.question_id, rq.question_text,
                       rq.semantic_threshold, br.started_at, br.completed_at,
                       br.status, br.error_message, br.models_evaluated,
                       br.authoritative_model, br.total_documents, br.config_snapshot
                FROM benchmarking.benchmark_runs br
                JOIN benchmarking.research_questions rq ON br.question_id = rq.question_id
                WHERE br.run_id = %s
                """,
                (run_id,)
            )
            return cur.fetchone()

    # =========================================================================
    # Benchmark Results
    # =========================================================================

    def create_benchmark_result(
        self,
        run_id: int,
        evaluator_id: int,
        documents_scored: int,
        total_scoring_time_ms: float
    ) -> int:
        """
        Create a benchmark result record for an evaluator.

        Args:
            run_id: ID of the benchmark run
            evaluator_id: ID of the evaluator
            documents_scored: Number of documents scored
            total_scoring_time_ms: Total scoring time in milliseconds

        Returns:
            result_id of the new record
        """
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO benchmarking.benchmark_results
                    (run_id, evaluator_id, documents_scored, total_scoring_time_ms)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (run_id, evaluator_id)
                DO UPDATE SET
                    documents_scored = EXCLUDED.documents_scored,
                    total_scoring_time_ms = EXCLUDED.total_scoring_time_ms
                RETURNING result_id
                """,
                (run_id, evaluator_id, documents_scored, total_scoring_time_ms)
            )
            result = cur.fetchone()
            self.conn.commit()
            return result[0]

    def update_alignment_metrics(
        self,
        run_id: int,
        evaluator_id: int,
        metrics: AlignmentMetrics
    ) -> None:
        """
        Update alignment metrics for a benchmark result.

        Args:
            run_id: ID of the benchmark run
            evaluator_id: ID of the evaluator
            metrics: Alignment metrics
        """
        with self.conn.cursor() as cur:
            cur.execute(
                """
                UPDATE benchmarking.benchmark_results
                SET mean_absolute_error = %s,
                    root_mean_squared_error = %s,
                    score_correlation = %s,
                    exact_match_rate = %s,
                    within_one_rate = %s
                WHERE run_id = %s AND evaluator_id = %s
                """,
                (
                    metrics.mean_absolute_error,
                    metrics.root_mean_squared_error,
                    metrics.score_correlation,
                    metrics.exact_match_rate,
                    metrics.within_one_rate,
                    run_id,
                    evaluator_id
                )
            )
            self.conn.commit()

    def calculate_and_store_alignment_metrics(
        self,
        run_id: int,
        evaluator_id: int,
        authoritative_evaluator_id: int
    ) -> Optional[AlignmentMetrics]:
        """
        Calculate alignment metrics using database function and store them.

        Args:
            run_id: ID of the benchmark run
            evaluator_id: ID of the evaluator
            authoritative_evaluator_id: ID of the authoritative evaluator

        Returns:
            AlignmentMetrics or None if calculation failed
        """
        with self.conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT * FROM benchmarking.calculate_alignment_metrics(%s, %s, %s)
                """,
                (run_id, evaluator_id, authoritative_evaluator_id)
            )
            row = cur.fetchone()
            if row and row.get("mae") is not None:
                metrics = AlignmentMetrics(
                    mean_absolute_error=row["mae"],
                    root_mean_squared_error=row["rmse"],
                    score_correlation=row["correlation"],
                    exact_match_rate=row["exact_match"],
                    within_one_rate=row["within_one"]
                )
                self.update_alignment_metrics(run_id, evaluator_id, metrics)
                return metrics
            return None

    def update_rankings(self, run_id: int) -> None:
        """
        Update all rankings for a benchmark run.

        Args:
            run_id: ID of the benchmark run
        """
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT benchmarking.update_rankings(%s)",
                (run_id,)
            )
            self.conn.commit()

    def get_benchmark_results(self, run_id: int) -> List[Dict[str, Any]]:
        """
        Get all benchmark results for a run.

        Args:
            run_id: ID of the benchmark run

        Returns:
            List of result dicts with evaluator info
        """
        with self.conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT br.result_id, br.run_id, br.evaluator_id,
                       e.model_name, e.temperature, e.top_p, e.is_authoritative,
                       br.documents_scored, br.total_scoring_time_ms,
                       br.avg_scoring_time_ms, br.mean_absolute_error,
                       br.root_mean_squared_error, br.score_correlation,
                       br.exact_match_rate, br.within_one_rate,
                       br.alignment_rank, br.performance_rank, br.final_rank
                FROM benchmarking.benchmark_results br
                JOIN benchmarking.evaluators e ON br.evaluator_id = e.evaluator_id
                WHERE br.run_id = %s
                ORDER BY br.final_rank ASC NULLS LAST, br.avg_scoring_time_ms ASC
                """,
                (run_id,)
            )
            return cur.fetchall()

    def get_ranked_results(self, run_id: int) -> List[Dict[str, Any]]:
        """
        Get ranked benchmark results (excluding authoritative).

        Args:
            run_id: ID of the benchmark run

        Returns:
            List of result dicts ordered by final rank
        """
        with self.conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT br.result_id, e.model_name, e.temperature, e.top_p,
                       br.documents_scored, br.avg_scoring_time_ms,
                       br.mean_absolute_error, br.exact_match_rate,
                       br.within_one_rate, br.alignment_rank,
                       br.performance_rank, br.final_rank
                FROM benchmarking.benchmark_results br
                JOIN benchmarking.evaluators e ON br.evaluator_id = e.evaluator_id
                WHERE br.run_id = %s AND e.is_authoritative = FALSE
                ORDER BY br.final_rank ASC NULLS LAST, br.avg_scoring_time_ms ASC
                """,
                (run_id,)
            )
            return cur.fetchall()

    # =========================================================================
    # Semantic Search
    # =========================================================================

    def semantic_search(
        self,
        question_text: str,
        threshold: float = SEMANTIC_THRESHOLD,
        limit: int = DEFAULT_DOCUMENT_LIMIT
    ) -> List[Dict[str, Any]]:
        """
        Perform semantic search for documents matching a question.

        Args:
            question_text: The research question
            threshold: Similarity threshold
            limit: Maximum number of results

        Returns:
            List of document dicts with similarity scores
        """
        with self.conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT DISTINCT ON (document_id)
                    document_id, title, doi, external_id, authors,
                    publication_date, abstract, score
                FROM semantic_docsearch(%s, %s, %s)
                ORDER BY document_id, score DESC
                """,
                (question_text, threshold, limit)
            )
            return cur.fetchall()

    def get_document_details(self, document_id: int) -> Optional[Dict[str, Any]]:
        """
        Get document details by ID.

        Args:
            document_id: ID of the document

        Returns:
            Document details dict or None
        """
        with self.conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, title, abstract, authors, doi, external_id,
                       publication_date, source_id
                FROM document
                WHERE id = %s
                """,
                (document_id,)
            )
            return cur.fetchone()

    # =========================================================================
    # Summary and Reporting
    # =========================================================================

    def get_benchmark_summary(self, run_id: int) -> Optional[BenchmarkSummary]:
        """
        Get summary statistics for a benchmark run.

        Args:
            run_id: ID of the benchmark run

        Returns:
            BenchmarkSummary or None if run not found
        """
        run = self.get_benchmark_run(run_id)
        if not run:
            return None

        results = self.get_ranked_results(run_id)
        if not results:
            return None

        # Find best and fastest models
        best_result = results[0]  # Already sorted by final_rank
        fastest_result = min(results, key=lambda r: r["avg_scoring_time_ms"] or float('inf'))

        rankings = [
            {
                "rank": r["final_rank"],
                "model_name": r["model_name"],
                "mae": r["mean_absolute_error"],
                "exact_match_rate": r["exact_match_rate"],
                "within_one_rate": r["within_one_rate"],
                "avg_time_ms": r["avg_scoring_time_ms"]
            }
            for r in results
        ]

        return BenchmarkSummary(
            run_id=run_id,
            question_text=run["question_text"],
            total_documents=run["total_documents"],
            models_evaluated=len(results),
            authoritative_model=run["authoritative_model"],
            best_model=best_result["model_name"],
            best_model_mae=best_result["mean_absolute_error"] or 0.0,
            best_model_exact_match_rate=best_result["exact_match_rate"] or 0.0,
            fastest_model=fastest_result["model_name"],
            fastest_model_avg_time_ms=fastest_result["avg_scoring_time_ms"] or 0.0,
            rankings=rankings
        )
