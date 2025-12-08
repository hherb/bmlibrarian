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

Phase 1 Implementation:
- Agent skeleton with configuration and component initialization
- Basic workflow structure with NotImplementedError stubs
- Integration with BaseAgent patterns
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple, TYPE_CHECKING

from ..base import BaseAgent, PerformanceMetrics

from .config import (
    SystematicReviewConfig,
    get_systematic_review_config,
    AGENT_TYPE,
    CHECKPOINT_TITLE_TRUNCATE_LENGTH,
    CHECKPOINT_SAMPLE_TITLES_COUNT,
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
from .documenter import Documenter
from .exceptions import (
    SystematicReviewError,
    SearchPlanningError,
    SearchExecutionError,
    ScoringError,
    QualityAssessmentError,
    ReportGenerationError,
    LLMConnectionError,
    DatabaseConnectionError,
)
from .resume_mixin import CheckpointResumeMixin

if TYPE_CHECKING:
    from ..orchestrator import AgentOrchestrator
    from .executor import AggregatedResults, PhasedSearchResults
    from .scorer import RelevanceScorer, CompositeScorer
    from .quality import QualityAssessor
    from .reporter import Reporter
    from bmlibrarian.database import DatabaseManager
    from bmlibrarian.evaluations import EvaluationStore, EvaluationRun

logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

AGENT_VERSION = "1.0.0"

# Action names for audit trail
ACTION_GENERATE_SEARCH_PLAN = "generate_search_plan"
ACTION_EXECUTE_SEARCH = "execute_search"
ACTION_INITIAL_FILTER = "initial_filter"
ACTION_SCORE_RELEVANCE = "score_relevance"
ACTION_ASSESS_QUALITY = "assess_quality"
ACTION_CALCULATE_COMPOSITE = "calculate_composite"
ACTION_GENERATE_REPORT = "generate_report"

# Checkpoint types
CHECKPOINT_SEARCH_STRATEGY = "search_strategy"
CHECKPOINT_INITIAL_RESULTS = "initial_results"
CHECKPOINT_SCORING_COMPLETE = "scoring_complete"
CHECKPOINT_QUALITY_ASSESSMENT = "quality_assessment"

# Note: CHECKPOINT_TITLE_TRUNCATE_LENGTH and CHECKPOINT_SAMPLE_TITLES_COUNT
# are imported from config.py to avoid duplication


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
        processing_time_ms: Optional[int] = None,
    ) -> int:
        """
        Save a scored paper to the evaluation store.

        Args:
            scored_paper: The scored paper to save.
            processing_time_ms: Optional processing time in milliseconds.

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
                f"evaluator_id={self._evaluator_id}"
            )
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
        processing_time_ms: Optional[int] = None,
    ) -> int:
        """
        Save an assessed paper to the evaluation store.

        Args:
            assessed_paper: The assessed paper to save.
            processing_time_ms: Optional processing time in milliseconds.

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
            "composite_score": assessed_paper.composite_score,
            "study_assessment": assessed_paper.study_assessment,
            "paper_weight": assessed_paper.paper_weight,
        }

        if assessed_paper.pico_components:
            evaluation_data["pico_components"] = assessed_paper.pico_components

        try:
            return self._evaluation_store.save_evaluation(
                run_id=self._evaluation_run.run_id,
                document_id=assessed_paper.scored_paper.paper.document_id,
                evaluation_type=EvaluationType.QUALITY_ASSESSMENT,
                evaluation_data=evaluation_data,
                primary_score=float(assessed_paper.composite_score) if assessed_paper.composite_score else None,
                evaluator_id=self._evaluator_id,
                processing_time_ms=processing_time_ms,
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

            inclusion_status = InclusionStatus.PENDING
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
                    rationale=inclusion_rationale,
                ),
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

            inclusion_status = InclusionStatus.PENDING
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
                    rationale=inclusion_rationale,
                ),
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
            if eval_record.primary_score and eval_record.primary_score < threshold:
                paper = paper_map.get(eval_record.document_id)
                if paper:
                    scored_paper = ScoredPaper(
                        paper=paper,
                        relevance_score=eval_record.primary_score,
                        relevance_rationale=eval_record.reasoning or "",
                        inclusion_decision=InclusionDecision(
                            status=InclusionStatus.EXCLUDED,
                            rationale="Below relevance threshold",
                            exclusion_stage=ExclusionStage.RELEVANCE_SCORING,
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
        self._evaluation_store.complete_run(
            run_id=self._evaluation_run.run_id,
            status=status,
            error_message=error_message,
        )
        logger.info(f"Completed evaluation run: id={self._evaluation_run.run_id}, status={status.value}")

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
        for human approval when in interactive mode.

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
            SystematicReviewResult with all papers and audit trail

        Raises:
            ValueError: If criteria validation fails
            NotImplementedError: Phase 1 skeleton - full implementation in Phase 2-5

        Example:
            >>> result = agent.run_review(
            ...     criteria=criteria,
            ...     weights=ScoringWeights(relevance=0.4, study_quality=0.3),
            ...     interactive=True,
            ...     output_path="results.json"
            ... )
        """
        # Validate inputs
        criteria_errors = validate_search_criteria(criteria)
        if criteria_errors:
            raise ValueError(f"Invalid search criteria: {'; '.join(criteria_errors)}")

        # Use provided weights or defaults
        if weights is None:
            weights = self.config.scoring_weights
        else:
            weight_errors = validate_scoring_weights(weights)
            if weight_errors:
                raise ValueError(f"Invalid scoring weights: {'; '.join(weight_errors)}")

        # Extract output directory for checkpoint saving
        from pathlib import Path
        output_dir: Optional[str] = None
        if output_path:
            output_dir = str(Path(output_path).expanduser().parent)

        # Store current review parameters
        self._criteria = criteria
        self._weights = weights

        # Initialize documenter for this review
        self.documenter = Documenter()
        self.documenter.start_review()

        # Log initialization
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

        # Start evaluation run for database-backed tracking
        # This enables saving evaluations and checking for cached results
        self._start_evaluation_run(documents_total=0)  # Will be updated after search

        # =====================================================================
        # Phase 5: Complete Workflow Implementation
        # =====================================================================

        try:
            # Import required components
            from .planner import Planner
            from .executor import SearchExecutor, PhasedSearchResults
            from .filters import InitialFilter, InclusionEvaluator
            from .scorer import RelevanceScorer, CompositeScorer
            from .quality import QualityAssessor
            from .reporter import Reporter

            # Initialize components
            planner = Planner(
                model=self.config.model,
                host=self.config.host,
                config=self.config,
                callback=self.callback,
            )

            executor = SearchExecutor(
                config=self.config,
                results_per_query=self.config.max_results_per_query,
                callback=self.callback,
            )

            initial_filter = InitialFilter(
                criteria=criteria,
                callback=self.callback,
            )

            scorer = RelevanceScorer(
                research_question=criteria.research_question,
                config=self.config,
                callback=self.callback,
                orchestrator=self.orchestrator,
                criteria=criteria,
            )

            quality_assessor = QualityAssessor(
                config=self.config,
                callback=self.callback,
                orchestrator=self.orchestrator,
            )

            composite_scorer = CompositeScorer(weights=weights)

            reporter = Reporter(
                documenter=self.documenter,
                criteria=criteria,
                weights=weights,
            )

            # =================================================================
            # Phase 1: Generate Search Plan
            # =================================================================
            self.documenter.set_phase("search_planning")

            with self.documenter.log_step_with_timer(
                action=ACTION_GENERATE_SEARCH_PLAN,
                tool="Planner",
                input_summary=f"Research question: {criteria.research_question[:100]}...",
                decision_rationale="Generating diverse queries for comprehensive coverage",
            ) as timer:
                self._search_plan = planner.generate_search_plan(criteria)
                timer.set_output(f"Generated {len(self._search_plan.queries)} queries")
                timer.add_metrics({
                    "queries_generated": len(self._search_plan.queries),
                    "estimated_yield": self._search_plan.total_estimated_yield,
                })

            # Checkpoint: Review search strategy
            if not self._checkpoint(
                checkpoint_type=CHECKPOINT_SEARCH_STRATEGY,
                state={
                    "search_plan": self._search_plan.to_dict(),
                    "queries_count": len(self._search_plan.queries),
                },
                interactive=interactive,
                checkpoint_callback=checkpoint_callback,
                output_dir=output_dir,
            ):
                logger.info("Review aborted at search strategy checkpoint")
                self.documenter.end_review()
                return self._build_empty_result(criteria, weights, "Aborted at search strategy")

            # =================================================================
            # Phase 2: Execute Search Plan
            # =================================================================
            self.documenter.set_phase("search_execution")

            # Choose search strategy based on configuration
            # Track common variables for both search modes
            total_before_dedup = 0
            paper_sources: Dict[int, List[str]] = {}

            if self.config.use_phased_search:
                # Phased search: semantic/HyDE first, then keyword
                with self.documenter.log_step_with_timer(
                    action=ACTION_EXECUTE_SEARCH,
                    tool="SearchExecutor (Phased)",
                    input_summary=f"Executing {len(self._search_plan.queries)} queries in two phases",
                    decision_rationale="Running phased search: semantic/HyDE first for baseline, then keyword",
                ) as timer:
                    phased_results = executor.execute_phased_plan(
                        self._search_plan,
                        max_phase2_no_overlap=self.config.max_phase2_no_overlap,
                    )
                    self._executed_queries = phased_results.executed_queries
                    self._all_papers = phased_results.all_papers
                    # Store phased results for query feedback
                    self._phased_results = phased_results
                    self._semantic_baseline_ids = phased_results.phase1_document_ids
                    paper_sources = phased_results.paper_sources

                    # Calculate total before dedup from executed queries
                    total_before_dedup = sum(
                        len(eq.document_ids) for eq in phased_results.executed_queries
                    )

                    timer.set_output(
                        f"Found {phased_results.total_count} unique papers "
                        f"(Phase 1: {phased_results.phase1_count}, Phase 2 new: {phased_results.phase2_new_count})"
                    )
                    timer.add_metrics({
                        "phase1_papers": phased_results.phase1_count,
                        "phase2_new_papers": phased_results.phase2_new_count,
                        "unique_papers": phased_results.total_count,
                        "search_strategy": "phased",
                    })
            else:
                # Standard search: all queries at once
                with self.documenter.log_step_with_timer(
                    action=ACTION_EXECUTE_SEARCH,
                    tool="SearchExecutor",
                    input_summary=f"Executing {len(self._search_plan.queries)} queries",
                    decision_rationale="Running all planned queries to find candidate papers",
                ) as timer:
                    search_results = executor.execute_plan(self._search_plan)
                    self._executed_queries = search_results.executed_queries
                    self._all_papers = search_results.papers
                    self._phased_results = None
                    self._semantic_baseline_ids = set()
                    total_before_dedup = search_results.total_before_dedup
                    paper_sources = search_results.paper_sources

                    timer.set_output(
                        f"Found {search_results.count} unique papers "
                        f"from {search_results.total_before_dedup} total"
                    )
                    timer.add_metrics({
                        "total_papers_found": search_results.total_before_dedup,
                        "unique_papers": search_results.count,
                        "deduplication_rate": round(search_results.deduplication_rate * 100, 2),
                        "search_strategy": "standard",
                    })

            # Track statistics
            total_considered = len(self._all_papers)

            # Checkpoint: Review initial results
            if not self._checkpoint(
                checkpoint_type=CHECKPOINT_INITIAL_RESULTS,
                state={
                    "unique_papers": len(self._all_papers),
                    "total_before_dedup": total_before_dedup,
                    "sample_titles": [
                        p.title[:CHECKPOINT_TITLE_TRUNCATE_LENGTH]
                        for p in self._all_papers[:CHECKPOINT_SAMPLE_TITLES_COUNT]
                    ],
                },
                interactive=interactive,
                checkpoint_callback=checkpoint_callback,
                output_dir=output_dir,
            ):
                logger.info("Review aborted at initial results checkpoint")
                self.documenter.end_review()
                return self._build_empty_result(criteria, weights, "Aborted at initial results")

            # =================================================================
            # Phase 3: Initial Filtering
            # =================================================================
            self.documenter.set_phase("initial_filtering")

            with self.documenter.log_step_with_timer(
                action=ACTION_INITIAL_FILTER,
                tool="InitialFilter",
                input_summary=f"Filtering {len(self._all_papers)} papers with heuristics",
                decision_rationale="Fast filtering before expensive LLM scoring",
            ) as timer:
                filter_result = initial_filter.filter_batch(self._all_papers)
                passed_filter = filter_result.passed
                rejected_filter = filter_result.rejected
                # Store for comprehensive reporting
                self._rejected_initial_filter = rejected_filter

                timer.set_output(
                    f"Passed: {len(passed_filter)}, Rejected: {len(rejected_filter)}"
                )
                timer.add_metrics({
                    "passed": len(passed_filter),
                    "rejected": len(rejected_filter),
                    "pass_rate": round(len(passed_filter) / total_considered * 100, 2) if total_considered > 0 else 0,
                })

            passed_initial_filter = len(passed_filter)

            # =================================================================
            # Phase 4: Relevance Scoring
            # =================================================================
            self.documenter.set_phase("relevance_scoring")

            # Check for already-evaluated documents to avoid redundant LLM calls
            from bmlibrarian.evaluations import EvaluationType
            all_doc_ids = [p.document_id for p in passed_filter]
            already_evaluated_ids = set(
                self._evaluation_store.get_evaluated_document_ids(
                    run_id=self._evaluation_run.run_id,
                    evaluation_type=EvaluationType.RELEVANCE_SCORE,
                )
            )
            papers_to_score = [p for p in passed_filter if p.document_id not in already_evaluated_ids]
            cached_count = len(passed_filter) - len(papers_to_score)

            if cached_count > 0:
                logger.info(
                    f"Found {cached_count} already-evaluated documents, "
                    f"scoring {len(papers_to_score)} new documents"
                )

            with self.documenter.log_step_with_timer(
                action=ACTION_SCORE_RELEVANCE,
                tool="RelevanceScorer",
                input_summary=f"Scoring {len(papers_to_score)} papers for relevance ({cached_count} cached)",
                decision_rationale="Assessing relevance to research question using LLM",
            ) as timer:
                if papers_to_score:
                    scoring_result = scorer.score_batch(
                        papers=papers_to_score,
                        evaluate_inclusion=True,
                        paper_sources=paper_sources,
                    )

                    # Save scored papers to database immediately after each batch
                    logger.info(f"Saving {len(scoring_result.scored_papers)} scored papers to database")
                    for i, sp in enumerate(scoring_result.scored_papers):
                        logger.debug(f"Saving scored paper {i+1}/{len(scoring_result.scored_papers)}: doc_id={sp.paper.document_id}")
                        self._save_scored_paper(sp)
                    logger.info(f"Finished saving {len(scoring_result.scored_papers)} scored papers")

                    timer.set_output(
                        f"Scored {len(scoring_result.scored_papers)} papers, "
                        f"avg score: {scoring_result.average_score:.2f} "
                        f"({cached_count} cached)"
                    )
                    timer.add_metrics({
                        "papers_scored": len(scoring_result.scored_papers),
                        "papers_cached": cached_count,
                        "average_score": round(scoring_result.average_score, 2),
                        "failed_scoring": len(scoring_result.failed_papers),
                    })
                else:
                    timer.set_output(f"All {cached_count} papers already evaluated (cached)")
                    timer.add_metrics({
                        "papers_scored": 0,
                        "papers_cached": cached_count,
                        "average_score": 0.0,
                        "failed_scoring": 0,
                    })

            # Apply relevance threshold using database query
            scored_papers = self.get_scored_papers()
            above_threshold, below_threshold = scorer.apply_relevance_threshold(
                scored_papers,
                threshold=self.config.relevance_threshold,
            )

            passed_relevance = len(above_threshold)

            # Log threshold application
            self.documenter.log_step(
                action="apply_relevance_threshold",
                tool=None,
                input_summary=f"Threshold: {self.config.relevance_threshold}",
                output_summary=f"Above: {len(above_threshold)}, Below: {len(below_threshold)}",
                decision_rationale=f"Filtering by relevance threshold {self.config.relevance_threshold}",
                metrics={
                    "above_threshold": len(above_threshold),
                    "below_threshold": len(below_threshold),
                    "threshold": self.config.relevance_threshold,
                }
            )

            # =================================================================
            # Phase 4b: Query Effectiveness Evaluation (if phased search used)
            # =================================================================
            self._query_feedback: Optional[QueryFeedback] = None

            if self.config.use_phased_search and self.config.enable_query_feedback:
                # Evaluate how effective each query was at finding relevant docs
                query_feedback = scorer.evaluate_query_effectiveness(
                    executed_queries=self._executed_queries,
                    scored_papers=scored_papers,  # Use already-fetched scored_papers
                    semantic_baseline_ids=self._semantic_baseline_ids,
                    threshold=self.config.relevance_threshold,
                )
                self._query_feedback = query_feedback

                # Log query effectiveness
                self.documenter.log_step(
                    action="evaluate_query_effectiveness",
                    tool=None,
                    input_summary=f"Evaluating {len(self._executed_queries)} queries",
                    output_summary=f"{query_feedback.total_effective_queries}/{query_feedback.total_queries_executed} effective",
                    decision_rationale="Tracking query effectiveness for feedback loop",
                    metrics={
                        "total_queries": query_feedback.total_queries_executed,
                        "effective_queries": query_feedback.total_effective_queries,
                        "effective_ratio": round(query_feedback.effective_ratio * 100, 2),
                        "effective_patterns": len(query_feedback.effective_queries),
                        "ineffective_patterns": len(query_feedback.ineffective_queries),
                    }
                )

                # Log warning about ineffective queries
                if query_feedback.ineffective_queries:
                    logger.info(
                        f"Identified {len(query_feedback.ineffective_queries)} ineffective queries "
                        f"that will be used as negative examples for future query generation"
                    )

            # Checkpoint: Review scoring results
            if not self._checkpoint(
                checkpoint_type=CHECKPOINT_SCORING_COMPLETE,
                state={
                    "total_scored": len(scored_papers),
                    "above_threshold": len(above_threshold),
                    "below_threshold": len(below_threshold),
                    "average_score": scoring_result.average_score,
                },
                interactive=interactive,
                checkpoint_callback=checkpoint_callback,
                output_dir=output_dir,
            ):
                logger.info("Review aborted at scoring checkpoint")
                self.documenter.end_review()
                return self._build_empty_result(criteria, weights, "Aborted at scoring")

            # =================================================================
            # Phase 5: Quality Assessment
            # =================================================================
            self.documenter.set_phase("quality_assessment")

            # Check for already-assessed documents to avoid redundant LLM calls
            already_assessed_ids = set(
                self._evaluation_store.get_evaluated_document_ids(
                    run_id=self._evaluation_run.run_id,
                    evaluation_type=EvaluationType.QUALITY_ASSESSMENT,
                )
            )
            papers_to_assess = [sp for sp in above_threshold if sp.paper.document_id not in already_assessed_ids]
            cached_assessment_count = len(above_threshold) - len(papers_to_assess)

            if cached_assessment_count > 0:
                logger.info(
                    f"Found {cached_assessment_count} already-assessed documents, "
                    f"assessing {len(papers_to_assess)} new documents"
                )

            with self.documenter.log_step_with_timer(
                action=ACTION_ASSESS_QUALITY,
                tool="QualityAssessor",
                input_summary=f"Assessing quality of {len(papers_to_assess)} papers ({cached_assessment_count} cached)",
                decision_rationale="Evaluating study quality and methodology",
            ) as timer:
                if papers_to_assess:
                    quality_result = quality_assessor.assess_batch(papers_to_assess)

                    # Save assessed papers to database immediately
                    for ap in quality_result.assessed_papers:
                        self._save_assessed_paper(ap)

                    timer.set_output(
                        f"Assessed {len(quality_result.assessed_papers)} papers, "
                        f"failed: {len(quality_result.failed_papers)} "
                        f"({cached_assessment_count} cached)"
                    )
                    timer.add_metrics({
                        "papers_assessed": len(quality_result.assessed_papers),
                        "papers_cached": cached_assessment_count,
                        "failed_assessment": len(quality_result.failed_papers),
                        **quality_result.assessment_statistics,
                    })
                else:
                    timer.set_output(f"All {cached_assessment_count} papers already assessed (cached)")
                    timer.add_metrics({
                        "papers_assessed": 0,
                        "papers_cached": cached_assessment_count,
                        "failed_assessment": 0,
                    })

            # Checkpoint: Review quality assessment
            assessed_papers = self.get_assessed_papers()
            if not self._checkpoint(
                checkpoint_type=CHECKPOINT_QUALITY_ASSESSMENT,
                state={
                    "papers_assessed": len(assessed_papers),
                    "assessment_stats": quality_result.assessment_statistics,
                },
                interactive=interactive,
                checkpoint_callback=checkpoint_callback,
                output_dir=output_dir,
            ):
                logger.info("Review aborted at quality assessment checkpoint")
                self.documenter.end_review()
                return self._build_empty_result(criteria, weights, "Aborted at quality assessment")

            # =================================================================
            # Phase 6: Composite Scoring and Ranking
            # =================================================================
            self.documenter.set_phase("ranking")

            with self.documenter.log_step_with_timer(
                action=ACTION_CALCULATE_COMPOSITE,
                tool="CompositeScorer",
                input_summary=f"Calculating composite scores for {len(assessed_papers)} papers",
                decision_rationale="Combining scores using user-defined weights",
            ) as timer:
                ranked_papers = composite_scorer.score_and_rank(assessed_papers)

                timer.set_output(f"Ranked {len(ranked_papers)} papers")
                timer.add_metrics({
                    "papers_ranked": len(ranked_papers),
                })

            # Apply quality gate
            included_papers, failed_quality = composite_scorer.apply_quality_gate(
                ranked_papers,
                threshold=self.config.quality_threshold,
            )

            passed_quality_gate = len(included_papers)

            self.documenter.log_step(
                action="apply_quality_gate",
                tool=None,
                input_summary=f"Quality threshold: {self.config.quality_threshold}",
                output_summary=f"Passed: {len(included_papers)}, Failed: {len(failed_quality)}",
                decision_rationale=f"Final quality gate at threshold {self.config.quality_threshold}",
                metrics={
                    "passed": len(included_papers),
                    "failed": len(failed_quality),
                    "threshold": self.config.quality_threshold,
                }
            )

            # =================================================================
            # Phase 7: Separate papers by status
            # =================================================================

            # Collect all excluded papers
            excluded_papers: List[ScoredPaper] = []

            # From initial filter
            for paper, reason in rejected_filter:
                excluded_papers.append(ScoredPaper(
                    paper=paper,
                    relevance_score=0.0,
                    relevance_rationale=reason,
                    inclusion_decision=InclusionDecision.create_excluded(
                        stage=ExclusionStage.INITIAL_FILTER,
                        reasons=[reason],
                        rationale=reason,
                    ),
                ))

            # From below relevance threshold
            excluded_papers.extend(below_threshold)

            # From failed quality gate (convert back to ScoredPaper representation)
            for assessed in failed_quality:
                excluded_papers.append(assessed.scored_paper)

            # Collect uncertain papers
            uncertain_papers = [
                p for p in scored_papers
                if p.inclusion_decision and p.inclusion_decision.status == InclusionStatus.UNCERTAIN
            ]

            # =================================================================
            # Phase 7a: Evidence Synthesis (Optional)
            # =================================================================
            evidence_synthesis = None
            if self.config.enable_evidence_synthesis and included_papers:
                self.documenter.set_phase("evidence_synthesis")

                from .synthesizer import EvidenceSynthesizer

                synthesizer = EvidenceSynthesizer(
                    model=self.config.synthesis_model or self.config.model,
                    citation_model=self.config.model,
                    temperature=self.config.synthesis_temperature,
                    citation_min_relevance=self.config.citation_min_relevance,
                    max_citations_per_paper=self.config.max_citations_per_paper,
                    progress_callback=self.callback,
                )

                with self.documenter.log_step_with_timer(
                    action="synthesize_evidence",
                    tool="EvidenceSynthesizer",
                    input_summary=f"Synthesizing evidence from {len(included_papers)} included papers",
                    decision_rationale="Extract citations and synthesize narrative answer to research question",
                ) as timer:
                    try:
                        evidence_synthesis = synthesizer.synthesize(
                            research_question=criteria.research_question,
                            included_papers=included_papers,
                        )

                        synth_stats = synthesizer.get_statistics()
                        timer.set_output(
                            f"Extracted {synth_stats['citations_extracted']} citations, "
                            f"evidence strength: {evidence_synthesis.evidence_strength}"
                        )
                        timer.add_metrics({
                            "citations_extracted": synth_stats["citations_extracted"],
                            "papers_with_citations": synth_stats["papers_processed"],
                            "extraction_failures": synth_stats["extraction_failures"],
                            "evidence_strength": evidence_synthesis.evidence_strength,
                        })

                        logger.info(
                            f"Evidence synthesis complete: {synth_stats['citations_extracted']} citations, "
                            f"strength={evidence_synthesis.evidence_strength}"
                        )

                    except Exception as e:
                        logger.warning(f"Evidence synthesis failed, continuing without: {e}")
                        timer.set_output(f"Evidence synthesis failed: {e}")

            # =================================================================
            # Phase 8: Generate Report
            # =================================================================
            self.documenter.set_phase("reporting")

            with self.documenter.log_step_with_timer(
                action=ACTION_GENERATE_REPORT,
                tool="Reporter",
                input_summary=f"Generating report: {len(included_papers)} included, {len(excluded_papers)} excluded",
                decision_rationale="Creating comprehensive review report",
            ) as timer:
                # Build statistics (use public accessor for LLM metrics)
                doc_stats = self.documenter.get_statistics()
                statistics = ReviewStatistics(
                    total_considered=total_considered,
                    passed_initial_filter=passed_initial_filter,
                    passed_relevance_threshold=passed_relevance,
                    passed_quality_gate=passed_quality_gate,
                    final_included=len(included_papers),
                    final_excluded=len(excluded_papers),
                    uncertain_for_review=len(uncertain_papers),
                    processing_time_seconds=self.documenter.get_duration(),
                    total_llm_calls=doc_stats.get("total_llm_calls", 0),
                    total_tokens_used=doc_stats.get("total_tokens", 0),
                )

                # Build result
                result = reporter.build_json_result(
                    included_papers=included_papers,
                    excluded_papers=excluded_papers,
                    uncertain_papers=uncertain_papers,
                    search_plan=self._search_plan,
                    executed_queries=self._executed_queries,
                    statistics=statistics,
                    evidence_synthesis=evidence_synthesis,
                )

                timer.set_output(f"Report generated with {statistics.final_included} included papers")
                timer.add_metrics(statistics.to_dict())

            # Save to file if path provided
            if output_path:
                reporter.generate_json_report(result, output_path)
                # Also generate markdown report
                md_path = output_path.replace(".json", ".md") if output_path.endswith(".json") else output_path + ".md"
                reporter.generate_markdown_report(result, md_path)

            # End review
            self.documenter.end_review()

            logger.info(
                f"Systematic review complete: {statistics.final_included} included, "
                f"{statistics.final_excluded} excluded, "
                f"{statistics.uncertain_for_review} uncertain"
            )

            return result

        except SystematicReviewError:
            # Re-raise our custom exceptions as-is
            self.documenter.end_review()
            raise
        except ConnectionError as e:
            # Database or network connectivity issues
            error_msg = f"Connection error during systematic review: {e}"
            logger.error(error_msg, exc_info=True)
            self.documenter.log_step(
                action="review_failed",
                tool=None,
                input_summary="Review encountered connection error",
                output_summary=error_msg,
                decision_rationale="Database or network connectivity failure",
                error=str(e),
            )
            self.documenter.end_review()
            raise DatabaseConnectionError(error_msg) from e
        except TimeoutError as e:
            # Timeout during LLM or database operations
            error_msg = f"Timeout during systematic review: {e}"
            logger.error(error_msg, exc_info=True)
            self.documenter.log_step(
                action="review_failed",
                tool=None,
                input_summary="Review timed out",
                output_summary=error_msg,
                decision_rationale="Operation timeout - consider increasing timeout settings",
                error=str(e),
            )
            self.documenter.end_review()
            raise LLMConnectionError(error_msg) from e
        except ValueError as e:
            # Data validation or configuration errors
            error_msg = f"Validation error during systematic review: {e}"
            logger.error(error_msg, exc_info=True)
            self.documenter.log_step(
                action="review_failed",
                tool=None,
                input_summary="Review encountered validation error",
                output_summary=error_msg,
                decision_rationale="Data validation or configuration error",
                error=str(e),
            )
            self.documenter.end_review()
            raise SystematicReviewError(error_msg) from e
        except KeyboardInterrupt:
            # User interrupted the review
            logger.info("Systematic review interrupted by user")
            self.documenter.log_step(
                action="review_interrupted",
                tool=None,
                input_summary="Review interrupted by user",
                output_summary="Review was cancelled by user",
                decision_rationale="User requested cancellation",
            )
            self.documenter.end_review()
            raise
        except Exception as e:
            # Catch-all for unexpected errors with detailed context
            error_type = type(e).__name__
            error_msg = f"Unexpected error ({error_type}) during systematic review: {e}"
            logger.error(error_msg, exc_info=True)
            self.documenter.log_step(
                action="review_failed",
                tool=None,
                input_summary=f"Review encountered unexpected {error_type}",
                output_summary=error_msg,
                decision_rationale="Unexpected error - please report this issue",
                error=str(e),
                metrics={
                    "error_type": error_type,
                    "phase": self.documenter._current_phase,
                }
            )
            self.documenter.end_review()
            raise SystematicReviewError(error_msg) from e

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
    # Workflow Phase Methods (Stubs for Phase 1)
    # =========================================================================

    def _generate_search_plan(
        self,
        criteria: SearchCriteria,
    ) -> SearchPlan:
        """
        Generate search strategy (Phase 2).

        Uses LLM to analyze the research question and generate
        diverse search queries for comprehensive coverage.

        Args:
            criteria: Search criteria to base plan on

        Returns:
            SearchPlan with queries to execute

        Note:
            Implementation in Phase 2
        """
        raise NotImplementedError("Implemented in Phase 2")

    def _execute_search_plan(
        self,
        plan: SearchPlan,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> tuple[List[ExecutedQuery], List[PaperData]]:
        """
        Execute all queries in the search plan (Phase 2).

        Runs each query and collects papers, deduplicating results.

        Args:
            plan: SearchPlan to execute
            progress_callback: Optional callback(current, total) for progress

        Returns:
            Tuple of (executed_queries, unique_papers)

        Note:
            Implementation in Phase 2
        """
        raise NotImplementedError("Implemented in Phase 2")

    def _apply_initial_filter(
        self,
        papers: List[PaperData],
        criteria: SearchCriteria,
    ) -> tuple[List[PaperData], List[tuple[PaperData, str]]]:
        """
        Apply fast heuristic filtering (Phase 3).

        Quickly filters papers based on date range, keywords,
        and other fast checks before expensive LLM scoring.

        Args:
            papers: Papers to filter
            criteria: Criteria to apply

        Returns:
            Tuple of (passed_papers, rejected_with_reasons)

        Note:
            Implementation in Phase 3
        """
        raise NotImplementedError("Implemented in Phase 3")

    def _score_papers(
        self,
        papers: List[PaperData],
        criteria: SearchCriteria,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> List[ScoredPaper]:
        """
        Score papers for relevance (Phase 3).

        Uses DocumentScoringAgent to evaluate relevance and
        applies inclusion/exclusion criteria.

        Args:
            papers: Papers to score
            criteria: Criteria for evaluation
            progress_callback: Optional callback for progress

        Returns:
            List of ScoredPaper with relevance scores

        Note:
            Implementation in Phase 3
        """
        raise NotImplementedError("Implemented in Phase 3")

    def _assess_quality(
        self,
        papers: List[ScoredPaper],
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> List[AssessedPaper]:
        """
        Perform quality assessment (Phase 4).

        Runs study assessment, paper weight evaluation, and
        optionally PICO/PRISMA assessment based on study type.

        Args:
            papers: Scored papers to assess
            progress_callback: Optional callback for progress

        Returns:
            List of AssessedPaper with quality scores

        Note:
            Implementation in Phase 4
        """
        raise NotImplementedError("Implemented in Phase 4")

    def _calculate_composite_scores(
        self,
        papers: List[AssessedPaper],
        weights: ScoringWeights,
    ) -> List[AssessedPaper]:
        """
        Calculate weighted composite scores (Phase 4).

        Combines relevance, quality, and other scores using
        user-defined weights.

        Args:
            papers: Assessed papers
            weights: Weights for score combination

        Returns:
            Papers with composite_score set

        Note:
            Implementation in Phase 4
        """
        raise NotImplementedError("Implemented in Phase 4")

    def _generate_report(
        self,
        included: List[AssessedPaper],
        excluded: List[ScoredPaper],
        uncertain: List[ScoredPaper],
    ) -> SystematicReviewResult:
        """
        Generate final report (Phase 5).

        Creates comprehensive output with all papers,
        rationales, and audit trail.

        Args:
            included: Papers that passed all criteria
            excluded: Papers that were rejected
            uncertain: Papers needing human review

        Returns:
            Complete SystematicReviewResult

        Note:
            Implementation in Phase 5
        """
        raise NotImplementedError("Implemented in Phase 5")

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
        self.documenter = Documenter()
        self.reset_metrics()
        logger.info("SystematicReviewAgent state reset")
