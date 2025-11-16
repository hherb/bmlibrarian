"""
Plugin manager for BMLibrarian Qt GUI.

Handles discovery, loading, and lifecycle management of tab plugins.
"""

import importlib
import importlib.util
from pathlib import Path
from typing import Dict, Optional
from .tab_registry import TabRegistry
from ..plugins.base_tab import BaseTabPlugin


class PluginManager:
    """Manages loading, registration, and lifecycle of tab plugins."""

    def __init__(self, registry: TabRegistry):
        """
        Initialize the plugin manager.

        Args:
            registry: Tab registry for plugin registration
        """
        self.registry = registry
        self.loaded_plugins: Dict[str, BaseTabPlugin] = {}
        self.plugin_path = Path(__file__).parent.parent / "plugins"

    def discover_plugins(self) -> list[str]:
        """
        Discover available plugins in the plugins directory.

        Returns:
            List of discovered plugin IDs
        """
        discovered = []

        if not self.plugin_path.exists():
            print(f"Plugin path does not exist: {self.plugin_path}")
            return discovered

        for plugin_dir in self.plugin_path.iterdir():
            if not plugin_dir.is_dir():
                continue

            # Check if plugin.py exists
            plugin_file = plugin_dir / "plugin.py"
            if plugin_file.exists() and plugin_dir.name not in ["__pycache__"]:
                discovered.append(plugin_dir.name)

        return discovered

    def load_plugin(self, plugin_id: str) -> Optional[BaseTabPlugin]:
        """
        Load a plugin by ID.

        Args:
            plugin_id: Plugin ID to load

        Returns:
            Loaded plugin instance or None if loading failed

        Raises:
            ValueError: If plugin not found or invalid
        """
        # Return already loaded plugin
        if plugin_id in self.loaded_plugins:
            return self.loaded_plugins[plugin_id]

        # Check if plugin exists
        plugin_file = self.plugin_path / plugin_id / "plugin.py"
        if not plugin_file.exists():
            raise ValueError(f"Plugin '{plugin_id}' not found at {plugin_file}")

        try:
            # Dynamic import
            module_name = f"bmlibrarian.gui.qt.plugins.{plugin_id}.plugin"
            spec = importlib.util.spec_from_file_location(module_name, plugin_file)

            if spec is None or spec.loader is None:
                raise ValueError(f"Failed to load plugin spec for '{plugin_id}'")

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # Check for create_plugin function
            if not hasattr(module, "create_plugin"):
                raise ValueError(f"Plugin '{plugin_id}' missing create_plugin() function")

            # Create plugin instance
            plugin = module.create_plugin()

            if not isinstance(plugin, BaseTabPlugin):
                raise ValueError(
                    f"Plugin '{plugin_id}' create_plugin() must return BaseTabPlugin instance"
                )

            # Register and store plugin
            self.registry.register(plugin)
            self.loaded_plugins[plugin_id] = plugin

            return plugin

        except Exception as e:
            print(f"Error loading plugin '{plugin_id}': {e}")
            import traceback

            traceback.print_exc()
            return None

    def load_enabled_plugins(self, enabled_list: list[str]) -> Dict[str, BaseTabPlugin]:
        """
        Load all enabled plugins from configuration.

        Args:
            enabled_list: List of plugin IDs to load

        Returns:
            Dictionary mapping plugin IDs to loaded plugin instances
        """
        loaded = {}

        for plugin_id in enabled_list:
            try:
                plugin = self.load_plugin(plugin_id)
                if plugin is not None:
                    loaded[plugin_id] = plugin
            except Exception as e:
                print(f"Failed to load plugin '{plugin_id}': {e}")

        return loaded

    def unload_plugin(self, plugin_id: str):
        """
        Unload a plugin and cleanup resources.

        Args:
            plugin_id: Plugin ID to unload
        """
        if plugin_id in self.loaded_plugins:
            plugin = self.loaded_plugins[plugin_id]

            # Cleanup plugin resources
            try:
                plugin.cleanup()
            except Exception as e:
                print(f"Error during plugin cleanup for '{plugin_id}': {e}")

            # Unregister and remove
            self.registry.unregister(plugin_id)
            del self.loaded_plugins[plugin_id]

    def unload_all_plugins(self):
        """Unload all loaded plugins."""
        # Make a copy of keys since we're modifying the dict
        plugin_ids = list(self.loaded_plugins.keys())
        for plugin_id in plugin_ids:
            self.unload_plugin(plugin_id)

    def reload_plugin(self, plugin_id: str) -> Optional[BaseTabPlugin]:
        """
        Reload a plugin (unload then load).

        Args:
            plugin_id: Plugin ID to reload

        Returns:
            Reloaded plugin instance or None if reloading failed
        """
        self.unload_plugin(plugin_id)
        return self.load_plugin(plugin_id)

    def get_loaded_plugin_ids(self) -> list[str]:
        """
        Get list of loaded plugin IDs.

        Returns:
            List of loaded plugin IDs
        """
        return list(self.loaded_plugins.keys())

    def is_loaded(self, plugin_id: str) -> bool:
        """
        Check if a plugin is loaded.

        Args:
            plugin_id: Plugin ID to check

        Returns:
            True if plugin is loaded, False otherwise
        """
        return plugin_id in self.loaded_plugins
