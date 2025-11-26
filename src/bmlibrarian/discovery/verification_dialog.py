"""PDF Verification Dialog for BMLibrarian.

Provides a PySide6 dialog for users to review and decide on PDF downloads
that fail automatic verification (DOI/title mismatch).
"""

import logging
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QFileDialog, QSplitter, QWidget, QSizePolicy
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from .verification_prompt import VerificationPromptData, VerificationDecision

logger = logging.getLogger(__name__)


class PDFVerificationDialog(QDialog):
    """Dialog for reviewing and deciding on mismatched PDF downloads.

    Shows the PDF in a viewer alongside mismatch details, with options to:
    - Accept (ingest despite mismatch)
    - Save As (save to custom location without ingesting)
    - Retry (try searching again)
    - Reject (discard)
    """

    # Minimum dialog size
    MIN_WIDTH = 1200
    MIN_HEIGHT = 800

    def __init__(
        self,
        data: VerificationPromptData,
        parent: Optional[QWidget] = None
    ):
        """Initialize the verification dialog.

        Args:
            data: Verification prompt data with expected vs extracted info
            parent: Optional parent widget
        """
        super().__init__(parent)
        self.data = data
        self.decision: VerificationDecision = VerificationDecision.REJECT
        self.save_path: Optional[Path] = None

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the dialog UI components."""
        self.setWindowTitle("PDF Verification Required")
        self.setMinimumSize(self.MIN_WIDTH, self.MIN_HEIGHT)

        # Import resources here to avoid circular imports
        try:
            from bmlibrarian.gui.qt.resources import (
                get_font_scale, StylesheetGenerator
            )
            self.scale = get_font_scale()
            self.style_gen = StylesheetGenerator(self.scale)
        except ImportError:
            # Fallback if GUI resources not available
            self.scale = {'font_normal': 10, 'font_medium': 11, 'font_large': 14,
                          'spacing_small': 8, 'spacing_medium': 12, 'padding_small': 8,
                          'padding_medium': 12, 'radius_small': 4}
            self.style_gen = None

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(self.scale.get('spacing_medium', 12))

        # Warning header
        header = self._create_header()
        main_layout.addWidget(header)

        # Splitter: PDF viewer (left) | Info panel (right)
        splitter = QSplitter(Qt.Horizontal)

        # PDF viewer panel
        pdf_panel = self._create_pdf_panel()
        splitter.addWidget(pdf_panel)

        # Info panel
        info_panel = self._create_info_panel()
        splitter.addWidget(info_panel)

        # Set initial sizes (60% PDF, 40% info)
        splitter.setSizes([720, 480])

        main_layout.addWidget(splitter, 1)

        # Button panel
        button_panel = self._create_button_panel()
        main_layout.addWidget(button_panel)

    def _create_header(self) -> QFrame:
        """Create the warning header."""
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background-color: #FFF3CD;
                border: 2px solid #FFC107;
                border-radius: 6px;
                padding: 8px;
            }
        """)

        layout = QHBoxLayout(frame)

        # Warning icon
        icon_label = QLabel("⚠️")
        icon_label.setStyleSheet("font-size: 24pt; background: transparent; border: none;")
        layout.addWidget(icon_label)

        # Warning text
        text_label = QLabel(
            "<b>PDF Verification Failed</b><br>"
            "The downloaded PDF does not match the expected document. "
            "Please review and decide how to proceed."
        )
        text_label.setStyleSheet("""
            background: transparent;
            border: none;
            color: #856404;
        """)
        text_label.setWordWrap(True)
        layout.addWidget(text_label, 1)

        return frame

    def _create_pdf_panel(self) -> QFrame:
        """Create the PDF viewer panel."""
        frame = QFrame()
        frame.setFrameStyle(QFrame.StyledPanel | QFrame.Sunken)

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)

        # Try to use the existing PDF viewer
        try:
            from bmlibrarian.gui.qt.widgets.pdf_viewer import PDFViewerWidget
            self.pdf_viewer = PDFViewerWidget()
            self.pdf_viewer.load_pdf(self.data.pdf_path)
            layout.addWidget(self.pdf_viewer)
        except Exception as e:
            logger.warning(f"Could not load PDF viewer: {e}")
            # Fallback: show file info
            fallback_label = QLabel(
                f"<h3>PDF Preview Unavailable</h3>"
                f"<p>File: {self.data.pdf_path.name}</p>"
                f"<p>Size: {self.data.pdf_path.stat().st_size / 1024:.1f} KB</p>"
                f"<p><i>Open the file externally to view contents.</i></p>"
            )
            fallback_label.setAlignment(Qt.AlignCenter)
            fallback_label.setWordWrap(True)
            layout.addWidget(fallback_label)

        return frame

    def _create_info_panel(self) -> QFrame:
        """Create the information panel showing mismatch details."""
        frame = QFrame()
        frame.setFrameStyle(QFrame.StyledPanel | QFrame.Raised)

        layout = QVBoxLayout(frame)
        layout.setSpacing(self.scale.get('spacing_medium', 12))

        # Section: Expected Document
        expected_section = self._create_section(
            "Expected Document",
            [
                ("DOI", self.data.expected_doi or "N/A"),
                ("Title", self.data.expected_title or "N/A"),
                ("PMID", self.data.expected_pmid or "N/A"),
            ],
            "#E3F2FD",  # Light blue
            "#1976D2"   # Blue border
        )
        layout.addWidget(expected_section)

        # Section: Downloaded PDF
        found_section = self._create_section(
            "Downloaded PDF",
            [
                ("DOI", self.data.extracted_doi or "Not found in PDF"),
                ("Title", self.data.extracted_title or "Not found in PDF"),
                ("PMID", self.data.extracted_pmid or "Not found in PDF"),
            ],
            "#FFEBEE",  # Light red
            "#D32F2F"   # Red border
        )
        layout.addWidget(found_section)

        # Section: Mismatch Details
        mismatch_section = self._create_mismatch_section()
        layout.addWidget(mismatch_section)

        layout.addStretch()

        return frame

    def _create_section(
        self,
        title: str,
        fields: list[tuple[str, str]],
        bg_color: str,
        border_color: str
    ) -> QFrame:
        """Create an information section with labeled fields."""
        frame = QFrame()
        frame.setStyleSheet(f"""
            QFrame {{
                background-color: {bg_color};
                border: 1px solid {border_color};
                border-radius: 6px;
                padding: 8px;
            }}
        """)

        layout = QVBoxLayout(frame)
        layout.setSpacing(4)

        # Title
        title_label = QLabel(f"<b>{title}</b>")
        title_label.setStyleSheet("background: transparent; border: none;")
        layout.addWidget(title_label)

        # Fields
        for field_name, field_value in fields:
            field_layout = QHBoxLayout()

            name_label = QLabel(f"<b>{field_name}:</b>")
            name_label.setStyleSheet("background: transparent; border: none;")
            name_label.setFixedWidth(60)
            field_layout.addWidget(name_label)

            # Truncate long values
            display_value = field_value
            if len(display_value) > 100:
                display_value = display_value[:97] + "..."

            value_label = QLabel(display_value)
            value_label.setStyleSheet("background: transparent; border: none;")
            value_label.setWordWrap(True)
            value_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            field_layout.addWidget(value_label, 1)

            layout.addLayout(field_layout)

        return frame

    def _create_mismatch_section(self) -> QFrame:
        """Create the mismatch details section."""
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background-color: #FFF8E1;
                border: 1px solid #FFA000;
                border-radius: 6px;
                padding: 8px;
            }
        """)

        layout = QVBoxLayout(frame)

        title_label = QLabel("<b>Mismatch Analysis</b>")
        title_label.setStyleSheet("background: transparent; border: none;")
        layout.addWidget(title_label)

        # Build mismatch details
        details = []

        # DOI comparison
        if self.data.expected_doi and self.data.extracted_doi:
            if self.data.expected_doi.lower() != self.data.extracted_doi.lower():
                details.append("❌ <b>DOI MISMATCH</b>: The DOIs are completely different")
        elif self.data.expected_doi and not self.data.extracted_doi:
            details.append("⚠️ <b>DOI not found</b>: Could not extract DOI from PDF")

        # Title comparison
        if self.data.title_similarity is not None:
            if self.data.title_similarity < 0.5:
                details.append(
                    f"❌ <b>Title MISMATCH</b>: "
                    f"Similarity only {self.data.title_similarity:.0%}"
                )
            elif self.data.title_similarity < 0.8:
                details.append(
                    f"⚠️ <b>Title partially matches</b>: "
                    f"Similarity {self.data.title_similarity:.0%}"
                )
        elif self.data.expected_title and not self.data.extracted_title:
            details.append("⚠️ <b>Title not found</b>: Could not extract title from PDF")

        # Add any additional warnings
        if self.data.verification_warnings:
            for warning in self.data.verification_warnings:
                if "mismatch" in warning.lower():
                    details.append(f"❌ {warning}")
                else:
                    details.append(f"⚠️ {warning}")

        if not details:
            details.append("⚠️ Verification failed for unknown reason")

        detail_text = "<br>".join(details)
        detail_label = QLabel(detail_text)
        detail_label.setStyleSheet("background: transparent; border: none;")
        detail_label.setWordWrap(True)
        layout.addWidget(detail_label)

        return frame

    def _create_button_panel(self) -> QFrame:
        """Create the action button panel."""
        frame = QFrame()
        layout = QHBoxLayout(frame)
        layout.setSpacing(self.scale.get('spacing_medium', 12))

        # Accept button (green)
        accept_btn = QPushButton("✓ Accept && Ingest")
        accept_btn.setToolTip("Accept this PDF and add it to the document record")
        accept_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border-radius: 6px;
                padding: 12px 24px;
                font-size: 12pt;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #388E3C;
            }
        """)
        accept_btn.clicked.connect(self._on_accept)
        layout.addWidget(accept_btn)

        # Save As button (blue)
        save_btn = QPushButton("💾 Save As...")
        save_btn.setToolTip("Save this PDF to a custom location without ingesting")
        save_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                border-radius: 6px;
                padding: 12px 24px;
                font-size: 12pt;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
        """)
        save_btn.clicked.connect(self._on_save_as)
        layout.addWidget(save_btn)

        # Retry button (orange)
        retry_btn = QPushButton("🔄 Retry Search")
        retry_btn.setToolTip("Discard this PDF and try searching for the correct one again")
        retry_btn.setStyleSheet("""
            QPushButton {
                background-color: #FF9800;
                color: white;
                border-radius: 6px;
                padding: 12px 24px;
                font-size: 12pt;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #F57C00;
            }
        """)
        retry_btn.clicked.connect(self._on_retry)
        layout.addWidget(retry_btn)

        # Reject button (red)
        reject_btn = QPushButton("✗ Reject")
        reject_btn.setToolTip("Discard this PDF completely")
        reject_btn.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                border-radius: 6px;
                padding: 12px 24px;
                font-size: 12pt;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #D32F2F;
            }
        """)
        reject_btn.clicked.connect(self._on_reject)
        layout.addWidget(reject_btn)

        return frame

    def _on_accept(self) -> None:
        """Handle Accept button click."""
        self.decision = VerificationDecision.ACCEPT
        self.accept()

    def _on_save_as(self) -> None:
        """Handle Save As button click."""
        # Open file save dialog
        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save PDF As",
            str(Path.home() / "Downloads" / self.data.pdf_path.name),
            "PDF Files (*.pdf)"
        )

        if save_path:
            self.decision = VerificationDecision.SAVE_AS
            self.save_path = Path(save_path)
            self.accept()

    def _on_retry(self) -> None:
        """Handle Retry button click."""
        self.decision = VerificationDecision.RETRY
        self.accept()

    def _on_reject(self) -> None:
        """Handle Reject button click."""
        self.decision = VerificationDecision.REJECT
        self.reject()
