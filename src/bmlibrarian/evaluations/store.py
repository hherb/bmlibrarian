"""
EvaluationStore: Database-backed evaluation storage.

This module replaces in-memory lists like _scored_papers, _assessed_papers
with a persistent database-backed storage system.

Key features:
- Persistent storage in PostgreSQL (evaluations schema)
- Run-based organization for grouping evaluations
- Checkpoint support for resumability
- Progress tracking with automatic updates
- Multi-evaluator comparison support

Author: BMLibrarian
Date: 2025-12-07
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple

from .schemas import (
    EvaluationType, RunType, RunStatus, CheckpointType, UserDecision,
    validate_evaluation_data, extract_primary_score
)
from .evaluator_registry import EvaluatorRegistry, EvaluatorInfo

logger = logging.getLogger(__name__)


@dataclass
class EvaluationRun:
    """Represents an evaluation run (scoring, assessment, etc.)."""
    run_id: int
    run_type: str
    research_question_id: Optional[int]
    research_question_text: Optional[str]
    evaluator_id: Optional[int]
    status: str
    config_snapshot: Optional[Dict[str, Any]]
    documents_total: int
    documents_processed: int
    started_at: datetime
    completed_at: Optional[datetime]
    error_message: Optional[str] = None

    @property
    def progress_percent(self) -> float:
        """Calculate progress percentage."""
        if self.documents_total == 0:
            return 0.0
        return round(100.0 * self.documents_processed / self.documents_total, 1)

    @property
    def is_complete(self) -> bool:
        """Check if run is complete."""
        return self.status in (RunStatus.COMPLETED.value, RunStatus.FAILED.value)

    @property
    def is_resumable(self) -> bool:
        """Check if run can be resumed."""
        return self.status in (RunStatus.IN_PROGRESS.value, RunStatus.PAUSED.value)


@dataclass
class DocumentEvaluation:
    """Represents a single document evaluation result."""
    evaluation_id: int
    run_id: int
    document_id: int
    evaluator_id: Optional[int]
    evaluation_type: str
    primary_score: Optional[float]
    confidence: Optional[float]
    evaluation_data: Dict[str, Any]
    reasoning: Optional[str]
    processing_time_ms: Optional[int]
    evaluated_at: datetime


@dataclass
class Checkpoint:
    """Represents a run checkpoint for resumability."""
    checkpoint_id: int
    run_id: int
    checkpoint_type: str
    checkpoint_data: Dict[str, Any]
    user_decision: Optional[str]
    user_feedback: Optional[str]
    created_at: datetime


class EvaluationStore:
    """
    Database-backed evaluation storage.

    Replaces in-memory lists like _scored_papers, _assessed_papers with
    persistent database storage. Provides CRUD operations for evaluation
    runs, document evaluations, and checkpoints.

    Usage:
        from bmlibrarian.evaluations import EvaluationStore
        from bmlibrarian.database import DatabaseManager

        db = DatabaseManager()
        store = EvaluationStore(db)

        # Create a new run
        run = store.create_run(
            run_type=RunType.RELEVANCE_SCORING,
            research_question="What are the cardiovascular benefits of exercise?",
            evaluator_id=1,
            config={"threshold": 3.0}
        )

        # Save evaluations
        store.save_evaluation(
            run_id=run.run_id,
            document_id=123,
            evaluation_type=EvaluationType.RELEVANCE_SCORE,
            primary_score=4.5,
            evaluation_data={"score": 4.5, "rationale": "Highly relevant..."}
        )

        # Get evaluated documents
        scored_docs = store.get_evaluations_for_run(
            run_id=run.run_id,
            min_score=3.0
        )

        # Complete the run
        store.complete_run(run.run_id)
    """

    def __init__(self, db_manager: Any):
        """
        Initialize the evaluation store.

        Args:
            db_manager: DatabaseManager instance for database access
        """
        self.db = db_manager
        self._evaluator_registry: Optional[EvaluatorRegistry] = None

    @property
    def evaluator_registry(self) -> EvaluatorRegistry:
        """Lazy-initialize evaluator registry."""
        if self._evaluator_registry is None:
            self._evaluator_registry = EvaluatorRegistry(self.db)
        return self._evaluator_registry

    # =========================================================================
    # Run Management
    # =========================================================================

    def create_run(
        self,
        run_type: RunType,
        research_question: str,
        evaluator_id: Optional[int] = None,
        config: Optional[Dict[str, Any]] = None,
        research_question_id: Optional[int] = None,
        session_id: Optional[int] = None,
        documents_total: int = 0,
    ) -> EvaluationRun:
        """
        Create a new evaluation run.

        Args:
            run_type: Type of evaluation run
            research_question: Research question text
            evaluator_id: Evaluator ID from public.evaluators
            config: Configuration snapshot for reproducibility
            research_question_id: Optional FK to audit.research_questions
            session_id: Optional FK to audit.research_sessions
            documents_total: Total documents to evaluate (for progress tracking)

        Returns:
            Created EvaluationRun object
        """
        query = """
            INSERT INTO evaluations.evaluation_runs (
                run_type, research_question_text, research_question_id,
                evaluator_id, config_snapshot, session_id, documents_total
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING run_id, status, started_at
        """

        config_json = json.dumps(config) if config else None

        with self.db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (
                    run_type.value if isinstance(run_type, RunType) else run_type,
                    research_question,
                    research_question_id,
                    evaluator_id,
                    config_json,
                    session_id,
                    documents_total
                ))
                row = cur.fetchone()
            conn.commit()

        run = EvaluationRun(
            run_id=row[0],
            run_type=run_type.value if isinstance(run_type, RunType) else run_type,
            research_question_id=research_question_id,
            research_question_text=research_question,
            evaluator_id=evaluator_id,
            status=row[1],
            config_snapshot=config,
            documents_total=documents_total,
            documents_processed=0,
            started_at=row[2],
            completed_at=None,
        )

        logger.info(
            f"Created evaluation run: id={run.run_id}, type={run.run_type}, "
            f"evaluator={evaluator_id}"
        )
        return run

    def get_run(self, run_id: int) -> Optional[EvaluationRun]:
        """
        Get an evaluation run by ID.

        Args:
            run_id: Run ID to retrieve

        Returns:
            EvaluationRun or None if not found
        """
        query = """
            SELECT run_id, run_type, research_question_id, research_question_text,
                   evaluator_id, status, config_snapshot, documents_total,
                   documents_processed, started_at, completed_at, error_message
            FROM evaluations.evaluation_runs
            WHERE run_id = %s
        """

        with self.db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (run_id,))
                row = cur.fetchone()

        if row is None:
            return None

        return EvaluationRun(
            run_id=row[0],
            run_type=row[1],
            research_question_id=row[2],
            research_question_text=row[3],
            evaluator_id=row[4],
            status=row[5],
            config_snapshot=row[6],
            documents_total=row[7],
            documents_processed=row[8],
            started_at=row[9],
            completed_at=row[10],
            error_message=row[11],
        )

    def get_or_resume_run(
        self,
        run_type: RunType,
        research_question: str,
        evaluator_id: int,
        config: Optional[Dict[str, Any]] = None,
    ) -> Tuple[EvaluationRun, bool]:
        """
        Get existing in-progress run or create a new one.

        Args:
            run_type: Type of evaluation run
            research_question: Research question text
            evaluator_id: Evaluator ID
            config: Configuration (used only if creating new run)

        Returns:
            Tuple of (EvaluationRun, is_new) where is_new indicates if run was created
        """
        # Try to find existing in-progress run
        query = """
            SELECT run_id FROM evaluations.evaluation_runs
            WHERE run_type = %s
              AND research_question_text = %s
              AND evaluator_id = %s
              AND status IN ('in_progress', 'paused')
            ORDER BY created_at DESC
            LIMIT 1
        """

        with self.db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (
                    run_type.value if isinstance(run_type, RunType) else run_type,
                    research_question,
                    evaluator_id
                ))
                row = cur.fetchone()

        if row:
            run = self.get_run(row[0])
            if run:
                logger.info(f"Resuming existing run: id={run.run_id}")
                return run, False

        # Create new run
        run = self.create_run(
            run_type=run_type,
            research_question=research_question,
            evaluator_id=evaluator_id,
            config=config
        )
        return run, True

    def update_run_progress(
        self,
        run_id: int,
        documents_processed: Optional[int] = None,
        documents_total: Optional[int] = None,
    ) -> None:
        """
        Update run progress counters.

        Args:
            run_id: Run ID to update
            documents_processed: Current processed count
            documents_total: Total documents count
        """
        updates = ["updated_at = NOW()"]
        params: List[Any] = []

        if documents_processed is not None:
            updates.append("documents_processed = %s")
            params.append(documents_processed)

        if documents_total is not None:
            updates.append("documents_total = %s")
            params.append(documents_total)

        params.append(run_id)

        query = f"""
            UPDATE evaluations.evaluation_runs
            SET {', '.join(updates)}
            WHERE run_id = %s
        """

        with self.db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, tuple(params))
            conn.commit()

    def complete_run(
        self,
        run_id: int,
        status: RunStatus = RunStatus.COMPLETED,
        error_message: Optional[str] = None,
    ) -> None:
        """
        Mark an evaluation run as complete.

        Args:
            run_id: Run ID to complete
            status: Final status (completed, failed, cancelled)
            error_message: Optional error message if failed
        """
        query = """
            UPDATE evaluations.evaluation_runs
            SET status = %s, completed_at = NOW(), updated_at = NOW(),
                error_message = %s
            WHERE run_id = %s
        """

        with self.db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (
                    status.value if isinstance(status, RunStatus) else status,
                    error_message,
                    run_id
                ))
            conn.commit()

        logger.info(f"Completed run {run_id} with status {status}")

    def pause_run(self, run_id: int) -> None:
        """
        Pause an evaluation run.

        Args:
            run_id: Run ID to pause
        """
        query = """
            UPDATE evaluations.evaluation_runs
            SET status = 'paused', updated_at = NOW()
            WHERE run_id = %s
        """

        with self.db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (run_id,))
            conn.commit()

        logger.info(f"Paused run {run_id}")

    def resume_run(self, run_id: int) -> None:
        """
        Resume a paused evaluation run.

        Args:
            run_id: Run ID to resume
        """
        query = """
            UPDATE evaluations.evaluation_runs
            SET status = 'in_progress', updated_at = NOW()
            WHERE run_id = %s AND status = 'paused'
        """

        with self.db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (run_id,))
            conn.commit()

        logger.info(f"Resumed run {run_id}")

    # =========================================================================
    # Document Evaluations
    # =========================================================================

    def save_evaluation(
        self,
        run_id: int,
        document_id: int,
        evaluation_type: EvaluationType,
        evaluation_data: Dict[str, Any],
        primary_score: Optional[float] = None,
        evaluator_id: Optional[int] = None,
        confidence: Optional[float] = None,
        reasoning: Optional[str] = None,
        processing_time_ms: Optional[int] = None,
        validate: bool = True,
    ) -> int:
        """
        Save or update a document evaluation.

        Uses upsert to handle re-evaluations gracefully.

        Args:
            run_id: Parent run ID
            document_id: Document being evaluated
            evaluation_type: Type of evaluation
            evaluation_data: Full evaluation details (JSON)
            primary_score: Normalized primary score (auto-extracted if not provided)
            evaluator_id: Evaluator ID (uses run's evaluator if not provided)
            confidence: Confidence score (0-1)
            reasoning: Text reasoning/rationale
            processing_time_ms: Processing time in milliseconds
            validate: Whether to validate evaluation_data against schema

        Returns:
            Evaluation ID (new or updated)
        """
        eval_type_str = (
            evaluation_type.value
            if isinstance(evaluation_type, EvaluationType)
            else evaluation_type
        )

        # Validate if requested
        if validate:
            is_valid, error = validate_evaluation_data(eval_type_str, evaluation_data)
            if not is_valid:
                raise ValueError(f"Invalid evaluation data: {error}")

        # Auto-extract primary score if not provided
        if primary_score is None:
            primary_score = extract_primary_score(eval_type_str, evaluation_data)

        query = """
            SELECT evaluations.save_evaluation(
                %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
        """

        with self.db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (
                    run_id,
                    document_id,
                    eval_type_str,
                    primary_score,
                    json.dumps(evaluation_data),
                    evaluator_id,
                    confidence,
                    reasoning,
                    processing_time_ms
                ))
                evaluation_id = cur.fetchone()[0]
            conn.commit()

        logger.debug(
            f"Saved evaluation: run={run_id}, doc={document_id}, "
            f"type={eval_type_str}, score={primary_score}"
        )
        return evaluation_id

    def save_evaluations_batch(
        self,
        run_id: int,
        evaluations: List[Dict[str, Any]],
        evaluation_type: EvaluationType,
        validate: bool = True,
    ) -> List[int]:
        """
        Save multiple evaluations in a batch.

        Args:
            run_id: Parent run ID
            evaluations: List of evaluation dicts with keys:
                - document_id (required)
                - evaluation_data (required)
                - primary_score (optional)
                - confidence (optional)
                - reasoning (optional)
                - processing_time_ms (optional)
            evaluation_type: Type of evaluation
            validate: Whether to validate each evaluation

        Returns:
            List of evaluation IDs
        """
        eval_ids = []
        for eval_dict in evaluations:
            eval_id = self.save_evaluation(
                run_id=run_id,
                document_id=eval_dict["document_id"],
                evaluation_type=evaluation_type,
                evaluation_data=eval_dict["evaluation_data"],
                primary_score=eval_dict.get("primary_score"),
                confidence=eval_dict.get("confidence"),
                reasoning=eval_dict.get("reasoning"),
                processing_time_ms=eval_dict.get("processing_time_ms"),
                validate=validate,
            )
            eval_ids.append(eval_id)

        logger.info(f"Saved batch of {len(eval_ids)} evaluations for run {run_id}")
        return eval_ids

    def get_evaluation(
        self,
        run_id: int,
        document_id: int,
        evaluation_type: EvaluationType,
    ) -> Optional[DocumentEvaluation]:
        """
        Get a specific evaluation.

        Args:
            run_id: Run ID
            document_id: Document ID
            evaluation_type: Evaluation type

        Returns:
            DocumentEvaluation or None if not found
        """
        eval_type_str = (
            evaluation_type.value
            if isinstance(evaluation_type, EvaluationType)
            else evaluation_type
        )

        query = """
            SELECT evaluation_id, run_id, document_id, evaluator_id,
                   evaluation_type, primary_score, confidence, evaluation_data,
                   reasoning, processing_time_ms, evaluated_at
            FROM evaluations.document_evaluations
            WHERE run_id = %s AND document_id = %s AND evaluation_type = %s
        """

        with self.db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (run_id, document_id, eval_type_str))
                row = cur.fetchone()

        if row is None:
            return None

        return DocumentEvaluation(
            evaluation_id=row[0],
            run_id=row[1],
            document_id=row[2],
            evaluator_id=row[3],
            evaluation_type=row[4],
            primary_score=float(row[5]) if row[5] else None,
            confidence=float(row[6]) if row[6] else None,
            evaluation_data=row[7],
            reasoning=row[8],
            processing_time_ms=row[9],
            evaluated_at=row[10],
        )

    def get_evaluated_document_ids(
        self,
        run_id: int,
        evaluation_type: Optional[EvaluationType] = None,
        min_score: Optional[float] = None,
    ) -> List[int]:
        """
        Get document IDs that have been evaluated in a run.

        Args:
            run_id: Run ID
            evaluation_type: Optional filter by evaluation type
            min_score: Optional minimum score filter

        Returns:
            List of document IDs
        """
        conditions = ["run_id = %s"]
        params: List[Any] = [run_id]

        if evaluation_type is not None:
            eval_type_str = (
                evaluation_type.value
                if isinstance(evaluation_type, EvaluationType)
                else evaluation_type
            )
            conditions.append("evaluation_type = %s")
            params.append(eval_type_str)

        if min_score is not None:
            conditions.append("primary_score >= %s")
            params.append(min_score)

        query = f"""
            SELECT DISTINCT document_id
            FROM evaluations.document_evaluations
            WHERE {' AND '.join(conditions)}
            ORDER BY document_id
        """

        with self.db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, tuple(params))
                return [row[0] for row in cur.fetchall()]

    def get_unevaluated_documents(
        self,
        run_id: int,
        document_ids: List[int],
        evaluation_type: EvaluationType,
    ) -> List[int]:
        """
        Get document IDs from input that have not been evaluated.

        Args:
            run_id: Run ID
            document_ids: List of document IDs to check
            evaluation_type: Evaluation type

        Returns:
            List of unevaluated document IDs
        """
        if not document_ids:
            return []

        eval_type_str = (
            evaluation_type.value
            if isinstance(evaluation_type, EvaluationType)
            else evaluation_type
        )

        query = """
            SELECT evaluations.get_unevaluated_documents(%s, %s, %s)
        """

        with self.db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (run_id, document_ids, eval_type_str))
                return [row[0] for row in cur.fetchall()]

    def get_evaluations_for_run(
        self,
        run_id: int,
        evaluation_type: Optional[EvaluationType] = None,
        min_score: Optional[float] = None,
        limit: Optional[int] = None,
        order_by_score: bool = True,
    ) -> List[DocumentEvaluation]:
        """
        Get all evaluations for a run.

        Args:
            run_id: Run ID
            evaluation_type: Optional filter by evaluation type
            min_score: Optional minimum score filter
            limit: Maximum number of results
            order_by_score: If True, order by primary_score descending

        Returns:
            List of DocumentEvaluation objects
        """
        conditions = ["run_id = %s"]
        params: List[Any] = [run_id]

        if evaluation_type is not None:
            eval_type_str = (
                evaluation_type.value
                if isinstance(evaluation_type, EvaluationType)
                else evaluation_type
            )
            conditions.append("evaluation_type = %s")
            params.append(eval_type_str)

        if min_score is not None:
            conditions.append("primary_score >= %s")
            params.append(min_score)

        order_clause = "ORDER BY primary_score DESC NULLS LAST" if order_by_score else ""
        limit_clause = f"LIMIT {limit}" if limit else ""

        query = f"""
            SELECT evaluation_id, run_id, document_id, evaluator_id,
                   evaluation_type, primary_score, confidence, evaluation_data,
                   reasoning, processing_time_ms, evaluated_at
            FROM evaluations.document_evaluations
            WHERE {' AND '.join(conditions)}
            {order_clause}
            {limit_clause}
        """

        with self.db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, tuple(params))
                results = []
                for row in cur.fetchall():
                    results.append(DocumentEvaluation(
                        evaluation_id=row[0],
                        run_id=row[1],
                        document_id=row[2],
                        evaluator_id=row[3],
                        evaluation_type=row[4],
                        primary_score=float(row[5]) if row[5] else None,
                        confidence=float(row[6]) if row[6] else None,
                        evaluation_data=row[7],
                        reasoning=row[8],
                        processing_time_ms=row[9],
                        evaluated_at=row[10],
                    ))
                return results

    # =========================================================================
    # Checkpoints
    # =========================================================================

    def save_checkpoint(
        self,
        run_id: int,
        checkpoint_type: CheckpointType,
        checkpoint_data: Optional[Dict[str, Any]] = None,
        user_decision: Optional[UserDecision] = None,
        user_feedback: Optional[str] = None,
    ) -> int:
        """
        Save a checkpoint for run resumability.

        Args:
            run_id: Run ID
            checkpoint_type: Type of checkpoint
            checkpoint_data: Minimal state data (IDs, counts, not full objects)
            user_decision: Optional user decision
            user_feedback: Optional user feedback text

        Returns:
            Checkpoint ID
        """
        query = """
            SELECT evaluations.save_checkpoint(%s, %s, %s, %s, %s)
        """

        cp_type_str = (
            checkpoint_type.value
            if isinstance(checkpoint_type, CheckpointType)
            else checkpoint_type
        )
        decision_str = (
            user_decision.value
            if isinstance(user_decision, UserDecision)
            else user_decision
        )

        with self.db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (
                    run_id,
                    cp_type_str,
                    json.dumps(checkpoint_data or {}),
                    decision_str,
                    user_feedback
                ))
                checkpoint_id = cur.fetchone()[0]
            conn.commit()

        logger.info(f"Saved checkpoint: run={run_id}, type={cp_type_str}")
        return checkpoint_id

    def get_latest_checkpoint(
        self,
        run_id: int,
        checkpoint_type: Optional[CheckpointType] = None,
    ) -> Optional[Checkpoint]:
        """
        Get the most recent checkpoint for a run.

        Args:
            run_id: Run ID
            checkpoint_type: Optional filter by checkpoint type

        Returns:
            Checkpoint or None if not found
        """
        cp_type_str = None
        if checkpoint_type is not None:
            cp_type_str = (
                checkpoint_type.value
                if isinstance(checkpoint_type, CheckpointType)
                else checkpoint_type
            )

        query = """
            SELECT checkpoint_id, checkpoint_type, checkpoint_data,
                   user_decision, created_at
            FROM evaluations.get_latest_checkpoint(%s, %s)
        """

        with self.db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (run_id, cp_type_str))
                row = cur.fetchone()

        if row is None or row[0] is None:
            return None

        return Checkpoint(
            checkpoint_id=row[0],
            run_id=run_id,
            checkpoint_type=row[1],
            checkpoint_data=row[2] or {},
            user_decision=row[3],
            user_feedback=None,  # Not returned by function
            created_at=row[4],
        )

    def get_all_checkpoints(self, run_id: int) -> List[Checkpoint]:
        """
        Get all checkpoints for a run, ordered by creation time.

        Args:
            run_id: Run ID

        Returns:
            List of Checkpoint objects
        """
        query = """
            SELECT checkpoint_id, checkpoint_type, checkpoint_data,
                   user_decision, user_feedback, created_at
            FROM evaluations.run_checkpoints
            WHERE run_id = %s
            ORDER BY created_at ASC
        """

        with self.db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (run_id,))
                results = []
                for row in cur.fetchall():
                    results.append(Checkpoint(
                        checkpoint_id=row[0],
                        run_id=run_id,
                        checkpoint_type=row[1],
                        checkpoint_data=row[2] or {},
                        user_decision=row[3],
                        user_feedback=row[4],
                        created_at=row[5],
                    ))
                return results

    def resume_from_checkpoint(
        self,
        run_id: int,
    ) -> Tuple[Optional[str], Dict[str, Any]]:
        """
        Get information needed to resume a run from its latest checkpoint.

        Args:
            run_id: Run ID

        Returns:
            Tuple of (checkpoint_type, checkpoint_data) for resumption,
            or (None, {}) if no checkpoint found
        """
        checkpoint = self.get_latest_checkpoint(run_id)
        if checkpoint is None:
            return None, {}

        # Resume the run status
        self.resume_run(run_id)

        return checkpoint.checkpoint_type, checkpoint.checkpoint_data

    # =========================================================================
    # Comparison Queries
    # =========================================================================

    def compare_evaluators(
        self,
        document_ids: List[int],
        research_question: str,
        evaluation_type: EvaluationType = EvaluationType.RELEVANCE_SCORE,
    ) -> List[Dict[str, Any]]:
        """
        Compare evaluations from different evaluators for the same documents.

        Args:
            document_ids: List of document IDs to compare
            research_question: Research question text
            evaluation_type: Type of evaluation to compare

        Returns:
            List of dicts with document_id, evaluator_id, evaluator_name,
            model_name, primary_score, evaluated_at
        """
        if not document_ids:
            return []

        eval_type_str = (
            evaluation_type.value
            if isinstance(evaluation_type, EvaluationType)
            else evaluation_type
        )

        query = """
            SELECT document_id, evaluator_id, evaluator_name, model_name,
                   primary_score, evaluated_at
            FROM evaluations.compare_evaluators(%s, %s, %s)
        """

        with self.db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (document_ids, research_question, eval_type_str))
                results = []
                for row in cur.fetchall():
                    results.append({
                        "document_id": row[0],
                        "evaluator_id": row[1],
                        "evaluator_name": row[2],
                        "model_name": row[3],
                        "primary_score": float(row[4]) if row[4] else None,
                        "evaluated_at": row[5],
                    })
                return results

    def get_run_statistics(self, run_id: int) -> Dict[str, Any]:
        """
        Get statistics for an evaluation run.

        Args:
            run_id: Run ID

        Returns:
            Dict with statistics
        """
        query = """
            SELECT
                COUNT(*) as total_evaluations,
                COUNT(DISTINCT document_id) as unique_documents,
                AVG(primary_score) as avg_score,
                MIN(primary_score) as min_score,
                MAX(primary_score) as max_score,
                AVG(processing_time_ms) as avg_processing_time_ms,
                SUM(processing_time_ms) as total_processing_time_ms,
                COUNT(*) FILTER (WHERE primary_score >= 3) as above_threshold_count
            FROM evaluations.document_evaluations
            WHERE run_id = %s
        """

        with self.db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (run_id,))
                row = cur.fetchone()

        return {
            "total_evaluations": row[0],
            "unique_documents": row[1],
            "avg_score": float(row[2]) if row[2] else None,
            "min_score": float(row[3]) if row[3] else None,
            "max_score": float(row[4]) if row[4] else None,
            "avg_processing_time_ms": float(row[5]) if row[5] else None,
            "total_processing_time_ms": row[6],
            "above_threshold_count": row[7],
        }
