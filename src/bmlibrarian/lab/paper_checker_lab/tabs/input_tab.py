"""
PaperChecker Laboratory - Input Tab

Tab widget for abstract text input and PMID lookup.
"""

import logging
from typing import Optional, List, Dict, Any

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QTextEdit, QGroupBox, QMessageBox,
    QSizePolicy,
)
from PySide6.QtCore import Signal

from bmlibrarian.gui.qt.resources.styles.dpi_scale import get_font_scale
from bmlibrarian.gui.qt.resources.styles.stylesheet_generator import get_stylesheet_generator

from ..constants import (
    COLOR_PRIMARY, COLOR_SUCCESS, COLOR_WARNING, COLOR_ERROR,
    MIN_ABSTRACT_LENGTH,
)
from ..utils import validate_abstract, validate_pmid
from ..dialogs import PMIDLookupDialog


logger = logging.getLogger(__name__)


class InputTab(QWidget):
    """
    Tab widget for abstract text input and PMID lookup.

    Provides text input for abstract, model selection, and PMID lookup
    functionality for fetching abstracts from the database.

    Signals:
        check_requested: Emitted when user requests a check.
            Args: abstract (str), metadata (dict)
        clear_requested: Emitted when user requests to clear.
    """

    check_requested = Signal(str, dict)  # (abstract, source_metadata)
    clear_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """
        Initialize input tab.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)

        self.scale = get_font_scale()
        self.styles = get_stylesheet_generator()
        self._available_models: List[str] = []
        self._current_metadata: Dict[str, Any] = {}

        self._setup_ui()
        self._load_models()

    def _setup_ui(self) -> None:
        """Setup tab user interface."""
        layout = QVBoxLayout(self)
        layout.setSpacing(self.scale['spacing_medium'])
        layout.setContentsMargins(
            self.scale['padding_large'],
            self.scale['padding_large'],
            self.scale['padding_large'],
            self.scale['padding_large']
        )

        # Model selection section
        model_group = QGroupBox("Model Selection")
        model_layout = QHBoxLayout()

        model_label = QLabel("Model:")
        model_layout.addWidget(model_label)

        self._model_combo = QComboBox()
        self._model_combo.setMinimumWidth(self.scale['control_width_large'])
        self._model_combo.currentTextChanged.connect(self._on_model_changed)
        model_layout.addWidget(self._model_combo, stretch=1)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setToolTip("Refresh available models from Ollama")
        refresh_btn.clicked.connect(self._load_models)
        model_layout.addWidget(refresh_btn)

        model_group.setLayout(model_layout)
        layout.addWidget(model_group)

        # Abstract input section
        abstract_group = QGroupBox("Abstract Input")
        abstract_layout = QVBoxLayout()

        # Instructions
        instructions = QLabel(
            "Enter the medical abstract text to fact-check, or use PMID lookup "
            "to fetch an abstract from the database."
        )
        instructions.setWordWrap(True)
        instructions.setStyleSheet(f"color: {self.scale.get('color_secondary', '#666')};")
        abstract_layout.addWidget(instructions)

        # Text input
        self._abstract_input = QTextEdit()
        self._abstract_input.setPlaceholderText(
            "Paste or type the medical abstract text here...\n\n"
            "The abstract should contain specific claims, findings, or conclusions "
            "that can be fact-checked against the literature."
        )
        self._abstract_input.setMinimumHeight(self.scale['base_line_height'] * 8)
        self._abstract_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._abstract_input.textChanged.connect(self._on_text_changed)
        abstract_layout.addWidget(self._abstract_input, stretch=1)

        # Character count
        self._char_count_label = QLabel("0 characters")
        self._char_count_label.setStyleSheet(f"color: #666;")
        abstract_layout.addWidget(self._char_count_label)

        abstract_group.setLayout(abstract_layout)
        layout.addWidget(abstract_group, stretch=1)

        # PMID lookup section
        pmid_group = QGroupBox("PMID Lookup")
        pmid_layout = QHBoxLayout()

        pmid_label = QLabel("PMID:")
        pmid_layout.addWidget(pmid_label)

        self._pmid_input = QLineEdit()
        self._pmid_input.setPlaceholderText("e.g., 12345678")
        self._pmid_input.setMaximumWidth(self.scale['control_width_medium'])
        self._pmid_input.returnPressed.connect(self._fetch_by_pmid)
        pmid_layout.addWidget(self._pmid_input)

        fetch_btn = QPushButton("Fetch Abstract")
        fetch_btn.setToolTip("Fetch abstract from database by PMID")
        fetch_btn.clicked.connect(self._fetch_by_pmid)
        pmid_layout.addWidget(fetch_btn)

        browse_btn = QPushButton("Browse...")
        browse_btn.setToolTip("Browse database for documents")
        browse_btn.clicked.connect(self._browse_database)
        pmid_layout.addWidget(browse_btn)

        pmid_layout.addStretch()

        pmid_group.setLayout(pmid_layout)
        layout.addWidget(pmid_group)

        # Source metadata display (initially hidden)
        self._metadata_label = QLabel("")
        self._metadata_label.setWordWrap(True)
        self._metadata_label.setVisible(False)
        self._metadata_label.setStyleSheet(f"""
            background-color: #f0f8ff;
            padding: {self.scale['padding_medium']}px;
            border-radius: {self.scale['radius_small']}px;
            color: #333;
        """)
        layout.addWidget(self._metadata_label)

        # Action buttons
        button_layout = QHBoxLayout()

        self._check_btn = QPushButton("Check Abstract")
        self._check_btn.setToolTip("Start fact-checking the abstract")
        self._check_btn.clicked.connect(self._on_check_clicked)
        self._check_btn.setStyleSheet(self.styles.button_stylesheet(bg_color=COLOR_SUCCESS))
        self._check_btn.setMinimumHeight(self.scale['control_height_large'])
        button_layout.addWidget(self._check_btn)

        self._clear_btn = QPushButton("Clear")
        self._clear_btn.setToolTip("Clear all inputs")
        self._clear_btn.clicked.connect(self._on_clear_clicked)
        self._clear_btn.setMinimumHeight(self.scale['control_height_large'])
        button_layout.addWidget(self._clear_btn)

        button_layout.addStretch()

        layout.addLayout(button_layout)

    def _load_models(self) -> None:
        """Load available models from Ollama."""
        try:
            import ollama
            response = ollama.list()
            models = [m.get('name', m.get('model', '')) for m in response.get('models', [])]
            self._available_models = sorted(models)

            current_text = self._model_combo.currentText()
            self._model_combo.clear()
            self._model_combo.addItems(self._available_models)

            # Try to restore previous selection or use default
            if current_text and current_text in self._available_models:
                self._model_combo.setCurrentText(current_text)
            elif 'gpt-oss:20b' in self._available_models:
                self._model_combo.setCurrentText('gpt-oss:20b')

            logger.info(f"Loaded {len(self._available_models)} models from Ollama")

        except Exception as e:
            logger.error(f"Failed to load models: {e}")
            QMessageBox.warning(
                self,
                "Model Load Error",
                f"Could not load models from Ollama:\n{str(e)}"
            )

    def _on_model_changed(self, model_name: str) -> None:
        """Handle model selection change."""
        logger.debug(f"Model changed to: {model_name}")

    def _on_text_changed(self) -> None:
        """Handle abstract text changes."""
        text = self._abstract_input.toPlainText()
        char_count = len(text)

        if char_count < MIN_ABSTRACT_LENGTH:
            color = COLOR_WARNING
        else:
            color = "#666"

        self._char_count_label.setText(f"{char_count:,} characters")
        self._char_count_label.setStyleSheet(f"color: {color};")

    def _fetch_by_pmid(self) -> None:
        """Fetch abstract by PMID from database."""
        pmid_str = self._pmid_input.text().strip()

        is_valid, pmid, error = validate_pmid(pmid_str)
        if not is_valid:
            QMessageBox.warning(self, "Invalid PMID", error)
            return

        # Use worker for database lookup
        from ..worker import DocumentFetchWorker

        self._fetch_worker = DocumentFetchWorker(pmid)
        self._fetch_worker.fetch_complete.connect(self._on_fetch_complete)
        self._fetch_worker.fetch_error.connect(self._on_fetch_error)
        self._fetch_worker.start()

    def _on_fetch_complete(self, document: dict) -> None:
        """Handle successful document fetch."""
        abstract = document.get('abstract', '')
        if not abstract:
            QMessageBox.warning(
                self,
                "No Abstract",
                "The document was found but has no abstract."
            )
            return

        # Populate the abstract input
        self._abstract_input.setPlainText(abstract)

        # Store and display metadata
        self._current_metadata = {
            'pmid': document.get('pmid'),
            'doi': document.get('doi'),
            'title': document.get('title'),
            'authors': document.get('authors'),
            'year': document.get('publication_date'),
        }

        self._show_metadata(document)
        logger.info(f"Fetched abstract for PMID {document.get('pmid')}")

    def _on_fetch_error(self, error: str) -> None:
        """Handle fetch error."""
        QMessageBox.warning(
            self,
            "Fetch Error",
            f"Could not fetch document:\n{error}"
        )

    def _browse_database(self) -> None:
        """Open PMID lookup dialog."""
        dialog = PMIDLookupDialog(self)
        if dialog.exec():
            result = dialog.get_result()
            if result:
                self._on_fetch_complete(result)

    def _show_metadata(self, document: dict) -> None:
        """Display source metadata."""
        parts = []

        if document.get('title'):
            parts.append(f"<b>{document['title']}</b>")

        meta_parts = []
        if document.get('authors'):
            authors = document['authors']
            if isinstance(authors, list):
                authors = ', '.join(authors[:3])
                if len(document['authors']) > 3:
                    authors += ' et al.'
            meta_parts.append(authors)

        if document.get('publication_date'):
            meta_parts.append(str(document['publication_date'])[:4])

        if document.get('pmid'):
            meta_parts.append(f"PMID: {document['pmid']}")

        if document.get('doi'):
            meta_parts.append(f"DOI: {document['doi']}")

        if meta_parts:
            parts.append(' | '.join(meta_parts))

        self._metadata_label.setText('<br>'.join(parts))
        self._metadata_label.setVisible(True)

    def _on_check_clicked(self) -> None:
        """Handle check button click."""
        abstract = self._abstract_input.toPlainText().strip()

        # Validate abstract
        is_valid, error = validate_abstract(abstract)
        if not is_valid:
            QMessageBox.warning(self, "Invalid Abstract", error)
            return

        # Emit check requested signal
        self.check_requested.emit(abstract, self._current_metadata.copy())

    def _on_clear_clicked(self) -> None:
        """Handle clear button click."""
        self._abstract_input.clear()
        self._pmid_input.clear()
        self._current_metadata.clear()
        self._metadata_label.setVisible(False)
        self.clear_requested.emit()

    def get_selected_model(self) -> str:
        """
        Get the currently selected model.

        Returns:
            Model name string
        """
        return self._model_combo.currentText()

    def set_abstract(self, abstract: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """
        Set the abstract text programmatically.

        Args:
            abstract: Abstract text
            metadata: Optional source metadata
        """
        self._abstract_input.setPlainText(abstract)

        if metadata:
            self._current_metadata = metadata.copy()
            self._show_metadata(metadata)
        else:
            self._current_metadata.clear()
            self._metadata_label.setVisible(False)

    def set_enabled(self, enabled: bool) -> None:
        """
        Enable or disable the tab controls.

        Args:
            enabled: Whether controls should be enabled
        """
        self._abstract_input.setEnabled(enabled)
        self._pmid_input.setEnabled(enabled)
        self._check_btn.setEnabled(enabled)
        self._clear_btn.setEnabled(enabled)
        self._model_combo.setEnabled(enabled)


__all__ = ['InputTab']
