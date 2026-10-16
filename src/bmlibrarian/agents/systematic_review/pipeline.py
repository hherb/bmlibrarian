"""
Review pipeline for SystematicReviewAgent.

Runs the phases that follow search planning:

    search execution → initial filtering + relevance scoring
    → quality assessment → ranking, synthesis and report

A fresh review (``run_review``) enters the pipeline at the first stage; a
resumed review (``run_review_from_checkpoint``) enters it at the stage after
the checkpoint it was saved at. Both paths share this one implementation, so
they cannot drift apart.

Every stage after search reads scored and assessed papers back from the
evaluation store rather than from in-memory results. That makes the stages
independent of how the review got there, and lets an interrupted run reuse
the evaluations it already saved instead of paying for them again.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path
from typing import Any, Callable, Dict, FrozenSet, List, Optional, Set, Tuple, TYPE_CHECKING

from .config import (
    CHECKPOINT_TITLE_TRUNCATE_LENGTH,
    CHECKPOINT_SAMPLE_TITLES_COUNT,
)
from .data_models import (
    SearchCriteria,
    ScoringWeights,
    SearchPlan,
    ExecutedQuery,
    QueryFeedback,
    PaperData,
    ScoredPaper,
    AssessedPaper,
    ReviewStatistics,
    SystematicReviewResult,
    InclusionDecision,
    InclusionStatus,
    ExclusionStage,
)
from .documenter import (
    Documenter,
    CHECKPOINT_SEARCH_STRATEGY,
    CHECKPOINT_INITIAL_RESULTS,
    CHECKPOINT_SCORING_COMPLETE,
    CHECKPOINT_QUALITY_ASSESSMENT,
    ACTION_EXECUTE_SEARCH,
    ACTION_INITIAL_FILTER,
    ACTION_SCORE_RELEVANCE,
    ACTION_ASSESS_QUALITY,
    ACTION_CALCULATE_COMPOSITE,
    ACTION_GENERATE_REPORT,
)
from .exceptions import (
    SystematicReviewError,
    LLMConnectionError,
    DatabaseConnectionError,
)

if TYPE_CHECKING:
    from bmlibrarian.evaluations import EvaluationRun, EvaluationStore
    from ..orchestrator import AgentOrchestrator
    from .config import SystematicReviewConfig
    from .executor import SearchExecutor
    from .filters import InitialFilter
    from .scorer import RelevanceScorer, CompositeScorer
    from .quality import QualityAssessor
    from .reporter import Reporter

logger = logging.getLogger(__name__)


# =============================================================================
# Stages
# =============================================================================

class ReviewStage(IntEnum):
    """
    Pipeline stages, in execution order.

    Initial filtering is part of SCORE_RELEVANCE: it is cheap and
    deterministic, so a resume re-runs it rather than checkpointing it.
    """

    EXECUTE_SEARCH = 1
    SCORE_RELEVANCE = 2
    ASSESS_QUALITY = 3
    FINALIZE = 4


# The stage a resume starts at, for each checkpoint type. A checkpoint is
# written after its phase finished, so the resume starts at the next stage.
RESUME_STAGE_BY_CHECKPOINT: Dict[str, ReviewStage] = {
    CHECKPOINT_SEARCH_STRATEGY: ReviewStage.EXECUTE_SEARCH,
    CHECKPOINT_INITIAL_RESULTS: ReviewStage.SCORE_RELEVANCE,
    CHECKPOINT_SCORING_COMPLETE: ReviewStage.ASSESS_QUALITY,
    CHECKPOINT_QUALITY_ASSESSMENT: ReviewStage.FINALIZE,
}

# Stages that read evaluations saved by earlier stages. Resuming at one of
# these without the original evaluation run would silently report nothing.
STAGES_REQUIRING_SAVED_EVALUATIONS: FrozenSet[ReviewStage] = frozenset({
    ReviewStage.ASSESS_QUALITY,
    ReviewStage.FINALIZE,
})

# Abort reasons reported in the empty result when a checkpoint is rejected.
ABORT_REASON_BY_CHECKPOINT: Dict[str, str] = {
    CHECKPOINT_SEARCH_STRATEGY: "Aborted at search strategy",
    CHECKPOINT_INITIAL_RESULTS: "Aborted at initial results",
    CHECKPOINT_SCORING_COMPLETE: "Aborted at scoring",
    CHECKPOINT_QUALITY_ASSESSMENT: "Aborted at quality assessment",
}


# =============================================================================
# Data types
# =============================================================================

@dataclass(frozen=True)
class ReviewRunOptions:
    """
    Caller options that apply to every stage of one review run.

    Attributes:
        interactive: Pause at checkpoints for approval.
        output_path: Optional path for the JSON report (Markdown alongside).
        checkpoint_callback: Optional callback deciding each checkpoint.
    """

    interactive: bool
    output_path: Optional[str]
    checkpoint_callback: Optional[Callable[[str, Dict], bool]]

    @property
    def output_dir(self) -> Optional[str]:
        """Directory checkpoint files are saved in (the report's directory)."""
        if not self.output_path:
            return None
        return str(Path(self.output_path).expanduser().parent)


@dataclass
class PipelineComponents:
    """
    Workers used by the pipeline stages.

    Attributes:
        executor: Search executor; only built when the search stage runs.
        initial_filter: Heuristic pre-filter.
        scorer: LLM relevance scorer.
        quality_assessor: Study quality assessor.
        composite_scorer: Weighted composite scorer and quality gate.
        reporter: Report builder.
    """

    executor: Optional["SearchExecutor"]
    initial_filter: "InitialFilter"
    scorer: "RelevanceScorer"
    quality_assessor: "QualityAssessor"
    composite_scorer: "CompositeScorer"
    reporter: "Reporter"


class ReviewAborted(Exception):
    """Raised when the user rejects a checkpoint; carries the abort reason."""

    def __init__(self, reason: str) -> None:
        """
        Create the abort signal.

        Args:
            reason: Human-readable abort reason for the empty result.
        """
        super().__init__(reason)
        self.reason = reason


# =============================================================================
# Pure helpers
# =============================================================================

def average_relevance(scored_papers: List[ScoredPaper]) -> float:
    """
    Mean relevance score of scored papers.

    Args:
        scored_papers: Scored papers (may be empty).

    Returns:
        The mean score, or 0.0 for an empty list.
    """
    if not scored_papers:
        return 0.0
    return sum(sp.relevance_score for sp in scored_papers) / len(scored_papers)


def markdown_report_path(output_path: str) -> str:
    """
    Path of the Markdown report written next to a JSON report.

    Args:
        output_path: JSON report path.

    Returns:
        ``report.json`` → ``report.md``; any other path gets ``.md`` appended.
    """
    if output_path.endswith(".json"):
        return output_path[: -len(".json")] + ".md"
    return output_path + ".md"


def exclude_at_initial_filter(paper: PaperData, reason: str) -> ScoredPaper:
    """
    Represent a paper rejected by the initial filter as an excluded result.

    Args:
        paper: The rejected paper.
        reason: Why the filter rejected it.

    Returns:
        A zero-score ScoredPaper excluded at the initial-filter stage.
    """
    return ScoredPaper(
        paper=paper,
        relevance_score=0.0,
        relevance_rationale=reason,
        inclusion_decision=InclusionDecision.create_excluded(
            stage=ExclusionStage.INITIAL_FILTER,
            reasons=[reason],
            rationale=reason,
        ),
    )


# =============================================================================
# Host declarations
# =============================================================================

class ReviewHost:
    """
    Declares the SystematicReviewAgent state and methods the review mixins use.

    Annotations only: nothing here exists at runtime. SystematicReviewAgent
    sets the attributes in ``__init__`` and defines the methods.
    """

    config: "SystematicReviewConfig"
    documenter: Documenter
    callback: Optional[Callable[[str, str], None]]
    orchestrator: Optional["AgentOrchestrator"]
    _criteria: Optional[SearchCriteria]
    _weights: Optional[ScoringWeights]
    _search_plan: Optional[SearchPlan]
    _executed_queries: List[ExecutedQuery]
    _all_papers: List[PaperData]
    _rejected_initial_filter: List[Tuple[PaperData, str]]
    _paper_sources: Dict[int, List[str]]
    _semantic_baseline_ids: Set[int]
    _query_feedback: Optional[QueryFeedback]
    _evaluation_store: "EvaluationStore"
    _evaluation_run: Optional["EvaluationRun"]

    if TYPE_CHECKING:
        def get_scored_papers(
            self, min_score: Optional[float] = None, limit: Optional[int] = None,
        ) -> List[ScoredPaper]:
            """Scored papers of the current run."""
            ...

        def get_assessed_papers(
            self,
            min_score: Optional[float] = None,
            limit: Optional[int] = None,
            _scored_papers_map: Optional[Dict[int, ScoredPaper]] = None,
        ) -> List[AssessedPaper]:
            """Assessed papers of the current run."""
            ...

        def get_scored_and_assessed_papers(
            self,
            min_relevance_score: Optional[float] = None,
            min_composite_score: Optional[float] = None,
        ) -> Tuple[List[ScoredPaper], List[AssessedPaper]]:
            """Scored and assessed papers of the current run."""
            ...

        def _save_scored_paper(self, scored_paper: ScoredPaper) -> int:
            """Persist one relevance score."""
            ...

        def _save_assessed_paper(self, assessed_paper: AssessedPaper) -> int:
            """Persist one quality assessment."""
            ...

        def _start_evaluation_run(self, documents_total: int = 0) -> "EvaluationRun":
            """Create a new evaluation run."""
            ...

        def _complete_evaluation_run(
            self, success: bool = True, error_message: Optional[str] = None,
        ) -> None:
            """Mark the run completed or failed."""
            ...

        def _pause_evaluation_run(self) -> None:
            """Mark the run paused."""
            ...

        def _checkpoint(
            self,
            checkpoint_type: str,
            state: Dict[str, Any],
            interactive: bool,
            checkpoint_callback: Optional[Callable[[str, Dict], bool]] = None,
            output_dir: Optional[str] = None,
        ) -> bool:
            """Handle a checkpoint; True to continue."""
            ...

        def _build_empty_result(
            self, criteria: SearchCriteria, weights: ScoringWeights, reason: str,
        ) -> SystematicReviewResult:
            """Result for an aborted review."""
            ...

    def _active_criteria(self) -> SearchCriteria:
        """
        The criteria of the review in progress.

        Returns:
            The current SearchCriteria.

        Raises:
            SystematicReviewError: If no review is in progress.
        """
        if self._criteria is None:
            raise SystematicReviewError("No review in progress: search criteria are not set")
        return self._criteria

    def _active_weights(self) -> ScoringWeights:
        """
        The scoring weights of the review in progress.

        Returns:
            The current ScoringWeights.

        Raises:
            SystematicReviewError: If no review is in progress.
        """
        if self._weights is None:
            raise SystematicReviewError("No review in progress: scoring weights are not set")
        return self._weights


# =============================================================================
# Pipeline mixin
# =============================================================================

class ReviewPipelineMixin(ReviewHost):
    """
    Pipeline stages for SystematicReviewAgent (state declared on ReviewHost).
    """

    # -------------------------------------------------------------------------
    # Entry points
    # -------------------------------------------------------------------------

    def _run_guarded(
        self,
        body: Callable[[], SystematicReviewResult],
    ) -> SystematicReviewResult:
        """
        Run a review body, recording the outcome on the evaluation run.

        Success completes the run; a rejected checkpoint or a user interrupt
        pauses it (it can be resumed from its checkpoint file); an error marks
        it failed and is re-raised as a SystematicReviewError subclass.

        Args:
            body: Callable executing the review and returning its result.

        Returns:
            The review result, or an empty result if a checkpoint was rejected.

        Raises:
            SystematicReviewError: On any failure (connection, timeout,
                validation and unexpected errors are wrapped).
            KeyboardInterrupt: If the user interrupts the review.
        """
        try:
            result = body()
        except ReviewAborted as aborted:
            logger.info(f"Review aborted: {aborted.reason}")
            self._pause_evaluation_run()
            self.documenter.end_review()
            return self._build_empty_result(
                self._active_criteria(), self._active_weights(), aborted.reason
            )
        except KeyboardInterrupt:
            logger.info("Systematic review interrupted by user")
            self.documenter.log_step(
                action="review_interrupted",
                tool=None,
                input_summary="Review interrupted by user",
                output_summary="Review was cancelled by user",
                decision_rationale="User requested cancellation",
            )
            self._pause_evaluation_run()
            self.documenter.end_review()
            raise
        except SystematicReviewError as e:
            self._record_review_failure(
                error=e,
                error_msg=str(e),
                input_summary="Review failed",
                rationale="Systematic review error",
            )
            raise
        except ConnectionError as e:
            error_msg = f"Connection error during systematic review: {e}"
            self._record_review_failure(
                error=e,
                error_msg=error_msg,
                input_summary="Review encountered connection error",
                rationale="Database or network connectivity failure",
            )
            raise DatabaseConnectionError(error_msg) from e
        except TimeoutError as e:
            error_msg = f"Timeout during systematic review: {e}"
            self._record_review_failure(
                error=e,
                error_msg=error_msg,
                input_summary="Review timed out",
                rationale="Operation timeout - consider increasing timeout settings",
            )
            raise LLMConnectionError(error_msg) from e
        except ValueError as e:
            error_msg = f"Validation error during systematic review: {e}"
            self._record_review_failure(
                error=e,
                error_msg=error_msg,
                input_summary="Review encountered validation error",
                rationale="Data validation or configuration error",
            )
            raise SystematicReviewError(error_msg) from e
        except Exception as e:
            error_type = type(e).__name__
            error_msg = f"Unexpected error ({error_type}) during systematic review: {e}"
            self._record_review_failure(
                error=e,
                error_msg=error_msg,
                input_summary=f"Review encountered unexpected {error_type}",
                rationale="Unexpected error - please report this issue",
                metrics={
                    "error_type": error_type,
                    "phase": self.documenter._current_phase,
                },
            )
            raise SystematicReviewError(error_msg) from e

        self._complete_evaluation_run(success=True)
        return result

    def _execute_pipeline(
        self,
        start: ReviewStage,
        options: ReviewRunOptions,
    ) -> SystematicReviewResult:
        """
        Run the pipeline from ``start`` to the final report.

        Args:
            start: First stage to run.
            options: Caller options for checkpoints and output.

        Returns:
            The completed review result.

        Raises:
            ReviewAborted: If the user rejects a checkpoint.
        """
        components = self._build_pipeline_components(
            include_executor=start <= ReviewStage.EXECUTE_SEARCH,
        )

        if start <= ReviewStage.EXECUTE_SEARCH:
            total_before_dedup = self._stage_execute_search(components.executor)
            self._require_checkpoint(
                CHECKPOINT_INITIAL_RESULTS,
                {
                    "unique_papers": len(self._all_papers),
                    "total_before_dedup": total_before_dedup,
                    "sample_titles": [
                        p.title[:CHECKPOINT_TITLE_TRUNCATE_LENGTH]
                        for p in self._all_papers[:CHECKPOINT_SAMPLE_TITLES_COUNT]
                    ],
                },
                options,
            )

        if start <= ReviewStage.SCORE_RELEVANCE:
            passed_filter = self._stage_initial_filter(components.initial_filter)
            scoring_state = self._stage_score_relevance(components.scorer, passed_filter)
            self._require_checkpoint(CHECKPOINT_SCORING_COMPLETE, scoring_state, options)

        if start <= ReviewStage.ASSESS_QUALITY:
            quality_state = self._stage_assess_quality(
                components.scorer, components.quality_assessor
            )
            self._require_checkpoint(CHECKPOINT_QUALITY_ASSESSMENT, quality_state, options)
        else:
            # Resumed after the quality checkpoint. A relevance threshold
            # lowered since then admits papers that were never assessed;
            # assess those (cached assessments are skipped, so this is
            # normally a no-op) rather than drop them from the report.
            self._stage_assess_quality(components.scorer, components.quality_assessor)

        return self._stage_finalize(components, options)

    # -------------------------------------------------------------------------
    # Stages
    # -------------------------------------------------------------------------

    def _stage_execute_search(self, executor: Optional["SearchExecutor"]) -> int:
        """
        Execute the search plan, phased or standard per configuration.

        Sets ``_executed_queries``, ``_all_papers``, ``_paper_sources`` and
        ``_semantic_baseline_ids``.

        Args:
            executor: The search executor.

        Returns:
            Total results before de-duplication.

        Raises:
            SystematicReviewError: If there is no executor or search plan.
        """
        if executor is None or self._search_plan is None:
            raise SystematicReviewError("Search stage needs a search plan and executor")

        self.documenter.set_phase("search_execution")
        query_count = len(self._search_plan.queries)

        if self.config.use_phased_search:
            with self.documenter.log_step_with_timer(
                action=ACTION_EXECUTE_SEARCH,
                tool="SearchExecutor (Phased)",
                input_summary=f"Executing {query_count} queries in two phases",
                decision_rationale="Running phased search: semantic/HyDE first for baseline, then keyword",
            ) as timer:
                phased = executor.execute_phased_plan(
                    self._search_plan,
                    max_phase2_no_overlap=self.config.max_phase2_no_overlap,
                )
                self._executed_queries = phased.executed_queries
                self._all_papers = phased.all_papers
                self._paper_sources = phased.paper_sources
                self._semantic_baseline_ids = set(phased.phase1_document_ids)
                total_before_dedup = sum(
                    len(eq.document_ids) for eq in phased.executed_queries
                )
                timer.set_output(
                    f"Found {phased.total_count} unique papers "
                    f"(Phase 1: {phased.phase1_count}, Phase 2 new: {phased.phase2_new_count})"
                )
                timer.add_metrics({
                    "phase1_papers": phased.phase1_count,
                    "phase2_new_papers": phased.phase2_new_count,
                    "unique_papers": phased.total_count,
                    "search_strategy": "phased",
                })
            return total_before_dedup

        with self.documenter.log_step_with_timer(
            action=ACTION_EXECUTE_SEARCH,
            tool="SearchExecutor",
            input_summary=f"Executing {query_count} queries",
            decision_rationale="Running all planned queries to find candidate papers",
        ) as timer:
            results = executor.execute_plan(self._search_plan)
            self._executed_queries = results.executed_queries
            self._all_papers = results.papers
            self._paper_sources = results.paper_sources
            self._semantic_baseline_ids = set()
            timer.set_output(
                f"Found {results.count} unique papers "
                f"from {results.total_before_dedup} total"
            )
            timer.add_metrics({
                "total_papers_found": results.total_before_dedup,
                "unique_papers": results.count,
                "deduplication_rate": round(results.deduplication_rate * 100, 2),
                "search_strategy": "standard",
            })
        return results.total_before_dedup

    def _stage_initial_filter(self, initial_filter: "InitialFilter") -> List[PaperData]:
        """
        Apply the heuristic pre-filter to all found papers.

        Sets ``_rejected_initial_filter``.

        Args:
            initial_filter: The initial filter.

        Returns:
            Papers that passed the filter.
        """
        self.documenter.set_phase("initial_filtering")
        total = len(self._all_papers)

        with self.documenter.log_step_with_timer(
            action=ACTION_INITIAL_FILTER,
            tool="InitialFilter",
            input_summary=f"Filtering {total} papers with heuristics",
            decision_rationale="Fast filtering before expensive LLM scoring",
        ) as timer:
            filter_result = initial_filter.filter_batch(self._all_papers)
            self._rejected_initial_filter = filter_result.rejected
            passed = filter_result.passed
            timer.set_output(
                f"Passed: {len(passed)}, Rejected: {len(filter_result.rejected)}"
            )
            timer.add_metrics({
                "passed": len(passed),
                "rejected": len(filter_result.rejected),
                "pass_rate": round(len(passed) / total * 100, 2) if total > 0 else 0,
            })
        return passed

    def _stage_score_relevance(
        self,
        scorer: "RelevanceScorer",
        passed_filter: List[PaperData],
    ) -> Dict[str, Any]:
        """
        Score papers not yet scored in this evaluation run.

        Papers already scored in the run (a resumed or repeated review) are
        reused, not re-scored. The threshold is then applied to every scored
        paper of the run, and query effectiveness is evaluated for phased
        searches.

        Args:
            scorer: The relevance scorer.
            passed_filter: Papers that passed the initial filter.

        Returns:
            The scoring-checkpoint state.
        """
        from bmlibrarian.evaluations import EvaluationType

        self.documenter.set_phase("relevance_scoring")

        already_scored = self._evaluated_document_ids(EvaluationType.RELEVANCE_SCORE)
        papers_to_score = [p for p in passed_filter if p.document_id not in already_scored]
        cached_count = len(passed_filter) - len(papers_to_score)
        if cached_count:
            logger.info(
                f"Found {cached_count} already-scored documents, "
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
                    paper_sources=self._paper_sources,
                    save_callback=self._save_scored_paper,
                )
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
                timer.set_output(f"All {cached_count} papers already scored (cached)")
                timer.add_metrics({
                    "papers_scored": 0,
                    "papers_cached": cached_count,
                    "failed_scoring": 0,
                })

        scored_papers = self.get_scored_papers()
        threshold = self.config.relevance_threshold
        above, below = scorer.apply_relevance_threshold(scored_papers, threshold=threshold)
        self.documenter.log_step(
            action="apply_relevance_threshold",
            tool=None,
            input_summary=f"Threshold: {threshold}",
            output_summary=f"Above: {len(above)}, Below: {len(below)}",
            decision_rationale=f"Filtering by relevance threshold {threshold}",
            metrics={
                "above_threshold": len(above),
                "below_threshold": len(below),
                "threshold": threshold,
            },
        )

        self._evaluate_query_feedback(scorer, scored_papers)

        return {
            "total_scored": len(scored_papers),
            "above_threshold": len(above),
            "below_threshold": len(below),
            "average_score": average_relevance(scored_papers),
        }

    def _evaluate_query_feedback(
        self,
        scorer: "RelevanceScorer",
        scored_papers: List[ScoredPaper],
    ) -> None:
        """
        Record how effective each query was (phased search only).

        Sets ``_query_feedback`` (None when disabled or not phased).

        Args:
            scorer: The relevance scorer.
            scored_papers: All scored papers of the run.
        """
        self._query_feedback = None
        if not (self.config.use_phased_search and self.config.enable_query_feedback):
            return

        feedback = scorer.evaluate_query_effectiveness(
            executed_queries=self._executed_queries,
            scored_papers=scored_papers,
            semantic_baseline_ids=self._semantic_baseline_ids,
            threshold=self.config.relevance_threshold,
        )
        self._query_feedback = feedback

        self.documenter.log_step(
            action="evaluate_query_effectiveness",
            tool=None,
            input_summary=f"Evaluating {len(self._executed_queries)} queries",
            output_summary=f"{feedback.total_effective_queries}/{feedback.total_queries_executed} effective",
            decision_rationale="Tracking query effectiveness for feedback loop",
            metrics={
                "total_queries": feedback.total_queries_executed,
                "effective_queries": feedback.total_effective_queries,
                "effective_ratio": round(feedback.effective_ratio * 100, 2),
                "effective_patterns": len(feedback.effective_queries),
                "ineffective_patterns": len(feedback.ineffective_queries),
            },
        )
        if feedback.ineffective_queries:
            logger.info(
                f"Identified {len(feedback.ineffective_queries)} ineffective queries "
                f"that will be used as negative examples for future query generation"
            )

    def _stage_assess_quality(
        self,
        scorer: "RelevanceScorer",
        quality_assessor: "QualityAssessor",
    ) -> Dict[str, Any]:
        """
        Assess the quality of above-threshold papers not yet assessed.

        Args:
            scorer: The relevance scorer (for the threshold split).
            quality_assessor: The quality assessor.

        Returns:
            The quality-checkpoint state.
        """
        from bmlibrarian.evaluations import EvaluationType

        self.documenter.set_phase("quality_assessment")

        above, _ = scorer.apply_relevance_threshold(
            self.get_scored_papers(), threshold=self.config.relevance_threshold
        )
        already_assessed = self._evaluated_document_ids(EvaluationType.QUALITY_ASSESSMENT)
        papers_to_assess = [sp for sp in above if sp.paper.document_id not in already_assessed]
        cached_count = len(above) - len(papers_to_assess)
        if cached_count:
            logger.info(
                f"Found {cached_count} already-assessed documents, "
                f"assessing {len(papers_to_assess)} new documents"
            )

        assessment_stats: Dict[str, Any] = {}
        with self.documenter.log_step_with_timer(
            action=ACTION_ASSESS_QUALITY,
            tool="QualityAssessor",
            input_summary=f"Assessing quality of {len(papers_to_assess)} papers ({cached_count} cached)",
            decision_rationale="Evaluating study quality and methodology",
        ) as timer:
            if papers_to_assess:
                quality_result = quality_assessor.assess_batch(
                    papers_to_assess,
                    save_callback=self._save_assessed_paper,
                )
                assessment_stats = quality_result.assessment_statistics
                timer.set_output(
                    f"Assessed {len(quality_result.assessed_papers)} papers, "
                    f"failed: {len(quality_result.failed_papers)} "
                    f"({cached_count} cached)"
                )
                timer.add_metrics({
                    "papers_assessed": len(quality_result.assessed_papers),
                    "papers_cached": cached_count,
                    "failed_assessment": len(quality_result.failed_papers),
                    **assessment_stats,
                })
            else:
                timer.set_output(f"All {cached_count} papers already assessed (cached)")
                timer.add_metrics({
                    "papers_assessed": 0,
                    "papers_cached": cached_count,
                    "failed_assessment": 0,
                })

        return {
            "papers_assessed": len(self.get_assessed_papers()),
            "assessment_stats": assessment_stats,
        }

    def _stage_finalize(
        self,
        components: PipelineComponents,
        options: ReviewRunOptions,
    ) -> SystematicReviewResult:
        """
        Rank, apply the quality gate, synthesise evidence and write the report.

        Args:
            components: Pipeline workers.
            options: Caller options (output path).

        Returns:
            The completed review result.
        """
        threshold = self.config.relevance_threshold
        scored_papers = self.get_scored_papers()
        above, below = components.scorer.apply_relevance_threshold(
            scored_papers, threshold=threshold
        )
        # Fetched separately from scored_papers: the quality gate rewrites the
        # inclusion decision of assessed papers, and the uncertain list below
        # must keep the screening decision. Only papers above the *current*
        # threshold are ranked: a resume may run with a raised threshold, and
        # a paper assessed earlier but now below it is already in `below`.
        above_ids = {sp.paper.document_id for sp in above}
        assessed_papers = [
            ap for ap in self.get_assessed_papers()
            if ap.scored_paper.paper.document_id in above_ids
        ]

        self.documenter.set_phase("ranking")
        with self.documenter.log_step_with_timer(
            action=ACTION_CALCULATE_COMPOSITE,
            tool="CompositeScorer",
            input_summary=f"Calculating composite scores for {len(assessed_papers)} papers",
            decision_rationale="Combining scores using user-defined weights",
        ) as timer:
            ranked = components.composite_scorer.score_and_rank(assessed_papers)
            timer.set_output(f"Ranked {len(ranked)} papers")
            timer.add_metrics({"papers_ranked": len(ranked)})

        quality_threshold = self.config.quality_threshold
        included, failed_quality = components.composite_scorer.apply_quality_gate(
            ranked, threshold=quality_threshold
        )
        self.documenter.log_step(
            action="apply_quality_gate",
            tool=None,
            input_summary=f"Quality threshold: {quality_threshold}",
            output_summary=f"Passed: {len(included)}, Failed: {len(failed_quality)}",
            decision_rationale=f"Final quality gate at threshold {quality_threshold}",
            metrics={
                "passed": len(included),
                "failed": len(failed_quality),
                "threshold": quality_threshold,
            },
        )

        excluded: List[ScoredPaper] = [
            exclude_at_initial_filter(paper, reason)
            for paper, reason in self._rejected_initial_filter
        ]
        excluded.extend(below)
        excluded.extend(ap.scored_paper for ap in failed_quality)

        uncertain = [
            sp for sp in scored_papers
            if sp.inclusion_decision
            and sp.inclusion_decision.status == InclusionStatus.UNCERTAIN
        ]

        evidence_synthesis = self._synthesize_evidence(included)

        self.documenter.set_phase("reporting")
        with self.documenter.log_step_with_timer(
            action=ACTION_GENERATE_REPORT,
            tool="Reporter",
            input_summary=f"Generating report: {len(included)} included, {len(excluded)} excluded",
            decision_rationale="Creating comprehensive review report",
        ) as timer:
            doc_stats = self.documenter.get_statistics()
            total_considered = len(self._all_papers)
            statistics = ReviewStatistics(
                total_considered=total_considered,
                passed_initial_filter=total_considered - len(self._rejected_initial_filter),
                passed_relevance_threshold=len(above),
                passed_quality_gate=len(included),
                final_included=len(included),
                final_excluded=len(excluded),
                uncertain_for_review=len(uncertain),
                processing_time_seconds=self.documenter.get_duration(),
                total_llm_calls=doc_stats.get("total_llm_calls", 0),
                total_tokens_used=doc_stats.get("total_tokens", 0),
            )
            result = components.reporter.build_json_result(
                included_papers=included,
                excluded_papers=excluded,
                uncertain_papers=uncertain,
                search_plan=self._search_plan,
                executed_queries=self._executed_queries,
                statistics=statistics,
                evidence_synthesis=evidence_synthesis,
            )
            timer.set_output(f"Report generated with {statistics.final_included} included papers")
            timer.add_metrics(statistics.to_dict())

        if options.output_path:
            components.reporter.generate_json_report(result, options.output_path)
            components.reporter.generate_markdown_report(
                result, markdown_report_path(options.output_path)
            )

        self.documenter.end_review()
        logger.info(
            f"Systematic review complete: {statistics.final_included} included, "
            f"{statistics.final_excluded} excluded, "
            f"{statistics.uncertain_for_review} uncertain"
        )
        return result

    def _synthesize_evidence(self, included: List[AssessedPaper]) -> Optional[Any]:
        """
        Run optional evidence synthesis over the included papers.

        Synthesis failure is logged and reported in the audit trail; the
        review continues without a synthesis.

        Args:
            included: Papers that passed the quality gate.

        Returns:
            The EvidenceSynthesis, or None if disabled, empty or failed.
        """
        if not (self.config.enable_evidence_synthesis and included):
            return None

        from .synthesizer import EvidenceSynthesizer

        self.documenter.set_phase("evidence_synthesis")
        synthesizer = EvidenceSynthesizer(
            model=self.config.synthesis_model or self.config.model,
            citation_model=self.config.model,
            temperature=self.config.synthesis_temperature,
            citation_min_relevance=self.config.citation_min_relevance,
            max_citations_per_paper=self.config.max_citations_per_paper,
            progress_callback=self._make_synthesis_callback(),
        )

        with self.documenter.log_step_with_timer(
            action="synthesize_evidence",
            tool="EvidenceSynthesizer",
            input_summary=f"Synthesizing evidence from {len(included)} included papers",
            decision_rationale="Extract citations and synthesize narrative answer to research question",
        ) as timer:
            try:
                synthesis = synthesizer.synthesize(
                    research_question=self._active_criteria().research_question,
                    included_papers=included,
                )
            except Exception as e:
                logger.warning(f"Evidence synthesis failed, continuing without: {e}")
                timer.set_output(f"Evidence synthesis failed: {e}")
                if self.callback:
                    self.callback("synthesis_failed", f"Evidence synthesis failed: {e}")
                return None

            synth_stats = synthesizer.get_statistics()
            timer.set_output(
                f"Extracted {synth_stats['citations_extracted']} citations, "
                f"evidence strength: {synthesis.evidence_strength}"
            )
            timer.add_metrics({
                "citations_extracted": synth_stats["citations_extracted"],
                "papers_with_citations": synth_stats["papers_processed"],
                "extraction_failures": synth_stats["extraction_failures"],
                "evidence_strength": synthesis.evidence_strength,
            })
            logger.info(
                f"Evidence synthesis complete: {synth_stats['citations_extracted']} citations, "
                f"strength={synthesis.evidence_strength}"
            )
        return synthesis

    def _make_synthesis_callback(self) -> Optional[Callable[[str, int, int], None]]:
        """
        Adapt the agent callback to EvidenceSynthesizer's progress signature.

        The synthesizer calls ``callback(message, current, total)``; the agent
        callback takes ``(event, data)``.

        Returns:
            The wrapped callback, or None if the agent has no callback.
        """
        agent_callback = self.callback
        if agent_callback is None:
            return None

        def synthesis_callback(message: str, current: int, total: int) -> None:
            """Forward synthesizer progress as a ``synthesis_progress`` event."""
            agent_callback("synthesis_progress", f"{current}/{total} | {message}")

        return synthesis_callback

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def _build_pipeline_components(self, include_executor: bool) -> PipelineComponents:
        """
        Build the pipeline workers for the current criteria and weights.

        Args:
            include_executor: Whether the search stage will run.

        Returns:
            The pipeline components.
        """
        from .executor import SearchExecutor
        from .filters import InitialFilter
        from .scorer import RelevanceScorer, CompositeScorer
        from .quality import QualityAssessor
        from .reporter import Reporter

        criteria = self._active_criteria()
        weights = self._active_weights()
        executor = None
        if include_executor:
            executor = SearchExecutor(
                config=self.config,
                results_per_query=self.config.max_results_per_query,
                callback=self.callback,
            )
        return PipelineComponents(
            executor=executor,
            initial_filter=InitialFilter(criteria=criteria, callback=self.callback),
            scorer=RelevanceScorer(
                research_question=criteria.research_question,
                config=self.config,
                callback=self.callback,
                orchestrator=self.orchestrator,
                criteria=criteria,
            ),
            quality_assessor=QualityAssessor(
                config=self.config,
                callback=self.callback,
                orchestrator=self.orchestrator,
            ),
            composite_scorer=CompositeScorer(weights=weights),
            reporter=Reporter(
                documenter=self.documenter,
                criteria=criteria,
                weights=weights,
            ),
        )

    def _evaluated_document_ids(self, evaluation_type: Any) -> Set[int]:
        """
        Document IDs already evaluated in the current run.

        Args:
            evaluation_type: The EvaluationType to look up.

        Returns:
            Set of document IDs.

        Raises:
            SystematicReviewError: If there is no active evaluation run.
        """
        if not self._evaluation_run:
            raise SystematicReviewError(
                "No active evaluation run: evaluations cannot be saved or reused"
            )
        return set(
            self._evaluation_store.get_evaluated_document_ids(
                run_id=self._evaluation_run.run_id,
                evaluation_type=evaluation_type,
            )
        )

    def _require_checkpoint(
        self,
        checkpoint_type: str,
        state: Dict[str, Any],
        options: ReviewRunOptions,
    ) -> None:
        """
        Pass a checkpoint, or abort the review if it is rejected.

        Args:
            checkpoint_type: Checkpoint type constant.
            state: State snapshot shown to the approver.
            options: Caller options.

        Raises:
            ReviewAborted: If the checkpoint is rejected.
        """
        approved = self._checkpoint(
            checkpoint_type=checkpoint_type,
            state=state,
            interactive=options.interactive,
            checkpoint_callback=options.checkpoint_callback,
            output_dir=options.output_dir,
        )
        if not approved:
            raise ReviewAborted(
                ABORT_REASON_BY_CHECKPOINT.get(checkpoint_type, f"Aborted at {checkpoint_type}")
            )

    def _record_review_failure(
        self,
        error: BaseException,
        error_msg: str,
        input_summary: str,
        rationale: str,
        metrics: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Log a failed review to the log, audit trail and evaluation run.

        Args:
            error: The exception that ended the review.
            error_msg: Message for the log and the run's error field.
            input_summary: Audit-trail input summary.
            rationale: Audit-trail decision rationale.
            metrics: Optional extra audit-trail metrics.
        """
        logger.error(error_msg, exc_info=error)
        self.documenter.log_step(
            action="review_failed",
            tool=None,
            input_summary=input_summary,
            output_summary=error_msg,
            decision_rationale=rationale,
            error=str(error),
            metrics=metrics,
        )
        self._complete_evaluation_run(success=False, error_message=error_msg)
        self.documenter.end_review()
