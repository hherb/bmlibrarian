"""
Paper Weight Laboratory - Custom Widgets

Custom Qt widgets for the Paper Weight Assessment Laboratory.
Includes tree widget with tooltip support for full text access.
"""

from typing import Optional, Dict, TYPE_CHECKING

from PySide6.QtWidgets import (
    QTreeWidget, QTreeWidgetItem, QGroupBox, QVBoxLayout,
    QMenu, QApplication, QWidget, QHBoxLayout, QLabel,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont

from bmlibrarian.gui.qt.resources.styles.dpi_scale import get_font_scale
from bmlibrarian.agents.paper_weight_models import (
    ALL_DIMENSIONS,
    PaperWeightResult,
)

from .constants import (
    TREE_COL_COMPONENT,
    TREE_COL_VALUE,
    TREE_COL_SCORE,
    TREE_COL_EVIDENCE,
    TREE_COL_WIDTH_COMPONENT,
    TREE_COL_WIDTH_VALUE,
    TREE_COL_WIDTH_SCORE,
    SCORE_DECIMALS,
    SPINNER_ANIMATION_INTERVAL_MS,
    SPINNER_FRAMES,
    PROGRESS_COMPLETE,
    PROGRESS_ERROR,
)
from .utils import format_dimension_name, format_score
from .dialogs import FullTextDialog


class StatusSpinnerWidget(QWidget):
    """
    A status line widget with an animated spinner.

    Displays a single line of status text with an optional animated
    spinner to indicate work in progress.
    """

    def __init__(self, parent: Optional[object] = None):
        """
        Initialize status spinner widget.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)

        self.scale = get_font_scale()
        self._frame_index = 0
        self._is_spinning = False

        self._setup_ui()
        self._setup_timer()

    def _setup_ui(self) -> None:
        """Setup widget UI."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(self.scale['spacing_small'])

        # Spinner label (fixed width for consistent alignment)
        self._spinner_label = QLabel("")
        self._spinner_label.setFixedWidth(self.scale['char_width'] * 2)
        layout.addWidget(self._spinner_label)

        # Status text label
        self._status_label = QLabel("Ready")
        layout.addWidget(self._status_label, stretch=1)

    def _setup_timer(self) -> None:
        """Setup animation timer."""
        self._timer = QTimer(self)
        self._timer.setInterval(SPINNER_ANIMATION_INTERVAL_MS)
        self._timer.timeout.connect(self._animate_spinner)

    def _animate_spinner(self) -> None:
        """Advance spinner animation frame."""
        if self._is_spinning:
            self._spinner_label.setText(SPINNER_FRAMES[self._frame_index])
            self._frame_index = (self._frame_index + 1) % len(SPINNER_FRAMES)

    def set_status(self, text: str) -> None:
        """
        Set the status text.

        Args:
            text: Status message to display
        """
        self._status_label.setText(text)

    def start_spinner(self) -> None:
        """Start the spinner animation."""
        self._is_spinning = True
        self._frame_index = 0
        self._timer.start()

    def stop_spinner(self) -> None:
        """Stop the spinner animation."""
        self._is_spinning = False
        self._timer.stop()
        self._spinner_label.setText("")

    def set_complete(self, text: str) -> None:
        """
        Set status to complete state.

        Args:
            text: Completion message to display
        """
        self.stop_spinner()
        self._spinner_label.setText(PROGRESS_COMPLETE)
        self._status_label.setText(text)

    def set_error(self, text: str) -> None:
        """
        Set status to error state.

        Args:
            text: Error message to display
        """
        self.stop_spinner()
        self._spinner_label.setText(PROGRESS_ERROR)
        self._status_label.setText(text)

    def reset(self) -> None:
        """Reset to initial state."""
        self.stop_spinner()
        self._spinner_label.setText("")
        self._status_label.setText("Ready")


class AuditTrailTreeWidget(QTreeWidget):
    """
    Custom tree widget for displaying assessment audit trail.

    Features:
    - Automatic tooltips showing full text for all cells
    - Double-click to open full text dialog
    - Right-click context menu to copy or view full text
    - Alternating row colors for readability
    """

    def __init__(self, parent: Optional[object] = None):
        """
        Initialize audit trail tree widget.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)

        self.scale = get_font_scale()

        # Store full text separately from display text
        self._full_text_data: Dict[int, Dict[str, str]] = {}
        self._item_counter = 0

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        """Setup tree widget UI."""
        self.setHeaderLabels(["Component", "Value", "Score", "Evidence"])
        self.setColumnWidth(
            TREE_COL_COMPONENT,
            self.scale['char_width'] * TREE_COL_WIDTH_COMPONENT
        )
        self.setColumnWidth(
            TREE_COL_VALUE,
            self.scale['char_width'] * TREE_COL_WIDTH_VALUE
        )
        self.setColumnWidth(
            TREE_COL_SCORE,
            self.scale['char_width'] * TREE_COL_WIDTH_SCORE
        )
        self.setAlternatingRowColors(True)

        # Enable word wrap for evidence column
        self.setWordWrap(True)

        # Enable context menu
        self.setContextMenuPolicy(Qt.CustomContextMenu)

    def _connect_signals(self) -> None:
        """Connect widget signals."""
        self.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.customContextMenuRequested.connect(self._show_context_menu)

    def clear(self) -> None:
        """Clear tree and reset data storage."""
        super().clear()
        self._full_text_data.clear()
        self._item_counter = 0

    def populate_from_result(self, result: PaperWeightResult) -> None:
        """
        Populate tree from a PaperWeightResult.

        Sets up full tooltips for all text fields so users can always
        access complete untruncated information.

        Args:
            result: PaperWeightResult to display
        """
        self.clear()

        for dim in ALL_DIMENSIONS:
            dim_score = getattr(result, dim)
            display_name = format_dimension_name(dim)

            # Create dimension root item
            dim_item = QTreeWidgetItem(self)
            dim_item.setText(TREE_COL_COMPONENT, display_name)
            dim_item.setText(TREE_COL_SCORE, format_score(dim_score.score))

            # Make dimension item bold
            font = dim_item.font(TREE_COL_COMPONENT)
            font.setBold(True)
            dim_item.setFont(TREE_COL_COMPONENT, font)

            # Store item ID for data lookup
            item_id = self._item_counter
            self._item_counter += 1
            dim_item.setData(TREE_COL_COMPONENT, Qt.UserRole, item_id)

            # Add details as children
            for detail in dim_score.details:
                detail_item = QTreeWidgetItem(dim_item)
                detail_item.setText(TREE_COL_COMPONENT, detail.component)

                # Value column
                value_text = str(detail.extracted_value) if detail.extracted_value else ''
                detail_item.setText(TREE_COL_VALUE, value_text)
                if value_text:
                    detail_item.setToolTip(TREE_COL_VALUE, value_text)

                # Score column
                detail_item.setText(TREE_COL_SCORE, format_score(detail.score_contribution))

                # Evidence column - show full text, set tooltip for easy viewing
                evidence_text = detail.evidence_text or ''
                detail_item.setText(TREE_COL_EVIDENCE, evidence_text)
                if evidence_text:
                    detail_item.setToolTip(TREE_COL_EVIDENCE, evidence_text)

                # Store full text data for double-click access
                detail_item_id = self._item_counter
                self._item_counter += 1
                detail_item.setData(TREE_COL_COMPONENT, Qt.UserRole, detail_item_id)
                self._full_text_data[detail_item_id] = {
                    'component': detail.component,
                    'value': value_text,
                    'evidence': evidence_text,
                    'reasoning': detail.reasoning or '',
                }

                # Add reasoning as child if present
                if detail.reasoning:
                    reasoning_item = QTreeWidgetItem(detail_item)
                    reasoning_item.setText(TREE_COL_COMPONENT, "Reasoning:")
                    reasoning_item.setText(TREE_COL_EVIDENCE, detail.reasoning)

                    # Full tooltip
                    reasoning_item.setToolTip(TREE_COL_EVIDENCE, detail.reasoning)

                    # Style reasoning in italic
                    font = reasoning_item.font(TREE_COL_COMPONENT)
                    font.setItalic(True)
                    reasoning_item.setFont(TREE_COL_COMPONENT, font)

                    # Store for double-click
                    reasoning_item_id = self._item_counter
                    self._item_counter += 1
                    reasoning_item.setData(TREE_COL_COMPONENT, Qt.UserRole, reasoning_item_id)
                    self._full_text_data[reasoning_item_id] = {
                        'component': f"{detail.component} - Reasoning",
                        'value': '',
                        'evidence': '',
                        'reasoning': detail.reasoning,
                    }

        # Expand all by default
        self.expandAll()

    def _on_item_double_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        """
        Handle double-click to show full text dialog.

        Args:
            item: Clicked tree item
            column: Clicked column index
        """
        item_id = item.data(TREE_COL_COMPONENT, Qt.UserRole)
        if item_id is None or item_id not in self._full_text_data:
            return

        data = self._full_text_data[item_id]

        # Determine which text to show based on column
        if column == TREE_COL_VALUE and data['value']:
            title = f"Value: {data['component']}"
            text = data['value']
        elif column == TREE_COL_EVIDENCE and data['evidence']:
            title = f"Evidence: {data['component']}"
            text = data['evidence']
        elif data['reasoning']:
            title = f"Reasoning: {data['component']}"
            text = data['reasoning']
        else:
            # Show all available text
            parts = []
            if data['value']:
                parts.append(f"VALUE:\n{data['value']}")
            if data['evidence']:
                parts.append(f"EVIDENCE:\n{data['evidence']}")
            if data['reasoning']:
                parts.append(f"REASONING:\n{data['reasoning']}")

            if not parts:
                return

            title = f"Full Details: {data['component']}"
            text = "\n\n".join(parts)

        dialog = FullTextDialog(title, text, self)
        dialog.exec()

    def _show_context_menu(self, position) -> None:
        """
        Show context menu with copy and view options.

        Args:
            position: Click position
        """
        item = self.itemAt(position)
        if not item:
            return

        item_id = item.data(TREE_COL_COMPONENT, Qt.UserRole)

        menu = QMenu(self)

        # Copy cell text
        copy_action = menu.addAction("Copy Cell Text")
        copy_action.triggered.connect(
            lambda: self._copy_cell_text(item, self.currentColumn())
        )

        # View full text (if we have stored data)
        if item_id is not None and item_id in self._full_text_data:
            menu.addSeparator()
            view_action = menu.addAction("View Full Details...")
            view_action.triggered.connect(
                lambda: self._on_item_double_clicked(item, TREE_COL_EVIDENCE)
            )

        menu.exec(self.viewport().mapToGlobal(position))

    def _copy_cell_text(self, item: QTreeWidgetItem, column: int) -> None:
        """
        Copy cell text to clipboard.

        Args:
            item: Tree item
            column: Column index
        """
        text = item.text(column)
        if text:
            clipboard = QApplication.clipboard()
            clipboard.setText(text)


class AuditTrailSection(QGroupBox):
    """
    Group box containing the audit trail tree widget.

    Provides a convenient wrapper with consistent styling.
    """

    def __init__(self, parent: Optional[object] = None):
        """
        Initialize audit trail section.

        Args:
            parent: Parent widget
        """
        super().__init__("Audit Trail", parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Setup section UI."""
        layout = QVBoxLayout()
        self.tree = AuditTrailTreeWidget(self)
        layout.addWidget(self.tree)
        self.setLayout(layout)

    def clear(self) -> None:
        """Clear the tree."""
        self.tree.clear()

    def populate_from_result(self, result: PaperWeightResult) -> None:
        """
        Populate from assessment result.

        Args:
            result: PaperWeightResult to display
        """
        self.tree.populate_from_result(result)


__all__ = [
    'StatusSpinnerWidget',
    'AuditTrailTreeWidget',
    'AuditTrailSection',
]
