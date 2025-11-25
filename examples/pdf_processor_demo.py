"""
PDF Processor Demo Application

A PySide6 application for testing biomedical publication segmentation.
Displays PDF on the left and extracted sections on the right.
"""

import sys
from pathlib import Path
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QFileDialog, QTextEdit, QSplitter, QLabel, QMessageBox
)
from PySide6.QtCore import Qt, QUrl
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPdfWidgets import QPdfView
from PySide6.QtGui import QFont

from bmlibrarian.pdf_processor import PDFExtractor, SectionSegmenter


class PDFProcessorDemoWindow(QMainWindow):
    """Main window for PDF processor demo application."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("PDF Processor Demo - Biomedical Publication Segmenter")
        self.setGeometry(100, 100, 1400, 900)

        # Initialize components
        self.pdf_document = QPdfDocument(self)
        self.current_pdf_path = None

        # Setup UI
        self._setup_ui()

    def _setup_ui(self):
        """Setup the user interface."""
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Main layout
        main_layout = QVBoxLayout(central_widget)

        # Top bar with file picker
        top_bar = self._create_top_bar()
        main_layout.addLayout(top_bar)

        # Splitter for PDF view and sections
        splitter = QSplitter(Qt.Horizontal)

        # Left side: PDF viewer
        pdf_container = self._create_pdf_viewer()
        splitter.addWidget(pdf_container)

        # Right side: Sections display
        sections_container = self._create_sections_viewer()
        splitter.addWidget(sections_container)

        # Set initial sizes (50-50 split)
        splitter.setSizes([700, 700])

        main_layout.addWidget(splitter)

    def _create_top_bar(self) -> QHBoxLayout:
        """Create top bar with file picker button."""
        layout = QHBoxLayout()

        # Info label
        self.info_label = QLabel("Select a PDF file to begin")
        self.info_label.setStyleSheet("font-weight: bold; padding: 5px;")
        layout.addWidget(self.info_label)

        layout.addStretch()

        # File picker button
        select_btn = QPushButton("Select PDF File")
        select_btn.clicked.connect(self._select_pdf)
        select_btn.setStyleSheet("""
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
        """)
        layout.addWidget(select_btn)

        return layout

    def _create_pdf_viewer(self) -> QWidget:
        """Create PDF viewer widget."""
        container = QWidget()
        layout = QVBoxLayout(container)

        # Title
        title = QLabel("PDF Document")
        title.setStyleSheet("font-size: 16px; font-weight: bold; padding: 5px;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # PDF view
        self.pdf_view = QPdfView()
        self.pdf_view.setDocument(self.pdf_document)
        self.pdf_view.setPageMode(QPdfView.PageMode.MultiPage)
        layout.addWidget(self.pdf_view)

        return container

    def _create_sections_viewer(self) -> QWidget:
        """Create sections display widget."""
        container = QWidget()
        layout = QVBoxLayout(container)

        # Title
        title = QLabel("Extracted Sections")
        title.setStyleSheet("font-size: 16px; font-weight: bold; padding: 5px;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # Text edit for sections
        self.sections_text = QTextEdit()
        self.sections_text.setReadOnly(True)
        self.sections_text.setFont(QFont("Courier", 10))
        self.sections_text.setPlaceholderText("Section content will appear here...")
        layout.addWidget(self.sections_text)

        return container

    def _select_pdf(self):
        """Open file dialog to select PDF."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select PDF File",
            str(Path.home()),
            "PDF Files (*.pdf)"
        )

        if file_path:
            self._load_pdf(file_path)

    def _load_pdf(self, file_path: str):
        """
        Load and process PDF file.

        Args:
            file_path: Path to PDF file
        """
        try:
            # Update info label
            self.info_label.setText(f"Processing: {Path(file_path).name}")
            QApplication.processEvents()  # Update UI

            # Load PDF for viewing
            self.pdf_document.load(file_path)
            self.current_pdf_path = file_path

            # Process PDF with our library
            self._process_pdf(file_path)

            # Update info label
            self.info_label.setText(f"Loaded: {Path(file_path).name}")

        except Exception as e:
            QMessageBox.critical(
                self,
                "Error Loading PDF",
                f"Failed to load PDF:\n{str(e)}"
            )
            self.info_label.setText("Error loading PDF")

    def _process_pdf(self, file_path: str):
        """
        Process PDF and extract sections.

        Args:
            file_path: Path to PDF file
        """
        try:
            # Extract text blocks with layout info
            with PDFExtractor(file_path) as extractor:
                blocks = extractor.extract_text_blocks()
                metadata = extractor.extract_metadata()
                metadata['file_path'] = file_path

            # Segment into sections
            segmenter = SectionSegmenter()
            document = segmenter.segment_document(blocks, metadata)

            # Display sections
            self._display_sections(document)

        except Exception as e:
            self.sections_text.setPlainText(f"Error processing PDF:\n{str(e)}")
            raise

    def _display_sections(self, document):
        """
        Display sections in the text area.

        Args:
            document: Document object with sections
        """
        output_lines = []

        # Add title if available
        if document.title:
            output_lines.append(f"# {document.title}\n")
            output_lines.append("=" * 80)
            output_lines.append("")

        # Add sections with double horizontal line separators
        for i, section in enumerate(document.sections):
            if i > 0:
                output_lines.append("")

            # Double horizontal line with section name
            output_lines.append("=" * 80)
            output_lines.append(f" {section.title.upper()} ".center(80, "="))
            output_lines.append("=" * 80)
            output_lines.append("")

            # Section content
            output_lines.append(section.content)

            # Add metadata
            output_lines.append("")
            output_lines.append(f"_Type: {section.section_type.value} | "
                              f"Pages: {section.page_start + 1}-{section.page_end + 1} | "
                              f"Confidence: {section.confidence:.1%}_")

        # Summary at the end
        output_lines.append("")
        output_lines.append("")
        output_lines.append("=" * 80)
        output_lines.append(" DOCUMENT SUMMARY ".center(80, "="))
        output_lines.append("=" * 80)
        output_lines.append(f"Total Sections: {len(document.sections)}")
        output_lines.append(f"Total Pages: {document.metadata.get('num_pages', 'Unknown')}")

        section_types = [s.section_type.value for s in document.sections]
        output_lines.append(f"Section Types: {', '.join(section_types)}")

        # Set text
        self.sections_text.setPlainText('\n'.join(output_lines))


def main():
    """Main entry point for the application."""
    app = QApplication(sys.argv)

    # Set application style
    app.setStyle("Fusion")

    # Create and show main window
    window = PDFProcessorDemoWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == '__main__':
    main()
