"""
Dialog widgets for BMLibrarian Lite Document Interrogation.

Provides reusable dialog components:
- WrongPDFDialog: Dialog for handling incorrect PDF files
- IdentifierInputDialog: Dialog for entering DOI/PMID identifiers
- OpenAthensPromptDialog: Dialog prompting for OpenAthens authentication

Usage:
    from bmlibrarian_lite.gui.dialogs import WrongPDFDialog, IdentifierInputDialog, OpenAthensPromptDialog

    # Wrong PDF dialog
    dialog = WrongPDFDialog(pdf_path, scale, parent)
    action = dialog.get_action()

    # Identifier input dialog
    dialog = IdentifierInputDialog(parent)
    doi, pmid = dialog.get_identifiers()

    # OpenAthens prompt dialog
    dialog = OpenAthensPromptDialog(article_url, parent)
    action = dialog.get_action()
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

from bmlibrarian_lite.resources.styles.dpi_scale import scaled

# Constants for dialog dimensions
IDENTIFIER_DIALOG_MIN_WIDTH = 400  # Minimum width for identifier input dialog
WRONG_PDF_DIALOG_MIN_WIDTH = 450  # Minimum width for wrong PDF dialog
OPENATHENS_DIALOG_MIN_WIDTH = 500  # Minimum width for OpenAthens dialog
OPENATHENS_SETUP_DIALOG_MIN_WIDTH = 450  # Minimum width for setup dialog


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
        self.setMinimumWidth(scaled(IDENTIFIER_DIALOG_MIN_WIDTH))

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
        self.setMinimumWidth(scaled(WRONG_PDF_DIALOG_MIN_WIDTH))

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


class OpenAthensPromptDialog(QDialog):
    """
    Dialog prompting user to authenticate via OpenAthens for paywalled content.

    Shown when PDF discovery fails and OpenAthens institutional access is available.

    Provides options to:
    - Login via OpenAthens and retry the download
    - Skip OpenAthens and use abstract only
    - Configure OpenAthens settings
    - Cancel

    Example:
        dialog = OpenAthensPromptDialog(article_url, parent)
        action = dialog.get_action()
        if action == 'authenticate':
            # Start OpenAthens authentication
            pass
    """

    # Action constants
    ACTION_AUTHENTICATE = 'authenticate'
    ACTION_SKIP = 'skip'
    ACTION_CONFIGURE = 'configure'
    ACTION_CANCEL = None

    def __init__(
        self,
        article_url: str,
        is_configured: bool = False,
        parent: Optional[QWidget] = None,
    ) -> None:
        """
        Initialize the OpenAthens prompt dialog.

        Args:
            article_url: URL of the paywalled article
            is_configured: Whether OpenAthens is already configured
            parent: Optional parent widget
        """
        super().__init__(parent)
        self.article_url = article_url
        self.is_configured = is_configured
        self._action: Optional[str] = None

        self.setWindowTitle("Institutional Access Available")
        self.setMinimumWidth(scaled(OPENATHENS_DIALOG_MIN_WIDTH))

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the dialog UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(scaled(12))

        # Info section
        info_text = (
            "<b>This article may be available through your institution.</b><br><br>"
            "The PDF could not be downloaded from open access sources. "
            "However, you may have access through your institution via OpenAthens.<br><br>"
            f"<b>Article:</b> <a href='{self.article_url}'>{self.article_url[:60]}{'...' if len(self.article_url) > 60 else ''}</a>"
        )
        info_label = QLabel(info_text)
        info_label.setWordWrap(True)
        info_label.setTextFormat(Qt.TextFormat.RichText)
        info_label.setOpenExternalLinks(True)
        layout.addWidget(info_label)

        # Action buttons
        btn_layout = QVBoxLayout()
        btn_layout.setSpacing(scaled(8))

        if self.is_configured:
            # OpenAthens is configured - show login button
            login_btn = QPushButton("🔐 Login via OpenAthens")
            login_btn.setToolTip("Open browser to complete institutional login, then retry download")
            login_btn.setStyleSheet(f"""
                QPushButton {{
                    padding: {scaled(10)}px;
                    background-color: #4CAF50;
                    color: white;
                    font-weight: bold;
                }}
                QPushButton:hover {{ background-color: #45a049; }}
            """)
            login_btn.clicked.connect(lambda: self._set_action(self.ACTION_AUTHENTICATE))
            btn_layout.addWidget(login_btn)
        else:
            # OpenAthens not configured - show setup button
            setup_btn = QPushButton("⚙️ Configure OpenAthens")
            setup_btn.setToolTip("Set up OpenAthens institutional access")
            setup_btn.setStyleSheet(f"""
                QPushButton {{
                    padding: {scaled(10)}px;
                    background-color: #2196F3;
                    color: white;
                    font-weight: bold;
                }}
                QPushButton:hover {{ background-color: #1976D2; }}
            """)
            setup_btn.clicked.connect(lambda: self._set_action(self.ACTION_CONFIGURE))
            btn_layout.addWidget(setup_btn)

        # Skip button
        skip_btn = QPushButton("Skip - Use Abstract Only")
        skip_btn.setToolTip("Continue without the full PDF, using only the abstract")
        skip_btn.setStyleSheet(f"QPushButton {{ padding: {scaled(8)}px; }}")
        skip_btn.clicked.connect(lambda: self._set_action(self.ACTION_SKIP))
        btn_layout.addWidget(skip_btn)

        # Cancel button
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet(f"QPushButton {{ padding: {scaled(8)}px; }}")
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
            Action string ('authenticate', 'skip', 'configure') or None if cancelled
        """
        if self.exec() == QDialog.DialogCode.Accepted:
            return self._action
        return None


class OpenAthensSetupDialog(QDialog):
    """
    Dialog for configuring OpenAthens institutional access.

    Allows users to enter their institution's OpenAthens login URL.

    Example:
        dialog = OpenAthensSetupDialog(parent)
        url = dialog.get_institution_url()
        if url:
            # Save to config
            config.openathens.institution_url = url
            config.openathens.enabled = True
    """

    def __init__(
        self,
        current_url: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        """
        Initialize the OpenAthens setup dialog.

        Args:
            current_url: Current institution URL (if configured)
            parent: Optional parent widget
        """
        super().__init__(parent)
        self.current_url = current_url
        self._result_url: Optional[str] = None

        self.setWindowTitle("Configure OpenAthens")
        self.setMinimumWidth(scaled(OPENATHENS_SETUP_DIALOG_MIN_WIDTH))

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the dialog UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(scaled(12))

        # Info section
        info_label = QLabel(
            "<b>OpenAthens Institutional Access</b><br><br>"
            "Enter your institution's OpenAthens Redirector URL or domain. "
            "This is typically found on your library's website (search for "
            "'OpenAthens Link Generator').<br><br>"
            "You can enter either the full Redirector URL or just your "
            "institution's domain."
        )
        info_label.setWordWrap(True)
        info_label.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(info_label)

        # URL input
        form_layout = QFormLayout()
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://go.openathens.net/redirector/yourinstitution.edu")
        self.url_input.setText(self.current_url)
        form_layout.addRow("Redirector URL:", self.url_input)
        layout.addLayout(form_layout)

        # Example/help text
        example_label = QLabel(
            "<small><b>Examples:</b><br>"
            "• https://go.openathens.net/redirector/jcu.edu.au<br>"
            "• jcu.edu.au (domain only - will auto-convert)</small>"
        )
        example_label.setTextFormat(Qt.TextFormat.RichText)
        example_label.setStyleSheet("QLabel { color: #666; }")
        layout.addWidget(example_label)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_accept(self) -> None:
        """Validate and accept the URL or domain."""
        url = self.url_input.text().strip()

        if not url:
            # User cleared the URL - disable OpenAthens
            self._result_url = ""
            self.accept()
            return

        # Check if it's a domain (contains a dot, no slashes except protocol)
        is_domain_only = '.' in url and '/' not in url.replace('https://', '').replace('http://', '')

        if is_domain_only:
            # Accept domain-only input - it will be converted to redirector URL
            self._result_url = url
            self.accept()
            return

        # Validate full URL format
        if not url.startswith("https://"):
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self,
                "Invalid URL",
                "The URL must start with https:// for security,\n"
                "or enter just your institution's domain (e.g., jcu.edu.au)."
            )
            return

        self._result_url = url
        self.accept()

    def get_institution_url(self) -> Optional[str]:
        """
        Show dialog and get the configured URL.

        Returns:
            Institution URL string, empty string to disable, or None if cancelled
        """
        if self.exec() == QDialog.DialogCode.Accepted:
            return self._result_url
        return None
