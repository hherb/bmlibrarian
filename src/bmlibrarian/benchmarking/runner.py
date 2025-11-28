"""
Model Benchmark Runner

Orchestrates document scoring benchmarks across multiple models,
comparing their performance against an authoritative model.
"""

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable

import psycopg

from bmlibrarian.agents.scoring_agent import DocumentScoringAgent, ScoringResult

from .data_types import (
    EvaluatorConfig,
    DocumentScore,
    AlignmentMetrics,
    ModelBenchmarkResult,
    BenchmarkRun,
    BenchmarkStatus,
    BenchmarkSummary,
    SEMANTIC_THRESHOLD,
    BEST_REASONING_MODEL,
    DEFAULT_TEMPERATURE,
    DEFAULT_TOP_P,
)
from .database import BenchmarkDatabase


logger = logging.getLogger(__name__)


class BenchmarkRunner:
    """
    Runs document scoring benchmarks across multiple models.

    Performs semantic search for a research question, then evaluates
    each model's scoring performance against an authoritative model.
    """

    def __init__(
        self,
        conn: psycopg.Connection,
        ollama_host: str = "http://localhost:11434",
        temperature: float = DEFAULT_TEMPERATURE,
        top_p: float = DEFAULT_TOP_P,
        authoritative_model: str = BEST_REASONING_MODEL,
        semantic_threshold: float = SEMANTIC_THRESHOLD,
        progress_callback: Optional[Callable[[str, int, int], None]] = None
    ):
        """
        Initialize the benchmark runner.

        Args:
            conn: Active database connection
            ollama_host: Ollama server URL
            temperature: Model temperature for scoring
            top_p: Model top_p for scoring
            authoritative_model: Model to use as ground truth
            semantic_threshold: Threshold for semantic search
            progress_callback: Optional callback(status, current, total)
        """
        self.conn = conn
        self.db = BenchmarkDatabase(conn)
        self.ollama_host = ollama_host
        self.temperature = temperature
        self.top_p = top_p
        self.authoritative_model = authoritative_model
        self.semantic_threshold = semantic_threshold
        self.progress_callback = progress_callback

    def _report_progress(
        self,
        status: str,
        current: int = 0,
        total: int = 0
    ) -> None:
        """Report progress via callback if available."""
        if self.progress_callback:
            self.progress_callback(status, current, total)
        logger.info(f"{status} ({current}/{total})" if total > 0 else status)

    def _create_scoring_agent(
        self,
        model: str,
        show_model_info: bool = False
    ) -> DocumentScoringAgent:
        """
        Create a DocumentScoringAgent for the specified model.

        Args:
            model: Model name
            show_model_info: Whether to display model info

        Returns:
            Configured DocumentScoringAgent
        """
        return DocumentScoringAgent(
            model=model,
            host=self.ollama_host,
            temperature=self.temperature,
            top_p=self.top_p,
            show_model_info=show_model_info
        )

    def _score_documents(
        self,
        agent: DocumentScoringAgent,
        question_text: str,
        documents: List[Dict[str, Any]],
        model_name: str
    ) -> tuple[List[DocumentScore], float]:
        """
        Score all documents with the given agent.

        Args:
            agent: DocumentScoringAgent to use
            question_text: Research question
            documents: List of document dicts
            model_name: Model name for logging

        Returns:
            Tuple of (list of DocumentScore, total_time_ms)
        """
        scores = []
        total_time_ms = 0.0
        total_docs = len(documents)

        for i, doc in enumerate(documents):
            self._report_progress(
                f"Scoring with {model_name}",
                i + 1,
                total_docs
            )

            start_time = time.perf_counter()
            try:
                result: ScoringResult = agent.evaluate_document(
                    user_question=question_text,
                    document=doc
                )
                elapsed_ms = (time.perf_counter() - start_time) * 1000

                score = DocumentScore(
                    document_id=doc["document_id"],
                    score=result["score"],
                    reasoning=result["reasoning"],
                    scoring_time_ms=elapsed_ms,
                    scored_at=datetime.now(),
                    document_title=doc.get("title")
                )
                scores.append(score)
                total_time_ms += elapsed_ms

                logger.debug(
                    f"Document {doc['document_id']}: score={result['score']}, "
                    f"time={elapsed_ms:.1f}ms"
                )

            except Exception as e:
                logger.error(f"Error scoring document {doc['document_id']}: {e}")
                # Record error as score 0 with timing
                elapsed_ms = (time.perf_counter() - start_time) * 1000
                score = DocumentScore(
                    document_id=doc["document_id"],
                    score=0,
                    reasoning=f"Scoring failed: {e}",
                    scoring_time_ms=elapsed_ms,
                    scored_at=datetime.now(),
                    document_title=doc.get("title")
                )
                scores.append(score)
                total_time_ms += elapsed_ms

        return scores, total_time_ms

    def run_benchmark(
        self,
        question_text: str,
        models: List[str],
        max_documents: Optional[int] = None,
        created_by: Optional[str] = None
    ) -> BenchmarkRun:
        """
        Run a complete benchmark for a research question.

        Args:
            question_text: Research question for semantic search
            models: List of model names to benchmark
            max_documents: Optional limit on documents to score
            created_by: Username of person running benchmark

        Returns:
            BenchmarkRun with all results
        """
        started_at = datetime.now()
        self._report_progress("Starting benchmark...")

        # Get or create research question
        question_id = self.db.get_or_create_question(
            question_text=question_text,
            semantic_threshold=self.semantic_threshold,
            created_by=created_by
        )

        # Perform semantic search
        self._report_progress("Performing semantic search...")
        documents = self.db.semantic_search(
            question_text=question_text,
            threshold=self.semantic_threshold,
            limit=max_documents or 100
        )

        if not documents:
            logger.warning("No documents found for question")
            return BenchmarkRun(
                run_id=None,
                question_id=question_id,
                question_text=question_text,
                semantic_threshold=self.semantic_threshold,
                documents_found=0,
                status=BenchmarkStatus.FAILED,
                started_at=started_at,
                completed_at=datetime.now(),
                error_message="No documents found in semantic search"
            )

        documents_found = len(documents)
        self.db.update_question_documents_found(question_id, documents_found)
        self._report_progress(f"Found {documents_found} documents")

        # Create benchmark run
        all_models = models + [self.authoritative_model]
        config_snapshot = {
            "ollama_host": self.ollama_host,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "semantic_threshold": self.semantic_threshold,
            "max_documents": max_documents
        }

        run_id = self.db.create_benchmark_run(
            question_id=question_id,
            models=all_models,
            authoritative_model=self.authoritative_model,
            total_documents=documents_found,
            config_snapshot=config_snapshot
        )

        # Initialize benchmark run object
        benchmark_run = BenchmarkRun(
            run_id=run_id,
            question_id=question_id,
            question_text=question_text,
            semantic_threshold=self.semantic_threshold,
            documents_found=documents_found,
            status=BenchmarkStatus.RUNNING,
            started_at=started_at,
            config_snapshot=config_snapshot
        )

        try:
            # Score with authoritative model first
            self._report_progress(f"Scoring with authoritative model: {self.authoritative_model}")
            auth_result = self._score_with_model(
                model=self.authoritative_model,
                question_id=question_id,
                question_text=question_text,
                documents=documents,
                run_id=run_id,
                is_authoritative=True
            )
            benchmark_run.authoritative_result = auth_result

            # Get authoritative evaluator ID
            auth_eval = self.db.get_authoritative_evaluator()
            if not auth_eval:
                raise RuntimeError("Failed to find authoritative evaluator")
            auth_evaluator_id = auth_eval["evaluator_id"]

            # Score with each test model
            for i, model in enumerate(models):
                self._report_progress(
                    f"Evaluating model {i + 1}/{len(models)}: {model}",
                    i + 1,
                    len(models)
                )

                model_result = self._score_with_model(
                    model=model,
                    question_id=question_id,
                    question_text=question_text,
                    documents=documents,
                    run_id=run_id,
                    is_authoritative=False
                )

                # Calculate alignment metrics
                if model_result.evaluator.evaluator_id:
                    metrics = self.db.calculate_and_store_alignment_metrics(
                        run_id=run_id,
                        evaluator_id=model_result.evaluator.evaluator_id,
                        authoritative_evaluator_id=auth_evaluator_id
                    )
                    model_result.alignment_metrics = metrics

                benchmark_run.model_results.append(model_result)

            # Update rankings
            self._report_progress("Calculating rankings...")
            self.db.update_rankings(run_id)

            # Refresh results with rankings
            ranked_results = self.db.get_ranked_results(run_id)
            for result_data in ranked_results:
                for model_result in benchmark_run.model_results:
                    if model_result.evaluator.model_name == result_data["model_name"]:
                        model_result.alignment_rank = result_data["alignment_rank"]
                        model_result.performance_rank = result_data["performance_rank"]
                        model_result.final_rank = result_data["final_rank"]
                        break

            # Mark as completed
            benchmark_run.status = BenchmarkStatus.COMPLETED
            benchmark_run.completed_at = datetime.now()
            self.db.update_benchmark_run_status(run_id, BenchmarkStatus.COMPLETED)

            self._report_progress("Benchmark completed successfully")

        except Exception as e:
            logger.error(f"Benchmark failed: {e}")
            benchmark_run.status = BenchmarkStatus.FAILED
            benchmark_run.error_message = str(e)
            benchmark_run.completed_at = datetime.now()
            self.db.update_benchmark_run_status(
                run_id,
                BenchmarkStatus.FAILED,
                error_message=str(e)
            )
            raise

        return benchmark_run

    def _score_with_model(
        self,
        model: str,
        question_id: int,
        question_text: str,
        documents: List[Dict[str, Any]],
        run_id: int,
        is_authoritative: bool
    ) -> ModelBenchmarkResult:
        """
        Score all documents with a specific model.

        Args:
            model: Model name
            question_id: Question ID
            question_text: Question text
            documents: Documents to score
            run_id: Benchmark run ID
            is_authoritative: Whether this is the authoritative model

        Returns:
            ModelBenchmarkResult with all scores
        """
        # Create evaluator config
        evaluator_config = EvaluatorConfig(
            model_name=model,
            temperature=self.temperature,
            top_p=self.top_p,
            is_authoritative=is_authoritative,
            ollama_host=self.ollama_host
        )

        # Get or create evaluator in database
        evaluator_id = self.db.get_or_create_evaluator(evaluator_config)
        evaluator_config.evaluator_id = evaluator_id

        if is_authoritative:
            self.db.set_authoritative_evaluator(evaluator_id)

        # Create scoring agent
        agent = self._create_scoring_agent(model, show_model_info=True)

        # Score documents
        scores, total_time_ms = self._score_documents(
            agent=agent,
            question_text=question_text,
            documents=documents,
            model_name=model
        )

        # Store scores in database
        for score in scores:
            self.db.record_score(
                question_id=question_id,
                evaluator_id=evaluator_id,
                document_id=score.document_id,
                score=score.score,
                reasoning=score.reasoning,
                scoring_time_ms=score.scoring_time_ms
            )

        # Create benchmark result record
        documents_scored = len(scores)
        self.db.create_benchmark_result(
            run_id=run_id,
            evaluator_id=evaluator_id,
            documents_scored=documents_scored,
            total_scoring_time_ms=total_time_ms
        )

        # Calculate average time
        avg_time_ms = total_time_ms / documents_scored if documents_scored > 0 else 0

        return ModelBenchmarkResult(
            evaluator=evaluator_config,
            documents_scored=documents_scored,
            total_scoring_time_ms=total_time_ms,
            avg_scoring_time_ms=avg_time_ms,
            scores=scores
        )

    def get_summary(self, run_id: int) -> Optional[BenchmarkSummary]:
        """
        Get summary for a benchmark run.

        Args:
            run_id: ID of the benchmark run

        Returns:
            BenchmarkSummary or None
        """
        return self.db.get_benchmark_summary(run_id)

    def export_results_json(
        self,
        benchmark_run: BenchmarkRun,
        output_path: Path
    ) -> None:
        """
        Export benchmark results to JSON file.

        Args:
            benchmark_run: BenchmarkRun to export
            output_path: Path to output file
        """
        data = benchmark_run.to_dict()
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info(f"Results exported to {output_path}")

    def print_summary(self, benchmark_run: BenchmarkRun) -> str:
        """
        Generate a formatted summary string.

        Args:
            benchmark_run: BenchmarkRun to summarize

        Returns:
            Formatted summary string
        """
        lines = [
            "=" * 70,
            "MODEL BENCHMARK RESULTS",
            "=" * 70,
            "",
            f"Question: {benchmark_run.question_text}",
            f"Documents scored: {benchmark_run.documents_found}",
            f"Authoritative model: {self.authoritative_model}",
            f"Status: {benchmark_run.status.value}",
            "",
            "-" * 70,
            "RANKED RESULTS (by alignment with authoritative, then speed)",
            "-" * 70,
        ]

        # Sort by final rank
        ranked_results = benchmark_run.get_ranked_results()

        for result in ranked_results:
            rank = result.final_rank or "N/A"
            mae = result.alignment_metrics.mean_absolute_error if result.alignment_metrics else "N/A"
            exact = result.alignment_metrics.exact_match_rate if result.alignment_metrics else "N/A"
            within_one = result.alignment_metrics.within_one_rate if result.alignment_metrics else "N/A"

            lines.extend([
                "",
                f"Rank #{rank}: {result.evaluator.model_name}",
                f"  Mean Absolute Error: {mae:.3f}" if isinstance(mae, float) else f"  Mean Absolute Error: {mae}",
                f"  Exact Match Rate: {exact:.1f}%" if isinstance(exact, float) else f"  Exact Match Rate: {exact}",
                f"  Within-1 Rate: {within_one:.1f}%" if isinstance(within_one, float) else f"  Within-1 Rate: {within_one}",
                f"  Avg Time/Doc: {result.avg_scoring_time_ms:.1f}ms",
                f"  Documents Scored: {result.documents_scored}",
            ])

        lines.extend([
            "",
            "-" * 70,
            "AUTHORITATIVE MODEL",
            "-" * 70,
            "",
        ])

        if benchmark_run.authoritative_result:
            auth = benchmark_run.authoritative_result
            lines.extend([
                f"Model: {auth.evaluator.model_name}",
                f"Avg Time/Doc: {auth.avg_scoring_time_ms:.1f}ms",
                f"Documents Scored: {auth.documents_scored}",
            ])

        lines.extend([
            "",
            "=" * 70,
        ])

        return "\n".join(lines)
