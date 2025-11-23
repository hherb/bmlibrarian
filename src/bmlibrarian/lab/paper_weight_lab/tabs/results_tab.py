"""
Paper Weight Laboratory - Results Tab

Tab widget for document assessment and results display.
"""

import json
import logging
from typing import Optional, Dict

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QTextEdit, QSplitter, QMessageBox, QFileDialog,
    QDialog,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent

from bmlibrarian.gui.qt.resources.styles.dpi_scale import get_font_scale
from bmlibrarian.gui.qt.resources.styles.stylesheet_generator import get_stylesheet_generator
from bmlibrarian.agents.paper_weight_agent import PaperWeightAssessmentAgent
from bmlibrarian.agents.paper_weight_models import (
    PaperWeightResult,
    ALL_DIMENSIONS,
)
from bmlibrarian.agents.paper_weight_db import get_document_metadata

from ..constants import SCORE_DECIMALS, WORKER_TERMINATE_TIMEOUT_MS
from ..utils import (
    format_dimension_name,
    format_score_with_max,
    format_datetime,
    format_document_metadata,
)
from ..radar_chart import RadarChartWidget
from ..worker import AssessmentWorker
from ..dialogs import DimensionWeightDialog
from ..widgets import AuditTrailSection, StatusSpinnerWidget

logger = logging.getLogger(__name__)


class ResultsTab(QWidget):
    """
    Tab widget for document assessment and results display.

    Shows selected document, assessment controls, results visualization,
    and audit trail.
    """

    def __init__(
        self,
        agent: Optional[PaperWeightAssessmentAgent] = None,
        parent: Optional[object] = None
    ):
        """
        Initialize results tab.

        Args:
            agent: Paper weight assessment agent (shared from main window)
            parent: Parent widget
        """
        super().__init__(parent)

        self.scale = get_font_scale()
        self.styles = get_stylesheet_generator()

        self.agent = agent
        self.current_document_id: Optional[int] = None
        self.current_document_meta: Optional[Dict] = None
        self.current_result: Optional[PaperWeightResult] = None
        self.assessment_worker: Optional[AssessmentWorker] = None

        self._setup_ui()

    def set_agent(self, agent: PaperWeightAssessmentAgent) -> None:
        """
        Set the assessment agent.

        Args:
            agent: Paper weight assessment agent
        """
        self.agent = agent
        self._update_button_states()

    def _setup_ui(self) -> None:
        """Setup tab user interface."""
        layout = QVBoxLayout(self)
        layout.setSpacing(self.scale['spacing_medium'])

        # Selected document display (fixed height)
        self.document_group = self._create_document_display()
        layout.addWidget(self.document_group)

        # Action buttons with status spinner (fixed height)
        action_widget = self._create_action_section()
        layout.addWidget(action_widget)

        # Splitter for results and audit trail (expandable)
        splitter = QSplitter(Qt.Vertical)

        # Results visualization (fixed height)
        self.results_section = self._create_results_section()
        self.results_section.hide()
        splitter.addWidget(self.results_section)

        # Audit trail section (expandable)
        self.audit_section = AuditTrailSection()
        splitter.addWidget(self.audit_section)

        splitter.setSizes([200, 400])
        layout.addWidget(splitter, stretch=1)

        # Bottom buttons (fixed height)
        layout.addWidget(self._create_bottom_buttons())

    def _create_document_display(self) -> QGroupBox:
        """Create document information display."""
        group = QGroupBox("Selected Document")
        layout = QVBoxLayout()
        layout.setSpacing(self.scale['spacing_small'])

        # Title label
        self.doc_title_label = QLabel("No document selected")
        self.doc_title_label.setWordWrap(True)
        self.doc_title_label.setStyleSheet(self.styles.label_stylesheet(
            font_size_key='font_medium',
            bold=True
        ))
        layout.addWidget(self.doc_title_label)

        # Metadata label
        self.doc_meta_label = QLabel("")
        self.doc_meta_label.setStyleSheet(self.styles.label_stylesheet(
            font_size_key='font_small',
            color='#666'
        ))
        layout.addWidget(self.doc_meta_label)

        # Abstract viewer (collapsible)
        self.abstract_text = QTextEdit()
        self.abstract_text.setReadOnly(True)
        self.abstract_text.setMaximumHeight(self.scale['control_height_xlarge'] * 3)
        self.abstract_text.hide()
        layout.addWidget(self.abstract_text)

        # Show/hide abstract button
        button_layout = QHBoxLayout()
        self.view_abstract_button = QPushButton("Show Abstract")
        self.view_abstract_button.setEnabled(False)
        self.view_abstract_button.clicked.connect(self._toggle_abstract)
        button_layout.addWidget(self.view_abstract_button)
        button_layout.addStretch()
        layout.addLayout(button_layout)

        group.setLayout(layout)
        return group

    def _create_action_section(self) -> QWidget:
        """Create action buttons and status spinner section."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(self.scale['spacing_small'])

        # Action buttons row
        button_layout = QHBoxLayout()

        self.assess_button = QPushButton("Assess Paper Weight")
        self.assess_button.setEnabled(False)
        self.assess_button.clicked.connect(self._start_assessment)
        self.assess_button.setStyleSheet(self.styles.button_stylesheet(
            bg_color="#4CAF50"
        ))
        button_layout.addWidget(self.assess_button)

        self.force_reassess_button = QPushButton("Force Re-assess")
        self.force_reassess_button.setEnabled(False)
        self.force_reassess_button.clicked.connect(
            lambda: self._start_assessment(force=True)
        )
        self.force_reassess_button.setStyleSheet(self.styles.button_stylesheet(
            bg_color="#FF9800"
        ))
        button_layout.addWidget(self.force_reassess_button)

        self.config_weights_button = QPushButton("Configure Weights")
        self.config_weights_button.clicked.connect(self._configure_weights)
        button_layout.addWidget(self.config_weights_button)

        button_layout.addStretch()
        layout.addLayout(button_layout)

        # Status spinner (replaces progress section)
        self.status_spinner = StatusSpinnerWidget()
        layout.addWidget(self.status_spinner)

        return widget

    def _create_results_section(self) -> QGroupBox:
        """Create results visualization section."""
        group = QGroupBox("Results")
        layout = QHBoxLayout()
        layout.setSpacing(self.scale['spacing_large'])

        # Left: Summary scores
        summary_layout = QVBoxLayout()

        self.final_weight_label = QLabel("Final Weight: --/10")
        self.final_weight_label.setStyleSheet(self.styles.label_stylesheet(
            font_size_key='font_xlarge',
            bold=True
        ))
        summary_layout.addWidget(self.final_weight_label)

        self.version_label = QLabel("Version: --")
        self.version_label.setStyleSheet(self.styles.label_stylesheet(
            font_size_key='font_small',
            color='#666'
        ))
        summary_layout.addWidget(self.version_label)

        self.assessed_label = QLabel("Assessed: --")
        self.assessed_label.setStyleSheet(self.styles.label_stylesheet(
            font_size_key='font_small',
            color='#666'
        ))
        summary_layout.addWidget(self.assessed_label)

        summary_layout.addSpacing(self.scale['spacing_large'])

        # Dimension breakdown
        breakdown_label = QLabel("Dimension Breakdown:")
        breakdown_label.setStyleSheet(self.styles.label_stylesheet(
            font_size_key='font_medium',
            bold=True
        ))
        summary_layout.addWidget(breakdown_label)

        self.dimension_score_labels: Dict[str, QLabel] = {}
        for dim in ALL_DIMENSIONS:
            display_name = format_dimension_name(dim)
            label = QLabel(f"{display_name}: --/10")
            label.setStyleSheet(self.styles.label_stylesheet(
                font_size_key='font_normal'
            ))
            self.dimension_score_labels[dim] = label
            summary_layout.addWidget(label)

        summary_layout.addStretch()
        layout.addLayout(summary_layout)

        # Right: Radar chart
        self.radar_chart = RadarChartWidget()
        self.radar_chart.setMinimumWidth(self.scale['control_width_large'])
        self.radar_chart.setMinimumHeight(self.scale['control_width_large'])
        layout.addWidget(self.radar_chart)

        group.setLayout(layout)
        return group

    def _create_bottom_buttons(self) -> QWidget:
        """Create bottom action buttons."""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        self.export_report_button = QPushButton("Export Report (Markdown)")
        self.export_report_button.setEnabled(False)
        self.export_report_button.clicked.connect(self._export_markdown)
        layout.addWidget(self.export_report_button)

        self.export_json_button = QPushButton("Export JSON")
        self.export_json_button.setEnabled(False)
        self.export_json_button.clicked.connect(self._export_json)
        layout.addWidget(self.export_json_button)

        layout.addStretch()

        self.clear_button = QPushButton("Clear / New Assessment")
        self.clear_button.clicked.connect(self.clear)
        layout.addWidget(self.clear_button)

        return widget

    def load_document(self, document_id: int) -> None:
        """
        Load document metadata and update display.

        Args:
            document_id: Document ID to load
        """
        meta = get_document_metadata(document_id)
        if not meta:
            QMessageBox.warning(
                self,
                "Document Not Found",
                f"Could not find document with ID: {document_id}"
            )
            return

        self.current_document_id = document_id
        self.current_document_meta = meta

        # Update display
        self.doc_title_label.setText(meta['title'] or 'No title')
        self.doc_meta_label.setText(format_document_metadata(
            authors=meta.get('authors'),
            year=meta.get('year'),
            pmid=meta.get('pmid'),
            doi=meta.get('doi')
        ))

        # Set abstract
        self.abstract_text.setText(
            meta.get('abstract') or 'No abstract available'
        )

        # Enable buttons
        self.view_abstract_button.setEnabled(True)
        self._update_button_states()

        # Hide previous results
        self.results_section.hide()
        self.audit_section.clear()

        # Reset status
        self.status_spinner.reset()

    def _update_button_states(self) -> None:
        """Update button enabled states."""
        has_document = self.current_document_id is not None
        has_agent = self.agent is not None

        self.assess_button.setEnabled(has_document and has_agent)
        self.force_reassess_button.setEnabled(has_document and has_agent)

    def _toggle_abstract(self) -> None:
        """Toggle abstract visibility."""
        if self.abstract_text.isVisible():
            self.abstract_text.hide()
            self.view_abstract_button.setText("Show Abstract")
        else:
            self.abstract_text.show()
            self.view_abstract_button.setText("Hide Abstract")

    def _configure_weights(self) -> None:
        """Open weight configuration dialog."""
        if self.agent is None:
            QMessageBox.warning(
                self,
                "Agent Not Available",
                "Paper weight assessment agent is not initialized."
            )
            return

        current_weights = self.agent.get_dimension_weights()
        dialog = DimensionWeightDialog(current_weights, self)

        if dialog.exec() == QDialog.Accepted:
            new_weights = dialog.get_weights()
            self.agent.config['dimension_weights'] = new_weights
            QMessageBox.information(
                self,
                "Weights Updated",
                "Dimension weights have been updated.\n"
                "Use 'Force Re-assess' to apply new weights."
            )

    def _start_assessment(self, force: bool = False) -> None:
        """Start paper weight assessment."""
        if self.current_document_id is None:
            QMessageBox.warning(
                self,
                "No Document",
                "Please select a document first."
            )
            return

        if self.agent is None:
            QMessageBox.warning(
                self,
                "Agent Not Available",
                "Paper weight assessment agent is not initialized."
            )
            return

        # Disable buttons during assessment
        self.assess_button.setEnabled(False)
        self.force_reassess_button.setEnabled(False)

        # Start spinner and show status
        self.status_spinner.start_spinner()
        self.status_spinner.set_status("Starting assessment...")

        # Hide previous results
        self.results_section.hide()
        self.audit_section.clear()

        # Create and start worker
        self.assessment_worker = AssessmentWorker(
            self.agent,
            self.current_document_id,
            force_reassess=force
        )
        self.assessment_worker.progress_update.connect(self._on_progress_update)
        self.assessment_worker.assessment_complete.connect(
            self._on_assessment_complete
        )
        self.assessment_worker.assessment_error.connect(
            self._on_assessment_error
        )
        self.assessment_worker.start()

    def _on_progress_update(self, dimension: str, status: str) -> None:
        """Handle progress update from worker."""
        display_name = format_dimension_name(dimension)
        self.status_spinner.set_status(f"Analyzing {display_name}...")

    def _on_assessment_complete(self, result: PaperWeightResult) -> None:
        """Handle completed assessment."""
        self.current_result = result

        # Update status spinner
        self.status_spinner.set_complete(
            f"Assessment complete ({format_score_with_max(result.final_weight)})"
        )

        # Show and populate results
        self.results_section.show()
        self.final_weight_label.setText(
            f"Final Weight: {format_score_with_max(result.final_weight)}"
        )
        self.version_label.setText(f"Version: {result.assessor_version}")
        self.assessed_label.setText(
            f"Assessed: {format_datetime(result.assessed_at)}"
        )

        for dim in ALL_DIMENSIONS:
            dim_score = getattr(result, dim)
            display_name = format_dimension_name(dim)
            self.dimension_score_labels[dim].setText(
                f"{display_name}: {format_score_with_max(dim_score.score)}"
            )

        # Update radar chart
        self.radar_chart.set_scores({
            dim: getattr(result, dim).score
            for dim in ALL_DIMENSIONS
        })

        # Populate audit trail
        self.audit_section.populate_from_result(result)

        # Enable buttons
        self._update_button_states()
        self.export_report_button.setEnabled(True)
        self.export_json_button.setEnabled(True)

    def _on_assessment_error(self, error_message: str) -> None:
        """Handle assessment error."""
        self.status_spinner.set_error(f"Error: {error_message[:50]}...")

        QMessageBox.critical(
            self,
            "Assessment Error",
            f"Error during assessment:\n{error_message}"
        )

        # Re-enable buttons
        self._update_button_states()

    def _export_markdown(self) -> None:
        """Export assessment as Markdown report."""
        if not self.current_result:
            return

        default_name = f"paper_weight_assessment_{self.current_document_id}.md"
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Assessment Report",
            default_name,
            "Markdown Files (*.md)"
        )

        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(self.current_result.to_markdown())

                QMessageBox.information(
                    self,
                    "Export Successful",
                    f"Report exported to:\n{file_path}"
                )
            except Exception as e:
                logger.error(f"Error exporting markdown: {e}")
                QMessageBox.critical(
                    self,
                    "Export Error",
                    f"Failed to export report:\n{e}"
                )

    def _export_json(self) -> None:
        """Export assessment as JSON."""
        if not self.current_result:
            return

        default_name = f"paper_weight_assessment_{self.current_document_id}.json"
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Assessment JSON",
            default_name,
            "JSON Files (*.json)"
        )

        if file_path:
            try:
                data = self.current_result.to_dict()
                if 'assessed_at' in data and data['assessed_at']:
                    data['assessed_at'] = data['assessed_at'].isoformat()

                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, default=str)

                QMessageBox.information(
                    self,
                    "Export Successful",
                    f"JSON exported to:\n{file_path}"
                )
            except Exception as e:
                logger.error(f"Error exporting JSON: {e}")
                QMessageBox.critical(
                    self,
                    "Export Error",
                    f"Failed to export JSON:\n{e}"
                )

    def clear(self) -> None:
        """Reset tab for new assessment."""
        self.current_document_id = None
        self.current_document_meta = None
        self.current_result = None

        # Reset document display
        self.doc_title_label.setText("No document selected")
        self.doc_meta_label.setText("")
        self.abstract_text.clear()
        self.abstract_text.hide()
        self.view_abstract_button.setText("Show Abstract")
        self.view_abstract_button.setEnabled(False)

        # Reset status
        self.status_spinner.reset()

        # Hide results and clear
        self.results_section.hide()
        self.audit_section.clear()
        self.radar_chart.clear_scores()

        # Reset buttons
        self._update_button_states()
        self.export_report_button.setEnabled(False)
        self.export_json_button.setEnabled(False)

    def _terminate_workers(self) -> None:
        """
        Safely terminate any running worker threads.

        Waits up to WORKER_TERMINATE_TIMEOUT_MS for workers to finish.
        """
        if self.assessment_worker is not None and self.assessment_worker.isRunning():
            logger.info("Terminating assessment_worker thread...")
            self.assessment_worker.terminate()
            if not self.assessment_worker.wait(WORKER_TERMINATE_TIMEOUT_MS):
                logger.warning(
                    f"assessment_worker did not terminate within "
                    f"{WORKER_TERMINATE_TIMEOUT_MS}ms"
                )

    def closeEvent(self, event: QCloseEvent) -> None:
        """
        Handle widget close event.

        Ensures worker threads are properly terminated before closing.

        Args:
            event: The close event
        """
        self._terminate_workers()
        # Clear worker reference for garbage collection
        self.assessment_worker = None
        super().closeEvent(event)


__all__ = ['ResultsTab']
