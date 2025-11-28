"""
Main citation editor widget.

A complete citation-aware markdown editor with:
- Split-pane layout (editor/preview on left, search/document on right)
- Autosave with version history
- Multiple citation styles
- Export with formatted references
"""

import logging
from pathlib import Path
from typing import Optional, Dict, Any, Callable

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QTabWidget,
    QPushButton, QToolBar, QComboBox, QLabel, QFileDialog,
    QMessageBox, QStatusBar, QMenu, QLineEdit, QInputDialog
)
from PySide6.QtCore import Signal, Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence

from ...resources.styles import get_font_scale, StylesheetGenerator
from .markdown_editor import MarkdownEditorWidget
from .markdown_preview import CitationMarkdownPreview
from .search_panel import CitationSearchPanel
from .document_panel import CitationDocumentPanel
from .citation_manager import CitationManager

from bmlibrarian.writing import (
    DocumentStore, WritingDocument, CitationStyle,
    AUTOSAVE_INTERVAL_SECONDS, MAX_VERSIONS
)
from bmlibrarian.exporters import PDFExporter, PDFExportError

logger = logging.getLogger(__name__)


class CitationEditorWidget(QWidget):
    """
    Main citation editor widget.

    Provides a complete environment for academic writing with
    integrated citation management.

    Signals:
        document_saved: Emitted when document is saved
        document_exported: Emitted when document is exported
        unsaved_changes: Emitted when there are unsaved changes (bool)
    """

    document_saved = Signal(int)  # document_id
    document_exported = Signal(str)  # export_path
    unsaved_changes = Signal(bool)

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        autosave_interval: int = AUTOSAVE_INTERVAL_SECONDS
    ) -> None:
        """
        Initialize citation editor.

        Args:
            parent: Parent widget
            autosave_interval: Autosave interval in seconds (0 to disable)
        """
        super().__init__(parent)

        self.scale = get_font_scale()
        self.style_gen = StylesheetGenerator()

        # State
        self._document = WritingDocument()
        self._has_unsaved_changes = False
        self._autosave_interval = autosave_interval

        # Components
        self._document_store = DocumentStore()
        self._citation_manager = CitationManager()

        # Timers
        self._autosave_timer: Optional[QTimer] = None
        self._preview_update_timer: Optional[QTimer] = None

        self._setup_ui()
        self._setup_toolbar()
        self._setup_status_bar()
        self._connect_signals()
        self._setup_autosave()

        # Load most recent document on startup
        self._load_most_recent_document()

    def _setup_ui(self) -> None:
        """Set up the user interface."""
        s = self.scale

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Toolbar placeholder (will be added in _setup_toolbar)
        self.toolbar_container = QWidget()
        toolbar_layout = QHBoxLayout(self.toolbar_container)
        toolbar_layout.setContentsMargins(s['padding_small'], s['padding_small'],
                                          s['padding_small'], s['padding_small'])
        layout.addWidget(self.toolbar_container)

        # Main splitter
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left panel - Editor and Preview
        self.left_panel = QWidget()
        left_layout = QVBoxLayout(self.left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self.left_tabs = QTabWidget()

        # Editor tab
        self.editor = MarkdownEditorWidget()
        self.left_tabs.addTab(self.editor, "Editor")

        # Preview tab
        self.preview = CitationMarkdownPreview()
        self.left_tabs.addTab(self.preview, "Preview")

        left_layout.addWidget(self.left_tabs)

        # Right panel - Search and Document
        self.right_panel = QWidget()
        right_layout = QVBoxLayout(self.right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)

        self.right_tabs = QTabWidget()

        # Search tab
        self.search_panel = CitationSearchPanel()
        self.right_tabs.addTab(self.search_panel, "Search")

        # Document tab
        self.document_panel = CitationDocumentPanel()
        self.right_tabs.addTab(self.document_panel, "Document")

        right_layout.addWidget(self.right_tabs)

        # Add panels to splitter
        self.main_splitter.addWidget(self.left_panel)
        self.main_splitter.addWidget(self.right_panel)

        # Set initial sizes (50/50)
        self.main_splitter.setSizes([500, 500])

        layout.addWidget(self.main_splitter, 1)

        # Status bar placeholder
        self.status_bar_container = QWidget()
        layout.addWidget(self.status_bar_container)

    def _setup_toolbar(self) -> None:
        """Set up the toolbar."""
        s = self.scale
        toolbar_layout = self.toolbar_container.layout()

        # Document title input
        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText("Document Title")
        self.title_input.setText(self._document.title)
        self.title_input.setStyleSheet(self.style_gen.input_stylesheet())
        self.title_input.setMinimumWidth(s['control_width_medium'])
        toolbar_layout.addWidget(self.title_input)

        toolbar_layout.addStretch()

        # New Document
        self.new_btn = QPushButton("New")
        self.new_btn.setStyleSheet(
            self.style_gen.button_stylesheet(bg_color="#9E9E9E", hover_color="#757575")
        )
        self.new_btn.setToolTip("Create new document")
        toolbar_layout.addWidget(self.new_btn)

        # Open Document
        self.open_btn = QPushButton("Open")
        self.open_btn.setStyleSheet(
            self.style_gen.button_stylesheet(bg_color="#9E9E9E", hover_color="#757575")
        )
        self.open_btn.setToolTip("Open existing document")
        toolbar_layout.addWidget(self.open_btn)

        # Save Document
        self.save_btn = QPushButton("Save")
        self.save_btn.setStyleSheet(
            self.style_gen.button_stylesheet(bg_color="#2196F3", hover_color="#1976D2")
        )
        self.save_btn.setToolTip("Save document (Ctrl+S)")
        self.save_btn.setShortcut(QKeySequence.StandardKey.Save)
        toolbar_layout.addWidget(self.save_btn)

        # Export dropdown
        self.export_btn = QPushButton("Export ▼")
        self.export_btn.setStyleSheet(
            self.style_gen.button_stylesheet(bg_color="#FF9800", hover_color="#F57C00")
        )
        self.export_btn.setToolTip("Export document")

        export_menu = QMenu(self.export_btn)
        export_menu.addAction("PDF (formatted)", self._export_pdf)
        export_menu.addSeparator()
        export_menu.addAction("Markdown (formatted)", self._export_formatted)
        export_menu.addAction("Markdown (raw)", self._export_raw)
        export_menu.addSeparator()
        export_menu.addAction("Copy to Clipboard (formatted)", self._copy_formatted)
        export_menu.addAction("Copy to Clipboard (raw)", self._copy_raw)
        self.export_btn.setMenu(export_menu)
        toolbar_layout.addWidget(self.export_btn)

        # Separator
        toolbar_layout.addSpacing(s['spacing_large'])

        # Format Citations
        self.format_btn = QPushButton("Format Citations")
        self.format_btn.setStyleSheet(
            self.style_gen.button_stylesheet(bg_color="#4CAF50", hover_color="#388E3C")
        )
        self.format_btn.setToolTip("Replace citations with numbered references")
        toolbar_layout.addWidget(self.format_btn)

        # Citation style dropdown
        self.style_combo = QComboBox()
        for style in CitationStyle:
            self.style_combo.addItem(
                CitationManager().get_style_description(style),
                style
            )
        self.style_combo.setToolTip("Citation formatting style")
        self.style_combo.setStyleSheet(self.style_gen.combo_stylesheet())
        toolbar_layout.addWidget(self.style_combo)

    def _setup_status_bar(self) -> None:
        """Set up the status bar."""
        s = self.scale

        layout = QHBoxLayout(self.status_bar_container)
        layout.setContentsMargins(s['padding_small'], s['padding_tiny'],
                                  s['padding_small'], s['padding_tiny'])

        # Citation count
        self.citation_label = QLabel("Citations: 0")
        self.citation_label.setStyleSheet(
            self.style_gen.label_stylesheet(font_size_key='font_small', color='#666')
        )
        layout.addWidget(self.citation_label)

        layout.addSpacing(s['spacing_large'])

        # Word count
        self.word_label = QLabel("Words: 0")
        self.word_label.setStyleSheet(
            self.style_gen.label_stylesheet(font_size_key='font_small', color='#666')
        )
        layout.addWidget(self.word_label)

        layout.addStretch()

        # Autosave status
        self.autosave_label = QLabel("")
        self.autosave_label.setStyleSheet(
            self.style_gen.label_stylesheet(font_size_key='font_small', color='#888')
        )
        layout.addWidget(self.autosave_label)

        layout.addSpacing(s['spacing_large'])

        # Unsaved indicator
        self.unsaved_label = QLabel("")
        self.unsaved_label.setStyleSheet(
            self.style_gen.label_stylesheet(font_size_key='font_small', color='#F44336')
        )
        layout.addWidget(self.unsaved_label)

    def _connect_signals(self) -> None:
        """Connect signal handlers."""
        # Toolbar buttons
        self.new_btn.clicked.connect(self._on_new)
        self.open_btn.clicked.connect(self._on_open)
        self.save_btn.clicked.connect(self._on_save)
        self.format_btn.clicked.connect(self._on_format_citations)
        self.style_combo.currentIndexChanged.connect(self._on_style_changed)
        self.title_input.textChanged.connect(self._on_title_changed)

        # Editor signals
        self.editor.text_changed.connect(self._on_text_changed)
        self.editor.citation_search_requested.connect(self._on_citation_search)
        self.editor.insert_citation_shortcut.connect(self._on_insert_shortcut)

        # Search panel signals
        self.search_panel.document_selected.connect(self._on_document_selected)
        self.search_panel.document_double_clicked.connect(self._on_document_double_clicked)

        # Document panel signals
        self.document_panel.insert_citation.connect(self._on_insert_citation)
        self.document_panel.back_to_search.connect(self._on_back_to_search)

        # Preview signals
        self.preview.citation_clicked.connect(self._on_citation_clicked)

        # Tab change signals
        self.left_tabs.currentChanged.connect(self._on_left_tab_changed)

        # Citation manager signals
        self._citation_manager.citations_updated.connect(self._on_citations_updated)

    def _setup_autosave(self) -> None:
        """Set up autosave timer."""
        if self._autosave_interval > 0:
            self._autosave_timer = QTimer(self)
            self._autosave_timer.timeout.connect(self._do_autosave)
            self._autosave_timer.start(self._autosave_interval * 1000)

        # Preview update timer (debounce)
        self._preview_update_timer = QTimer(self)
        self._preview_update_timer.setSingleShot(True)
        self._preview_update_timer.timeout.connect(self._update_preview)

    # Event handlers

    def _on_text_changed(self, text: str) -> None:
        """Handle editor text change."""
        self._document.content = text
        self._mark_unsaved()

        # Update citation manager
        self._citation_manager.update_text(text)

        # Update word count
        words = len(text.split())
        self.word_label.setText(f"Words: {words:,}")

        # Schedule preview update (debounced)
        self._preview_update_timer.start(500)

    def _on_title_changed(self, title: str) -> None:
        """Handle title change."""
        self._document.title = title
        self._mark_unsaved()

    def _on_style_changed(self, index: int) -> None:
        """Handle citation style change."""
        style = self.style_combo.currentData()
        if style:
            self._citation_manager.style = style

    def _on_citations_updated(self, total: int, unique: int) -> None:
        """Handle citation count update."""
        self.citation_label.setText(f"Citations: {total} ({unique} unique)")

    def _on_left_tab_changed(self, index: int) -> None:
        """Handle left tab change."""
        if index == 1:  # Preview tab
            self._update_preview()

    def _update_preview(self) -> None:
        """Update the preview pane."""
        text = self.editor.toPlainText()
        self.preview.set_markdown(text)

        # Update citation metadata for tooltips
        metadata = self._citation_manager.get_citation_metadata_for_preview()
        self.preview.set_citation_metadata(metadata)

    def _on_citation_search(self, text: str) -> None:
        """Handle citation search request from editor."""
        self.search_panel.set_search_query(text)
        self.search_panel.search(text)
        self.right_tabs.setCurrentIndex(0)  # Switch to search tab

    def _on_document_selected(self, doc_data: Dict[str, Any]) -> None:
        """Handle document selection in search results."""
        self.document_panel.load_document(doc_data)
        self.right_tabs.setCurrentIndex(1)  # Switch to document tab

    def _on_document_double_clicked(self, doc_data: Dict[str, Any]) -> None:
        """Handle document double-click (quick insert)."""
        doc_id = doc_data.get('id') or doc_data.get('document_id')
        if doc_id:
            label = self._citation_manager.generate_label(doc_id)
            self._insert_citation_with_reference(doc_id, label)

    def _on_insert_citation(self, document_id: int, label: str) -> None:
        """Handle citation insertion."""
        self._insert_citation_with_reference(document_id, label)
        self.editor.setFocus()

    def _on_insert_shortcut(self) -> None:
        """Handle Ctrl+Shift+K shortcut."""
        doc_id = self.document_panel.get_current_document_id()
        if doc_id:
            label = self._citation_manager.generate_label(doc_id)
            self._insert_citation_with_reference(doc_id, label)

    def _insert_citation_with_reference(self, document_id: int, label: str) -> None:
        """
        Insert citation and add to References section if new.

        If the citation is for a document not already cited, the reference
        is automatically appended to the ## References section.

        Args:
            document_id: Database document ID
            label: Human-readable citation label
        """
        # Check if this is a new citation before inserting
        is_new = not self._citation_manager.is_citation_already_used(document_id)

        # Insert the citation marker at cursor
        self.editor.insert_citation(document_id, label)

        # If this is a new citation, add to References section
        if is_new:
            self._add_reference_entry(document_id)

    def _on_back_to_search(self) -> None:
        """Handle back to search button."""
        self.right_tabs.setCurrentIndex(0)

    def _on_citation_clicked(self, document_id: int) -> None:
        """Handle citation click in preview."""
        self.document_panel.load_document_by_id(document_id)
        self.right_tabs.setCurrentIndex(1)

    # Document operations

    def _on_new(self) -> None:
        """Create new document."""
        if self._has_unsaved_changes:
            reply = QMessageBox.question(
                self,
                "Unsaved Changes",
                "You have unsaved changes. Do you want to save before creating a new document?",
                QMessageBox.StandardButton.Save |
                QMessageBox.StandardButton.Discard |
                QMessageBox.StandardButton.Cancel
            )

            if reply == QMessageBox.StandardButton.Save:
                self._on_save()
            elif reply == QMessageBox.StandardButton.Cancel:
                return

        self._document = WritingDocument()
        self.editor.setPlainText("")
        self.title_input.setText("Untitled Document")
        self._has_unsaved_changes = False
        self._update_unsaved_indicator()

    def _on_open(self) -> None:
        """Open existing document."""
        # Get list of documents
        documents = self._document_store.list_documents(limit=50)

        if not documents:
            QMessageBox.information(
                self,
                "No Documents",
                "No saved documents found."
            )
            return

        # Show selection dialog
        items = [f"{d['title']} (ID: {d['id']})" for d in documents]
        item, ok = QInputDialog.getItem(
            self,
            "Open Document",
            "Select a document:",
            items,
            0,
            False
        )

        if ok and item:
            # Extract ID from selection
            try:
                doc_id = int(item.split("ID: ")[1].rstrip(")"))
                self.load_document(doc_id)
            except (IndexError, ValueError):
                logger.error(f"Failed to parse document ID from: {item}")

    def _on_save(self) -> None:
        """Save document."""
        self._document.title = self.title_input.text()
        self._document.content = self.editor.toPlainText()

        try:
            self._document = self._document_store.save_document(
                self._document,
                version_type="manual"
            )
            self._has_unsaved_changes = False
            self._update_unsaved_indicator()
            self.autosave_label.setText("Saved")

            self.document_saved.emit(self._document.id)

            logger.info(f"Document saved: {self._document.id}")

        except Exception as e:
            logger.error(f"Failed to save document: {e}")
            QMessageBox.critical(
                self,
                "Save Error",
                f"Failed to save document: {e}"
            )

    def _on_format_citations(self) -> None:
        """Format citations with reference list."""
        # Strip existing References section before formatting
        text = self._strip_references_section(self.editor.toPlainText())
        formatted = self._citation_manager.format_full_document(text)

        # Show in preview
        self.preview.set_markdown(formatted)
        self.left_tabs.setCurrentIndex(1)  # Switch to preview

        QMessageBox.information(
            self,
            "Citations Formatted",
            "Citations have been formatted in the preview.\n\n"
            "Use 'Export' to save the formatted document."
        )

    # Export operations

    def _export_formatted(self) -> None:
        """Export document with formatted citations."""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Formatted Document",
            f"{self._document.title}.md",
            "Markdown Files (*.md)"
        )

        if file_path:
            try:
                # Get text and remove existing References section
                text = self._strip_references_section(self.editor.toPlainText())

                # Format with numbered citations and proper reference list
                formatted = self._citation_manager.format_full_document(text)

                Path(file_path).write_text(formatted, encoding='utf-8')
                self.document_exported.emit(file_path)
                QMessageBox.information(
                    self,
                    "Export Complete",
                    f"Document exported to:\n{file_path}"
                )
            except Exception as e:
                QMessageBox.critical(self, "Export Error", str(e))

    def _export_raw(self) -> None:
        """Export document with citation markers intact."""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Raw Document",
            f"{self._document.title}_raw.md",
            "Markdown Files (*.md)"
        )

        if file_path:
            try:
                Path(file_path).write_text(
                    self.editor.toPlainText(),
                    encoding='utf-8'
                )
                self.document_exported.emit(file_path)
                QMessageBox.information(
                    self,
                    "Export Complete",
                    f"Document exported to:\n{file_path}"
                )
            except Exception as e:
                QMessageBox.critical(self, "Export Error", str(e))

    def _export_pdf(self) -> None:
        """Export document as PDF with formatted citations."""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export PDF Document",
            f"{self._document.title}.pdf",
            "PDF Files (*.pdf)"
        )

        if file_path:
            try:
                # Get text and remove existing References section
                text = self._strip_references_section(self.editor.toPlainText())

                # Format with numbered citations and proper reference list
                formatted = self._citation_manager.format_full_document(text)

                # Export to PDF
                exporter = PDFExporter()
                exporter.markdown_to_pdf(
                    markdown_content=formatted,
                    output_path=Path(file_path),
                    metadata={
                        'title': self._document.title,
                        'author': 'BMLibrarian',
                        'subject': 'Academic Writing'
                    }
                )

                self.document_exported.emit(file_path)
                QMessageBox.information(
                    self,
                    "Export Complete",
                    f"PDF exported to:\n{file_path}"
                )
            except PDFExportError as e:
                QMessageBox.critical(
                    self,
                    "PDF Export Error",
                    f"Failed to export PDF:\n{str(e)}"
                )
            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Export Error",
                    f"Unexpected error:\n{str(e)}"
                )

    def _copy_formatted(self) -> None:
        """Copy formatted document to clipboard."""
        from PySide6.QtWidgets import QApplication

        # Strip existing References section before formatting
        text = self._strip_references_section(self.editor.toPlainText())
        formatted = self._citation_manager.format_full_document(text)
        QApplication.clipboard().setText(formatted)

    def _copy_raw(self) -> None:
        """Copy raw document to clipboard."""
        from PySide6.QtWidgets import QApplication

        QApplication.clipboard().setText(self.editor.toPlainText())

    # Autosave

    def _do_autosave(self) -> None:
        """Perform autosave."""
        if not self._has_unsaved_changes:
            return

        if not self._document.content.strip():
            return

        try:
            self._document.title = self.title_input.text()
            self._document.content = self.editor.toPlainText()

            self._document = self._document_store.autosave_document(self._document)

            # Don't clear unsaved flag - user should still explicitly save
            self.autosave_label.setText("Auto-saved")

            logger.debug(f"Document auto-saved: {self._document.id}")

        except Exception as e:
            logger.error(f"Autosave failed: {e}")
            self.autosave_label.setText("Autosave failed")

    def _mark_unsaved(self) -> None:
        """Mark document as having unsaved changes."""
        self._has_unsaved_changes = True
        self._update_unsaved_indicator()
        self.unsaved_changes.emit(True)

    def _update_unsaved_indicator(self) -> None:
        """Update unsaved changes indicator."""
        if self._has_unsaved_changes:
            self.unsaved_label.setText("● Unsaved changes")
        else:
            self.unsaved_label.setText("")

    # Public API

    def load_document(self, document_id: int) -> bool:
        """
        Load a document by ID.

        Args:
            document_id: Document database ID

        Returns:
            True if loaded successfully
        """
        try:
            document = self._document_store.load_document(document_id)
            if document:
                self._document = document
                self.editor.setPlainText(document.content)
                self.title_input.setText(document.title)
                self._has_unsaved_changes = False
                self._update_unsaved_indicator()
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to load document {document_id}: {e}")
            return False

    def get_document(self) -> WritingDocument:
        """Get the current document."""
        self._document.content = self.editor.toPlainText()
        self._document.title = self.title_input.text()
        return self._document

    def set_content(self, content: str) -> None:
        """Set editor content."""
        self.editor.setPlainText(content)

    def get_content(self) -> str:
        """Get editor content."""
        return self.editor.toPlainText()

    def has_unsaved_changes(self) -> bool:
        """Check if there are unsaved changes."""
        return self._has_unsaved_changes

    def trigger_search(self, query: str) -> None:
        """
        Trigger a citation search.

        Args:
            query: Search query
        """
        self.search_panel.set_search_query(query)
        self.search_panel.search(query)
        self.right_tabs.setCurrentIndex(0)

    def _load_most_recent_document(self) -> None:
        """
        Load the most recently edited document on startup.

        This allows users to continue where they left off without
        needing to manually open their previous work.
        """
        try:
            document = self._document_store.get_most_recent_document()
            if document:
                self._document = document
                self.editor.setPlainText(document.content)
                self.title_input.setText(document.title)
                self._has_unsaved_changes = False
                self._update_unsaved_indicator()

                # Update citation manager with loaded content
                self._citation_manager.update_text(document.content)

                # Update word count
                words = len(document.content.split())
                self.word_label.setText(f"Words: {words:,}")

                logger.info(f"Loaded most recent document: {document.id} - {document.title}")
            else:
                logger.debug("No existing documents found, starting with blank document")
        except Exception as e:
            # Don't fail startup if we can't load - just log and continue with blank
            logger.warning(f"Could not load most recent document: {e}")

    def _add_reference_entry(self, document_id: int) -> None:
        """
        Add a reference entry to the References section.

        If no References section exists, one is created at the end of the document.
        The reference entry is appended as a bullet point.

        Args:
            document_id: Database document ID
        """
        import re

        text = self.editor.toPlainText()
        reference_entry = self._citation_manager.generate_reference_entry(document_id)

        # Find the References section
        references_pattern = r'^## References\s*$'
        match = re.search(references_pattern, text, re.MULTILINE)

        if match:
            # References section exists - find where to append
            # Look for the end of the references section (next heading or end of doc)
            section_start = match.end()

            # Find the next heading (## or higher) after References
            next_heading = re.search(r'^##?\s+\w', text[section_start:], re.MULTILINE)

            if next_heading:
                # Insert before the next heading
                insert_position = section_start + next_heading.start()
                # Insert with proper spacing
                new_text = text[:insert_position].rstrip() + "\n" + reference_entry + "\n\n" + text[insert_position:]
            else:
                # Append to end of document
                new_text = text.rstrip() + "\n" + reference_entry + "\n"
        else:
            # No References section - create one at the end
            new_text = text.rstrip() + "\n\n## References\n\n" + reference_entry + "\n"

        # Update editor without triggering cursor position changes
        cursor = self.editor.textCursor()
        cursor_pos = cursor.position()

        self.editor.setPlainText(new_text)

        # Restore cursor position (may have shifted slightly)
        cursor = self.editor.textCursor()
        cursor.setPosition(min(cursor_pos, len(new_text)))
        self.editor.setTextCursor(cursor)

    def _strip_references_section(self, text: str) -> str:
        """
        Remove the ## References section from text for export formatting.

        The reference builder will regenerate a properly numbered
        reference list during export.

        Args:
            text: Document text with ## References section

        Returns:
            Text with References section removed
        """
        import re

        # Find the References section
        references_pattern = r'^## References\s*$'
        match = re.search(references_pattern, text, re.MULTILINE)

        if not match:
            return text

        section_start = match.start()

        # Find the next heading (## or higher) after References
        next_heading = re.search(r'^##?\s+\w', text[match.end():], re.MULTILINE)

        if next_heading:
            # Remove only the References section
            section_end = match.end() + next_heading.start()
            return text[:section_start].rstrip() + "\n\n" + text[section_end:].lstrip()
        else:
            # References is at the end - remove to end of document
            return text[:section_start].rstrip()
