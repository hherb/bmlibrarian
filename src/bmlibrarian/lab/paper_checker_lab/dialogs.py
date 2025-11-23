"""
PaperChecker Laboratory - Dialog Classes

Reusable dialog classes for the PaperChecker Laboratory.
"""

import logging
from typing import Optional

from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QVBoxLayout, QHBoxLayout,
    QLabel, QTextEdit, QPushButton, QFileDialog, QMessageBox,
    QApplication, QSizePolicy,
)
from PySide6.QtCore import Qt

from bmlibrarian.gui.qt.resources.styles.dpi_scale import get_font_scale
from bmlibrarian.gui.qt.resources.styles.stylesheet_generator import get_stylesheet_generator

from .constants import (
    WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT,
    COLOR_PRIMARY, COLOR_SUCCESS, COLOR_GREY_600,
)


logger = logging.getLogger(__name__)


class FullTextDialog(QDialog):
    """
    Dialog for displaying full untruncated text.

    Used when tree widget or card text is truncated and user wants
    to see the complete content.
    """

    def __init__(
        self,
        title: str,
        text: str,
        parent: Optional[object] = None
    ) -> None:
        """
        Initialize full text dialog.

        Args:
            title: Dialog title
            text: Full text to display
            parent: Parent widget
        """
        super().__init__(parent)
        self.setWindowTitle(title)

        self.scale = get_font_scale()
        self.styles = get_stylesheet_generator()
        self._text = text

        self.setMinimumWidth(self.scale['control_width_xlarge'])
        self.setMinimumHeight(self.scale['line_height'] * 15)

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Setup dialog user interface."""
        layout = QVBoxLayout()
        layout.setSpacing(self.scale['spacing_medium'])
        layout.setContentsMargins(
            self.scale['padding_large'],
            self.scale['padding_large'],
            self.scale['padding_large'],
            self.scale['padding_large']
        )

        # Text display area
        self._text_edit = QTextEdit()
        self._text_edit.setReadOnly(True)
        self._text_edit.setPlainText(self._text)
        self._text_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self._text_edit, stretch=1)

        # Buttons row
        button_layout = QHBoxLayout()

        # Copy button
        copy_btn = QPushButton("Copy to Clipboard")
        copy_btn.clicked.connect(self._copy_to_clipboard)
        button_layout.addWidget(copy_btn)

        button_layout.addStretch()

        # Close button
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        close_btn.setDefault(True)
        button_layout.addWidget(close_btn)

        layout.addLayout(button_layout)
        self.setLayout(layout)

    def _copy_to_clipboard(self) -> None:
        """Copy text to clipboard."""
        clipboard = QApplication.clipboard()
        clipboard.setText(self._text)

        # Brief visual feedback
        self.setWindowTitle(self.windowTitle() + " - Copied!")


class ExportPreviewDialog(QDialog):
    """
    Dialog for previewing and saving export content.

    Shows the export content (JSON or Markdown) and allows
    saving to file or copying to clipboard.
    """

    def __init__(
        self,
        title: str,
        content: str,
        file_extension: str = ".txt",
        parent: Optional[object] = None
    ) -> None:
        """
        Initialize export preview dialog.

        Args:
            title: Dialog title
            content: Export content to display
            file_extension: Default file extension for save dialog
            parent: Parent widget
        """
        super().__init__(parent)
        self.setWindowTitle(title)

        self.scale = get_font_scale()
        self.styles = get_stylesheet_generator()
        self._content = content
        self._file_extension = file_extension

        self.setMinimumWidth(int(WINDOW_MIN_WIDTH * 0.6))
        self.setMinimumHeight(int(WINDOW_MIN_HEIGHT * 0.6))

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Setup dialog user interface."""
        layout = QVBoxLayout()
        layout.setSpacing(self.scale['spacing_medium'])
        layout.setContentsMargins(
            self.scale['padding_large'],
            self.scale['padding_large'],
            self.scale['padding_large'],
            self.scale['padding_large']
        )

        # Info label
        info_label = QLabel(f"Preview ({len(self._content):,} characters)")
        info_label.setStyleSheet(f"color: {COLOR_GREY_600};")
        layout.addWidget(info_label)

        # Content display area
        self._text_edit = QTextEdit()
        self._text_edit.setReadOnly(True)
        self._text_edit.setPlainText(self._content)
        self._text_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # Use monospace font for JSON
        if self._file_extension in ('.json', '.md'):
            font = self._text_edit.font()
            font.setFamily("Courier New, Consolas, monospace")
            self._text_edit.setFont(font)

        layout.addWidget(self._text_edit, stretch=1)

        # Buttons row
        button_layout = QHBoxLayout()

        # Copy button
        copy_btn = QPushButton("Copy to Clipboard")
        copy_btn.clicked.connect(self._copy_to_clipboard)
        button_layout.addWidget(copy_btn)

        # Save button
        save_btn = QPushButton("Save to File...")
        save_btn.clicked.connect(self._save_to_file)
        save_btn.setStyleSheet(self.styles.button_stylesheet(bg_color=COLOR_PRIMARY))
        button_layout.addWidget(save_btn)

        button_layout.addStretch()

        # Close button
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        button_layout.addWidget(close_btn)

        layout.addLayout(button_layout)
        self.setLayout(layout)

    def _copy_to_clipboard(self) -> None:
        """Copy content to clipboard."""
        clipboard = QApplication.clipboard()
        clipboard.setText(self._content)

        QMessageBox.information(
            self,
            "Copied",
            "Content copied to clipboard."
        )

    def _save_to_file(self) -> None:
        """Save content to file."""
        # Determine file filter based on extension
        if self._file_extension == '.json':
            file_filter = "JSON Files (*.json);;All Files (*)"
            default_name = "paper_check_result.json"
        elif self._file_extension == '.md':
            file_filter = "Markdown Files (*.md);;All Files (*)"
            default_name = "paper_check_report.md"
        else:
            file_filter = "Text Files (*.txt);;All Files (*)"
            default_name = "paper_check_export.txt"

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Export",
            default_name,
            file_filter
        )

        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(self._content)

                QMessageBox.information(
                    self,
                    "Saved",
                    f"Export saved to:\n{file_path}"
                )
                logger.info(f"Export saved to: {file_path}")

            except Exception as e:
                logger.error(f"Failed to save export: {e}")
                QMessageBox.critical(
                    self,
                    "Save Error",
                    f"Failed to save file:\n{str(e)}"
                )


class PMIDLookupDialog(QDialog):
    """
    Dialog for looking up a document by PMID.

    Allows user to enter a PMID and fetch the document from the database.
    """

    def __init__(self, parent: Optional[object] = None) -> None:
        """
        Initialize PMID lookup dialog.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)
        self.setWindowTitle("Lookup by PMID")

        self.scale = get_font_scale()
        self.styles = get_stylesheet_generator()
        self._result = None

        self.setMinimumWidth(self.scale['control_width_large'])

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Setup dialog user interface."""
        layout = QVBoxLayout()
        layout.setSpacing(self.scale['spacing_medium'])
        layout.setContentsMargins(
            self.scale['padding_large'],
            self.scale['padding_large'],
            self.scale['padding_large'],
            self.scale['padding_large']
        )

        # Instructions
        instructions = QLabel("Enter a PubMed ID to fetch the abstract from the database:")
        instructions.setWordWrap(True)
        layout.addWidget(instructions)

        # PMID input row
        input_layout = QHBoxLayout()

        label = QLabel("PMID:")
        input_layout.addWidget(label)

        from PySide6.QtWidgets import QLineEdit
        self._pmid_input = QLineEdit()
        self._pmid_input.setPlaceholderText("e.g., 12345678")
        self._pmid_input.returnPressed.connect(self._lookup)
        input_layout.addWidget(self._pmid_input, stretch=1)

        layout.addLayout(input_layout)

        # Status label
        self._status_label = QLabel("")
        self._status_label.setWordWrap(True)
        layout.addWidget(self._status_label)

        # Result preview (initially hidden)
        self._result_group = QLabel("")
        self._result_group.setWordWrap(True)
        self._result_group.setVisible(False)
        self._result_group.setStyleSheet(f"""
            background-color: #f5f5f5;
            padding: {self.scale['padding_medium']}px;
            border-radius: {self.scale['border_radius']}px;
        """)
        layout.addWidget(self._result_group)

        # Buttons
        button_layout = QHBoxLayout()

        lookup_btn = QPushButton("Lookup")
        lookup_btn.clicked.connect(self._lookup)
        lookup_btn.setStyleSheet(self.styles.button_stylesheet(bg_color=COLOR_PRIMARY))
        button_layout.addWidget(lookup_btn)

        button_layout.addStretch()

        self._use_btn = QPushButton("Use This Abstract")
        self._use_btn.clicked.connect(self.accept)
        self._use_btn.setEnabled(False)
        self._use_btn.setStyleSheet(self.styles.button_stylesheet(bg_color=COLOR_SUCCESS))
        button_layout.addWidget(self._use_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        layout.addLayout(button_layout)
        self.setLayout(layout)

    def _lookup(self) -> None:
        """Perform PMID lookup."""
        from .utils import validate_pmid
        from .worker import DocumentFetchWorker

        pmid_str = self._pmid_input.text().strip()
        is_valid, pmid, error = validate_pmid(pmid_str)

        if not is_valid:
            self._status_label.setText(f"❌ {error}")
            self._status_label.setStyleSheet(f"color: red;")
            return

        self._status_label.setText("🔍 Looking up...")
        self._status_label.setStyleSheet(f"color: {COLOR_GREY_600};")
        self._result_group.setVisible(False)
        self._use_btn.setEnabled(False)

        # Use worker for database lookup (runs in background)
        self._worker = DocumentFetchWorker(pmid)
        self._worker.fetch_complete.connect(self._on_fetch_complete)
        self._worker.fetch_error.connect(self._on_fetch_error)
        self._worker.start()

    def _on_fetch_complete(self, document: dict) -> None:
        """Handle successful document fetch."""
        self._result = document
        self._status_label.setText("✓ Document found")
        self._status_label.setStyleSheet(f"color: green;")

        # Show preview
        title = document.get('title', 'No title')
        abstract = document.get('abstract', '')
        preview = f"<b>{title}</b><br><br>{abstract[:300]}..."

        self._result_group.setText(preview)
        self._result_group.setVisible(True)
        self._use_btn.setEnabled(True)

    def _on_fetch_error(self, error: str) -> None:
        """Handle fetch error."""
        self._status_label.setText(f"❌ {error}")
        self._status_label.setStyleSheet(f"color: red;")
        self._result_group.setVisible(False)
        self._use_btn.setEnabled(False)

    def get_result(self) -> Optional[dict]:
        """
        Get the lookup result.

        Returns:
            Document dict if found and accepted, None otherwise
        """
        return self._result


__all__ = [
    'FullTextDialog',
    'ExportPreviewDialog',
    'PMIDLookupDialog',
]
