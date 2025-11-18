"""
PICO Lab Tab Widget for BMLibrarian Qt GUI.

Interactive interface for experimenting with PICOAgent and extracting
Population, Intervention, Comparison, and Outcome components from research papers.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QGroupBox, QLineEdit, QComboBox, QSplitter,
    QMessageBox, QFormLayout
)
from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtGui import QFont, QIntValidator
from typing import Optional, Dict, Any

from bmlibrarian.agents import PICOAgent, AgentOrchestrator
from bmlibrarian.agents.pico_agent import PICOExtraction
from bmlibrarian.config import get_config
from bmlibrarian.database import fetch_documents_by_ids


class PICOExtractionWorker(QThread):
    """Worker thread for PICO extraction to prevent UI blocking."""

    result_ready = Signal(object)  # PICOExtraction object
    error_occurred = Signal(str)

    def __init__(self, pico_agent: PICOAgent, document: Dict[str, Any]):
        """
        Initialize worker thread.

        Args:
            pico_agent: PICOAgent instance
            document: Document dictionary
        """
        super().__init__()
        self.pico_agent = pico_agent
        self.document = document

    def run(self):
        """Execute PICO extraction in background thread."""
        try:
            extraction = self.pico_agent.extract_pico_from_document(
                document=self.document,
                min_confidence=0.0  # Show all extractions
            )
            if extraction:
                self.result_ready.emit(extraction)
            else:
                self.error_occurred.emit("PICO extraction returned no results")
        except Exception as e:
            self.error_occurred.emit(str(e))


class PICOLabTabWidget(QWidget):
    """Main PICO Lab tab widget."""

    status_message = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None):
        """
        Initialize PICO Lab tab.

        Args:
            parent: Optional parent widget
        """
        super().__init__(parent)

        self.config = get_config()
        self.pico_agent: Optional[PICOAgent] = None
        self.orchestrator: Optional[AgentOrchestrator] = None
        self.worker: Optional[PICOExtractionWorker] = None
        self.current_document: Optional[Dict[str, Any]] = None
        self.current_extraction: Optional[PICOExtraction] = None

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

        # PICO results
        self.pico_confidence_label: Optional[QLabel] = None
        self.study_info_label: Optional[QLabel] = None
        self.population_edit: Optional[QTextEdit] = None
        self.population_conf_label: Optional[QLabel] = None
        self.intervention_edit: Optional[QTextEdit] = None
        self.intervention_conf_label: Optional[QLabel] = None
        self.comparison_edit: Optional[QTextEdit] = None
        self.comparison_conf_label: Optional[QLabel] = None
        self.outcome_edit: Optional[QTextEdit] = None
        self.outcome_conf_label: Optional[QLabel] = None

        self.status_label: Optional[QLabel] = None

        self._init_agent()
        self._setup_ui()

    def _init_agent(self):
        """Initialize PICOAgent with orchestrator."""
        try:
            self.orchestrator = AgentOrchestrator(max_workers=2)

            # Get configuration
            default_model = self.config.get_model('pico_agent') or "gpt-oss:20b"
            agent_config = self.config.get_agent_config('pico') or {}
            host = self.config.get_ollama_config()['host']

            self.pico_agent = PICOAgent(
                model=default_model,
                host=host,
                temperature=agent_config.get('temperature', 0.1),
                top_p=agent_config.get('top_p', 0.9),
                max_tokens=agent_config.get('max_tokens', 2000),
                orchestrator=self.orchestrator,
                show_model_info=True
            )
            print(f"✓ PICOAgent initialized with model: {default_model}")
        except Exception as e:
            print(f"Warning: Failed to initialize PICOAgent: {e}")
            self.pico_agent = None

    def _setup_ui(self):
        """Setup the user interface."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)

        # Header
        header = self._create_header()
        main_layout.addWidget(header)

        # Input panel
        input_panel = self._create_input_panel()
        main_layout.addWidget(input_panel)

        # Splitter for document and PICO panels
        splitter = QSplitter(Qt.Horizontal)

        # Left: Document display
        doc_panel = self._create_document_panel()
        splitter.addWidget(doc_panel)

        # Right: PICO results
        pico_panel = self._create_pico_panel()
        splitter.addWidget(pico_panel)

        # Set initial sizes (40% document, 60% PICO)
        splitter.setSizes([400, 600])

        main_layout.addWidget(splitter, stretch=1)

        # Status bar
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color: gray; font-size: 11px;")
        main_layout.addWidget(self.status_label)

    def _create_header(self) -> QWidget:
        """Create header section."""
        header_widget = QWidget()
        header_layout = QVBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(5)

        title = QLabel("PICO Laboratory")
        title.setFont(QFont("", 20, QFont.Bold))
        title.setStyleSheet("color: #1976D2;")

        subtitle = QLabel("Extract Population, Intervention, Comparison, and Outcome components from research papers")
        subtitle.setStyleSheet("color: gray; font-size: 12px;")

        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)

        return header_widget

    def _create_input_panel(self) -> QGroupBox:
        """Create input panel for document loading."""
        group = QGroupBox("Document Input")
        layout = QVBoxLayout(group)
        layout.setSpacing(10)

        # Model selection row
        model_row = QHBoxLayout()
        model_label = QLabel("PICO Model:")
        model_label.setFont(QFont("", 10, QFont.Bold))

        self.model_combo = QComboBox()
        self.model_combo.setMinimumWidth(300)
        self._refresh_models()
        self.model_combo.currentTextChanged.connect(self._on_model_changed)

        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self._refresh_models)
        self.refresh_button.setMaximumWidth(80)

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
        self.doc_id_input.setMaximumWidth(200)
        self.doc_id_input.setValidator(QIntValidator(1, 999999999))
        self.doc_id_input.returnPressed.connect(self._load_document)

        self.load_button = QPushButton("Load & Analyze")
        self.load_button.clicked.connect(self._load_document)
        self.load_button.setStyleSheet("background-color: #43A047; color: white; font-weight: bold;")
        self.load_button.setMinimumHeight(35)
        self.load_button.setMaximumWidth(150)

        self.clear_button = QPushButton("Clear")
        self.clear_button.clicked.connect(self._clear_all)
        self.clear_button.setMaximumWidth(80)
        self.clear_button.setMinimumHeight(35)

        input_row.addWidget(doc_id_label)
        input_row.addWidget(self.doc_id_input)
        input_row.addWidget(self.load_button)
        input_row.addWidget(self.clear_button)
        input_row.addStretch()

        layout.addLayout(input_row)

        return group

    def _create_document_panel(self) -> QGroupBox:
        """Create document display panel."""
        group = QGroupBox("Document")
        layout = QVBoxLayout(group)
        layout.setSpacing(10)

        # Title
        self.doc_title_label = QLabel("No document loaded")
        self.doc_title_label.setFont(QFont("", 12, QFont.Bold))
        self.doc_title_label.setWordWrap(True)
        self.doc_title_label.setStyleSheet("color: #424242;")

        # Metadata
        self.doc_metadata_label = QLabel("")
        self.doc_metadata_label.setStyleSheet("color: gray; font-size: 11px;")
        self.doc_metadata_label.setWordWrap(True)

        # Abstract
        abstract_label = QLabel("Abstract:")
        abstract_label.setFont(QFont("", 10, QFont.Bold))

        self.doc_abstract_edit = QTextEdit()
        self.doc_abstract_edit.setReadOnly(True)
        self.doc_abstract_edit.setPlaceholderText("Document abstract will appear here...")

        layout.addWidget(self.doc_title_label)
        layout.addWidget(self.doc_metadata_label)
        layout.addSpacing(10)
        layout.addWidget(abstract_label)
        layout.addWidget(self.doc_abstract_edit)

        return group

    def _create_pico_panel(self) -> QGroupBox:
        """Create PICO results display panel."""
        group = QGroupBox("PICO Analysis")
        layout = QVBoxLayout(group)
        layout.setSpacing(10)

        # Overall confidence and study info
        self.pico_confidence_label = QLabel("")
        self.pico_confidence_label.setFont(QFont("", 11, QFont.Bold))
        self.pico_confidence_label.setStyleSheet("color: #2E7D32;")

        self.study_info_label = QLabel("")
        self.study_info_label.setStyleSheet("color: #424242; font-size: 11px;")
        self.study_info_label.setWordWrap(True)

        layout.addWidget(self.pico_confidence_label)
        layout.addWidget(self.study_info_label)

        # Population
        pop_label = QLabel("Population (P):")
        pop_label.setFont(QFont("", 10, QFont.Bold))
        pop_label.setStyleSheet("color: #1976D2;")

        self.population_edit = QTextEdit()
        self.population_edit.setReadOnly(True)
        self.population_edit.setPlaceholderText("Population will appear here...")
        self.population_edit.setMaximumHeight(80)

        self.population_conf_label = QLabel("")
        self.population_conf_label.setStyleSheet("color: gray; font-size: 10px;")

        layout.addWidget(pop_label)
        layout.addWidget(self.population_edit)
        layout.addWidget(self.population_conf_label)

        # Intervention
        int_label = QLabel("Intervention (I):")
        int_label.setFont(QFont("", 10, QFont.Bold))
        int_label.setStyleSheet("color: #388E3C;")

        self.intervention_edit = QTextEdit()
        self.intervention_edit.setReadOnly(True)
        self.intervention_edit.setPlaceholderText("Intervention will appear here...")
        self.intervention_edit.setMaximumHeight(80)

        self.intervention_conf_label = QLabel("")
        self.intervention_conf_label.setStyleSheet("color: gray; font-size: 10px;")

        layout.addWidget(int_label)
        layout.addWidget(self.intervention_edit)
        layout.addWidget(self.intervention_conf_label)

        # Comparison
        comp_label = QLabel("Comparison (C):")
        comp_label.setFont(QFont("", 10, QFont.Bold))
        comp_label.setStyleSheet("color: #F57C00;")

        self.comparison_edit = QTextEdit()
        self.comparison_edit.setReadOnly(True)
        self.comparison_edit.setPlaceholderText("Comparison will appear here...")
        self.comparison_edit.setMaximumHeight(80)

        self.comparison_conf_label = QLabel("")
        self.comparison_conf_label.setStyleSheet("color: gray; font-size: 10px;")

        layout.addWidget(comp_label)
        layout.addWidget(self.comparison_edit)
        layout.addWidget(self.comparison_conf_label)

        # Outcome
        out_label = QLabel("Outcome (O):")
        out_label.setFont(QFont("", 10, QFont.Bold))
        out_label.setStyleSheet("color: #7B1FA2;")

        self.outcome_edit = QTextEdit()
        self.outcome_edit.setReadOnly(True)
        self.outcome_edit.setPlaceholderText("Outcome will appear here...")
        self.outcome_edit.setMaximumHeight(80)

        self.outcome_conf_label = QLabel("")
        self.outcome_conf_label.setStyleSheet("color: gray; font-size: 10px;")

        layout.addWidget(out_label)
        layout.addWidget(self.outcome_edit)
        layout.addWidget(self.outcome_conf_label)

        layout.addStretch()

        return group

    def _refresh_models(self):
        """Refresh available models from Ollama."""
        try:
            # Get available models
            import requests
            host = self.config.get_ollama_config()['host']
            response = requests.get(f"{host}/api/tags", timeout=5)

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
                    default_model = self.config.get_model('pico_agent') or "gpt-oss:20b"
                    if default_model in models:
                        self.model_combo.setCurrentText(default_model)

                self.status_message.emit(f"Refreshed models - {len(models)} available")
            else:
                QMessageBox.warning(self, "Error", "Failed to fetch models from Ollama")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to connect to Ollama: {str(e)}")

    def _on_model_changed(self, model_name: str):
        """Handle model selection change."""
        if not model_name or not self.pico_agent:
            return

        try:
            # Reinitialize agent with new model
            agent_config = self.config.get_agent_config('pico') or {}
            host = self.config.get_ollama_config()['host']

            self.pico_agent = PICOAgent(
                model=model_name,
                host=host,
                temperature=agent_config.get('temperature', 0.1),
                top_p=agent_config.get('top_p', 0.9),
                max_tokens=agent_config.get('max_tokens', 2000),
                orchestrator=self.orchestrator,
                show_model_info=True
            )
            self.status_message.emit(f"Switched to model: {model_name}")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to switch model: {str(e)}")

    def _load_document(self):
        """Load document and perform PICO analysis."""
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
        self.status_label.setStyleSheet("color: #1976D2; font-size: 11px;")
        self.load_button.setEnabled(False)

        try:
            # Fetch document
            documents = fetch_documents_by_ids({doc_id})

            if not documents:
                QMessageBox.warning(self, "Not Found", f"Document {doc_id} not found in database.")
                self.status_label.setText("Ready")
                self.status_label.setStyleSheet("color: gray; font-size: 11px;")
                self.load_button.setEnabled(True)
                return

            self.current_document = documents[0]
            self._display_document()

            # Check agent
            if not self.pico_agent:
                QMessageBox.warning(self, "Agent Error", "PICO Agent not initialized. Cannot perform analysis.")
                self.status_label.setText("Agent unavailable")
                self.status_label.setStyleSheet("color: red; font-size: 11px;")
                self.load_button.setEnabled(True)
                return

            # Start PICO extraction in background
            self.status_label.setText("Running PICO extraction...")
            self.status_label.setStyleSheet("color: #1976D2; font-size: 11px;")

            self.worker = PICOExtractionWorker(self.pico_agent, self.current_document)
            self.worker.result_ready.connect(self._on_extraction_complete)
            self.worker.error_occurred.connect(self._on_extraction_error)
            self.worker.finished.connect(lambda: self.load_button.setEnabled(True))
            self.worker.start()

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error loading document: {str(e)}")
            self.status_label.setText(f"Error: {str(e)[:50]}...")
            self.status_label.setStyleSheet("color: red; font-size: 11px;")
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

    def _on_extraction_complete(self, extraction: PICOExtraction):
        """Handle PICO extraction completion."""
        self.current_extraction = extraction
        self._display_pico_results()

        confidence_pct = extraction.extraction_confidence * 100
        self.status_label.setText(f"✓ Analysis complete (confidence: {confidence_pct:.1f}%)")
        self.status_label.setStyleSheet("color: #2E7D32; font-size: 11px;")
        self.status_message.emit(f"PICO extraction complete - {confidence_pct:.1f}% confidence")

    def _on_extraction_error(self, error_msg: str):
        """Handle PICO extraction error."""
        QMessageBox.critical(self, "Extraction Error", f"PICO extraction failed: {error_msg}")
        self.status_label.setText("Extraction failed")
        self.status_label.setStyleSheet("color: red; font-size: 11px;")

    def _display_pico_results(self):
        """Display PICO extraction results."""
        if not self.current_extraction:
            return

        ext = self.current_extraction

        # Overall info
        confidence_pct = ext.extraction_confidence * 100
        self.pico_confidence_label.setText(f"Overall Confidence: {confidence_pct:.1f}%")

        # Color-code confidence
        if ext.extraction_confidence >= 0.8:
            self.pico_confidence_label.setStyleSheet("color: #2E7D32; font-weight: bold; font-size: 11pt;")
        elif ext.extraction_confidence >= 0.6:
            self.pico_confidence_label.setStyleSheet("color: #F57C00; font-weight: bold; font-size: 11pt;")
        else:
            self.pico_confidence_label.setStyleSheet("color: #C62828; font-weight: bold; font-size: 11pt;")

        study_info_parts = []
        if ext.study_type:
            study_info_parts.append(f"Study Type: {ext.study_type}")
        if ext.sample_size:
            study_info_parts.append(f"Sample Size: {ext.sample_size}")

        self.study_info_label.setText(" | ".join(study_info_parts))

        # Population
        self.population_edit.setPlainText(ext.population or "Not identified")
        if ext.population_confidence:
            pop_conf = ext.population_confidence * 100
            self.population_conf_label.setText(f"Confidence: {pop_conf:.1f}%")
        else:
            self.population_conf_label.setText("")

        # Intervention
        self.intervention_edit.setPlainText(ext.intervention or "Not identified")
        if ext.intervention_confidence:
            int_conf = ext.intervention_confidence * 100
            self.intervention_conf_label.setText(f"Confidence: {int_conf:.1f}%")
        else:
            self.intervention_conf_label.setText("")

        # Comparison
        self.comparison_edit.setPlainText(ext.comparison or "Not identified")
        if ext.comparison_confidence:
            comp_conf = ext.comparison_confidence * 100
            self.comparison_conf_label.setText(f"Confidence: {comp_conf:.1f}%")
        else:
            self.comparison_conf_label.setText("")

        # Outcome
        self.outcome_edit.setPlainText(ext.outcome or "Not identified")
        if ext.outcome_confidence:
            out_conf = ext.outcome_confidence * 100
            self.outcome_conf_label.setText(f"Confidence: {out_conf:.1f}%")
        else:
            self.outcome_conf_label.setText("")

    def _clear_all(self):
        """Clear all fields."""
        self.doc_id_input.clear()
        self.doc_title_label.setText("No document loaded")
        self.doc_metadata_label.setText("")
        self.doc_abstract_edit.clear()

        self.pico_confidence_label.setText("")
        self.study_info_label.setText("")
        self.population_edit.clear()
        self.population_conf_label.setText("")
        self.intervention_edit.clear()
        self.intervention_conf_label.setText("")
        self.comparison_edit.clear()
        self.comparison_conf_label.setText("")
        self.outcome_edit.clear()
        self.outcome_conf_label.setText("")

        self.status_label.setText("Ready")
        self.status_label.setStyleSheet("color: gray; font-size: 11px;")

        self.current_document = None
        self.current_extraction = None

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
