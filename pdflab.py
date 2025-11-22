"""
PDF Conversion Lab Application

A PySide6 application for testing PDF to Markdown conversion using pymupdf4llm
with pymupdf-layout for enhanced layout detection and header/footer removal.

Displays PDF on the left and converted Markdown on the right.
"""

import sys
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QFileDialog, QTextEdit, QSplitter, QLabel, QMessageBox,
    QCheckBox
)
from PySide6.QtCore import Qt, QUrl
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPdfWidgets import QPdfView
from PySide6.QtGui import QFont

# IMPORTANT: pymupdf.layout MUST be imported BEFORE pymupdf4llm
# to activate layout detection features including header/footer removal
import pymupdf.layout  # noqa: F401 - activates layout features
import pymupdf4llm


# Window dimensions
WINDOW_WIDTH = 1400
WINDOW_HEIGHT = 900
WINDOW_X = 100
WINDOW_Y = 100

# Splitter initial sizes
SPLITTER_LEFT_WIDTH = 700
SPLITTER_RIGHT_WIDTH = 700

# Styles
BUTTON_STYLE = """
    QPushButton {
        background-color: #4CAF50;
        color: white;
        padding: 10px 20px;
        font-size: 14px;
        border-radius: 5px;
    }
    QPushButton:hover {
        background-color: #45a049;
    }
"""

TITLE_STYLE = "font-size: 16px; font-weight: bold; padding: 5px;"
INFO_LABEL_STYLE = "font-weight: bold; padding: 5px;"
CHECKBOX_STYLE = "padding: 5px; font-size: 13px;"


class PDFConversionLabWindow(QMainWindow):
    """Main window for PDF conversion lab application."""

    def __init__(self) -> None:
        """Initialize the PDF conversion lab window."""
        super().__init__()
        self.setWindowTitle("PDF Conversion Lab - pymupdf4llm")
        self.setGeometry(WINDOW_X, WINDOW_Y, WINDOW_WIDTH, WINDOW_HEIGHT)

        # Initialize components
        self.pdf_document = QPdfDocument(self)
        self.current_pdf_path: Optional[str] = None

        # UI Components (will be set in _setup_ui)
        self.info_label: Optional[QLabel] = None
        self.remove_headers_checkbox: Optional[QCheckBox] = None
        self.remove_footers_checkbox: Optional[QCheckBox] = None
        self.pdf_view: Optional[QPdfView] = None
        self.markdown_text: Optional[QTextEdit] = None

        # Setup UI
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the user interface."""
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Main layout
        main_layout = QVBoxLayout(central_widget)

        # Top bar with file picker and options
        top_bar = self._create_top_bar()
        main_layout.addLayout(top_bar)

        # Splitter for PDF view and markdown
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left side: PDF viewer
        pdf_container = self._create_pdf_viewer()
        splitter.addWidget(pdf_container)

        # Right side: Markdown display
        markdown_container = self._create_markdown_viewer()
        splitter.addWidget(markdown_container)

        # Set initial sizes (50-50 split)
        splitter.setSizes([SPLITTER_LEFT_WIDTH, SPLITTER_RIGHT_WIDTH])

        main_layout.addWidget(splitter)

    def _create_top_bar(self) -> QHBoxLayout:
        """
        Create top bar with file picker button and options.

        Returns:
            QHBoxLayout containing the top bar widgets.
        """
        layout = QHBoxLayout()

        # File picker button
        select_btn = QPushButton("Select PDF File")
        select_btn.clicked.connect(self._select_pdf)
        select_btn.setStyleSheet(BUTTON_STYLE)
        layout.addWidget(select_btn)

        # File title / info label
        self.info_label = QLabel("No file selected")
        self.info_label.setStyleSheet(INFO_LABEL_STYLE)
        layout.addWidget(self.info_label)

        layout.addStretch()

        # Remove headers checkbox
        self.remove_headers_checkbox = QCheckBox("Remove Headers")
        self.remove_headers_checkbox.setStyleSheet(CHECKBOX_STYLE)
        self.remove_headers_checkbox.stateChanged.connect(self._on_option_changed)
        layout.addWidget(self.remove_headers_checkbox)

        # Remove footers checkbox
        self.remove_footers_checkbox = QCheckBox("Remove Footers")
        self.remove_footers_checkbox.setStyleSheet(CHECKBOX_STYLE)
        self.remove_footers_checkbox.stateChanged.connect(self._on_option_changed)
        layout.addWidget(self.remove_footers_checkbox)

        return layout

    def _create_pdf_viewer(self) -> QWidget:
        """
        Create PDF viewer widget.

        Returns:
            QWidget containing the PDF viewer.
        """
        container = QWidget()
        layout = QVBoxLayout(container)

        # Title
        title = QLabel("PDF Document")
        title.setStyleSheet(TITLE_STYLE)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # PDF view
        self.pdf_view = QPdfView()
        self.pdf_view.setDocument(self.pdf_document)
        self.pdf_view.setPageMode(QPdfView.PageMode.MultiPage)
        layout.addWidget(self.pdf_view)

        return container

    def _create_markdown_viewer(self) -> QWidget:
        """
        Create markdown display widget.

        Returns:
            QWidget containing the markdown viewer.
        """
        container = QWidget()
        layout = QVBoxLayout(container)

        # Title
        title = QLabel("Converted Markdown")
        title.setStyleSheet(TITLE_STYLE)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # Text edit for markdown
        self.markdown_text = QTextEdit()
        self.markdown_text.setReadOnly(True)
        self.markdown_text.setFont(QFont("Courier", 10))
        self.markdown_text.setPlaceholderText(
            "Markdown content will appear here after selecting a PDF..."
        )
        layout.addWidget(self.markdown_text)

        return container

    def _select_pdf(self) -> None:
        """Open file dialog to select PDF."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select PDF File",
            str(Path.home()),
            "PDF Files (*.pdf)"
        )

        if file_path:
            self._load_pdf(file_path)

    def _on_option_changed(self) -> None:
        """Handle checkbox state changes - reconvert if a PDF is loaded."""
        if self.current_pdf_path:
            self._convert_to_markdown(self.current_pdf_path)

    def _load_pdf(self, file_path: str) -> None:
        """
        Load and process PDF file.

        Args:
            file_path: Path to PDF file.
        """
        try:
            # Update info label
            file_name = Path(file_path).name
            self.info_label.setText(f"Processing: {file_name}")
            QApplication.processEvents()  # Update UI

            # Load PDF for viewing
            self.pdf_document.load(file_path)
            self.current_pdf_path = file_path

            # Convert to markdown
            self._convert_to_markdown(file_path)

            # Update info label
            self.info_label.setText(f"Loaded: {file_name}")

        except Exception as e:
            QMessageBox.critical(
                self,
                "Error Loading PDF",
                f"Failed to load PDF:\n{str(e)}"
            )
            self.info_label.setText("Error loading PDF")

    def _convert_to_markdown(self, file_path: str) -> None:
        """
        Convert PDF to Markdown using pymupdf4llm with pymupdf-layout.

        Uses the layout-enhanced conversion with optional header/footer removal.
        The header/footer parameters are only available when pymupdf.layout
        is imported before pymupdf4llm.

        Args:
            file_path: Path to PDF file.
        """
        try:
            # Get checkbox states (inverted: checkbox = remove, so header=not checked)
            include_headers = not self.remove_headers_checkbox.isChecked()
            include_footers = not self.remove_footers_checkbox.isChecked()

            # Convert to markdown with layout-enhanced features
            # header/footer params: True = include, False = exclude
            md_text = pymupdf4llm.to_markdown(
                file_path,
                header=include_headers,
                footer=include_footers,
            )

            # Display markdown
            self.markdown_text.setPlainText(md_text)

        except Exception as e:
            self.markdown_text.setPlainText(f"Error converting PDF:\n{str(e)}")
            raise


def main() -> None:
    """Main entry point for the application."""
    app = QApplication(sys.argv)

    # Set application style
    app.setStyle("Fusion")

    # Create and show main window
    window = PDFConversionLabWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == '__main__':
    main()
