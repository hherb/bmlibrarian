"""
Fact-Checker Review Plugin Entry Point.
"""

from typing import Optional
from PySide6.QtWidgets import QWidget
from ..base_tab import BaseTabPlugin, TabPluginMetadata
from .fact_checker_tab import FactCheckerTabWidget


class FactCheckerPlugin(BaseTabPlugin):
    """Fact-checker review tab plugin."""

    def __init__(self):
        """Initialize the plugin."""
        super().__init__()
        self._widget: Optional[FactCheckerTabWidget] = None

    def get_metadata(self) -> TabPluginMetadata:
        """Return plugin metadata."""
        return TabPluginMetadata(
            plugin_id="fact_checker",
            display_name="Fact Checker",
            description="Review and annotate fact-checking results",
            version="1.0.0",
            icon=None,
            requires=[]
        )

    def create_widget(self, parent: Optional[QWidget] = None) -> QWidget:
        """Create and return the main widget for this tab."""
        if self._widget is None:
            self._widget = FactCheckerTabWidget(parent)
            # Connect widget signals to plugin signals
            self._widget.status_changed.connect(self.status_changed.emit)
        return self._widget

    def on_tab_activated(self):
        """Called when this tab becomes active."""
        if self._widget:
            self._widget.on_activated()
        self.status_changed.emit("Fact Checker tab activated")

    def on_tab_deactivated(self):
        """Called when this tab is deactivated."""
        if self._widget:
            self._widget.on_deactivated()

    def cleanup(self):
        """Cleanup resources when plugin is unloaded."""
        if self._widget:
            self._widget.cleanup()
            self._widget = None


def create_plugin() -> BaseTabPlugin:
    """Plugin entry point."""
    return FactCheckerPlugin()
