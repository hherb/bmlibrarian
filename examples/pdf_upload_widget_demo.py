#!/usr/bin/env python3
"""
Standalone demo application for PDFUploadWidget development and testing.

This demo provides a simple interface to test the PDF upload widget functionality:
- PDF selection and viewing
- Fast regex-based identifier extraction
- Quick database lookup
- LLM-based fallback extraction
- Document matching and selection

Usage:
    uv run python pdf_upload_widget_demo.py
    uv run python pdf_upload_widget_demo.py /path/to/file.pdf  # Load PDF directly
"""

import logging
import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QGroupBox,
    QLabel,
    QTextEdit,
)
from PySide6.QtCore import Qt

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class PDFUploadDemo(QMainWindow):
    """
    Demo application for testing PDFUploadWidget.

    Provides a simple interface to test:
    - PDF loading and viewing
    - Quick extraction (regex + database lookup)
    - LLM extraction fallback
    - Document selection and creation
    """

    def __init__(self):
        """Initialize the demo application."""
        super().__init__()

        self.setWindowTitle("PDF Upload Widget Demo - BMLibrarian")
        self.setMinimumSize(1400, 900)

        # Import widget after QApplication is created
        from bmlibrarian.gui.qt.widgets import PDFUploadWidget
        from bmlibrarian.gui.qt.resources.styles import get_font_scale

        self.scale = get_font_scale()

        # Create central widget
        central = QWidget()
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)
        s = self.scale
        layout.setContentsMargins(s['padding_large'], s['padding_large'],
                                  s['padding_large'], s['padding_large'])
        layout.setSpacing(s['spacing_large'])

        # Create PDF upload widget
        self.upload_widget = PDFUploadWidget()
        self.upload_widget.document_selected.connect(self._on_document_selected)
        self.upload_widget.document_created.connect(self._on_document_created)
        self.upload_widget.pdf_loaded.connect(self._on_pdf_loaded)
        self.upload_widget.cancelled.connect(self._on_cancelled)

        layout.addWidget(self.upload_widget, stretch=1)

        # Event log section
        log_group = QGroupBox("Event Log")
        log_layout = QVBoxLayout(log_group)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(150)
        self.log_text.setPlaceholderText("Events will appear here...")
        log_layout.addWidget(self.log_text)

        layout.addWidget(log_group)

        # Instructions
        instructions = QLabel(
            "<b>Instructions:</b><br>"
            "1. Click 'Browse...' to select a PDF file<br>"
            "2. The widget will attempt fast regex extraction first<br>"
            "3. If a quick match is found, you can accept it or search for more<br>"
            "4. Otherwise, LLM extraction will run automatically<br>"
            "5. Select a match from the tree or create a new document<br><br>"
            "<i>Check the event log below for signal emissions</i>"
        )
        instructions.setWordWrap(True)
        instructions.setStyleSheet(f"color: gray; font-size: {s['font_small']}pt;")
        layout.addWidget(instructions)

        self._log("Demo application started")

    def _log(self, message: str):
        """Add a message to the event log."""
        self.log_text.append(message)
        logger.info(message)

    def _on_document_selected(self, doc_id: int):
        """Handle document selection."""
        self._log(f"[SIGNAL] document_selected emitted: doc_id={doc_id}")

        # Get additional info from widget
        doc = self.upload_widget.get_selected_document()
        if doc:
            self._log(f"  - Title: {doc.get('title', 'Unknown')[:60]}...")
            self._log(f"  - DOI: {doc.get('doi', 'N/A')}")

        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(
            self,
            "Document Selected",
            f"You selected document ID: {doc_id}\n\n"
            f"In a real application, this would proceed to the next step "
            f"(e.g., document assessment)."
        )

    def _on_document_created(self, doc_id: int):
        """Handle document creation."""
        self._log(f"[SIGNAL] document_created emitted: doc_id={doc_id}")

        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(
            self,
            "Document Created",
            f"New document created with ID: {doc_id}"
        )

    def _on_pdf_loaded(self, path: str):
        """Handle PDF loading."""
        self._log(f"[SIGNAL] pdf_loaded emitted: {path}")

    def _on_cancelled(self):
        """Handle cancellation."""
        self._log("[SIGNAL] cancelled emitted")

        from PySide6.QtWidgets import QMessageBox
        result = QMessageBox.question(
            self,
            "Close Application?",
            "Do you want to close the demo application?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if result == QMessageBox.Yes:
            self.close()

    def load_pdf_from_arg(self, pdf_path: str):
        """Load a PDF file passed as command line argument."""
        path = Path(pdf_path)
        if path.exists():
            self._log(f"Loading PDF from argument: {pdf_path}")
            self.upload_widget.load_pdf(path)
        else:
            self._log(f"File not found: {pdf_path}")


def main():
    """Main entry point."""
    app = QApplication(sys.argv)
    app.setApplicationName("PDF Upload Widget Demo")
    app.setOrganizationName("BMLibrarian")

    # Create main window
    window = PDFUploadDemo()
    window.show()

    # Load PDF if provided as argument
    if len(sys.argv) > 1:
        window.load_pdf_from_arg(sys.argv[1])

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
