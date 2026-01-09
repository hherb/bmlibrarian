"""
Workflow Panel for Paper Reviewer Lab

Panel showing step-by-step workflow progress.
"""

import logging
from typing import Optional, Dict, Any, List

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QProgressBar, QFrame,
)

from bmlibrarian.gui.qt.resources.styles.dpi_scale import scaled

from ..constants import (
    WORKFLOW_STEPS, STEP_WEIGHTS,
    STATUS_PENDING, STATUS_IN_PROGRESS, STATUS_COMPLETED,
    STATUS_SKIPPED, STATUS_FAILED,
)
from ..widgets import StepCard

logger = logging.getLogger(__name__)


class WorkflowPanel(QWidget):
    """
    Panel showing workflow progress with step cards.

    Features:
    - Overall progress bar
    - List of collapsible step cards
    - Abort button during processing
    """

    # Signal emitted when abort is requested
    abort_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        """Initialize the workflow panel."""
        super().__init__(parent)
        self._step_cards: Dict[str, StepCard] = {}
        self._current_step: Optional[str] = None
        self._is_processing = False
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(scaled(12), scaled(12), scaled(12), scaled(12))
        layout.setSpacing(scaled(12))

        # Header row
        header_row = QHBoxLayout()

        header = QLabel("Workflow Progress")
        header.setStyleSheet(f"font-size: {scaled(16)}px; font-weight: bold;")
        header_row.addWidget(header)

        header_row.addStretch()

        self.abort_btn = QPushButton("Abort")
        self.abort_btn.setVisible(False)
        self.abort_btn.clicked.connect(self._on_abort_clicked)
        self.abort_btn.setStyleSheet("""
            QPushButton {
                background-color: #DC143C;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background-color: #B22222;
            }
        """)
        header_row.addWidget(self.abort_btn)

        layout.addLayout(header_row)

        # Overall progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p% Complete")
        layout.addWidget(self.progress_bar)

        # Status label
        self.status_label = QLabel("Ready to start review")
        self.status_label.setStyleSheet("color: #808080;")
        layout.addWidget(self.status_label)

        # Scroll area for step cards
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)

        # Container for step cards
        self.steps_container = QWidget()
        self.steps_layout = QVBoxLayout(self.steps_container)
        self.steps_layout.setContentsMargins(0, 0, 0, 0)
        self.steps_layout.setSpacing(scaled(8))

        # Create step cards
        for step_name, display_name in WORKFLOW_STEPS:
            card = StepCard(step_name, display_name)
            self._step_cards[step_name] = card
            self.steps_layout.addWidget(card)

        self.steps_layout.addStretch()
        scroll_area.setWidget(self.steps_container)
        layout.addWidget(scroll_area)

    def _on_abort_clicked(self) -> None:
        """Handle abort button click."""
        self.abort_btn.setEnabled(False)
        self.abort_btn.setText("Aborting...")
        self.abort_requested.emit()

    def start_processing(self) -> None:
        """Start processing state."""
        self._is_processing = True
        self.abort_btn.setVisible(True)
        self.abort_btn.setEnabled(True)
        self.abort_btn.setText("Abort")
        self.progress_bar.setValue(0)
        self.status_label.setText("Starting review...")

    def stop_processing(self) -> None:
        """Stop processing state."""
        self._is_processing = False
        self.abort_btn.setVisible(False)
        self._current_step = None

    def update_step(
        self,
        step_name: str,
        status: str,
        message: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Update a step's status.

        Args:
            step_name: Step identifier
            status: New status
            message: Optional status message
            data: Optional result data
        """
        card = self._step_cards.get(step_name)
        if not card:
            logger.warning(f"Unknown step: {step_name}")
            return

        card.set_status(status, message)

        if data:
            card.set_result(data, message)

        # Update current step tracking
        if status == STATUS_IN_PROGRESS:
            self._current_step = step_name
            self.status_label.setText(f"Processing: {card.display_name}")

        # Auto-expand on completion/failure
        if status in (STATUS_COMPLETED, STATUS_FAILED) and data:
            card.expand()

        # Update overall progress
        self._update_progress()

    def _update_progress(self) -> None:
        """Update the overall progress bar."""
        completed_weight = 0.0
        in_progress_weight = 0.0

        for step_name, weight in STEP_WEIGHTS.items():
            card = self._step_cards.get(step_name)
            if card:
                if card.status == STATUS_COMPLETED:
                    completed_weight += weight
                elif card.status == STATUS_SKIPPED:
                    completed_weight += weight
                elif card.status == STATUS_IN_PROGRESS:
                    in_progress_weight = weight * 0.5  # Assume 50% through

        total_progress = (completed_weight + in_progress_weight) * 100
        self.progress_bar.setValue(int(total_progress))

    def set_completed(self, message: str = "Review completed") -> None:
        """Set the workflow as completed."""
        self.stop_processing()
        self.progress_bar.setValue(100)
        self.status_label.setText(message)
        self.status_label.setStyleSheet("color: #32CD32;")

    def set_failed(self, error: str) -> None:
        """Set the workflow as failed."""
        self.stop_processing()
        self.status_label.setText(f"Error: {error}")
        self.status_label.setStyleSheet("color: #DC143C;")

    def reset(self) -> None:
        """Reset all steps to pending state."""
        self._is_processing = False
        self._current_step = None
        self.abort_btn.setVisible(False)
        self.progress_bar.setValue(0)
        self.status_label.setText("Ready to start review")
        self.status_label.setStyleSheet("color: #808080;")

        for card in self._step_cards.values():
            card.reset()


__all__ = ['WorkflowPanel']
