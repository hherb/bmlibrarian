"""
Documenter Component for SystematicReviewAgent

Provides audit trail logging for systematic review workflows.
Records all process steps, checkpoints, and decisions for
reproducibility and transparency.

Features:
- Process step logging with timing and metrics
- Checkpoint creation and management for resumability
- Export to Markdown for human-readable audit trails
- JSON serialization for programmatic access
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .data_models import (
    ProcessStep,
    Checkpoint,
    SearchCriteria,
    ScoringWeights,
    ReviewStatistics,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

# Markdown formatting
MARKDOWN_HEADER_CHAR = "#"
MARKDOWN_BULLET = "-"
MARKDOWN_CODE_FENCE = "```"

# Checkpoint types
CHECKPOINT_SEARCH_STRATEGY = "search_strategy"
CHECKPOINT_INITIAL_RESULTS = "initial_results"
CHECKPOINT_SCORING_COMPLETE = "scoring_complete"
CHECKPOINT_QUALITY_ASSESSMENT = "quality_assessment"
CHECKPOINT_FINAL_REVIEW = "final_review"

# Step action names
ACTION_INITIALIZE = "initialize_review"
ACTION_GENERATE_SEARCH_PLAN = "generate_search_plan"
ACTION_EXECUTE_SEARCH = "execute_search"
ACTION_DEDUPLICATE = "deduplicate_results"
ACTION_INITIAL_FILTER = "initial_filter"
ACTION_SCORE_RELEVANCE = "score_relevance"
ACTION_EVALUATE_INCLUSION = "evaluate_inclusion"
ACTION_ASSESS_QUALITY = "assess_quality"
ACTION_CALCULATE_COMPOSITE = "calculate_composite_scores"
ACTION_RANK_PAPERS = "rank_papers"
ACTION_GENERATE_REPORT = "generate_report"


# =============================================================================
# Documenter Class
# =============================================================================

class Documenter:
    """
    Audit trail logging component for SystematicReviewAgent.

    Records all steps in the review process for reproducibility
    and transparency. Supports checkpoint creation for resumability.

    Attributes:
        steps: List of all recorded process steps
        checkpoints: List of saved checkpoints
        start_time: When the review started
        review_id: Unique identifier for this review session

    Example:
        >>> documenter = Documenter()
        >>> documenter.start_review()
        >>> step = documenter.log_step(
        ...     action="execute_search",
        ...     tool="SemanticQueryAgent",
        ...     input_summary="Query: cardiovascular disease",
        ...     output_summary="Found 150 papers",
        ...     decision_rationale="Using semantic search for initial discovery",
        ...     metrics={"papers_found": 150, "execution_time": 2.5}
        ... )
        >>> markdown = documenter.export_markdown()
    """

    def __init__(self, review_id: Optional[str] = None) -> None:
        """
        Initialize the Documenter.

        Args:
            review_id: Optional unique identifier for this review session.
                      If not provided, a UUID will be generated.
        """
        self.steps: List[ProcessStep] = []
        self.checkpoints: List[Checkpoint] = []
        self._step_counter: int = 0
        self._start_time: Optional[float] = None
        self._end_time: Optional[float] = None
        self.review_id: str = review_id or f"review_{uuid.uuid4().hex[:12]}"
        self._current_phase: str = "initialization"

        # Metrics tracking
        self._total_llm_calls: int = 0
        self._total_tokens: int = 0

        logger.debug(f"Documenter initialized with review_id: {self.review_id}")

    # =========================================================================
    # Review Lifecycle
    # =========================================================================

    def start_review(self) -> None:
        """
        Mark the start of a review session.

        Records the start timestamp for duration calculations.
        Should be called before any steps are logged.
        """
        self._start_time = time.time()
        self._current_phase = "search"
        logger.info(f"Review started: {self.review_id}")

    def end_review(self) -> float:
        """
        Mark the end of a review session.

        Returns:
            Total duration of the review in seconds
        """
        self._end_time = time.time()
        duration = self.get_duration()
        logger.info(f"Review ended: {self.review_id} (duration: {duration:.2f}s)")
        return duration

    def get_duration(self) -> float:
        """
        Get the total duration of the review.

        Returns:
            Duration in seconds, or elapsed time if review not ended
        """
        if self._start_time is None:
            return 0.0

        end = self._end_time or time.time()
        return end - self._start_time

    def set_phase(self, phase: str) -> None:
        """
        Set the current workflow phase.

        Args:
            phase: Name of the current phase (e.g., "search", "scoring")
        """
        self._current_phase = phase

    # =========================================================================
    # Step Logging
    # =========================================================================

    def log_step(
        self,
        action: str,
        tool: Optional[str],
        input_summary: str,
        output_summary: str,
        decision_rationale: str,
        metrics: Optional[Dict[str, Any]] = None,
        duration_seconds: Optional[float] = None,
        error: Optional[str] = None,
    ) -> ProcessStep:
        """
        Log a workflow step.

        Creates a new ProcessStep record with all provided information
        and adds it to the audit trail.

        Args:
            action: What action was performed (e.g., "execute_search")
            tool: Which tool/agent was invoked (e.g., "SemanticQueryAgent")
            input_summary: Summary of inputs to this step
            output_summary: Summary of outputs from this step
            decision_rationale: Why this action was taken
            metrics: Quantitative metrics (optional)
            duration_seconds: How long the step took (optional, auto-calculated if None)
            error: Error message if step failed (optional)

        Returns:
            The created ProcessStep record

        Example:
            >>> step = documenter.log_step(
            ...     action="score_relevance",
            ...     tool="DocumentScoringAgent",
            ...     input_summary="Scoring 150 papers",
            ...     output_summary="Scored all papers, 45 above threshold",
            ...     decision_rationale="Using relevance threshold 2.5",
            ...     metrics={"papers_scored": 150, "above_threshold": 45}
            ... )
        """
        self._step_counter += 1

        step = ProcessStep(
            step_number=self._step_counter,
            action=action,
            tool_used=tool,
            input_summary=input_summary,
            output_summary=output_summary,
            decision_rationale=decision_rationale,
            timestamp=datetime.now().isoformat(),
            duration_seconds=duration_seconds or 0.0,
            metrics=metrics or {},
            error=error,
        )

        self.steps.append(step)

        # Update LLM metrics if provided
        if metrics:
            self._total_llm_calls += metrics.get("llm_calls", 0)
            self._total_tokens += metrics.get("tokens_used", 0)

        # Log the step
        log_level = logging.ERROR if error else logging.INFO
        logger.log(
            log_level,
            f"Step {step.step_number}: {action} - {output_summary}"
        )

        return step

    def log_step_with_timer(
        self,
        action: str,
        tool: Optional[str],
        input_summary: str,
        decision_rationale: str,
    ) -> "StepTimer":
        """
        Create a context manager for timed step logging.

        Use this when you want to automatically measure the duration
        of a step. The step is logged when the context manager exits.

        Args:
            action: What action is being performed
            tool: Which tool/agent is being used
            input_summary: Summary of inputs
            decision_rationale: Why this action is taken

        Returns:
            StepTimer context manager

        Example:
            >>> with documenter.log_step_with_timer(
            ...     action="execute_search",
            ...     tool="SemanticQueryAgent",
            ...     input_summary="Query: cardiovascular disease",
            ...     decision_rationale="Semantic search for broad coverage"
            ... ) as timer:
            ...     results = agent.search(query)
            ...     timer.set_output(f"Found {len(results)} papers")
            ...     timer.add_metrics({"papers_found": len(results)})
        """
        return StepTimer(
            documenter=self,
            action=action,
            tool=tool,
            input_summary=input_summary,
            decision_rationale=decision_rationale,
        )

    # =========================================================================
    # Checkpoint Management
    # =========================================================================

    def log_checkpoint(
        self,
        checkpoint_type: str,
        phase: str,
        state_snapshot: Dict[str, Any],
        user_decision: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Checkpoint:
        """
        Log a checkpoint for workflow resumability.

        Checkpoints allow the review to be paused and resumed.
        They capture the complete state at key decision points.

        Args:
            checkpoint_type: Type of checkpoint (e.g., "search_strategy")
            phase: Current workflow phase
            state_snapshot: Serialized state at this point
            user_decision: User's decision at checkpoint (optional)
            notes: Any notes from user or system (optional)

        Returns:
            The created Checkpoint record

        Example:
            >>> checkpoint = documenter.log_checkpoint(
            ...     checkpoint_type="search_strategy",
            ...     phase="search",
            ...     state_snapshot={"plan": plan.to_dict()},
            ...     user_decision="approved"
            ... )
        """
        checkpoint = Checkpoint(
            checkpoint_id=f"cp_{uuid.uuid4().hex[:12]}",
            checkpoint_type=checkpoint_type,
            timestamp=datetime.now().isoformat(),
            phase=phase,
            state_snapshot=state_snapshot,
            user_decision=user_decision,
            notes=notes,
        )

        self.checkpoints.append(checkpoint)

        logger.info(
            f"Checkpoint created: {checkpoint_type} at phase {phase} "
            f"(id: {checkpoint.checkpoint_id})"
        )

        return checkpoint

    def get_checkpoint(self, checkpoint_id: str) -> Optional[Checkpoint]:
        """
        Retrieve a checkpoint by ID.

        Args:
            checkpoint_id: The unique checkpoint identifier

        Returns:
            The Checkpoint if found, None otherwise
        """
        for checkpoint in self.checkpoints:
            if checkpoint.checkpoint_id == checkpoint_id:
                return checkpoint
        return None

    def get_latest_checkpoint(
        self,
        checkpoint_type: Optional[str] = None
    ) -> Optional[Checkpoint]:
        """
        Get the most recent checkpoint.

        Args:
            checkpoint_type: Optional filter by checkpoint type

        Returns:
            The most recent Checkpoint matching criteria, or None
        """
        filtered = self.checkpoints
        if checkpoint_type:
            filtered = [c for c in filtered if c.checkpoint_type == checkpoint_type]

        return filtered[-1] if filtered else None

    def save_checkpoint_to_file(
        self,
        checkpoint: Checkpoint,
        directory: str,
    ) -> Path:
        """
        Save a checkpoint to a JSON file.

        Args:
            checkpoint: The Checkpoint to save
            directory: Directory to save the file in

        Returns:
            Path to the saved file
        """
        dir_path = Path(directory).expanduser()
        dir_path.mkdir(parents=True, exist_ok=True)

        filename = f"{self.review_id}_{checkpoint.checkpoint_id}.json"
        file_path = dir_path / filename

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(checkpoint.to_full_dict(), f, indent=2, ensure_ascii=False)

        logger.info(f"Checkpoint saved to: {file_path}")
        return file_path

    @staticmethod
    def load_checkpoint_from_file(file_path: str) -> Checkpoint:
        """
        Load a checkpoint from a JSON file.

        Args:
            file_path: Path to the checkpoint file

        Returns:
            Loaded Checkpoint instance
        """
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return Checkpoint.from_dict(data)

    # =========================================================================
    # Export Methods
    # =========================================================================

    def generate_process_log(self) -> List[Dict[str, Any]]:
        """
        Generate serializable process log.

        Returns:
            List of step dictionaries suitable for JSON serialization
        """
        return [step.to_dict() for step in self.steps]

    def generate_checkpoint_log(self) -> List[Dict[str, Any]]:
        """
        Generate serializable checkpoint log.

        Note: Does not include state_snapshot to reduce size.
        Use checkpoint.to_full_dict() if full state is needed.

        Returns:
            List of checkpoint summary dictionaries
        """
        return [checkpoint.to_dict() for checkpoint in self.checkpoints]

    def export_markdown(
        self,
        include_metrics: bool = True,
        include_checkpoints: bool = True,
    ) -> str:
        """
        Export audit trail as Markdown.

        Generates a human-readable Markdown document describing
        the entire review process.

        Args:
            include_metrics: Whether to include step metrics
            include_checkpoints: Whether to include checkpoint information

        Returns:
            Markdown string

        Example:
            >>> markdown = documenter.export_markdown()
            >>> with open("audit_trail.md", "w") as f:
            ...     f.write(markdown)
        """
        lines: List[str] = []

        # Header
        lines.append(f"# Systematic Review Audit Trail")
        lines.append(f"")
        lines.append(f"**Review ID:** {self.review_id}")
        lines.append(f"**Generated:** {datetime.now().isoformat()}")
        if self._start_time:
            start_dt = datetime.fromtimestamp(self._start_time)
            lines.append(f"**Started:** {start_dt.isoformat()}")
        if self._end_time:
            end_dt = datetime.fromtimestamp(self._end_time)
            lines.append(f"**Ended:** {end_dt.isoformat()}")
        lines.append(f"**Duration:** {self.get_duration():.2f} seconds")
        lines.append(f"**Total Steps:** {len(self.steps)}")
        lines.append(f"")

        # Summary statistics
        lines.append(f"## Summary Statistics")
        lines.append(f"")
        lines.append(f"- Total LLM calls: {self._total_llm_calls}")
        lines.append(f"- Total tokens used: {self._total_tokens}")
        lines.append(f"- Checkpoints created: {len(self.checkpoints)}")
        lines.append(f"")

        # Process steps
        lines.append(f"## Process Steps")
        lines.append(f"")

        for step in self.steps:
            status_icon = "✓" if step.success else "✗"
            lines.append(f"### Step {step.step_number}: {step.action} {status_icon}")
            lines.append(f"")
            lines.append(f"**Timestamp:** {step.timestamp}")
            if step.tool_used:
                lines.append(f"**Tool:** {step.tool_used}")
            lines.append(f"**Duration:** {step.duration_seconds:.2f}s")
            lines.append(f"")
            lines.append(f"**Input:** {step.input_summary}")
            lines.append(f"")
            lines.append(f"**Output:** {step.output_summary}")
            lines.append(f"")
            lines.append(f"**Rationale:** {step.decision_rationale}")
            lines.append(f"")

            if step.error:
                lines.append(f"**Error:** {step.error}")
                lines.append(f"")

            if include_metrics and step.metrics:
                lines.append(f"**Metrics:**")
                for key, value in step.metrics.items():
                    lines.append(f"- {key}: {value}")
                lines.append(f"")

            lines.append(f"---")
            lines.append(f"")

        # Checkpoints
        if include_checkpoints and self.checkpoints:
            lines.append(f"## Checkpoints")
            lines.append(f"")

            for checkpoint in self.checkpoints:
                lines.append(f"### {checkpoint.checkpoint_type}")
                lines.append(f"")
                lines.append(f"**ID:** {checkpoint.checkpoint_id}")
                lines.append(f"**Timestamp:** {checkpoint.timestamp}")
                lines.append(f"**Phase:** {checkpoint.phase}")
                if checkpoint.user_decision:
                    lines.append(f"**User Decision:** {checkpoint.user_decision}")
                if checkpoint.notes:
                    lines.append(f"**Notes:** {checkpoint.notes}")
                lines.append(f"")

        return "\n".join(lines)

    def export_json(self, indent: int = 2) -> str:
        """
        Export complete audit trail as JSON.

        Args:
            indent: JSON indentation level

        Returns:
            JSON string with all steps and checkpoints
        """
        data = {
            "review_id": self.review_id,
            "start_time": self._start_time,
            "end_time": self._end_time,
            "duration_seconds": self.get_duration(),
            "total_llm_calls": self._total_llm_calls,
            "total_tokens": self._total_tokens,
            "steps": self.generate_process_log(),
            "checkpoints": [c.to_full_dict() for c in self.checkpoints],
        }
        return json.dumps(data, indent=indent, ensure_ascii=False)

    def save_to_file(self, file_path: str, format: str = "json") -> None:
        """
        Save audit trail to file.

        Args:
            file_path: Output file path
            format: Output format ("json" or "markdown")
        """
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        if format == "json":
            content = self.export_json()
        elif format == "markdown":
            content = self.export_markdown()
        else:
            raise ValueError(f"Unknown format: {format}. Use 'json' or 'markdown'.")

        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

        logger.info(f"Audit trail saved to: {path}")

    # =========================================================================
    # Statistics
    # =========================================================================

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get summary statistics for the review process.

        Returns:
            Dictionary with statistics
        """
        successful_steps = sum(1 for s in self.steps if s.success)
        failed_steps = len(self.steps) - successful_steps

        return {
            "review_id": self.review_id,
            "total_steps": len(self.steps),
            "successful_steps": successful_steps,
            "failed_steps": failed_steps,
            "total_checkpoints": len(self.checkpoints),
            "duration_seconds": self.get_duration(),
            "total_llm_calls": self._total_llm_calls,
            "total_tokens": self._total_tokens,
        }

    def add_llm_metrics(self, calls: int, tokens: int) -> None:
        """
        Add LLM usage metrics.

        Args:
            calls: Number of LLM calls to add
            tokens: Number of tokens to add
        """
        self._total_llm_calls += calls
        self._total_tokens += tokens


# =============================================================================
# Step Timer Context Manager
# =============================================================================

class StepTimer:
    """
    Context manager for timed step logging.

    Automatically measures step duration and logs the step
    when the context manager exits.

    Attributes:
        documenter: Parent Documenter instance
        action: Action name
        tool: Tool/agent name
        input_summary: Input summary
        decision_rationale: Decision rationale
        output_summary: Output summary (set via set_output)
        metrics: Step metrics (set via add_metrics)
        error: Error message (set via set_error)
    """

    def __init__(
        self,
        documenter: Documenter,
        action: str,
        tool: Optional[str],
        input_summary: str,
        decision_rationale: str,
    ) -> None:
        """
        Initialize the StepTimer.

        Args:
            documenter: Parent Documenter instance
            action: Action being performed
            tool: Tool/agent being used
            input_summary: Summary of inputs
            decision_rationale: Why this action is taken
        """
        self.documenter = documenter
        self.action = action
        self.tool = tool
        self.input_summary = input_summary
        self.decision_rationale = decision_rationale

        self.output_summary: str = ""
        self.metrics: Dict[str, Any] = {}
        self.error: Optional[str] = None

        self._start_time: float = 0.0
        self._step: Optional[ProcessStep] = None

    def __enter__(self) -> "StepTimer":
        """Start timing."""
        self._start_time = time.time()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        """
        Stop timing and log the step.

        If an exception occurred, records it as the error.
        """
        duration = time.time() - self._start_time

        # Capture exception as error if one occurred
        if exc_val is not None:
            self.error = str(exc_val)
            if not self.output_summary:
                self.output_summary = f"Failed: {exc_val}"

        self._step = self.documenter.log_step(
            action=self.action,
            tool=self.tool,
            input_summary=self.input_summary,
            output_summary=self.output_summary or "Completed",
            decision_rationale=self.decision_rationale,
            metrics=self.metrics,
            duration_seconds=duration,
            error=self.error,
        )

        # Don't suppress exceptions
        return False

    def set_output(self, output_summary: str) -> None:
        """
        Set the output summary for this step.

        Args:
            output_summary: Summary of step outputs
        """
        self.output_summary = output_summary

    def add_metrics(self, metrics: Dict[str, Any]) -> None:
        """
        Add metrics to this step.

        Args:
            metrics: Dictionary of metrics to add
        """
        self.metrics.update(metrics)

    def set_error(self, error: str) -> None:
        """
        Set an error message for this step.

        Args:
            error: Error description
        """
        self.error = error

    @property
    def step(self) -> Optional[ProcessStep]:
        """Get the logged step (available after context manager exits)."""
        return self._step
