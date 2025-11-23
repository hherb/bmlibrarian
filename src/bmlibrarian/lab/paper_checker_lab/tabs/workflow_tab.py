"""
PaperChecker Laboratory - Workflow Tab

Tab widget for displaying workflow progress visualization.
"""

import logging
from typing import Optional, List, Dict, Any

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QGroupBox, QScrollArea, QProgressBar,
    QSizePolicy, QFrame,
)
from PySide6.QtCore import Signal, Qt

from bmlibrarian.gui.qt.resources.styles.dpi_scale import get_font_scale
from bmlibrarian.gui.qt.resources.styles.stylesheet_generator import get_stylesheet_generator

from ..constants import (
    WORKFLOW_STEPS, WORKFLOW_STEP_COUNT,
    COLOR_PRIMARY, COLOR_SUCCESS, COLOR_ERROR, COLOR_GREY_600,
    SEARCH_STRATEGY_COLORS,
)
from ..widgets import WorkflowStepCard, StatusSpinnerWidget
from ..utils import get_workflow_step_index, calculate_workflow_progress


logger = logging.getLogger(__name__)


class WorkflowTab(QWidget):
    """
    Tab widget for workflow progress visualization.

    Displays the 11 workflow steps with real-time status updates
    and an overall progress bar.

    Signals:
        abort_requested: Emitted when user requests to abort processing.
    """

    abort_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """
        Initialize workflow tab.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)

        self.scale = get_font_scale()
        self.styles = get_stylesheet_generator()
        self._step_cards: List[WorkflowStepCard] = []
        self._current_step_index = -1

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Setup tab user interface."""
        layout = QVBoxLayout(self)
        layout.setSpacing(self.scale['spacing_medium'])
        layout.setContentsMargins(
            self.scale['padding_large'],
            self.scale['padding_large'],
            self.scale['padding_large'],
            self.scale['padding_large']
        )

        # Header section
        header_layout = QHBoxLayout()

        title_label = QLabel("Workflow Progress")
        title_font = title_label.font()
        title_font.setBold(True)
        title_font.setPointSize(title_font.pointSize() + 2)
        title_label.setFont(title_font)
        header_layout.addWidget(title_label)

        header_layout.addStretch()

        self._abort_btn = QPushButton("Abort")
        self._abort_btn.setToolTip("Cancel the current check")
        self._abort_btn.clicked.connect(self._on_abort_clicked)
        self._abort_btn.setEnabled(False)
        self._abort_btn.setStyleSheet(self.styles.button_stylesheet(bg_color=COLOR_ERROR))
        header_layout.addWidget(self._abort_btn)

        layout.addLayout(header_layout)

        # Overall progress section
        progress_group = QGroupBox("Overall Progress")
        progress_layout = QVBoxLayout()

        self._status_spinner = StatusSpinnerWidget(self)
        progress_layout.addWidget(self._status_spinner)

        self._progress_bar = QProgressBar()
        self._progress_bar.setMinimum(0)
        self._progress_bar.setMaximum(100)
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(True)
        self._progress_bar.setFormat("%v%")
        progress_layout.addWidget(self._progress_bar)

        self._progress_label = QLabel("Waiting to start...")
        self._progress_label.setStyleSheet(f"color: {COLOR_GREY_600};")
        progress_layout.addWidget(self._progress_label)

        progress_group.setLayout(progress_layout)
        layout.addWidget(progress_group)

        # Workflow steps section
        steps_group = QGroupBox("Workflow Steps")
        steps_layout = QVBoxLayout()

        # Create scrollable area for step cards
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)

        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setSpacing(self.scale['spacing_small'])

        # Create step cards
        for i, step_name in enumerate(WORKFLOW_STEPS):
            card = WorkflowStepCard(i, step_name, self)
            self._step_cards.append(card)
            scroll_layout.addWidget(card)

        scroll_layout.addStretch()
        scroll_area.setWidget(scroll_content)

        steps_layout.addWidget(scroll_area)
        steps_group.setLayout(steps_layout)
        layout.addWidget(steps_group, stretch=1)

        # Time elapsed
        self._time_label = QLabel("")
        self._time_label.setStyleSheet(f"color: {COLOR_GREY_600};")
        layout.addWidget(self._time_label)

    def reset(self) -> None:
        """Reset all workflow steps to pending state."""
        self._current_step_index = -1

        for card in self._step_cards:
            card.set_status("pending")
            card.clear_content()

        self._progress_bar.setValue(0)
        self._status_spinner.reset()
        self._status_spinner.set_status("Ready")
        self._progress_label.setText("Waiting to start...")
        self._time_label.setText("")
        self._abort_btn.setEnabled(False)

    def start(self) -> None:
        """Start workflow visualization."""
        self.reset()
        self._status_spinner.start_spinner()
        self._status_spinner.set_status("Starting...")
        self._abort_btn.setEnabled(True)
        self._current_step_index = 0

        if self._step_cards:
            self._step_cards[0].set_status("running")

    def update_step(self, step_name: str, progress: float) -> None:
        """
        Update workflow progress based on step name.

        Args:
            step_name: Name of the current step
            progress: Progress fraction (0.0 to 1.0)
        """
        # Find step index
        step_index = get_workflow_step_index(step_name)

        if step_index < 0:
            # Unknown step, just update status
            self._status_spinner.set_status(step_name)
            return

        # Mark previous steps as complete
        for i in range(step_index):
            if i < len(self._step_cards):
                self._step_cards[i].set_status("complete")

        # Mark current step as running
        if step_index < len(self._step_cards):
            self._step_cards[step_index].set_status("running")

        # Mark subsequent steps as pending
        for i in range(step_index + 1, len(self._step_cards)):
            self._step_cards[i].set_status("pending")

        # Update progress bar
        progress_percent = int(progress * 100)
        self._progress_bar.setValue(progress_percent)

        # Update status
        self._status_spinner.set_status(step_name)
        self._progress_label.setText(f"Step {step_index + 1} of {WORKFLOW_STEP_COUNT}: {step_name}")

        self._current_step_index = step_index

    def set_complete(self, elapsed_seconds: Optional[float] = None) -> None:
        """
        Mark workflow as complete.

        Args:
            elapsed_seconds: Optional elapsed time in seconds
        """
        # Mark all steps complete
        for card in self._step_cards:
            card.set_status("complete")

        self._progress_bar.setValue(100)
        self._status_spinner.set_complete("Complete")
        self._progress_label.setText("All steps completed successfully")
        self._abort_btn.setEnabled(False)

        if elapsed_seconds is not None:
            from ..utils import format_duration
            self._time_label.setText(f"Total time: {format_duration(elapsed_seconds)}")

    def set_error(self, error_message: str, step_index: Optional[int] = None) -> None:
        """
        Mark workflow as errored.

        Args:
            error_message: Error message to display
            step_index: Optional step index where error occurred
        """
        # Mark current step as error
        if step_index is not None and 0 <= step_index < len(self._step_cards):
            self._step_cards[step_index].set_status("error")
        elif self._current_step_index >= 0:
            self._step_cards[self._current_step_index].set_status("error")

        self._status_spinner.set_error(error_message)
        self._progress_label.setText(f"Error: {error_message}")
        self._abort_btn.setEnabled(False)

    def _on_abort_clicked(self) -> None:
        """Handle abort button click."""
        self._status_spinner.set_status("Aborting...")
        self._abort_btn.setEnabled(False)
        self.abort_requested.emit()

    def set_enabled(self, enabled: bool) -> None:
        """
        Enable or disable the tab controls.

        Args:
            enabled: Whether controls should be enabled
        """
        # The abort button is managed separately based on processing state
        pass

    def update_intermediate_data(self, step_name: str, data: Dict[str, Any]) -> None:
        """
        Update a workflow step with intermediate data for visual debugging.

        Formats the data appropriately based on step type and displays
        it in the collapsible content area of the corresponding step card.

        Args:
            step_name: Name of the step (used to find the card)
            data: Dictionary containing step-specific intermediate results
        """
        step_index = get_workflow_step_index(step_name)

        if step_index < 0 or step_index >= len(self._step_cards):
            logger.debug(f"Unknown step for intermediate data: {step_name}")
            return

        card = self._step_cards[step_index]

        # Format data based on step type
        content = self._format_intermediate_data(step_name, data)
        card.set_content(content)

        # Add stat chips for numeric data
        self._add_stat_chips(card, step_name, data)

    def _format_intermediate_data(self, step_name: str, data: Dict[str, Any]) -> str:
        """
        Format intermediate data as human-readable text.

        Args:
            step_name: Name of the step
            data: Raw data dictionary

        Returns:
            Formatted text string for display
        """
        lines = []

        if "Extracting statements" in step_name:
            # Format extracted statements
            statements = data.get("statements", [])
            for stmt in statements:
                stmt_type = stmt.get("type", "unknown")
                text = stmt.get("text", "")
                lines.append(f"• [{stmt_type}] {text}")

        elif "counter-statements" in step_name.lower():
            # Format counter-statements
            counter_stmts = data.get("counter_statements", [])
            for cs in counter_stmts:
                original = cs.get("original", "")[:80]
                negated = cs.get("negated", "")[:80]
                keywords = cs.get("keywords", [])
                hyde_count = cs.get("hyde_count", 0)
                lines.append(f"Original: {original}...")
                lines.append(f"→ Counter: {negated}...")
                if keywords:
                    lines.append(f"  Keywords: {', '.join(keywords)}")
                lines.append(f"  HyDE abstracts: {hyde_count}")
                lines.append("")

        elif "counter-evidence" in step_name.lower():
            # Format search results
            stmt_idx = data.get("statement_index", 0)
            counter_stmt = data.get("counter_statement", "")
            lines.append(f"Statement #{stmt_idx + 1}: {counter_stmt}")
            lines.append("")
            lines.append(f"Semantic: {data.get('semantic_count', 0)} docs")
            lines.append(f"HyDE: {data.get('hyde_count', 0)} docs")
            lines.append(f"Keyword: {data.get('keyword_count', 0)} docs")
            lines.append(f"Total (deduplicated): {data.get('deduplicated_count', 0)} docs")

        elif "Scoring documents" in step_name:
            # Format scoring results
            stmt_idx = data.get("statement_index", 0)
            scored = data.get("documents_scored", 0)
            above = data.get("documents_above_threshold", 0)
            threshold = data.get("threshold", 3.0)
            lines.append(f"Statement #{stmt_idx + 1}")
            lines.append(f"Scored: {scored} → Above threshold ({threshold}): {above}")
            lines.append("")
            top_scores = data.get("top_scores", [])
            if top_scores:
                lines.append("Top scoring documents:")
                for doc in top_scores[:3]:
                    title = doc.get("title", "Untitled")[:40]
                    score = doc.get("score", 0)
                    lines.append(f"  • [{score}] {title}...")

        elif "Extracting citations" in step_name:
            # Format citation extraction
            stmt_idx = data.get("statement_index", 0)
            count = data.get("citations_extracted", 0)
            lines.append(f"Statement #{stmt_idx + 1}: {count} citations extracted")
            citations = data.get("citations", [])
            for cit in citations[:3]:
                passage = cit.get("passage", "")[:100]
                score = cit.get("score", 0)
                lines.append(f"  • [Score: {score}] \"{passage}...\"")

        elif "counter-report" in step_name.lower():
            # Format counter-report
            stmt_idx = data.get("statement_index", 0)
            num_citations = data.get("num_citations", 0)
            summary_len = data.get("summary_length", 0)
            preview = data.get("summary_preview", "")
            lines.append(f"Statement #{stmt_idx + 1}")
            lines.append(f"Citations used: {num_citations}, Length: {summary_len} chars")
            lines.append("")
            lines.append(f"Preview: {preview}")

        elif "verdict" in step_name.lower() and "overall" not in step_name.lower():
            # Format verdict analysis
            stmt_idx = data.get("statement_index", 0)
            original = data.get("original_statement", "")
            verdict = data.get("verdict", "undecided")
            confidence = data.get("confidence", "medium")
            rationale = data.get("rationale", "")
            lines.append(f"Statement #{stmt_idx + 1}: {original}")
            lines.append("")
            lines.append(f"VERDICT: {verdict.upper()} ({confidence} confidence)")
            lines.append(f"Rationale: {rationale}")

        elif "overall assessment" in step_name.lower():
            # Format overall assessment
            summary = data.get("verdict_summary", {})
            supports = summary.get("supports", 0)
            contradicts = summary.get("contradicts", 0)
            undecided = summary.get("undecided", 0)
            assessment = data.get("assessment", "")
            lines.append(f"Supports: {supports} | Contradicts: {contradicts} | Undecided: {undecided}")
            lines.append("")
            lines.append(assessment[:300] + "..." if len(assessment) > 300 else assessment)

        else:
            # Generic formatting for unknown step types
            for key, value in data.items():
                if isinstance(value, (str, int, float)):
                    lines.append(f"{key}: {value}")
                elif isinstance(value, list) and len(value) <= 5:
                    lines.append(f"{key}: {value}")

        return "\n".join(lines) if lines else "Processing..."

    def _add_stat_chips(
        self, card: WorkflowStepCard, step_name: str, data: Dict[str, Any]
    ) -> None:
        """
        Add statistic chips to a card based on step data.

        Args:
            card: The workflow step card to add chips to
            step_name: Name of the step
            data: Data dictionary with numeric values
        """
        if "counter-evidence" in step_name.lower():
            # Add search strategy chips
            semantic = data.get("semantic_count", 0)
            hyde = data.get("hyde_count", 0)
            keyword = data.get("keyword_count", 0)
            total = data.get("deduplicated_count", 0)

            if semantic > 0:
                card.add_stat_chip("Semantic", str(semantic), SEARCH_STRATEGY_COLORS.get("semantic", COLOR_PRIMARY))
            if hyde > 0:
                card.add_stat_chip("HyDE", str(hyde), SEARCH_STRATEGY_COLORS.get("hyde", COLOR_PRIMARY))
            if keyword > 0:
                card.add_stat_chip("Keyword", str(keyword), SEARCH_STRATEGY_COLORS.get("keyword", COLOR_PRIMARY))
            if total > 0:
                card.add_stat_chip("Total", str(total), COLOR_PRIMARY)

        elif "Scoring documents" in step_name:
            above = data.get("documents_above_threshold", 0)
            if above > 0:
                card.add_stat_chip("Above threshold", str(above), COLOR_SUCCESS)

        elif "Extracting citations" in step_name:
            count = data.get("citations_extracted", 0)
            card.add_stat_chip("Citations", str(count), COLOR_PRIMARY)


__all__ = ['WorkflowTab']
