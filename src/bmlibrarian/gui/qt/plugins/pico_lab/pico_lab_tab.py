"""
PICO Lab Tab Widget for BMLibrarian Qt GUI.

Interactive interface for extracting PICO components from research papers.
Space-efficient layout with document ID input, model selector, and splitter view.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QLineEdit, QComboBox, QMessageBox, QSplitter,
    QGroupBox, QScrollArea, QFrame
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
            document: Document dictionary with abstract and metadata
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
    """Main PICO Lab tab widget with space-efficient layout."""

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
        self.doc_id_input: Optional[QLineEdit] = None
        self.model_combo: Optional[QComboBox] = None
        self.load_btn: Optional[QPushButton] = None
        self.clear_btn: Optional[QPushButton] = None
        self.status_label: Optional[QLabel] = None

        # Abstract panel components
        self.abstract_text: Optional[QTextEdit] = None
        self.doc_title_label: Optional[QLabel] = None
        self.doc_metadata_label: Optional[QLabel] = None

        # PICO panel components
        self.confidence_label: Optional[QLabel] = None
        self.study_info_label: Optional[QLabel] = None
        self.population_text: Optional[QTextEdit] = None
        self.population_conf_label: Optional[QLabel] = None
        self.intervention_text: Optional[QTextEdit] = None
        self.intervention_conf_label: Optional[QLabel] = None
        self.comparison_text: Optional[QTextEdit] = None
        self.comparison_conf_label: Optional[QLabel] = None
        self.outcome_text: Optional[QTextEdit] = None
        self.outcome_conf_label: Optional[QLabel] = None

        self._init_agent()
        self._setup_ui()

    def _init_agent(self):
        """Initialize PICOAgent with orchestrator."""
        try:
            self.orchestrator = AgentOrchestrator(max_workers=2)

            # Get configuration
            model = self.config.get_model('pico_agent') or "gpt-oss:20b"
            agent_config = self.config.get_agent_config('pico') or {}
            host = self.config.get_ollama_config()['host']

            print(f"🚀 Initializing PICOAgent with model: {model}")

            self.pico_agent = PICOAgent(
                model=model,
                host=host,
                temperature=agent_config.get('temperature', 0.1),
                top_p=agent_config.get('top_p', 0.9),
                max_tokens=agent_config.get('max_tokens', 2000),
                orchestrator=self.orchestrator,
                show_model_info=True
            )
        except Exception as e:
            print(f"Warning: Failed to initialize PICOAgent: {e}")
            self.pico_agent = None

    def _setup_ui(self):
        """Setup the user interface with space-efficient layout."""
        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(5)

        # Top row: Document ID + Model selector (fixed narrow height)
        top_row = self._create_top_row()
        main_layout.addLayout(top_row)

        # Splitter for Abstract (left) and PICO Analysis (right)
        splitter = self._create_splitter()
        main_layout.addWidget(splitter, stretch=1)

        # Status bar at bottom
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color: gray; font-size: 10pt; padding: 5px;")
        main_layout.addWidget(self.status_label)

    def _create_top_row(self) -> QHBoxLayout:
        """
        Create top row with document ID input and model selector.

        Returns:
            Layout containing top row controls
        """
        layout = QHBoxLayout()
        layout.setSpacing(10)

        # Document ID input
        id_label = QLabel("Document ID:")
        id_label.setFont(QFont("", 10, QFont.Bold))
        layout.addWidget(id_label)

        self.doc_id_input = QLineEdit()
        self.doc_id_input.setPlaceholderText("Enter document ID...")
        self.doc_id_input.setValidator(QIntValidator(1, 999999999))
        self.doc_id_input.setMaximumWidth(150)
        self.doc_id_input.returnPressed.connect(self._on_load_document)
        layout.addWidget(self.doc_id_input)

        # Model selector
        model_label = QLabel("Model:")
        model_label.setFont(QFont("", 10, QFont.Bold))
        layout.addWidget(model_label)

        self.model_combo = QComboBox()
        self.model_combo.setMinimumWidth(250)
        self._refresh_models()
        self.model_combo.currentTextChanged.connect(self._on_model_changed)
        layout.addWidget(self.model_combo)

        # Refresh models button
        refresh_btn = QPushButton("↻")
        refresh_btn.setMaximumWidth(30)
        refresh_btn.setToolTip("Refresh available models")
        refresh_btn.clicked.connect(self._on_refresh_models)
        layout.addWidget(refresh_btn)

        layout.addStretch()

        # Load button
        self.load_btn = QPushButton("Load & Analyze")
        self.load_btn.setStyleSheet(
            "background-color: #27ae60; color: white; padding: 5px 15px; font-weight: bold;"
        )
        self.load_btn.clicked.connect(self._on_load_document)
        layout.addWidget(self.load_btn)

        # Clear button
        self.clear_btn = QPushButton("Clear")
        self.clear_btn.setStyleSheet("padding: 5px 15px;")
        self.clear_btn.clicked.connect(self._on_clear_all)
        layout.addWidget(self.clear_btn)

        return layout

    def _create_splitter(self) -> QSplitter:
        """
        Create splitter with abstract (left) and PICO analysis (right).

        Returns:
            Splitter widget containing both panels
        """
        splitter = QSplitter(Qt.Horizontal)

        # Left panel: Abstract
        abstract_panel = self._create_abstract_panel()
        splitter.addWidget(abstract_panel)

        # Right panel: PICO Analysis
        pico_panel = self._create_pico_panel()
        splitter.addWidget(pico_panel)

        # Set initial sizes (50/50 split)
        splitter.setSizes([400, 400])
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)

        return splitter

    def _create_abstract_panel(self) -> QWidget:
        """
        Create abstract display panel.

        Returns:
            Widget containing abstract display
        """
        widget = QGroupBox("Document Abstract")
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # Title
        self.doc_title_label = QLabel("No document loaded")
        self.doc_title_label.setFont(QFont("", 11, QFont.Bold))
        self.doc_title_label.setWordWrap(True)
        self.doc_title_label.setStyleSheet("color: #2c3e50;")
        layout.addWidget(self.doc_title_label)

        # Metadata
        self.doc_metadata_label = QLabel("")
        self.doc_metadata_label.setFont(QFont("", 9))
        self.doc_metadata_label.setStyleSheet("color: #7f8c8d;")
        self.doc_metadata_label.setWordWrap(True)
        layout.addWidget(self.doc_metadata_label)

        # Separator
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        layout.addWidget(line)

        # Abstract text (scrollable)
        self.abstract_text = QTextEdit()
        self.abstract_text.setReadOnly(True)
        self.abstract_text.setPlaceholderText("Abstract will appear here...")
        self.abstract_text.setStyleSheet(
            "background-color: #f8f9fa; border: 1px solid #dee2e6; "
            "padding: 10px; font-size: 10pt; line-height: 1.5;"
        )
        layout.addWidget(self.abstract_text)

        return widget

    def _create_pico_panel(self) -> QWidget:
        """
        Create PICO analysis display panel.

        Returns:
            Widget containing PICO analysis display
        """
        # Use QScrollArea for the PICO panel to handle overflow
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        # Container widget
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # Title
        title_label = QLabel("PICO Analysis")
        title_label.setFont(QFont("", 12, QFont.Bold))
        title_label.setStyleSheet("color: #2c3e50;")
        layout.addWidget(title_label)

        # Overall confidence
        self.confidence_label = QLabel("")
        self.confidence_label.setFont(QFont("", 10, QFont.Bold))
        layout.addWidget(self.confidence_label)

        # Study info
        self.study_info_label = QLabel("")
        self.study_info_label.setFont(QFont("", 9))
        self.study_info_label.setStyleSheet("color: #7f8c8d;")
        layout.addWidget(self.study_info_label)

        # Separator
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        layout.addWidget(line)

        # Population
        self._add_pico_component(
            layout, "Population (P)", "#3498db",
            lambda: self.population_text, lambda: self.population_conf_label
        )

        # Intervention
        self._add_pico_component(
            layout, "Intervention (I)", "#27ae60",
            lambda: self.intervention_text, lambda: self.intervention_conf_label
        )

        # Comparison
        self._add_pico_component(
            layout, "Comparison (C)", "#e67e22",
            lambda: self.comparison_text, lambda: self.comparison_conf_label
        )

        # Outcome
        self._add_pico_component(
            layout, "Outcome (O)", "#9b59b6",
            lambda: self.outcome_text, lambda: self.outcome_conf_label
        )

        layout.addStretch()

        scroll.setWidget(container)
        return scroll

    def _add_pico_component(
        self, layout: QVBoxLayout, label: str, color: str,
        text_getter, conf_getter
    ):
        """
        Add a PICO component to the layout.

        Args:
            layout: Parent layout
            label: Component label (e.g., "Population (P)")
            color: Border color for the text edit
            text_getter: Function that returns the text edit widget reference
            conf_getter: Function that returns the confidence label reference
        """
        # Label
        comp_label = QLabel(label)
        comp_label.setFont(QFont("", 10, QFont.Bold))
        comp_label.setStyleSheet(f"color: {color};")
        layout.addWidget(comp_label)

        # Text edit
        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setPlaceholderText(f"{label} will appear here...")
        text_edit.setMaximumHeight(80)
        text_edit.setStyleSheet(
            f"background-color: white; border: 2px solid {color}; "
            f"border-radius: 5px; padding: 5px; font-size: 10pt;"
        )

        # Store reference based on label
        if "Population" in label:
            self.population_text = text_edit
        elif "Intervention" in label:
            self.intervention_text = text_edit
        elif "Comparison" in label:
            self.comparison_text = text_edit
        elif "Outcome" in label:
            self.outcome_text = text_edit

        layout.addWidget(text_edit)

        # Confidence label
        conf_label = QLabel("")
        conf_label.setFont(QFont("", 9))
        conf_label.setStyleSheet("color: #7f8c8d;")

        # Store reference based on label
        if "Population" in label:
            self.population_conf_label = conf_label
        elif "Intervention" in label:
            self.intervention_conf_label = conf_label
        elif "Comparison" in label:
            self.comparison_conf_label = conf_label
        elif "Outcome" in label:
            self.outcome_conf_label = conf_label

        layout.addWidget(conf_label)

    def _refresh_models(self):
        """Refresh available models from Ollama."""
        try:
            import ollama
            host = self.config.get_ollama_config()['host']
            client = ollama.Client(host=host)
            models_response = client.list()

            models = sorted([model.model for model in models_response.models])

            # Get current selection
            current_model = self.model_combo.currentText() if self.model_combo else None

            # Update combo box
            if self.model_combo:
                self.model_combo.clear()
                self.model_combo.addItems(models)

                # Restore selection or use configured model
                configured_model = self.config.get_model('pico_agent')
                if current_model and current_model in models:
                    self.model_combo.setCurrentText(current_model)
                elif configured_model and configured_model in models:
                    self.model_combo.setCurrentText(configured_model)
                elif models:
                    self.model_combo.setCurrentIndex(0)
        except Exception as e:
            print(f"Failed to refresh models: {e}")
            # Fallback models
            if self.model_combo:
                self.model_combo.clear()
                self.model_combo.addItems([
                    "gpt-oss:20b",
                    "medgemma-27b-text-it-Q8_0:latest",
                    "medgemma4B_it_q8:latest"
                ])

    def _on_refresh_models(self):
        """Handle model refresh button click."""
        self._refresh_models()
        self.status_message.emit("Models refreshed")
        QMessageBox.information(self, "Success", "Models refreshed successfully!")

    def _on_model_changed(self, model: str):
        """
        Handle model selection change.

        Args:
            model: New model name
        """
        if not model:
            return

        print(f"Model changed to: {model}")
        self.status_label.setText(f"Switching to {model}...")
        self.status_label.setStyleSheet("color: blue; font-size: 10pt; padding: 5px;")

        # Reinitialize agent with new model
        self._reinit_agent(model)

        if self.pico_agent:
            self.status_label.setText(f"Ready (using {model})")
            self.status_label.setStyleSheet("color: green; font-size: 10pt; padding: 5px;")
        else:
            self.status_label.setText("Agent initialization failed")
            self.status_label.setStyleSheet("color: red; font-size: 10pt; padding: 5px;")

    def _reinit_agent(self, model: str):
        """
        Reinitialize PICOAgent with new model.

        Args:
            model: Model name
        """
        try:
            agent_config = self.config.get_agent_config('pico') or {}
            host = self.config.get_ollama_config()['host']

            print(f"🔄 Reinitializing PICOAgent with model: {model}")

            self.pico_agent = PICOAgent(
                model=model,
                host=host,
                temperature=agent_config.get('temperature', 0.1),
                top_p=agent_config.get('top_p', 0.9),
                max_tokens=agent_config.get('max_tokens', 2000),
                orchestrator=self.orchestrator,
                show_model_info=True
            )
        except Exception as e:
            print(f"Failed to reinitialize agent: {e}")
            self.pico_agent = None

    def _on_load_document(self):
        """Load document and perform PICO analysis."""
        doc_id_str = self.doc_id_input.text().strip()

        if not doc_id_str:
            QMessageBox.warning(self, "Warning", "Please enter a document ID.")
            return

        try:
            doc_id = int(doc_id_str)
        except ValueError:
            QMessageBox.warning(self, "Warning", "Invalid document ID. Please enter a number.")
            return

        # Update status
        self.status_label.setText(f"Loading document {doc_id}...")
        self.status_label.setStyleSheet("color: blue; font-size: 10pt; padding: 5px;")
        self.status_message.emit(f"Loading document {doc_id}...")

        try:
            # Fetch document from database
            documents = fetch_documents_by_ids({doc_id})

            if not documents:
                QMessageBox.warning(
                    self, "Warning",
                    f"Document {doc_id} not found in database."
                )
                self.status_label.setText("Ready")
                self.status_label.setStyleSheet("color: gray; font-size: 10pt; padding: 5px;")
                return

            self.current_document = documents[0]

            # Display document
            self._display_document()

            # Check agent availability
            if not self.pico_agent:
                QMessageBox.warning(
                    self, "Warning",
                    "PICO Agent not initialized. Cannot perform analysis."
                )
                self.status_label.setText("Agent unavailable")
                self.status_label.setStyleSheet("color: red; font-size: 10pt; padding: 5px;")
                return

            # Update status
            self.status_label.setText("Running PICO extraction...")
            self.status_label.setStyleSheet("color: blue; font-size: 10pt; padding: 5px;")
            self.status_message.emit("Running PICO extraction...")

            # Run extraction in background thread
            self.worker = PICOExtractionWorker(self.pico_agent, self.current_document)
            self.worker.result_ready.connect(self._on_extraction_result)
            self.worker.error_occurred.connect(self._on_extraction_error)
            self.worker.start()

        except Exception as ex:
            QMessageBox.critical(self, "Error", f"Error loading document:\n\n{str(ex)}")
            self.status_label.setText(f"Error: {str(ex)[:50]}...")
            self.status_label.setStyleSheet("color: red; font-size: 10pt; padding: 5px;")

    def _display_document(self):
        """Display the loaded document."""
        if not self.current_document:
            return

        # Title
        title = self.current_document.get('title', 'Untitled')
        self.doc_title_label.setText(title)

        # Metadata
        metadata_parts = []
        if self.current_document.get('pmid'):
            metadata_parts.append(f"PMID: {self.current_document['pmid']}")
        if self.current_document.get('doi'):
            metadata_parts.append(f"DOI: {self.current_document['doi']}")
        if self.current_document.get('publication_date'):
            metadata_parts.append(f"Date: {self.current_document['publication_date']}")
        if self.current_document.get('source_name'):
            metadata_parts.append(f"Source: {self.current_document['source_name']}")

        self.doc_metadata_label.setText(" | ".join(metadata_parts))

        # Abstract
        abstract = self.current_document.get('abstract', 'No abstract available')
        self.abstract_text.setPlainText(abstract)

    def _on_extraction_result(self, extraction: PICOExtraction):
        """
        Handle PICO extraction result.

        Args:
            extraction: PICOExtraction object
        """
        self.current_extraction = extraction
        self._display_pico_results()

        # Update status
        confidence_pct = extraction.extraction_confidence * 100
        self.status_label.setText(
            f"✅ Analysis complete (confidence: {confidence_pct:.0f}%)"
        )
        self.status_label.setStyleSheet("color: green; font-size: 10pt; padding: 5px;")
        self.status_message.emit("PICO analysis completed successfully")

    def _on_extraction_error(self, error: str):
        """
        Handle PICO extraction error.

        Args:
            error: Error message
        """
        QMessageBox.critical(
            self, "Error",
            f"PICO extraction failed:\n\n{error}"
        )
        self.status_label.setText("Extraction failed")
        self.status_label.setStyleSheet("color: red; font-size: 10pt; padding: 5px;")
        self.status_message.emit(f"PICO extraction failed: {error}")

    def _display_pico_results(self):
        """Display PICO extraction results."""
        if not self.current_extraction:
            return

        ex = self.current_extraction

        # Overall confidence
        confidence_pct = ex.extraction_confidence * 100
        self.confidence_label.setText(f"Overall Confidence: {confidence_pct:.0f}%")

        if ex.extraction_confidence >= 0.8:
            self.confidence_label.setStyleSheet("color: #27ae60; font-weight: bold;")
        elif ex.extraction_confidence >= 0.6:
            self.confidence_label.setStyleSheet("color: #e67e22; font-weight: bold;")
        else:
            self.confidence_label.setStyleSheet("color: #e74c3c; font-weight: bold;")

        # Study info
        study_parts = []
        if ex.study_type:
            study_parts.append(f"Study Type: {ex.study_type}")
        if ex.sample_size:
            study_parts.append(f"Sample Size: {ex.sample_size}")
        self.study_info_label.setText(" | ".join(study_parts) if study_parts else "")

        # Population
        self.population_text.setPlainText(ex.population)
        if ex.population_confidence:
            self.population_conf_label.setText(f"Confidence: {ex.population_confidence * 100:.0f}%")
        else:
            self.population_conf_label.setText("")

        # Intervention
        self.intervention_text.setPlainText(ex.intervention)
        if ex.intervention_confidence:
            self.intervention_conf_label.setText(f"Confidence: {ex.intervention_confidence * 100:.0f}%")
        else:
            self.intervention_conf_label.setText("")

        # Comparison
        self.comparison_text.setPlainText(ex.comparison)
        if ex.comparison_confidence:
            self.comparison_conf_label.setText(f"Confidence: {ex.comparison_confidence * 100:.0f}%")
        else:
            self.comparison_conf_label.setText("")

        # Outcome
        self.outcome_text.setPlainText(ex.outcome)
        if ex.outcome_confidence:
            self.outcome_conf_label.setText(f"Confidence: {ex.outcome_confidence * 100:.0f}%")
        else:
            self.outcome_conf_label.setText("")

    def _on_clear_all(self):
        """Clear all fields."""
        self.doc_id_input.clear()
        self.doc_title_label.setText("No document loaded")
        self.doc_metadata_label.setText("")
        self.abstract_text.clear()

        self.confidence_label.setText("")
        self.study_info_label.setText("")
        self.population_text.clear()
        self.population_conf_label.setText("")
        self.intervention_text.clear()
        self.intervention_conf_label.setText("")
        self.comparison_text.clear()
        self.comparison_conf_label.setText("")
        self.outcome_text.clear()
        self.outcome_conf_label.setText("")

        self.current_document = None
        self.current_extraction = None

        self.status_label.setText("Ready")
        self.status_label.setStyleSheet("color: gray; font-size: 10pt; padding: 5px;")
        self.status_message.emit("Cleared all fields")

    def cleanup(self):
        """Cleanup resources when tab is closed."""
        if self.worker and self.worker.isRunning():
            self.worker.terminate()
            self.worker.wait()

        if self.orchestrator:
            # Cleanup orchestrator if needed
            pass
