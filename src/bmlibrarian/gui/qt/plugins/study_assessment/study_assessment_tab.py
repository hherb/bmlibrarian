"""
Study Assessment Lab Tab Widget for BMLibrarian Qt GUI.

Interactive interface for evaluating research quality, study design, and
trustworthiness of biomedical evidence using StudyAssessmentAgent.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QGroupBox, QLineEdit, QComboBox, QSplitter,
    QMessageBox, QScrollArea
)
from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtGui import QFont, QIntValidator
from typing import Optional, Dict, Any

from bmlibrarian.agents import StudyAssessmentAgent, AgentOrchestrator
from bmlibrarian.agents.study_assessment_agent import StudyAssessment
from bmlibrarian.config import get_config
from bmlibrarian.database import get_document_details
from ...resources.styles import get_font_scale, scale_px, StylesheetGenerator
from ...widgets import DocumentViewWidget, DocumentViewData
from ...core.document_receiver import IDocumentReceiver
from .constants import (
    QUALITY_COLORS, CONFIDENCE_COLORS, BIAS_RISK_COLORS,
    SECTION_COLORS
)


class StudyAssessmentWorker(QThread):
    """Worker thread for study assessment to prevent UI blocking."""

    result_ready = Signal(object)  # StudyAssessment object
    error_occurred = Signal(str)

    def __init__(self, assessment_agent: StudyAssessmentAgent, document: Dict[str, Any]):
        """
        Initialize worker thread.

        Args:
            assessment_agent: StudyAssessmentAgent instance
            document: Document dictionary
        """
        super().__init__()
        self.assessment_agent = assessment_agent
        self.document = document

    def run(self):
        """Execute study assessment in background thread."""
        try:
            assessment = self.assessment_agent.assess_study(
                document=self.document,
                min_confidence=0.0  # Show all assessments in lab mode
            )
            if assessment:
                self.result_ready.emit(assessment)
            else:
                self.error_occurred.emit("Study assessment returned no results")
        except Exception as e:
            self.error_occurred.emit(str(e))


class StudyAssessmentTabWidget(QWidget, IDocumentReceiver):
    """Main Study Assessment Lab tab widget with document receiver capability."""

    status_message = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None):
        """
        Initialize Study Assessment Lab tab.

        Args:
            parent: Optional parent widget
        """
        super().__init__(parent)

        self.scale = get_font_scale()
        self.stylesheet_gen = StylesheetGenerator()
        self.config = get_config()
        self.assessment_agent: Optional[StudyAssessmentAgent] = None
        self.orchestrator: Optional[AgentOrchestrator] = None
        self.worker: Optional[StudyAssessmentWorker] = None
        self.current_document: Optional[Dict[str, Any]] = None
        self.current_assessment: Optional[StudyAssessment] = None

        # UI Components
        self.model_combo: Optional[QComboBox] = None
        self.doc_id_input: Optional[QLineEdit] = None
        self.load_button: Optional[QPushButton] = None
        self.clear_button: Optional[QPushButton] = None
        self.refresh_button: Optional[QPushButton] = None

        # Document display - using reusable DocumentViewWidget
        self.document_view: Optional[DocumentViewWidget] = None

        # Assessment results
        self.assessment_scroll: Optional[QScrollArea] = None
        self.assessment_widget: Optional[QWidget] = None
        self.assessment_layout: Optional[QVBoxLayout] = None

        self.status_label: Optional[QLabel] = None

        self._init_agent()
        self._setup_ui()

    def _init_agent(self):
        """Initialize StudyAssessmentAgent with orchestrator."""
        try:
            self.orchestrator = AgentOrchestrator(max_workers=2)

            # Get configuration
            default_model = self.config.get_model('study_assessment_agent') or "gpt-oss:20b"
            agent_config = self.config.get_agent_config('study_assessment') or {}
            host = self.config.get_ollama_config()['host']

            self.assessment_agent = StudyAssessmentAgent(
                model=default_model,
                host=host,
                temperature=agent_config.get('temperature', 0.1),
                top_p=agent_config.get('top_p', 0.9),
                max_tokens=agent_config.get('max_tokens', 3000),
                orchestrator=self.orchestrator,
                show_model_info=True
            )
            print(f"✓ StudyAssessmentAgent initialized with model: {default_model}")
        except Exception as e:
            print(f"Warning: Failed to initialize StudyAssessmentAgent: {e}")
            self.assessment_agent = None

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

        title = QLabel("Study Assessment Laboratory")
        title.setFont(QFont("", 10, QFont.Bold))
        title.setStyleSheet(
            self.stylesheet_gen.label_stylesheet(
                font_size_key='font_large',
                color=SECTION_COLORS['title'],
                bold=True
            )
        )

        subtitle = QLabel(
            "Evaluate research quality, study design, and trustworthiness of biomedical evidence"
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

        model_label = QLabel("Assessment Model:")
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

    def _create_document_panel(self) -> QWidget:
        """Create document display panel using DocumentViewWidget."""
        self.document_view = DocumentViewWidget()
        return self.document_view

    def _create_assessment_panel(self) -> QGroupBox:
        """Create assessment results display panel."""
        group = QGroupBox("Quality Assessment")
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
        if not self.assessment_agent:
            QMessageBox.warning(
                self,
                "Agent Error",
                "Assessment agent not initialized. Cannot refresh models."
            )
            return

        try:
            # Use agent's get_available_models method (uses ollama library internally)
            models = self.assessment_agent.get_available_models()

            current = self.model_combo.currentText()
            self.model_combo.clear()
            self.model_combo.addItems(models)

            # Restore selection if possible
            if current in models:
                self.model_combo.setCurrentText(current)
            else:
                # Set to configured model
                default_model = self.config.get_model('study_assessment_agent') or "gpt-oss:20b"
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
        if not model_name or not self.assessment_agent:
            return

        try:
            # Reinitialize agent with new model
            agent_config = self.config.get_agent_config('study_assessment') or {}
            host = self.config.get_ollama_config()['host']

            self.assessment_agent = StudyAssessmentAgent(
                model=model_name,
                host=host,
                temperature=agent_config.get('temperature', 0.1),
                top_p=agent_config.get('top_p', 0.9),
                max_tokens=agent_config.get('max_tokens', 3000),
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
        """Load document and perform study assessment."""
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
            # Fetch document using canonical function
            doc = get_document_details(doc_id)

            if not doc:
                QMessageBox.warning(
                    self,
                    "Not Found",
                    f"Document {doc_id} not found in database."
                )
                self._update_status("Ready", 'gray')
                self.load_button.setEnabled(True)
                return

            self.current_document = doc
            self._display_document()

            # Check agent
            if not self.assessment_agent:
                QMessageBox.warning(
                    self,
                    "Agent Error",
                    "Assessment Agent not initialized. Cannot perform assessment."
                )
                self._update_status("Agent unavailable", SECTION_COLORS['error'])
                self.load_button.setEnabled(True)
                return

            # Start assessment in background
            self._update_status("Running quality assessment...", SECTION_COLORS['info'])

            self.worker = StudyAssessmentWorker(self.assessment_agent, self.current_document)
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
        """Display the loaded document using DocumentViewWidget.

        Uses document data from get_document_details which provides
        pre-formatted authors string and consistent field names.
        """
        if not self.current_document:
            return

        doc = self.current_document

        # Create DocumentViewData from document dict
        # get_document_details returns 'authors' already formatted as string
        doc_data = DocumentViewData(
            document_id=doc.get('id'),
            title=doc.get('title', 'No title'),
            authors=doc.get('authors'),  # Already formatted by get_document_details
            journal=doc.get('journal'),
            year=doc.get('year'),
            pmid=doc.get('pmid'),
            doi=doc.get('doi'),
            abstract=doc.get('abstract'),
            full_text=doc.get('full_text'),
            pdf_path=doc.get('pdf_filename'),  # Note: pdf_filename from get_document_details
            pdf_url=doc.get('pdf_url'),
            publication_date=doc.get('publication_date'),
        )

        self.document_view.set_document(doc_data)

    def _on_assessment_complete(self, assessment: StudyAssessment):
        """Handle study assessment completion."""
        self.current_assessment = assessment
        self._display_assessment()

        confidence_pct = assessment.overall_confidence * 100
        self._update_status(
            f"✓ Assessment complete (confidence: {confidence_pct:.1f}%)",
            SECTION_COLORS['success']
        )
        self.status_message.emit(f"Study assessment complete - {confidence_pct:.1f}% confidence")

    def _on_assessment_error(self, error_msg: str):
        """Handle study assessment error."""
        QMessageBox.critical(
            self,
            "Assessment Error",
            f"Study assessment failed: {error_msg}"
        )
        self._update_status("Assessment failed", SECTION_COLORS['error'])

    def _display_assessment(self):
        """Display study assessment results."""
        if not self.current_assessment:
            return

        # Clear previous results
        while self.assessment_layout.count():
            child = self.assessment_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        a = self.current_assessment

        # Add result sections
        self.assessment_layout.addWidget(self._create_classification_section(a))
        self.assessment_layout.addWidget(self._create_quality_section(a))

        if self._has_design_characteristics(a):
            self.assessment_layout.addWidget(self._create_design_section(a))

        if a.strengths:
            self.assessment_layout.addWidget(self._create_strengths_section(a))

        if a.limitations:
            self.assessment_layout.addWidget(self._create_limitations_section(a))

        if self._has_bias_assessment(a):
            self.assessment_layout.addWidget(self._create_bias_section(a))

        self.assessment_layout.addStretch()

    def _create_classification_section(self, a: StudyAssessment) -> QGroupBox:
        """Create study classification section."""
        section = QGroupBox("📊 Study Classification")
        section.setStyleSheet(
            self.stylesheet_gen.card_stylesheet(
                bg_color=SECTION_COLORS['classification_bg']
            )
        )
        layout = QVBoxLayout(section)
        layout.setSpacing(scale_px(8))

        layout.addWidget(self._create_info_row("Study Type", a.study_type))
        layout.addWidget(self._create_info_row("Study Design", a.study_design))
        layout.addWidget(self._create_info_row("Evidence Level", a.evidence_level))
        layout.addWidget(self._create_info_row("Sample Size", a.sample_size or "Not reported"))
        layout.addWidget(self._create_info_row("Follow-up", a.follow_up_duration or "Not reported"))

        return section

    def _create_quality_section(self, a: StudyAssessment) -> QGroupBox:
        """Create quality metrics section."""
        section = QGroupBox("⭐ Quality Metrics")
        section.setStyleSheet(
            self.stylesheet_gen.card_stylesheet(
                bg_color=SECTION_COLORS['quality_bg']
            )
        )
        layout = QVBoxLayout(section)
        layout.setSpacing(scale_px(8))

        # Quality score
        quality_color = self._get_quality_color(a.quality_score)
        score_row = QHBoxLayout()
        score_label = QLabel("Quality Score:")
        score_label.setFont(QFont("", 10, QFont.Bold))
        score_value = QLabel(f"{a.quality_score:.1f}/10")
        score_value.setStyleSheet(
            self.stylesheet_gen.label_stylesheet(
                font_size_key='font_medium',
                color=quality_color,
                bold=True
            )
        )
        score_row.addWidget(score_label)
        score_row.addWidget(score_value)
        score_row.addStretch()

        # Confidence
        confidence_color = self._get_confidence_color(a.overall_confidence)
        conf_row = QHBoxLayout()
        conf_label = QLabel("Confidence:")
        conf_label.setFont(QFont("", 10, QFont.Bold))
        conf_value = QLabel(f"{a.overall_confidence:.1%}")
        conf_value.setStyleSheet(
            self.stylesheet_gen.label_stylesheet(
                font_size_key='font_medium',
                color=confidence_color,
                bold=True
            )
        )
        conf_row.addWidget(conf_label)
        conf_row.addWidget(conf_value)
        conf_row.addStretch()

        layout.addLayout(score_row)
        layout.addLayout(conf_row)

        # Confidence explanation
        if a.confidence_explanation:
            explanation = QLabel(a.confidence_explanation)
            explanation.setWordWrap(True)
            explanation.setStyleSheet(
                self.stylesheet_gen.label_stylesheet(
                    font_size_key='font_small',
                    color='gray'
                )
            )
            layout.addWidget(explanation)

        return section

    def _create_design_section(self, a: StudyAssessment) -> QGroupBox:
        """Create design characteristics section."""
        section = QGroupBox("🔬 Design Characteristics")
        section.setStyleSheet(
            self.stylesheet_gen.card_stylesheet(
                bg_color=SECTION_COLORS['design_bg']
            )
        )
        layout = QVBoxLayout(section)

        design_chars = self._get_design_characteristics(a)
        chars_label = QLabel(", ".join(design_chars))
        chars_label.setWordWrap(True)
        chars_label.setStyleSheet(
            self.stylesheet_gen.label_stylesheet(
                font_size_key='font_medium',
                color=SECTION_COLORS['design_text']
            )
        )
        layout.addWidget(chars_label)

        return section

    def _create_strengths_section(self, a: StudyAssessment) -> QGroupBox:
        """Create strengths section."""
        section = QGroupBox("✅ Strengths")
        section.setStyleSheet(
            self.stylesheet_gen.card_stylesheet(
                bg_color=SECTION_COLORS['strengths_bg']
            )
        )
        layout = QVBoxLayout(section)
        layout.setSpacing(scale_px(5))

        for strength in a.strengths:
            label = QLabel(f"• {strength}")
            label.setWordWrap(True)
            label.setStyleSheet(
                self.stylesheet_gen.label_stylesheet(
                    font_size_key='font_medium'
                )
            )
            layout.addWidget(label)

        return section

    def _create_limitations_section(self, a: StudyAssessment) -> QGroupBox:
        """Create limitations section."""
        section = QGroupBox("⚠️  Limitations")
        section.setStyleSheet(
            self.stylesheet_gen.card_stylesheet(
                bg_color=SECTION_COLORS['limitations_bg']
            )
        )
        layout = QVBoxLayout(section)
        layout.setSpacing(scale_px(5))

        for limitation in a.limitations:
            label = QLabel(f"• {limitation}")
            label.setWordWrap(True)
            label.setStyleSheet(
                self.stylesheet_gen.label_stylesheet(
                    font_size_key='font_medium'
                )
            )
            layout.addWidget(label)

        return section

    def _create_bias_section(self, a: StudyAssessment) -> QGroupBox:
        """Create bias risk assessment section."""
        section = QGroupBox("🎯 Bias Risk Assessment")
        section.setStyleSheet(
            self.stylesheet_gen.card_stylesheet(
                bg_color=SECTION_COLORS['bias_bg']
            )
        )
        layout = QVBoxLayout(section)
        layout.setSpacing(scale_px(8))

        bias_items = self._get_bias_items(a)
        for bias_type, risk_level in bias_items:
            bias_row = self._create_bias_row(bias_type, risk_level)
            layout.addLayout(bias_row)

        return section

    def _create_bias_row(self, bias_type: str, risk_level: str) -> QHBoxLayout:
        """Create a bias risk row."""
        row = QHBoxLayout()

        type_label = QLabel(f"{bias_type}:")
        type_label.setFont(QFont("", 10, QFont.Bold))
        type_label.setFixedWidth(scale_px(120))

        risk_badge = QLabel(risk_level.upper())
        risk_badge.setAlignment(Qt.AlignCenter)
        risk_badge.setFixedWidth(scale_px(100))
        s = get_font_scale()
        risk_badge.setStyleSheet(
            f"""
                QLabel {{
                    background-color: {BIAS_RISK_COLORS.get(risk_level.lower(), BIAS_RISK_COLORS['unclear'])};
                    color: white;
                    font-weight: bold;
                    font-size: {s['font_small']}pt;
                    padding: {s['padding_tiny']}px;
                    border-radius: {s['radius_small']}px;
                }}
            """
        )

        row.addWidget(type_label)
        row.addWidget(risk_badge)
        row.addStretch()

        return row

    def _create_info_row(self, label: str, value: str) -> QWidget:
        """Create an information row widget."""
        widget = QWidget()
        row = QHBoxLayout(widget)
        row.setContentsMargins(0, 0, 0, 0)

        label_widget = QLabel(f"{label}:")
        label_widget.setFont(QFont("", 10, QFont.Bold))
        label_widget.setFixedWidth(scale_px(120))

        value_widget = QLabel(value)
        value_widget.setStyleSheet(
            self.stylesheet_gen.label_stylesheet(
                font_size_key='font_medium',
                color='#424242'
            )
        )

        row.addWidget(label_widget)
        row.addWidget(value_widget)
        row.addStretch()

        return widget

    def _get_quality_color(self, score: float) -> str:
        """Get color based on quality score."""
        if score >= 9:
            return QUALITY_COLORS['excellent']
        elif score >= 7:
            return QUALITY_COLORS['good']
        elif score >= 5:
            return QUALITY_COLORS['fair']
        elif score >= 3:
            return QUALITY_COLORS['poor']
        else:
            return QUALITY_COLORS['very_poor']

    def _get_confidence_color(self, confidence: float) -> str:
        """Get color based on confidence level."""
        if confidence >= 0.8:
            return CONFIDENCE_COLORS['high']
        elif confidence >= 0.6:
            return CONFIDENCE_COLORS['medium']
        elif confidence >= 0.4:
            return CONFIDENCE_COLORS['low']
        else:
            return CONFIDENCE_COLORS['very_low']

    def _has_design_characteristics(self, a: StudyAssessment) -> bool:
        """Check if assessment has design characteristics."""
        return any([
            a.is_prospective, a.is_retrospective, a.is_randomized,
            a.is_controlled, a.is_blinded, a.is_double_blinded,
            a.is_multi_center
        ])

    def _get_design_characteristics(self, a: StudyAssessment) -> list[str]:
        """Get list of design characteristics."""
        chars = []
        if a.is_prospective:
            chars.append("✓ Prospective")
        if a.is_retrospective:
            chars.append("✓ Retrospective")
        if a.is_randomized:
            chars.append("✓ Randomized")
        if a.is_controlled:
            chars.append("✓ Controlled")
        if a.is_double_blinded:
            chars.append("✓ Double-blinded")
        elif a.is_blinded:
            chars.append("✓ Blinded")
        if a.is_multi_center:
            chars.append("✓ Multi-center")
        return chars

    def _has_bias_assessment(self, a: StudyAssessment) -> bool:
        """Check if assessment has bias risk data."""
        return any([
            a.selection_bias_risk, a.performance_bias_risk,
            a.detection_bias_risk, a.attrition_bias_risk,
            a.reporting_bias_risk
        ])

    def _get_bias_items(self, a: StudyAssessment) -> list[tuple[str, str]]:
        """Get list of bias assessment items."""
        items = []
        if a.selection_bias_risk:
            items.append(("Selection", a.selection_bias_risk))
        if a.performance_bias_risk:
            items.append(("Performance", a.performance_bias_risk))
        if a.detection_bias_risk:
            items.append(("Detection", a.detection_bias_risk))
        if a.attrition_bias_risk:
            items.append(("Attrition", a.attrition_bias_risk))
        if a.reporting_bias_risk:
            items.append(("Reporting", a.reporting_bias_risk))
        return items

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

        # Clear document view widget
        self.document_view.clear()

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

    # ========================================================================
    # IDocumentReceiver Interface Implementation
    # ========================================================================

    def get_receiver_id(self) -> str:
        """Get unique identifier for this receiver."""
        return "study_assessment"

    def get_receiver_name(self) -> str:
        """Get display name for this receiver."""
        return "Study Assessment Lab"

    def get_receiver_description(self) -> Optional[str]:
        """Get optional tooltip description for this receiver."""
        return "Assess research quality, study design, and methodological rigor"

    def can_receive_document(self, document_data: Dict[str, Any]) -> bool:
        """Check if this receiver can accept the given document.

        Study Assessment Lab can accept any document with an ID.

        Args:
            document_data: Document data dictionary

        Returns:
            bool: True if document has an ID
        """
        doc_id = document_data.get('id') or document_data.get('document_id')
        return doc_id is not None

    def receive_document(self, document_data: Dict[str, Any]) -> None:
        """Receive and load a document for study assessment.

        Args:
            document_data: Full document data dictionary
        """
        doc_id = document_data.get('id') or document_data.get('document_id')
        if doc_id:
            # Set the document ID in the input field
            self.doc_id_input.setText(str(doc_id))
            # Trigger loading
            self._load_document()

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
