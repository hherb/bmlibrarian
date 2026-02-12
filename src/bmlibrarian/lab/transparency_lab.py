"""
Transparency Assessment Laboratory - PySide6/Qt GUI

Interactive interface for assessing transparency and undisclosed bias risk
in biomedical research papers. Uses the TransparencyAgent for offline
LLM-based analysis.
"""

import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import Qt, Signal, QThread, QObject
from PySide6.QtGui import QFont

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Worker Thread
# ──────────────────────────────────────────────────────────────────────────────

class AssessmentWorker(QObject):
    """Worker that runs transparency assessment in a background thread."""

    finished = Signal(object)  # TransparencyAssessment or None
    error = Signal(str)
    progress = Signal(str)

    def __init__(self, agent: Any, document: Dict[str, Any]) -> None:
        """Initialize the assessment worker.

        Args:
            agent: TransparencyAgent instance.
            document: Document dictionary to assess.
        """
        super().__init__()
        self.agent = agent
        self.document = document

    def run(self) -> None:
        """Run the transparency assessment."""
        try:
            self.progress.emit("Running transparency assessment...")
            assessment = self.agent.assess_transparency(self.document)
            if assessment:
                self.progress.emit("Enriching with bulk metadata...")
                self.agent.enrich_with_metadata(assessment)
            self.finished.emit(assessment)
        except Exception as e:
            self.error.emit(str(e))


# ──────────────────────────────────────────────────────────────────────────────
# Main Window
# ──────────────────────────────────────────────────────────────────────────────

class TransparencyLabWindow(QMainWindow):
    """Main window for the Transparency Assessment Laboratory."""

    def __init__(self) -> None:
        """Initialize the laboratory window."""
        super().__init__()
        self.setWindowTitle("Transparency Assessment Laboratory - BMLibrarian")
        self.setMinimumSize(1200, 800)
        self.resize(1400, 900)

        self.agent = None
        self.worker = None
        self.thread = None

        self._init_ui()
        self._init_agent()

    def _init_ui(self) -> None:
        """Initialize the user interface."""
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(16, 16, 16, 16)

        # Header
        header = QLabel("Transparency Assessment Laboratory")
        header.setFont(QFont("", 20, QFont.Weight.Bold))
        subtitle = QLabel(
            "Detect undisclosed bias risk: funding, COI, data availability, trial registration"
        )
        main_layout.addWidget(header)
        main_layout.addWidget(subtitle)

        # Input section
        input_group = self._create_input_section()
        main_layout.addWidget(input_group)

        # Splitter: document info (left) | results (right)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left panel: document info
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        self.doc_info_widget = QTextEdit()
        self.doc_info_widget.setReadOnly(True)
        self.doc_info_widget.setPlaceholderText("Document information will appear here...")
        left_scroll.setWidget(self.doc_info_widget)
        splitter.addWidget(left_scroll)

        # Right panel: results
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        self.results_widget = QTextEdit()
        self.results_widget.setReadOnly(True)
        self.results_widget.setPlaceholderText("Assessment results will appear here...")
        right_scroll.setWidget(self.results_widget)
        splitter.addWidget(right_scroll)

        splitter.setSizes([500, 700])
        main_layout.addWidget(splitter, stretch=1)

        # Status bar
        self.status_label = QLabel("Ready")
        main_layout.addWidget(self.status_label)

    def _create_input_section(self) -> QGroupBox:
        """Create the document input section.

        Returns:
            QGroupBox containing input controls.
        """
        group = QGroupBox("Document Input")
        layout = QHBoxLayout(group)

        # Document ID input
        layout.addWidget(QLabel("Document ID:"))
        self.doc_id_input = QLineEdit()
        self.doc_id_input.setPlaceholderText("Enter document ID, DOI, or PMID")
        self.doc_id_input.returnPressed.connect(self._on_load_clicked)
        layout.addWidget(self.doc_id_input, stretch=1)

        # Load button
        self.load_btn = QPushButton("Load")
        self.load_btn.clicked.connect(self._on_load_clicked)
        layout.addWidget(self.load_btn)

        # Model selector
        layout.addWidget(QLabel("Model:"))
        self.model_combo = QComboBox()
        self.model_combo.setMinimumWidth(200)
        self._populate_models()
        layout.addWidget(self.model_combo)

        # Assess button
        self.assess_btn = QPushButton("Assess Transparency")
        self.assess_btn.setEnabled(False)
        self.assess_btn.clicked.connect(self._on_assess_clicked)
        layout.addWidget(self.assess_btn)

        return group

    def _populate_models(self) -> None:
        """Populate the model dropdown with available Ollama models."""
        self.model_combo.clear()
        self.model_combo.addItem("gpt-oss:20b")
        self.model_combo.addItem("medgemma4B_it_q8:latest")

        try:
            import ollama
            models = ollama.list()
            model_names = [m.model for m in models.models]
            self.model_combo.clear()
            for name in sorted(model_names):
                self.model_combo.addItem(name)
            # Select default
            idx = self.model_combo.findText("gpt-oss:20b")
            if idx >= 0:
                self.model_combo.setCurrentIndex(idx)
        except Exception as e:
            logger.debug(f"Could not list Ollama models: {e}")

    def _init_agent(self) -> None:
        """Initialize the TransparencyAgent."""
        try:
            from bmlibrarian.agents import TransparencyAgent
            from bmlibrarian.config import get_config

            config = get_config()
            model = config.get_model("transparency") or "gpt-oss:20b"
            host = config.get_ollama_config().get("host", "http://localhost:11434")

            self.agent = TransparencyAgent(
                model=model,
                host=host,
                temperature=0.1,
                show_model_info=False,
            )
            self.status_label.setText("Agent initialized")
        except Exception as e:
            self.status_label.setText(f"Agent init failed: {e}")
            logger.error(f"Failed to initialize TransparencyAgent: {e}")

    def _on_load_clicked(self) -> None:
        """Handle load button click — fetch document from database."""
        input_text = self.doc_id_input.text().strip()
        if not input_text:
            return

        self.status_label.setText(f"Loading document: {input_text}...")
        self.doc_info_widget.clear()
        self.results_widget.clear()
        self.assess_btn.setEnabled(False)

        try:
            from bmlibrarian.database import fetch_documents_by_ids, get_db_connection

            # Try as numeric ID first
            try:
                doc_id = int(input_text)
                docs = fetch_documents_by_ids({doc_id})
            except ValueError:
                # Try as DOI or PMID
                conn = get_db_connection()
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT id FROM public.document
                        WHERE doi = %s OR external_id = %s
                        LIMIT 1
                        """,
                        (input_text, input_text),
                    )
                    row = cur.fetchone()
                    if row:
                        docs = fetch_documents_by_ids({row[0]})
                    else:
                        docs = []

            if not docs:
                self.doc_info_widget.setPlainText(f"Document not found: {input_text}")
                self.status_label.setText("Document not found")
                return

            doc = docs[0]
            self._current_document = doc

            # Display document info
            info_parts = [
                f"**Title:** {doc.get('title', 'N/A')}",
                f"**ID:** {doc.get('id', 'N/A')}",
                f"**DOI:** {doc.get('doi', 'N/A')}",
                f"**PMID:** {doc.get('pmid', doc.get('external_id', 'N/A'))}",
                f"**Authors:** {', '.join(doc.get('authors', [])) if isinstance(doc.get('authors'), list) else doc.get('authors', 'N/A')}",
                "",
                "---",
                "",
            ]

            abstract = doc.get("abstract", "")
            full_text = doc.get("full_text", "")
            if full_text:
                info_parts.append(f"**Full text available** ({len(full_text)} characters)")
                info_parts.append("")
                # Show first 2000 chars
                info_parts.append(full_text[:2000])
                if len(full_text) > 2000:
                    info_parts.append(f"\n... ({len(full_text) - 2000} more characters)")
            elif abstract:
                info_parts.append("**Abstract only** (no full text)")
                info_parts.append("")
                info_parts.append(abstract)

            self.doc_info_widget.setPlainText("\n".join(info_parts))
            self.assess_btn.setEnabled(True)
            self.status_label.setText(f"Loaded document {doc.get('id')}")

        except Exception as e:
            self.doc_info_widget.setPlainText(f"Error loading document: {e}")
            self.status_label.setText(f"Error: {e}")
            logger.error(f"Error loading document: {e}")

    def _on_assess_clicked(self) -> None:
        """Handle assess button click — run transparency assessment."""
        if not self.agent or not hasattr(self, "_current_document"):
            return

        # Update model from dropdown
        selected_model = self.model_combo.currentText()
        if selected_model:
            self.agent.model = selected_model

        self.assess_btn.setEnabled(False)
        self.results_widget.setPlainText("Running assessment...")
        self.status_label.setText("Assessing transparency...")

        # Run in background thread
        self.thread = QThread()
        self.worker = AssessmentWorker(self.agent, self._current_document)
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self._on_assessment_complete)
        self.worker.error.connect(self._on_assessment_error)
        self.worker.progress.connect(self._on_progress)

        self.thread.start()

    def _on_assessment_complete(self, assessment: Any) -> None:
        """Handle completed assessment.

        Args:
            assessment: TransparencyAssessment object or None.
        """
        self.thread.quit()
        self.assess_btn.setEnabled(True)

        if assessment is None:
            self.results_widget.setPlainText("Assessment failed - no result returned.")
            self.status_label.setText("Assessment failed")
            return

        # Format results
        summary = self.agent.format_assessment_summary(assessment)
        self.results_widget.setPlainText(summary)
        self.status_label.setText(
            f"Assessment complete: score={assessment.transparency_score:.1f}/10, "
            f"risk={assessment.risk_level}"
        )

    def _on_assessment_error(self, error_msg: str) -> None:
        """Handle assessment error.

        Args:
            error_msg: Error message string.
        """
        self.thread.quit()
        self.assess_btn.setEnabled(True)
        self.results_widget.setPlainText(f"Error: {error_msg}")
        self.status_label.setText(f"Error: {error_msg}")

    def _on_progress(self, message: str) -> None:
        """Handle progress update.

        Args:
            message: Progress message.
        """
        self.status_label.setText(message)


# ──────────────────────────────────────────────────────────────────────────────
# Entry Point
# ──────────────────────────────────────────────────────────────────────────────

def main() -> None:
    """Launch the Transparency Assessment Laboratory."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    window = TransparencyLabWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
