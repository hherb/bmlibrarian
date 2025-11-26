"""
PRISMA 2020 Lab Tab Widget for BMLibrarian Qt GUI.

Interactive interface for assessing systematic reviews and meta-analyses
against PRISMA 2020 reporting guidelines using PRISMA2020Agent.
"""

import logging
from typing import Optional, Dict, Any

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QMessageBox, QSplitter
)
from PySide6.QtCore import Qt, Signal

from bmlibrarian.agents import PRISMA2020Agent, AgentOrchestrator
from bmlibrarian.agents.prisma2020_agent import PRISMA2020Assessment
from bmlibrarian.config import get_config
from bmlibrarian.database import get_document_details
from ...resources.styles import get_font_scale, scale_px, StylesheetGenerator
from ...widgets import DocumentViewData
from ...core.document_receiver import IDocumentReceiver
from .constants import (
    SECTION_COLORS, DEFAULT_SPLITTER_SIZES,
    DEFAULT_PRISMA_MODEL, DEFAULT_TEMPERATURE,
    DEFAULT_TOP_P, DEFAULT_MAX_TOKENS, DEFAULT_MAX_WORKERS,
    STATUS_READY, ASSESSMENT_PLACEHOLDER,
)
from .worker import PRISMA2020AssessmentWorker
from .ui_builders import (
    UIComponents, create_header, create_input_panel,
    create_document_panel, create_assessment_panel,
    create_status_label, clear_layout,
)
from .assessment_display import (
    create_suitability_section, create_overall_section, create_criteria_table,
)

logger = logging.getLogger(__name__)


class PRISMA2020LabTabWidget(QWidget, IDocumentReceiver):
    """Main PRISMA 2020 Lab tab widget with document receiver capability."""

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

        # UI Components container
        self.ui = UIComponents()

        self._init_agent()
        self._setup_ui()

    def _validate_config(self) -> None:
        """Validate required configuration is present and valid."""
        logger.debug("Validating PRISMA 2020 Lab plugin configuration")

        ollama_config = self.config.get_ollama_config()
        if not ollama_config or not ollama_config.get('host'):
            logger.error("Missing required configuration: Ollama host")
            raise ValueError("Missing required configuration: Ollama host")

        logger.info(f"Ollama host configured: {ollama_config.get('host')}")

        agent_config = self.config.get_agent_config('prisma2020')
        if not agent_config:
            logger.warning("PRISMA2020 agent config not found, using defaults")
            print("Warning: PRISMA2020 agent config not found, using defaults")
        else:
            logger.debug(f"PRISMA2020 agent config loaded: {agent_config}")

    def _init_agent(self) -> None:
        """Initialize PRISMA2020Agent with orchestrator."""
        logger.info("Initializing PRISMA2020Agent")

        try:
            self._validate_config()

            self.orchestrator = AgentOrchestrator(max_workers=DEFAULT_MAX_WORKERS)
            logger.debug(f"Created AgentOrchestrator with {DEFAULT_MAX_WORKERS} workers")

            default_model = self.config.get_model('prisma2020_agent') or DEFAULT_PRISMA_MODEL
            agent_config = self.config.get_agent_config('prisma2020') or {}
            host = self.config.get_ollama_config()['host']

            logger.info(f"Initializing PRISMA2020Agent with model: {default_model}, host: {host}")

            self.prisma_agent = PRISMA2020Agent(
                model=default_model,
                host=host,
                temperature=agent_config.get('temperature', DEFAULT_TEMPERATURE),
                top_p=agent_config.get('top_p', DEFAULT_TOP_P),
                max_tokens=agent_config.get('max_tokens', DEFAULT_MAX_TOKENS),
                orchestrator=self.orchestrator,
                show_model_info=True
            )
            logger.info(f"✓ PRISMA2020Agent initialized successfully with model: {default_model}")
            print(f"✓ PRISMA2020Agent initialized with model: {default_model}")
        except Exception as e:
            logger.error(f"Failed to initialize PRISMA2020Agent: {e}", exc_info=True)
            print(f"Warning: Failed to initialize PRISMA2020Agent: {e}")
            self.prisma_agent = None

    def _setup_ui(self) -> None:
        """Setup the user interface."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(scale_px(20), scale_px(20), scale_px(20), scale_px(20))
        main_layout.setSpacing(scale_px(15))

        # Header
        header = create_header(self.stylesheet_gen)
        main_layout.addWidget(header)

        # Input panel
        input_panel = create_input_panel(
            self.stylesheet_gen,
            self.ui,
            on_model_changed=self._on_model_changed,
            on_refresh=self._refresh_models,
            on_load=self._load_document,
            on_clear=self._clear_all
        )
        main_layout.addWidget(input_panel)

        # Splitter for document and assessment panels
        splitter = QSplitter(Qt.Horizontal)

        doc_panel = create_document_panel(self.stylesheet_gen, self.ui)
        splitter.addWidget(doc_panel)

        assessment_panel = create_assessment_panel(self.stylesheet_gen, self.ui)
        splitter.addWidget(assessment_panel)

        splitter.setSizes(DEFAULT_SPLITTER_SIZES)
        main_layout.addWidget(splitter, stretch=1)

        # Status bar
        self.ui.status_label = create_status_label(self.stylesheet_gen)
        main_layout.addWidget(self.ui.status_label)

        # Initial model refresh
        self._refresh_models()

    def _refresh_models(self) -> None:
        """Refresh available models from Ollama using the agent's method."""
        logger.debug("Refreshing available models from Ollama")

        if not self.prisma_agent:
            logger.error("Cannot refresh models: PRISMA agent not initialized")
            QMessageBox.warning(
                self, "Agent Error",
                "PRISMA agent not initialized. Cannot refresh models."
            )
            return

        try:
            models = self.prisma_agent.get_available_models()
            logger.info(f"Successfully refreshed {len(models)} models from Ollama")

            current = self.ui.model_combo.currentText()
            self.ui.model_combo.clear()
            self.ui.model_combo.addItems(models)

            if current in models:
                self.ui.model_combo.setCurrentText(current)
                logger.debug(f"Restored previous model selection: {current}")
            else:
                default_model = self.config.get_model('prisma2020_agent') or DEFAULT_PRISMA_MODEL
                if default_model in models:
                    self.ui.model_combo.setCurrentText(default_model)
                    logger.debug(f"Set to default model: {default_model}")

            self.status_message.emit(f"Refreshed models - {len(models)} available")
        except ConnectionError as e:
            logger.error(f"Failed to connect to Ollama: {e}")
            QMessageBox.warning(
                self, "Connection Error",
                f"Failed to connect to Ollama: {str(e)}\n\nPlease ensure Ollama is running."
            )
        except Exception as e:
            logger.error(f"Unexpected error while refreshing models: {e}", exc_info=True)
            QMessageBox.warning(self, "Error", f"Unexpected error while refreshing models: {str(e)}")

    def _on_model_changed(self, model_name: str) -> None:
        """Handle model selection change."""
        if not model_name or not self.prisma_agent:
            return

        logger.info(f"Switching to model: {model_name}")

        try:
            agent_config = self.config.get_agent_config('prisma2020') or {}
            host = self.config.get_ollama_config()['host']

            self.prisma_agent = PRISMA2020Agent(
                model=model_name,
                host=host,
                temperature=agent_config.get('temperature', DEFAULT_TEMPERATURE),
                top_p=agent_config.get('top_p', DEFAULT_TOP_P),
                max_tokens=agent_config.get('max_tokens', DEFAULT_MAX_TOKENS),
                orchestrator=self.orchestrator,
                show_model_info=True
            )
            logger.info(f"Successfully switched to model: {model_name}")
            self.status_message.emit(f"Switched to model: {model_name}")
        except ConnectionError as e:
            logger.error(f"Connection error while switching to model {model_name}: {e}")
            QMessageBox.warning(
                self, "Connection Error",
                f"Failed to connect to Ollama with model {model_name}: {str(e)}"
            )
        except Exception as e:
            logger.error(f"Failed to switch to model {model_name}: {e}", exc_info=True)
            QMessageBox.warning(self, "Error", f"Failed to switch model: {str(e)}")

    def _load_document(self) -> None:
        """Load document and perform PRISMA 2020 assessment."""
        doc_id_str = self.ui.doc_id_input.text().strip()

        if not doc_id_str:
            logger.debug("Load document attempted with empty document ID")
            QMessageBox.warning(self, "Input Error", "Please enter a document ID.")
            return

        try:
            doc_id = int(doc_id_str)
        except ValueError:
            logger.warning(f"Invalid document ID format: {doc_id_str}")
            QMessageBox.warning(
                self, "Input Error",
                "Invalid document ID. Please enter a number."
            )
            return

        logger.info(f"Loading document {doc_id} for PRISMA 2020 assessment")
        self._update_status(f"Loading document {doc_id}...", SECTION_COLORS['info'])
        self.ui.load_button.setEnabled(False)

        try:
            # Fetch document using canonical function
            doc = get_document_details(doc_id)

            if not doc:
                logger.warning(f"Document {doc_id} not found in database")
                QMessageBox.warning(self, "Not Found", f"Document {doc_id} not found in database.")
                self._update_status(STATUS_READY, 'gray')
                self.ui.load_button.setEnabled(True)
                return

            self.current_document = doc
            doc_title = self.current_document.get('title', 'Untitled')
            logger.info(f"Document {doc_id} loaded successfully: {doc_title[:100]}")
            self._display_document()

            if not self.prisma_agent:
                logger.error("PRISMA Agent not initialized, cannot perform assessment")
                QMessageBox.warning(
                    self, "Agent Error",
                    "PRISMA Agent not initialized. Cannot perform assessment."
                )
                self._update_status("Agent unavailable", SECTION_COLORS['error'])
                self.ui.load_button.setEnabled(True)
                return

            self._update_status("Running PRISMA 2020 assessment...", SECTION_COLORS['info'])

            if self.worker and self.worker.isRunning():
                logger.debug("Terminating previous worker thread")
                self.worker.terminate()
                self.worker.wait()

            # Create worker with semantic search enabled
            self.worker = PRISMA2020AssessmentWorker(
                self.prisma_agent,
                self.current_document,
                use_semantic_search=True  # Enable enhanced assessment
            )
            self.worker.result_ready.connect(self._on_assessment_complete)
            self.worker.error_occurred.connect(self._on_assessment_error)
            self.worker.status_update.connect(self._on_status_update)
            self.worker.finished.connect(lambda: self.ui.load_button.setEnabled(True))
            self.worker.start()

        except ConnectionError as e:
            logger.error(f"Database connection error while loading document {doc_id}: {e}", exc_info=True)
            QMessageBox.critical(self, "Database Error", f"Failed to connect to database: {str(e)}")
            self._update_status("Database connection failed", SECTION_COLORS['error'])
            self.ui.load_button.setEnabled(True)
        except Exception as e:
            logger.error(f"Unexpected error loading document {doc_id}: {e}", exc_info=True)
            QMessageBox.critical(self, "Error", f"Unexpected error loading document: {str(e)}")
            self._update_status(f"Error: {str(e)[:50]}...", SECTION_COLORS['error'])
            self.ui.load_button.setEnabled(True)

    def _display_document(self) -> None:
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

        self.ui.document_view.set_document(doc_data)

    def _on_assessment_complete(self, assessment: PRISMA2020Assessment) -> None:
        """Handle PRISMA 2020 assessment completion."""
        compliance_pct = assessment.overall_compliance_percentage
        logger.info(f"Assessment complete: {compliance_pct:.1f}% compliance, "
                   f"{assessment.total_applicable_items} items assessed")

        self.current_assessment = assessment
        self._display_assessment()

        self._update_status(
            f"✓ Assessment complete ({compliance_pct:.1f}% compliance)",
            SECTION_COLORS['success']
        )
        self.status_message.emit(f"PRISMA 2020 assessment complete - {compliance_pct:.1f}% compliance")

    def _on_assessment_error(self, error_msg: str) -> None:
        """Handle PRISMA 2020 assessment error."""
        logger.error(f"Assessment error: {error_msg}")
        QMessageBox.critical(
            self, "Assessment Error",
            f"PRISMA 2020 assessment failed: {error_msg}"
        )
        self._update_status("Assessment failed", SECTION_COLORS['error'])

    def _on_status_update(self, message: str) -> None:
        """Handle status update from worker thread."""
        logger.debug(f"Worker status: {message}")
        self._update_status(message, SECTION_COLORS['info'])

    def _display_assessment(self) -> None:
        """Display PRISMA 2020 assessment results in tabular format."""
        if not self.current_assessment:
            return

        clear_layout(self.ui.assessment_layout)

        a = self.current_assessment

        suitability_section = create_suitability_section(a, self.stylesheet_gen)
        self.ui.assessment_layout.addWidget(suitability_section, stretch=0)

        overall_section = create_overall_section(a, self.stylesheet_gen)
        self.ui.assessment_layout.addWidget(overall_section, stretch=0)

        criteria_table = create_criteria_table(a, self.stylesheet_gen)
        self.ui.assessment_layout.addWidget(criteria_table, stretch=1)

    def _update_status(self, message: str, color: str) -> None:
        """Update status label with message and color."""
        self.ui.status_label.setText(message)
        self.ui.status_label.setStyleSheet(
            self.stylesheet_gen.label_stylesheet(
                font_size_key='font_small',
                color=color
            )
        )

    def _clear_all(self) -> None:
        """Clear all fields."""
        logger.debug("Clearing all fields")

        if self.ui.doc_id_input:
            self.ui.doc_id_input.clear()

        # Clear document view widget
        if self.ui.document_view:
            self.ui.document_view.clear()

        clear_layout(self.ui.assessment_layout)

        placeholder = QLabel(ASSESSMENT_PLACEHOLDER)
        placeholder.setStyleSheet(
            self.stylesheet_gen.label_stylesheet(
                font_size_key='font_medium',
                color='gray'
            )
        )
        self.ui.assessment_layout.addWidget(placeholder)

        self._update_status(STATUS_READY, 'gray')
        self.current_document = None
        self.current_assessment = None
        self.status_message.emit("Cleared all fields")
        logger.info("All fields cleared successfully")

    # ========================================================================
    # IDocumentReceiver Interface Implementation
    # ========================================================================

    def get_receiver_id(self) -> str:
        """Get unique identifier for this receiver."""
        return "prisma2020_lab"

    def get_receiver_name(self) -> str:
        """Get display name for this receiver."""
        return "PRISMA 2020 Lab"

    def get_receiver_description(self) -> Optional[str]:
        """Get optional tooltip description for this receiver."""
        return "Assess systematic reviews against PRISMA 2020 reporting guidelines"

    def can_receive_document(self, document_data: Dict[str, Any]) -> bool:
        """
        Check if this receiver can accept the given document.

        PRISMA 2020 Lab can accept any document with an ID.

        Args:
            document_data: Document data dictionary

        Returns:
            bool: True if document has an ID
        """
        doc_id = document_data.get('id') or document_data.get('document_id')
        return doc_id is not None

    def receive_document(self, document_data: Dict[str, Any]) -> None:
        """
        Receive and load a document for PRISMA 2020 assessment.

        Args:
            document_data: Full document data dictionary
        """
        doc_id = document_data.get('id') or document_data.get('document_id')
        if doc_id:
            logger.info(f"Received document {doc_id} from context menu")
            self.ui.doc_id_input.setText(str(doc_id))
            self._load_document()

    def cleanup(self) -> None:
        """Cleanup resources."""
        logger.info("Cleaning up PRISMA 2020 Lab plugin resources")

        if self.worker and self.worker.isRunning():
            logger.debug("Terminating worker thread")
            self.worker.terminate()
            self.worker.wait()

        if self.orchestrator:
            try:
                logger.debug("Shutting down orchestrator")
                logger.info("Orchestrator cleanup complete")
            except Exception as e:
                logger.error(f"Error during orchestrator cleanup: {e}", exc_info=True)
                print(f"Warning: Error during orchestrator cleanup: {e}")

        logger.info("PRISMA 2020 Lab plugin cleanup complete")
