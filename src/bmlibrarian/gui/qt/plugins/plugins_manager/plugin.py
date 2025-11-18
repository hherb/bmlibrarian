"""Plugins Manager plugin for managing BMLibrarian Qt GUI plugins.

This plugin provides a graphical interface for:
- Viewing all available plugins (discovered and loaded)
- Enabling/disabling plugins
- Viewing plugin metadata and descriptions
- Managing plugin load order
"""

from PySide6.QtWidgets import QWidget
from typing import Dict, Any

from ..base_tab import BaseTabPlugin, TabPluginMetadata
from .plugins_manager_tab import PluginsManagerTab


class PluginsManagerPlugin(BaseTabPlugin):
    """Plugin manager tab plugin.

    This plugin provides a UI for managing other plugins including viewing
    available plugins, enabling/disabling them, and viewing their metadata.
    """

    def __init__(self):
        """Initialize the plugins manager plugin."""
        super().__init__()
        self.widget = None

    def get_metadata(self) -> TabPluginMetadata:
        """Return plugin metadata.

        Returns:
            TabPluginMetadata: Metadata describing this plugin
        """
        return TabPluginMetadata(
            plugin_id="plugins_manager",
            display_name="Plugins",
            description="Manage BMLibrarian Qt GUI plugins",
            version="1.0.0",
            icon=None,
            requires=[]  # No dependencies
        )

    def create_widget(self, parent=None) -> QWidget:
        """Create the plugins manager tab widget.

        Args:
            parent: Parent widget

        Returns:
            QWidget: The plugins manager widget
        """
        self.widget = PluginsManagerTab(self, parent)
        return self.widget

    def on_tab_activated(self):
        """Called when this tab becomes active."""
        self.status_changed.emit("Plugins manager activated")
        self._is_active = True
        if self.widget:
            self.widget.on_activated()

    def on_tab_deactivated(self):
        """Called when this tab is deactivated."""
        self._is_active = False
        if self.widget:
            self.widget.on_deactivated()

    def get_config(self) -> Dict[str, Any]:
        """Get plugin configuration.

        Returns:
            Dict[str, Any]: Configuration dictionary
        """
        return {
            "show_descriptions": True,
            "show_versions": True
        }

    def set_config(self, config: Dict[str, Any]):
        """Update plugin configuration.

        Args:
            config: New configuration dictionary
        """
        self.logger.info(f"Configuration updated: {config}")
        # Could update widget behavior here if needed

    def cleanup(self):
        """Cleanup resources when plugin is unloaded."""
        self.logger.debug("Cleaning up plugins manager plugin")

        if self.widget:
            self.widget = None

        # Call parent cleanup
        super().cleanup()


def create_plugin() -> BaseTabPlugin:
    """Plugin entry point.

    This function is called by the PluginManager to instantiate the plugin.

    Returns:
        BaseTabPlugin: The plugins manager plugin instance
    """
    return PluginsManagerPlugin()
