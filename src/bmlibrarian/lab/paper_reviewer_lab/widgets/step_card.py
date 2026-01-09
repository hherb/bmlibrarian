"""
Step Card Widget for Paper Reviewer Lab

Collapsible card showing workflow step status and results.
"""

import logging
from typing import Optional, Dict, Any

from PySide6.QtCore import Qt, Signal, QPropertyAnimation, QEasingCurve
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QWidget, QSizePolicy,
)

from bmlibrarian.gui.qt.resources.dpi_scale import scaled

from ..constants import (
    STATUS_PENDING, STATUS_IN_PROGRESS, STATUS_COMPLETED,
    STATUS_SKIPPED, STATUS_FAILED, STATUS_COLORS,
    STEP_EXPAND_ANIMATION_MS,
)

logger = logging.getLogger(__name__)


class StepCard(QFrame):
    """
    Collapsible card showing a workflow step's status and results.

    Features:
    - Step name and status indicator
    - Collapsible content area for results
    - Progress indicator (spinner or checkmark)
    - Click to expand/collapse
    """

    # Signal emitted when card is clicked
    clicked = Signal(str)  # step_name

    def __init__(
        self,
        step_name: str,
        display_name: str,
        parent: Optional[QWidget] = None,
    ):
        """
        Initialize the step card.

        Args:
            step_name: Internal step identifier
            display_name: Human-readable step name
            parent: Parent widget
        """
        super().__init__(parent)
        self.step_name = step_name
        self.display_name = display_name
        self._status = STATUS_PENDING
        self._expanded = False
        self._result_data: Optional[Dict[str, Any]] = None

        self._setup_ui()
        self._apply_style()

    def _setup_ui(self) -> None:
        """Set up the UI components."""
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(
            scaled(8), scaled(6), scaled(8), scaled(6)
        )
        main_layout.setSpacing(scaled(4))

        # Header row
        header_layout = QHBoxLayout()
        header_layout.setSpacing(scaled(8))

        # Status indicator
        self.status_indicator = QLabel("○")
        self.status_indicator.setFixedWidth(scaled(20))
        self.status_indicator.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(self.status_indicator)

        # Step name
        self.name_label = QLabel(self.display_name)
        self.name_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        header_layout.addWidget(self.name_label)

        # Status label
        self.status_label = QLabel("Pending")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        header_layout.addWidget(self.status_label)

        # Expand indicator
        self.expand_indicator = QLabel("▶")
        self.expand_indicator.setFixedWidth(scaled(16))
        header_layout.addWidget(self.expand_indicator)

        main_layout.addLayout(header_layout)

        # Collapsible content area
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(
            scaled(28), scaled(4), scaled(8), scaled(4)
        )
        self.content_layout.setSpacing(scaled(4))

        # Summary label (for quick results)
        self.summary_label = QLabel("")
        self.summary_label.setWordWrap(True)
        self.summary_label.setVisible(False)
        self.content_layout.addWidget(self.summary_label)

        self.content_widget.setVisible(False)
        main_layout.addWidget(self.content_widget)

    def _apply_style(self) -> None:
        """Apply styling based on current status."""
        color = STATUS_COLORS.get(self._status, STATUS_COLORS[STATUS_PENDING])

        # Update status indicator
        if self._status == STATUS_PENDING:
            self.status_indicator.setText("○")
        elif self._status == STATUS_IN_PROGRESS:
            self.status_indicator.setText("◐")
        elif self._status == STATUS_COMPLETED:
            self.status_indicator.setText("●")
        elif self._status == STATUS_SKIPPED:
            self.status_indicator.setText("⊘")
        elif self._status == STATUS_FAILED:
            self.status_indicator.setText("✕")

        self.status_indicator.setStyleSheet(f"color: {color}; font-size: {scaled(14)}px;")

        # Update status label
        status_text = self._status.replace("_", " ").title()
        self.status_label.setText(status_text)
        self.status_label.setStyleSheet(f"color: {color};")

        # Update expand indicator
        expand_text = "▼" if self._expanded else "▶"
        self.expand_indicator.setText(expand_text)

    def set_status(self, status: str, summary: Optional[str] = None) -> None:
        """
        Update the step status.

        Args:
            status: New status value
            summary: Optional summary text to display
        """
        self._status = status
        self._apply_style()

        if summary:
            self.summary_label.setText(summary)
            self.summary_label.setVisible(True)

    def set_result(self, data: Dict[str, Any], summary: Optional[str] = None) -> None:
        """
        Set the result data for this step.

        Args:
            data: Result data dictionary
            summary: Optional summary text
        """
        self._result_data = data

        if summary:
            self.summary_label.setText(summary)
            self.summary_label.setVisible(True)

    def expand(self) -> None:
        """Expand the content area."""
        if not self._expanded:
            self._expanded = True
            self.content_widget.setVisible(True)
            self._apply_style()

    def collapse(self) -> None:
        """Collapse the content area."""
        if self._expanded:
            self._expanded = False
            self.content_widget.setVisible(False)
            self._apply_style()

    def toggle(self) -> None:
        """Toggle the expanded state."""
        if self._expanded:
            self.collapse()
        else:
            self.expand()

    def reset(self) -> None:
        """Reset the card to pending state."""
        self._status = STATUS_PENDING
        self._result_data = None
        self._expanded = False
        self.summary_label.setText("")
        self.summary_label.setVisible(False)
        self.content_widget.setVisible(False)
        self._apply_style()

    def mousePressEvent(self, event) -> None:
        """Handle mouse press to toggle expansion."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.toggle()
            self.clicked.emit(self.step_name)
        super().mousePressEvent(event)

    @property
    def status(self) -> str:
        """Get current status."""
        return self._status

    @property
    def result_data(self) -> Optional[Dict[str, Any]]:
        """Get result data."""
        return self._result_data


__all__ = ['StepCard']
