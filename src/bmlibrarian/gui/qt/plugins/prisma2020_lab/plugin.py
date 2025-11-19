"""
PRISMA 2020 Lab Plugin for BMLibrarian Qt GUI.

Provides an interactive interface for assessing systematic reviews
and meta-analyses against PRISMA 2020 reporting guidelines using
PRISMA2020Agent.
"""

from PySide6.QtWidgets import QWidget
from typing import Optional

from ..base_tab import BaseTabPlugin, TabPluginMetadata
from .prisma2020_lab_tab import PRISMA2020LabTabWidget
from ...core.document_receiver_registry import DocumentReceiverRegistry


class PRISMA2020LabPlugin(BaseTabPlugin):
    """Plugin for PRISMA 2020 Laboratory interface."""

    def __init__(self):
        """Initialize PRISMA 2020 Lab plugin."""
        super().__init__()
        self.tab_widget: Optional[PRISMA2020LabTabWidget] = None

    def get_metadata(self) -> TabPluginMetadata:
        """
        Get plugin metadata.

        Returns:
            Plugin metadata including ID, name, and description
        """
        return TabPluginMetadata(
            plugin_id="prisma2020_lab",
            display_name="PRISMA 2020 Lab",
            description="Interactive laboratory for assessing systematic reviews and meta-analyses against PRISMA 2020 reporting guidelines",
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
            Main PRISMA 2020 Lab tab widget
        """
        self.tab_widget = PRISMA2020LabTabWidget(parent)

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
        self.status_changed.emit("PRISMA 2020 Lab activated - Ready to assess systematic reviews")

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
        Initialized PRISMA2020LabPlugin instance
    """
    return PRISMA2020LabPlugin()
