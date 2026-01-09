"""
Input Panel for Paper Reviewer Lab

Panel for DOI, PMID, PDF, and text input.
"""

import logging
import re
from pathlib import Path
from typing import Optional, Dict, Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QTextEdit, QPushButton, QFileDialog,
    QGroupBox, QCheckBox, QComboBox, QTabWidget,
    QFrame, QSizePolicy,
)

from bmlibrarian.gui.qt.resources.dpi_scale import scaled
from bmlibrarian.config import get_models_list, get_model

from ..constants import (
    INPUT_TYPE_DOI, INPUT_TYPE_PMID, INPUT_TYPE_PDF,
    INPUT_TYPE_TEXT, INPUT_TYPE_FILE,
    PDF_FILE_FILTER, TEXT_FILE_FILTER,
    DOI_PATTERN, PMID_PATTERN,
)

logger = logging.getLogger(__name__)


class InputPanel(QWidget):
    """
    Panel for paper input via DOI, PMID, PDF, or text.

    Signals:
        review_requested: Emitted when user clicks Review button
                         with dict containing input type and value
    """

    review_requested = Signal(dict)

    def __init__(self, parent: Optional[QWidget] = None):
        """Initialize the input panel."""
        super().__init__(parent)
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        """Set up the UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(scaled(12), scaled(12), scaled(12), scaled(12))
        layout.setSpacing(scaled(12))

        # Header
        header = QLabel("Paper Reviewer")
        header.setStyleSheet(f"font-size: {scaled(18)}px; font-weight: bold;")
        layout.addWidget(header)

        description = QLabel(
            "Enter a DOI, PMID, upload a PDF, or paste text for comprehensive review."
        )
        description.setWordWrap(True)
        layout.addWidget(description)

        # Input tabs
        self.input_tabs = QTabWidget()
        layout.addWidget(self.input_tabs)

        # DOI/PMID tab
        id_tab = QWidget()
        id_layout = QVBoxLayout(id_tab)
        id_layout.setSpacing(scaled(12))

        # DOI input
        doi_group = QGroupBox("DOI")
        doi_layout = QVBoxLayout(doi_group)
        self.doi_input = QLineEdit()
        self.doi_input.setPlaceholderText("e.g., 10.1038/nature12373")
        doi_layout.addWidget(self.doi_input)
        id_layout.addWidget(doi_group)

        # PMID input
        pmid_group = QGroupBox("PubMed ID (PMID)")
        pmid_layout = QVBoxLayout(pmid_group)
        self.pmid_input = QLineEdit()
        self.pmid_input.setPlaceholderText("e.g., 12345678")
        pmid_layout.addWidget(self.pmid_input)
        id_layout.addWidget(pmid_group)

        id_layout.addStretch()
        self.input_tabs.addTab(id_tab, "DOI / PMID")

        # PDF tab
        pdf_tab = QWidget()
        pdf_layout = QVBoxLayout(pdf_tab)
        pdf_layout.setSpacing(scaled(12))

        pdf_group = QGroupBox("PDF File")
        pdf_group_layout = QVBoxLayout(pdf_group)

        pdf_row = QHBoxLayout()
        self.pdf_path_input = QLineEdit()
        self.pdf_path_input.setPlaceholderText("Select or drag a PDF file...")
        self.pdf_path_input.setReadOnly(True)
        pdf_row.addWidget(self.pdf_path_input)

        self.pdf_browse_btn = QPushButton("Browse...")
        self.pdf_browse_btn.clicked.connect(self._browse_pdf)
        pdf_row.addWidget(self.pdf_browse_btn)

        pdf_group_layout.addLayout(pdf_row)

        # Drop zone hint
        drop_hint = QLabel("You can also drag and drop a PDF file here")
        drop_hint.setStyleSheet("color: #808080; font-style: italic;")
        pdf_group_layout.addWidget(drop_hint)

        pdf_layout.addWidget(pdf_group)
        pdf_layout.addStretch()

        self.input_tabs.addTab(pdf_tab, "PDF Upload")

        # Text tab
        text_tab = QWidget()
        text_layout = QVBoxLayout(text_tab)
        text_layout.setSpacing(scaled(8))

        # Text file or paste
        text_group = QGroupBox("Text Input")
        text_group_layout = QVBoxLayout(text_group)

        # File row
        file_row = QHBoxLayout()
        self.text_file_input = QLineEdit()
        self.text_file_input.setPlaceholderText("Or select a text/markdown file...")
        self.text_file_input.setReadOnly(True)
        file_row.addWidget(self.text_file_input)

        self.text_browse_btn = QPushButton("Browse...")
        self.text_browse_btn.clicked.connect(self._browse_text_file)
        file_row.addWidget(self.text_browse_btn)

        text_group_layout.addLayout(file_row)

        # Text area
        text_label = QLabel("Or paste abstract/full text:")
        text_group_layout.addWidget(text_label)

        self.text_input = QTextEdit()
        self.text_input.setPlaceholderText(
            "Paste the paper abstract or full text here..."
        )
        self.text_input.setMinimumHeight(scaled(150))
        text_group_layout.addWidget(self.text_input)

        text_layout.addWidget(text_group)

        self.input_tabs.addTab(text_tab, "Text Input")

        # Options section
        options_group = QGroupBox("Options")
        options_layout = QVBoxLayout(options_group)

        # Model selection
        model_row = QHBoxLayout()
        model_label = QLabel("Model:")
        model_row.addWidget(model_label)

        self.model_combo = QComboBox()
        self._populate_models()
        model_row.addWidget(self.model_combo)
        model_row.addStretch()

        options_layout.addLayout(model_row)

        # Search external checkbox
        self.search_external_cb = QCheckBox("Search PubMed for contradictory evidence")
        self.search_external_cb.setChecked(True)
        options_layout.addWidget(self.search_external_cb)

        layout.addWidget(options_group)

        # Review button
        button_row = QHBoxLayout()
        button_row.addStretch()

        self.review_btn = QPushButton("Review Paper")
        self.review_btn.setMinimumWidth(scaled(120))
        self.review_btn.setMinimumHeight(scaled(36))
        self.review_btn.setStyleSheet("""
            QPushButton {
                background-color: #1E90FF;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1C86EE;
            }
            QPushButton:disabled {
                background-color: #808080;
            }
        """)
        self.review_btn.clicked.connect(self._on_review_clicked)
        button_row.addWidget(self.review_btn)

        layout.addLayout(button_row)

    def _connect_signals(self) -> None:
        """Connect internal signals."""
        # Clear other inputs when one is used
        self.doi_input.textChanged.connect(lambda: self._on_input_changed(INPUT_TYPE_DOI))
        self.pmid_input.textChanged.connect(lambda: self._on_input_changed(INPUT_TYPE_PMID))
        self.text_input.textChanged.connect(lambda: self._on_input_changed(INPUT_TYPE_TEXT))

    def _populate_models(self) -> None:
        """Populate the model dropdown."""
        try:
            models = get_models_list()
            current_model = get_model('paper_reviewer')

            self.model_combo.clear()
            for model in models:
                self.model_combo.addItem(model)

            # Select current model
            index = self.model_combo.findText(current_model)
            if index >= 0:
                self.model_combo.setCurrentIndex(index)
        except Exception as e:
            logger.warning(f"Failed to get models list: {e}")
            self.model_combo.addItem("default")

    def _on_input_changed(self, input_type: str) -> None:
        """Handle input field change."""
        # Don't clear other fields - let user switch tabs
        pass

    def _browse_pdf(self) -> None:
        """Open file dialog for PDF selection."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Select PDF File", "", PDF_FILE_FILTER
        )
        if path:
            self.pdf_path_input.setText(path)
            # Clear text file if set
            self.text_file_input.clear()

    def _browse_text_file(self) -> None:
        """Open file dialog for text file selection."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Text File", "", TEXT_FILE_FILTER
        )
        if path:
            self.text_file_input.setText(path)
            # Clear text input
            self.text_input.clear()

    def _validate_doi(self, doi: str) -> bool:
        """Validate DOI format."""
        if not doi:
            return False
        # Normalize
        doi = doi.strip()
        for prefix in ['https://doi.org/', 'http://doi.org/', 'doi.org/', 'doi:']:
            if doi.lower().startswith(prefix.lower()):
                doi = doi[len(prefix):]
        return bool(re.match(DOI_PATTERN, doi))

    def _validate_pmid(self, pmid: str) -> bool:
        """Validate PMID format."""
        if not pmid:
            return False
        pmid = pmid.strip()
        for prefix in ['pmid:', 'pmid', 'pubmed:']:
            if pmid.lower().startswith(prefix.lower()):
                pmid = pmid[len(prefix):]
        return bool(re.match(PMID_PATTERN, pmid))

    def _get_active_input(self) -> Optional[Dict[str, Any]]:
        """Get the active input based on current tab and filled fields."""
        current_tab = self.input_tabs.currentIndex()

        if current_tab == 0:  # DOI/PMID tab
            doi = self.doi_input.text().strip()
            pmid = self.pmid_input.text().strip()

            if doi:
                if not self._validate_doi(doi):
                    return {"error": "Invalid DOI format"}
                return {"type": INPUT_TYPE_DOI, "value": doi}
            elif pmid:
                if not self._validate_pmid(pmid):
                    return {"error": "Invalid PMID format"}
                return {"type": INPUT_TYPE_PMID, "value": pmid}

        elif current_tab == 1:  # PDF tab
            pdf_path = self.pdf_path_input.text().strip()
            if pdf_path:
                path = Path(pdf_path)
                if not path.exists():
                    return {"error": f"PDF file not found: {pdf_path}"}
                return {"type": INPUT_TYPE_PDF, "value": path}

        elif current_tab == 2:  # Text tab
            text_file = self.text_file_input.text().strip()
            if text_file:
                path = Path(text_file)
                if not path.exists():
                    return {"error": f"Text file not found: {text_file}"}
                return {"type": INPUT_TYPE_FILE, "value": path}

            text = self.text_input.toPlainText().strip()
            if text:
                return {"type": INPUT_TYPE_TEXT, "value": text}

        return None

    def _on_review_clicked(self) -> None:
        """Handle Review button click."""
        input_data = self._get_active_input()

        if not input_data:
            logger.warning("No input provided")
            return

        if "error" in input_data:
            logger.warning(f"Input validation error: {input_data['error']}")
            # Could show error dialog here
            return

        # Add options
        input_data["search_external"] = self.search_external_cb.isChecked()
        input_data["model"] = self.model_combo.currentText()

        logger.info(f"Review requested: {input_data['type']}")
        self.review_requested.emit(input_data)

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable the panel."""
        self.review_btn.setEnabled(enabled)
        self.input_tabs.setEnabled(enabled)

    def clear(self) -> None:
        """Clear all inputs."""
        self.doi_input.clear()
        self.pmid_input.clear()
        self.pdf_path_input.clear()
        self.text_file_input.clear()
        self.text_input.clear()


__all__ = ['InputPanel']
