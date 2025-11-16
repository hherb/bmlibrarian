"""
Tab plugin registry for BMLibrarian Qt GUI.

Manages registration and lookup of tab plugins.
"""

from typing import Dict, Optional
from ..plugins.base_tab import BaseTabPlugin, TabPluginMetadata


class TabRegistry:
    """Registry for managing tab plugins."""

    def __init__(self):
        """Initialize the plugin registry."""
        self._plugins: Dict[str, BaseTabPlugin] = {}
        self._metadata: Dict[str, TabPluginMetadata] = {}

    def register(self, plugin: BaseTabPlugin):
        """
        Register a plugin.

        Args:
            plugin: Plugin instance to register

        Raises:
            ValueError: If plugin ID already registered or metadata invalid
        """
        metadata = plugin.get_metadata()

        if not metadata.plugin_id:
            raise ValueError("Plugin must have a valid plugin_id")

        if metadata.plugin_id in self._plugins:
            raise ValueError(f"Plugin '{metadata.plugin_id}' is already registered")

        self._plugins[metadata.plugin_id] = plugin
        self._metadata[metadata.plugin_id] = metadata

    def unregister(self, plugin_id: str):
        """
        Unregister a plugin.

        Args:
            plugin_id: ID of plugin to unregister
        """
        if plugin_id in self._plugins:
            del self._plugins[plugin_id]
        if plugin_id in self._metadata:
            del self._metadata[plugin_id]

    def get_plugin(self, plugin_id: str) -> Optional[BaseTabPlugin]:
        """
        Get a registered plugin by ID.

        Args:
            plugin_id: Plugin ID to look up

        Returns:
            Plugin instance or None if not found
        """
        return self._plugins.get(plugin_id)

    def get_metadata(self, plugin_id: str) -> Optional[TabPluginMetadata]:
        """
        Get plugin metadata by ID.

        Args:
            plugin_id: Plugin ID to look up

        Returns:
            Plugin metadata or None if not found
        """
        return self._metadata.get(plugin_id)

    def get_all_plugins(self) -> Dict[str, BaseTabPlugin]:
        """
        Get all registered plugins.

        Returns:
            Dictionary mapping plugin IDs to plugin instances
        """
        return dict(self._plugins)

    def get_all_metadata(self) -> Dict[str, TabPluginMetadata]:
        """
        Get all plugin metadata.

        Returns:
            Dictionary mapping plugin IDs to metadata
        """
        return dict(self._metadata)

    def is_registered(self, plugin_id: str) -> bool:
        """
        Check if a plugin is registered.

        Args:
            plugin_id: Plugin ID to check

        Returns:
            True if plugin is registered, False otherwise
        """
        return plugin_id in self._plugins

    def get_plugin_ids(self) -> list[str]:
        """
        Get list of all registered plugin IDs.

        Returns:
            List of plugin IDs
        """
        return list(self._plugins.keys())

    def clear(self):
        """Clear all registered plugins."""
        self._plugins.clear()
        self._metadata.clear()
