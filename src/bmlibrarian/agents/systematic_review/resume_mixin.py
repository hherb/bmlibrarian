"""
Checkpoint Resume Mixin for SystematicReviewAgent.

Resuming a review means: load a checkpoint file and validate all of it
(``parse_checkpoint``), fetch its papers and find its evaluation run, and
only then replace the agent's state with what the checkpoint describes
(criteria, weights, search plan, executed queries, papers, initial-filter
rejections and the evaluation run holding the saved scores and
assessments). The review then enters the shared pipeline (``pipeline.py``)
at the stage after the checkpoint; the phases themselves are not duplicated
here.

Because the file is validated, and the papers and evaluation run are looked
up, before the agent's state is touched, a resume rejected for bad or
missing data leaves the agent as it was.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import (
    Any, Callable, Dict, FrozenSet, List, Optional, Tuple, TypeVar, TYPE_CHECKING,
)

from .config import AGENT_VERSION
from .data_models import (
    SearchCriteria,
    ScoringWeights,
    SearchPlan,
    ExecutedQuery,
    PaperData,
    SystematicReviewResult,
    validate_scoring_weights,
    validate_search_criteria,
)
from .documenter import Documenter
from .exceptions import ResumeError
from .executor import build_paper_sources, collect_phase1_document_ids
from .pipeline import (
    RESUME_STAGE_BY_CHECKPOINT,
    STAGES_REQUIRING_SAVED_EVALUATIONS,
    ReviewPipelineMixin,
    ReviewRunOptions,
    ReviewStage,
)

if TYPE_CHECKING:
    from bmlibrarian.evaluations import EvaluationRun

logger = logging.getLogger(__name__)

# Phase recorded for a resumed review when the checkpoint names none
DEFAULT_RESUMED_PHASE = "initial_filtering"

# Reason recorded for a rejected paper when the checkpoint names none
UNKNOWN_REJECTION_REASON = "Unknown reason"

# Checkpoint validators raise ValueError for wrongly typed data too (ruff
# TRY004 is silenced on them): callers treat every ValueError as "invalid
# checkpoint file", and a TypeError would escape that handling.

# Errors a checkpoint part's from_dict raises on malformed data
_MALFORMED_DATA_ERRORS = (KeyError, TypeError, ValueError, AttributeError)

_T = TypeVar("_T")


# =============================================================================
# Data types
# =============================================================================

@dataclass(frozen=True)
class ResumeCheckpoint:
    """
    A validated checkpoint file: everything a resume restores.

    Built only by ``parse_checkpoint``, which checks that the data needed
    by the resume stage is present.

    Attributes:
        checkpoint_type: Checkpoint type constant.
        stage: The pipeline stage the resume starts at.
        review_id: The original review's ID, if recorded.
        criteria: The review's search criteria.
        weights: The review's scoring weights; None to use the configured ones.
        search_plan: The search plan; always set when ``stage`` is the search.
        executed_queries: Queries already executed, in execution order.
        paper_ids: Document IDs of every paper the search found.
        rejected: (document ID, reason) of papers the initial filter rejected.
        evaluation_run_id: The evaluation run holding saved evaluations.
        semantic_baseline_ids: Phase-1 document IDs of a phased search, or
            None for checkpoints written before they were recorded.
        documenter_phase: The audit-trail phase at the checkpoint, if recorded.
    """

    checkpoint_type: str
    stage: ReviewStage
    review_id: Optional[str]
    criteria: SearchCriteria
    weights: Optional[ScoringWeights]
    search_plan: Optional[SearchPlan]
    executed_queries: Tuple[ExecutedQuery, ...]
    paper_ids: Tuple[int, ...]
    rejected: Tuple[Tuple[int, str], ...]
    evaluation_run_id: Optional[int]
    semantic_baseline_ids: Optional[FrozenSet[int]]
    documenter_phase: Optional[str]


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
        raise ValueError("Invalid checkpoint file: 'evaluation_run_id' must be an integer")  # noqa: TRY004
    return raw


def parse_optional_text(raw: Any, field_name: str) -> Optional[str]:
    """
    Validate an optional text field read from a checkpoint file.

    Args:
        raw: The value read from the file.
        field_name: Field name, for the error message.

    Returns:
        The text, or None if absent or empty.

    Raises:
        ValueError: If the value is present but not a string.
    """
    if raw is None or raw == "":
        return None
    if not isinstance(raw, str):
        raise ValueError(f"Invalid checkpoint file: '{field_name}' must be a string")  # noqa: TRY004
    return raw


def parse_rejected_entries(raw: Any) -> Tuple[Tuple[int, str], ...]:
    """
    Validate the ``rejected_initial_filter`` list of a checkpoint file.

    Args:
        raw: The value read from the file.

    Returns:
        (document ID, reason) pairs, in file order.

    Raises:
        ValueError: If the value or one of its entries is malformed.
    """
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ValueError("Invalid checkpoint file: 'rejected_initial_filter' must be a list")  # noqa: TRY004
    entries: List[Tuple[int, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("Invalid checkpoint file: malformed 'rejected_initial_filter' entry")  # noqa: TRY004
        doc_id = parse_document_ids([item.get("document_id")], "rejected_initial_filter")[0]
        reason = item.get("reason")
        entries.append((doc_id, str(reason) if reason else UNKNOWN_REJECTION_REASON))
    return tuple(entries)


def _parse_part(field_name: str, parse: Callable[[Any], _T], raw: Any) -> _T:
    """
    Parse one structured part of a checkpoint, reporting bad data as ValueError.

    Args:
        field_name: Field name, for the error message.
        parse: The part's parser (typically a ``from_dict``).
        raw: The value read from the file.

    Returns:
        The parsed value.

    Raises:
        ValueError: If the parser rejects the data.
    """
    try:
        return parse(raw)
    except _MALFORMED_DATA_ERRORS as e:
        raise ValueError(
            f"Invalid checkpoint file: malformed '{field_name}' ({type(e).__name__}: {e})"
        ) from e


def parse_checkpoint(data: Dict[str, Any]) -> ResumeCheckpoint:
    """
    Validate checkpoint data and check it can be resumed from.

    Args:
        data: Checkpoint data from ``load_checkpoint_file``.

    Returns:
        The validated checkpoint.

    Raises:
        ValueError: If any field is missing or malformed, or data the resume
            stage needs is absent.
    """
    checkpoint_type = data["checkpoint_type"]
    stage = RESUME_STAGE_BY_CHECKPOINT[checkpoint_type]

    criteria_data = data.get("criteria")
    if not isinstance(criteria_data, dict) or not criteria_data:
        raise ValueError(
            f"Checkpoint missing required 'criteria' data. Checkpoint type: {checkpoint_type}"
        )
    criteria = _parse_part("criteria", SearchCriteria.from_dict, criteria_data)
    criteria_errors = _parse_part("criteria", validate_search_criteria, criteria)
    if criteria_errors:
        raise ValueError(
            f"Invalid checkpoint file: invalid 'criteria' ({'; '.join(criteria_errors)})"
        )

    weights: Optional[ScoringWeights] = None
    weights_data = data.get("weights")
    if weights_data:
        weights = _parse_part("weights", ScoringWeights.from_dict, weights_data)
        weight_errors = _parse_part("weights", validate_scoring_weights, weights)
        if weight_errors:
            raise ValueError(
                f"Invalid checkpoint file: invalid 'weights' ({'; '.join(weight_errors)})"
            )

    search_plan_data = data.get("search_plan")
    search_plan = (
        _parse_part("search_plan", SearchPlan.from_dict, search_plan_data)
        if search_plan_data else None
    )
    if stage == ReviewStage.EXECUTE_SEARCH and search_plan is None:
        raise ValueError("Checkpoint has no 'search_plan'; cannot resume search execution")

    executed_data = data.get("executed_queries") or []
    if not isinstance(executed_data, list):
        raise ValueError("Invalid checkpoint file: 'executed_queries' must be a list")  # noqa: TRY004
    executed_queries = tuple(
        _parse_part("executed_queries", ExecutedQuery.from_dict, q) for q in executed_data
    )

    baseline_raw = data.get("semantic_baseline_ids")
    semantic_baseline_ids = (
        frozenset(parse_document_ids(baseline_raw, "semantic_baseline_ids"))
        if baseline_raw is not None else None
    )

    return ResumeCheckpoint(
        checkpoint_type=checkpoint_type,
        stage=stage,
        review_id=parse_optional_text(data.get("review_id"), "review_id"),
        criteria=criteria,
        weights=weights,
        search_plan=search_plan,
        executed_queries=executed_queries,
        paper_ids=tuple(parse_document_ids(data.get("paper_document_ids"), "paper_document_ids")),
        rejected=parse_rejected_entries(data.get("rejected_initial_filter")),
        evaluation_run_id=parse_evaluation_run_id(data.get("evaluation_run_id")),
        semantic_baseline_ids=semantic_baseline_ids,
        documenter_phase=parse_optional_text(data.get("documenter_phase"), "documenter_phase"),
    )


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
        raise ValueError("Invalid checkpoint file: expected a JSON object")  # noqa: TRY004

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

        Setup (reading the file, fetching papers, finding the evaluation run)
        happens before the agent's state is replaced, so a resume rejected
        for bad or missing data leaves the agent unchanged. Setup errors
        propagate as they are, without touching any run status; only errors
        once the pipeline runs are recorded on the run.

        Args:
            checkpoint_path: Path to the checkpoint JSON file
            interactive: If True, pause at subsequent checkpoints for approval
            output_path: Optional path to save results JSON
            checkpoint_callback: Optional callback for checkpoint decisions

        Returns:
            SystematicReviewResult with all papers and audit trail, or an
            empty result carrying ``abort_reason`` if a checkpoint is rejected

        Raises:
            FileNotFoundError: If checkpoint file doesn't exist
            ValueError: If checkpoint file is invalid or incompatible
            ResumeError: If the checkpoint's papers or evaluation run cannot
                be restored
            RuntimeError: If the database cannot be read (raised by the
                evaluation store)
            SystematicReviewError: If the resumed review fails
            KeyboardInterrupt: If the user interrupts the resumed review

        Example:
            >>> result = agent.run_review_from_checkpoint(
            ...     checkpoint_path="reviews/review_abc123_initial_results.json",
            ...     interactive=True
            ... )
        """
        checkpoint = parse_checkpoint(load_checkpoint_file(checkpoint_path))
        logger.info(
            f"Resuming review {checkpoint.review_id} from checkpoint: {checkpoint.checkpoint_type}"
        )

        # Everything that can fail runs before any state is replaced.
        papers, missing_ids = self._fetch_papers(list(checkpoint.paper_ids))
        if checkpoint.paper_ids and not papers:
            raise ResumeError(
                f"None of the {len(checkpoint.paper_ids)} papers in the checkpoint could be "
                "restored from the database. Is the application connected to the database "
                "the review was run against?"
            )
        rejected, missing_rejected_ids = self._restore_rejected_papers(checkpoint.rejected, papers)
        run = self._find_evaluation_run(checkpoint)

        self._apply_checkpoint(checkpoint, papers, rejected)
        self._attach_evaluation_run(run)

        papers_not_restored = len(missing_ids) + len(missing_rejected_ids)
        if papers_not_restored:
            self._warn(
                f"{papers_not_restored} papers in the checkpoint could not be restored from "
                f"the database and are left out of the review "
                f"(document IDs: {sorted(missing_ids + missing_rejected_ids)})."
            )

        self.documenter.log_step(
            action="resume_from_checkpoint",
            tool=None,
            input_summary=f"Resuming from {checkpoint.checkpoint_type} checkpoint",
            output_summary=f"Restored {len(self._all_papers)} papers, continuing review",
            decision_rationale="User requested resume from saved checkpoint",
            metrics={
                "checkpoint_type": checkpoint.checkpoint_type,
                "papers_restored": len(self._all_papers),
                "papers_not_restored": papers_not_restored,
                "original_review_id": checkpoint.review_id,
                "evaluation_run_id": self._active_run().run_id,
            },
        )

        options = ReviewRunOptions(
            interactive=interactive,
            output_path=output_path,
            checkpoint_callback=checkpoint_callback,
        )

        def resume_body() -> SystematicReviewResult:
            """Report restored progress, then run the rest of the pipeline."""
            self._emit_restored_progress(checkpoint)
            return self._execute_pipeline(checkpoint.stage, options)

        return self._run_guarded(resume_body)

    def _apply_checkpoint(
        self,
        checkpoint: ResumeCheckpoint,
        papers: List[PaperData],
        rejected: List[Tuple[PaperData, str]],
    ) -> None:
        """
        Replace all review state with the checkpoint's.

        Nothing from a previous review on this agent instance survives: the
        evaluation run is cleared (``_attach_evaluation_run`` sets the
        checkpoint's) and a new documenter is started.

        Args:
            checkpoint: The validated checkpoint.
            papers: The checkpoint's papers, fetched from the database.
            rejected: The papers the initial filter rejected, with reasons.
        """
        self._criteria = checkpoint.criteria
        self._weights = checkpoint.weights or self.config.scoring_weights
        self._search_plan = checkpoint.search_plan
        self._executed_queries = list(checkpoint.executed_queries)
        # Provenance is derived from the executed queries exactly as the
        # executor built it.
        self._paper_sources = build_paper_sources(self._executed_queries)
        if checkpoint.semantic_baseline_ids is not None:
            self._semantic_baseline_ids = set(checkpoint.semantic_baseline_ids)
        else:
            # Checkpoints written before the baseline was recorded: derive it
            # as the phased executor would have.
            self._semantic_baseline_ids = (
                collect_phase1_document_ids(self._executed_queries)
                if self.config.use_phased_search else set()
            )
        self._all_papers = papers
        self._rejected_initial_filter = rejected
        self._query_feedback = None
        self._evaluation_run = None

        self.documenter = Documenter(review_id=checkpoint.review_id)
        self.documenter.start_review()
        self.documenter.set_phase(checkpoint.documenter_phase or DEFAULT_RESUMED_PHASE)
        logger.info(
            f"Restored {len(papers)} papers and {len(rejected)} papers rejected in initial filter"
        )

    def _restore_rejected_papers(
        self,
        entries: Tuple[Tuple[int, str], ...],
        papers: List[PaperData],
    ) -> Tuple[List[Tuple[PaperData, str]], List[int]]:
        """
        Restore the papers rejected by the initial filter, with reasons.

        Args:
            entries: The checkpoint's (document ID, reason) pairs.
            papers: Papers already fetched for the checkpoint.

        Returns:
            ((paper, reason) for every rejected paper found,
            IDs of rejected papers that could not be restored)
        """
        paper_lookup = {p.document_id: p for p in papers}
        missing_ids = [doc_id for doc_id, _ in entries if doc_id not in paper_lookup]
        if missing_ids:
            fetched, _ = self._fetch_papers(missing_ids)
            for paper in fetched:
                paper_lookup[paper.document_id] = paper

        rejected = [
            (paper_lookup[doc_id], reason) for doc_id, reason in entries if doc_id in paper_lookup
        ]
        not_restored = [doc_id for doc_id, _ in entries if doc_id not in paper_lookup]
        return rejected, not_restored

    def _fetch_papers(self, document_ids: List[int]) -> Tuple[List[PaperData], List[int]]:
        """
        Fetch papers by document ID.

        Args:
            document_ids: Document IDs to fetch.

        Returns:
            (the papers found and parsed, the IDs that were not)
        """
        if not document_ids:
            return [], []
        from bmlibrarian.database import fetch_documents_by_ids

        papers: List[PaperData] = []
        for doc in fetch_documents_by_ids(set(document_ids)):
            try:
                papers.append(PaperData.from_database_row(doc))
            except _MALFORMED_DATA_ERRORS as e:
                logger.warning(f"Failed to restore paper {doc.get('id')}: {e}")

        found = {p.document_id for p in papers}
        return papers, [doc_id for doc_id in document_ids if doc_id not in found]

    def _find_evaluation_run(self, checkpoint: ResumeCheckpoint) -> Optional["EvaluationRun"]:
        """
        Find the evaluation run holding the checkpoint's saved evaluations.

        A checkpoint without a run ID can only be resumed from a stage that
        does not need saved evaluations; a new run is started for it.

        Args:
            checkpoint: The validated checkpoint.

        Returns:
            The run, or None if a new run must be started.

        Raises:
            ResumeError: If the run is needed but missing, cannot be found,
                or belongs to a different research question.
        """
        run_id = checkpoint.evaluation_run_id
        if run_id is None:
            if checkpoint.stage in STAGES_REQUIRING_SAVED_EVALUATIONS:
                raise ResumeError(
                    "The checkpoint has no evaluation run ID, so its scored and "
                    "assessed papers cannot be restored. Resume from an earlier "
                    "checkpoint (search strategy or initial results) instead."
                )
            return None

        run = self._evaluation_store.get_run(run_id)
        if run is None:
            raise ResumeError(
                f"Evaluation run {run_id} referenced by the checkpoint was not found. "
                "Is the application connected to the database the review was run against?"
            )
        if (
            run.research_question_text is not None
            and run.research_question_text != checkpoint.criteria.research_question
        ):
            raise ResumeError(
                f"Evaluation run {run_id} belongs to a different research question "
                f"({run.research_question_text!r}); the checkpoint does not match it."
            )
        return run

    def _attach_evaluation_run(self, run: Optional["EvaluationRun"]) -> None:
        """
        Reopen the checkpoint's evaluation run, or start a new one.

        Args:
            run: The run found by ``_find_evaluation_run``, or None.

        Raises:
            ResumeError: If the run disappeared before it could be reopened.
        """
        if run is None:
            self._warn(
                "The checkpoint has no evaluation run ID: a new evaluation run is "
                "started, so scores saved before the interruption are not reused."
            )
            self._start_evaluation_run()
            return

        reopened = self._evaluation_store.reopen_run(run.run_id)
        if reopened is None:
            raise ResumeError(
                f"Evaluation run {run.run_id} was deleted before it could be reopened."
            )
        self._evaluation_run = reopened
        logger.info(f"Restored evaluation run {run.run_id} (was {run.status})")

    def _emit_restored_progress(self, checkpoint: ResumeCheckpoint) -> None:
        """
        Report the progress completed before the checkpoint to the UI.

        Args:
            checkpoint: The checkpoint being resumed from.
        """
        if not self.callback:
            return

        total_papers = len(self._all_papers)
        rejected_initial = len(self._rejected_initial_filter)
        passed_initial = total_papers - rejected_initial

        scored_papers, assessed_papers = self.get_scored_and_assessed_papers()
        scored_count = len(scored_papers)
        assessed_count = len(assessed_papers)

        self.callback(
            "checkpoint_restored",
            f"Resumed from {checkpoint.checkpoint_type} | {total_papers} papers found"
        )

        start = checkpoint.stage
        if start > ReviewStage.EXECUTE_SEARCH:
            self.callback(
                "execution_completed",
                f"[RESTORED] Search completed: {total_papers} papers found"
            )

        if start > ReviewStage.SCORE_RELEVANCE:
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

        if start > ReviewStage.ASSESS_QUALITY and assessed_count > 0:
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
