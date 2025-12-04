"""
Report Preview Widget for Systematic Review.

Provides a tabbed widget for previewing systematic review reports
with support for both rendered markdown and raw text views.
The text is selectable for copy/paste operations.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTabWidget,
    QTextEdit,
    QGroupBox,
)

from bmlibrarian.gui.qt.widgets.markdown_viewer import MarkdownViewer
from bmlibrarian.gui.qt.resources.styles.dpi_scale import scale_px

logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

PLACEHOLDER_TEXT = "Report will be displayed here after the review completes..."
TAB_RENDERED = "Rendered"
TAB_RAW = "Raw Markdown"


# =============================================================================
# Report Preview Widget
# =============================================================================


class ReportPreviewWidget(QWidget):
    """
    Widget for previewing systematic review reports.

    Provides:
    - Rendered markdown view with proper styling
    - Raw markdown text view for copy/paste
    - Toggle between views
    - Copy button for easy clipboard access
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """
        Initialize the report preview widget.

        Args:
            parent: Optional parent widget
        """
        super().__init__(parent)
        self._markdown_content: str = ""
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(scale_px(8))

        # Header with title and copy button
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)

        title_label = QLabel("Report Preview")
        title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        header_layout.addWidget(title_label)

        header_layout.addStretch()

        self.copy_btn = QPushButton("Copy to Clipboard")
        self.copy_btn.setToolTip("Copy raw markdown to clipboard")
        self.copy_btn.clicked.connect(self._copy_to_clipboard)
        self.copy_btn.setEnabled(False)
        header_layout.addWidget(self.copy_btn)

        layout.addLayout(header_layout)

        # Tab widget for different views
        self.tab_widget = QTabWidget()

        # Rendered markdown view
        self.rendered_view = MarkdownViewer()
        self.rendered_view.setPlaceholderText(PLACEHOLDER_TEXT)
        self.tab_widget.addTab(self.rendered_view, TAB_RENDERED)

        # Raw markdown view (selectable text)
        self.raw_view = QTextEdit()
        self.raw_view.setReadOnly(True)
        self.raw_view.setPlaceholderText(PLACEHOLDER_TEXT)
        self.raw_view.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        # Use monospace font for raw markdown
        self.raw_view.setStyleSheet(
            "QTextEdit { font-family: 'Consolas', 'Monaco', 'Courier New', monospace; }"
        )
        self.tab_widget.addTab(self.raw_view, TAB_RAW)

        layout.addWidget(self.tab_widget)

    def set_report(self, markdown_content: str) -> None:
        """
        Set the report content to display.

        Args:
            markdown_content: Markdown-formatted report text
        """
        self._markdown_content = markdown_content

        # Update both views
        self.rendered_view.set_markdown(markdown_content)
        self.raw_view.setPlainText(markdown_content)

        # Enable copy button
        self.copy_btn.setEnabled(bool(markdown_content))

        logger.debug(
            f"Report preview updated with {len(markdown_content)} characters"
        )

    def set_report_from_result(self, result: Dict[str, Any]) -> None:
        """
        Generate and set report from a SystematicReviewResult dict.

        Args:
            result: Dictionary from SystematicReviewResult.to_dict()
        """
        try:
            from bmlibrarian.agents.systematic_review.reporter import Reporter
            from bmlibrarian.agents.systematic_review.data_models import (
                SystematicReviewResult,
            )

            # Convert dict back to SystematicReviewResult
            review_result = SystematicReviewResult.from_dict(result)

            # Create reporter and generate markdown
            reporter = Reporter(documenter=None, criteria=None, weights=None)
            markdown_report = reporter.generate_markdown_string(review_result)

            self.set_report(markdown_report)

        except Exception as e:
            logger.error(f"Failed to generate report from result: {e}", exc_info=True)
            self.set_report(f"# Error Generating Report\n\nFailed to generate report: {e}")

    def clear_report(self) -> None:
        """Clear the report preview."""
        self._markdown_content = ""
        self.rendered_view.clear_content()
        self.raw_view.clear()
        self.copy_btn.setEnabled(False)

    def get_markdown(self) -> str:
        """
        Get the current markdown content.

        Returns:
            Current markdown content or empty string
        """
        return self._markdown_content

    @Slot()
    def _copy_to_clipboard(self) -> None:
        """Copy raw markdown to clipboard."""
        from PySide6.QtWidgets import QApplication

        if self._markdown_content:
            clipboard = QApplication.clipboard()
            clipboard.setText(self._markdown_content)
            logger.info("Report copied to clipboard")
