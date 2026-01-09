"""
Results Panel for Paper Reviewer Lab

Panel for displaying review results with export options.
"""

import json
import logging
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTextEdit, QFileDialog, QFrame,
    QScrollArea, QMessageBox, QTabWidget,
)

from bmlibrarian.gui.qt.resources.styles.dpi_scale import scaled
from bmlibrarian.gui.qt.widgets.markdown_viewer import MarkdownViewer
from bmlibrarian.agents.paper_reviewer import PaperReviewResult

from ..constants import (
    EXPORT_FORMAT_MARKDOWN, EXPORT_FORMAT_PDF, EXPORT_FORMAT_JSON,
    EXPORT_FILE_FILTERS,
)

logger = logging.getLogger(__name__)


class ResultsPanel(QWidget):
    """
    Panel for displaying and exporting review results.

    Features:
    - Markdown-formatted results display
    - Export to Markdown, PDF, JSON
    - Copy to clipboard
    """

    def __init__(self, parent: Optional[QWidget] = None):
        """Initialize the results panel."""
        super().__init__(parent)
        self._result: Optional[PaperReviewResult] = None
        self._markdown_content: str = ''  # Raw markdown for copy/export
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(scaled(12), scaled(12), scaled(12), scaled(12))
        layout.setSpacing(scaled(12))

        # Header row
        header_row = QHBoxLayout()

        header = QLabel("Review Results")
        header.setStyleSheet(f"font-size: {scaled(16)}px; font-weight: bold;")
        header_row.addWidget(header)

        header_row.addStretch()
        layout.addLayout(header_row)

        # Results tabs
        self.result_tabs = QTabWidget()
        layout.addWidget(self.result_tabs)

        # Markdown view (rendered HTML)
        self.markdown_view = MarkdownViewer()
        self.result_tabs.addTab(self.markdown_view, "Report")

        # JSON view
        self.json_view = QTextEdit()
        self.json_view.setReadOnly(True)
        self.json_view.setPlaceholderText("JSON data will appear here...")
        self.json_view.setStyleSheet("font-family: monospace;")
        self.result_tabs.addTab(self.json_view, "JSON")

        # Export buttons row
        export_row = QHBoxLayout()
        export_row.addStretch()

        self.copy_btn = QPushButton("Copy to Clipboard")
        self.copy_btn.clicked.connect(self._copy_to_clipboard)
        self.copy_btn.setEnabled(False)
        export_row.addWidget(self.copy_btn)

        self.export_md_btn = QPushButton("Export Markdown")
        self.export_md_btn.clicked.connect(lambda: self._export(EXPORT_FORMAT_MARKDOWN))
        self.export_md_btn.setEnabled(False)
        export_row.addWidget(self.export_md_btn)

        self.export_pdf_btn = QPushButton("Export PDF")
        self.export_pdf_btn.clicked.connect(lambda: self._export(EXPORT_FORMAT_PDF))
        self.export_pdf_btn.setEnabled(False)
        export_row.addWidget(self.export_pdf_btn)

        self.export_json_btn = QPushButton("Export JSON")
        self.export_json_btn.clicked.connect(lambda: self._export(EXPORT_FORMAT_JSON))
        self.export_json_btn.setEnabled(False)
        export_row.addWidget(self.export_json_btn)

        layout.addLayout(export_row)

    def set_result(self, result: PaperReviewResult) -> None:
        """
        Set the review result to display.

        Args:
            result: Complete paper review result
        """
        self._result = result

        # Update markdown view (rendered)
        try:
            markdown_content = result.to_markdown()
            self._markdown_content = markdown_content  # Store for copy/export
            self.markdown_view.set_markdown(markdown_content)
        except Exception as e:
            logger.error(f"Failed to generate markdown: {e}")
            self._markdown_content = f"Error generating report: {e}"
            self.markdown_view.set_markdown(f"**Error:** {e}")

        # Update JSON view
        try:
            json_content = result.to_json(indent=2)
            self.json_view.setPlainText(json_content)
        except Exception as e:
            logger.error(f"Failed to generate JSON: {e}")
            self.json_view.setPlainText(f"Error generating JSON: {e}")

        # Enable export buttons
        self.copy_btn.setEnabled(True)
        self.export_md_btn.setEnabled(True)
        self.export_pdf_btn.setEnabled(True)
        self.export_json_btn.setEnabled(True)

    def _copy_to_clipboard(self) -> None:
        """Copy current view to clipboard."""
        from PySide6.QtWidgets import QApplication

        current_tab = self.result_tabs.currentIndex()
        if current_tab == 0:
            # Copy raw markdown (not HTML) for the report tab
            text = getattr(self, '_markdown_content', '')
        else:
            text = self.json_view.toPlainText()

        clipboard = QApplication.clipboard()
        clipboard.setText(text)

        logger.info("Copied results to clipboard")

    def _export(self, format_type: str) -> None:
        """
        Export results to file.

        Args:
            format_type: Export format (markdown, pdf, json)
        """
        if not self._result:
            return

        # Suggest filename based on paper title
        title = self._result.title or "paper_review"
        # Sanitize filename
        safe_title = "".join(c if c.isalnum() or c in " -_" else "_" for c in title)
        safe_title = safe_title[:50].strip()

        if format_type == EXPORT_FORMAT_MARKDOWN:
            default_name = f"{safe_title}.md"
        elif format_type == EXPORT_FORMAT_PDF:
            default_name = f"{safe_title}.pdf"
        else:
            default_name = f"{safe_title}.json"

        # Get save path
        file_filter = EXPORT_FILE_FILTERS.get(format_type, "All Files (*)")
        path, _ = QFileDialog.getSaveFileName(
            self, f"Export as {format_type.upper()}", default_name, file_filter
        )

        if not path:
            return

        try:
            if format_type == EXPORT_FORMAT_MARKDOWN:
                self._export_markdown(Path(path))
            elif format_type == EXPORT_FORMAT_PDF:
                self._export_pdf(Path(path))
            elif format_type == EXPORT_FORMAT_JSON:
                self._export_json(Path(path))

            logger.info(f"Exported to {path}")
            QMessageBox.information(
                self, "Export Complete",
                f"Results exported to:\n{path}"
            )

        except Exception as e:
            logger.error(f"Export failed: {e}")
            QMessageBox.critical(
                self, "Export Failed",
                f"Failed to export: {e}"
            )

    def _export_markdown(self, path: Path) -> None:
        """Export to Markdown file."""
        content = self._result.to_markdown()
        path.write_text(content, encoding='utf-8')

    def _export_pdf(self, path: Path) -> None:
        """Export to PDF file."""
        try:
            from bmlibrarian.exporters import PDFExporter

            exporter = PDFExporter()
            markdown_content = self._result.to_markdown()

            exporter.export_report(
                report_content=markdown_content,
                output_path=path,
                research_question=f"Paper Review: {self._result.title}",
                citation_count=len(self._result.contradictory_papers),
            )
        except ImportError:
            # Fall back to simple text export
            logger.warning("PDFExporter not available, saving as text")
            path_txt = path.with_suffix('.txt')
            path_txt.write_text(self._result.to_markdown(), encoding='utf-8')
            raise RuntimeError(
                f"PDF export not available. Saved as text: {path_txt}"
            )

    def _export_json(self, path: Path) -> None:
        """Export to JSON file."""
        content = self._result.to_json(indent=2)
        path.write_text(content, encoding='utf-8')

    def clear(self) -> None:
        """Clear the results display."""
        self._result = None
        self._markdown_content = ''
        self.markdown_view.clear_content()
        self.json_view.clear()
        self.copy_btn.setEnabled(False)
        self.export_md_btn.setEnabled(False)
        self.export_pdf_btn.setEnabled(False)
        self.export_json_btn.setEnabled(False)


__all__ = ['ResultsPanel']
