"""
Paper Weight Assessment Laboratory - Main Window

The main application window for the Paper Weight Assessment Laboratory.
Uses modular components for better maintainability.
"""

import json
import logging
import sys
from typing import Optional, Dict

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QComboBox, QTextEdit,
    QGroupBox, QSplitter, QMessageBox, QFileDialog, QDialog,
    QFrame,
)
from PySide6.QtCore import Qt

from bmlibrarian.agents.paper_weight_agent import PaperWeightAssessmentAgent
from bmlibrarian.agents.paper_weight_models import (
    PaperWeightResult,
    ALL_DIMENSIONS,
)
from bmlibrarian.agents.paper_weight_db import (
    search_documents,
    get_recent_assessments,
    get_document_metadata,
)
from bmlibrarian.gui.qt.resources.styles.dpi_scale import get_font_scale
from bmlibrarian.gui.qt.resources.styles.stylesheet_generator import get_stylesheet_generator

from .constants import (
    WINDOW_MIN_WIDTH,
    WINDOW_MIN_HEIGHT,
    WINDOW_DEFAULT_WIDTH,
    WINDOW_DEFAULT_HEIGHT,
    PROGRESS_PENDING,
    PROGRESS_COMPLETE,
    PROGRESS_ERROR,
    SCORE_DECIMALS,
)
from .utils import (
    format_dimension_name,
    format_score,
    format_score_with_max,
    format_datetime,
    format_document_metadata,
    format_recent_assessment_display,
)
from .worker import AssessmentWorker
from .dialogs import DimensionWeightDialog, DocumentSearchDialog
from .widgets import AuditTrailSection


logger = logging.getLogger(__name__)


class PaperWeightLab(QMainWindow):
    """
    Main laboratory GUI window for paper weight assessment.

    Provides comprehensive interface for:
    - Document selection (search or recent assessments)
    - Assessment triggering with progress tracking
    - Results visualization
    - Audit trail inspection
    - Export functionality
    """

    def __init__(self):
        """Initialize the Paper Weight Laboratory."""
        super().__init__()

        # Get scaling values
        self.scale = get_font_scale()
        self.styles = get_stylesheet_generator()

        # Initialize agent
        try:
            self.agent = PaperWeightAssessmentAgent(show_model_info=False)
        except Exception as e:
            logger.error(f"Failed to initialize agent: {e}")
            self.agent = None

        # State
        self.current_document_id: Optional[int] = None
        self.current_document_meta: Optional[Dict] = None
        self.current_result: Optional[PaperWeightResult] = None
        self.assessment_worker: Optional[AssessmentWorker] = None

        self._setup_ui()
        self._load_recent_assessments()

    def _setup_ui(self) -> None:
        """Initialize user interface."""
        self.setWindowTitle("Paper Weight Assessment Laboratory")
        self.setMinimumSize(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT)
        self.resize(WINDOW_DEFAULT_WIDTH, WINDOW_DEFAULT_HEIGHT)

        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(self.scale['spacing_medium'])
        main_layout.setContentsMargins(
            self.scale['padding_medium'],
            self.scale['padding_medium'],
            self.scale['padding_medium'],
            self.scale['padding_medium']
        )

        # Document selection section
        main_layout.addWidget(self._create_document_selection())

        # Selected document display
        self.document_display = self._create_document_display()
        main_layout.addWidget(self.document_display)

        # Action buttons
        main_layout.addWidget(self._create_action_buttons())

        # Progress section
        self.progress_section = self._create_progress_section()
        main_layout.addWidget(self.progress_section)

        # Splitter for results and audit trail
        splitter = QSplitter(Qt.Vertical)

        # Results visualization
        self.results_section = self._create_results_section()
        self.results_section.hide()
        splitter.addWidget(self.results_section)

        # Audit trail section (uses custom widget with tooltips/dialogs)
        self.audit_section = AuditTrailSection()
        splitter.addWidget(self.audit_section)

        splitter.setSizes([200, 300])
        main_layout.addWidget(splitter, stretch=1)

        # Bottom buttons
        main_layout.addWidget(self._create_bottom_buttons())

    def _create_document_selection(self) -> QGroupBox:
        """Create document selection widgets."""
        group = QGroupBox("Document Selection")
        layout = QVBoxLayout()
        layout.setSpacing(self.scale['spacing_small'])

        # Search row
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("Search:"))

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(
            "Enter PMID, DOI, or title keywords..."
        )
        self.search_input.returnPressed.connect(self._quick_search)
        search_layout.addWidget(self.search_input, stretch=1)

        self.search_button = QPushButton("Search")
        self.search_button.clicked.connect(self._open_search_dialog)
        self.search_button.setStyleSheet(self.styles.button_stylesheet(
            bg_color="#2196F3"
        ))
        search_layout.addWidget(self.search_button)

        layout.addLayout(search_layout)

        # Recent assessments dropdown
        recent_layout = QHBoxLayout()
        recent_layout.addWidget(QLabel("Recent assessments:"))

        self.recent_combo = QComboBox()
        self.recent_combo.setMinimumWidth(self.scale['control_width_xlarge'])
        self.recent_combo.currentIndexChanged.connect(
            self._on_recent_selection_changed
        )
        recent_layout.addWidget(self.recent_combo, stretch=1)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._load_recent_assessments)
        recent_layout.addWidget(refresh_btn)

        layout.addLayout(recent_layout)

        group.setLayout(layout)
        return group

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

        # Buttons
        button_layout = QHBoxLayout()

        self.view_abstract_button = QPushButton("Show Abstract")
        self.view_abstract_button.setEnabled(False)
        self.view_abstract_button.clicked.connect(self._toggle_abstract)
        button_layout.addWidget(self.view_abstract_button)

        button_layout.addStretch()
        layout.addLayout(button_layout)

        group.setLayout(layout)
        return group

    def _create_action_buttons(self) -> QWidget:
        """Create action button row."""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        self.assess_button = QPushButton("Assess Paper Weight")
        self.assess_button.setEnabled(False)
        self.assess_button.clicked.connect(self._start_assessment)
        self.assess_button.setStyleSheet(self.styles.button_stylesheet(
            bg_color="#4CAF50"
        ))
        layout.addWidget(self.assess_button)

        self.force_reassess_button = QPushButton("Force Re-assess")
        self.force_reassess_button.setEnabled(False)
        self.force_reassess_button.clicked.connect(
            lambda: self._start_assessment(force=True)
        )
        self.force_reassess_button.setStyleSheet(self.styles.button_stylesheet(
            bg_color="#FF9800"
        ))
        layout.addWidget(self.force_reassess_button)

        self.config_weights_button = QPushButton("Configure Weights")
        self.config_weights_button.clicked.connect(self._configure_weights)
        layout.addWidget(self.config_weights_button)

        layout.addStretch()

        return widget

    def _create_progress_section(self) -> QGroupBox:
        """Create assessment progress display."""
        group = QGroupBox("Assessment Progress")
        layout = QVBoxLayout()
        layout.setSpacing(self.scale['spacing_small'])

        self.progress_labels: Dict[str, QLabel] = {}

        for dim in ALL_DIMENSIONS:
            display_name = format_dimension_name(dim)
            label = QLabel(f"{PROGRESS_PENDING} {display_name}: Pending")
            label.setStyleSheet(self.styles.label_stylesheet(
                font_size_key='font_normal'
            ))
            self.progress_labels[dim] = label
            layout.addWidget(label)

        group.setLayout(layout)
        return group

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

        # Right: Visual placeholder
        visual_frame = QFrame()
        visual_frame.setMinimumWidth(self.scale['control_width_large'])
        visual_frame.setStyleSheet(self.styles.card_stylesheet(
            border_color='#DDD'
        ))
        visual_layout = QVBoxLayout(visual_frame)
        visual_label = QLabel("(Visualization placeholder)")
        visual_label.setAlignment(Qt.AlignCenter)
        visual_label.setStyleSheet(self.styles.label_stylesheet(
            color='#999'
        ))
        visual_layout.addWidget(visual_label)
        layout.addWidget(visual_frame)

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
        self.clear_button.clicked.connect(self._reset_for_new_assessment)
        layout.addWidget(self.clear_button)

        return widget

    # =========================================================================
    # Event Handlers
    # =========================================================================

    def _load_recent_assessments(self) -> None:
        """Load recent assessments into dropdown."""
        self.recent_combo.clear()
        self.recent_combo.addItem("-- Select recent assessment --", None)

        recent = get_recent_assessments()
        for item in recent:
            display_text = format_recent_assessment_display(
                item['title'], item['final_weight']
            )
            self.recent_combo.addItem(display_text, item['document_id'])

    def _on_recent_selection_changed(self, index: int) -> None:
        """Handle selection change in recent assessments dropdown."""
        document_id = self.recent_combo.currentData()
        if document_id:
            self._load_document(document_id)

    def _quick_search(self) -> None:
        """Perform quick search from inline search box."""
        query = self.search_input.text().strip()
        if not query:
            return

        results = search_documents(query, limit=1)
        if results:
            self._load_document(results[0]['id'])
        else:
            QMessageBox.information(
                self,
                "No Results",
                f"No documents found matching: {query}"
            )

    def _open_search_dialog(self) -> None:
        """Open full search dialog."""
        dialog = DocumentSearchDialog(self)
        if dialog.exec() == QDialog.Accepted:
            document_id = dialog.get_selected_document_id()
            if document_id:
                self._load_document(document_id)

    def _load_document(self, document_id: int) -> None:
        """Load document metadata and update display."""
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
        self.abstract_text.setText(meta.get('abstract') or 'No abstract available')

        # Enable buttons
        self.view_abstract_button.setEnabled(True)
        self.assess_button.setEnabled(self.agent is not None)
        self.force_reassess_button.setEnabled(self.agent is not None)

        # Hide results from previous assessment
        self.results_section.hide()
        self.audit_section.clear()

        # Reset progress labels
        self._reset_progress_labels()

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

        # Reset progress indicators
        self._reset_progress_labels()

        # Hide previous results
        self.results_section.hide()
        self.audit_section.clear()

        # Create and start worker thread
        self.assessment_worker = AssessmentWorker(
            self.agent,
            self.current_document_id,
            force_reassess=force
        )
        self.assessment_worker.progress_update.connect(
            self._on_progress_update
        )
        self.assessment_worker.assessment_complete.connect(
            self._on_assessment_complete
        )
        self.assessment_worker.assessment_error.connect(
            self._on_assessment_error
        )
        self.assessment_worker.start()

    def _reset_progress_labels(self) -> None:
        """Reset all progress labels to pending state."""
        for dim in ALL_DIMENSIONS:
            display_name = format_dimension_name(dim)
            self.progress_labels[dim].setText(
                f"{PROGRESS_PENDING} {display_name}: Pending"
            )

    def _update_progress_label(
        self,
        dimension: str,
        status: str,
        score: Optional[float] = None
    ) -> None:
        """Update a progress label."""
        display_name = format_dimension_name(dimension)
        if score is not None:
            text = f"{status} {display_name}: {format_score_with_max(score)}"
        elif status == PROGRESS_PENDING:
            text = f"{status} {display_name}: Pending"
        else:
            text = f"{status} {display_name}: Analyzing..."

        self.progress_labels[dimension].setText(text)

    def _on_progress_update(self, dimension: str, status: str) -> None:
        """Handle progress update from worker thread."""
        self._update_progress_label(dimension, status)

    def _on_assessment_complete(self, result: PaperWeightResult) -> None:
        """Handle completed assessment."""
        self.current_result = result

        # Update progress labels to completed with scores
        for dim in ALL_DIMENSIONS:
            dim_score = getattr(result, dim)
            self._update_progress_label(dim, PROGRESS_COMPLETE, dim_score.score)

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

        # Populate audit trail (with full tooltips and click-to-view)
        self.audit_section.populate_from_result(result)

        # Enable buttons
        self.assess_button.setEnabled(True)
        self.force_reassess_button.setEnabled(True)
        self.export_report_button.setEnabled(True)
        self.export_json_button.setEnabled(True)

        # Refresh recent assessments
        self._load_recent_assessments()

    def _on_assessment_error(self, error_message: str) -> None:
        """Handle assessment error."""
        QMessageBox.critical(
            self,
            "Assessment Error",
            f"Error during assessment:\n{error_message}"
        )

        # Mark progress as error
        for dim in ALL_DIMENSIONS:
            display_name = format_dimension_name(dim)
            self.progress_labels[dim].setText(
                f"{PROGRESS_ERROR} {display_name}: Error"
            )

        # Re-enable buttons
        self.assess_button.setEnabled(True)
        self.force_reassess_button.setEnabled(True)

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

    def _reset_for_new_assessment(self) -> None:
        """Reset GUI for new assessment."""
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

        # Reset progress
        self._reset_progress_labels()

        # Hide results
        self.results_section.hide()
        self.audit_section.clear()

        # Reset buttons
        self.assess_button.setEnabled(False)
        self.force_reassess_button.setEnabled(False)
        self.export_report_button.setEnabled(False)
        self.export_json_button.setEnabled(False)

        # Clear search input
        self.search_input.clear()

        # Reset recent dropdown
        self.recent_combo.setCurrentIndex(0)


def main() -> None:
    """Main entry point for the Paper Weight Laboratory."""
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    app = QApplication(sys.argv)
    app.setStyle('Fusion')

    lab = PaperWeightLab()
    lab.show()

    sys.exit(app.exec())


__all__ = ['PaperWeightLab', 'main']
