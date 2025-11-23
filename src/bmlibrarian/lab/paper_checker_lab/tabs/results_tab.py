"""
PaperChecker Laboratory - Results Tab

Tab widget for displaying paper check results with 5 sub-tabs.
"""

import json
import logging
from typing import Optional, Dict, Any, List, TYPE_CHECKING

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QGroupBox, QScrollArea, QTabWidget,
    QTextEdit, QFrame, QSizePolicy,
)
from PySide6.QtCore import Qt

from bmlibrarian.gui.qt.resources.styles.dpi_scale import get_font_scale
from bmlibrarian.gui.qt.resources.styles.stylesheet_generator import get_stylesheet_generator

from ..constants import (
    RESULTS_TAB_INDEX_SUMMARY, RESULTS_TAB_INDEX_STATEMENTS,
    RESULTS_TAB_INDEX_EVIDENCE, RESULTS_TAB_INDEX_VERDICTS,
    RESULTS_TAB_INDEX_EXPORT, EXPORT_JSON_INDENT,
    COLOR_PRIMARY, COLOR_SUCCESS, COLOR_GREY_600,
)
from ..widgets import (
    VerdictBadge, StatChipWidget, CitationCardWidget, StatisticsSection,
)
from ..dialogs import FullTextDialog, ExportPreviewDialog
from ..utils import (
    format_verdict_display, format_confidence_display, format_statement_type_display,
    format_duration, format_search_stats, truncate_passage,
)

if TYPE_CHECKING:
    from bmlibrarian.paperchecker.data_models import PaperCheckResult


logger = logging.getLogger(__name__)


class ResultsTab(QWidget):
    """
    Tab widget for displaying paper check results.

    Contains 5 sub-tabs:
    - Summary: Overall assessment and processing statistics
    - Statements: Extracted statements with counter-statements
    - Evidence: Search results and citations
    - Verdicts: Individual verdicts with rationale
    - Export: JSON and Markdown export options
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """
        Initialize results tab.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)

        self.scale = get_font_scale()
        self.styles = get_stylesheet_generator()
        self._result: Optional["PaperCheckResult"] = None

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

        # Sub-tabs
        self._tab_widget = QTabWidget()
        self._tab_widget.addTab(self._create_summary_tab(), "Summary")
        self._tab_widget.addTab(self._create_statements_tab(), "Statements")
        self._tab_widget.addTab(self._create_evidence_tab(), "Evidence")
        self._tab_widget.addTab(self._create_verdicts_tab(), "Verdicts")
        self._tab_widget.addTab(self._create_export_tab(), "Export")

        layout.addWidget(self._tab_widget)

    def _create_summary_tab(self) -> QWidget:
        """Create the Summary sub-tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(self.scale['spacing_medium'])

        # Overall assessment
        assessment_group = QGroupBox("Overall Assessment")
        assessment_layout = QVBoxLayout()

        self._assessment_text = QTextEdit()
        self._assessment_text.setReadOnly(True)
        self._assessment_text.setPlaceholderText("No results yet...")
        self._assessment_text.setMinimumHeight(self.scale['line_height'] * 6)
        assessment_layout.addWidget(self._assessment_text)

        assessment_group.setLayout(assessment_layout)
        layout.addWidget(assessment_group)

        # Statistics
        stats_group = QGroupBox("Processing Statistics")
        stats_layout = QVBoxLayout()

        self._stats_container = QHBoxLayout()
        stats_layout.addLayout(self._stats_container)

        self._processing_info = QLabel("")
        self._processing_info.setStyleSheet(f"color: {COLOR_GREY_600};")
        stats_layout.addWidget(self._processing_info)

        stats_group.setLayout(stats_layout)
        layout.addWidget(stats_group)

        # Source metadata
        source_group = QGroupBox("Source Document")
        source_layout = QVBoxLayout()

        self._source_metadata_label = QLabel("")
        self._source_metadata_label.setWordWrap(True)
        source_layout.addWidget(self._source_metadata_label)

        source_group.setLayout(source_layout)
        layout.addWidget(source_group)

        layout.addStretch()
        return widget

    def _create_statements_tab(self) -> QWidget:
        """Create the Statements sub-tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)

        self._statements_container = QWidget()
        self._statements_layout = QVBoxLayout(self._statements_container)
        self._statements_layout.setSpacing(self.scale['spacing_medium'])

        scroll_area.setWidget(self._statements_container)
        layout.addWidget(scroll_area)

        return widget

    def _create_evidence_tab(self) -> QWidget:
        """Create the Evidence sub-tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Search statistics
        self._search_stats = StatisticsSection("Search Statistics", self)
        layout.addWidget(self._search_stats)

        # Citations scroll area
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)

        self._evidence_container = QWidget()
        self._evidence_layout = QVBoxLayout(self._evidence_container)
        self._evidence_layout.setSpacing(self.scale['spacing_medium'])

        scroll_area.setWidget(self._evidence_container)
        layout.addWidget(scroll_area, stretch=1)

        return widget

    def _create_verdicts_tab(self) -> QWidget:
        """Create the Verdicts sub-tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)

        self._verdicts_container = QWidget()
        self._verdicts_layout = QVBoxLayout(self._verdicts_container)
        self._verdicts_layout.setSpacing(self.scale['spacing_medium'])

        scroll_area.setWidget(self._verdicts_container)
        layout.addWidget(scroll_area)

        return widget

    def _create_export_tab(self) -> QWidget:
        """Create the Export sub-tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(self.scale['spacing_large'])

        # Export buttons
        button_group = QGroupBox("Export Options")
        button_layout = QHBoxLayout()

        json_btn = QPushButton("Export JSON")
        json_btn.setToolTip("Export results as JSON file")
        json_btn.clicked.connect(self._export_json)
        json_btn.setMinimumHeight(self.scale['control_height_large'])
        button_layout.addWidget(json_btn)

        md_btn = QPushButton("Export Markdown")
        md_btn.setToolTip("Export results as Markdown report")
        md_btn.clicked.connect(self._export_markdown)
        md_btn.setMinimumHeight(self.scale['control_height_large'])
        button_layout.addWidget(md_btn)

        copy_btn = QPushButton("Copy Summary")
        copy_btn.setToolTip("Copy brief summary to clipboard")
        copy_btn.clicked.connect(self._copy_summary)
        button_layout.addWidget(copy_btn)

        button_layout.addStretch()

        button_group.setLayout(button_layout)
        layout.addWidget(button_group)

        # Export preview
        preview_group = QGroupBox("Export Preview")
        preview_layout = QVBoxLayout()

        self._export_preview = QTextEdit()
        self._export_preview.setReadOnly(True)
        self._export_preview.setPlaceholderText("Select an export format to preview...")
        preview_layout.addWidget(self._export_preview)

        preview_group.setLayout(preview_layout)
        layout.addWidget(preview_group, stretch=1)

        return widget

    def load_result(self, result: "PaperCheckResult") -> None:
        """
        Load and display a PaperCheckResult.

        Args:
            result: PaperCheckResult to display
        """
        self._result = result
        self._populate_summary()
        self._populate_statements()
        self._populate_evidence()
        self._populate_verdicts()
        logger.info("Results loaded successfully")

    def _populate_summary(self) -> None:
        """Populate the Summary sub-tab."""
        if not self._result:
            return

        # Overall assessment
        self._assessment_text.setPlainText(
            self._result.overall_assessment or "No overall assessment available."
        )

        # Clear existing stats
        while self._stats_container.count():
            item = self._stats_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Add stats chips
        num_statements = len(self._result.statements)
        chip = StatChipWidget("Statements", str(num_statements), COLOR_PRIMARY, self)
        self._stats_container.addWidget(chip)

        # Count verdicts
        verdict_counts = {"supports": 0, "contradicts": 0, "undecided": 0}
        for verdict in self._result.verdicts:
            v = verdict.verdict.lower()
            if v in verdict_counts:
                verdict_counts[v] += 1

        from ..constants import VERDICT_COLORS
        for v_name, v_count in verdict_counts.items():
            if v_count > 0:
                chip = StatChipWidget(v_name.title(), str(v_count), VERDICT_COLORS[v_name], self)
                self._stats_container.addWidget(chip)

        self._stats_container.addStretch()

        # Processing info
        meta = self._result.processing_metadata or {}
        info_parts = []
        if meta.get('model'):
            info_parts.append(f"Model: {meta['model']}")
        if meta.get('processing_time_seconds'):
            info_parts.append(f"Time: {format_duration(meta['processing_time_seconds'])}")
        if meta.get('timestamp'):
            info_parts.append(f"Processed: {meta['timestamp']}")

        self._processing_info.setText(" | ".join(info_parts))

        # Source metadata
        source = self._result.source_metadata or {}
        source_parts = []
        if source.get('title'):
            source_parts.append(f"<b>{source['title']}</b>")
        if source.get('pmid'):
            source_parts.append(f"PMID: {source['pmid']}")
        if source.get('doi'):
            source_parts.append(f"DOI: {source['doi']}")

        self._source_metadata_label.setText("<br>".join(source_parts) if source_parts else "No source metadata")

    def _populate_statements(self) -> None:
        """Populate the Statements sub-tab."""
        # Clear existing
        while self._statements_layout.count():
            item = self._statements_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self._result or not self._result.statements:
            label = QLabel("No statements extracted.")
            self._statements_layout.addWidget(label)
            return

        for i, statement in enumerate(self._result.statements):
            card = self._create_statement_card(i, statement)
            self._statements_layout.addWidget(card)

        self._statements_layout.addStretch()

    def _create_statement_card(self, index: int, statement: Any) -> QFrame:
        """Create a card for a single statement."""
        card = QFrame()
        card.setFrameShape(QFrame.StyledPanel)
        card.setStyleSheet(f"""
            QFrame {{
                background-color: white;
                border: 1px solid #ddd;
                border-radius: {self.scale['border_radius']}px;
                padding: {self.scale['padding_medium']}px;
            }}
        """)

        layout = QVBoxLayout(card)
        layout.setSpacing(self.scale['spacing_small'])

        # Header with type badge
        header = QHBoxLayout()
        header.addWidget(QLabel(f"<b>Statement {index + 1}</b>"))

        type_text, type_color = format_statement_type_display(statement.statement_type)
        type_label = QLabel(type_text)
        type_label.setStyleSheet(f"""
            background-color: {type_color};
            color: white;
            padding: 2px 8px;
            border-radius: 4px;
        """)
        header.addWidget(type_label)

        confidence_label = QLabel(f"Confidence: {statement.confidence:.2f}")
        confidence_label.setStyleSheet(f"color: {COLOR_GREY_600};")
        header.addWidget(confidence_label)

        header.addStretch()
        layout.addLayout(header)

        # Statement text
        statement_text = QLabel(statement.text)
        statement_text.setWordWrap(True)
        layout.addWidget(statement_text)

        # Counter-statement (if available)
        if index < len(self._result.counter_statements):
            counter = self._result.counter_statements[index]
            counter_group = QGroupBox("Counter-Statement")
            counter_layout = QVBoxLayout()

            counter_text = QLabel(counter.negated_text)
            counter_text.setWordWrap(True)
            counter_text.setStyleSheet("font-style: italic;")
            counter_layout.addWidget(counter_text)

            # Keywords
            if counter.keywords:
                keywords_label = QLabel(f"<b>Keywords:</b> {', '.join(counter.keywords[:10])}")
                keywords_label.setWordWrap(True)
                counter_layout.addWidget(keywords_label)

            counter_group.setLayout(counter_layout)
            layout.addWidget(counter_group)

        return card

    def _populate_evidence(self) -> None:
        """Populate the Evidence sub-tab."""
        # Clear existing
        self._search_stats.clear()
        while self._evidence_layout.count():
            item = self._evidence_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self._result or not self._result.search_results:
            label = QLabel("No evidence found.")
            self._evidence_layout.addWidget(label)
            return

        # Aggregate search stats from all statements
        total_stats = {
            'semantic_count': 0,
            'hyde_count': 0,
            'keyword_count': 0,
            'deduplicated_count': 0,
        }

        for search_result in self._result.search_results:
            stats = format_search_stats(search_result)
            total_stats['semantic_count'] += stats['semantic_count']
            total_stats['hyde_count'] += stats['hyde_count']
            total_stats['keyword_count'] += stats['keyword_count']
            total_stats['deduplicated_count'] += stats['deduplicated_count']

        self._search_stats.set_search_stats(total_stats)

        # Display citations from counter-reports
        for i, counter_report in enumerate(self._result.counter_reports):
            # Counter-report header
            header = QLabel(f"<b>Evidence for Statement {i + 1}</b>")
            self._evidence_layout.addWidget(header)

            # Summary
            if counter_report.summary:
                summary_label = QLabel(counter_report.summary)
                summary_label.setWordWrap(True)
                self._evidence_layout.addWidget(summary_label)

            # Citations
            for citation in counter_report.citations[:5]:  # Show top 5
                citation_data = {
                    'title': citation.metadata.get('title', 'No title'),
                    'authors': citation.metadata.get('authors', []),
                    'year': citation.metadata.get('year'),
                    'pmid': citation.metadata.get('pmid'),
                    'doi': citation.metadata.get('doi'),
                    'passage': citation.passage,
                    'score': citation.relevance_score,
                    'strategies': [],  # Could add provenance here
                }
                card = CitationCardWidget(citation_data, self)
                self._evidence_layout.addWidget(card)

        self._evidence_layout.addStretch()

    def _populate_verdicts(self) -> None:
        """Populate the Verdicts sub-tab."""
        # Clear existing
        while self._verdicts_layout.count():
            item = self._verdicts_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self._result or not self._result.verdicts:
            label = QLabel("No verdicts available.")
            self._verdicts_layout.addWidget(label)
            return

        for i, verdict in enumerate(self._result.verdicts):
            card = self._create_verdict_card(i, verdict)
            self._verdicts_layout.addWidget(card)

        self._verdicts_layout.addStretch()

    def _create_verdict_card(self, index: int, verdict: Any) -> QFrame:
        """Create a card for a single verdict."""
        card = QFrame()
        card.setFrameShape(QFrame.StyledPanel)

        # Get verdict color for border
        verdict_text, verdict_color = format_verdict_display(verdict.verdict)

        card.setStyleSheet(f"""
            QFrame {{
                background-color: white;
                border: 2px solid {verdict_color};
                border-radius: {self.scale['border_radius']}px;
                padding: {self.scale['padding_medium']}px;
            }}
        """)

        layout = QVBoxLayout(card)
        layout.setSpacing(self.scale['spacing_small'])

        # Header with verdict badge
        header = QHBoxLayout()
        header.addWidget(QLabel(f"<b>Statement {index + 1} Verdict</b>"))

        badge = VerdictBadge(verdict.verdict, verdict.confidence, self)
        header.addWidget(badge)

        header.addStretch()
        layout.addLayout(header)

        # Original statement (if available)
        if index < len(self._result.statements):
            statement = self._result.statements[index]
            stmt_label = QLabel(f"<i>\"{statement.text}\"</i>")
            stmt_label.setWordWrap(True)
            stmt_label.setStyleSheet(f"color: {COLOR_GREY_600};")
            layout.addWidget(stmt_label)

        # Rationale
        rationale_group = QGroupBox("Rationale")
        rationale_layout = QVBoxLayout()

        rationale_text = QLabel(verdict.rationale)
        rationale_text.setWordWrap(True)
        rationale_layout.addWidget(rationale_text)

        rationale_group.setLayout(rationale_layout)
        layout.addWidget(rationale_group)

        return card

    def _export_json(self) -> None:
        """Export results as JSON."""
        if not self._result:
            return

        try:
            json_content = json.dumps(
                self._result.to_json_dict(),
                indent=EXPORT_JSON_INDENT,
                ensure_ascii=False
            )

            dialog = ExportPreviewDialog(
                "Export JSON",
                json_content,
                ".json",
                self
            )
            dialog.exec()

        except Exception as e:
            logger.error(f"JSON export error: {e}")

    def _export_markdown(self) -> None:
        """Export results as Markdown."""
        if not self._result:
            return

        try:
            md_content = self._result.to_markdown_report()

            dialog = ExportPreviewDialog(
                "Export Markdown",
                md_content,
                ".md",
                self
            )
            dialog.exec()

        except Exception as e:
            logger.error(f"Markdown export error: {e}")

    def _copy_summary(self) -> None:
        """Copy brief summary to clipboard."""
        if not self._result:
            return

        from PySide6.QtWidgets import QApplication

        summary_parts = []
        summary_parts.append("PaperChecker Results Summary")
        summary_parts.append("=" * 30)

        if self._result.source_metadata:
            if self._result.source_metadata.get('title'):
                summary_parts.append(f"Title: {self._result.source_metadata['title']}")

        summary_parts.append(f"\nStatements checked: {len(self._result.statements)}")

        for i, verdict in enumerate(self._result.verdicts):
            v_text, _ = format_verdict_display(verdict.verdict)
            c_text, _ = format_confidence_display(verdict.confidence)
            summary_parts.append(f"Statement {i + 1}: {v_text} ({c_text})")

        if self._result.overall_assessment:
            summary_parts.append(f"\nOverall Assessment:\n{self._result.overall_assessment}")

        clipboard = QApplication.clipboard()
        clipboard.setText("\n".join(summary_parts))

    def clear(self) -> None:
        """Clear all results."""
        self._result = None
        self._assessment_text.clear()
        self._source_metadata_label.clear()
        self._processing_info.clear()
        self._search_stats.clear()
        self._export_preview.clear()

        # Clear dynamic content
        for container_layout in [self._statements_layout, self._evidence_layout, self._verdicts_layout]:
            while container_layout.count():
                item = container_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()


__all__ = ['ResultsTab']
