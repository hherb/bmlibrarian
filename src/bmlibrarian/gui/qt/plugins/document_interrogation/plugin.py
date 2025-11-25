"""
Document Interrogation Plugin for BMLibrarian Qt GUI.

Provides an interactive interface for asking questions about documents
using the DocumentInterrogationAgent with sliding window chunk processing.
"""

from PySide6.QtWidgets import QWidget
from typing import Optional

from ..base_tab import BaseTabPlugin, TabPluginMetadata
from .document_interrogation_tab import DocumentInterrogationTabWidget
from ...core.document_receiver_registry import DocumentReceiverRegistry


class DocumentInterrogationPlugin(BaseTabPlugin):
    """Plugin for Document Interrogation interface."""

    def __init__(self):
        """Initialize Document Interrogation plugin."""
        super().__init__()
        self.tab_widget: Optional[DocumentInterrogationTabWidget] = None

    def get_metadata(self) -> TabPluginMetadata:
        """
        Get plugin metadata.

        Returns:
            Plugin metadata including ID, name, and description
        """
        return TabPluginMetadata(
            plugin_id="document_interrogation",
            display_name="Document Interrogation",
            description="Interactive document viewer with AI chat interface for asking questions about PDFs and Markdown files",
            version="1.0.0",
            icon="document",
            requires=[]
        )

    def create_widget(self, parent: Optional[QWidget] = None) -> QWidget:
        """
        Create the main widget for this tab.

        Args:
            parent: Optional parent widget

        Returns:
            Main Document Interrogation tab widget
        """
        self.tab_widget = DocumentInterrogationTabWidget(parent)

        # Connect signals
        self.tab_widget.status_message.connect(
            lambda msg: self.status_changed.emit(msg)
        )

        # Register as document receiver
        registry = DocumentReceiverRegistry()
        registry.register_receiver(self.tab_widget)

        return self.tab_widget

    def on_tab_activated(self):
        """Called when this tab becomes active."""
        self.status_changed.emit("Document Interrogation activated - Load a document to get started")

    def on_tab_deactivated(self):
        """Called when this tab is deactivated."""
        pass

    def cleanup(self):
        """Cleanup resources when plugin is unloaded."""
        # Unregister from document receiver registry
        if self.tab_widget:
            registry = DocumentReceiverRegistry()
            registry.unregister_receiver(self.tab_widget.get_receiver_id())
            self.tab_widget.cleanup()


def create_plugin() -> BaseTabPlugin:
    """
    Plugin factory function.

    Returns:
        Initialized DocumentInterrogationPlugin instance
    """
    return DocumentInterrogationPlugin()
