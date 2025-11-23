"""
Document Creation Dialog for BMLibrarian Qt GUI.

Provides a dialog for creating new document records in the database
with pre-filled metadata extracted from PDFs.

This dialog is typically launched from PDFUploadWidget when no matching
document is found in the database.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QLineEdit,
    QTextEdit,
    QComboBox,
    QPushButton,
    QLabel,
    QGroupBox,
    QMessageBox,
    QDialogButtonBox,
    QFrame,
)
from PySide6.QtCore import Qt

from ..resources.styles import get_font_scale, StylesheetGenerator
from ..resources.styles.theme_colors import ThemeColors
from .validators import (
    validate_doi,
    validate_pmid,
    validate_year,
    validate_title,
    DebouncedValidator,
    VALIDATION_DEBOUNCE_MS,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Validation Constants
# =============================================================================
MAX_TITLE_LENGTH = 1000
MAX_ABSTRACT_LENGTH = 50000
MAX_AUTHORS_LENGTH = 5000


class DocumentCreateDialog(QDialog):
    """
    Dialog for creating a new document record in the database.

    Pre-fills fields with extracted metadata and allows user editing
    before saving to the database.

    Attributes:
        document_id: The ID of the created document (set after successful save)
    """

    def __init__(
        self,
        parent=None,
        metadata: Optional[Dict[str, Any]] = None,
        pdf_path: Optional[Path] = None,
    ):
        """
        Initialize the document creation dialog.

        Args:
            parent: Parent widget
            metadata: Pre-filled metadata dict with keys:
                - title: Document title
                - authors: List of author names or comma-separated string
                - doi: Digital Object Identifier
                - pmid: PubMed ID
                - year: Publication year
                - abstract: Document abstract
                - journal: Journal/publication name
            pdf_path: Path to the associated PDF file
        """
        super().__init__(parent)

        self.scale = get_font_scale()
        self.style_gen = StylesheetGenerator()
        self.metadata = metadata or {}
        self.pdf_path = pdf_path
        self.document_id: Optional[int] = None

        # Create debounced validator for improved UX with long text input
        self._debounced_validator = DebouncedValidator(
            callback=self._validate_form,
            delay_ms=VALIDATION_DEBOUNCE_MS
        )

        self._setup_ui()
        self._populate_fields()

    def _setup_ui(self):
        """Set up the dialog UI."""
        s = self.scale

        self.setWindowTitle("Create New Document")
        self.setMinimumWidth(s['control_height_large'] * 15)
        self.setMinimumHeight(s['control_height_large'] * 20)

        layout = QVBoxLayout(self)
        layout.setSpacing(s['spacing_medium'])

        # Header
        header = QLabel("Create New Document Record")
        header.setStyleSheet(
            self.style_gen.label_stylesheet(
                font_size_key='font_large',
                bold=True
            )
        )
        layout.addWidget(header)

        # Instructions
        instructions = QLabel(
            "Review and edit the extracted metadata below. "
            "Required fields are marked with *."
        )
        instructions.setWordWrap(True)
        instructions.setStyleSheet(
            self.style_gen.label_stylesheet(
                font_size_key='font_small',
                color=ThemeColors.TEXT_MUTED
            )
        )
        layout.addWidget(instructions)

        # Required fields group
        required_group = QGroupBox("Required Information")
        required_layout = QFormLayout(required_group)
        required_layout.setSpacing(s['spacing_small'])

        # Title (required)
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("Document title (required)")
        self.title_edit.setMaxLength(MAX_TITLE_LENGTH)
        self.title_edit.textChanged.connect(self._debounced_validator.trigger)
        required_layout.addRow("Title *:", self.title_edit)

        # External ID (required - will be auto-generated if not provided)
        self.external_id_edit = QLineEdit()
        self.external_id_edit.setPlaceholderText(
            "Unique identifier (auto-generated if empty)"
        )
        required_layout.addRow("External ID *:", self.external_id_edit)

        layout.addWidget(required_group)

        # Optional identifiers group
        identifiers_group = QGroupBox("Identifiers")
        identifiers_layout = QFormLayout(identifiers_group)
        identifiers_layout.setSpacing(s['spacing_small'])

        # DOI
        self.doi_edit = QLineEdit()
        self.doi_edit.setPlaceholderText("e.g., 10.1234/example")
        self.doi_edit.textChanged.connect(self._on_doi_changed)
        identifiers_layout.addRow("DOI:", self.doi_edit)

        # PMID
        self.pmid_edit = QLineEdit()
        self.pmid_edit.setPlaceholderText("e.g., 12345678")
        self.pmid_edit.textChanged.connect(self._debounced_validator.trigger)
        identifiers_layout.addRow("PMID:", self.pmid_edit)

        layout.addWidget(identifiers_group)

        # Metadata group
        metadata_group = QGroupBox("Document Metadata")
        metadata_layout = QFormLayout(metadata_group)
        metadata_layout.setSpacing(s['spacing_small'])

        # Authors
        self.authors_edit = QLineEdit()
        self.authors_edit.setPlaceholderText("Author names, comma-separated")
        self.authors_edit.setMaxLength(MAX_AUTHORS_LENGTH)
        metadata_layout.addRow("Authors:", self.authors_edit)

        # Year
        self.year_edit = QLineEdit()
        self.year_edit.setPlaceholderText("e.g., 2024")
        self.year_edit.setMaximumWidth(s['control_height_large'] * 3)
        self.year_edit.textChanged.connect(self._debounced_validator.trigger)
        metadata_layout.addRow("Year:", self.year_edit)

        # Publication/Journal
        self.journal_edit = QLineEdit()
        self.journal_edit.setPlaceholderText("Journal or publication name")
        metadata_layout.addRow("Journal:", self.journal_edit)

        # Source selection
        self.source_combo = QComboBox()
        self._populate_sources()
        metadata_layout.addRow("Source:", self.source_combo)

        layout.addWidget(metadata_group)

        # Abstract group
        abstract_group = QGroupBox("Abstract")
        abstract_layout = QVBoxLayout(abstract_group)

        self.abstract_edit = QTextEdit()
        self.abstract_edit.setPlaceholderText("Document abstract")
        self.abstract_edit.setMinimumHeight(s['control_height_large'] * 4)
        abstract_layout.addWidget(self.abstract_edit)

        layout.addWidget(abstract_group, stretch=1)

        # Validation message
        self.validation_label = QLabel("")
        self.validation_label.setStyleSheet(
            self.style_gen.label_stylesheet(
                font_size_key='font_small',
                color=ThemeColors.ERROR_TEXT
            )
        )
        self.validation_label.setWordWrap(True)
        layout.addWidget(self.validation_label)

        # Button box
        self.button_box = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel
        )
        self.save_button = self.button_box.button(QDialogButtonBox.Save)
        self.save_button.setText("Save Document")
        self.save_button.setEnabled(False)

        self.button_box.accepted.connect(self._on_save)
        self.button_box.rejected.connect(self.reject)

        layout.addWidget(self.button_box)

    def _populate_sources(self):
        """Populate source dropdown from database."""
        try:
            from bmlibrarian.database import get_db_manager

            db_manager = get_db_manager()
            with db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT id, name FROM sources ORDER BY name")
                    sources = cur.fetchall()

            # Add "Manual Import" as default
            self.source_combo.addItem("Manual Import", None)

            for source_id, name in sources:
                self.source_combo.addItem(name, source_id)

        except Exception as e:
            logger.warning(f"Failed to load sources: {e}")
            self.source_combo.addItem("Manual Import", None)

    def _populate_fields(self):
        """Populate form fields from metadata."""
        if not self.metadata:
            return

        # Title
        title = self.metadata.get('title', '')
        if title:
            self.title_edit.setText(title)

        # DOI
        doi = self.metadata.get('doi', '')
        if doi:
            self.doi_edit.setText(doi)
            # Auto-populate external_id from DOI
            self.external_id_edit.setText(doi)

        # PMID
        pmid = self.metadata.get('pmid', '')
        if pmid:
            self.pmid_edit.setText(str(pmid))
            # If no DOI, use PMID as external_id
            if not doi:
                self.external_id_edit.setText(str(pmid))

        # Authors
        authors = self.metadata.get('authors', [])
        if isinstance(authors, list):
            self.authors_edit.setText(", ".join(authors))
        elif isinstance(authors, str):
            self.authors_edit.setText(authors)

        # Year
        year = self.metadata.get('year', '')
        if year:
            self.year_edit.setText(str(year))

        # Journal
        journal = self.metadata.get('journal', '')
        if journal:
            self.journal_edit.setText(journal)

        # Abstract
        abstract = self.metadata.get('abstract', '')
        if abstract:
            self.abstract_edit.setPlainText(abstract)

        # Validate after populating
        self._validate_form()

    def _on_doi_changed(self):
        """Update external_id when DOI changes."""
        doi = self.doi_edit.text().strip()
        if doi and not self.external_id_edit.text().strip():
            self.external_id_edit.setText(doi)
        self._debounced_validator.trigger()

    def _validate_form(self) -> bool:
        """
        Validate form fields and update UI.

        Returns:
            True if form is valid, False otherwise
        """
        errors = []

        # Validate title (required)
        title = self.title_edit.text().strip()
        is_valid, msg = validate_title(title)
        if not is_valid:
            errors.append(msg)

        # Validate DOI (optional)
        doi = self.doi_edit.text().strip()
        if doi:
            is_valid, msg = validate_doi(doi)
            if not is_valid:
                errors.append(f"DOI: {msg}")

        # Validate PMID (optional)
        pmid = self.pmid_edit.text().strip()
        if pmid:
            is_valid, msg = validate_pmid(pmid)
            if not is_valid:
                errors.append(f"PMID: {msg}")

        # Validate year (optional)
        year = self.year_edit.text().strip()
        if year:
            is_valid, msg = validate_year(year)
            if not is_valid:
                errors.append(f"Year: {msg}")

        # Update validation label
        if errors:
            self.validation_label.setText("\n".join(errors))
            self.save_button.setEnabled(False)
            return False
        else:
            self.validation_label.setText("")
            self.save_button.setEnabled(True)
            return True

    def _on_save(self):
        """Handle save button click."""
        # Force immediate validation, bypassing debounce
        self._debounced_validator.force_validate()
        if not self._validate_form():
            return

        try:
            self.document_id = self._save_to_database()
            if self.document_id:
                QMessageBox.information(
                    self,
                    "Success",
                    f"Document created successfully (ID: {self.document_id})"
                )
                self.accept()
            else:
                QMessageBox.critical(
                    self,
                    "Error",
                    "Failed to create document. Please check the logs."
                )
        except Exception as e:
            logger.exception(f"Error saving document: {e}")
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to create document:\n{e}"
            )

    def _save_to_database(self) -> Optional[int]:
        """
        Save the document to the database.

        Returns:
            Document ID if successful, None otherwise
        """
        from bmlibrarian.database import get_db_manager

        # Gather form data
        title = self.title_edit.text().strip()
        doi = self.doi_edit.text().strip() or None
        pmid = self.pmid_edit.text().strip() or None
        authors_text = self.authors_edit.text().strip()
        year_text = self.year_edit.text().strip()
        journal = self.journal_edit.text().strip() or None
        abstract = self.abstract_edit.toPlainText().strip() or None
        external_id = self.external_id_edit.text().strip()

        # Auto-generate external_id if not provided
        if not external_id:
            external_id = f"manual-{datetime.now().strftime('%Y%m%d%H%M%S')}"

        # Parse authors into array
        if authors_text:
            authors = [a.strip() for a in authors_text.split(',') if a.strip()]
        else:
            authors = None

        # Parse year into date
        publication_date = None
        if year_text:
            try:
                year = int(year_text)
                publication_date = f"{year}-01-01"
            except ValueError:
                pass

        # Get source_id
        source_id = self.source_combo.currentData()

        # PDF info
        pdf_filename = None
        if self.pdf_path and self.pdf_path.exists():
            pdf_filename = self.pdf_path.name

        db_manager = get_db_manager()

        with db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                # Check for existing document with same external_id or DOI
                if doi:
                    cur.execute(
                        "SELECT id FROM document WHERE doi = %s",
                        (doi,)
                    )
                    existing = cur.fetchone()
                    if existing:
                        raise ValueError(
                            f"Document with DOI {doi} already exists (ID: {existing[0]})"
                        )

                cur.execute(
                    "SELECT id FROM document WHERE external_id = %s",
                    (external_id,)
                )
                existing = cur.fetchone()
                if existing:
                    raise ValueError(
                        f"Document with external ID {external_id} already exists"
                    )

                # Insert document
                cur.execute("""
                    INSERT INTO document (
                        source_id, external_id, doi, title, abstract,
                        authors, publication, publication_date, pdf_filename
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (
                    source_id,
                    external_id,
                    doi,
                    title,
                    abstract,
                    authors,
                    journal,
                    publication_date,
                    pdf_filename,
                ))

                doc_id = cur.fetchone()[0]
                conn.commit()

                logger.info(f"Created document ID {doc_id}: {title}")
                return doc_id

        return None

    def get_document_id(self) -> Optional[int]:
        """Get the ID of the created document."""
        return self.document_id

    def get_document_data(self) -> Dict[str, Any]:
        """
        Get the form data as a dictionary.

        Returns:
            Dict with document metadata
        """
        authors_text = self.authors_edit.text().strip()
        if authors_text:
            authors = [a.strip() for a in authors_text.split(',') if a.strip()]
        else:
            authors = []

        return {
            'title': self.title_edit.text().strip(),
            'external_id': self.external_id_edit.text().strip(),
            'doi': self.doi_edit.text().strip() or None,
            'pmid': self.pmid_edit.text().strip() or None,
            'authors': authors,
            'year': self.year_edit.text().strip() or None,
            'journal': self.journal_edit.text().strip() or None,
            'abstract': self.abstract_edit.toPlainText().strip() or None,
            'source_id': self.source_combo.currentData(),
        }
