"""PDF Verification Dialog for BMLibrarian.

Provides a PySide6 dialog for users to review and decide on PDF downloads
that fail automatic verification (DOI/title mismatch).
"""

import logging
import shutil
import webbrowser
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QFileDialog, QSplitter, QWidget, QSizePolicy, QMessageBox
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from .verification_prompt import VerificationPromptData, VerificationDecision

logger = logging.getLogger(__name__)


class PDFVerificationDialog(QDialog):
    """Dialog for reviewing and deciding on mismatched PDF downloads.

    Shows the PDF in a viewer alongside mismatch details, with options to:
    - Accept (ingest despite mismatch)
    - Reassign (assign to matching document if found)
    - Save As (save to custom location, then continue choosing)
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
        self.reassign_doc_id: Optional[int] = None
        self._pdf_saved = False  # Track if user already saved a copy
        self._pdf_reassigned = False  # Track if PDF was reassigned to another document

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
        self.button_panel = self._create_button_panel()
        main_layout.addWidget(self.button_panel)

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

        # Section: Alternative Document (if available)
        if self.data.alternative_document and not self.data.alternative_document.has_pdf:
            alt_section = self._create_alternative_section()
            layout.addWidget(alt_section)

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

    def _create_alternative_section(self) -> QFrame:
        """Create the alternative document section with Reassign button."""
        alt = self.data.alternative_document
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background-color: #E8F5E9;
                border: 2px solid #4CAF50;
                border-radius: 6px;
                padding: 8px;
            }
        """)

        layout = QVBoxLayout(frame)

        # Header
        header_layout = QHBoxLayout()
        icon_label = QLabel("📄")
        icon_label.setStyleSheet("font-size: 18pt; background: transparent; border: none;")
        header_layout.addWidget(icon_label)

        title_label = QLabel("<b>Matching Document Found!</b>")
        title_label.setStyleSheet("background: transparent; border: none; color: #2E7D32;")
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        # Info text
        info_text = f"""
        <p>The PDF's DOI matches a document in your database that <b>doesn't have a PDF yet</b>:</p>
        <p><b>Title:</b> {alt.title[:80]}{'...' if len(alt.title) > 80 else ''}</p>
        <p><b>DOI:</b> {alt.doi}</p>
        """
        if alt.authors:
            info_text += f"<p><b>Authors:</b> {alt.authors[:60]}{'...' if len(alt.authors) > 60 else ''}</p>"
        if alt.year:
            info_text += f"<p><b>Year:</b> {alt.year}</p>"
        info_text += f"<p><b>Document ID:</b> {alt.doc_id}</p>"

        info_label = QLabel(info_text)
        info_label.setStyleSheet("background: transparent; border: none;")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        # Reassign button (purple) - directly under the matching document info
        self.reassign_btn = QPushButton(f"📄 Assign PDF to Document {alt.doc_id}")
        self.reassign_btn.setToolTip(
            f"Assign this PDF to '{alt.title[:50]}...' instead\n"
            "The dialog will remain open for further actions."
        )
        self.reassign_btn.setStyleSheet("""
            QPushButton {
                background-color: #9C27B0;
                color: white;
                border-radius: 6px;
                padding: 10px 20px;
                font-size: 11pt;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #7B1FA2;
            }
            QPushButton:disabled {
                background-color: #CE93D8;
                color: #E1BEE7;
            }
        """)
        self.reassign_btn.clicked.connect(self._on_reassign)
        layout.addWidget(self.reassign_btn)

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
        """Create the action button panel.

        Button layout (two rows for better organization):
        Row 1: Accept, Manual Upload
        Row 2: Open in Browser (if available), Save As, Retry, Reject

        Note: Reassign button is now in the alternative document section.
        """
        frame = QFrame()
        main_layout = QVBoxLayout(frame)
        main_layout.setSpacing(self.scale.get('spacing_small', 8))

        # Row 1: Primary actions
        row1_layout = QHBoxLayout()
        row1_layout.setSpacing(self.scale.get('spacing_medium', 12))

        # Accept button (green)
        self.accept_btn = QPushButton("✓ Accept && Ingest")
        self.accept_btn.setToolTip("Accept this PDF and add it to the document record")
        self.accept_btn.setStyleSheet("""
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
        self.accept_btn.clicked.connect(self._on_accept)
        row1_layout.addWidget(self.accept_btn)

        # Manual Upload button (teal) - select a different PDF
        self.upload_btn = QPushButton("📁 Manual Upload")
        self.upload_btn.setToolTip("Select a different PDF file to ingest instead")
        self.upload_btn.setStyleSheet("""
            QPushButton {
                background-color: #009688;
                color: white;
                border-radius: 6px;
                padding: 12px 24px;
                font-size: 12pt;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #00796B;
            }
        """)
        self.upload_btn.clicked.connect(self._on_manual_upload)
        row1_layout.addWidget(self.upload_btn)

        row1_layout.addStretch()
        main_layout.addLayout(row1_layout)

        # Row 2: Secondary actions
        row2_layout = QHBoxLayout()
        row2_layout.setSpacing(self.scale.get('spacing_medium', 12))

        # Open in Browser button (cyan) - only if source URL available
        if self.data.source_url:
            self.browser_btn = QPushButton("🌐 Open in Browser")
            self.browser_btn.setToolTip(
                f"Open the source URL in your browser to manually find the correct PDF\n"
                f"URL: {self.data.source_url[:60]}..."
            )
            self.browser_btn.setStyleSheet("""
                QPushButton {
                    background-color: #00BCD4;
                    color: white;
                    border-radius: 6px;
                    padding: 12px 24px;
                    font-size: 12pt;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #0097A7;
                }
            """)
            self.browser_btn.clicked.connect(self._on_open_browser)
            row2_layout.addWidget(self.browser_btn)

        # Save As button (blue)
        self.save_btn = QPushButton("💾 Save As...")
        self.save_btn.setToolTip("Save this PDF to a custom location (then choose what to do next)")
        self.save_btn.setStyleSheet("""
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
        self.save_btn.clicked.connect(self._on_save_as)
        row2_layout.addWidget(self.save_btn)

        # Retry button (orange)
        self.retry_btn = QPushButton("🔄 Retry Search")
        self.retry_btn.setToolTip("Discard this PDF and try searching for the correct one again")
        self.retry_btn.setStyleSheet("""
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
        self.retry_btn.clicked.connect(self._on_retry)
        row2_layout.addWidget(self.retry_btn)

        # Reject button (red)
        self.reject_btn = QPushButton("✗ Reject")
        self.reject_btn.setToolTip("Discard this PDF completely")
        self.reject_btn.setStyleSheet("""
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
        self.reject_btn.clicked.connect(self._on_reject)
        row2_layout.addWidget(self.reject_btn)

        row2_layout.addStretch()
        main_layout.addLayout(row2_layout)

        return frame

    def _on_accept(self) -> None:
        """Handle Accept button click."""
        self.decision = VerificationDecision.ACCEPT
        self.accept()

    def _on_reassign(self) -> None:
        """Handle Reassign button click.

        Assigns the PDF to the alternative document but keeps the dialog open
        so the user can perform additional actions (like opening browser to
        find the correct PDF for the original document).
        """
        alt = self.data.alternative_document
        self.reassign_doc_id = alt.doc_id

        try:
            # Perform the reassignment immediately
            from bmlibrarian.database import get_db_manager
            db_manager = get_db_manager()

            # Calculate relative path for database
            from bmlibrarian.utils.pdf_manager import PDFManager
            pdf_manager = PDFManager()

            # Get the relative path (year/filename.pdf format)
            document = {
                'id': alt.doc_id,
                'pdf_filename': self.data.pdf_path.name
            }
            # We need to get the year from the alternative document
            # For now, use the filename as-is and let the database store it
            relative_path = self.data.pdf_path.name
            if pdf_manager.base_dir and self.data.pdf_path.is_relative_to(pdf_manager.base_dir):
                relative_path = str(self.data.pdf_path.relative_to(pdf_manager.base_dir))

            with db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE document SET pdf_filename = %s WHERE id = %s",
                        (relative_path, alt.doc_id)
                    )
                    conn.commit()

            logger.info(f"Reassigned PDF to document {alt.doc_id}: {relative_path}")

            # Update button to show success and disable it
            self.reassign_btn.setEnabled(False)
            self.reassign_btn.setText(f"✓ Assigned to Doc {alt.doc_id}")
            self.reassign_btn.setStyleSheet("""
                QPushButton {
                    background-color: #CE93D8;
                    color: #4A148C;
                    border-radius: 6px;
                    padding: 10px 20px;
                    font-size: 11pt;
                    font-weight: bold;
                }
            """)

            # Show success message
            QMessageBox.information(
                self,
                "PDF Reassigned",
                f"PDF has been assigned to document {alt.doc_id}:\n"
                f"{alt.title[:60]}...\n\n"
                "You can now:\n"
                "• Open the source URL in browser to find the correct PDF\n"
                "• Manually upload the correct PDF\n"
                "• Reject to close without further action"
            )

            # Mark that we've done a reassignment (for return value)
            self._pdf_reassigned = True

        except Exception as e:
            logger.error(f"Failed to reassign PDF to document {alt.doc_id}: {e}")
            QMessageBox.critical(
                self,
                "Reassignment Failed",
                f"Failed to assign PDF to document {alt.doc_id}:\n{e}"
            )

    def _on_save_as(self) -> None:
        """Handle Save As button click - save copy but continue dialog."""
        # Open file save dialog
        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save PDF As",
            str(Path.home() / "Downloads" / self.data.pdf_path.name),
            "PDF Files (*.pdf)"
        )

        if save_path:
            save_path = Path(save_path)
            try:
                shutil.copy2(self.data.pdf_path, save_path)
                self.save_path = save_path
                self._pdf_saved = True

                # Show success message
                QMessageBox.information(
                    self,
                    "PDF Saved",
                    f"PDF saved to:\n{save_path}\n\n"
                    "Now choose what to do with the original download."
                )

                # Disable Save As button (already saved)
                self.save_btn.setEnabled(False)
                self.save_btn.setText("✓ Saved")
                self.save_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #90CAF9;
                        color: #1565C0;
                        border-radius: 6px;
                        padding: 12px 24px;
                        font-size: 12pt;
                        font-weight: bold;
                    }
                """)

                # Update reject button text since we saved a copy
                self.reject_btn.setText("✗ Reject (copy saved)")

            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Save Failed",
                    f"Failed to save PDF:\n{e}"
                )

    def _on_retry(self) -> None:
        """Handle Retry button click."""
        self.decision = VerificationDecision.RETRY
        self.accept()

    def _on_reject(self) -> None:
        """Handle Reject button click."""
        self.decision = VerificationDecision.REJECT
        self.reject()

    def _on_open_browser(self) -> None:
        """Handle Open in Browser button click.

        Opens the source URL in the default browser but keeps the dialog open
        so the user can manually download and then use Manual Upload.
        """
        if self.data.source_url:
            try:
                webbrowser.open(self.data.source_url)
                logger.info(f"Opened source URL in browser: {self.data.source_url}")
            except Exception as e:
                logger.error(f"Failed to open browser: {e}")
                QMessageBox.warning(
                    self,
                    "Browser Error",
                    f"Failed to open browser:\n{e}\n\n"
                    f"URL: {self.data.source_url}"
                )

    def _on_manual_upload(self) -> None:
        """Handle Manual Upload button click.

        Opens a file dialog to select a different PDF file.
        If selected, closes the dialog with MANUAL_UPLOAD decision.
        """
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select PDF File",
            str(Path.home() / "Downloads"),
            "PDF Files (*.pdf)"
        )

        if file_path:
            upload_path = Path(file_path)
            if upload_path.exists() and upload_path.suffix.lower() == '.pdf':
                self.data.manual_upload_path = upload_path
                self.decision = VerificationDecision.MANUAL_UPLOAD
                logger.info(f"User selected manual upload: {upload_path}")
                self.accept()
            else:
                QMessageBox.warning(
                    self,
                    "Invalid File",
                    "Please select a valid PDF file."
                )
