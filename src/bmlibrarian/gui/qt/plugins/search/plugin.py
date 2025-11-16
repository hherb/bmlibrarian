"""
Search Plugin for BMLibrarian Qt GUI.

Provides an advanced document search interface with filters and results visualization.
"""

from PySide6.QtWidgets import QWidget
from typing import Optional

from ..base_tab import BaseTabPlugin, TabPluginMetadata
from .search_tab import SearchTabWidget


class SearchPlugin(BaseTabPlugin):
    """Plugin for advanced document search interface."""

    def __init__(self):
        """Initialize Search plugin."""
        super().__init__()
        self.tab_widget: Optional[SearchTabWidget] = None

    def get_metadata(self) -> TabPluginMetadata:
        """
        Get plugin metadata.

        Returns:
            Plugin metadata including ID, name, and description
        """
        return TabPluginMetadata(
            plugin_id="search",
            display_name="Document Search",
            description="Advanced document search with filters and results visualization",
            version="1.0.0",
            icon="search",
            requires=[]
        )

    def create_widget(self, parent: Optional[QWidget] = None) -> QWidget:
        """
        Create the main widget for this tab.

        Args:
            parent: Optional parent widget

        Returns:
            Main Search tab widget
        """
        self.tab_widget = SearchTabWidget(parent)

        # Connect signals
        self.tab_widget.status_message.connect(
            lambda msg: self.status_changed.emit(msg)
        )

        return self.tab_widget

    def on_tab_activated(self):
        """Called when this tab becomes active."""
        self.status_changed.emit("Document Search activated - Ready to search")

    def on_tab_deactivated(self):
        """Called when this tab is deactivated."""
        pass

    def cleanup(self):
        """Cleanup resources when plugin is unloaded."""
        if self.tab_widget:
            self.tab_widget.cleanup()


def create_plugin() -> BaseTabPlugin:
    """
    Plugin factory function.

    Returns:
        Initialized SearchPlugin instance
    """
    return SearchPlugin()
