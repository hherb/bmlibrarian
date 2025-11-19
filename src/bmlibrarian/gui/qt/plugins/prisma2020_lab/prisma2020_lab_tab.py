"""
PRISMA 2020 Lab Tab Widget for BMLibrarian Qt GUI.

Interactive interface for assessing systematic reviews and meta-analyses
against PRISMA 2020 reporting guidelines using PRISMA2020Agent.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QGroupBox, QLineEdit, QComboBox, QSplitter,
    QMessageBox, QScrollArea
)
from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtGui import QFont, QIntValidator
from typing import Optional, Dict, Any

from bmlibrarian.agents import PRISMA2020Agent, AgentOrchestrator
from bmlibrarian.agents.prisma2020_agent import PRISMA2020Assessment
from bmlibrarian.config import get_config
from bmlibrarian.database import fetch_documents_by_ids
from ...resources.styles import get_font_scale, scale_px, StylesheetGenerator


# Color constants for scoring
SCORE_COLORS = {
    0.0: '#D32F2F',    # Red - Not reported
    1.0: '#F57C00',    # Orange - Partially reported
    2.0: '#388E3C',    # Green - Fully reported
}

COMPLIANCE_COLORS = {
    'excellent': '#1B5E20',  # Dark green (≥90%)
    'good': '#388E3C',       # Green (75-89%)
    'adequate': '#F57C00',   # Orange (60-74%)
    'poor': '#E65100',       # Dark orange (40-59%)
    'very_poor': '#B71C1C',  # Dark red (<40%)
}

SECTION_COLORS = {
    'title': '#1976D2',
    'info': '#1976D2',
    'success': '#2E7D32',
    'error': '#C62828',
}


class PRISMA2020AssessmentWorker(QThread):
    """Worker thread for PRISMA 2020 assessment to prevent UI blocking."""

    result_ready = Signal(object)  # PRISMA2020Assessment object
    error_occurred = Signal(str)

    def __init__(self, prisma_agent: PRISMA2020Agent, document: Dict[str, Any]):
        """
        Initialize worker thread.

        Args:
            prisma_agent: PRISMA2020Agent instance
            document: Document dictionary
        """
        super().__init__()
        self.prisma_agent = prisma_agent
        self.document = document

    def run(self):
        """Execute PRISMA 2020 assessment in background thread."""
        try:
            assessment = self.prisma_agent.assess_prisma_compliance(
                document=self.document,
                min_confidence=0.0  # Show all assessments in lab mode
            )
            if assessment:
                self.result_ready.emit(assessment)
            else:
                self.error_occurred.emit("PRISMA 2020 assessment returned no results (document may not be a systematic review)")
        except Exception as e:
            self.error_occurred.emit(str(e))


class PRISMA2020LabTabWidget(QWidget):
    """Main PRISMA 2020 Lab tab widget."""

    status_message = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None):
        """
        Initialize PRISMA 2020 Lab tab.

        Args:
            parent: Optional parent widget
        """
        super().__init__(parent)

        self.scale = get_font_scale()
        self.stylesheet_gen = StylesheetGenerator()
        self.config = get_config()
        self.prisma_agent: Optional[PRISMA2020Agent] = None
        self.orchestrator: Optional[AgentOrchestrator] = None
        self.worker: Optional[PRISMA2020AssessmentWorker] = None
        self.current_document: Optional[Dict[str, Any]] = None
        self.current_assessment: Optional[PRISMA2020Assessment] = None

        # UI Components
        self.model_combo: Optional[QComboBox] = None
        self.doc_id_input: Optional[QLineEdit] = None
        self.load_button: Optional[QPushButton] = None
        self.clear_button: Optional[QPushButton] = None
        self.refresh_button: Optional[QPushButton] = None

        # Document display
        self.doc_title_label: Optional[QLabel] = None
        self.doc_metadata_label: Optional[QLabel] = None
        self.doc_abstract_edit: Optional[QTextEdit] = None

        # Assessment results
        self.assessment_scroll: Optional[QScrollArea] = None
        self.assessment_widget: Optional[QWidget] = None
        self.assessment_layout: Optional[QVBoxLayout] = None

        self.status_label: Optional[QLabel] = None

        self._init_agent()
        self._setup_ui()

    def _init_agent(self):
        """Initialize PRISMA2020Agent with orchestrator."""
        try:
            self.orchestrator = AgentOrchestrator(max_workers=2)

            # Get configuration
            default_model = self.config.get_model('prisma2020_agent') or "gpt-oss:20b"
            agent_config = self.config.get_agent_config('prisma2020') or {}
            host = self.config.get_ollama_config()['host']

            self.prisma_agent = PRISMA2020Agent(
                model=default_model,
                host=host,
                temperature=agent_config.get('temperature', 0.1),
                top_p=agent_config.get('top_p', 0.9),
                max_tokens=agent_config.get('max_tokens', 4000),
                orchestrator=self.orchestrator,
                show_model_info=True
            )
            print(f"✓ PRISMA2020Agent initialized with model: {default_model}")
        except Exception as e:
            print(f"Warning: Failed to initialize PRISMA2020Agent: {e}")
            self.prisma_agent = None

    def _setup_ui(self):
        """Setup the user interface."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(scale_px(20), scale_px(20), scale_px(20), scale_px(20))
        main_layout.setSpacing(scale_px(15))

        # Header
        header = self._create_header()
        main_layout.addWidget(header)

        # Input panel
        input_panel = self._create_input_panel()
        main_layout.addWidget(input_panel)

        # Splitter for document and assessment panels
        splitter = QSplitter(Qt.Horizontal)

        # Left: Document display
        doc_panel = self._create_document_panel()
        splitter.addWidget(doc_panel)

        # Right: Assessment results
        assessment_panel = self._create_assessment_panel()
        splitter.addWidget(assessment_panel)

        # Set initial sizes (40% document, 60% assessment)
        splitter.setSizes([400, 600])

        main_layout.addWidget(splitter, stretch=1)

        # Status bar
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet(
            self.stylesheet_gen.label_stylesheet(
                font_size_key='font_small',
                color='gray'
            )
        )
        main_layout.addWidget(self.status_label)

    def _create_header(self) -> QWidget:
        """Create header section."""
        header_widget = QWidget()
        header_layout = QVBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(scale_px(5))

        title = QLabel("PRISMA 2020 Laboratory")
        title.setFont(QFont("", 10, QFont.Bold))
        title.setStyleSheet(
            self.stylesheet_gen.label_stylesheet(
                font_size_key='font_large',
                color=SECTION_COLORS['title'],
                bold=True
            )
        )

        subtitle = QLabel(
            "Assess systematic reviews and meta-analyses against PRISMA 2020 reporting guidelines"
        )
        subtitle.setStyleSheet(
            self.stylesheet_gen.label_stylesheet(
                font_size_key='font_medium',
                color='gray'
            )
        )

        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)

        return header_widget

    def _create_input_panel(self) -> QGroupBox:
        """Create input panel for document loading."""
        group = QGroupBox("Document Input")
        layout = QVBoxLayout(group)
        layout.setSpacing(scale_px(10))

        # Model selection row
        model_row = self._create_model_selection_row()
        layout.addLayout(model_row)

        # Document ID input row
        input_row = self._create_document_input_row()
        layout.addLayout(input_row)

        return group

    def _create_model_selection_row(self) -> QHBoxLayout:
        """Create model selection row."""
        model_row = QHBoxLayout()

        model_label = QLabel("PRISMA Model:")
        model_label.setFont(QFont("", 10, QFont.Bold))

        self.model_combo = QComboBox()
        self.model_combo.setMinimumWidth(scale_px(300))
        self._refresh_models()
        self.model_combo.currentTextChanged.connect(self._on_model_changed)

        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self._refresh_models)
        self.refresh_button.setMaximumWidth(scale_px(80))
        self.refresh_button.setStyleSheet(
            self.stylesheet_gen.button_stylesheet()
        )

        model_row.addWidget(model_label)
        model_row.addWidget(self.model_combo)
        model_row.addWidget(self.refresh_button)
        model_row.addStretch()

        return model_row

    def _create_document_input_row(self) -> QHBoxLayout:
        """Create document ID input row."""
        input_row = QHBoxLayout()

        doc_id_label = QLabel("Document ID:")
        self.doc_id_input = QLineEdit()
        self.doc_id_input.setPlaceholderText("Enter document ID (e.g., 12345)")
        self.doc_id_input.setMaximumWidth(scale_px(200))
        self.doc_id_input.setValidator(QIntValidator(1, 999999999))
        self.doc_id_input.returnPressed.connect(self._load_document)
        self.doc_id_input.setStyleSheet(
            self.stylesheet_gen.input_stylesheet()
        )

        self.load_button = QPushButton("Load & Assess")
        self.load_button.clicked.connect(self._load_document)
        self.load_button.setMinimumHeight(scale_px(35))
        self.load_button.setMaximumWidth(scale_px(150))
        self.load_button.setStyleSheet(
            self.stylesheet_gen.button_stylesheet(
                bg_color='#43A047',
                hover_color='#2E7D32'
            )
        )

        self.clear_button = QPushButton("Clear")
        self.clear_button.clicked.connect(self._clear_all)
        self.clear_button.setMaximumWidth(scale_px(80))
        self.clear_button.setMinimumHeight(scale_px(35))
        self.clear_button.setStyleSheet(
            self.stylesheet_gen.button_stylesheet()
        )

        input_row.addWidget(doc_id_label)
        input_row.addWidget(self.doc_id_input)
        input_row.addWidget(self.load_button)
        input_row.addWidget(self.clear_button)
        input_row.addStretch()

        return input_row

    def _create_document_panel(self) -> QGroupBox:
        """Create document display panel."""
        group = QGroupBox("Document")
        layout = QVBoxLayout(group)
        layout.setSpacing(scale_px(10))

        # Title
        self.doc_title_label = QLabel("No document loaded")
        self.doc_title_label.setFont(QFont("", 10, QFont.Bold))
        self.doc_title_label.setWordWrap(True)
        self.doc_title_label.setStyleSheet(
            self.stylesheet_gen.label_stylesheet(
                font_size_key='font_medium',
                color='#424242',
                bold=True
            )
        )

        # Metadata
        self.doc_metadata_label = QLabel("")
        self.doc_metadata_label.setWordWrap(True)
        self.doc_metadata_label.setStyleSheet(
            self.stylesheet_gen.label_stylesheet(
                font_size_key='font_small',
                color='gray'
            )
        )

        # Abstract
        abstract_label = QLabel("Abstract:")
        abstract_label.setFont(QFont("", 10, QFont.Bold))

        self.doc_abstract_edit = QTextEdit()
        self.doc_abstract_edit.setReadOnly(True)
        self.doc_abstract_edit.setPlaceholderText("Document abstract will appear here...")
        self.doc_abstract_edit.setStyleSheet(
            self.stylesheet_gen.input_stylesheet()
        )

        layout.addWidget(self.doc_title_label)
        layout.addWidget(self.doc_metadata_label)
        layout.addSpacing(scale_px(10))
        layout.addWidget(abstract_label)
        layout.addWidget(self.doc_abstract_edit)

        return group

    def _create_assessment_panel(self) -> QGroupBox:
        """Create assessment results display panel."""
        group = QGroupBox("PRISMA 2020 Assessment")
        layout = QVBoxLayout(group)
        layout.setSpacing(scale_px(10))

        # Scrollable assessment results
        self.assessment_scroll = QScrollArea()
        self.assessment_scroll.setWidgetResizable(True)
        self.assessment_scroll.setFrameShape(QScrollArea.NoFrame)

        self.assessment_widget = QWidget()
        self.assessment_layout = QVBoxLayout(self.assessment_widget)
        self.assessment_layout.setSpacing(scale_px(10))
        self.assessment_layout.setAlignment(Qt.AlignTop)

        placeholder = QLabel("Assessment results will appear here after loading a document.")
        placeholder.setStyleSheet(
            self.stylesheet_gen.label_stylesheet(
                font_size_key='font_medium',
                color='gray'
            )
        )
        self.assessment_layout.addWidget(placeholder)

        self.assessment_scroll.setWidget(self.assessment_widget)
        layout.addWidget(self.assessment_scroll)

        return group

    def _refresh_models(self):
        """Refresh available models from Ollama using the agent's method."""
        if not self.prisma_agent:
            QMessageBox.warning(
                self,
                "Agent Error",
                "PRISMA agent not initialized. Cannot refresh models."
            )
            return

        try:
            # Use agent's get_available_models method (uses ollama library internally)
            models = self.prisma_agent.get_available_models()

            current = self.model_combo.currentText()
            self.model_combo.clear()
            self.model_combo.addItems(models)

            # Restore selection if possible
            if current in models:
                self.model_combo.setCurrentText(current)
            else:
                # Set to configured model
                default_model = self.config.get_model('prisma2020_agent') or "gpt-oss:20b"
                if default_model in models:
                    self.model_combo.setCurrentText(default_model)

            self.status_message.emit(f"Refreshed models - {len(models)} available")
        except ConnectionError as e:
            QMessageBox.warning(
                self,
                "Connection Error",
                f"Failed to connect to Ollama: {str(e)}\n\nPlease ensure Ollama is running."
            )
        except Exception as e:
            QMessageBox.warning(
                self,
                "Error",
                f"Unexpected error while refreshing models: {str(e)}"
            )

    def _on_model_changed(self, model_name: str):
        """Handle model selection change."""
        if not model_name or not self.prisma_agent:
            return

        try:
            # Reinitialize agent with new model
            agent_config = self.config.get_agent_config('prisma2020') or {}
            host = self.config.get_ollama_config()['host']

            self.prisma_agent = PRISMA2020Agent(
                model=model_name,
                host=host,
                temperature=agent_config.get('temperature', 0.1),
                top_p=agent_config.get('top_p', 0.9),
                max_tokens=agent_config.get('max_tokens', 4000),
                orchestrator=self.orchestrator,
                show_model_info=True
            )
            self.status_message.emit(f"Switched to model: {model_name}")
        except ConnectionError as e:
            QMessageBox.warning(
                self,
                "Connection Error",
                f"Failed to connect to Ollama with model {model_name}: {str(e)}"
            )
        except Exception as e:
            QMessageBox.warning(
                self,
                "Error",
                f"Failed to switch model: {str(e)}"
            )

    def _load_document(self):
        """Load document and perform PRISMA 2020 assessment."""
        doc_id_str = self.doc_id_input.text().strip()

        if not doc_id_str:
            QMessageBox.warning(self, "Input Error", "Please enter a document ID.")
            return

        try:
            doc_id = int(doc_id_str)
        except ValueError:
            QMessageBox.warning(
                self,
                "Input Error",
                "Invalid document ID. Please enter a number."
            )
            return

        # Update status
        self._update_status(f"Loading document {doc_id}...", SECTION_COLORS['info'])
        self.load_button.setEnabled(False)

        try:
            # Fetch document
            documents = fetch_documents_by_ids({doc_id})

            if not documents:
                QMessageBox.warning(
                    self,
                    "Not Found",
                    f"Document {doc_id} not found in database."
                )
                self._update_status("Ready", 'gray')
                self.load_button.setEnabled(True)
                return

            self.current_document = documents[0]
            self._display_document()

            # Check agent
            if not self.prisma_agent:
                QMessageBox.warning(
                    self,
                    "Agent Error",
                    "PRISMA Agent not initialized. Cannot perform assessment."
                )
                self._update_status("Agent unavailable", SECTION_COLORS['error'])
                self.load_button.setEnabled(True)
                return

            # Start assessment in background
            self._update_status("Running PRISMA 2020 assessment...", SECTION_COLORS['info'])

            self.worker = PRISMA2020AssessmentWorker(self.prisma_agent, self.current_document)
            self.worker.result_ready.connect(self._on_assessment_complete)
            self.worker.error_occurred.connect(self._on_assessment_error)
            self.worker.finished.connect(lambda: self.load_button.setEnabled(True))
            self.worker.start()

        except ConnectionError as e:
            QMessageBox.critical(
                self,
                "Database Error",
                f"Failed to connect to database: {str(e)}"
            )
            self._update_status("Database connection failed", SECTION_COLORS['error'])
            self.load_button.setEnabled(True)
        except Exception as e:
            QMessageBox.critical(
                self,
                "Error",
                f"Unexpected error loading document: {str(e)}"
            )
            self._update_status(f"Error: {str(e)[:50]}...", SECTION_COLORS['error'])
            self.load_button.setEnabled(True)

    def _display_document(self):
        """Display the loaded document."""
        if not self.current_document:
            return

        doc = self.current_document

        # Title
        title = doc.get('title', 'No title')
        self.doc_title_label.setText(title)

        # Metadata
        metadata_parts = []
        if doc.get('year'):
            metadata_parts.append(f"Year: {doc['year']}")
        if doc.get('pmid'):
            metadata_parts.append(f"PMID: {doc['pmid']}")
        if doc.get('doi'):
            metadata_parts.append(f"DOI: {doc['doi']}")

        self.doc_metadata_label.setText(" | ".join(metadata_parts))

        # Abstract
        abstract = doc.get('abstract', 'No abstract available')
        self.doc_abstract_edit.setPlainText(abstract)

    def _on_assessment_complete(self, assessment: PRISMA2020Assessment):
        """Handle PRISMA 2020 assessment completion."""
        self.current_assessment = assessment
        self._display_assessment()

        compliance_pct = assessment.overall_compliance_percentage
        self._update_status(
            f"✓ Assessment complete ({compliance_pct:.1f}% compliance)",
            SECTION_COLORS['success']
        )
        self.status_message.emit(f"PRISMA 2020 assessment complete - {compliance_pct:.1f}% compliance")

    def _on_assessment_error(self, error_msg: str):
        """Handle PRISMA 2020 assessment error."""
        QMessageBox.critical(
            self,
            "Assessment Error",
            f"PRISMA 2020 assessment failed: {error_msg}"
        )
        self._update_status("Assessment failed", SECTION_COLORS['error'])

    def _display_assessment(self):
        """Display PRISMA 2020 assessment results."""
        if not self.current_assessment:
            return

        # Clear previous results
        while self.assessment_layout.count():
            child = self.assessment_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        a = self.current_assessment

        # Add result sections
        self.assessment_layout.addWidget(self._create_suitability_section(a))
        self.assessment_layout.addWidget(self._create_overall_section(a))
        self.assessment_layout.addWidget(self._create_title_abstract_section(a))
        self.assessment_layout.addWidget(self._create_introduction_section(a))
        self.assessment_layout.addWidget(self._create_methods_section(a))
        self.assessment_layout.addWidget(self._create_results_section(a))
        self.assessment_layout.addWidget(self._create_discussion_section(a))
        self.assessment_layout.addWidget(self._create_other_info_section(a))

        self.assessment_layout.addStretch()

    def _create_suitability_section(self, a: PRISMA2020Assessment) -> QGroupBox:
        """Create suitability assessment section."""
        section = QGroupBox("📋 Document Suitability")
        section.setStyleSheet(
            self.stylesheet_gen.card_stylesheet(bg_color='#E3F2FD')
        )
        layout = QVBoxLayout(section)
        layout.setSpacing(scale_px(8))

        # Document type
        doc_type = []
        if a.is_systematic_review:
            doc_type.append("✓ Systematic Review")
        if a.is_meta_analysis:
            doc_type.append("✓ Meta-Analysis")

        type_label = QLabel(" | ".join(doc_type) if doc_type else "Not a systematic review or meta-analysis")
        type_label.setFont(QFont("", 10, QFont.Bold))
        type_label.setStyleSheet(
            self.stylesheet_gen.label_stylesheet(
                font_size_key='font_medium',
                color='#1976D2' if doc_type else '#D32F2F',
                bold=True
            )
        )
        layout.addWidget(type_label)

        # Rationale
        rationale_label = QLabel(a.suitability_rationale)
        rationale_label.setWordWrap(True)
        rationale_label.setStyleSheet(
            self.stylesheet_gen.label_stylesheet(
                font_size_key='font_medium',
                color='#424242'
            )
        )
        layout.addWidget(rationale_label)

        return section

    def _create_overall_section(self, a: PRISMA2020Assessment) -> QGroupBox:
        """Create overall compliance section."""
        section = QGroupBox("⭐ Overall Compliance")

        # Get compliance category for color
        category = a.get_compliance_category()
        if '≥90%' in category:
            bg_color = '#E8F5E9'
        elif '75-89%' in category:
            bg_color = '#F1F8E9'
        elif '60-74%' in category:
            bg_color = '#FFF3E0'
        elif '40-59%' in category:
            bg_color = '#FFE0B2'
        else:
            bg_color = '#FFEBEE'

        section.setStyleSheet(
            self.stylesheet_gen.card_stylesheet(bg_color=bg_color)
        )
        layout = QVBoxLayout(section)
        layout.setSpacing(scale_px(8))

        # Compliance score
        score_row = QHBoxLayout()
        score_label = QLabel("Compliance Score:")
        score_label.setFont(QFont("", 10, QFont.Bold))
        score_value = QLabel(f"{a.overall_compliance_percentage:.1f}% ({a.overall_compliance_score:.2f}/2.0)")
        score_value.setStyleSheet(
            self.stylesheet_gen.label_stylesheet(
                font_size_key='font_large',
                color=self._get_compliance_color(a.overall_compliance_percentage),
                bold=True
            )
        )
        score_row.addWidget(score_label)
        score_row.addWidget(score_value)
        score_row.addStretch()
        layout.addLayout(score_row)

        # Category
        category_row = QHBoxLayout()
        category_label = QLabel("Category:")
        category_label.setFont(QFont("", 10, QFont.Bold))
        category_value = QLabel(category)
        category_value.setStyleSheet(
            self.stylesheet_gen.label_stylesheet(
                font_size_key='font_medium',
                color=self._get_compliance_color(a.overall_compliance_percentage),
                bold=True
            )
        )
        category_row.addWidget(category_label)
        category_row.addWidget(category_value)
        category_row.addStretch()
        layout.addLayout(category_row)

        # Statistics
        stats_text = (
            f"Items Assessed: {a.total_applicable_items} | "
            f"Fully Reported: {a.fully_reported_items} | "
            f"Partially Reported: {a.partially_reported_items} | "
            f"Not Reported: {a.not_reported_items}"
        )
        stats_label = QLabel(stats_text)
        stats_label.setStyleSheet(
            self.stylesheet_gen.label_stylesheet(
                font_size_key='font_small',
                color='gray'
            )
        )
        layout.addWidget(stats_label)

        return section

    def _create_title_abstract_section(self, a: PRISMA2020Assessment) -> QGroupBox:
        """Create Title and Abstract section."""
        section = QGroupBox("1. TITLE AND ABSTRACT")
        section.setStyleSheet(
            self.stylesheet_gen.card_stylesheet(bg_color='#F5F5F5')
        )
        layout = QVBoxLayout(section)
        layout.setSpacing(scale_px(5))

        layout.addWidget(self._create_item_row(1, "Title", a.title_score, a.title_explanation))
        layout.addWidget(self._create_item_row(2, "Abstract", a.abstract_score, a.abstract_explanation))

        return section

    def _create_introduction_section(self, a: PRISMA2020Assessment) -> QGroupBox:
        """Create Introduction section."""
        section = QGroupBox("2. INTRODUCTION")
        section.setStyleSheet(
            self.stylesheet_gen.card_stylesheet(bg_color='#F5F5F5')
        )
        layout = QVBoxLayout(section)
        layout.setSpacing(scale_px(5))

        layout.addWidget(self._create_item_row(3, "Rationale", a.rationale_score, a.rationale_explanation))
        layout.addWidget(self._create_item_row(4, "Objectives", a.objectives_score, a.objectives_explanation))

        return section

    def _create_methods_section(self, a: PRISMA2020Assessment) -> QGroupBox:
        """Create Methods section."""
        section = QGroupBox("3. METHODS")
        section.setStyleSheet(
            self.stylesheet_gen.card_stylesheet(bg_color='#F5F5F5')
        )
        layout = QVBoxLayout(section)
        layout.setSpacing(scale_px(5))

        layout.addWidget(self._create_item_row(5, "Eligibility Criteria", a.eligibility_criteria_score, a.eligibility_criteria_explanation))
        layout.addWidget(self._create_item_row(6, "Information Sources", a.information_sources_score, a.information_sources_explanation))
        layout.addWidget(self._create_item_row(7, "Search Strategy", a.search_strategy_score, a.search_strategy_explanation))
        layout.addWidget(self._create_item_row(8, "Selection Process", a.selection_process_score, a.selection_process_explanation))
        layout.addWidget(self._create_item_row(9, "Data Collection", a.data_collection_score, a.data_collection_explanation))
        layout.addWidget(self._create_item_row(10, "Data Items", a.data_items_score, a.data_items_explanation))
        layout.addWidget(self._create_item_row(11, "Risk of Bias Assessment", a.risk_of_bias_score, a.risk_of_bias_explanation))
        layout.addWidget(self._create_item_row(12, "Effect Measures", a.effect_measures_score, a.effect_measures_explanation))
        layout.addWidget(self._create_item_row(13, "Synthesis Methods", a.synthesis_methods_score, a.synthesis_methods_explanation))
        layout.addWidget(self._create_item_row(14, "Reporting Bias Assessment", a.reporting_bias_assessment_score, a.reporting_bias_assessment_explanation))
        layout.addWidget(self._create_item_row(15, "Certainty Assessment", a.certainty_assessment_score, a.certainty_assessment_explanation))

        return section

    def _create_results_section(self, a: PRISMA2020Assessment) -> QGroupBox:
        """Create Results section."""
        section = QGroupBox("4. RESULTS")
        section.setStyleSheet(
            self.stylesheet_gen.card_stylesheet(bg_color='#F5F5F5')
        )
        layout = QVBoxLayout(section)
        layout.setSpacing(scale_px(5))

        layout.addWidget(self._create_item_row(16, "Study Selection", a.study_selection_score, a.study_selection_explanation))
        layout.addWidget(self._create_item_row(17, "Study Characteristics", a.study_characteristics_score, a.study_characteristics_explanation))
        layout.addWidget(self._create_item_row(18, "Risk of Bias Results", a.risk_of_bias_results_score, a.risk_of_bias_results_explanation))
        layout.addWidget(self._create_item_row(19, "Individual Studies Results", a.individual_studies_results_score, a.individual_studies_results_explanation))
        layout.addWidget(self._create_item_row(20, "Synthesis Results", a.synthesis_results_score, a.synthesis_results_explanation))
        layout.addWidget(self._create_item_row(21, "Reporting Biases Results", a.reporting_biases_results_score, a.reporting_biases_results_explanation))
        layout.addWidget(self._create_item_row(22, "Certainty of Evidence", a.certainty_of_evidence_score, a.certainty_of_evidence_explanation))

        return section

    def _create_discussion_section(self, a: PRISMA2020Assessment) -> QGroupBox:
        """Create Discussion section."""
        section = QGroupBox("5. DISCUSSION")
        section.setStyleSheet(
            self.stylesheet_gen.card_stylesheet(bg_color='#F5F5F5')
        )
        layout = QVBoxLayout(section)
        layout.setSpacing(scale_px(5))

        layout.addWidget(self._create_item_row(23, "Discussion", a.discussion_score, a.discussion_explanation))
        layout.addWidget(self._create_item_row(24, "Limitations", a.limitations_score, a.limitations_explanation))
        layout.addWidget(self._create_item_row(25, "Conclusions", a.conclusions_score, a.conclusions_explanation))

        return section

    def _create_other_info_section(self, a: PRISMA2020Assessment) -> QGroupBox:
        """Create Other Information section."""
        section = QGroupBox("6. OTHER INFORMATION")
        section.setStyleSheet(
            self.stylesheet_gen.card_stylesheet(bg_color='#F5F5F5')
        )
        layout = QVBoxLayout(section)
        layout.setSpacing(scale_px(5))

        layout.addWidget(self._create_item_row(26, "Registration & Protocol", a.registration_score, a.registration_explanation))
        layout.addWidget(self._create_item_row(27, "Support & Funding", a.support_score, a.support_explanation))

        return section

    def _create_item_row(self, item_num: int, label: str, score: float, explanation: str) -> QWidget:
        """Create a checklist item row with score badge and explanation."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(scale_px(10), scale_px(5), scale_px(10), scale_px(5))
        layout.setSpacing(scale_px(3))

        # Header row with item number, label, and score
        header_row = QHBoxLayout()

        item_label = QLabel(f"Item {item_num}: {label}")
        item_label.setFont(QFont("", 10, QFont.Bold))

        score_badge = QLabel(self._get_score_text(score))
        score_badge.setAlignment(Qt.AlignCenter)
        score_badge.setFixedWidth(scale_px(120))
        score_badge.setStyleSheet(
            self.stylesheet_gen.custom(f"""
                QLabel {{
                    background-color: {self._get_score_color(score)};
                    color: white;
                    font-weight: bold;
                    font-size: {{font_small}}pt;
                    padding: {{padding_tiny}}px;
                    border-radius: {{radius_small}}px;
                }}
            """)
        )

        header_row.addWidget(item_label)
        header_row.addStretch()
        header_row.addWidget(score_badge)

        # Explanation
        explanation_label = QLabel(explanation)
        explanation_label.setWordWrap(True)
        explanation_label.setStyleSheet(
            self.stylesheet_gen.label_stylesheet(
                font_size_key='font_small',
                color='#424242'
            )
        )

        layout.addLayout(header_row)
        layout.addWidget(explanation_label)

        # Add separator line
        separator = QWidget()
        separator.setFixedHeight(1)
        separator.setStyleSheet("background-color: #E0E0E0;")
        layout.addWidget(separator)

        return widget

    def _get_score_color(self, score: float) -> str:
        """Get color based on item score."""
        if score >= 1.9:  # Treat ≥1.9 as fully reported
            return SCORE_COLORS[2.0]
        elif score >= 0.9:  # Treat ≥0.9 as partially reported
            return SCORE_COLORS[1.0]
        else:
            return SCORE_COLORS[0.0]

    def _get_score_text(self, score: float) -> str:
        """Get text description for score."""
        if score >= 1.9:
            return f"✓ Fully Reported ({score:.1f})"
        elif score >= 0.9:
            return f"◐ Partial ({score:.1f})"
        else:
            return f"✗ Not Reported ({score:.1f})"

    def _get_compliance_color(self, percentage: float) -> str:
        """Get color based on compliance percentage."""
        if percentage >= 90:
            return COMPLIANCE_COLORS['excellent']
        elif percentage >= 75:
            return COMPLIANCE_COLORS['good']
        elif percentage >= 60:
            return COMPLIANCE_COLORS['adequate']
        elif percentage >= 40:
            return COMPLIANCE_COLORS['poor']
        else:
            return COMPLIANCE_COLORS['very_poor']

    def _update_status(self, message: str, color: str):
        """Update status label with message and color."""
        self.status_label.setText(message)
        self.status_label.setStyleSheet(
            self.stylesheet_gen.label_stylesheet(
                font_size_key='font_small',
                color=color
            )
        )

    def _clear_all(self):
        """Clear all fields."""
        self.doc_id_input.clear()
        self.doc_title_label.setText("No document loaded")
        self.doc_metadata_label.setText("")
        self.doc_abstract_edit.clear()

        # Clear assessment results
        while self.assessment_layout.count():
            child = self.assessment_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        placeholder = QLabel("Assessment results will appear here after loading a document.")
        placeholder.setStyleSheet(
            self.stylesheet_gen.label_stylesheet(
                font_size_key='font_medium',
                color='gray'
            )
        )
        self.assessment_layout.addWidget(placeholder)

        self._update_status("Ready", 'gray')
        self.current_document = None
        self.current_assessment = None
        self.status_message.emit("Cleared all fields")

    def cleanup(self):
        """Cleanup resources."""
        if self.worker and self.worker.isRunning():
            self.worker.terminate()
            self.worker.wait()

        if self.orchestrator:
            try:
                self.orchestrator.shutdown()
            except Exception as e:
                print(f"Warning: Error during orchestrator shutdown: {e}")
