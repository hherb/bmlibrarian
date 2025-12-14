"""
Dialog widgets for BMLibrarian Lite Document Interrogation.

Provides reusable dialog components:
- WrongPDFDialog: Dialog for handling incorrect PDF files
- IdentifierInputDialog: Dialog for entering DOI/PMID identifiers

Usage:
    from bmlibrarian.lite.gui.dialogs import WrongPDFDialog, IdentifierInputDialog

    # Wrong PDF dialog
    dialog = WrongPDFDialog(pdf_path, scale, parent)
    action = dialog.get_action()

    # Identifier input dialog
    dialog = IdentifierInputDialog(parent)
    doi, pmid = dialog.get_identifiers()
"""

from pathlib import Path
from typing import Optional, Tuple

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import Qt

from bmlibrarian.gui.qt.resources.styles.dpi_scale import scaled


class IdentifierInputDialog(QDialog):
    """
    Dialog for entering DOI/PMID identifiers to fetch a PDF.

    Provides a simple form with DOI and PMID input fields.

    Example:
        dialog = IdentifierInputDialog(parent)
        doi, pmid = dialog.get_identifiers()
        if doi or pmid:
            # Proceed with PDF fetch
            pass
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """
        Initialize the identifier input dialog.

        Args:
            parent: Optional parent widget
        """
        super().__init__(parent)
        self.setWindowTitle("Fetch PDF - Enter Identifier")
        self.setMinimumWidth(scaled(400))

        self._doi: Optional[str] = None
        self._pmid: Optional[str] = None

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the dialog UI."""
        form_layout = QFormLayout(self)

        self.doi_input = QLineEdit()
        self.doi_input.setPlaceholderText("e.g., 10.1038/nature12373")
        form_layout.addRow("DOI:", self.doi_input)

        self.pmid_input = QLineEdit()
        self.pmid_input.setPlaceholderText("e.g., 12345678")
        form_layout.addRow("PMID:", self.pmid_input)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        form_layout.addRow(buttons)

    def _on_accept(self) -> None:
        """Handle accept - store values and accept dialog."""
        self._doi = self.doi_input.text().strip() or None
        self._pmid = self.pmid_input.text().strip() or None
        self.accept()

    def get_identifiers(self) -> Tuple[Optional[str], Optional[str]]:
        """
        Show dialog and get entered identifiers.

        Returns:
            Tuple of (doi, pmid), both None if dialog was cancelled
        """
        if self.exec() == QDialog.DialogCode.Accepted:
            return self._doi, self._pmid
        return None, None


class WrongPDFDialog(QDialog):
    """
    Dialog for handling incorrectly downloaded PDF files.

    Provides options to:
    - Delete the PDF and clear the view
    - Delete the PDF and try to fetch again
    - Clear the view only (keep the file)
    - Cancel (do nothing)

    Example:
        dialog = WrongPDFDialog(Path("/path/to/wrong.pdf"), scale_dict, parent)
        action = dialog.get_action()
        if action == 'delete':
            # Handle delete action
            pass
    """

    # Action constants
    ACTION_DELETE = 'delete'
    ACTION_RETRY = 'retry'
    ACTION_CLEAR_ONLY = 'clear_only'
    ACTION_CANCEL = None

    def __init__(
        self,
        pdf_path: Path,
        scale: dict,
        parent: Optional[QWidget] = None,
    ) -> None:
        """
        Initialize the wrong PDF dialog.

        Args:
            pdf_path: Path to the incorrect PDF file
            scale: Font-relative scaling dimensions from get_font_scale()
            parent: Optional parent widget
        """
        super().__init__(parent)
        self.pdf_path = pdf_path
        self.scale = scale
        self._action: Optional[str] = None

        self.setWindowTitle("Wrong PDF - Actions")
        self.setMinimumWidth(450)

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the dialog UI."""
        s = self.scale
        layout = QVBoxLayout(self)

        # Info section
        info_label = QLabel(
            f"<b>Current PDF:</b><br><code>{self.pdf_path}</code><br><br>"
            "This PDF appears to be incorrect. Choose an action below:"
        )
        info_label.setWordWrap(True)
        info_label.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(info_label)
        layout.addSpacing(s['spacing_medium'])

        # Action buttons
        btn_layout = QVBoxLayout()
        btn_layout.setSpacing(s['spacing_small'])

        # Delete and clear button
        delete_btn = QPushButton("Delete PDF and Clear View")
        delete_btn.setToolTip("Delete the PDF file from disk and clear the document view")
        delete_btn.setStyleSheet(f"""
            QPushButton {{ padding: {s['padding_small']}px; background-color: #FFCCCB; }}
            QPushButton:hover {{ background-color: #FF9999; }}
        """)
        delete_btn.clicked.connect(lambda: self._set_action(self.ACTION_DELETE))
        btn_layout.addWidget(delete_btn)

        # Delete and retry button
        retry_btn = QPushButton("Delete PDF and Try Again")
        retry_btn.setToolTip("Delete the PDF file and attempt to fetch the correct one")
        retry_btn.setStyleSheet(f"""
            QPushButton {{ padding: {s['padding_small']}px; background-color: #FFE4B5; }}
            QPushButton:hover {{ background-color: #FFD700; }}
        """)
        retry_btn.clicked.connect(lambda: self._set_action(self.ACTION_RETRY))
        btn_layout.addWidget(retry_btn)

        # Keep file but clear view
        clear_only_btn = QPushButton("Clear View Only (Keep File)")
        clear_only_btn.setToolTip("Clear the document view but keep the PDF file for manual inspection")
        clear_only_btn.setStyleSheet(f"QPushButton {{ padding: {s['padding_small']}px; }}")
        clear_only_btn.clicked.connect(lambda: self._set_action(self.ACTION_CLEAR_ONLY))
        btn_layout.addWidget(clear_only_btn)

        # Cancel button
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet(f"QPushButton {{ padding: {s['padding_small']}px; }}")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        layout.addLayout(btn_layout)

    def _set_action(self, action: str) -> None:
        """Set the selected action and accept the dialog."""
        self._action = action
        self.accept()

    def get_action(self) -> Optional[str]:
        """
        Show dialog and get the selected action.

        Returns:
            Action string ('delete', 'retry', 'clear_only') or None if cancelled
        """
        if self.exec() == QDialog.DialogCode.Accepted:
            return self._action
        return None
