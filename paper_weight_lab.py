"""
Paper Weight Assessment Laboratory - PySide6 GUI

Battle testing interface for paper weight assessment with full
visual inspection of all assessment steps and audit trails.

This module provides:
- Document selection via search or recent assessments
- Real-time progress tracking during assessment
- Visual results display with dimension breakdown
- Expandable audit trail tree
- Export to Markdown and JSON formats
- Weight configuration dialog

Usage:
    uv run python paper_weight_lab.py
"""

import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Callable

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QComboBox, QTextEdit,
    QTreeWidget, QTreeWidgetItem, QGroupBox, QProgressBar,
    QSplitter, QMessageBox, QFileDialog, QDialog, QDialogButtonBox,
    QSlider, QFormLayout, QFrame, QScrollArea
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QFont

from bmlibrarian.agents.paper_weight_agent import (
    PaperWeightAssessmentAgent,
)
from bmlibrarian.agents.paper_weight_models import (
    PaperWeightResult,
    DimensionScore,
    AssessmentDetail,
    ALL_DIMENSIONS,
    DIMENSION_STUDY_DESIGN,
    DIMENSION_SAMPLE_SIZE,
    DIMENSION_METHODOLOGICAL_QUALITY,
    DIMENSION_RISK_OF_BIAS,
    DIMENSION_REPLICATION_STATUS,
)
from bmlibrarian.agents.paper_weight_db import (
    search_documents,
    get_recent_assessments,
    get_document_metadata,
    SEARCH_RESULT_LIMIT,
    RECENT_ASSESSMENTS_LIMIT,
)

# Import styling infrastructure
from bmlibrarian.gui.qt.resources.styles.dpi_scale import (
    FontScale,
    get_font_scale,
    get_scale_value,
)
from bmlibrarian.gui.qt.resources.styles.stylesheet_generator import (
    StylesheetGenerator,
    get_stylesheet_generator,
)


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

# Window dimensions (will be scaled by DPI)
WINDOW_MIN_WIDTH = 1000
WINDOW_MIN_HEIGHT = 700
WINDOW_DEFAULT_WIDTH = 1200
WINDOW_DEFAULT_HEIGHT = 900

# Progress indicator symbols
PROGRESS_PENDING = "⊡"
PROGRESS_ANALYZING = "⟳"
PROGRESS_COMPLETE = "✓"
PROGRESS_ERROR = "✗"

# Score formatting
SCORE_MAX = 10.0
SCORE_DECIMALS = 2

# Tree column indices
TREE_COL_COMPONENT = 0
TREE_COL_VALUE = 1
TREE_COL_SCORE = 2
TREE_COL_EVIDENCE = 3

# Tree column widths (character-based, will be scaled)
TREE_COL_WIDTH_COMPONENT = 25
TREE_COL_WIDTH_VALUE = 20
TREE_COL_WIDTH_SCORE = 10


# Weight slider range
WEIGHT_SLIDER_MIN = 0
WEIGHT_SLIDER_MAX = 100
WEIGHT_SLIDER_PRECISION = 100  # Divide by this to get actual weight

# Evidence text truncation for tree display
EVIDENCE_DISPLAY_MAX_LENGTH = 100
REASONING_DISPLAY_MAX_LENGTH = 200


# =============================================================================
# Worker Thread
# =============================================================================

class AssessmentWorker(QThread):
    """
    Background worker thread for paper weight assessment.

    Runs assessment in a separate thread to keep GUI responsive during
    LLM calls which can take several seconds.

    Signals:
        progress_update: Emitted when a dimension assessment starts
        assessment_complete: Emitted with PaperWeightResult when done
        assessment_error: Emitted with error message on failure
    """

    # Signals for thread-safe GUI updates
    progress_update = Signal(str, str)  # (dimension_name, status)
    assessment_complete = Signal(object)  # PaperWeightResult
    assessment_error = Signal(str)  # error_message

    def __init__(
        self,
        agent: PaperWeightAssessmentAgent,
        document_id: int,
        force_reassess: bool = False
    ):
        """
        Initialize assessment worker.

        Args:
            agent: PaperWeightAssessmentAgent instance
            document_id: Database ID of document to assess
            force_reassess: If True, skip cache and re-assess
        """
        super().__init__()
        self.agent = agent
        self.document_id = document_id
        self.force_reassess = force_reassess

    def run(self) -> None:
        """Run assessment in background thread."""
        try:
            # Emit progress for each dimension as we start
            for dim in ALL_DIMENSIONS:
                self.progress_update.emit(dim, PROGRESS_ANALYZING)

            # Perform assessment
            result = self.agent.assess_paper(
                self.document_id,
                force_reassess=self.force_reassess
            )

            # Emit completion signal
            self.assessment_complete.emit(result)

        except Exception as e:
            logger.error(f"Assessment worker error: {e}")
            self.assessment_error.emit(str(e))


# =============================================================================
# Dialogs
# =============================================================================

class DimensionWeightDialog(QDialog):
    """
    Dialog for configuring dimension weights.

    Provides sliders for each dimension weight with real-time validation
    that weights sum to 1.0.
    """

    def __init__(
        self,
        current_weights: Dict[str, float],
        parent: Optional[QWidget] = None
    ):
        """
        Initialize weight configuration dialog.

        Args:
            current_weights: Current dimension weights dictionary
            parent: Parent widget
        """
        super().__init__(parent)
        self.setWindowTitle("Configure Dimension Weights")

        # Get scaling values
        self.scale = get_font_scale()
        self.styles = get_stylesheet_generator()

        self.setMinimumWidth(self.scale['control_width_xlarge'])

        self.weights = current_weights.copy()
        self.sliders: Dict[str, QSlider] = {}
        self.value_labels: Dict[str, QLabel] = {}

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Setup dialog user interface."""
        layout = QFormLayout()
        layout.setSpacing(self.scale['spacing_medium'])

        # Create slider for each dimension
        for dim_name, weight in self.weights.items():
            slider = QSlider(Qt.Horizontal)
            slider.setMinimum(WEIGHT_SLIDER_MIN)
            slider.setMaximum(WEIGHT_SLIDER_MAX)
            slider.setValue(int(weight * WEIGHT_SLIDER_PRECISION))
            slider.valueChanged.connect(self._on_weight_changed)

            value_label = QLabel(f"{weight:.2f}")
            value_label.setMinimumWidth(self.scale['control_width_tiny'])

            h_layout = QHBoxLayout()
            h_layout.addWidget(slider, stretch=1)
            h_layout.addWidget(value_label)

            # Format dimension name for display
            display_name = dim_name.replace('_', ' ').title()
            layout.addRow(f"{display_name}:", h_layout)

            self.sliders[dim_name] = slider
            self.value_labels[dim_name] = value_label

        # Warning/status label
        self.status_label = QLabel()
        self.status_label.setStyleSheet(self.styles.label_stylesheet(
            font_size_key='font_small',
            color='#666'
        ))
        layout.addRow(self.status_label)

        # Update status initially
        self._update_status()

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

        self.setLayout(layout)

    def _on_weight_changed(self) -> None:
        """Handle slider value changes."""
        # Update value labels
        for dim_name, slider in self.sliders.items():
            value = slider.value() / WEIGHT_SLIDER_PRECISION
            self.value_labels[dim_name].setText(f"{value:.2f}")

        self._update_status()

    def _update_status(self) -> None:
        """Update status label with weight sum validation."""
        total = sum(
            slider.value() / WEIGHT_SLIDER_PRECISION
            for slider in self.sliders.values()
        )

        # Check if weights sum to 1.0 (with small tolerance)
        tolerance = 0.01
        if abs(total - 1.0) <= tolerance:
            self.status_label.setText(f"{PROGRESS_COMPLETE} Weights sum to 1.0")
            self.status_label.setStyleSheet(self.styles.label_stylesheet(
                font_size_key='font_small',
                color='green'
            ))
        else:
            self.status_label.setText(
                f"⚠ Weights sum to {total:.2f} (must be 1.0)"
            )
            self.status_label.setStyleSheet(self.styles.label_stylesheet(
                font_size_key='font_small',
                color='orange'
            ))

    def _validate_and_accept(self) -> None:
        """Validate weights sum to 1.0 before accepting."""
        total = sum(
            slider.value() / WEIGHT_SLIDER_PRECISION
            for slider in self.sliders.values()
        )

        tolerance = 0.01
        if abs(total - 1.0) > tolerance:
            QMessageBox.warning(
                self,
                "Invalid Weights",
                f"Weights must sum to 1.0 (currently {total:.2f}).\n"
                "Please adjust the sliders."
            )
            return

        self.accept()

    def get_weights(self) -> Dict[str, float]:
        """
        Get configured weights.

        Returns:
            Dictionary mapping dimension names to their weights
        """
        return {
            dim: slider.value() / WEIGHT_SLIDER_PRECISION
            for dim, slider in self.sliders.items()
        }


class DocumentSearchDialog(QDialog):
    """
    Dialog for searching and selecting documents.

    Provides a search interface with results list.
    """

    def __init__(self, parent: Optional[QWidget] = None):
        """
        Initialize document search dialog.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)
        self.setWindowTitle("Search Documents")

        self.scale = get_font_scale()
        self.styles = get_stylesheet_generator()

        self.setMinimumWidth(self.scale['control_width_xlarge'] * 2)
        self.setMinimumHeight(self.scale['control_height_xlarge'] * 10)

        self.selected_document_id: Optional[int] = None
        self.search_results: List[Dict] = []

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Setup dialog user interface."""
        layout = QVBoxLayout()
        layout.setSpacing(self.scale['spacing_medium'])

        # Search input
        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(
            "Enter PMID, DOI, or title keywords..."
        )
        self.search_input.returnPressed.connect(self._do_search)
        search_layout.addWidget(self.search_input, stretch=1)

        search_btn = QPushButton("Search")
        search_btn.clicked.connect(self._do_search)
        search_btn.setStyleSheet(self.styles.button_stylesheet(
            bg_color="#2196F3"
        ))
        search_layout.addWidget(search_btn)

        layout.addLayout(search_layout)

        # Results list
        self.results_list = QTreeWidget()
        self.results_list.setHeaderLabels(["ID", "Title", "PMID", "Year"])
        self.results_list.setColumnWidth(0, self.scale['char_width'] * 8)
        self.results_list.setColumnWidth(1, self.scale['char_width'] * 60)
        self.results_list.setColumnWidth(2, self.scale['char_width'] * 12)
        self.results_list.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self.results_list)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self._select_document)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

        self.setLayout(layout)

    def _do_search(self) -> None:
        """Perform document search."""
        query = self.search_input.text().strip()
        if not query:
            return

        self.results_list.clear()
        self.search_results = search_documents(query)

        for doc in self.search_results:
            item = QTreeWidgetItem([
                str(doc['id']),
                doc['title'] or 'No title',
                str(doc['pmid'] or ''),
                str(doc['year'] or '')
            ])
            self.results_list.addTopLevelItem(item)

        if not self.search_results:
            QMessageBox.information(
                self,
                "No Results",
                f"No documents found matching: {query}"
            )

    def _on_item_double_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        """Handle double-click on result item."""
        self._select_document()

    def _select_document(self) -> None:
        """Select current document and close dialog."""
        current = self.results_list.currentItem()
        if current:
            self.selected_document_id = int(current.text(0))
            self.accept()
        else:
            QMessageBox.warning(
                self,
                "No Selection",
                "Please select a document from the list."
            )

    def get_selected_document_id(self) -> Optional[int]:
        """
        Get the selected document ID.

        Returns:
            Selected document ID or None if nothing selected
        """
        return self.selected_document_id


# =============================================================================
# Main Window
# =============================================================================

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

        # Audit trail tree
        self.audit_section = self._create_audit_trail_section()
        splitter.addWidget(self.audit_section)

        # Set initial splitter sizes
        splitter.setSizes([200, 300])
        main_layout.addWidget(splitter, stretch=1)

        # Bottom buttons
        main_layout.addWidget(self._create_bottom_buttons())

    def _create_document_selection(self) -> QGroupBox:
        """
        Create document selection widgets.

        Returns:
            QGroupBox containing search and recent assessments controls
        """
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
        """
        Create document information display.

        Returns:
            QGroupBox containing document metadata display
        """
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
        """
        Create action button row.

        Returns:
            QWidget containing action buttons
        """
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
        """
        Create assessment progress display.

        Returns:
            QGroupBox containing progress indicators for each dimension
        """
        group = QGroupBox("Assessment Progress")
        layout = QVBoxLayout()
        layout.setSpacing(self.scale['spacing_small'])

        self.progress_labels: Dict[str, QLabel] = {}

        for dim in ALL_DIMENSIONS:
            display_name = dim.replace('_', ' ').title()
            label = QLabel(f"{PROGRESS_PENDING} {display_name}: Pending")
            label.setStyleSheet(self.styles.label_stylesheet(
                font_size_key='font_normal'
            ))
            self.progress_labels[dim] = label
            layout.addWidget(label)

        group.setLayout(layout)
        return group

    def _create_results_section(self) -> QGroupBox:
        """
        Create results visualization section.

        Returns:
            QGroupBox containing score breakdown and visualization
        """
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
            display_name = dim.replace('_', ' ').title()
            label = QLabel(f"{display_name}: --/10")
            label.setStyleSheet(self.styles.label_stylesheet(
                font_size_key='font_normal'
            ))
            self.dimension_score_labels[dim] = label
            summary_layout.addWidget(label)

        summary_layout.addStretch()
        layout.addLayout(summary_layout)

        # Right: Visual representation (placeholder for future radar chart)
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

    def _create_audit_trail_section(self) -> QGroupBox:
        """
        Create audit trail tree view section.

        Returns:
            QGroupBox containing expandable audit trail tree
        """
        group = QGroupBox("Audit Trail")
        layout = QVBoxLayout()

        self.audit_tree = QTreeWidget()
        self.audit_tree.setHeaderLabels([
            "Component", "Value", "Score", "Evidence"
        ])
        self.audit_tree.setColumnWidth(
            TREE_COL_COMPONENT,
            self.scale['char_width'] * TREE_COL_WIDTH_COMPONENT
        )
        self.audit_tree.setColumnWidth(
            TREE_COL_VALUE,
            self.scale['char_width'] * TREE_COL_WIDTH_VALUE
        )
        self.audit_tree.setColumnWidth(
            TREE_COL_SCORE,
            self.scale['char_width'] * TREE_COL_WIDTH_SCORE
        )
        self.audit_tree.setAlternatingRowColors(True)

        layout.addWidget(self.audit_tree)

        group.setLayout(layout)
        return group

    def _create_bottom_buttons(self) -> QWidget:
        """
        Create bottom action buttons.

        Returns:
            QWidget containing export and navigation buttons
        """
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
            display_text = (
                f"[{item['final_weight']:.1f}] "
                f"{item['title'][:60]}{'...' if len(item['title'] or '') > 60 else ''}"
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
        """
        Load document metadata and update display.

        Args:
            document_id: Database ID of document to load
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

        meta_parts = []
        if meta.get('authors'):
            # Truncate authors if too long
            authors = meta['authors']
            if len(authors) > 100:
                authors = authors[:100] + '...'
            meta_parts.append(authors)
        if meta.get('year'):
            meta_parts.append(str(meta['year']))
        if meta.get('pmid'):
            meta_parts.append(f"PMID: {meta['pmid']}")
        if meta.get('doi'):
            meta_parts.append(f"DOI: {meta['doi']}")

        self.doc_meta_label.setText(' | '.join(meta_parts))

        # Set abstract
        self.abstract_text.setText(meta.get('abstract') or 'No abstract available')

        # Enable buttons
        self.view_abstract_button.setEnabled(True)
        self.assess_button.setEnabled(self.agent is not None)
        self.force_reassess_button.setEnabled(self.agent is not None)

        # Hide results from previous assessment
        self.results_section.hide()
        self.audit_tree.clear()

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
        """
        Start paper weight assessment.

        Args:
            force: If True, skip cache and force re-assessment
        """
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
        self.audit_tree.clear()

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

        # Update first dimension to analyzing
        first_dim = ALL_DIMENSIONS[0]
        self._update_progress_label(first_dim, PROGRESS_ANALYZING)

    def _reset_progress_labels(self) -> None:
        """Reset all progress labels to pending state."""
        for dim in ALL_DIMENSIONS:
            display_name = dim.replace('_', ' ').title()
            self.progress_labels[dim].setText(
                f"{PROGRESS_PENDING} {display_name}: Pending"
            )

    def _update_progress_label(
        self,
        dimension: str,
        status: str,
        score: Optional[float] = None
    ) -> None:
        """
        Update a progress label.

        Args:
            dimension: Dimension name
            status: Status indicator symbol
            score: Optional score to display
        """
        display_name = dimension.replace('_', ' ').title()
        if score is not None:
            text = f"{status} {display_name}: {score:.1f}/10"
        elif status == PROGRESS_ANALYZING:
            text = f"{status} {display_name}: Analyzing..."
        else:
            text = f"{status} {display_name}: Pending"

        self.progress_labels[dimension].setText(text)

    def _on_progress_update(self, dimension: str, status: str) -> None:
        """
        Handle progress update from worker thread.

        Args:
            dimension: Dimension being processed
            status: Current status
        """
        self._update_progress_label(dimension, status)

    def _on_assessment_complete(self, result: PaperWeightResult) -> None:
        """
        Handle completed assessment.

        Args:
            result: PaperWeightResult from assessment
        """
        self.current_result = result

        # Update progress labels to completed with scores
        for dim in ALL_DIMENSIONS:
            dim_score = getattr(result, dim)
            self._update_progress_label(dim, PROGRESS_COMPLETE, dim_score.score)

        # Show and populate results
        self.results_section.show()
        self.final_weight_label.setText(
            f"Final Weight: {result.final_weight:.{SCORE_DECIMALS}f}/10"
        )
        self.version_label.setText(f"Version: {result.assessor_version}")
        self.assessed_label.setText(
            f"Assessed: {result.assessed_at.strftime('%Y-%m-%d %H:%M')}"
        )

        for dim in ALL_DIMENSIONS:
            dim_score = getattr(result, dim)
            display_name = dim.replace('_', ' ').title()
            self.dimension_score_labels[dim].setText(
                f"{display_name}: {dim_score.score:.1f}/10"
            )

        # Populate audit trail
        self._populate_audit_trail(result)

        # Enable buttons
        self.assess_button.setEnabled(True)
        self.force_reassess_button.setEnabled(True)
        self.export_report_button.setEnabled(True)
        self.export_json_button.setEnabled(True)

        # Refresh recent assessments
        self._load_recent_assessments()

    def _on_assessment_error(self, error_message: str) -> None:
        """
        Handle assessment error.

        Args:
            error_message: Error description
        """
        QMessageBox.critical(
            self,
            "Assessment Error",
            f"Error during assessment:\n{error_message}"
        )

        # Mark progress as error
        for dim in ALL_DIMENSIONS:
            display_name = dim.replace('_', ' ').title()
            self.progress_labels[dim].setText(
                f"{PROGRESS_ERROR} {display_name}: Error"
            )

        # Re-enable buttons
        self.assess_button.setEnabled(True)
        self.force_reassess_button.setEnabled(True)

    def _populate_audit_trail(self, result: PaperWeightResult) -> None:
        """
        Populate audit trail tree with assessment details.

        Args:
            result: PaperWeightResult to display
        """
        self.audit_tree.clear()

        for dim in ALL_DIMENSIONS:
            dim_score = getattr(result, dim)
            display_name = dim.replace('_', ' ').title()

            # Create dimension root item
            dim_item = QTreeWidgetItem(self.audit_tree)
            dim_item.setText(TREE_COL_COMPONENT, display_name)
            dim_item.setText(TREE_COL_SCORE, f"{dim_score.score:.{SCORE_DECIMALS}f}")

            # Make dimension item bold
            font = dim_item.font(TREE_COL_COMPONENT)
            font.setBold(True)
            dim_item.setFont(TREE_COL_COMPONENT, font)

            # Add details as children
            for detail in dim_score.details:
                detail_item = QTreeWidgetItem(dim_item)
                detail_item.setText(TREE_COL_COMPONENT, detail.component)
                detail_item.setText(
                    TREE_COL_VALUE,
                    str(detail.extracted_value) if detail.extracted_value else ''
                )
                detail_item.setText(
                    TREE_COL_SCORE,
                    f"{detail.score_contribution:.{SCORE_DECIMALS}f}"
                )

                # Truncate evidence for display
                if detail.evidence_text:
                    evidence = detail.evidence_text
                    if len(evidence) > EVIDENCE_DISPLAY_MAX_LENGTH:
                        evidence = evidence[:EVIDENCE_DISPLAY_MAX_LENGTH] + '...'
                    detail_item.setText(TREE_COL_EVIDENCE, evidence)

                # Add reasoning as child if present
                if detail.reasoning:
                    reasoning_item = QTreeWidgetItem(detail_item)
                    reasoning_item.setText(TREE_COL_COMPONENT, "Reasoning:")

                    reasoning = detail.reasoning
                    if len(reasoning) > REASONING_DISPLAY_MAX_LENGTH:
                        reasoning = reasoning[:REASONING_DISPLAY_MAX_LENGTH] + '...'
                    reasoning_item.setText(TREE_COL_EVIDENCE, reasoning)

                    # Style reasoning in italic
                    font = reasoning_item.font(TREE_COL_COMPONENT)
                    font.setItalic(True)
                    reasoning_item.setFont(TREE_COL_COMPONENT, font)

        # Expand all by default
        self.audit_tree.expandAll()

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
                # Convert datetime to ISO format for JSON
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
        self.audit_tree.clear()

        # Reset buttons
        self.assess_button.setEnabled(False)
        self.force_reassess_button.setEnabled(False)
        self.export_report_button.setEnabled(False)
        self.export_json_button.setEnabled(False)

        # Clear search input
        self.search_input.clear()

        # Reset recent dropdown
        self.recent_combo.setCurrentIndex(0)


# =============================================================================
# Main Entry Point
# =============================================================================

def main() -> None:
    """Main entry point for the Paper Weight Laboratory."""
    app = QApplication(sys.argv)

    # Set application style
    app.setStyle('Fusion')

    # Create and show main window
    lab = PaperWeightLab()
    lab.show()

    sys.exit(app.exec())


if __name__ == '__main__':
    main()
