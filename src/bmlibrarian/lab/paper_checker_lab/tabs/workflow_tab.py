"""
PaperChecker Laboratory - Workflow Tab

Tab widget for displaying workflow progress visualization.
"""

import logging
from typing import Optional, List

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


__all__ = ['WorkflowTab']
