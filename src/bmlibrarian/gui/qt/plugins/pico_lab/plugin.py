"""
PICO Lab Plugin for BMLibrarian Qt GUI.

Provides an interactive interface for extracting PICO (Population, Intervention,
Comparison, Outcome) components from biomedical research papers.
"""

from PySide6.QtWidgets import QWidget
from typing import Optional

from ..base_tab import BaseTabPlugin, TabPluginMetadata
from .pico_lab_tab import PICOLabTabWidget


class PICOLabPlugin(BaseTabPlugin):
    """Plugin for PICO Laboratory interface."""

    def __init__(self):
        """Initialize PICO Lab plugin."""
        super().__init__()
        self.tab_widget: Optional[PICOLabTabWidget] = None

    def get_metadata(self) -> TabPluginMetadata:
        """
        Get plugin metadata.

        Returns:
            Plugin metadata including ID, name, and description
        """
        return TabPluginMetadata(
            plugin_id="pico_lab",
            display_name="PICO Lab",
            description="Interactive laboratory for extracting PICO components from research papers",
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
            Main PICO Lab tab widget
        """
        self.tab_widget = PICOLabTabWidget(parent)

        # Connect signals
        self.tab_widget.status_message.connect(
            lambda msg: self.status_changed.emit(msg)
        )

        return self.tab_widget

    def on_tab_activated(self):
        """Called when this tab becomes active."""
        self.status_changed.emit("PICO Lab activated - Ready to analyze documents")

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
        Initialized PICOLabPlugin instance
    """
    return PICOLabPlugin()
