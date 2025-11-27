"""
Writing Plugin for BMLibrarian Qt GUI.

Provides a citation-aware markdown editor for academic writing with:
- Markdown syntax highlighting
- Citation management ([@id:12345:Label] format)
- Semantic search for finding references
- Multiple citation styles (Vancouver, APA, Harvard, Chicago)
- Autosave with version history
- Export with formatted reference lists
"""

import logging
from typing import Optional

from PySide6.QtWidgets import QWidget

from ..base_tab import BaseTabPlugin, TabPluginMetadata
from ...widgets.citation_editor import CitationEditorWidget

logger = logging.getLogger(__name__)


class WritingPlugin(BaseTabPlugin):
    """Plugin for Citation-Aware Markdown Editor."""

    def __init__(self) -> None:
        """Initialize Writing plugin."""
        super().__init__()
        self.tab_widget: Optional[CitationEditorWidget] = None

    def get_metadata(self) -> TabPluginMetadata:
        """
        Get plugin metadata.

        Returns:
            Plugin metadata including ID, name, and description
        """
        return TabPluginMetadata(
            plugin_id="writing",
            display_name="Writing",
            description="Citation-aware markdown editor for academic writing with semantic search integration",
            version="1.0.0",
            icon="edit",
            requires=[]
        )

    def create_widget(self, parent: Optional[QWidget] = None) -> QWidget:
        """
        Create the main widget for this tab.

        Args:
            parent: Optional parent widget

        Returns:
            Main Citation Editor widget
        """
        self.tab_widget = CitationEditorWidget(parent)

        # Connect signals
        self.tab_widget.document_saved.connect(self._on_document_saved)
        self.tab_widget.document_exported.connect(self._on_document_exported)
        self.tab_widget.unsaved_changes.connect(self._on_unsaved_changes)

        return self.tab_widget

    def on_tab_activated(self) -> None:
        """Called when this tab becomes active."""
        self._is_active = True
        self.status_changed.emit("Writing - Citation-aware markdown editor")

    def on_tab_deactivated(self) -> None:
        """Called when this tab is deactivated."""
        self._is_active = False

    def cleanup(self) -> None:
        """Cleanup resources when plugin is unloaded."""
        if self.tab_widget:
            # Check for unsaved changes
            if self.tab_widget.has_unsaved_changes():
                logger.warning("Writing plugin has unsaved changes during cleanup")

        super().cleanup()

    def _on_document_saved(self, document_id: int) -> None:
        """
        Handle document saved event.

        Args:
            document_id: ID of saved document
        """
        self.status_changed.emit(f"Document saved (ID: {document_id})")
        logger.info(f"Document saved: {document_id}")

    def _on_document_exported(self, path: str) -> None:
        """
        Handle document exported event.

        Args:
            path: Export file path
        """
        self.status_changed.emit(f"Document exported: {path}")
        logger.info(f"Document exported to: {path}")

    def _on_unsaved_changes(self, has_changes: bool) -> None:
        """
        Handle unsaved changes status.

        Args:
            has_changes: True if there are unsaved changes
        """
        if has_changes:
            self.status_changed.emit("Writing - Unsaved changes")

    # Public API for external integration

    def trigger_search(self, query: str) -> None:
        """
        Trigger a citation search from external source.

        Args:
            query: Search query
        """
        if self.tab_widget:
            self.tab_widget.trigger_search(query)

    def set_content(self, content: str) -> None:
        """
        Set editor content from external source.

        Args:
            content: Markdown content to set
        """
        if self.tab_widget:
            self.tab_widget.set_content(content)

    def get_content(self) -> str:
        """
        Get current editor content.

        Returns:
            Current markdown content
        """
        if self.tab_widget:
            return self.tab_widget.get_content()
        return ""

    def load_document(self, document_id: int) -> bool:
        """
        Load a writing document by ID.

        Args:
            document_id: Document database ID

        Returns:
            True if loaded successfully
        """
        if self.tab_widget:
            return self.tab_widget.load_document(document_id)
        return False


def create_plugin() -> BaseTabPlugin:
    """
    Plugin factory function.

    Returns:
        Initialized WritingPlugin instance
    """
    return WritingPlugin()
