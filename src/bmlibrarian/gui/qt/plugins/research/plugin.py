"""
Research plugin for BMLibrarian Qt GUI.

Provides research workflow interface with agent orchestration.
"""

from ...plugins.base_tab import BaseTabPlugin, TabPluginMetadata
from .research_tab import ResearchTabWidget
from PySide6.QtWidgets import QWidget
from typing import Optional


class ResearchPlugin(BaseTabPlugin):
    """
    Research workflow plugin.

    Implements the main research interface with:
    - Research question input
    - Multi-agent workflow execution
    - Document and citation display
    - Report generation and preview
    """

    def __init__(self):
        """Initialize research plugin."""
        super().__init__()
        self.research_widget: Optional[ResearchTabWidget] = None

    def get_metadata(self) -> TabPluginMetadata:
        """
        Get plugin metadata.

        Returns:
            Plugin metadata
        """
        return TabPluginMetadata(
            plugin_id="research",
            display_name="Research",
            description="Biomedical literature research workflow",
            version="1.0.0",
            icon=None,  # TODO: Add icon
        )

    def create_widget(self, parent: Optional[QWidget] = None) -> QWidget:
        """
        Create the research tab widget.

        Args:
            parent: Optional parent widget (should be main window with agents)

        Returns:
            Research tab widget instance
        """
        # Get agents from parent (main window)
        agents = None
        if parent and hasattr(parent, 'agents'):
            agents = parent.agents

        self.research_widget = ResearchTabWidget(parent=parent, agents=agents)

        # Connect widget signals to plugin signals
        self.research_widget.status_message.connect(
            lambda msg: self.status_changed.emit(msg)
        )

        return self.research_widget

    def on_tab_activated(self):
        """Called when research tab becomes active."""
        self.status_changed.emit("Research tab activated")

        # Refresh UI if needed
        if self.research_widget:
            # Could refresh data, update UI, etc.
            pass

    def on_tab_deactivated(self):
        """Called when research tab is deactivated."""
        # Pause any ongoing operations if needed
        pass

    def cleanup(self):
        """Cleanup resources."""
        # Cancel any ongoing workflows
        if self.research_widget:
            # Could cancel workflows, cleanup threads, etc.
            pass


def create_plugin() -> BaseTabPlugin:
    """
    Plugin factory function.

    Returns:
        ResearchPlugin instance
    """
    return ResearchPlugin()
