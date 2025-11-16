"""
Base tab plugin interface for BMLibrarian Qt GUI.

This module defines the abstract base class that all tab plugins must implement.
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import QObject, Signal


class TabPluginMetadata:
    """Metadata for a tab plugin."""

    def __init__(
        self,
        plugin_id: str,
        display_name: str,
        description: str,
        version: str,
        icon: Optional[str] = None,
        requires: Optional[list[str]] = None,
    ):
        """
        Initialize plugin metadata.

        Args:
            plugin_id: Unique identifier for the plugin (e.g., "research")
            display_name: Human-readable name displayed in tab (e.g., "Research")
            description: Brief description of plugin functionality
            version: Plugin version string (e.g., "1.0.0")
            icon: Optional path to icon file
            requires: Optional list of required plugin IDs
        """
        self.plugin_id = plugin_id
        self.display_name = display_name
        self.description = description
        self.version = version
        self.icon = icon
        self.requires = requires or []


class BaseTabPlugin(QObject, ABC):
    """Abstract base class for all tab plugins."""

    # Signals for inter-tab communication
    request_navigation = Signal(str)  # Navigate to another tab
    status_changed = Signal(str)  # Update status bar
    data_updated = Signal(dict)  # Share data with other tabs

    def __init__(self):
        """Initialize the base plugin."""
        super().__init__()

    @abstractmethod
    def get_metadata(self) -> TabPluginMetadata:
        """
        Return plugin metadata.

        Returns:
            TabPluginMetadata instance with plugin information
        """
        pass

    @abstractmethod
    def create_widget(self, parent: Optional[QWidget] = None) -> QWidget:
        """
        Create and return the main widget for this tab.

        Args:
            parent: Optional parent widget

        Returns:
            QWidget instance for the tab content
        """
        pass

    @abstractmethod
    def on_tab_activated(self):
        """
        Called when this tab becomes active.

        Override to refresh data, start timers, etc.
        """
        pass

    @abstractmethod
    def on_tab_deactivated(self):
        """
        Called when this tab is deactivated.

        Override to pause operations, stop timers, etc.
        """
        pass

    def get_config(self) -> Dict[str, Any]:
        """
        Get plugin-specific configuration.

        Returns:
            Dictionary of configuration values
        """
        return {}

    def set_config(self, config: Dict[str, Any]):
        """
        Update plugin configuration.

        Args:
            config: Dictionary of configuration values to update
        """
        pass

    def cleanup(self):
        """
        Cleanup resources when plugin is unloaded.

        Override to release resources, close connections, etc.
        """
        pass
