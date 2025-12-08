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
# Exceptions
# =============================================================================

class SystematicReviewError(Exception):
    """Base exception for systematic review errors."""

    pass


class SearchPlanningError(SystematicReviewError):
    """Exception raised when search plan generation fails."""

    pass


class SearchExecutionError(SystematicReviewError):
    """Exception raised when search execution fails."""

    pass


class ScoringError(SystematicReviewError):
    """Exception raised when document scoring fails."""

    pass


class QualityAssessmentError(SystematicReviewError):
    """Exception raised when quality assessment fails."""

    pass


class ReportGenerationError(SystematicReviewError):
    """Exception raised when report generation fails."""

    pass


class LLMConnectionError(SystematicReviewError):
    """Exception raised when LLM connection fails."""

    pass


class DatabaseConnectionError(SystematicReviewError):
    """Exception raised when database connection fails."""

    pass


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

# Checkpoint display constants
CHECKPOINT_TITLE_TRUNCATE_LENGTH = 80
CHECKPOINT_SAMPLE_TITLES_COUNT = 10


# =============================================================================
# SystematicReviewAgent
# =============================================================================

class SystematicReviewAgent(BaseAgent):
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
            return self._evaluation_store.save_evaluation(
                run_id=self._evaluation_run.run_id,
                document_id=scored_paper.paper.document_id,
                evaluation_type=EvaluationType.RELEVANCE_SCORE,
                evaluation_data=evaluation_data,
                primary_score=float(scored_paper.relevance_score),
                evaluator_id=self._evaluator_id,
                reasoning=scored_paper.relevance_rationale,
                processing_time_ms=processing_time_ms,
            )
        except Exception as e:
            logger.error(
                f"Failed to save scored paper document_id={scored_paper.paper.document_id}: {e}"
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
    ) -> List[AssessedPaper]:
        """
        Get assessed papers from the evaluation store.

        Args:
            min_score: Optional minimum composite score filter.
            limit: Optional maximum number of results.

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

        # Get scored papers to build AssessedPaper objects
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
                    "total_before_dedup": search_results.total_before_dedup,
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

            with self.documenter.log_step_with_timer(
                action=ACTION_SCORE_RELEVANCE,
                tool="RelevanceScorer",
                input_summary=f"Scoring {len(passed_filter)} papers for relevance",
                decision_rationale="Assessing relevance to research question using LLM",
            ) as timer:
                scoring_result = scorer.score_batch(
                    papers=passed_filter,
                    evaluate_inclusion=True,
                    paper_sources=search_results.paper_sources,
                )

                # Save scored papers to database
                for sp in scoring_result.scored_papers:
                    self._save_scored_paper(sp)

                timer.set_output(
                    f"Scored {len(scoring_result.scored_papers)} papers, "
                    f"avg score: {scoring_result.average_score:.2f}"
                )
                timer.add_metrics({
                    "papers_scored": len(scoring_result.scored_papers),
                    "average_score": round(scoring_result.average_score, 2),
                    "failed_scoring": len(scoring_result.failed_papers),
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

            with self.documenter.log_step_with_timer(
                action=ACTION_ASSESS_QUALITY,
                tool="QualityAssessor",
                input_summary=f"Assessing quality of {len(above_threshold)} papers",
                decision_rationale="Evaluating study quality and methodology",
            ) as timer:
                quality_result = quality_assessor.assess_batch(above_threshold)

                # Save assessed papers to database
                for ap in quality_result.assessed_papers:
                    self._save_assessed_paper(ap)

                timer.set_output(
                    f"Assessed {len(quality_result.assessed_papers)} papers, "
                    f"failed: {len(quality_result.failed_papers)}"
                )
                timer.add_metrics({
                    "papers_assessed": len(quality_result.assessed_papers),
                    "failed_assessment": len(quality_result.failed_papers),
                    **quality_result.assessment_statistics,
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

    def run_review_from_checkpoint(
        self,
        checkpoint_path: str,
        interactive: bool = True,
        output_path: Optional[str] = None,
        checkpoint_callback: Optional[Callable[[str, Dict], bool]] = None,
    ) -> SystematicReviewResult:
        """
        Resume a systematic review from a saved checkpoint.

        Loads state from a checkpoint file and continues the review
        from the phase following the checkpoint.

        Args:
            checkpoint_path: Path to the checkpoint JSON file
            interactive: If True, pause at subsequent checkpoints for approval
            output_path: Optional path to save results JSON
            checkpoint_callback: Optional callback for checkpoint decisions

        Returns:
            SystematicReviewResult with all papers and audit trail

        Raises:
            FileNotFoundError: If checkpoint file doesn't exist
            ValueError: If checkpoint file is invalid or incompatible
            SystematicReviewError: If resume fails

        Example:
            >>> result = agent.run_review_from_checkpoint(
            ...     checkpoint_path="reviews/review_abc123_initial_results.json",
            ...     interactive=True
            ... )
        """
        from pathlib import Path
        import json

        checkpoint_file = Path(checkpoint_path).expanduser()

        if not checkpoint_file.exists():
            raise FileNotFoundError(f"Checkpoint file not found: {checkpoint_path}")

        # Load checkpoint data
        try:
            with open(checkpoint_file, "r", encoding="utf-8") as f:
                checkpoint_data = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid checkpoint file format: {e}")

        # Validate checkpoint version
        checkpoint_version = checkpoint_data.get("version", "unknown")
        if checkpoint_version != AGENT_VERSION:
            logger.warning(
                f"Checkpoint version mismatch: {checkpoint_version} vs {AGENT_VERSION}. "
                "Attempting resume anyway."
            )

        checkpoint_type = checkpoint_data.get("checkpoint_type")
        review_id = checkpoint_data.get("review_id")

        logger.info(f"Resuming review {review_id} from checkpoint: {checkpoint_type}")

        # Restore state
        self._restore_state_from_checkpoint(checkpoint_data)

        # Initialize documenter with the same review ID
        self.documenter = Documenter(review_id=review_id)
        self.documenter.start_review()
        self.documenter._current_phase = checkpoint_data.get("documenter_phase", "initial_filtering")

        # Log the resume event
        self.documenter.log_step(
            action="resume_from_checkpoint",
            tool=None,
            input_summary=f"Resuming from {checkpoint_type} checkpoint",
            output_summary=f"Restored {len(self._all_papers)} papers, continuing review",
            decision_rationale="User requested resume from saved checkpoint",
            metrics={
                "checkpoint_type": checkpoint_type,
                "papers_restored": len(self._all_papers),
                "original_review_id": review_id,
            }
        )

        # Extract output directory for checkpoint saving during resume
        output_dir: Optional[str] = None
        if output_path:
            output_dir = str(Path(output_path).expanduser().parent)

        # Continue from the appropriate phase based on checkpoint type
        try:
            if checkpoint_type == CHECKPOINT_SEARCH_STRATEGY:
                # Resume from search execution (Phase 2)
                return self._continue_from_search_execution(
                    interactive=interactive,
                    output_path=output_path,
                    checkpoint_callback=checkpoint_callback,
                )
            elif checkpoint_type == CHECKPOINT_INITIAL_RESULTS:
                # Resume from initial filtering (Phase 3)
                return self._continue_from_initial_filtering(
                    interactive=interactive,
                    output_path=output_path,
                    checkpoint_callback=checkpoint_callback,
                    output_dir=output_dir,
                )
            elif checkpoint_type == CHECKPOINT_SCORING_COMPLETE:
                # Resume from quality assessment (Phase 5)
                return self._continue_from_quality_assessment(
                    interactive=interactive,
                    output_path=output_path,
                    checkpoint_callback=checkpoint_callback,
                )
            elif checkpoint_type == CHECKPOINT_QUALITY_ASSESSMENT:
                # Resume from composite scoring (Phase 6)
                return self._continue_from_composite_scoring(
                    interactive=interactive,
                    output_path=output_path,
                    checkpoint_callback=checkpoint_callback,
                )
            else:
                raise ValueError(f"Unknown checkpoint type: {checkpoint_type}")

        except KeyboardInterrupt:
            logger.info("Review cancelled by user during resume")
            self.documenter.end_review()
            raise
        except Exception as e:
            error_type = type(e).__name__
            error_msg = f"Error resuming review: {e}"
            logger.error(error_msg, exc_info=True)
            self.documenter.end_review()
            raise SystematicReviewError(error_msg) from e

    def _restore_state_from_checkpoint(
        self,
        checkpoint_data: Dict[str, Any],
    ) -> None:
        """
        Restore agent state from checkpoint data.

        Args:
            checkpoint_data: Dictionary with checkpoint state
        """
        from bmlibrarian.database import fetch_documents_by_ids

        # Validate this is a proper checkpoint file (not a final report)
        checkpoint_type = checkpoint_data.get("checkpoint_type")
        if not checkpoint_type:
            # This might be a final report JSON, not a checkpoint file
            if "metadata" in checkpoint_data and "search_strategy" in checkpoint_data:
                raise ValueError(
                    "This appears to be a final report file, not a checkpoint file. "
                    "Please select a checkpoint file (e.g., *_search_strategy.json "
                    "or *_initial_results.json) to resume from."
                )
            raise ValueError(
                "Invalid checkpoint file: missing 'checkpoint_type' field. "
                "Please select a valid checkpoint file."
            )

        # Restore criteria
        criteria_data = checkpoint_data.get("criteria")
        if criteria_data:
            self._criteria = SearchCriteria.from_dict(criteria_data)
        else:
            raise ValueError(
                f"Checkpoint missing required 'criteria' data. "
                f"Checkpoint type: {checkpoint_type}"
            )

        # Restore weights
        weights_data = checkpoint_data.get("weights")
        if weights_data:
            self._weights = ScoringWeights.from_dict(weights_data)
        else:
            self._weights = self.config.scoring_weights

        # Restore search plan
        search_plan_data = checkpoint_data.get("search_plan")
        if search_plan_data:
            self._search_plan = SearchPlan.from_dict(search_plan_data)

        # Restore executed queries
        executed_queries_data = checkpoint_data.get("executed_queries", [])
        self._executed_queries = [
            ExecutedQuery.from_dict(q) for q in executed_queries_data
        ]

        # Re-fetch papers from database using saved document IDs
        paper_ids = checkpoint_data.get("paper_document_ids", [])
        if paper_ids:
            logger.info(f"Re-fetching {len(paper_ids)} papers from database...")
            documents = fetch_documents_by_ids(set(paper_ids))

            self._all_papers = []
            for doc in documents:
                try:
                    paper = PaperData.from_database_row(doc)
                    self._all_papers.append(paper)
                except Exception as e:
                    logger.warning(f"Failed to restore paper {doc.get('id')}: {e}")

            logger.info(f"Restored {len(self._all_papers)} papers")

            # Check for missing papers
            if len(self._all_papers) < len(paper_ids):
                missing = len(paper_ids) - len(self._all_papers)
                logger.warning(f"{missing} papers could not be restored from database")

        # Restore rejected initial filter papers
        rejected_initial_data = checkpoint_data.get("rejected_initial_filter", [])
        if rejected_initial_data:
            # Create a lookup for papers by document_id
            paper_lookup = {p.document_id: p for p in self._all_papers}
            self._rejected_initial_filter = []

            for item in rejected_initial_data:
                doc_id = item.get("document_id")
                reason = item.get("reason", "Unknown reason")

                if doc_id in paper_lookup:
                    self._rejected_initial_filter.append((paper_lookup[doc_id], reason))
                else:
                    # Need to re-fetch this paper from database
                    try:
                        from bmlibrarian.database import fetch_documents_by_ids
                        docs = fetch_documents_by_ids({doc_id})
                        if docs:
                            paper = PaperData.from_database_row(docs[0])
                            self._rejected_initial_filter.append((paper, reason))
                    except Exception as e:
                        logger.warning(f"Failed to restore rejected paper {doc_id}: {e}")

            logger.info(f"Restored {len(self._rejected_initial_filter)} papers rejected in initial filter")

        # Restore scored papers if available (for scoring_complete checkpoint)
        scored_papers_data = checkpoint_data.get("scored_papers", [])
        if scored_papers_data:
            # First, ensure we have paper_lookup from all_papers
            if not hasattr(self, '_all_papers') or not self._all_papers:
                # Re-fetch papers if needed
                paper_ids = checkpoint_data.get("paper_document_ids", [])
                if paper_ids:
                    from bmlibrarian.database import fetch_documents_by_ids
                    documents = fetch_documents_by_ids(set(paper_ids))
                    self._all_papers = []
                    for doc in documents:
                        try:
                            paper = PaperData.from_database_row(doc)
                            self._all_papers.append(paper)
                        except Exception as e:
                            logger.warning(f"Failed to restore paper {doc.get('id')}: {e}")

            # Build paper lookup for later use
            self._paper_lookup = {p.document_id: p for p in self._all_papers}

        # Restore evaluation run from database
        evaluation_run_id = checkpoint_data.get("evaluation_run_id")
        if evaluation_run_id:
            self._evaluation_run = self._evaluation_store.get_run(evaluation_run_id)
            if self._evaluation_run:
                # Resume the run
                self._evaluation_store.resume_run(evaluation_run_id)
                scored_papers = self.get_scored_papers()
                assessed_papers = self.get_assessed_papers()
                logger.info(
                    f"Restored evaluation run {evaluation_run_id}: "
                    f"{len(scored_papers)} scored, {len(assessed_papers)} assessed"
                )
            else:
                logger.warning(f"Evaluation run {evaluation_run_id} not found in database")

    def _continue_from_search_execution(
        self,
        interactive: bool,
        output_path: Optional[str],
        checkpoint_callback: Optional[Callable[[str, Dict], bool]],
    ) -> SystematicReviewResult:
        """
        Continue review from after search strategy checkpoint.

        Executes: Search Execution → Initial Filtering → Scoring → Quality → Report

        Args:
            interactive: Whether to run in interactive mode
            output_path: Optional path for saving results
            checkpoint_callback: Optional callback for checkpoint decisions

        Returns:
            SystematicReviewResult with all papers and audit trail
        """
        from pathlib import Path
        from .executor import SearchExecutor

        # Extract output directory for checkpoint saving
        output_dir: Optional[str] = None
        if output_path:
            output_dir = str(Path(output_path).expanduser().parent)

        # Initialize components
        executor = SearchExecutor(
            config=self.config,
            results_per_query=self.config.max_results_per_query,
            callback=self.callback,
        )

        # Phase 2: Execute Search Plan
        self.documenter.set_phase("search_execution")

        with self.documenter.log_step_with_timer(
            action=ACTION_EXECUTE_SEARCH,
            tool="SearchExecutor",
            input_summary=f"Executing {len(self._search_plan.queries)} queries (resumed)",
            decision_rationale="Continuing from search strategy checkpoint",
        ) as timer:
            search_results = executor.execute_plan(self._search_plan)
            self._executed_queries = search_results.executed_queries
            self._all_papers = search_results.papers

            timer.set_output(
                f"Found {search_results.count} unique papers "
                f"from {search_results.total_before_dedup} total"
            )

        # Continue with remaining phases via the common continuation path
        return self._continue_from_initial_results_checkpoint(
            search_results=search_results,
            interactive=interactive,
            output_path=output_path,
            checkpoint_callback=checkpoint_callback,
            output_dir=output_dir,
        )

    def _continue_from_initial_filtering(
        self,
        interactive: bool,
        output_path: Optional[str],
        checkpoint_callback: Optional[Callable[[str, Dict], bool]],
        output_dir: Optional[str] = None,
    ) -> SystematicReviewResult:
        """
        Continue review from after initial results checkpoint.

        Executes: Initial Filtering → Scoring → Quality → Report

        Args:
            interactive: Whether to run in interactive mode
            output_path: Optional path for saving results
            checkpoint_callback: Optional callback for checkpoint decisions
            output_dir: Optional directory for checkpoint file saving
        """
        from .filters import InitialFilter, InclusionEvaluator
        from .scorer import RelevanceScorer, CompositeScorer
        from .quality import QualityAssessor
        from .reporter import Reporter

        criteria = self._criteria
        weights = self._weights

        # Initialize remaining components
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

        total_considered = len(self._all_papers)

        # Phase 3: Initial Filtering
        self.documenter.set_phase("initial_filtering")

        with self.documenter.log_step_with_timer(
            action=ACTION_INITIAL_FILTER,
            tool="InitialFilter",
            input_summary=f"Filtering {len(self._all_papers)} papers with heuristics (resumed)",
            decision_rationale="Continuing from initial results checkpoint",
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

        # Continue with scoring, quality assessment, and report generation
        return self._continue_from_scoring_phase(
            passed_filter=passed_filter,
            scorer=scorer,
            quality_assessor=quality_assessor,
            composite_scorer=composite_scorer,
            reporter=reporter,
            total_considered=total_considered,
            passed_initial_filter=passed_initial_filter,
            interactive=interactive,
            output_path=output_path,
            checkpoint_callback=checkpoint_callback,
            output_dir=output_dir,
        )

    def _continue_from_quality_assessment(
        self,
        interactive: bool,
        output_path: Optional[str],
        checkpoint_callback: Optional[Callable[[str, Dict], bool]],
    ) -> SystematicReviewResult:
        """
        Continue review from after scoring checkpoint.

        Executes: Quality Assessment → Composite Scoring → Report

        This resumes from the scoring_complete checkpoint where we have
        scored papers already restored from the checkpoint file.
        """
        from pathlib import Path
        from .scorer import CompositeScorer
        from .quality import QualityAssessor
        from .reporter import Reporter

        criteria = self._criteria
        weights = self._weights

        # Extract output directory for checkpoint saving
        output_dir: Optional[str] = None
        if output_path:
            output_dir = str(Path(output_path).expanduser().parent)

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

        # Calculate statistics from restored state
        total_considered = len(self._all_papers)
        passed_initial_filter = total_considered - len(self._rejected_initial_filter)

        # Get papers above relevance threshold from database
        relevance_threshold = self.config.relevance_threshold
        scored_papers = self.get_scored_papers()
        relevant_papers = [
            sp for sp in scored_papers
            if sp.relevance_score >= relevance_threshold
        ]
        passed_relevance = len(relevant_papers)

        logger.info(
            f"Resuming from scoring_complete: {len(scored_papers)} scored papers, "
            f"{passed_relevance} above threshold"
        )

        # Phase 5: Quality Assessment
        self.documenter.set_phase("quality_assessment")

        with self.documenter.log_step_with_timer(
            action=ACTION_ASSESS_QUALITY,
            tool="QualityAssessor",
            input_summary=f"Assessing quality of {len(relevant_papers)} papers (resumed from checkpoint)",
            decision_rationale="Continuing from scoring_complete checkpoint",
        ) as timer:
            quality_result = quality_assessor.assess_batch(relevant_papers)

            # Save assessed papers to database
            for ap in quality_result.assessed_papers:
                self._save_assessed_paper(ap)

            timer.set_output(
                f"Assessed {len(quality_result.assessed_papers)} papers, "
                f"failed: {len(quality_result.failed_papers)}"
            )
            timer.add_metrics({
                "papers_assessed": len(quality_result.assessed_papers),
                "failed_assessment": len(quality_result.failed_papers),
                **quality_result.assessment_statistics,
            })

        # Checkpoint: Review quality assessment results
        if not self._checkpoint(
            checkpoint_type=CHECKPOINT_QUALITY_ASSESSMENT,
            state={
                "papers_assessed": len(quality_result.assessed_papers),
                "failed_assessment": len(quality_result.failed_papers),
                "study_assessments": quality_result.assessment_statistics.get("study_assessments", 0),
                "weight_assessments": quality_result.assessment_statistics.get("weight_assessments", 0),
            },
            interactive=interactive,
            checkpoint_callback=checkpoint_callback,
            output_dir=output_dir,
        ):
            logger.info("Review aborted at quality assessment checkpoint")
            self.documenter.end_review()
            return self._build_empty_result(criteria, weights, "Aborted at quality assessment")

        # Phase 6: Composite Scoring
        # Get assessed papers from database
        assessed_papers = self.get_assessed_papers()

        with self.documenter.log_step_with_timer(
            action=ACTION_CALCULATE_COMPOSITE,
            tool="CompositeScorer",
            input_summary=f"Calculating composite scores for {len(assessed_papers)} papers",
            decision_rationale="Combining all scores for final ranking",
        ) as timer:
            for assessed in assessed_papers:
                assessed.composite_score = composite_scorer.score(assessed)

            # Sort by composite score and assign ranks
            assessed_papers.sort(key=lambda x: x.composite_score, reverse=True)
            for i, paper in enumerate(assessed_papers):
                paper.final_rank = i + 1

            timer.set_output(
                f"Ranked {len(assessed_papers)} papers by composite score"
            )

        # Determine final inclusion
        final_included = [ap for ap in assessed_papers if ap.is_included]
        final_excluded_assessed = [ap for ap in assessed_papers if not ap.is_included]

        # =================================================================
        # Collect ALL excluded papers for comprehensive reporting
        # =================================================================
        all_excluded_papers: List[ScoredPaper] = []

        # 1. Papers rejected in initial filter
        for paper, reason in self._rejected_initial_filter:
            all_excluded_papers.append(ScoredPaper(
                paper=paper,
                relevance_score=0.0,
                relevance_rationale=reason,
                inclusion_decision=InclusionDecision.create_excluded(
                    stage=ExclusionStage.INITIAL_FILTER,
                    reasons=[reason],
                    rationale=reason,
                ),
            ))

        # 2. Papers below relevance threshold from database
        all_excluded_papers.extend(self.get_below_threshold_papers())

        # 3. Papers that failed quality gate
        for ap in final_excluded_assessed:
            all_excluded_papers.append(ap.scored_paper)

        # Build statistics with accurate counts
        # NOTE: passed_quality_gate should be final_included, not len(_assessed_papers)
        # _assessed_papers = all papers that were quality assessed
        # final_included = papers that actually passed the quality threshold
        stats = ReviewStatistics(
            total_considered=total_considered,
            passed_initial_filter=passed_initial_filter,
            passed_relevance_threshold=passed_relevance,
            passed_quality_gate=len(final_included),
            final_included=len(final_included),
            final_excluded=len(all_excluded_papers),
            uncertain_for_review=0,
            processing_time_seconds=self.documenter.get_duration(),
            total_llm_calls=self.documenter._total_llm_calls,
            total_tokens_used=self.documenter._total_tokens,
        )

        # =================================================================
        # Phase 6a: Evidence Synthesis (Optional)
        # =================================================================
        evidence_synthesis = None
        if self.config.enable_evidence_synthesis and final_included:
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
                input_summary=f"Synthesizing evidence from {len(final_included)} included papers",
                decision_rationale="Extract citations and synthesize narrative answer to research question",
            ) as timer:
                try:
                    evidence_synthesis = synthesizer.synthesize(
                        research_question=criteria.research_question,
                        included_papers=final_included,
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

        # Phase 7: Report Generation
        self.documenter.set_phase("reporting")

        with self.documenter.log_step_with_timer(
            action=ACTION_GENERATE_REPORT,
            tool="Reporter",
            input_summary=f"Generating report for {len(final_included)} included, {len(all_excluded_papers)} excluded papers",
            decision_rationale="Creating final systematic review output",
        ) as timer:
            result = reporter.build_json_result(
                included_papers=final_included,
                excluded_papers=all_excluded_papers,
                uncertain_papers=[],
                search_plan=self._search_plan,
                executed_queries=self._executed_queries,
                statistics=stats,
                evidence_synthesis=evidence_synthesis,
            )

            if output_path:
                reporter.generate_json_report(result, output_path)
                # Also generate markdown report
                md_path = output_path.replace(".json", ".md") if output_path.endswith(".json") else output_path + ".md"
                reporter.generate_markdown_report(result, md_path)

            timer.set_output(f"Report generated with {len(final_included)} included papers")

        self.documenter.end_review()
        return result

    def _continue_from_composite_scoring(
        self,
        interactive: bool,
        output_path: Optional[str],
        checkpoint_callback: Optional[Callable[[str, Dict], bool]],
    ) -> SystematicReviewResult:
        """
        Continue review from after quality assessment checkpoint.

        Executes: Composite Scoring → Evidence Synthesis → Report

        This resumes from the quality_assessment checkpoint where we have
        assessed papers already restored from the checkpoint file.
        """
        from pathlib import Path
        from .scorer import CompositeScorer
        from .reporter import Reporter

        criteria = self._criteria
        weights = self._weights

        # Extract output directory for checkpoint saving
        output_dir: Optional[str] = None
        if output_path:
            output_dir = str(Path(output_path).expanduser().parent)

        composite_scorer = CompositeScorer(weights=weights)

        reporter = Reporter(
            documenter=self.documenter,
            criteria=criteria,
            weights=weights,
        )

        # Get counts from restored state - use database queries
        scored_papers = self.get_scored_papers()
        assessed_papers = self.get_assessed_papers()
        total_considered = len(self._all_papers) + len(self._rejected_initial_filter)
        passed_initial_filter = len(self._all_papers)
        passed_relevance = len(scored_papers) if scored_papers else len(assessed_papers)

        # =================================================================
        # Phase 6: Composite Scoring
        # =================================================================
        self.documenter.set_phase("ranking")

        with self.documenter.log_step_with_timer(
            action=ACTION_CALCULATE_COMPOSITE,
            tool="CompositeScorer",
            input_summary=f"Calculating composite scores for {len(assessed_papers)} papers",
            decision_rationale="Combining all scores for final ranking",
        ) as timer:
            for assessed in assessed_papers:
                assessed.composite_score = composite_scorer.score(assessed)

            # Sort by composite score and assign ranks
            assessed_papers.sort(key=lambda x: x.composite_score, reverse=True)
            for i, paper in enumerate(assessed_papers):
                paper.final_rank = i + 1

            timer.set_output(
                f"Ranked {len(assessed_papers)} papers by composite score"
            )

        # Determine final inclusion
        final_included = [ap for ap in assessed_papers if ap.is_included]
        final_excluded_assessed = [ap for ap in assessed_papers if not ap.is_included]

        # =================================================================
        # Collect ALL excluded papers for comprehensive reporting
        # =================================================================
        all_excluded_papers: List[ScoredPaper] = []

        # 1. Papers rejected in initial filter
        for paper, reason in self._rejected_initial_filter:
            all_excluded_papers.append(ScoredPaper(
                paper=paper,
                relevance_score=0.0,
                relevance_rationale=reason,
                inclusion_decision=InclusionDecision.create_excluded(
                    stage=ExclusionStage.INITIAL_FILTER,
                    reasons=[reason],
                    rationale=reason,
                ),
            ))

        # 2. Papers below relevance threshold from database
        all_excluded_papers.extend(self.get_below_threshold_papers())

        # 3. Papers that failed quality gate
        for ap in final_excluded_assessed:
            all_excluded_papers.append(ap.scored_paper)

        # Build statistics with accurate counts
        stats = ReviewStatistics(
            total_considered=total_considered,
            passed_initial_filter=passed_initial_filter,
            passed_relevance_threshold=passed_relevance,
            passed_quality_gate=len(final_included),
            final_included=len(final_included),
            final_excluded=len(all_excluded_papers),
            uncertain_for_review=0,
            processing_time_seconds=self.documenter.get_duration(),
            total_llm_calls=self.documenter._total_llm_calls,
            total_tokens_used=self.documenter._total_tokens,
        )

        # =================================================================
        # Phase 6a: Evidence Synthesis (Optional)
        # =================================================================
        evidence_synthesis = None
        if self.config.enable_evidence_synthesis and final_included:
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
                input_summary=f"Synthesizing evidence from {len(final_included)} included papers",
                decision_rationale="Extract citations and synthesize narrative answer to research question",
            ) as timer:
                try:
                    evidence_synthesis = synthesizer.synthesize(
                        research_question=criteria.research_question,
                        included_papers=final_included,
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

        # Phase 7: Report Generation
        self.documenter.set_phase("reporting")

        with self.documenter.log_step_with_timer(
            action=ACTION_GENERATE_REPORT,
            tool="Reporter",
            input_summary=f"Generating report for {len(final_included)} included, {len(all_excluded_papers)} excluded papers",
            decision_rationale="Creating final systematic review output",
        ) as timer:
            result = reporter.build_json_result(
                included_papers=final_included,
                excluded_papers=all_excluded_papers,
                uncertain_papers=[],
                search_plan=self._search_plan,
                executed_queries=self._executed_queries,
                statistics=stats,
                evidence_synthesis=evidence_synthesis,
            )

            if output_path:
                reporter.generate_json_report(result, output_path)
                # Also generate markdown report
                md_path = output_path.replace(".json", ".md") if output_path.endswith(".json") else output_path + ".md"
                reporter.generate_markdown_report(result, md_path)

            timer.set_output(f"Report generated with {len(final_included)} included papers")

        self.documenter.end_review()
        return result

    def _continue_from_initial_results_checkpoint(
        self,
        search_results: "AggregatedResults",
        interactive: bool,
        output_path: Optional[str],
        checkpoint_callback: Optional[Callable[[str, Dict], bool]],
        output_dir: Optional[str] = None,
    ) -> SystematicReviewResult:
        """
        Common continuation path after search results are available.

        This is called when resuming from search_strategy checkpoint
        after search execution is complete.

        Args:
            search_results: Aggregated search results from executor
            interactive: Whether to run in interactive mode
            output_path: Optional path for saving results
            checkpoint_callback: Optional callback for checkpoint decisions
            output_dir: Optional directory for checkpoint file saving

        Returns:
            SystematicReviewResult with all papers and audit trail
        """
        # Checkpoint: Review initial results
        if not self._checkpoint(
            checkpoint_type=CHECKPOINT_INITIAL_RESULTS,
            state={
                "unique_papers": len(self._all_papers),
                "total_before_dedup": search_results.total_before_dedup,
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
            return self._build_empty_result(
                self._criteria, self._weights, "Aborted at initial results"
            )

        # Continue with initial filtering
        return self._continue_from_initial_filtering(
            interactive=interactive,
            output_path=output_path,
            checkpoint_callback=checkpoint_callback,
            output_dir=output_dir,
        )

    def _continue_from_scoring_phase(
        self,
        passed_filter: List[PaperData],
        scorer: "RelevanceScorer",
        quality_assessor: "QualityAssessor",
        composite_scorer: "CompositeScorer",
        reporter: "Reporter",
        total_considered: int,
        passed_initial_filter: int,
        interactive: bool,
        output_path: Optional[str],
        checkpoint_callback: Optional[Callable[[str, Dict], bool]],
        output_dir: Optional[str] = None,
    ) -> SystematicReviewResult:
        """
        Continue from the scoring phase onwards.

        Executes: Relevance Scoring → Inclusion Evaluation → Quality Assessment → Report

        Args:
            passed_filter: Papers that passed initial filtering
            scorer: RelevanceScorer instance for relevance assessment
            quality_assessor: QualityAssessor instance for quality assessment
            composite_scorer: CompositeScorer instance for final scoring
            reporter: Reporter instance for output generation
            total_considered: Total number of papers considered
            passed_initial_filter: Number of papers that passed initial filter
            interactive: Whether to run in interactive mode
            output_path: Optional path for saving results
            checkpoint_callback: Optional callback for checkpoint decisions
            output_dir: Optional directory for checkpoint file saving

        Returns:
            SystematicReviewResult with all papers and audit trail
        """
        from .filters import InclusionEvaluator

        criteria = self._criteria
        weights = self._weights

        # Phase 4: Relevance Scoring
        self.documenter.set_phase("relevance_scoring")

        with self.documenter.log_step_with_timer(
            action=ACTION_SCORE_RELEVANCE,
            tool="RelevanceScorer",
            input_summary=f"Scoring {len(passed_filter)} papers for relevance",
            decision_rationale="Assessing relevance to research question using LLM",
        ) as timer:
            # Get paper sources for scoring
            paper_sources = {p.document_id: ["resumed"] for p in passed_filter}

            scoring_result = scorer.score_batch(
                papers=passed_filter,
                evaluate_inclusion=True,
                paper_sources=paper_sources,
            )
            scored_papers = scoring_result.scored_papers

            # Save scored papers to database
            for sp in scored_papers:
                self._save_scored_paper(sp)

            timer.set_output(
                f"Scored {len(scoring_result.scored_papers)} papers, "
                f"avg score: {scoring_result.average_score:.2f}"
            )
            timer.add_metrics({
                "papers_scored": len(scoring_result.scored_papers),
                "average_score": round(scoring_result.average_score, 2),
                "failed_scoring": len(scoring_result.failed_papers),
            })

        # Apply relevance threshold
        relevance_threshold = self.config.relevance_threshold
        relevant_papers = [
            sp for sp in scored_papers
            if sp.relevance_score >= relevance_threshold
        ]
        below_threshold = [
            sp for sp in scored_papers
            if sp.relevance_score < relevance_threshold
        ]

        passed_relevance = len(relevant_papers)
        logger.info(f"{passed_relevance} papers passed relevance threshold ({relevance_threshold})")

        # Checkpoint: Review scoring results
        if not self._checkpoint(
            checkpoint_type=CHECKPOINT_SCORING_COMPLETE,
            state={
                "total_scored": len(scored_papers),
                "above_threshold": len(relevant_papers),
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

        # Phase 5: Quality Assessment
        self.documenter.set_phase("quality_assessment")

        with self.documenter.log_step_with_timer(
            action=ACTION_ASSESS_QUALITY,
            tool="QualityAssessor",
            input_summary=f"Assessing quality of {len(relevant_papers)} papers",
            decision_rationale="Evaluating study quality for final ranking",
        ) as timer:
            assessment_result = quality_assessor.assess_batch(relevant_papers)

            # Save assessed papers to database
            for ap in assessment_result.assessed_papers:
                self._save_assessed_paper(ap)

            timer.set_output(
                f"Assessed {len(assessment_result.assessed_papers)} papers, "
                f"failed: {len(assessment_result.failed_papers)}"
            )
            timer.add_metrics({
                "papers_assessed": len(assessment_result.assessed_papers),
                "failed_assessment": len(assessment_result.failed_papers),
                **assessment_result.assessment_statistics,
            })

        # Checkpoint: Review quality assessment results
        if not self._checkpoint(
            checkpoint_type=CHECKPOINT_QUALITY_ASSESSMENT,
            state={
                "papers_assessed": len(assessment_result.assessed_papers),
                "failed_assessment": len(assessment_result.failed_papers),
                "study_assessments": assessment_result.assessment_statistics.get("study_assessments", 0),
                "weight_assessments": assessment_result.assessment_statistics.get("weight_assessments", 0),
            },
            interactive=interactive,
            checkpoint_callback=checkpoint_callback,
            output_dir=output_dir,
        ):
            logger.info("Review aborted at quality assessment checkpoint")
            self.documenter.end_review()
            return self._build_empty_result(criteria, weights, "Aborted at quality assessment")

        # Phase 6: Composite Scoring
        # Get assessed papers from database
        assessed_papers = self.get_assessed_papers()

        with self.documenter.log_step_with_timer(
            action=ACTION_CALCULATE_COMPOSITE,
            tool="CompositeScorer",
            input_summary=f"Calculating composite scores for {len(assessed_papers)} papers",
            decision_rationale="Combining all scores for final ranking",
        ) as timer:
            for assessed in assessed_papers:
                assessed.composite_score = composite_scorer.score(assessed)

            # Sort by composite score and assign ranks
            assessed_papers.sort(key=lambda x: x.composite_score, reverse=True)
            for i, paper in enumerate(assessed_papers):
                paper.final_rank = i + 1

            timer.set_output(
                f"Ranked {len(assessed_papers)} papers by composite score"
            )

        # Determine final inclusion
        final_included = [ap for ap in assessed_papers if ap.is_included]
        final_excluded_assessed = [ap for ap in assessed_papers if not ap.is_included]

        # =================================================================
        # Collect ALL excluded papers for comprehensive reporting
        # =================================================================
        all_excluded_papers: List[ScoredPaper] = []

        # 1. Papers rejected in initial filter (from checkpoint or current run)
        for paper, reason in self._rejected_initial_filter:
            all_excluded_papers.append(ScoredPaper(
                paper=paper,
                relevance_score=0.0,
                relevance_rationale=reason,
                inclusion_decision=InclusionDecision.create_excluded(
                    stage=ExclusionStage.INITIAL_FILTER,
                    reasons=[reason],
                    rationale=reason,
                ),
            ))

        # 2. Papers below relevance threshold from database
        all_excluded_papers.extend(self.get_below_threshold_papers())

        # 3. Papers that failed quality gate (from assessed papers)
        for ap in final_excluded_assessed:
            all_excluded_papers.append(ap.scored_paper)

        # Build statistics with accurate counts
        # NOTE: passed_quality_gate should be final_included, not len(_assessed_papers)
        # _assessed_papers = all papers that were quality assessed
        # final_included = papers that actually passed the quality threshold
        stats = ReviewStatistics(
            total_considered=total_considered,
            passed_initial_filter=passed_initial_filter,
            passed_relevance_threshold=passed_relevance,
            passed_quality_gate=len(final_included),
            final_included=len(final_included),
            final_excluded=len(all_excluded_papers),
            uncertain_for_review=0,
            processing_time_seconds=self.documenter.get_duration(),
            total_llm_calls=self.documenter._total_llm_calls,
            total_tokens_used=self.documenter._total_tokens,
        )

        # =================================================================
        # Phase 6a: Evidence Synthesis (Optional)
        # =================================================================
        evidence_synthesis = None
        if self.config.enable_evidence_synthesis and final_included:
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
                input_summary=f"Synthesizing evidence from {len(final_included)} included papers",
                decision_rationale="Extract citations and synthesize narrative answer to research question",
            ) as timer:
                try:
                    evidence_synthesis = synthesizer.synthesize(
                        research_question=criteria.research_question,
                        included_papers=final_included,
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

        # Phase 7: Report Generation
        self.documenter.set_phase("reporting")

        with self.documenter.log_step_with_timer(
            action=ACTION_GENERATE_REPORT,
            tool="Reporter",
            input_summary=f"Generating report for {len(final_included)} included, {len(all_excluded_papers)} excluded papers",
            decision_rationale="Creating final systematic review output with comprehensive excluded paper tracking",
        ) as timer:
            # Build result using reporter with ALL excluded papers
            result = reporter.build_json_result(
                included_papers=final_included,
                excluded_papers=all_excluded_papers,
                uncertain_papers=[],
                search_plan=self._search_plan,
                executed_queries=self._executed_queries,
                statistics=stats,
                evidence_synthesis=evidence_synthesis,
            )

            if output_path:
                reporter.generate_json_report(result, output_path)
                # Also generate markdown report
                md_path = output_path.replace(".json", ".md") if output_path.endswith(".json") else output_path + ".md"
                reporter.generate_markdown_report(result, md_path)

            timer.set_output(f"Report generated with {len(final_included)} papers")

        self.documenter.end_review()
        return result

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
        # Get counts from database
        scored_papers = self.get_scored_papers()
        assessed_papers = self.get_assessed_papers()

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
