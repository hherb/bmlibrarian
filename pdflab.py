"""
PDF Conversion Lab Application

A PySide6 application for testing PDF to Markdown conversion using pymupdf4llm
with pymupdf-layout for enhanced layout detection and header/footer removal.

Displays PDF on the left and converted Markdown on the right.
Includes quality rating system with database persistence.
"""

import sys
import json
import logging
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QFileDialog, QTextEdit, QSplitter, QLabel, QMessageBox,
    QCheckBox, QButtonGroup, QRadioButton, QLineEdit, QFrame
)
from PySide6.QtCore import Qt
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPdfWidgets import QPdfView
from PySide6.QtGui import QFont

# IMPORTANT: pymupdf.layout MUST be imported BEFORE pymupdf4llm
# to activate layout detection features including header/footer removal
import pymupdf.layout  # noqa: F401 - activates layout features
import pymupdf4llm

from bmlibrarian.database import DatabaseManager

# Configure logging
logger = logging.getLogger('pdflab')

# Window dimensions
WINDOW_WIDTH = 1400
WINDOW_HEIGHT = 900
WINDOW_X = 100
WINDOW_Y = 100

# Splitter initial sizes
SPLITTER_LEFT_WIDTH = 700
SPLITTER_RIGHT_WIDTH = 700

# Rating values
RATING_GOOD = "good"
RATING_ACCEPTABLE = "acceptable"
RATING_FAIL = "fail"

# Default conversion strategy
DEFAULT_STRATEGY = "pymupdf4llm"

# Max comment length
MAX_COMMENT_LENGTH = 500

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

SAVE_BUTTON_STYLE = """
    QPushButton {
        background-color: #2196F3;
        color: white;
        padding: 8px 16px;
        font-size: 13px;
        border-radius: 4px;
    }
    QPushButton:hover {
        background-color: #1976D2;
    }
    QPushButton:disabled {
        background-color: #BDBDBD;
        color: #757575;
    }
"""

TITLE_STYLE = "font-size: 16px; font-weight: bold; padding: 5px;"
INFO_LABEL_STYLE = "font-weight: bold; padding: 5px;"
CHECKBOX_STYLE = "padding: 5px; font-size: 13px;"
RATING_GROUP_STYLE = "font-size: 13px; padding: 5px;"


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
        self.db_manager: Optional[DatabaseManager] = None

        # UI Components - initialized in _setup_ui, typed as concrete classes
        self.info_label: QLabel
        self.remove_headers_checkbox: QCheckBox
        self.remove_footers_checkbox: QCheckBox
        self.pdf_view: QPdfView
        self.markdown_text: QTextEdit
        self.rating_group: QButtonGroup
        self.radio_good: QRadioButton
        self.radio_acceptable: QRadioButton
        self.radio_fail: QRadioButton
        self.comment_input: QLineEdit
        self.save_button: QPushButton

        # Setup UI
        self._setup_ui()

        # Initialize database connection
        self._init_database()

    def _init_database(self) -> None:
        """Initialize database connection for storing ratings."""
        try:
            self.db_manager = DatabaseManager()
            logger.info("Database connection established")
        except Exception as e:
            logger.warning(f"Could not connect to database: {e}")
            QMessageBox.warning(
                self,
                "Database Connection",
                f"Could not connect to database. Ratings will not be saved.\n\n{e}"
            )

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

        # Bottom bar with rating controls
        rating_bar = self._create_rating_bar()
        main_layout.addWidget(rating_bar)

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

    def _create_rating_bar(self) -> QFrame:
        """
        Create rating bar with quality rating options and comment field.

        Returns:
            QFrame containing the rating controls.
        """
        frame = QFrame()
        frame.setFrameStyle(QFrame.Shape.StyledPanel | QFrame.Shadow.Raised)
        layout = QHBoxLayout(frame)

        # Rating label
        rating_label = QLabel("Quality Rating:")
        rating_label.setStyleSheet("font-weight: bold; padding: 5px;")
        layout.addWidget(rating_label)

        # Radio buttons for rating
        self.rating_group = QButtonGroup(self)

        self.radio_good = QRadioButton("Good")
        self.radio_good.setStyleSheet(RATING_GROUP_STYLE)
        self.rating_group.addButton(self.radio_good)
        layout.addWidget(self.radio_good)

        self.radio_acceptable = QRadioButton("Acceptable")
        self.radio_acceptable.setStyleSheet(RATING_GROUP_STYLE)
        self.rating_group.addButton(self.radio_acceptable)
        layout.addWidget(self.radio_acceptable)

        self.radio_fail = QRadioButton("Fail")
        self.radio_fail.setStyleSheet(RATING_GROUP_STYLE)
        self.rating_group.addButton(self.radio_fail)
        layout.addWidget(self.radio_fail)

        layout.addSpacing(20)

        # Comment field
        comment_label = QLabel("Comment:")
        comment_label.setStyleSheet("padding: 5px;")
        layout.addWidget(comment_label)

        self.comment_input = QLineEdit()
        self.comment_input.setPlaceholderText("Optional comment (max 2 lines)")
        self.comment_input.setMaxLength(MAX_COMMENT_LENGTH)
        self.comment_input.setMinimumWidth(300)
        layout.addWidget(self.comment_input)

        layout.addStretch()

        # Save button
        self.save_button = QPushButton("Save Rating")
        self.save_button.setStyleSheet(SAVE_BUTTON_STYLE)
        self.save_button.clicked.connect(self._save_rating)
        self.save_button.setEnabled(False)  # Disabled until PDF loaded and rating selected
        layout.addWidget(self.save_button)

        # Enable save button when rating selected
        self.rating_group.buttonClicked.connect(self._on_rating_changed)

        return frame

    def _on_rating_changed(self) -> None:
        """Handle rating selection change - enable save button if PDF is loaded."""
        self.save_button.setEnabled(self.current_pdf_path is not None)

    def _get_current_strategy_options(self) -> dict:
        """
        Get current conversion strategy options as a dictionary.

        Returns:
            Dictionary containing the current strategy options.
        """
        return {
            "remove_headers": self.remove_headers_checkbox.isChecked(),
            "remove_footers": self.remove_footers_checkbox.isChecked()
        }

    def _get_selected_rating(self) -> Optional[str]:
        """
        Get the currently selected rating.

        Returns:
            Rating string ('good', 'acceptable', 'fail') or None if none selected.
        """
        if self.radio_good.isChecked():
            return RATING_GOOD
        elif self.radio_acceptable.isChecked():
            return RATING_ACCEPTABLE
        elif self.radio_fail.isChecked():
            return RATING_FAIL
        return None

    def _save_rating(self) -> None:
        """Save the current rating to the database."""
        if not self.current_pdf_path:
            QMessageBox.warning(self, "No PDF", "Please load a PDF file first.")
            return

        rating = self._get_selected_rating()
        if not rating:
            QMessageBox.warning(self, "No Rating", "Please select a rating.")
            return

        if not self.db_manager:
            QMessageBox.warning(
                self,
                "No Database",
                "Database connection not available. Rating cannot be saved."
            )
            return

        # Get comment and strategy options
        comment = self.comment_input.text().strip() or None
        strategy_options = self._get_current_strategy_options()

        try:
            # Record the conversion using the database function
            with self.db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT debug.record_pdf_conversion(
                            %s, %s, %s, %s, %s
                        )
                        """,
                        (
                            self.current_pdf_path,
                            rating,
                            DEFAULT_STRATEGY,
                            json.dumps(strategy_options),
                            comment
                        )
                    )
                    result = cur.fetchone()
                    record_id = result[0] if result else None
                conn.commit()

            logger.info(
                f"Saved rating '{rating}' for {self.current_pdf_path} (id: {record_id})"
            )

            QMessageBox.information(
                self,
                "Rating Saved",
                f"Rating '{rating}' saved successfully for:\n{Path(self.current_pdf_path).name}"
            )

            # Clear the form for next rating
            self._clear_rating_form()

        except Exception as e:
            logger.error(f"Failed to save rating: {e}")
            QMessageBox.critical(
                self,
                "Save Failed",
                f"Failed to save rating:\n{e}"
            )

    def _clear_rating_form(self) -> None:
        """Clear the rating form after saving."""
        self.rating_group.setExclusive(False)
        self.radio_good.setChecked(False)
        self.radio_acceptable.setChecked(False)
        self.radio_fail.setChecked(False)
        self.rating_group.setExclusive(True)
        self.comment_input.clear()
        self.save_button.setEnabled(False)

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

            # Clear previous rating
            self._clear_rating_form()

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

            # Display rendered markdown
            self.markdown_text.setMarkdown(md_text)

        except Exception as e:
            self.markdown_text.setPlainText(f"Error converting PDF:\n{str(e)}")
            raise


def main() -> None:
    """Main entry point for the application."""
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    app = QApplication(sys.argv)

    # Set application style
    app.setStyle("Fusion")

    # Create and show main window
    window = PDFConversionLabWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == '__main__':
    main()
