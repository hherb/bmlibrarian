"""
Query Lab Plugin for BMLibrarian Qt GUI.

Provides an interactive interface for experimenting with QueryAgent
and natural language to PostgreSQL query conversion.
"""

from PySide6.QtWidgets import QWidget
from typing import Optional

from ..base_tab import BaseTabPlugin, TabPluginMetadata
from .query_lab_tab import QueryLabTabWidget


class QueryLabPlugin(BaseTabPlugin):
    """Plugin for Query Laboratory interface."""

    def __init__(self):
        """Initialize Query Lab plugin."""
        super().__init__()
        self.tab_widget: Optional[QueryLabTabWidget] = None

    def get_metadata(self) -> TabPluginMetadata:
        """
        Get plugin metadata.

        Returns:
            Plugin metadata including ID, name, and description
        """
        return TabPluginMetadata(
            plugin_id="query_lab",
            display_name="Query Lab",
            description="Interactive laboratory for experimenting with natural language to PostgreSQL query conversion",
            version="1.0.0",
            icon="experiment",
            requires=[]
        )

    def create_widget(self, parent: Optional[QWidget] = None) -> QWidget:
        """
        Create the main widget for this tab.

        Args:
            parent: Optional parent widget

        Returns:
            Main Query Lab tab widget
        """
        self.tab_widget = QueryLabTabWidget(parent)

        # Connect signals
        self.tab_widget.status_message.connect(
            lambda msg: self.status_changed.emit(msg)
        )

        return self.tab_widget

    def on_tab_activated(self):
        """Called when this tab becomes active."""
        self.status_changed.emit("Query Lab activated - Ready to generate queries")

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
        Initialized QueryLabPlugin instance
    """
    return QueryLabPlugin()
