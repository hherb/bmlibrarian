"""
Study Assessment Lab Tab Widget for BMLibrarian Qt GUI.

Interactive interface for experimenting with StudyAssessmentAgent and evaluating
research quality, study design, methodological rigor, and trustworthiness.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QGroupBox, QLineEdit, QComboBox, QSplitter,
    QMessageBox, QFormLayout, QScrollArea, QFrame
)
from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtGui import QFont, QIntValidator
from typing import Optional, Dict, Any

from bmlibrarian.agents import StudyAssessmentAgent, AgentOrchestrator
from bmlibrarian.agents.study_assessment_agent import (
    StudyAssessment,
    QUALITY_THRESHOLD_EXCEPTIONAL,
    QUALITY_THRESHOLD_HIGH,
    QUALITY_THRESHOLD_MODERATE,
    QUALITY_THRESHOLD_LOW,
)
from bmlibrarian.config import get_config
from bmlibrarian.database import fetch_documents_by_ids
from ...resources.styles import get_font_scale, scale_px

# UI Constants
ORCHESTRATOR_MAX_WORKERS = 2
SPLITTER_DOC_WIDTH = 350
SPLITTER_ASSESSMENT_WIDTH = 650
MAX_DOCUMENT_ID = 999999999
OLLAMA_REQUEST_TIMEOUT = 5  # seconds
CONFIDENCE_THRESHOLD_HIGH = 0.8
CONFIDENCE_THRESHOLD_MODERATE = 0.6


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
                min_confidence=0.0  # Show all assessments
            )
            if assessment:
                self.result_ready.emit(assessment)
            else:
                self.error_occurred.emit("Study assessment returned no results")
        except Exception as e:
            self.error_occurred.emit(str(e))


class StudyAssessmentLabTabWidget(QWidget):
    """Main Study Assessment Lab tab widget."""

    status_message = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None):
        """
        Initialize Study Assessment Lab tab.

        Args:
            parent: Optional parent widget
        """
        super().__init__(parent)

        self.scale = get_font_scale()
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

        # Document display
        self.doc_title_label: Optional[QLabel] = None
        self.doc_metadata_label: Optional[QLabel] = None
        self.doc_abstract_edit: Optional[QTextEdit] = None

        # Study assessment results
        self.study_type_label: Optional[QLabel] = None
        self.study_design_label: Optional[QLabel] = None
        self.evidence_level_label: Optional[QLabel] = None
        self.quality_score_label: Optional[QLabel] = None
        self.confidence_label: Optional[QLabel] = None
        self.confidence_explanation_edit: Optional[QTextEdit] = None

        # Characteristics
        self.sample_size_label: Optional[QLabel] = None
        self.follow_up_label: Optional[QLabel] = None
        self.characteristics_label: Optional[QLabel] = None

        # Strengths and limitations
        self.strengths_edit: Optional[QTextEdit] = None
        self.limitations_edit: Optional[QTextEdit] = None

        # Bias assessment
        self.selection_bias_label: Optional[QLabel] = None
        self.performance_bias_label: Optional[QLabel] = None
        self.detection_bias_label: Optional[QLabel] = None
        self.attrition_bias_label: Optional[QLabel] = None
        self.reporting_bias_label: Optional[QLabel] = None

        self.status_label: Optional[QLabel] = None

        self._init_agent()
        self._setup_ui()

    def _init_agent(self):
        """Initialize StudyAssessmentAgent with orchestrator."""
        try:
            self.orchestrator = AgentOrchestrator(max_workers=ORCHESTRATOR_MAX_WORKERS)

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
        s = self.scale
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

        # Right: Assessment results (scrollable)
        assessment_scroll = QScrollArea()
        assessment_scroll.setWidgetResizable(True)
        assessment_scroll.setFrameShape(QFrame.NoFrame)

        assessment_panel = self._create_assessment_panel()
        assessment_scroll.setWidget(assessment_panel)

        splitter.addWidget(assessment_scroll)

        # Set initial sizes (35% document, 65% assessment)
        splitter.setSizes([SPLITTER_DOC_WIDTH, SPLITTER_ASSESSMENT_WIDTH])

        main_layout.addWidget(splitter, stretch=1)

        # Status bar
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet(f"color: gray; font-size: {scale_px(11)}px;")
        main_layout.addWidget(self.status_label)

    def _create_header(self) -> QWidget:
        """Create header section."""
        s = self.scale
        header_widget = QWidget()
        header_layout = QVBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(scale_px(5))

        title = QLabel("Study Assessment Laboratory")
        title.setFont(QFont("", 10, QFont.Bold))
        title.setStyleSheet("color: #7B1FA2;")

        subtitle = QLabel("Evaluate research quality, study design, methodological rigor, and trustworthiness")
        subtitle.setStyleSheet(f"color: gray; font-size: {scale_px(12)}px;")

        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)

        return header_widget

    def _create_input_panel(self) -> QGroupBox:
        """Create input panel for document loading."""
        s = self.scale
        group = QGroupBox("Document Input")
        layout = QVBoxLayout(group)
        layout.setSpacing(scale_px(10))

        # Model selection row
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

        model_row.addWidget(model_label)
        model_row.addWidget(self.model_combo)
        model_row.addWidget(self.refresh_button)
        model_row.addStretch()

        layout.addLayout(model_row)

        # Document ID input row
        input_row = QHBoxLayout()

        doc_id_label = QLabel("Document ID:")
        self.doc_id_input = QLineEdit()
        self.doc_id_input.setPlaceholderText("Enter document ID (e.g., 12345)")
        self.doc_id_input.setMaximumWidth(scale_px(200))
        self.doc_id_input.setValidator(QIntValidator(1, MAX_DOCUMENT_ID))
        self.doc_id_input.returnPressed.connect(self._load_document)

        self.load_button = QPushButton("Load & Assess")
        self.load_button.clicked.connect(self._load_document)
        self.load_button.setStyleSheet("background-color: #7B1FA2; color: white; font-weight: bold;")
        self.load_button.setMinimumHeight(scale_px(35))
        self.load_button.setMaximumWidth(scale_px(150))

        self.clear_button = QPushButton("Clear")
        self.clear_button.clicked.connect(self._clear_all)
        self.clear_button.setMaximumWidth(scale_px(80))
        self.clear_button.setMinimumHeight(scale_px(35))

        input_row.addWidget(doc_id_label)
        input_row.addWidget(self.doc_id_input)
        input_row.addWidget(self.load_button)
        input_row.addWidget(self.clear_button)
        input_row.addStretch()

        layout.addLayout(input_row)

        return group

    def _create_document_panel(self) -> QGroupBox:
        """Create document display panel."""
        s = self.scale
        group = QGroupBox("Document")
        layout = QVBoxLayout(group)
        layout.setSpacing(scale_px(10))

        # Title
        self.doc_title_label = QLabel("No document loaded")
        self.doc_title_label.setFont(QFont("", 10, QFont.Bold))
        self.doc_title_label.setWordWrap(True)
        self.doc_title_label.setStyleSheet("color: #424242;")

        # Metadata
        self.doc_metadata_label = QLabel("")
        self.doc_metadata_label.setStyleSheet(f"color: gray; font-size: {scale_px(11)}px;")
        self.doc_metadata_label.setWordWrap(True)

        # Abstract
        abstract_label = QLabel("Abstract:")
        abstract_label.setFont(QFont("", 10, QFont.Bold))

        self.doc_abstract_edit = QTextEdit()
        self.doc_abstract_edit.setReadOnly(True)
        self.doc_abstract_edit.setPlaceholderText("Document abstract will appear here...")

        layout.addWidget(self.doc_title_label)
        layout.addWidget(self.doc_metadata_label)
        layout.addSpacing(scale_px(10))
        layout.addWidget(abstract_label)
        layout.addWidget(self.doc_abstract_edit)

        return group

    def _create_assessment_panel(self) -> QWidget:
        """Create study assessment results display panel."""
        s = self.scale
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(scale_px(15))
        layout.setContentsMargins(scale_px(10), scale_px(10), scale_px(10), scale_px(10))

        # Section: Study Classification
        classification_group = QGroupBox("Study Classification")
        classification_layout = QFormLayout(classification_group)
        classification_layout.setSpacing(scale_px(8))

        self.study_type_label = QLabel("—")
        self.study_type_label.setStyleSheet("font-weight: bold; color: #424242;")
        self.study_type_label.setWordWrap(True)

        self.study_design_label = QLabel("—")
        self.study_design_label.setWordWrap(True)

        self.evidence_level_label = QLabel("—")
        self.evidence_level_label.setStyleSheet("color: #1976D2; font-weight: bold;")

        classification_layout.addRow("Study Type:", self.study_type_label)
        classification_layout.addRow("Study Design:", self.study_design_label)
        classification_layout.addRow("Evidence Level:", self.evidence_level_label)

        layout.addWidget(classification_group)

        # Section: Quality Assessment
        quality_group = QGroupBox("Quality Assessment")
        quality_layout = QVBoxLayout(quality_group)
        quality_layout.setSpacing(scale_px(8))

        # Quality score and confidence on same row
        scores_row = QHBoxLayout()

        quality_container = QWidget()
        quality_inner_layout = QVBoxLayout(quality_container)
        quality_inner_layout.setContentsMargins(0, 0, 0, 0)
        quality_label_text = QLabel("Quality Score:")
        quality_label_text.setStyleSheet("font-size: 11px; color: gray;")
        self.quality_score_label = QLabel("—")
        self.quality_score_label.setFont(QFont("", 14, QFont.Bold))
        self.quality_score_label.setStyleSheet("color: #2E7D32;")
        quality_inner_layout.addWidget(quality_label_text)
        quality_inner_layout.addWidget(self.quality_score_label)

        confidence_container = QWidget()
        confidence_inner_layout = QVBoxLayout(confidence_container)
        confidence_inner_layout.setContentsMargins(0, 0, 0, 0)
        confidence_label_text = QLabel("Overall Confidence:")
        confidence_label_text.setStyleSheet("font-size: 11px; color: gray;")
        self.confidence_label = QLabel("—")
        self.confidence_label.setFont(QFont("", 14, QFont.Bold))
        self.confidence_label.setStyleSheet("color: #2E7D32;")
        confidence_inner_layout.addWidget(confidence_label_text)
        confidence_inner_layout.addWidget(self.confidence_label)

        scores_row.addWidget(quality_container)
        scores_row.addWidget(confidence_container)
        scores_row.addStretch()

        quality_layout.addLayout(scores_row)

        # Confidence explanation
        conf_exp_label = QLabel("Explanation:")
        conf_exp_label.setFont(QFont("", 10, QFont.Bold))
        self.confidence_explanation_edit = QTextEdit()
        self.confidence_explanation_edit.setReadOnly(True)
        self.confidence_explanation_edit.setPlaceholderText("Confidence explanation will appear here...")
        self.confidence_explanation_edit.setMaximumHeight(scale_px(60))

        quality_layout.addWidget(conf_exp_label)
        quality_layout.addWidget(self.confidence_explanation_edit)

        layout.addWidget(quality_group)

        # Section: Study Characteristics
        characteristics_group = QGroupBox("Study Characteristics")
        characteristics_layout = QVBoxLayout(characteristics_group)
        characteristics_layout.setSpacing(scale_px(5))

        self.sample_size_label = QLabel("Sample Size: —")
        self.follow_up_label = QLabel("Follow-up: —")
        self.characteristics_label = QLabel("Characteristics: —")
        self.characteristics_label.setWordWrap(True)

        characteristics_layout.addWidget(self.sample_size_label)
        characteristics_layout.addWidget(self.follow_up_label)
        characteristics_layout.addWidget(self.characteristics_label)

        layout.addWidget(characteristics_group)

        # Section: Strengths
        strengths_group = QGroupBox("Strengths")
        strengths_layout = QVBoxLayout(strengths_group)

        self.strengths_edit = QTextEdit()
        self.strengths_edit.setReadOnly(True)
        self.strengths_edit.setPlaceholderText("Study strengths will appear here...")
        self.strengths_edit.setMaximumHeight(scale_px(100))

        strengths_layout.addWidget(self.strengths_edit)

        layout.addWidget(strengths_group)

        # Section: Limitations
        limitations_group = QGroupBox("Limitations")
        limitations_layout = QVBoxLayout(limitations_group)

        self.limitations_edit = QTextEdit()
        self.limitations_edit.setReadOnly(True)
        self.limitations_edit.setPlaceholderText("Study limitations will appear here...")
        self.limitations_edit.setMaximumHeight(scale_px(100))

        limitations_layout.addWidget(self.limitations_edit)

        layout.addWidget(limitations_group)

        # Section: Bias Assessment
        bias_group = QGroupBox("Bias Risk Assessment")
        bias_layout = QFormLayout(bias_group)
        bias_layout.setSpacing(scale_px(5))

        self.selection_bias_label = QLabel("—")
        self.selection_bias_label.setTextFormat(Qt.RichText)
        self.performance_bias_label = QLabel("—")
        self.performance_bias_label.setTextFormat(Qt.RichText)
        self.detection_bias_label = QLabel("—")
        self.detection_bias_label.setTextFormat(Qt.RichText)
        self.attrition_bias_label = QLabel("—")
        self.attrition_bias_label.setTextFormat(Qt.RichText)
        self.reporting_bias_label = QLabel("—")
        self.reporting_bias_label.setTextFormat(Qt.RichText)

        bias_layout.addRow("Selection Bias:", self.selection_bias_label)
        bias_layout.addRow("Performance Bias:", self.performance_bias_label)
        bias_layout.addRow("Detection Bias:", self.detection_bias_label)
        bias_layout.addRow("Attrition Bias:", self.attrition_bias_label)
        bias_layout.addRow("Reporting Bias:", self.reporting_bias_label)

        layout.addWidget(bias_group)

        layout.addStretch()

        return container

    def _refresh_models(self):
        """Refresh available models from Ollama."""
        try:
            # Get available models
            import requests
            host = self.config.get_ollama_config()['host']
            response = requests.get(f"{host}/api/tags", timeout=OLLAMA_REQUEST_TIMEOUT)

            if response.status_code == 200:
                data = response.json()
                models = [m['name'] for m in data.get('models', [])]

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
            else:
                QMessageBox.warning(self, "Error", "Failed to fetch models from Ollama")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to connect to Ollama: {str(e)}")

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
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to switch model: {str(e)}")

    def _load_document(self):
        """Load document and perform study assessment."""
        s = self.scale
        doc_id_str = self.doc_id_input.text().strip()

        if not doc_id_str:
            QMessageBox.warning(self, "Input Error", "Please enter a document ID.")
            return

        try:
            doc_id = int(doc_id_str)
        except ValueError:
            QMessageBox.warning(self, "Input Error", "Invalid document ID. Please enter a number.")
            return

        # Update status
        self.status_label.setText(f"Loading document {doc_id}...")
        self.status_label.setStyleSheet(f"color: #7B1FA2; font-size: {scale_px(11)}px;")
        self.load_button.setEnabled(False)

        try:
            # Fetch document
            documents = fetch_documents_by_ids({doc_id})

            if not documents:
                QMessageBox.warning(self, "Not Found", f"Document {doc_id} not found in database.")
                self.status_label.setText("Ready")
                self.status_label.setStyleSheet(f"color: gray; font-size: {scale_px(11)}px;")
                self.load_button.setEnabled(True)
                return

            self.current_document = documents[0]
            self._display_document()

            # Check agent
            if not self.assessment_agent:
                QMessageBox.warning(self, "Agent Error", "Study Assessment Agent not initialized. Cannot perform analysis.")
                self.status_label.setText("Agent unavailable")
                self.status_label.setStyleSheet(f"color: red; font-size: {scale_px(11)}px;")
                self.load_button.setEnabled(True)
                return

            # Start study assessment in background
            self.status_label.setText("Running study assessment...")
            self.status_label.setStyleSheet(f"color: #7B1FA2; font-size: {scale_px(11)}px;")

            self.worker = StudyAssessmentWorker(self.assessment_agent, self.current_document)
            self.worker.result_ready.connect(self._on_assessment_complete)
            self.worker.error_occurred.connect(self._on_assessment_error)
            self.worker.finished.connect(lambda: self.load_button.setEnabled(True))
            self.worker.start()

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error loading document: {str(e)}")
            self.status_label.setText(f"Error: {str(e)[:50]}...")
            self.status_label.setStyleSheet(f"color: red; font-size: {scale_px(11)}px;")
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

    def _on_assessment_complete(self, assessment: StudyAssessment):
        """Handle study assessment completion."""
        s = self.scale
        self.current_assessment = assessment
        self._display_assessment_results()

        confidence_pct = assessment.overall_confidence * 100
        self.status_label.setText(f"✓ Assessment complete (quality: {assessment.quality_score:.1f}/10, confidence: {confidence_pct:.1f}%)")
        self.status_label.setStyleSheet(f"color: #2E7D32; font-size: {scale_px(11)}px;")
        self.status_message.emit(f"Study assessment complete - {assessment.quality_score:.1f}/10 quality, {confidence_pct:.1f}% confidence")

    def _on_assessment_error(self, error_msg: str):
        """Handle study assessment error."""
        s = self.scale
        QMessageBox.critical(self, "Assessment Error", f"Study assessment failed: {error_msg}")
        self.status_label.setText("Assessment failed")
        self.status_label.setStyleSheet(f"color: red; font-size: {scale_px(11)}px;")

    def _display_assessment_results(self):
        """Display study assessment results."""
        if not self.current_assessment:
            return

        s = self.scale
        a = self.current_assessment

        # Study Classification
        self.study_type_label.setText(a.study_type or "—")
        self.study_design_label.setText(a.study_design or "—")
        self.evidence_level_label.setText(a.evidence_level or "—")

        # Quality Assessment
        self.quality_score_label.setText(f"{a.quality_score:.1f} / 10")

        # Color-code quality score using thresholds from study_assessment_agent
        if a.quality_score >= QUALITY_THRESHOLD_EXCEPTIONAL:
            self.quality_score_label.setStyleSheet("color: #1B5E20; font-weight: bold; font-size: 14px;")  # Dark green
        elif a.quality_score >= QUALITY_THRESHOLD_HIGH:
            self.quality_score_label.setStyleSheet("color: #2E7D32; font-weight: bold; font-size: 14px;")  # Green
        elif a.quality_score >= QUALITY_THRESHOLD_MODERATE:
            self.quality_score_label.setStyleSheet("color: #F57C00; font-weight: bold; font-size: 14px;")  # Orange
        elif a.quality_score >= QUALITY_THRESHOLD_LOW:
            self.quality_score_label.setStyleSheet("color: #E64A19; font-weight: bold; font-size: 14px;")  # Dark orange
        else:
            self.quality_score_label.setStyleSheet("color: #C62828; font-weight: bold; font-size: 14px;")  # Red

        confidence_pct = a.overall_confidence * 100
        self.confidence_label.setText(f"{confidence_pct:.1f}%")

        # Color-code confidence
        if a.overall_confidence >= CONFIDENCE_THRESHOLD_HIGH:
            self.confidence_label.setStyleSheet("color: #2E7D32; font-weight: bold; font-size: 14px;")
        elif a.overall_confidence >= CONFIDENCE_THRESHOLD_MODERATE:
            self.confidence_label.setStyleSheet("color: #F57C00; font-weight: bold; font-size: 14px;")
        else:
            self.confidence_label.setStyleSheet("color: #C62828; font-weight: bold; font-size: 14px;")

        self.confidence_explanation_edit.setPlainText(a.confidence_explanation or "—")

        # Study Characteristics
        self.sample_size_label.setText(f"Sample Size: {a.sample_size or '—'}")
        self.follow_up_label.setText(f"Follow-up: {a.follow_up_duration or '—'}")

        # Design characteristics
        chars = []
        if a.is_prospective:
            chars.append("Prospective")
        if a.is_retrospective:
            chars.append("Retrospective")
        if a.is_randomized:
            chars.append("Randomized")
        if a.is_controlled:
            chars.append("Controlled")
        if a.is_double_blinded:
            chars.append("Double-blinded")
        elif a.is_blinded:
            chars.append("Blinded")
        if a.is_multi_center:
            chars.append("Multi-center")

        self.characteristics_label.setText(f"Characteristics: {', '.join(chars) if chars else '—'}")

        # Strengths
        strengths_text = "\n".join([f"• {s}" for s in a.strengths]) if a.strengths else "—"
        self.strengths_edit.setPlainText(strengths_text)

        # Limitations
        limitations_text = "\n".join([f"• {l}" for l in a.limitations]) if a.limitations else "—"
        self.limitations_edit.setPlainText(limitations_text)

        # Bias Assessment
        self.selection_bias_label.setText(self._format_bias_risk(a.selection_bias_risk))
        self.performance_bias_label.setText(self._format_bias_risk(a.performance_bias_risk))
        self.detection_bias_label.setText(self._format_bias_risk(a.detection_bias_risk))
        self.attrition_bias_label.setText(self._format_bias_risk(a.attrition_bias_risk))
        self.reporting_bias_label.setText(self._format_bias_risk(a.reporting_bias_risk))

    def _format_bias_risk(self, risk: Optional[str]) -> str:
        """
        Format bias risk with color coding.

        Args:
            risk: Bias risk level (low, moderate, high, unclear, or None)

        Returns:
            HTML-formatted string with color-coded bias risk
        """
        if not risk:
            return "—"

        # Create a rich text label with color
        if risk.lower() == "low":
            color = "#2E7D32"  # Green
        elif risk.lower() == "moderate":
            color = "#F57C00"  # Orange
        elif risk.lower() == "high":
            color = "#C62828"  # Red
        else:  # unclear
            color = "#757575"  # Gray

        return f'<span style="color: {color}; font-weight: bold;">{risk.capitalize()}</span>'

    def _clear_all(self):
        """Clear all fields."""
        s = self.scale
        self.doc_id_input.clear()
        self.doc_title_label.setText("No document loaded")
        self.doc_metadata_label.setText("")
        self.doc_abstract_edit.clear()

        # Clear all assessment fields
        self.study_type_label.setText("—")
        self.study_design_label.setText("—")
        self.evidence_level_label.setText("—")
        self.quality_score_label.setText("—")
        self.quality_score_label.setStyleSheet("color: #2E7D32; font-weight: bold; font-size: 14px;")
        self.confidence_label.setText("—")
        self.confidence_label.setStyleSheet("color: #2E7D32; font-weight: bold; font-size: 14px;")
        self.confidence_explanation_edit.clear()

        self.sample_size_label.setText("Sample Size: —")
        self.follow_up_label.setText("Follow-up: —")
        self.characteristics_label.setText("Characteristics: —")

        self.strengths_edit.clear()
        self.limitations_edit.clear()

        self.selection_bias_label.setText("—")
        self.performance_bias_label.setText("—")
        self.detection_bias_label.setText("—")
        self.attrition_bias_label.setText("—")
        self.reporting_bias_label.setText("—")

        self.status_label.setText("Ready")
        self.status_label.setStyleSheet(f"color: gray; font-size: {scale_px(11)}px;")

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
