"""
EvaluationStoreMixin - Database-backed evaluation storage for SystematicReviewAgent.

This mixin provides EvaluationStore integration for gradual migration from
in-memory state tracking to database-backed storage.

Usage:
    class SystematicReviewAgent(EvaluationStoreMixin, BaseAgent):
        def __init__(self, ...):
            super().__init__(...)
            self._init_evaluation_store(db_manager)  # Optional

        def score_papers(self, papers):
            for paper in papers:
                score = self._score_paper(paper)
                # Save to both in-memory list AND database
                self._scored_papers.append(scored_paper)
                self._save_scored_paper_to_store(scored_paper)

Author: BMLibrarian
Date: 2025-12-08
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from bmlibrarian.database import DatabaseManager
    from bmlibrarian.evaluations import (
        EvaluationStore,
        EvaluationRun,
        EvaluationType,
        RunType,
        CheckpointType,
    )
    from .data_models import ScoredPaper, AssessedPaper, SearchCriteria

logger = logging.getLogger(__name__)


class EvaluationStoreMixin:
    """
    Mixin class providing EvaluationStore integration.

    This mixin can be added to SystematicReviewAgent to enable database-backed
    evaluation storage alongside existing in-memory tracking.

    Attributes:
        _evaluation_store: Optional EvaluationStore instance
        _evaluation_run: Current evaluation run (if store is enabled)
        _evaluator_id: ID of the current evaluator (model configuration)
    """

    _evaluation_store: Optional["EvaluationStore"] = None
    _evaluation_run: Optional["EvaluationRun"] = None
    _evaluator_id: Optional[int] = None

    def _init_evaluation_store(
        self,
        db_manager: Optional["DatabaseManager"] = None,
        model_name: Optional[str] = None,
        temperature: float = 0.0,
        top_p: float = 1.0,
    ) -> None:
        """
        Initialize EvaluationStore integration.

        Args:
            db_manager: DatabaseManager instance. If None, store is disabled.
            model_name: Model name for evaluator registration.
            temperature: Model temperature for evaluator registration.
            top_p: Model top_p for evaluator registration.
        """
        if db_manager is None:
            logger.debug("EvaluationStore disabled (no db_manager provided)")
            return

        from bmlibrarian.evaluations import EvaluationStore

        self._evaluation_store = EvaluationStore(db_manager)

        # Register evaluator
        if model_name:
            self._evaluator_id = self._evaluation_store.evaluator_registry.get_or_create_model_evaluator(
                model_name=model_name,
                temperature=temperature,
                top_p=top_p,
            )
            logger.info(f"Registered model evaluator: id={self._evaluator_id}")

    @property
    def evaluation_store_enabled(self) -> bool:
        """Check if EvaluationStore is enabled."""
        return self._evaluation_store is not None

    def _start_evaluation_run(
        self,
        criteria: "SearchCriteria",
        run_type: str = "systematic_review",
        config: Optional[Dict[str, Any]] = None,
        documents_total: int = 0,
    ) -> Optional["EvaluationRun"]:
        """
        Start a new evaluation run.

        Args:
            criteria: Search criteria for the review.
            run_type: Type of run (default: systematic_review).
            config: Optional configuration snapshot.
            documents_total: Total documents to process.

        Returns:
            EvaluationRun if store is enabled, None otherwise.
        """
        if not self._evaluation_store:
            return None

        from bmlibrarian.evaluations import RunType

        try:
            run_type_enum = RunType(run_type)
        except ValueError:
            run_type_enum = RunType.SYSTEMATIC_REVIEW

        self._evaluation_run = self._evaluation_store.create_run(
            run_type=run_type_enum,
            research_question=criteria.research_question,
            evaluator_id=self._evaluator_id,
            config=config,
            documents_total=documents_total,
        )

        logger.info(f"Started evaluation run: id={self._evaluation_run.run_id}")
        return self._evaluation_run

    def _save_scored_paper_to_store(
        self,
        scored_paper: "ScoredPaper",
        processing_time_ms: Optional[int] = None,
    ) -> Optional[int]:
        """
        Save a scored paper to EvaluationStore.

        Args:
            scored_paper: ScoredPaper to save.
            processing_time_ms: Optional processing time.

        Returns:
            Evaluation ID if saved, None if store is disabled.
        """
        if not self._evaluation_store or not self._evaluation_run:
            return None

        from bmlibrarian.evaluations import EvaluationType

        # Build evaluation data from ScoredPaper
        evaluation_data = {
            "score": scored_paper.relevance_score,
            "rationale": scored_paper.relevance_rationale,
            "inclusion_decision": (
                scored_paper.inclusion_decision.status.value
                if scored_paper.inclusion_decision
                else None
            ),
        }

        # Add optional fields
        if scored_paper.inclusion_decision and scored_paper.inclusion_decision.rationale:
            evaluation_data["inclusion_rationale"] = scored_paper.inclusion_decision.rationale

        if scored_paper.relevant_citations:
            evaluation_data["citation_count"] = len(scored_paper.relevant_citations)

        try:
            eval_id = self._evaluation_store.save_evaluation(
                run_id=self._evaluation_run.run_id,
                document_id=scored_paper.paper.document_id,
                evaluation_type=EvaluationType.RELEVANCE_SCORE,
                evaluation_data=evaluation_data,
                primary_score=float(scored_paper.relevance_score),
                evaluator_id=self._evaluator_id,
                reasoning=scored_paper.relevance_rationale,
                processing_time_ms=processing_time_ms,
            )
            return eval_id
        except Exception as e:
            logger.warning(f"Failed to save scored paper to store: {e}")
            return None

    def _save_assessed_paper_to_store(
        self,
        assessed_paper: "AssessedPaper",
        processing_time_ms: Optional[int] = None,
    ) -> Optional[int]:
        """
        Save an assessed paper to EvaluationStore.

        Args:
            assessed_paper: AssessedPaper to save.
            processing_time_ms: Optional processing time.

        Returns:
            Evaluation ID if saved, None if store is disabled.
        """
        if not self._evaluation_store or not self._evaluation_run:
            return None

        from bmlibrarian.evaluations import EvaluationType

        # Build evaluation data from AssessedPaper
        evaluation_data = {
            "study_design": assessed_paper.study_assessment.get("study_design", "unknown"),
            "composite_score": assessed_paper.composite_score,
        }

        # Add study assessment details if available
        if assessed_paper.study_assessment:
            for key in ["methodology_score", "bias_risk_score", "sample_size_score",
                       "recency_score", "strengths", "limitations"]:
                if key in assessed_paper.study_assessment:
                    evaluation_data[key] = assessed_paper.study_assessment[key]

        # Add paper weight if available
        if assessed_paper.paper_weight:
            evaluation_data["evidential_weight"] = assessed_paper.paper_weight.get("weight", 0)
            evaluation_data["weight_category"] = assessed_paper.paper_weight.get("category", "unknown")

        try:
            eval_id = self._evaluation_store.save_evaluation(
                run_id=self._evaluation_run.run_id,
                document_id=assessed_paper.scored_paper.paper.document_id,
                evaluation_type=EvaluationType.QUALITY_ASSESSMENT,
                evaluation_data=evaluation_data,
                primary_score=float(assessed_paper.composite_score) if assessed_paper.composite_score else None,
                evaluator_id=self._evaluator_id,
                processing_time_ms=processing_time_ms,
            )
            return eval_id
        except Exception as e:
            logger.warning(f"Failed to save assessed paper to store: {e}")
            return None

    def _save_scoring_checkpoint(
        self,
        scored_count: int,
        total_count: int,
        additional_data: Optional[Dict[str, Any]] = None,
    ) -> Optional[int]:
        """
        Save a checkpoint after scoring phase.

        Args:
            scored_count: Number of papers scored so far.
            total_count: Total papers to score.
            additional_data: Optional additional checkpoint data.

        Returns:
            Checkpoint ID if saved, None if store is disabled.
        """
        if not self._evaluation_store or not self._evaluation_run:
            return None

        from bmlibrarian.evaluations import CheckpointType

        checkpoint_data = {
            "scored_count": scored_count,
            "total_count": total_count,
            "timestamp": datetime.utcnow().isoformat(),
        }

        if additional_data:
            checkpoint_data.update(additional_data)

        try:
            cp_id = self._evaluation_store.save_checkpoint(
                run_id=self._evaluation_run.run_id,
                checkpoint_type=CheckpointType.RELEVANCE_SCORING,
                checkpoint_data=checkpoint_data,
            )

            # Update run progress
            self._evaluation_store.update_run_progress(
                run_id=self._evaluation_run.run_id,
                documents_processed=scored_count,
                documents_total=total_count,
            )

            return cp_id
        except Exception as e:
            logger.warning(f"Failed to save scoring checkpoint: {e}")
            return None

    def _complete_evaluation_run(
        self,
        success: bool = True,
        error_message: Optional[str] = None,
    ) -> None:
        """
        Complete the current evaluation run.

        Args:
            success: Whether the run completed successfully.
            error_message: Optional error message if failed.
        """
        if not self._evaluation_store or not self._evaluation_run:
            return

        from bmlibrarian.evaluations import RunStatus

        status = RunStatus.COMPLETED if success else RunStatus.FAILED

        try:
            self._evaluation_store.complete_run(
                run_id=self._evaluation_run.run_id,
                status=status,
                error_message=error_message,
            )
            logger.info(f"Completed evaluation run: id={self._evaluation_run.run_id}, status={status.value}")
        except Exception as e:
            logger.warning(f"Failed to complete evaluation run: {e}")

    def _get_scored_papers_from_store(
        self,
        min_score: Optional[float] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get scored papers from EvaluationStore.

        Args:
            min_score: Optional minimum score filter.
            limit: Optional maximum number of results.

        Returns:
            List of evaluation dictionaries.
        """
        if not self._evaluation_store or not self._evaluation_run:
            return []

        from bmlibrarian.evaluations import EvaluationType

        try:
            evaluations = self._evaluation_store.get_evaluations_for_run(
                run_id=self._evaluation_run.run_id,
                evaluation_type=EvaluationType.RELEVANCE_SCORE,
                min_score=min_score,
                limit=limit,
            )
            return [
                {
                    "document_id": e.document_id,
                    "score": e.primary_score,
                    "reasoning": e.reasoning,
                    "evaluation_data": e.evaluation_data,
                }
                for e in evaluations
            ]
        except Exception as e:
            logger.warning(f"Failed to get scored papers from store: {e}")
            return []

    def _get_run_statistics(self) -> Optional[Dict[str, Any]]:
        """
        Get statistics for the current evaluation run.

        Returns:
            Statistics dictionary or None if store is disabled.
        """
        if not self._evaluation_store or not self._evaluation_run:
            return None

        try:
            return self._evaluation_store.get_run_statistics(
                self._evaluation_run.run_id
            )
        except Exception as e:
            logger.warning(f"Failed to get run statistics: {e}")
            return None
