"""
SystematicReviewAgent - Main Agent Class

This module provides the SystematicReviewAgent, an AI-assisted systematic
literature review agent that automates the process of finding, filtering,
evaluating, and ranking scientific papers based on user-defined criteria.

The agent operates autonomously but pauses at key decision points for
human approval, balancing efficiency with scientific rigor.

Key Features:
- Checkpoint-based autonomy with human oversight
- Multi-strategy search (semantic, keyword, hybrid)
- LLM-powered relevance scoring and inclusion/exclusion evaluation
- Quality assessment integration (PICO, PRISMA, paper weight)
- Complete audit trail for reproducibility
- Configurable scoring weights
- Resumable from checkpoint files (resume_mixin.py), sharing one review
  pipeline (pipeline.py) with fresh runs
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, TYPE_CHECKING

from ..base import BaseAgent

from .config import (
    SystematicReviewConfig,
    get_systematic_review_config,
)
from .data_models import (
    SearchCriteria,
    ScoringWeights,
    SearchPlan,
    ExecutedQuery,
    PaperData,
    ScoredPaper,
    AssessedPaper,
    ReviewStatistics,
    SystematicReviewResult,
    InclusionDecision,
    InclusionStatus,
    ExclusionStage,
    validate_search_criteria,
    validate_scoring_weights,
    QueryFeedback,
)
from .documenter import (
    Documenter,
    ACTION_GENERATE_SEARCH_PLAN,
    CHECKPOINT_SEARCH_STRATEGY,
)
from .pipeline import ReviewRunOptions, ReviewStage
from .resume_mixin import CheckpointResumeMixin

if TYPE_CHECKING:
    from ..orchestrator import AgentOrchestrator
    from bmlibrarian.database import DatabaseManager
    from bmlibrarian.evaluations import EvaluationStore, EvaluationRun

logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

AGENT_VERSION = "1.0.0"

# Action and checkpoint names live in documenter.py (single source of truth)


# =============================================================================
# SystematicReviewAgent
# =============================================================================

class SystematicReviewAgent(CheckpointResumeMixin, BaseAgent):
    """
    AI-assisted systematic literature review agent.

    Automates the systematic review process while maintaining human oversight
    at key decision points. Integrates with existing BMLibrarian agents for
    search, scoring, and quality assessment.

    Workflow Phases:
    1. Search Strategy: Generate diverse queries for comprehensive coverage
    2. Search Execution: Run queries and deduplicate results
    3. Initial Filtering: Fast heuristic-based paper filtering
    4. Relevance Scoring: LLM-based relevance assessment
    5. Inclusion Evaluation: Apply inclusion/exclusion criteria
    6. Quality Assessment: Detailed quality and methodology evaluation
    7. Final Ranking: Calculate composite scores and rank papers
    8. Report Generation: Generate comprehensive output report

    Attributes:
        config: SystematicReviewConfig with agent settings
        documenter: Audit trail logging component
        criteria: Current SearchCriteria (set when run_review is called)
        weights: Current ScoringWeights (set when run_review is called)

    Example:
        >>> agent = SystematicReviewAgent()
        >>> criteria = SearchCriteria(
        ...     research_question="Effect of statins on CVD prevention?",
        ...     purpose="Clinical guideline development",
        ...     inclusion_criteria=["Human studies", "Statin intervention"],
        ...     exclusion_criteria=["Animal studies", "Case reports"]
        ... )
        >>> result = agent.run_review(criteria, interactive=True)
        >>> result.save("systematic_review_results.json")
    """

    def __init__(
        self,
        db_manager: "DatabaseManager",
        config: Optional[SystematicReviewConfig] = None,
        callback: Optional[Callable[[str, str], None]] = None,
        orchestrator: Optional["AgentOrchestrator"] = None,
        show_model_info: bool = True,
    ) -> None:
        """
        Initialize the SystematicReviewAgent.

        Args:
            db_manager: DatabaseManager instance for database access.
            config: Optional configuration. If None, loads from BMLibrarian config.
            callback: Optional callback for progress updates.
            orchestrator: Optional orchestrator for queue-based processing.
            show_model_info: Whether to display model information on init.
        """
        # Load configuration
        self.config = config or get_systematic_review_config()

        # Initialize base agent with model settings
        super().__init__(
            model=self.config.model,
            host=self.config.host,
            temperature=self.config.temperature,
            top_p=self.config.top_p,
            callback=callback,
            orchestrator=orchestrator,
            show_model_info=show_model_info,
        )

        # Initialize documenter for audit trail
        self.documenter = Documenter()

        # Database and evaluation store
        self._db_manager = db_manager
        self._init_evaluation_store()

        # Current review state (set when run_review is called)
        self._criteria: Optional[SearchCriteria] = None
        self._weights: Optional[ScoringWeights] = None
        self._search_plan: Optional[SearchPlan] = None
        self._executed_queries: List[ExecutedQuery] = []
        self._all_papers: List[PaperData] = []
        # Track papers rejected at each stage for comprehensive reporting
        self._rejected_initial_filter: List[Tuple[PaperData, str]] = []
        # Search provenance: document_id -> query_ids that found it
        self._paper_sources: Dict[int, List[str]] = {}
        # Phase-1 (semantic/HyDE/hybrid) results of a phased search
        self._semantic_baseline_ids: Set[int] = set()
        self._query_feedback: Optional[QueryFeedback] = None

        # Child agents (initialized lazily)
        self._query_agent = None
        self._scoring_agent = None
        self._citation_agent = None
        self._pico_agent = None
        self._study_assessment_agent = None
        self._paper_weight_agent = None
        self._prisma_agent = None
        self._semantic_query_agent = None

        logger.info(f"SystematicReviewAgent v{AGENT_VERSION} initialized")

    def _init_evaluation_store(self) -> None:
        """
        Initialize the EvaluationStore and register evaluator.

        Raises:
            RuntimeError: If evaluation store initialization fails.
        """
        from bmlibrarian.evaluations import EvaluationStore

        try:
            self._evaluation_store: "EvaluationStore" = EvaluationStore(self._db_manager)
            self._evaluation_run: Optional["EvaluationRun"] = None

            # Register this agent's model as an evaluator
            self._evaluator_id = self._evaluation_store.evaluator_registry.get_or_create_model_evaluator(
                model_name=self.config.model,
                temperature=self.config.temperature,
                top_p=self.config.top_p,
            )
            logger.debug(f"Registered evaluator: id={self._evaluator_id}")
        except Exception as e:
            logger.error(f"Failed to initialize evaluation store: {e}")
            raise RuntimeError(f"Evaluation store initialization failed: {e}") from e

    # =========================================================================
    # BaseAgent Implementation
    # =========================================================================

    def get_agent_type(self) -> str:
        """
        Get the type/name of this agent.

        Returns:
            String identifier "SystematicReviewAgent"
        """
        return "SystematicReviewAgent"

    # =========================================================================
    # Properties
    # =========================================================================

    @property
    def criteria(self) -> Optional[SearchCriteria]:
        """Get current search criteria."""
        return self._criteria

    @property
    def weights(self) -> Optional[ScoringWeights]:
        """Get current scoring weights."""
        return self._weights

    @property
    def evaluation_run(self) -> Optional["EvaluationRun"]:
        """Get the current evaluation run."""
        return self._evaluation_run

    # =========================================================================
    # Evaluation Store Methods
    # =========================================================================

    def _start_evaluation_run(self, documents_total: int = 0) -> "EvaluationRun":
        """
        Start a new evaluation run for this review.

        Args:
            documents_total: Total number of documents to process.

        Returns:
            The created EvaluationRun.
        """
        from bmlibrarian.evaluations import RunType

        if not self._criteria:
            raise ValueError("Cannot start evaluation run without criteria")

        config_snapshot = {
            "model": self.config.model,
            "temperature": self.config.temperature,
            "top_p": self.config.top_p,
            "relevance_threshold": self.config.relevance_threshold,
            "weights": self._weights.to_dict() if self._weights else None,
        }

        self._evaluation_run = self._evaluation_store.create_run(
            run_type=RunType.SYSTEMATIC_REVIEW,
            research_question=self._criteria.research_question,
            evaluator_id=self._evaluator_id,
            config=config_snapshot,
            documents_total=documents_total,
        )

        logger.info(f"Started evaluation run: id={self._evaluation_run.run_id}")
        return self._evaluation_run

    def _save_scored_paper(
        self,
        scored_paper: ScoredPaper,
    ) -> int:
        """
        Save a scored paper to the evaluation store.

        Args:
            scored_paper: The scored paper to save (includes processing_time_ms).

        Returns:
            The evaluation ID.

        Raises:
            ValueError: If no active evaluation run exists.
            RuntimeError: If saving to database fails.
        """
        from bmlibrarian.evaluations import EvaluationType

        if not self._evaluation_run:
            raise ValueError("No active evaluation run")

        evaluation_data = {
            "score": scored_paper.relevance_score,
            "rationale": scored_paper.relevance_rationale,
        }

        if scored_paper.inclusion_decision:
            evaluation_data["inclusion_decision"] = scored_paper.inclusion_decision.status.value
            if scored_paper.inclusion_decision.rationale:
                evaluation_data["inclusion_rationale"] = scored_paper.inclusion_decision.rationale

        if scored_paper.relevant_citations:
            evaluation_data["citation_count"] = len(scored_paper.relevant_citations)

        try:
            logger.info(
                f"Saving scored paper: run_id={self._evaluation_run.run_id}, "
                f"doc_id={scored_paper.paper.document_id}, "
                f"score={scored_paper.relevance_score}, "
                f"evaluator_id={self._evaluator_id}, "
                f"processing_time_ms={scored_paper.processing_time_ms}"
            )
            eval_id = self._evaluation_store.save_evaluation(
                run_id=self._evaluation_run.run_id,
                document_id=scored_paper.paper.document_id,
                evaluation_type=EvaluationType.RELEVANCE_SCORE,
                evaluation_data=evaluation_data,
                primary_score=float(scored_paper.relevance_score),
                evaluator_id=self._evaluator_id,
                reasoning=scored_paper.relevance_rationale,
                processing_time_ms=scored_paper.processing_time_ms,
            )
            logger.info(f"Saved scored paper: eval_id={eval_id}")
            return eval_id
        except Exception as e:
            logger.error(
                f"Failed to save scored paper document_id={scored_paper.paper.document_id}: {e}",
                exc_info=True
            )
            raise RuntimeError(f"Failed to save scored paper: {e}") from e

    def _save_assessed_paper(
        self,
        assessed_paper: AssessedPaper,
    ) -> int:
        """
        Save an assessed paper to the evaluation store.

        Args:
            assessed_paper: The assessed paper to save (includes processing_time_ms).

        Returns:
            The evaluation ID.

        Raises:
            ValueError: If no active evaluation run exists.
            RuntimeError: If saving to database fails.
        """
        from bmlibrarian.evaluations import EvaluationType

        if not self._evaluation_run:
            raise ValueError("No active evaluation run")

        # Extract study_design from study_assessment (required by schema)
        study_design = assessed_paper.study_assessment.get(
            "study_design",
            assessed_paper.study_assessment.get("study_type", "unknown")
        )

        evaluation_data = {
            "study_design": study_design,
            "composite_score": assessed_paper.composite_score,
            "study_assessment": assessed_paper.study_assessment,
            "paper_weight": assessed_paper.paper_weight,
        }

        if assessed_paper.pico_components:
            evaluation_data["pico_components"] = assessed_paper.pico_components

        try:
            logger.info(
                f"Saving assessed paper: run_id={self._evaluation_run.run_id}, "
                f"doc_id={assessed_paper.scored_paper.paper.document_id}, "
                f"composite_score={assessed_paper.composite_score}, "
                f"processing_time_ms={assessed_paper.processing_time_ms}"
            )
            return self._evaluation_store.save_evaluation(
                run_id=self._evaluation_run.run_id,
                document_id=assessed_paper.scored_paper.paper.document_id,
                evaluation_type=EvaluationType.QUALITY_ASSESSMENT,
                evaluation_data=evaluation_data,
                primary_score=float(assessed_paper.composite_score) if assessed_paper.composite_score else None,
                evaluator_id=self._evaluator_id,
                processing_time_ms=assessed_paper.processing_time_ms,
            )
        except Exception as e:
            doc_id = assessed_paper.scored_paper.paper.document_id
            logger.error(f"Failed to save assessed paper document_id={doc_id}: {e}")
            raise RuntimeError(f"Failed to save assessed paper: {e}") from e

    def get_scored_papers(
        self,
        min_score: Optional[float] = None,
        limit: Optional[int] = None,
    ) -> List[ScoredPaper]:
        """
        Get scored papers from the evaluation store.

        Args:
            min_score: Optional minimum score filter.
            limit: Optional maximum number of results.

        Returns:
            List of ScoredPaper objects.
        """
        from bmlibrarian.evaluations import EvaluationType

        if not self._evaluation_run:
            return []

        evaluations = self._evaluation_store.get_evaluations_for_run(
            run_id=self._evaluation_run.run_id,
            evaluation_type=EvaluationType.RELEVANCE_SCORE,
            min_score=min_score,
            limit=limit,
        )

        # Convert evaluations back to ScoredPaper objects
        scored_papers = []
        paper_map = {p.document_id: p for p in self._all_papers}

        for eval_record in evaluations:
            paper = paper_map.get(eval_record.document_id)
            if not paper:
                logger.warning(f"Paper not found for document_id={eval_record.document_id}")
                continue

            inclusion_status = InclusionStatus.UNCERTAIN  # Default when no decision recorded
            inclusion_rationale = None
            if eval_record.evaluation_data.get("inclusion_decision"):
                try:
                    inclusion_status = InclusionStatus(eval_record.evaluation_data["inclusion_decision"])
                except ValueError:
                    pass
                inclusion_rationale = eval_record.evaluation_data.get("inclusion_rationale")

            scored_paper = ScoredPaper(
                paper=paper,
                relevance_score=eval_record.primary_score or 0.0,
                relevance_rationale=eval_record.reasoning or "",
                inclusion_decision=InclusionDecision(
                    status=inclusion_status,
                    stage=ExclusionStage.RELEVANCE_SCORING,
                    reasons=["Restored from database"],
                    rationale=inclusion_rationale or "Restored from previous evaluation",
                ),
                processing_time_ms=eval_record.processing_time_ms,
            )
            scored_papers.append(scored_paper)

        return scored_papers

    def get_assessed_papers(
        self,
        min_score: Optional[float] = None,
        limit: Optional[int] = None,
        _scored_papers_map: Optional[Dict[int, ScoredPaper]] = None,
    ) -> List[AssessedPaper]:
        """
        Get assessed papers from the evaluation store.

        Args:
            min_score: Optional minimum composite score filter.
            limit: Optional maximum number of results.
            _scored_papers_map: Optional pre-fetched map of document_id -> ScoredPaper.
                               Used internally to avoid N+1 query pattern when calling
                               get_scored_and_assessed_papers(). Prefer using that method
                               when you need both scored and assessed papers.

        Returns:
            List of AssessedPaper objects.
        """
        from bmlibrarian.evaluations import EvaluationType

        if not self._evaluation_run:
            return []

        evaluations = self._evaluation_store.get_evaluations_for_run(
            run_id=self._evaluation_run.run_id,
            evaluation_type=EvaluationType.QUALITY_ASSESSMENT,
            min_score=min_score,
            limit=limit,
        )

        # Use provided map or fetch scored papers (causes additional query)
        if _scored_papers_map is not None:
            scored_map = _scored_papers_map
        else:
            scored_papers = self.get_scored_papers()
            scored_map = {sp.paper.document_id: sp for sp in scored_papers}

        assessed_papers = []
        for eval_record in evaluations:
            scored_paper = scored_map.get(eval_record.document_id)
            if not scored_paper:
                logger.warning(f"ScoredPaper not found for document_id={eval_record.document_id}")
                continue

            assessed_paper = AssessedPaper(
                scored_paper=scored_paper,
                study_assessment=eval_record.evaluation_data.get("study_assessment", {}),
                paper_weight=eval_record.evaluation_data.get("paper_weight", {}),
                pico_components=eval_record.evaluation_data.get("pico_components"),
                composite_score=eval_record.primary_score,
            )
            assessed_papers.append(assessed_paper)

        return assessed_papers

    def get_scored_and_assessed_papers(
        self,
        min_relevance_score: Optional[float] = None,
        min_composite_score: Optional[float] = None,
    ) -> Tuple[List[ScoredPaper], List[AssessedPaper]]:
        """
        Get both scored and assessed papers efficiently in a single database query.

        This method avoids the N+1 query pattern by fetching both RELEVANCE_SCORE
        and QUALITY_ASSESSMENT evaluations in a single query.

        Args:
            min_relevance_score: Optional minimum relevance score filter.
            min_composite_score: Optional minimum composite score filter.

        Returns:
            Tuple of (scored_papers, assessed_papers).
        """
        from bmlibrarian.evaluations import EvaluationType

        if not self._evaluation_run:
            return [], []

        # Fetch both evaluation types in a single query
        eval_map = self._evaluation_store.get_evaluations_for_multiple_types(
            run_id=self._evaluation_run.run_id,
            evaluation_types=[EvaluationType.RELEVANCE_SCORE, EvaluationType.QUALITY_ASSESSMENT],
        )

        # Build paper lookup map
        paper_map = {p.document_id: p for p in self._all_papers}

        # Build scored papers from relevance scores
        relevance_evals = eval_map.get(EvaluationType.RELEVANCE_SCORE.value, [])
        scored_papers = []
        scored_map: Dict[int, ScoredPaper] = {}

        for eval_record in relevance_evals:
            # Apply min_relevance_score filter
            if min_relevance_score is not None:
                if eval_record.primary_score is None or eval_record.primary_score < min_relevance_score:
                    continue

            paper = paper_map.get(eval_record.document_id)
            if not paper:
                logger.warning(f"Paper not found for document_id={eval_record.document_id}")
                continue

            inclusion_status = InclusionStatus.UNCERTAIN  # Default when no decision recorded
            inclusion_rationale = None
            if eval_record.evaluation_data.get("inclusion_decision"):
                try:
                    inclusion_status = InclusionStatus(eval_record.evaluation_data["inclusion_decision"])
                except ValueError:
                    pass
                inclusion_rationale = eval_record.evaluation_data.get("inclusion_rationale")

            scored_paper = ScoredPaper(
                paper=paper,
                relevance_score=eval_record.primary_score or 0.0,
                relevance_rationale=eval_record.reasoning or "",
                inclusion_decision=InclusionDecision(
                    status=inclusion_status,
                    stage=ExclusionStage.RELEVANCE_SCORING,
                    reasons=["Restored from database"],
                    rationale=inclusion_rationale or "Restored from previous evaluation",
                ),
                processing_time_ms=eval_record.processing_time_ms,
            )
            scored_papers.append(scored_paper)
            scored_map[paper.document_id] = scored_paper

        # Build assessed papers using the scored_map (avoids N+1)
        quality_evals = eval_map.get(EvaluationType.QUALITY_ASSESSMENT.value, [])
        assessed_papers = []

        for eval_record in quality_evals:
            # Apply min_composite_score filter
            if min_composite_score is not None:
                if eval_record.primary_score is None or eval_record.primary_score < min_composite_score:
                    continue

            matched_paper = scored_map.get(eval_record.document_id)
            if not matched_paper:
                logger.warning(f"ScoredPaper not found for document_id={eval_record.document_id}")
                continue

            assessed_paper = AssessedPaper(
                scored_paper=matched_paper,
                study_assessment=eval_record.evaluation_data.get("study_assessment", {}),
                paper_weight=eval_record.evaluation_data.get("paper_weight", {}),
                pico_components=eval_record.evaluation_data.get("pico_components"),
                composite_score=eval_record.primary_score,
            )
            assessed_papers.append(assessed_paper)

        return scored_papers, assessed_papers

    def get_below_threshold_papers(self) -> List[ScoredPaper]:
        """
        Get papers that scored below the relevance threshold.

        Returns:
            List of ScoredPaper objects below threshold.
        """
        from bmlibrarian.evaluations import EvaluationType

        if not self._evaluation_run:
            return []

        # Get all scored papers and filter those below threshold
        all_evaluations = self._evaluation_store.get_evaluations_for_run(
            run_id=self._evaluation_run.run_id,
            evaluation_type=EvaluationType.RELEVANCE_SCORE,
        )

        paper_map = {p.document_id: p for p in self._all_papers}
        threshold = self.config.relevance_threshold

        below_threshold = []
        for eval_record in all_evaluations:
            if eval_record.primary_score is not None and eval_record.primary_score < threshold:
                paper = paper_map.get(eval_record.document_id)
                if paper:
                    scored_paper = ScoredPaper(
                        paper=paper,
                        relevance_score=eval_record.primary_score,
                        relevance_rationale=eval_record.reasoning or "",
                        inclusion_decision=InclusionDecision(
                            status=InclusionStatus.EXCLUDED,
                            stage=ExclusionStage.RELEVANCE_SCORING,
                            reasons=["Below relevance threshold"],
                            rationale="Below relevance threshold",
                        ),
                    )
                    below_threshold.append(scored_paper)

        return below_threshold

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
        from bmlibrarian.evaluations import RunStatus

        if not self._evaluation_run:
            return

        status = RunStatus.COMPLETED if success else RunStatus.FAILED
        run_id = self._evaluation_run.run_id
        try:
            self._evaluation_store.complete_run(
                run_id=run_id,
                status=status,
                error_message=error_message,
            )
        except Exception as e:
            # Never let a status update mask the review's own outcome
            logger.error(f"Failed to mark evaluation run {run_id} {status.value}: {e}")
            return
        logger.info(f"Completed evaluation run: id={run_id}, status={status.value}")

    def _pause_evaluation_run(self) -> None:
        """
        Mark the current evaluation run paused (aborted or interrupted).

        A paused run can be continued with ``run_review_from_checkpoint``.
        """
        if not self._evaluation_run:
            return

        run_id = self._evaluation_run.run_id
        try:
            self._evaluation_store.pause_run(run_id)
        except Exception as e:
            logger.error(f"Failed to mark evaluation run {run_id} paused: {e}")
            return
        logger.info(f"Paused evaluation run: id={run_id}")

    # =========================================================================
    # Main Entry Point
    # =========================================================================

    def run_review(
        self,
        criteria: SearchCriteria,
        weights: Optional[ScoringWeights] = None,
        interactive: bool = True,
        output_path: Optional[str] = None,
        checkpoint_callback: Optional[Callable[[str, Dict], bool]] = None,
    ) -> SystematicReviewResult:
        """
        Run complete systematic review workflow.

        This is the main entry point for conducting a systematic review.
        The workflow proceeds through multiple phases, pausing at checkpoints
        for human approval when in interactive mode. After search planning,
        the phases run in the review pipeline shared with
        ``run_review_from_checkpoint``.

        Args:
            criteria: SearchCriteria defining what papers to find
            weights: Optional ScoringWeights for composite scoring.
                    Defaults to equal weights if not provided.
            interactive: If True, pause at checkpoints for approval.
                        If False, run autonomously.
            output_path: Optional path to save results JSON.
            checkpoint_callback: Optional callback for checkpoint decisions.
                               Receives (checkpoint_type, state) and returns
                               True to continue or False to abort.

        Returns:
            SystematicReviewResult with all papers and audit trail (empty if
            a checkpoint was rejected).

        Raises:
            ValueError: If criteria or weights validation fails
            SystematicReviewError: If the review fails

        Example:
            >>> result = agent.run_review(
            ...     criteria=criteria,
            ...     weights=ScoringWeights(relevance=0.4, study_quality=0.3),
            ...     interactive=True,
            ...     output_path="results.json"
            ... )
        """
        criteria_errors = validate_search_criteria(criteria)
        if criteria_errors:
            raise ValueError(f"Invalid search criteria: {'; '.join(criteria_errors)}")

        if weights is None:
            weights = self.config.scoring_weights
        else:
            weight_errors = validate_scoring_weights(weights)
            if weight_errors:
                raise ValueError(f"Invalid scoring weights: {'; '.join(weight_errors)}")

        # Start from clean state: nothing from a previous review on this
        # instance may leak into this one.
        self._criteria = criteria
        self._weights = weights
        self._search_plan = None
        self._executed_queries = []
        self._all_papers = []
        self._rejected_initial_filter = []
        self._paper_sources = {}
        self._semantic_baseline_ids = set()
        self._query_feedback = None

        self.documenter = Documenter()
        self.documenter.start_review()
        self.documenter.log_step(
            action="initialize_review",
            tool=None,
            input_summary=f"Research question: {criteria.research_question[:100]}...",
            output_summary="Review initialized successfully",
            decision_rationale="Starting systematic review with user-defined criteria",
            metrics={
                "inclusion_criteria_count": len(criteria.inclusion_criteria),
                "exclusion_criteria_count": len(criteria.exclusion_criteria),
                "has_date_range": criteria.date_range is not None,
                "has_study_type_filter": criteria.target_study_types is not None,
            }
        )

        # Database-backed run: every evaluation is saved as it is made, so an
        # interrupted review can resume without re-scoring.
        self._start_evaluation_run(documents_total=0)

        options = ReviewRunOptions(
            interactive=interactive,
            output_path=output_path,
            checkpoint_callback=checkpoint_callback,
        )
        return self._run_guarded(lambda: self._plan_and_execute(options))

    def _plan_and_execute(self, options: ReviewRunOptions) -> SystematicReviewResult:
        """
        Generate the search plan, pass its checkpoint, then run the pipeline.

        Args:
            options: Caller options for checkpoints and output.

        Returns:
            The completed review result.

        Raises:
            ReviewAborted: If the user rejects a checkpoint.
        """
        from .planner import Planner

        criteria = self._active_criteria()
        planner = Planner(
            model=self.config.model,
            host=self.config.host,
            config=self.config,
            callback=self.callback,
        )

        self.documenter.set_phase("search_planning")
        with self.documenter.log_step_with_timer(
            action=ACTION_GENERATE_SEARCH_PLAN,
            tool="Planner",
            input_summary=f"Research question: {criteria.research_question[:100]}...",
            decision_rationale="Generating diverse queries for comprehensive coverage",
        ) as timer:
            plan = planner.generate_search_plan(criteria)
            self._search_plan = plan
            timer.set_output(f"Generated {len(plan.queries)} queries")
            timer.add_metrics({
                "queries_generated": len(plan.queries),
                "estimated_yield": plan.total_estimated_yield,
            })

        self._require_checkpoint(
            CHECKPOINT_SEARCH_STRATEGY,
            {
                "search_plan": plan.to_dict(),
                "queries_count": len(plan.queries),
            },
            options,
        )
        return self._execute_pipeline(ReviewStage.EXECUTE_SEARCH, options)

    def _build_empty_result(
        self,
        criteria: SearchCriteria,
        weights: ScoringWeights,
        reason: str,
    ) -> SystematicReviewResult:
        """
        Build an empty result when review is aborted.

        Args:
            criteria: The search criteria that was used
            weights: The scoring weights that were configured
            reason: Why the review was aborted

        Returns:
            SystematicReviewResult with zero papers and abort reason
        """
        from .reporter import Reporter

        reporter = Reporter(
            documenter=self.documenter,
            criteria=criteria,
            weights=weights,
        )

        doc_stats = self.documenter.get_statistics()
        statistics = ReviewStatistics(
            total_considered=0,
            passed_initial_filter=0,
            passed_relevance_threshold=0,
            passed_quality_gate=0,
            final_included=0,
            final_excluded=0,
            uncertain_for_review=0,
            processing_time_seconds=self.documenter.get_duration(),
            total_llm_calls=doc_stats.get("total_llm_calls", 0),
            total_tokens_used=doc_stats.get("total_tokens", 0),
        )

        return reporter.build_json_result(
            included_papers=[],
            excluded_papers=[],
            uncertain_papers=[],
            search_plan=self._search_plan,
            executed_queries=self._executed_queries,
            statistics=statistics,
        )

    # =========================================================================
    # Checkpoint Handling
    # =========================================================================

    def _checkpoint(
        self,
        checkpoint_type: str,
        state: Dict[str, Any],
        interactive: bool,
        checkpoint_callback: Optional[Callable[[str, Dict], bool]] = None,
        output_dir: Optional[str] = None,
    ) -> bool:
        """
        Handle a workflow checkpoint.

        In interactive mode, pauses for human approval.
        In auto mode, continues unless callback returns False.
        When output_dir is provided, saves a checkpoint file for resumability.

        Args:
            checkpoint_type: Type of checkpoint (e.g., "search_strategy")
            state: Current state snapshot
            interactive: Whether running in interactive mode
            checkpoint_callback: Optional callback for decision
            output_dir: Optional directory for saving checkpoint files

        Returns:
            True to continue, False to abort
        """
        # Log checkpoint
        checkpoint = self.documenter.log_checkpoint(
            checkpoint_type=checkpoint_type,
            phase=self.documenter._current_phase,
            state_snapshot=state,
        )

        # Save checkpoint file for resumability (before getting user decision)
        if output_dir:
            checkpoint_path = self._save_checkpoint_file(checkpoint_type, output_dir)
            if checkpoint_path:
                logger.info(f"Checkpoint saved for resume: {checkpoint_path}")

        # If callback provided, use it
        if checkpoint_callback:
            decision = checkpoint_callback(checkpoint_type, state)
            checkpoint.user_decision = "approved" if decision else "rejected"
            return decision

        # In non-interactive mode, auto-approve
        if not interactive:
            checkpoint.user_decision = "auto_approved"
            return True

        # Interactive mode without callback - would need UI integration
        # For now, auto-approve with warning
        logger.warning(
            f"Checkpoint '{checkpoint_type}' reached in interactive mode "
            "but no callback provided. Auto-approving."
        )
        checkpoint.user_decision = "auto_approved_no_callback"
        return True

    def _save_checkpoint_file(
        self,
        checkpoint_type: str,
        output_dir: str,
    ) -> Optional[str]:
        """
        Save complete checkpoint state to a file for resumability.

        Saves all state needed to resume the review from this checkpoint:
        - Search criteria and weights
        - Search plan and executed queries
        - All paper document IDs (papers are re-fetched on resume)
        - Documenter state

        Args:
            checkpoint_type: Type of checkpoint being saved
            output_dir: Directory to save checkpoint files

        Returns:
            Path to saved checkpoint file, or None if save failed
        """
        from pathlib import Path
        import json

        try:
            # Build complete state for resumability
            resume_state = {
                "version": AGENT_VERSION,
                "checkpoint_type": checkpoint_type,
                "review_id": self.documenter.review_id,
                "timestamp": datetime.now().isoformat(),
                # Input parameters
                "criteria": self._criteria.to_dict() if self._criteria else None,
                "weights": self._weights.to_dict() if self._weights else None,
                # Search state
                "search_plan": self._search_plan.to_dict() if self._search_plan else None,
                "executed_queries": [q.to_dict() for q in self._executed_queries],
                # Paper IDs (full data re-fetched on resume)
                "paper_document_ids": [p.document_id for p in self._all_papers],
                "paper_count": len(self._all_papers),
                # Evaluation run ID (scored/assessed papers stored in database)
                "evaluation_run_id": self._evaluation_run.run_id if self._evaluation_run else None,
                # Excluded paper tracking for comprehensive reporting
                "rejected_initial_filter": [
                    {"document_id": paper.document_id, "reason": reason}
                    for paper, reason in self._rejected_initial_filter
                ],
                # Documenter state
                "documenter_phase": self.documenter._current_phase,
            }

            # Create checkpoint directory
            checkpoint_dir = Path(output_dir).expanduser() / "checkpoints"
            checkpoint_dir.mkdir(parents=True, exist_ok=True)

            # Save checkpoint file
            filename = f"{self.documenter.review_id}_{checkpoint_type}.json"
            filepath = checkpoint_dir / filename

            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(resume_state, f, indent=2, ensure_ascii=False)

            logger.info(f"Checkpoint saved to: {filepath}")
            return str(filepath)

        except Exception as e:
            logger.error(f"Failed to save checkpoint file: {e}")
            return None

    # =========================================================================
    # Child Agent Initialization (Lazy)
    # =========================================================================

    def _get_query_agent(self):
        """Get or create QueryAgent instance."""
        if self._query_agent is None:
            from ..query_agent import QueryAgent
            from ...config import get_model, get_ollama_host, get_agent_config

            model = get_model("query_agent")
            config = get_agent_config("query")

            self._query_agent = QueryAgent(
                model=model,
                host=get_ollama_host(),
                temperature=config.get("temperature", 0.1),
                top_p=config.get("top_p", 0.9),
                callback=self.callback,
                orchestrator=self.orchestrator,
                show_model_info=False,
            )
        return self._query_agent

    def _get_scoring_agent(self):
        """Get or create DocumentScoringAgent instance."""
        if self._scoring_agent is None:
            from ..scoring_agent import DocumentScoringAgent
            from ...config import get_model, get_ollama_host, get_agent_config

            model = get_model("scoring_agent")
            config = get_agent_config("scoring")

            self._scoring_agent = DocumentScoringAgent(
                model=model,
                host=get_ollama_host(),
                temperature=config.get("temperature", 0.1),
                top_p=config.get("top_p", 0.9),
                callback=self.callback,
                orchestrator=self.orchestrator,
                show_model_info=False,
            )
        return self._scoring_agent

    def _get_semantic_query_agent(self):
        """Get or create SemanticQueryAgent instance."""
        if self._semantic_query_agent is None:
            from ..semantic_query_agent import SemanticQueryAgent

            self._semantic_query_agent = SemanticQueryAgent(
                callback=self.callback,
                show_model_info=False,
            )
        return self._semantic_query_agent

    def _get_pico_agent(self):
        """Get or create PICOAgent instance."""
        if self._pico_agent is None:
            from ..pico_agent import PICOAgent
            from ...config import get_model, get_ollama_host, get_agent_config

            model = get_model("pico_agent")
            config = get_agent_config("pico")

            self._pico_agent = PICOAgent(
                model=model,
                host=get_ollama_host(),
                temperature=config.get("temperature", 0.1),
                top_p=config.get("top_p", 0.9),
                callback=self.callback,
                orchestrator=self.orchestrator,
                show_model_info=False,
            )
        return self._pico_agent

    def _get_study_assessment_agent(self):
        """Get or create StudyAssessmentAgent instance."""
        if self._study_assessment_agent is None:
            from ..study_assessment_agent import StudyAssessmentAgent
            from ...config import get_model, get_ollama_host, get_agent_config

            model = get_model("study_assessment_agent")
            config = get_agent_config("study_assessment")

            self._study_assessment_agent = StudyAssessmentAgent(
                model=model,
                host=get_ollama_host(),
                temperature=config.get("temperature", 0.1),
                top_p=config.get("top_p", 0.9),
                callback=self.callback,
                orchestrator=self.orchestrator,
                show_model_info=False,
            )
        return self._study_assessment_agent

    def _get_paper_weight_agent(self):
        """Get or create PaperWeightAssessmentAgent instance."""
        if self._paper_weight_agent is None:
            from ..paper_weight import PaperWeightAssessmentAgent
            from ...config import get_model, get_ollama_host, get_agent_config

            model = get_model("paper_weight_assessment_agent")
            config = get_agent_config("paper_weight_assessment")

            self._paper_weight_agent = PaperWeightAssessmentAgent(
                model=model,
                host=get_ollama_host(),
                temperature=config.get("temperature", 0.3),
                top_p=config.get("top_p", 0.9),
                callback=self.callback,
                orchestrator=self.orchestrator,
                show_model_info=False,
            )
        return self._paper_weight_agent

    def _get_prisma_agent(self):
        """Get or create PRISMA2020Agent instance."""
        if self._prisma_agent is None:
            from ..prisma2020_agent import PRISMA2020Agent
            from ...config import get_model, get_ollama_host, get_agent_config

            model = get_model("prisma2020_agent")
            config = get_agent_config("prisma2020")

            self._prisma_agent = PRISMA2020Agent(
                model=model,
                host=get_ollama_host(),
                temperature=config.get("temperature", 0.1),
                top_p=config.get("top_p", 0.9),
                callback=self.callback,
                orchestrator=self.orchestrator,
                show_model_info=False,
            )
        return self._prisma_agent

    # =========================================================================
    # Utility Methods
    # =========================================================================

    def get_review_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about the current/last review.

        Returns:
            Dictionary with review statistics
        """
        # Get counts from database using combined query to avoid N+1 pattern
        scored_papers, assessed_papers = self.get_scored_and_assessed_papers()

        return {
            "review_id": self.documenter.review_id,
            "evaluation_run_id": self._evaluation_run.run_id if self._evaluation_run else None,
            "papers_found": len(self._all_papers),
            "papers_scored": len(scored_papers),
            "papers_assessed": len(assessed_papers),
            "process_steps": len(self.documenter.steps),
            "checkpoints": len(self.documenter.checkpoints),
            "duration_seconds": self.documenter.get_duration(),
        }

    def export_audit_trail(
        self,
        output_path: str,
        format: str = "markdown"
    ) -> None:
        """
        Export the audit trail to a file.

        Args:
            output_path: Path for the output file
            format: Output format ("markdown" or "json")
        """
        self.documenter.save_to_file(output_path, format=format)

    def test_connection(self) -> bool:
        """
        Test connection to Ollama and verify model availability.

        Returns:
            True if connection is successful and model is available
        """
        try:
            result = super().test_connection()
            if result:
                logger.info(
                    f"SystematicReviewAgent connection test passed. "
                    f"Model: {self.model}"
                )
            return result
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return False

    def reset(self) -> None:
        """
        Reset agent state for a new review.

        Clears all papers, scores, and creates new documenter.
        Does not reset configuration.
        """
        # Complete any existing evaluation run as aborted
        if self._evaluation_run:
            self._complete_evaluation_run(success=False, error_message="Review aborted by reset")
            self._evaluation_run = None

        self._criteria = None
        self._weights = None
        self._search_plan = None
        self._executed_queries = []
        self._all_papers = []
        # Clear excluded paper tracking (initial filter results not in database)
        self._rejected_initial_filter = []
        self._paper_sources = {}
        self._semantic_baseline_ids = set()
        self._query_feedback = None
        self.documenter = Documenter()
        self.reset_metrics()
        logger.info("SystematicReviewAgent state reset")
