#!/usr/bin/env python3
"""
PDF Verification Review GUI for BMLibrarian.

A PySide6 GUI for reviewing PDF verification results, comparing expected vs
extracted metadata, and accepting or rejecting PDFs that don't match their
database records.

Usage:
    uv run python pdf_verification_gui.py
    uv run python pdf_verification_gui.py --year 2024
    uv run python pdf_verification_gui.py --limit 100
"""

import argparse
import logging
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QSplitter, QFrame, QScrollArea,
    QMessageBox, QProgressBar, QGroupBox, QTextEdit, QSpinBox,
    QTabWidget, QPlainTextEdit, QCheckBox
)
from PySide6.QtCore import Qt, Signal, QThread, QObject
from PySide6.QtGui import QFont

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from bmlibrarian.database import get_db_manager
from bmlibrarian.config import BMLibrarianConfig
from bmlibrarian.discovery.pdf_verifier import PDFVerifier, VerificationResult, PDFValidityResult
from bmlibrarian.gui.qt.widgets.pdf_viewer import PDFViewerWidget
from bmlibrarian.gui.qt.resources.styles import get_font_scale, StylesheetGenerator

if TYPE_CHECKING:
    import psycopg

logger = logging.getLogger(__name__)

# Constants
PUBMED_SOURCE_ID = 1
DEFAULT_BATCH_SIZE = 20
REJECTED_DIR_NAME = "rejected"


@dataclass
class DocumentRecord:
    """A document record for verification."""

    doc_id: int
    doi: Optional[str]
    pmid: Optional[str]
    title: Optional[str]
    pdf_filename: str
    pdf_path: Optional[Path]
    publication_date: Optional[str]
    full_text: Optional[str]

    # Verification results (populated after checking)
    verification: Optional[VerificationResult] = None
    # PDF validity check (populated before verification)
    pdf_validity: Optional[PDFValidityResult] = None
    # Extracted text from first page (for debugging)
    extracted_text: Optional[str] = None


def get_pdf_base_dir() -> Path:
    """Get PDF base directory from configuration."""
    config = BMLibrarianConfig()
    return Path(config.get('pdf', {}).get('base_dir', '~/knowledgebase/pdf')).expanduser()


def find_pdf_path(pdf_filename: str, base_dir: Path) -> Optional[Path]:
    """Find the actual path to a PDF file."""
    # Try as relative path from base_dir
    relative_path = base_dir / pdf_filename
    if relative_path.exists():
        return relative_path

    # Try as just filename in base_dir
    if '/' in pdf_filename:
        filename_only = Path(pdf_filename).name
        flat_path = base_dir / filename_only
        if flat_path.exists():
            return flat_path

    # Try searching in year directories
    for year_dir in base_dir.iterdir():
        if year_dir.is_dir() and year_dir.name.isdigit():
            year_path = year_dir / Path(pdf_filename).name
            if year_path.exists():
                return year_path

    return None


class DocumentLoader(QObject):
    """Worker object for loading documents in a separate thread."""

    finished = Signal(list)  # Emits list of DocumentRecord
    progress = Signal(int, int)  # current, total
    error = Signal(str)

    def __init__(
        self,
        year: Optional[int] = None,
        limit: Optional[int] = None,
        offset: int = 0,
        batch_size: int = DEFAULT_BATCH_SIZE
    ) -> None:
        super().__init__()
        self.year = year
        self.limit = limit
        self.offset = offset
        self.batch_size = batch_size
        self._cancelled = False

    def cancel(self) -> None:
        """Cancel the loading operation."""
        self._cancelled = True

    def run(self) -> None:
        """Load documents from database."""
        try:
            db_manager = get_db_manager()
            base_dir = get_pdf_base_dir()
            verifier = PDFVerifier()

            with db_manager.get_connection() as conn:
                documents = self._fetch_documents(conn, base_dir)

                # Verify each document
                verified_docs = []
                total = len(documents)

                for i, doc in enumerate(documents):
                    if self._cancelled:
                        break

                    self.progress.emit(i + 1, total)

                    if doc.pdf_path and doc.pdf_path.exists():
                        try:
                            # First check PDF validity
                            doc.pdf_validity = verifier.check_pdf_validity(doc.pdf_path)

                            # Extract text for debugging (first page only)
                            if doc.pdf_validity.is_valid:
                                doc.extracted_text = verifier.extract_text_from_pdf(
                                    doc.pdf_path, max_pages=1
                                )

                            # Only run full verification if PDF is valid
                            if doc.pdf_validity.is_valid:
                                doc.verification = verifier.verify_pdf(
                                    pdf_path=doc.pdf_path,
                                    expected_doi=doc.doi,
                                    expected_pmid=doc.pmid,
                                    expected_title=doc.title
                                )
                            else:
                                # Create a verification result indicating invalid PDF
                                doc.verification = VerificationResult(
                                    verified=False,
                                    confidence=0.0,
                                    is_valid_pdf=False,
                                    error=doc.pdf_validity.error or "Invalid PDF file",
                                    expected_doi=doc.doi,
                                    expected_pmid=doc.pmid,
                                    expected_title=doc.title,
                                )
                        except Exception as e:
                            logger.error(f"Error verifying PDF {doc.pdf_path}: {e}")

                    verified_docs.append(doc)

                self.finished.emit(verified_docs)

        except Exception as e:
            logger.exception("Error loading documents")
            self.error.emit(str(e))

    def _fetch_documents(
        self,
        conn: "psycopg.Connection",
        base_dir: Path
    ) -> List[DocumentRecord]:
        """Fetch documents from database."""
        with conn.cursor() as cur:
            query = """
                SELECT id, doi, external_id, title, pdf_filename,
                       publication_date, full_text
                FROM document
                WHERE source_id = %s
                  AND pdf_filename IS NOT NULL
                  AND pdf_filename != ''
            """
            params: List[Any] = [PUBMED_SOURCE_ID]

            if self.year:
                query += " AND EXTRACT(YEAR FROM publication_date) = %s"
                params.append(self.year)

            query += " ORDER BY id"

            actual_limit = self.limit if self.limit else self.batch_size
            query += f" LIMIT {actual_limit}"

            if self.offset:
                query += f" OFFSET {self.offset}"

            cur.execute(query, params)
            rows = cur.fetchall()

            documents = []
            for row in rows:
                doc_id, doi, external_id, title, pdf_filename, pub_date, full_text = row
                pdf_path = find_pdf_path(pdf_filename, base_dir)

                documents.append(DocumentRecord(
                    doc_id=doc_id,
                    doi=doi,
                    pmid=external_id,
                    title=title,
                    pdf_filename=pdf_filename,
                    pdf_path=pdf_path,
                    publication_date=str(pub_date) if pub_date else None,
                    full_text=full_text
                ))

            return documents


class MetadataComparisonWidget(QWidget):
    """Widget for comparing expected vs extracted metadata."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.scale = get_font_scale()
        self.style_gen = StylesheetGenerator()
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the UI."""
        s = self.scale
        layout = QVBoxLayout(self)
        layout.setContentsMargins(s['padding_small'], s['padding_small'],
                                  s['padding_small'], s['padding_small'])
        layout.setSpacing(s['spacing_medium'])

        # Document info header
        self.doc_header = QLabel("Document Information")
        self.doc_header.setStyleSheet(
            self.style_gen.label_stylesheet(font_size_key='font_large', bold=True)
        )
        layout.addWidget(self.doc_header)

        # Document ID and publication date
        info_layout = QHBoxLayout()
        self.doc_id_label = QLabel("ID: -")
        self.pub_date_label = QLabel("Published: -")
        info_layout.addWidget(self.doc_id_label)
        info_layout.addStretch()
        info_layout.addWidget(self.pub_date_label)
        layout.addLayout(info_layout)

        # PDF validity status (prominent display for invalid PDFs)
        self.pdf_validity_frame = QFrame()
        self.pdf_validity_frame.setFrameShape(QFrame.StyledPanel)
        validity_layout = QHBoxLayout(self.pdf_validity_frame)

        self.pdf_validity_label = QLabel("PDF Status: -")
        self.pdf_validity_label.setStyleSheet(
            self.style_gen.label_stylesheet(font_size_key='font_medium', bold=True)
        )
        validity_layout.addWidget(self.pdf_validity_label)

        self.pdf_validity_details = QLabel("")
        validity_layout.addWidget(self.pdf_validity_details)
        validity_layout.addStretch()

        layout.addWidget(self.pdf_validity_frame)

        # Title comparison
        title_group = QGroupBox("Title")
        title_layout = QVBoxLayout(title_group)

        self.expected_title = QTextEdit()
        self.expected_title.setReadOnly(True)
        self.expected_title.setMaximumHeight(s['control_height_medium'] * 2)
        self.expected_title.setPlaceholderText("Expected title from database")
        title_layout.addWidget(QLabel("Expected:"))
        title_layout.addWidget(self.expected_title)

        self.extracted_title = QTextEdit()
        self.extracted_title.setReadOnly(True)
        self.extracted_title.setMaximumHeight(s['control_height_medium'] * 2)
        self.extracted_title.setPlaceholderText("Extracted title from PDF")
        title_layout.addWidget(QLabel("Extracted:"))
        title_layout.addWidget(self.extracted_title)

        self.title_similarity = QLabel("Similarity: -")
        title_layout.addWidget(self.title_similarity)

        layout.addWidget(title_group)

        # DOI comparison
        doi_group = QGroupBox("DOI")
        doi_layout = QVBoxLayout(doi_group)

        doi_row = QHBoxLayout()
        doi_row.addWidget(QLabel("Expected:"))
        self.expected_doi = QLabel("-")
        self.expected_doi.setTextInteractionFlags(Qt.TextSelectableByMouse)
        doi_row.addWidget(self.expected_doi)
        doi_row.addStretch()
        doi_layout.addLayout(doi_row)

        doi_row2 = QHBoxLayout()
        doi_row2.addWidget(QLabel("Extracted:"))
        self.extracted_doi = QLabel("-")
        self.extracted_doi.setTextInteractionFlags(Qt.TextSelectableByMouse)
        doi_row2.addWidget(self.extracted_doi)
        doi_row2.addStretch()
        doi_layout.addLayout(doi_row2)

        self.doi_match = QLabel("Match: -")
        doi_layout.addWidget(self.doi_match)

        layout.addWidget(doi_group)

        # PMID comparison
        pmid_group = QGroupBox("PMID")
        pmid_layout = QVBoxLayout(pmid_group)

        pmid_row = QHBoxLayout()
        pmid_row.addWidget(QLabel("Expected:"))
        self.expected_pmid = QLabel("-")
        self.expected_pmid.setTextInteractionFlags(Qt.TextSelectableByMouse)
        pmid_row.addWidget(self.expected_pmid)
        pmid_row.addStretch()
        pmid_layout.addLayout(pmid_row)

        pmid_row2 = QHBoxLayout()
        pmid_row2.addWidget(QLabel("Extracted:"))
        self.extracted_pmid = QLabel("-")
        self.extracted_pmid.setTextInteractionFlags(Qt.TextSelectableByMouse)
        pmid_row2.addWidget(self.extracted_pmid)
        pmid_row2.addStretch()
        pmid_layout.addLayout(pmid_row2)

        self.pmid_match = QLabel("Match: -")
        pmid_layout.addWidget(self.pmid_match)

        layout.addWidget(pmid_group)

        # Verification summary
        summary_group = QGroupBox("Verification Summary")
        summary_layout = QVBoxLayout(summary_group)

        self.verification_status = QLabel("Status: -")
        self.verification_status.setStyleSheet(
            self.style_gen.label_stylesheet(font_size_key='font_medium', bold=True)
        )
        summary_layout.addWidget(self.verification_status)

        self.confidence_label = QLabel("Confidence: -")
        summary_layout.addWidget(self.confidence_label)

        self.match_type_label = QLabel("Match Type: -")
        summary_layout.addWidget(self.match_type_label)

        self.warnings_text = QTextEdit()
        self.warnings_text.setReadOnly(True)
        self.warnings_text.setMaximumHeight(s['control_height_medium'] * 2)
        self.warnings_text.setPlaceholderText("Warnings will appear here")
        summary_layout.addWidget(QLabel("Warnings:"))
        summary_layout.addWidget(self.warnings_text)

        layout.addWidget(summary_group)

        layout.addStretch()

    def update_display(self, doc: Optional[DocumentRecord]) -> None:
        """Update the display with document data."""
        if not doc:
            self._clear_display()
            return

        # Document info
        self.doc_id_label.setText(f"ID: {doc.doc_id}")
        self.pub_date_label.setText(f"Published: {doc.publication_date or '-'}")

        # PDF validity status
        pv = doc.pdf_validity
        v = doc.verification

        if pv:
            if pv.is_valid:
                if pv.has_text:
                    self.pdf_validity_label.setText("PDF Status: ✓ VALID")
                    self.pdf_validity_label.setStyleSheet("color: green; font-weight: bold;")
                    self.pdf_validity_details.setText(f"({pv.page_count} pages, text extractable)")
                else:
                    self.pdf_validity_label.setText("PDF Status: ⚠ SCANNED")
                    self.pdf_validity_label.setStyleSheet("color: orange; font-weight: bold;")
                    self.pdf_validity_details.setText(f"({pv.page_count} pages, no extractable text)")
                self.pdf_validity_frame.setStyleSheet("")
            else:
                self.pdf_validity_label.setText("PDF Status: ✗ INVALID")
                self.pdf_validity_label.setStyleSheet("color: white; font-weight: bold;")
                self.pdf_validity_details.setText(pv.error or "Unknown error")
                self.pdf_validity_frame.setStyleSheet("background-color: #f44336;")  # Red background
        elif v and not v.is_valid_pdf:
            # Validity from verification result
            self.pdf_validity_label.setText("PDF Status: ✗ INVALID")
            self.pdf_validity_label.setStyleSheet("color: white; font-weight: bold;")
            self.pdf_validity_details.setText(v.error or "Invalid PDF file")
            self.pdf_validity_frame.setStyleSheet("background-color: #f44336;")
        else:
            self.pdf_validity_label.setText("PDF Status: -")
            self.pdf_validity_label.setStyleSheet("")
            self.pdf_validity_details.setText("")
            self.pdf_validity_frame.setStyleSheet("")

        # Expected values
        self.expected_title.setText(doc.title or "-")
        self.expected_doi.setText(doc.doi or "-")
        self.expected_pmid.setText(str(doc.pmid) if doc.pmid else "-")

        # Verification results
        if v:
            # Extracted values
            self.extracted_title.setText(v.extracted_title or "-")
            self.extracted_doi.setText(v.extracted_doi or "-")
            self.extracted_pmid.setText(v.extracted_pmid or "-")

            # Title similarity
            if v.title_similarity is not None:
                sim_pct = f"{v.title_similarity:.1%}"
                color = "green" if v.title_similarity >= 0.8 else "orange" if v.title_similarity >= 0.5 else "red"
                self.title_similarity.setText(f"Similarity: {sim_pct}")
                self.title_similarity.setStyleSheet(f"color: {color};")
            else:
                self.title_similarity.setText("Similarity: N/A")
                self.title_similarity.setStyleSheet("")

            # DOI match
            if doc.doi and v.extracted_doi:
                match = doc.doi.lower() == v.extracted_doi.lower()
                self.doi_match.setText(f"Match: {'✓ YES' if match else '✗ NO'}")
                self.doi_match.setStyleSheet(f"color: {'green' if match else 'red'};")
            else:
                self.doi_match.setText("Match: N/A (missing data)")
                self.doi_match.setStyleSheet("color: gray;")

            # PMID match
            if doc.pmid and v.extracted_pmid:
                match = str(doc.pmid) == str(v.extracted_pmid)
                self.pmid_match.setText(f"Match: {'✓ YES' if match else '✗ NO'}")
                self.pmid_match.setStyleSheet(f"color: {'green' if match else 'red'};")
            else:
                self.pmid_match.setText("Match: N/A (missing data)")
                self.pmid_match.setStyleSheet("color: gray;")

            # Verification summary
            if v.verified is True:
                self.verification_status.setText("Status: ✓ VERIFIED")
                self.verification_status.setStyleSheet("color: green; font-weight: bold;")
            elif v.verified is False:
                self.verification_status.setText("Status: ✗ MISMATCH")
                self.verification_status.setStyleSheet("color: red; font-weight: bold;")
            else:
                self.verification_status.setText("Status: ? INCONCLUSIVE")
                self.verification_status.setStyleSheet("color: orange; font-weight: bold;")

            self.confidence_label.setText(
                f"Confidence: {v.confidence:.1%}" if v.confidence else "Confidence: N/A"
            )
            self.match_type_label.setText(f"Match Type: {v.match_type or 'N/A'}")

            # Warnings
            warnings = v.warnings or []
            if v.error:
                warnings = [v.error] + warnings
            self.warnings_text.setText("\n".join(warnings) if warnings else "None")
        else:
            self._clear_verification()

    def _clear_display(self) -> None:
        """Clear all display fields."""
        self.doc_id_label.setText("ID: -")
        self.pub_date_label.setText("Published: -")
        self.pdf_validity_label.setText("PDF Status: -")
        self.pdf_validity_label.setStyleSheet("")
        self.pdf_validity_details.setText("")
        self.pdf_validity_frame.setStyleSheet("")
        self.expected_title.clear()
        self.expected_doi.setText("-")
        self.expected_pmid.setText("-")
        self._clear_verification()

    def _clear_verification(self) -> None:
        """Clear verification fields."""
        self.extracted_title.clear()
        self.extracted_doi.setText("-")
        self.extracted_pmid.setText("-")
        self.title_similarity.setText("Similarity: -")
        self.title_similarity.setStyleSheet("")
        self.doi_match.setText("Match: -")
        self.doi_match.setStyleSheet("")
        self.pmid_match.setText("Match: -")
        self.pmid_match.setStyleSheet("")
        self.verification_status.setText("Status: -")
        self.verification_status.setStyleSheet("")
        self.confidence_label.setText("Confidence: -")
        self.match_type_label.setText("Match Type: -")
        self.warnings_text.clear()


class PDFVerificationGUI(QMainWindow):
    """Main window for PDF verification review."""

    def __init__(
        self,
        year: Optional[int] = None,
        limit: Optional[int] = None
    ) -> None:
        super().__init__()

        self.year = year
        self.limit = limit
        self.batch_size = DEFAULT_BATCH_SIZE
        self.current_offset = 0

        # All loaded documents (unfiltered)
        self._all_documents: List[DocumentRecord] = []
        # Currently displayed documents (filtered)
        self.documents: List[DocumentRecord] = []
        self.current_index = 0

        self.scale = get_font_scale()
        self.style_gen = StylesheetGenerator()
        self.base_dir = get_pdf_base_dir()

        self._loader_thread: Optional[QThread] = None
        self._loader: Optional[DocumentLoader] = None

        self._setup_ui()
        self._load_documents()

    def _setup_ui(self) -> None:
        """Set up the main UI."""
        self.setWindowTitle("PDF Verification Review - BMLibrarian")
        self.setMinimumSize(1400, 800)

        s = self.scale

        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(s['padding_medium'], s['padding_medium'],
                                       s['padding_medium'], s['padding_medium'])
        main_layout.setSpacing(s['spacing_medium'])

        # Header with navigation
        header_layout = QHBoxLayout()

        title_label = QLabel("PDF Verification Review")
        title_label.setStyleSheet(
            self.style_gen.label_stylesheet(font_size_key='font_xlarge', bold=True)
        )
        header_layout.addWidget(title_label)

        header_layout.addStretch()

        # Navigation controls
        self.prev_btn = QPushButton("◀ Previous")
        self.prev_btn.clicked.connect(self._on_previous)
        self.prev_btn.setEnabled(False)
        header_layout.addWidget(self.prev_btn)

        self.position_label = QLabel("0 / 0")
        self.position_label.setMinimumWidth(s['control_height_medium'] * 2)
        self.position_label.setAlignment(Qt.AlignCenter)
        header_layout.addWidget(self.position_label)

        self.next_btn = QPushButton("Next ▶")
        self.next_btn.clicked.connect(self._on_next)
        self.next_btn.setEnabled(False)
        header_layout.addWidget(self.next_btn)

        header_layout.addSpacing(s['spacing_large'])

        # Filter checkbox - show only failed verifications
        self.show_failed_only = QCheckBox("Show Failed Only")
        self.show_failed_only.setChecked(True)  # Default to showing only failures
        self.show_failed_only.stateChanged.connect(self._on_filter_changed)
        header_layout.addWidget(self.show_failed_only)

        header_layout.addSpacing(s['spacing_medium'])

        self.load_more_btn = QPushButton("Load More")
        self.load_more_btn.clicked.connect(self._on_load_more)
        header_layout.addWidget(self.load_more_btn)

        main_layout.addLayout(header_layout)

        # Progress bar (hidden by default)
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar)

        # Splitter with PDF viewer and metadata comparison
        splitter = QSplitter(Qt.Horizontal)

        # Left side: Tabbed interface for PDF view and extracted text
        left_frame = QFrame()
        left_frame.setFrameShape(QFrame.StyledPanel)
        left_layout = QVBoxLayout(left_frame)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self.left_tabs = QTabWidget()

        # Tab 1: PDF Viewer
        pdf_tab = QWidget()
        pdf_tab_layout = QVBoxLayout(pdf_tab)
        pdf_tab_layout.setContentsMargins(0, 0, 0, 0)
        self.pdf_viewer = PDFViewerWidget()
        pdf_tab_layout.addWidget(self.pdf_viewer)
        self.left_tabs.addTab(pdf_tab, "PDF View")

        # Tab 2: Extracted Text
        text_tab = QWidget()
        text_tab_layout = QVBoxLayout(text_tab)
        text_tab_layout.setContentsMargins(s['padding_small'], s['padding_small'],
                                           s['padding_small'], s['padding_small'])

        # Header with expected title for reference
        text_header = QLabel("Expected Title (for reference):")
        text_header.setStyleSheet(
            self.style_gen.label_stylesheet(font_size_key='font_small', bold=True)
        )
        text_tab_layout.addWidget(text_header)

        self.expected_title_display = QPlainTextEdit()
        self.expected_title_display.setReadOnly(True)
        self.expected_title_display.setMaximumHeight(s['control_height_large'])
        self.expected_title_display.setStyleSheet(
            "background-color: #fff3cd; border: 1px solid #ffc107;"
        )
        text_tab_layout.addWidget(self.expected_title_display)

        text_label = QLabel("Extracted Text (first page):")
        text_label.setStyleSheet(
            self.style_gen.label_stylesheet(font_size_key='font_small', bold=True)
        )
        text_tab_layout.addWidget(text_label)

        self.extracted_text_view = QPlainTextEdit()
        self.extracted_text_view.setReadOnly(True)
        self.extracted_text_view.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        text_tab_layout.addWidget(self.extracted_text_view)

        self.left_tabs.addTab(text_tab, "Extracted Text")

        left_layout.addWidget(self.left_tabs)
        splitter.addWidget(left_frame)

        # Right side: Metadata comparison and actions
        right_frame = QFrame()
        right_frame.setFrameShape(QFrame.StyledPanel)
        right_layout = QVBoxLayout(right_frame)
        right_layout.setContentsMargins(s['padding_small'], s['padding_small'],
                                        s['padding_small'], s['padding_small'])

        # Scrollable metadata comparison
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.metadata_widget = MetadataComparisonWidget()
        scroll.setWidget(self.metadata_widget)

        right_layout.addWidget(scroll)

        # Action buttons
        action_layout = QHBoxLayout()
        action_layout.setSpacing(s['spacing_large'])

        self.accept_btn = QPushButton("✓ Accept")
        self.accept_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-weight: bold;
                padding: 10px 20px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)
        self.accept_btn.clicked.connect(self._on_accept)
        self.accept_btn.setEnabled(False)
        action_layout.addWidget(self.accept_btn)

        self.reject_btn = QPushButton("✗ Reject")
        self.reject_btn.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                font-weight: bold;
                padding: 10px 20px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #da190b;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)
        self.reject_btn.clicked.connect(self._on_reject)
        self.reject_btn.setEnabled(False)
        action_layout.addWidget(self.reject_btn)

        right_layout.addLayout(action_layout)

        splitter.addWidget(right_frame)

        # Set initial splitter sizes (60% PDF, 40% metadata)
        splitter.setSizes([840, 560])

        main_layout.addWidget(splitter)

        # Status bar
        self.statusBar().showMessage("Ready")

    def _load_documents(self) -> None:
        """Load documents from database."""
        # Clean up previous loader
        if self._loader_thread and self._loader_thread.isRunning():
            self._loader.cancel()
            self._loader_thread.quit()
            self._loader_thread.wait()

        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.statusBar().showMessage("Loading documents...")

        # Create loader
        self._loader = DocumentLoader(
            year=self.year,
            limit=self.limit,
            offset=self.current_offset,
            batch_size=self.batch_size
        )

        # Create thread
        self._loader_thread = QThread()
        self._loader.moveToThread(self._loader_thread)

        # Connect signals
        self._loader_thread.started.connect(self._loader.run)
        self._loader.finished.connect(self._on_documents_loaded)
        self._loader.progress.connect(self._on_load_progress)
        self._loader.error.connect(self._on_load_error)
        self._loader.finished.connect(self._loader_thread.quit)

        # Start
        self._loader_thread.start()

    def _on_documents_loaded(self, documents: List[DocumentRecord]) -> None:
        """Handle loaded documents."""
        self._all_documents.extend(documents)
        self.progress_bar.setVisible(False)

        if not self._all_documents:
            self.statusBar().showMessage("No documents found")
            QMessageBox.information(
                self, "No Documents",
                "No PubMed documents with PDFs found matching the criteria."
            )
            return

        self.current_offset += len(documents)
        self._apply_filter()
        self._update_display()

    def _apply_filter(self) -> None:
        """Apply the current filter to documents."""
        if self.show_failed_only.isChecked():
            # Show only documents where verification failed or has low confidence
            self.documents = [
                doc for doc in self._all_documents
                if self._is_failed_verification(doc)
            ]
        else:
            self.documents = list(self._all_documents)

        # Update status bar with counts
        failed_count = sum(1 for d in self._all_documents if self._is_failed_verification(d))
        self.statusBar().showMessage(
            f"Showing {len(self.documents)} of {len(self._all_documents)} documents "
            f"({failed_count} failed verification)"
        )

    def _is_failed_verification(self, doc: DocumentRecord) -> bool:
        """Check if a document's verification failed or needs review."""
        v = doc.verification
        if v is None:
            return True  # No verification result
        if not v.is_valid_pdf:
            return True  # Invalid PDF
        if not v.verified:
            return True  # Verification failed
        if v.confidence < 0.80:
            return True  # Low confidence
        return False

    def _on_filter_changed(self, state: int) -> None:
        """Handle filter checkbox state change."""
        self.current_index = 0
        self._apply_filter()
        self._update_display()

    def _on_load_progress(self, current: int, total: int) -> None:
        """Update progress bar."""
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        self.statusBar().showMessage(f"Verifying document {current}/{total}...")

    def _on_load_error(self, error: str) -> None:
        """Handle load error."""
        self.progress_bar.setVisible(False)
        self.statusBar().showMessage(f"Error: {error}")
        QMessageBox.critical(self, "Error", f"Failed to load documents:\n{error}")

    def _on_load_more(self) -> None:
        """Load more documents."""
        self._load_documents()

    def _update_display(self) -> None:
        """Update the display with current document."""
        has_docs = len(self.documents) > 0
        has_current = has_docs and 0 <= self.current_index < len(self.documents)

        # Update navigation
        self.prev_btn.setEnabled(self.current_index > 0)
        self.next_btn.setEnabled(self.current_index < len(self.documents) - 1)
        self.accept_btn.setEnabled(has_current)
        self.reject_btn.setEnabled(has_current)

        self.position_label.setText(
            f"{self.current_index + 1} / {len(self.documents)}" if has_docs else "0 / 0"
        )

        if has_current:
            doc = self.documents[self.current_index]

            # Update PDF viewer
            if doc.pdf_path and doc.pdf_path.exists():
                self.pdf_viewer.load_pdf(doc.pdf_path)
            else:
                self.pdf_viewer.clear()

            # Update extracted text tab
            self.expected_title_display.setPlainText(doc.title or "(No title)")
            if doc.extracted_text:
                self.extracted_text_view.setPlainText(doc.extracted_text)
            else:
                self.extracted_text_view.setPlainText(
                    "(No text extracted - PDF may be scanned or invalid)"
                )

            # Update metadata comparison
            self.metadata_widget.update_display(doc)
        else:
            self.pdf_viewer.clear()
            self.expected_title_display.clear()
            self.extracted_text_view.clear()
            self.metadata_widget.update_display(None)

    def _on_previous(self) -> None:
        """Go to previous document."""
        if self.current_index > 0:
            self.current_index -= 1
            self._update_display()

    def _on_next(self) -> None:
        """Go to next document."""
        if self.current_index < len(self.documents) - 1:
            self.current_index += 1
            self._update_display()

    def _on_accept(self) -> None:
        """Accept current document and move to next."""
        if not self.documents:
            return

        doc = self.documents[self.current_index]
        self.statusBar().showMessage(f"Accepted document {doc.doc_id}")

        # Move to next
        if self.current_index < len(self.documents) - 1:
            self.current_index += 1
        self._update_display()

    def _on_reject(self) -> None:
        """Reject current document - move PDF and update database."""
        if not self.documents:
            return

        doc = self.documents[self.current_index]

        # Confirm rejection
        result = QMessageBox.question(
            self,
            "Confirm Rejection",
            f"Reject document {doc.doc_id}?\n\n"
            f"This will:\n"
            f"• Move PDF to {REJECTED_DIR_NAME}/ directory\n"
            f"• Clear pdf_filename in database\n"
            f"• Delete full_text if present\n"
            f"• Delete associated chunks in semantic.chunks\n\n"
            f"Continue?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if result != QMessageBox.Yes:
            return

        try:
            self._perform_rejection(doc)
            self.statusBar().showMessage(f"Rejected document {doc.doc_id}")

            # Remove from list and update display
            self.documents.pop(self.current_index)
            if self.current_index >= len(self.documents) and self.current_index > 0:
                self.current_index -= 1
            self._update_display()

        except Exception as e:
            logger.exception(f"Error rejecting document {doc.doc_id}")
            QMessageBox.critical(
                self, "Error",
                f"Failed to reject document:\n{str(e)}"
            )

    def _perform_rejection(self, doc: DocumentRecord) -> None:
        """Perform the actual rejection - move PDF and update database."""
        # 1. Move PDF to rejected directory
        if doc.pdf_path and doc.pdf_path.exists():
            rejected_dir = self.base_dir / REJECTED_DIR_NAME
            rejected_dir.mkdir(exist_ok=True)

            # Preserve year subdirectory structure
            if doc.pdf_filename and '/' in doc.pdf_filename:
                year_part = doc.pdf_filename.split('/')[0]
                if year_part.isdigit():
                    rejected_subdir = rejected_dir / year_part
                    rejected_subdir.mkdir(exist_ok=True)
                    dest = rejected_subdir / doc.pdf_path.name
                else:
                    dest = rejected_dir / doc.pdf_path.name
            else:
                dest = rejected_dir / doc.pdf_path.name

            shutil.move(str(doc.pdf_path), str(dest))
            logger.info(f"Moved PDF to {dest}")

        # 2. Update database
        db_manager = get_db_manager()
        with db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                # Clear pdf_filename and full_text
                cur.execute("""
                    UPDATE document
                    SET pdf_filename = NULL,
                        full_text = NULL
                    WHERE id = %s
                """, (doc.doc_id,))

                # Delete chunks from semantic.chunks
                cur.execute("""
                    DELETE FROM semantic.chunks
                    WHERE document_id = %s
                """, (doc.doc_id,))
                deleted_chunks = cur.rowcount

                conn.commit()

        logger.info(
            f"Updated database for doc {doc.doc_id}: "
            f"cleared pdf_filename/full_text, deleted {deleted_chunks} chunks"
        )

    def closeEvent(self, event) -> None:
        """Handle window close."""
        # Clean up loader thread
        if self._loader_thread and self._loader_thread.isRunning():
            self._loader.cancel()
            self._loader_thread.quit()
            self._loader_thread.wait()
        event.accept()


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="PDF Verification Review GUI for BMLibrarian"
    )
    parser.add_argument(
        '--year',
        type=int,
        help='Filter by publication year'
    )
    parser.add_argument(
        '--limit',
        type=int,
        help='Maximum number of documents to load'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug logging'
    )

    args = parser.parse_args()

    # Setup logging
    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    # Create application
    app = QApplication(sys.argv)
    app.setApplicationName("PDF Verification Review")
    app.setOrganizationName("BMLibrarian")

    # Create and show main window
    window = PDFVerificationGUI(year=args.year, limit=args.limit)
    window.show()

    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
