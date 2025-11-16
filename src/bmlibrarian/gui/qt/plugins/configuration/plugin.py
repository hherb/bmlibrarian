"""
Configuration plugin for BMLibrarian Qt GUI.

Provides settings and configuration interface for agents and system settings.
"""

from ...plugins.base_tab import BaseTabPlugin, TabPluginMetadata
from .config_tab import ConfigurationTabWidget
from PySide6.QtWidgets import QWidget
from typing import Optional


class ConfigurationPlugin(BaseTabPlugin):
    """
    Configuration plugin.

    Implements the settings interface with:
    - General settings (Ollama, database)
    - Agent configuration (models, parameters)
    - Query generation settings
    - Connection testing
    """

    def __init__(self):
        """Initialize configuration plugin."""
        super().__init__()
        self.config_widget: Optional[ConfigurationTabWidget] = None

    def get_metadata(self) -> TabPluginMetadata:
        """
        Get plugin metadata.

        Returns:
            Plugin metadata
        """
        return TabPluginMetadata(
            plugin_id="configuration",
            display_name="Configuration",
            description="System and agent configuration settings",
            version="1.0.0",
            icon=None,  # TODO: Add settings icon
        )

    def create_widget(self, parent: Optional[QWidget] = None) -> QWidget:
        """
        Create the configuration tab widget.

        Args:
            parent: Optional parent widget

        Returns:
            Configuration tab widget instance
        """
        self.config_widget = ConfigurationTabWidget(parent)

        # Connect widget signals to plugin signals
        self.config_widget.status_message.connect(
            lambda msg: self.status_changed.emit(msg)
        )

        return self.config_widget

    def on_tab_activated(self):
        """Called when configuration tab becomes active."""
        self.status_changed.emit("Configuration tab activated")

        # Refresh configuration if needed
        if self.config_widget:
            self.config_widget.refresh_models()

    def on_tab_deactivated(self):
        """Called when configuration tab is deactivated."""
        pass

    def cleanup(self):
        """Cleanup resources."""
        # Save any pending changes
        if self.config_widget:
            # Could auto-save or prompt user
            pass


def create_plugin() -> BaseTabPlugin:
    """
    Plugin factory function.

    Returns:
        ConfigurationPlugin instance
    """
    return ConfigurationPlugin()
