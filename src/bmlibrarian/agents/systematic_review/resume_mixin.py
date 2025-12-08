"""
Checkpoint Resume Mixin for SystematicReviewAgent.

This module provides the CheckpointResumeMixin class that handles all
checkpoint resumption logic for the SystematicReviewAgent. The mixin
pattern allows these methods to be organized separately while still
having full access to the agent's state and methods.

The mixin contains methods for:
- Loading and validating checkpoint files
- Restoring agent state from checkpoints
- Continuing reviews from various checkpoint types
- Handling the complete workflow resumption
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

from .config import (
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
from .exceptions import SystematicReviewError

if TYPE_CHECKING:
    from .executor import AggregatedResults
    from .scorer import RelevanceScorer, CompositeScorer
    from .quality import QualityAssessor
    from .reporter import Reporter

logger = logging.getLogger(__name__)

# Agent version - should match agent.py AGENT_VERSION
AGENT_VERSION = "1.0.0"

# Note: CHECKPOINT_TITLE_TRUNCATE_LENGTH and CHECKPOINT_SAMPLE_TITLES_COUNT
# are imported from config.py to avoid duplication


class CheckpointResumeMixin:
    """
    Mixin providing checkpoint resume functionality for SystematicReviewAgent.

    This mixin is designed to be used with SystematicReviewAgent and requires
    the following attributes/methods to be present on the class:

    Attributes expected:
        - config: SystematicReviewConfig
        - documenter: Documenter
        - callback: Optional progress callback
        - _criteria: Optional[SearchCriteria]
        - _weights: Optional[ScoringWeights]
        - _search_plan: Optional[SearchPlan]
        - _executed_queries: List[ExecutedQuery]
        - _all_papers: List[PaperData]
        - _rejected_initial_filter: List[Tuple[PaperData, str]]
        - _evaluation_store: EvaluationStore
        - _evaluation_run: Optional[EvaluationRun]

    Methods expected:
        - _checkpoint(): Save checkpoint
        - _save_checkpoint_file(): Save checkpoint to file
        - _build_empty_result(): Build empty result
        - _save_scored_paper(): Save scored paper to database
        - _save_assessed_paper(): Save assessed paper to database
        - get_scored_papers(): Get scored papers from database
        - get_assessed_papers(): Get assessed papers from database
        - get_below_threshold_papers(): Get below threshold papers
    """

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
            raise ValueError(f"Invalid checkpoint file format: {e}") from e

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

        Raises:
            ValueError: If checkpoint data is invalid or missing required fields.
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
                # Use combined query to avoid N+1 pattern
                scored_papers, assessed_papers = self.get_scored_and_assessed_papers()
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

        Executes: Initial Filtering → Scoring → Quality Assessment → Report

        Args:
            interactive: Whether to run in interactive mode
            output_path: Optional path for saving results
            checkpoint_callback: Optional callback for checkpoint decisions
            output_dir: Optional directory for checkpoint file saving

        Returns:
            SystematicReviewResult with all papers and audit trail
        """
        from pathlib import Path
        from .filters import InitialFilter
        from .scorer import RelevanceScorer, CompositeScorer
        from .quality import QualityAssessor
        from .reporter import Reporter

        # Extract output directory if not provided
        if output_dir is None and output_path:
            output_dir = str(Path(output_path).expanduser().parent)

        criteria = self._criteria
        weights = self._weights

        # Initialize components
        initial_filter = InitialFilter(
            criteria=criteria,
            callback=self.callback,
        )

        scorer = RelevanceScorer(
            config=self.config,
            criteria=criteria,
            callback=self.callback,
            orchestrator=getattr(self, 'orchestrator', None),
        )

        quality_assessor = QualityAssessor(
            config=self.config,
            callback=self.callback,
            orchestrator=getattr(self, 'orchestrator', None),
        )

        composite_scorer = CompositeScorer(weights=weights)

        reporter = Reporter(
            documenter=self.documenter,
            criteria=criteria,
            weights=weights,
        )

        # Phase 3: Initial Filtering
        self.documenter.set_phase("initial_filtering")

        with self.documenter.log_step_with_timer(
            action=ACTION_INITIAL_FILTER,
            tool="InitialFilter",
            input_summary=f"Filtering {len(self._all_papers)} papers (resumed from checkpoint)",
            decision_rationale="Continuing from initial_results checkpoint",
        ) as timer:
            filter_result = initial_filter.filter_batch(self._all_papers)
            passed_filter = filter_result.passed
            rejected_filter = filter_result.rejected

            # Store rejected for comprehensive reporting
            self._rejected_initial_filter = rejected_filter

            timer.set_output(
                f"Passed: {len(passed_filter)}, Rejected: {len(rejected_filter)}"
            )
            timer.add_metrics({
                "passed_initial_filter": len(passed_filter),
                "rejected_initial_filter": len(rejected_filter),
            })

        total_considered = len(self._all_papers)
        passed_initial_filter = len(passed_filter)

        # Continue with scoring phase
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

        Args:
            interactive: Whether to run in interactive mode
            output_path: Optional path for saving results
            checkpoint_callback: Optional callback for checkpoint decisions

        Returns:
            SystematicReviewResult with all papers and audit trail
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
            orchestrator=getattr(self, 'orchestrator', None),
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

        Args:
            interactive: Whether to run in interactive mode
            output_path: Optional path for saving results
            checkpoint_callback: Optional callback for checkpoint decisions

        Returns:
            SystematicReviewResult with all papers and audit trail
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

        # Get counts from restored state - use combined query to avoid N+1 pattern
        scored_papers, assessed_papers = self.get_scored_and_assessed_papers()
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
            decision_rationale="Creating final systematic review output",
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
