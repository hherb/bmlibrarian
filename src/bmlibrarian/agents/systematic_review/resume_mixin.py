"""
Checkpoint Resume Mixin for SystematicReviewAgent.

Resuming a review means: load and validate a checkpoint file, restore the
agent state it describes (criteria, weights, search plan, executed queries,
papers, initial-filter rejections and the evaluation run holding the saved
scores and assessments), then enter the shared review pipeline
(``pipeline.py``) at the stage after the checkpoint. The phases themselves
are not duplicated here.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from .data_models import (
    SearchCriteria,
    ScoringWeights,
    SearchPlan,
    ExecutedQuery,
    PaperData,
    SystematicReviewResult,
)
from .documenter import (
    Documenter,
    CHECKPOINT_INITIAL_RESULTS,
    CHECKPOINT_SCORING_COMPLETE,
    CHECKPOINT_QUALITY_ASSESSMENT,
)
from .exceptions import ResumeError
from .executor import build_paper_sources, collect_phase1_document_ids
from .pipeline import (
    RESUME_STAGE_BY_CHECKPOINT,
    STAGES_REQUIRING_SAVED_EVALUATIONS,
    ReviewPipelineMixin,
    ReviewRunOptions,
    ReviewStage,
)

logger = logging.getLogger(__name__)

# Agent version - should match agent.py AGENT_VERSION
AGENT_VERSION = "1.0.0"


# =============================================================================
# Pure helpers
# =============================================================================

def parse_document_ids(raw: Any, field_name: str) -> List[int]:
    """
    Validate a list of document IDs read from a checkpoint file.

    Args:
        raw: The value read from the file.
        field_name: Field name, for the error message.

    Returns:
        The document IDs, in file order.

    Raises:
        ValueError: If the value is not a list of integers.
    """
    if raw is None:
        return []
    if not isinstance(raw, list) or not all(
        isinstance(doc_id, int) and not isinstance(doc_id, bool) for doc_id in raw
    ):
        raise ValueError(f"Invalid checkpoint file: '{field_name}' must be a list of integers")
    return raw


def parse_evaluation_run_id(raw: Any) -> Optional[int]:
    """
    Validate the evaluation run ID read from a checkpoint file.

    Args:
        raw: The value read from the file.

    Returns:
        The run ID, or None if the checkpoint has none.

    Raises:
        ValueError: If the value is present but not an integer.
    """
    if raw is None:
        return None
    if not isinstance(raw, int) or isinstance(raw, bool):
        raise ValueError("Invalid checkpoint file: 'evaluation_run_id' must be an integer")
    return raw


def load_checkpoint_file(checkpoint_path: str) -> Dict[str, Any]:
    """
    Load a checkpoint file and check it is a resumable checkpoint.

    Args:
        checkpoint_path: Path to the checkpoint JSON file.

    Returns:
        The checkpoint data.

    Raises:
        FileNotFoundError: If the file doesn't exist.
        ValueError: If the file is not a valid, resumable checkpoint.
    """
    checkpoint_file = Path(checkpoint_path).expanduser()
    if not checkpoint_file.exists():
        raise FileNotFoundError(f"Checkpoint file not found: {checkpoint_path}")

    try:
        with open(checkpoint_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid checkpoint file format: {e}") from e

    if not isinstance(data, dict):
        raise ValueError("Invalid checkpoint file: expected a JSON object")

    checkpoint_type = data.get("checkpoint_type")
    if not checkpoint_type:
        if "metadata" in data and "search_strategy" in data:
            raise ValueError(
                "This appears to be a final report file, not a checkpoint file. "
                "Please select a checkpoint file (e.g., *_search_strategy.json "
                "or *_initial_results.json) to resume from."
            )
        raise ValueError(
            "Invalid checkpoint file: missing 'checkpoint_type' field. "
            "Please select a valid checkpoint file."
        )
    if checkpoint_type not in RESUME_STAGE_BY_CHECKPOINT:
        raise ValueError(f"Unknown checkpoint type: {checkpoint_type}")

    version = data.get("version", "unknown")
    if version != AGENT_VERSION:
        logger.warning(
            f"Checkpoint version mismatch: {version} vs {AGENT_VERSION}. "
            "Attempting resume anyway."
        )
    return data


# =============================================================================
# Mixin
# =============================================================================

class CheckpointResumeMixin(ReviewPipelineMixin):
    """
    Checkpoint resume for SystematicReviewAgent.

    Builds on the review pipeline; state is declared on ReviewHost.
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

        Restores the state saved in the checkpoint file and continues the
        review from the phase after it. Papers already scored or assessed in
        the original evaluation run are reused, not re-evaluated.

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
            ResumeError: If the saved evaluation run cannot be restored
            SystematicReviewError: If the resumed review fails

        Example:
            >>> result = agent.run_review_from_checkpoint(
            ...     checkpoint_path="reviews/review_abc123_initial_results.json",
            ...     interactive=True
            ... )
        """
        checkpoint_data = load_checkpoint_file(checkpoint_path)
        checkpoint_type = checkpoint_data["checkpoint_type"]
        start = RESUME_STAGE_BY_CHECKPOINT[checkpoint_type]
        review_id = checkpoint_data.get("review_id")

        logger.info(f"Resuming review {review_id} from checkpoint: {checkpoint_type}")

        self._restore_state_from_checkpoint(checkpoint_data, start)
        self._restore_evaluation_run(
            parse_evaluation_run_id(checkpoint_data.get("evaluation_run_id")), start
        )

        self.documenter = Documenter(review_id=review_id)
        self.documenter.start_review()
        self.documenter._current_phase = checkpoint_data.get("documenter_phase", "initial_filtering")
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
                "evaluation_run_id": (
                    self._evaluation_run.run_id if self._evaluation_run else None
                ),
            },
        )

        self._emit_restored_progress(checkpoint_type)

        options = ReviewRunOptions(
            interactive=interactive,
            output_path=output_path,
            checkpoint_callback=checkpoint_callback,
        )
        return self._run_guarded(lambda: self._execute_pipeline(start, options))

    def _restore_state_from_checkpoint(
        self,
        checkpoint_data: Dict[str, Any],
        start: ReviewStage,
    ) -> None:
        """
        Restore review state (everything except the evaluation run).

        All state is replaced, so nothing from a previous review on this
        agent instance survives.

        Args:
            checkpoint_data: Validated checkpoint data.
            start: The stage the resume will start at.

        Raises:
            ValueError: If required data is missing or malformed.
        """
        checkpoint_type = checkpoint_data["checkpoint_type"]

        criteria_data = checkpoint_data.get("criteria")
        if not criteria_data:
            raise ValueError(
                f"Checkpoint missing required 'criteria' data. "
                f"Checkpoint type: {checkpoint_type}"
            )
        self._criteria = SearchCriteria.from_dict(criteria_data)

        weights_data = checkpoint_data.get("weights")
        self._weights = (
            ScoringWeights.from_dict(weights_data) if weights_data else self.config.scoring_weights
        )

        search_plan_data = checkpoint_data.get("search_plan")
        self._search_plan = SearchPlan.from_dict(search_plan_data) if search_plan_data else None
        if start == ReviewStage.EXECUTE_SEARCH and self._search_plan is None:
            raise ValueError(
                "Checkpoint has no 'search_plan'; cannot resume search execution"
            )

        self._executed_queries = [
            ExecutedQuery.from_dict(q) for q in checkpoint_data.get("executed_queries") or []
        ]
        # Provenance and the phased-search baseline are derived from the
        # executed queries exactly as the executor built them.
        self._paper_sources = build_paper_sources(self._executed_queries)
        self._semantic_baseline_ids = (
            collect_phase1_document_ids(self._executed_queries)
            if self.config.use_phased_search else set()
        )

        paper_ids = parse_document_ids(
            checkpoint_data.get("paper_document_ids"), "paper_document_ids"
        )
        self._all_papers = self._fetch_papers(paper_ids)
        if len(self._all_papers) < len(paper_ids):
            logger.warning(
                f"{len(paper_ids) - len(self._all_papers)} of {len(paper_ids)} papers "
                "could not be restored from the database"
            )
        logger.info(f"Restored {len(self._all_papers)} papers")

        self._rejected_initial_filter = self._restore_rejected_papers(
            checkpoint_data.get("rejected_initial_filter") or []
        )
        self._query_feedback = None

    def _restore_rejected_papers(
        self,
        rejected_data: List[Any],
    ) -> List[Tuple[PaperData, str]]:
        """
        Restore the papers rejected by the initial filter, with reasons.

        Args:
            rejected_data: The checkpoint's ``rejected_initial_filter`` list.

        Returns:
            (paper, reason) pairs for every rejected paper found.

        Raises:
            ValueError: If an entry is malformed.
        """
        entries: List[Tuple[int, str]] = []
        for item in rejected_data:
            if not isinstance(item, dict):
                raise ValueError("Invalid checkpoint file: malformed 'rejected_initial_filter' entry")
            doc_id = parse_document_ids([item.get("document_id")], "rejected_initial_filter")[0]
            entries.append((doc_id, str(item.get("reason") or "Unknown reason")))

        paper_lookup = {p.document_id: p for p in self._all_papers}
        missing_ids = [doc_id for doc_id, _ in entries if doc_id not in paper_lookup]
        if missing_ids:
            for paper in self._fetch_papers(missing_ids):
                paper_lookup[paper.document_id] = paper

        rejected = [
            (paper_lookup[doc_id], reason) for doc_id, reason in entries if doc_id in paper_lookup
        ]
        if len(rejected) < len(entries):
            logger.warning(
                f"{len(entries) - len(rejected)} rejected papers could not be restored"
            )
        logger.info(f"Restored {len(rejected)} papers rejected in initial filter")
        return rejected

    def _fetch_papers(self, document_ids: List[int]) -> List[PaperData]:
        """
        Fetch papers by document ID, skipping rows that cannot be parsed.

        Args:
            document_ids: Document IDs to fetch.

        Returns:
            The papers that were found and parsed.
        """
        if not document_ids:
            return []
        from bmlibrarian.database import fetch_documents_by_ids

        papers: List[PaperData] = []
        for doc in fetch_documents_by_ids(set(document_ids)):
            try:
                papers.append(PaperData.from_database_row(doc))
            except Exception as e:
                logger.warning(f"Failed to restore paper {doc.get('id')}: {e}")
        return papers

    def _restore_evaluation_run(
        self,
        run_id: Optional[int],
        start: ReviewStage,
    ) -> None:
        """
        Reattach the evaluation run holding the review's saved evaluations.

        A checkpoint without a run ID can only be resumed from a stage that
        does not need saved evaluations; a new run is started for it.

        Args:
            run_id: The checkpoint's evaluation run ID, or None.
            start: The stage the resume will start at.

        Raises:
            ResumeError: If the run is needed but missing, cannot be found,
                or belongs to a different research question.
        """
        self._evaluation_run = None

        if run_id is None:
            if start in STAGES_REQUIRING_SAVED_EVALUATIONS:
                raise ResumeError(
                    "The checkpoint has no evaluation run ID, so its scored and "
                    "assessed papers cannot be restored. Resume from an earlier "
                    "checkpoint (search strategy or initial results) instead."
                )
            logger.warning("Checkpoint has no evaluation run ID; starting a new run")
            self._start_evaluation_run()
            return

        run = self._evaluation_store.get_run(run_id)
        if run is None:
            raise ResumeError(
                f"Evaluation run {run_id} referenced by the checkpoint was not found. "
                "Is the application connected to the database the review was run against?"
            )
        if (
            run.research_question_text is not None
            and run.research_question_text != self._active_criteria().research_question
        ):
            raise ResumeError(
                f"Evaluation run {run_id} belongs to a different research question "
                f"({run.research_question_text!r}); the checkpoint does not match it."
            )

        self._evaluation_store.reopen_run(run_id)
        self._evaluation_run = run
        logger.info(f"Restored evaluation run {run_id} (was {run.status})")

    def _emit_restored_progress(self, checkpoint_type: str) -> None:
        """
        Report the progress completed before the checkpoint to the UI.

        Args:
            checkpoint_type: Type of checkpoint being resumed from.
        """
        if not self.callback:
            return

        total_papers = len(self._all_papers)
        rejected_initial = len(self._rejected_initial_filter)
        passed_initial = total_papers - rejected_initial

        scored_count = 0
        assessed_count = 0
        if self._evaluation_run:
            scored_papers, assessed_papers = self.get_scored_and_assessed_papers()
            scored_count = len(scored_papers)
            assessed_count = len(assessed_papers)

        self.callback(
            "checkpoint_restored",
            f"Resumed from {checkpoint_type} | {total_papers} papers found"
        )

        if checkpoint_type in (
            CHECKPOINT_INITIAL_RESULTS,
            CHECKPOINT_SCORING_COMPLETE,
            CHECKPOINT_QUALITY_ASSESSMENT,
        ):
            self.callback(
                "execution_completed",
                f"[RESTORED] Search completed: {total_papers} papers found"
            )

        if checkpoint_type in (CHECKPOINT_SCORING_COMPLETE, CHECKPOINT_QUALITY_ASSESSMENT):
            self.callback(
                "filtering_complete",
                f"[RESTORED] Initial filter: {passed_initial} passed, {rejected_initial} rejected"
            )
            if scored_count > 0:
                self.callback(
                    "scoring_complete",
                    f"[RESTORED] Relevance scoring: {scored_count} papers scored"
                )
                self.callback(
                    "scoring_progress",
                    f"[RESTORED] {scored_count}/{passed_initial}"
                )

        if checkpoint_type == CHECKPOINT_QUALITY_ASSESSMENT and assessed_count > 0:
            self.callback(
                "quality_complete",
                f"[RESTORED] Quality assessment: {assessed_count} papers assessed"
            )
            self.callback(
                "quality_progress",
                f"[RESTORED] {assessed_count}/{scored_count}"
            )

        logger.info(
            f"Restored progress: {total_papers} found, {passed_initial} passed initial filter, "
            f"{scored_count} scored, {assessed_count} assessed"
        )
