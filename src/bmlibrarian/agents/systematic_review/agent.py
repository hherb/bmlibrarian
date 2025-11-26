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
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

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
)
from .documenter import Documenter

if TYPE_CHECKING:
    from ..orchestrator import AgentOrchestrator

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
        config: Optional[SystematicReviewConfig] = None,
        callback: Optional[Callable[[str, str], None]] = None,
        orchestrator: Optional["AgentOrchestrator"] = None,
        show_model_info: bool = True,
    ) -> None:
        """
        Initialize the SystematicReviewAgent.

        Args:
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

        # Current review state (set when run_review is called)
        self._criteria: Optional[SearchCriteria] = None
        self._weights: Optional[ScoringWeights] = None
        self._search_plan: Optional[SearchPlan] = None
        self._executed_queries: List[ExecutedQuery] = []
        self._all_papers: List[PaperData] = []
        self._scored_papers: List[ScoredPaper] = []
        self._assessed_papers: List[AssessedPaper] = []

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
            from .executor import SearchExecutor
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
                config=self.config,
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
            ):
                logger.info("Review aborted at search strategy checkpoint")
                self.documenter.end_review()
                return self._build_empty_result(criteria, weights, "Aborted at search strategy")

            # =================================================================
            # Phase 2: Execute Search Plan
            # =================================================================
            self.documenter.set_phase("search_execution")

            with self.documenter.log_step_with_timer(
                action=ACTION_EXECUTE_SEARCH,
                tool="SearchExecutor",
                input_summary=f"Executing {len(self._search_plan.queries)} queries",
                decision_rationale="Running all planned queries to find candidate papers",
            ) as timer:
                search_results = executor.execute_plan(self._search_plan)
                self._executed_queries = search_results.executed_queries
                self._all_papers = search_results.papers

                timer.set_output(
                    f"Found {search_results.count} unique papers "
                    f"from {search_results.total_before_dedup} total"
                )
                timer.add_metrics({
                    "total_papers_found": search_results.total_before_dedup,
                    "unique_papers": search_results.count,
                    "deduplication_rate": round(search_results.deduplication_rate * 100, 2),
                })

            # Track statistics
            total_considered = len(self._all_papers)

            # Checkpoint: Review initial results
            if not self._checkpoint(
                checkpoint_type=CHECKPOINT_INITIAL_RESULTS,
                state={
                    "unique_papers": len(self._all_papers),
                    "total_before_dedup": search_results.total_before_dedup,
                    "sample_titles": [p.title[:80] for p in self._all_papers[:10]],
                },
                interactive=interactive,
                checkpoint_callback=checkpoint_callback,
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
                passed_filter = filter_result.passed_papers
                rejected_filter = filter_result.rejected_papers

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
                self._scored_papers = scoring_result.scored_papers

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
            above_threshold, below_threshold = scorer.apply_relevance_threshold(
                self._scored_papers,
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

            # Checkpoint: Review scoring results
            if not self._checkpoint(
                checkpoint_type=CHECKPOINT_SCORING_COMPLETE,
                state={
                    "total_scored": len(self._scored_papers),
                    "above_threshold": len(above_threshold),
                    "below_threshold": len(below_threshold),
                    "average_score": scoring_result.average_score,
                },
                interactive=interactive,
                checkpoint_callback=checkpoint_callback,
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
                self._assessed_papers = quality_result.assessed_papers

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
            if not self._checkpoint(
                checkpoint_type=CHECKPOINT_QUALITY_ASSESSMENT,
                state={
                    "papers_assessed": len(self._assessed_papers),
                    "assessment_stats": quality_result.assessment_statistics,
                },
                interactive=interactive,
                checkpoint_callback=checkpoint_callback,
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
                input_summary=f"Calculating composite scores for {len(self._assessed_papers)} papers",
                decision_rationale="Combining scores using user-defined weights",
            ) as timer:
                ranked_papers = composite_scorer.score_and_rank(self._assessed_papers)

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
                p for p in self._scored_papers
                if p.inclusion_decision.status == InclusionStatus.UNCERTAIN
            ]

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
    ) -> bool:
        """
        Handle a workflow checkpoint.

        In interactive mode, pauses for human approval.
        In auto mode, continues unless callback returns False.

        Args:
            checkpoint_type: Type of checkpoint (e.g., "search_strategy")
            state: Current state snapshot
            interactive: Whether running in interactive mode
            checkpoint_callback: Optional callback for decision

        Returns:
            True to continue, False to abort
        """
        # Log checkpoint
        checkpoint = self.documenter.log_checkpoint(
            checkpoint_type=checkpoint_type,
            phase=self.documenter._current_phase,
            state_snapshot=state,
        )

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
        return {
            "review_id": self.documenter.review_id,
            "papers_found": len(self._all_papers),
            "papers_scored": len(self._scored_papers),
            "papers_assessed": len(self._assessed_papers),
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
        self._criteria = None
        self._weights = None
        self._search_plan = None
        self._executed_queries = []
        self._all_papers = []
        self._scored_papers = []
        self._assessed_papers = []
        self.documenter = Documenter()
        self.reset_metrics()
        logger.info("SystematicReviewAgent state reset")
