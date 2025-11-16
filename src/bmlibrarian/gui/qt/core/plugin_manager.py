"""Plugin manager for loading and managing tab plugins.

This module provides the PluginManager class which handles discovery, loading,
and lifecycle management of tab plugins.
"""

from typing import Dict, List, Optional
from pathlib import Path
import importlib
import importlib.util
import sys
import logging

from .tab_registry import TabRegistry, DependencyError, CircularDependencyError
from ..plugins.base_tab import BaseTabPlugin, TabPluginMetadata


class PluginLoadError(Exception):
    """Raised when a plugin fails to load."""
    pass


class PluginManager:
    """Manages loading, registration, and lifecycle of tab plugins.

    This class handles:
    - Plugin discovery in the plugins directory
    - Dynamic loading of plugin modules
    - Registration with TabRegistry
    - Dependency resolution and load ordering
    - Error handling for failed plugins
    - Plugin unloading and cleanup

    Error Handling:
    - Missing plugin files: Logged as warnings, continue loading others
    - Import errors: Logged with full traceback, skip plugin
    - Dependency errors: Reported to user, suggest load order
    - Circular dependencies: Detected and reported before loading
    """

    def __init__(self, registry: TabRegistry):
        """Initialize the plugin manager.

        Args:
            registry: TabRegistry instance for plugin registration
        """
        self.registry = registry
        self.loaded_plugins: Dict[str, BaseTabPlugin] = {}
        self.plugin_path = Path(__file__).parent.parent / "plugins"
        self.logger = logging.getLogger("bmlibrarian.gui.qt.core.PluginManager")

        # Track failed plugins to avoid retry loops
        self._failed_plugins: Dict[str, str] = {}  # plugin_id -> error_message

    def discover_plugins(self) -> List[str]:
        """Discover available plugins in the plugins directory.

        Scans the plugins directory for subdirectories containing a plugin.py file.
        Each such directory is considered a potential plugin.

        Returns:
            List[str]: List of discovered plugin directory names

        Example:
            If plugins/ contains:
                research/plugin.py -> returns ["research"]
                search/plugin.py -> returns ["research", "search"]
                example/ (no plugin.py) -> not included
        """
        discovered = []

        if not self.plugin_path.exists():
            self.logger.warning(f"Plugin directory not found: {self.plugin_path}")
            return discovered

        for plugin_dir in self.plugin_path.iterdir():
            # Skip __pycache__ and other special directories
            if plugin_dir.name.startswith('_') or plugin_dir.name.startswith('.'):
                continue

            if plugin_dir.is_dir():
                plugin_file = plugin_dir / "plugin.py"
                if plugin_file.exists():
                    discovered.append(plugin_dir.name)
                    self.logger.debug(f"Discovered plugin: {plugin_dir.name}")
                else:
                    self.logger.debug(
                        f"Skipping {plugin_dir.name} - no plugin.py found"
                    )

        self.logger.info(f"Discovered {len(discovered)} plugins: {discovered}")
        return discovered

    def load_plugin(self, plugin_id: str) -> Optional[BaseTabPlugin]:
        """Load a plugin by ID.

        This method:
        1. Checks if plugin is already loaded
        2. Checks if plugin previously failed to load
        3. Dynamically imports the plugin module
        4. Calls create_plugin() to instantiate the plugin
        5. Validates the plugin implements BaseTabPlugin
        6. Registers the plugin with TabRegistry
        7. Stores the plugin in loaded_plugins

        Args:
            plugin_id: ID/directory name of the plugin to load

        Returns:
            Optional[BaseTabPlugin]: The loaded plugin instance, or None if loading failed

        Raises:
            PluginLoadError: If the plugin cannot be loaded (details in message)

        Error Handling:
        - Already loaded: Returns cached instance
        - Previously failed: Returns None, logs warning
        - File not found: Raises PluginLoadError
        - Import error: Raises PluginLoadError with traceback
        - Missing create_plugin(): Raises PluginLoadError
        - Invalid plugin type: Raises PluginLoadError
        - Dependency error: Raises PluginLoadError
        """
        # Check if already loaded
        if plugin_id in self.loaded_plugins:
            self.logger.debug(f"Plugin '{plugin_id}' already loaded")
            return self.loaded_plugins[plugin_id]

        # Check if previously failed
        if plugin_id in self._failed_plugins:
            self.logger.warning(
                f"Plugin '{plugin_id}' previously failed to load: "
                f"{self._failed_plugins[plugin_id]}"
            )
            return None

        plugin_file = self.plugin_path / plugin_id / "plugin.py"

        # Check if plugin file exists
        if not plugin_file.exists():
            error_msg = f"Plugin file not found: {plugin_file}"
            self.logger.error(error_msg)
            self._failed_plugins[plugin_id] = error_msg
            raise PluginLoadError(error_msg)

        try:
            # Dynamic import of plugin module
            module_name = f"bmlibrarian.gui.qt.plugins.{plugin_id}.plugin"
            spec = importlib.util.spec_from_file_location(module_name, plugin_file)

            if spec is None or spec.loader is None:
                error_msg = f"Failed to create module spec for plugin '{plugin_id}'"
                self.logger.error(error_msg)
                self._failed_plugins[plugin_id] = error_msg
                raise PluginLoadError(error_msg)

            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            # Check for create_plugin() function
            if not hasattr(module, "create_plugin"):
                error_msg = (
                    f"Plugin '{plugin_id}' missing create_plugin() function. "
                    f"Each plugin.py must have: def create_plugin() -> BaseTabPlugin"
                )
                self.logger.error(error_msg)
                self._failed_plugins[plugin_id] = error_msg
                raise PluginLoadError(error_msg)

            # Instantiate plugin
            plugin = module.create_plugin()

            # Validate plugin type
            if not isinstance(plugin, BaseTabPlugin):
                error_msg = (
                    f"Plugin '{plugin_id}' create_plugin() returned "
                    f"{type(plugin).__name__}, expected BaseTabPlugin subclass"
                )
                self.logger.error(error_msg)
                self._failed_plugins[plugin_id] = error_msg
                raise PluginLoadError(error_msg)

            # Get metadata for validation
            metadata = plugin.get_metadata()
            if metadata.plugin_id != plugin_id:
                self.logger.warning(
                    f"Plugin directory name '{plugin_id}' does not match "
                    f"metadata plugin_id '{metadata.plugin_id}'. "
                    f"Using metadata plugin_id."
                )

            # Register with registry (this validates dependencies)
            try:
                self.registry.register(plugin)
            except (DependencyError, CircularDependencyError) as e:
                error_msg = f"Dependency error loading plugin '{plugin_id}': {e}"
                self.logger.error(error_msg)
                self._failed_plugins[plugin_id] = error_msg
                raise PluginLoadError(error_msg) from e

            # Store in loaded plugins (use metadata plugin_id)
            self.loaded_plugins[metadata.plugin_id] = plugin

            self.logger.info(
                f"Successfully loaded plugin '{metadata.plugin_id}' "
                f"v{metadata.version}"
            )

            return plugin

        except ImportError as e:
            error_msg = f"Import error loading plugin '{plugin_id}': {e}"
            self.logger.error(error_msg, exc_info=True)
            self._failed_plugins[plugin_id] = str(e)
            raise PluginLoadError(error_msg) from e

        except Exception as e:
            error_msg = f"Unexpected error loading plugin '{plugin_id}': {e}"
            self.logger.error(error_msg, exc_info=True)
            self._failed_plugins[plugin_id] = str(e)
            raise PluginLoadError(error_msg) from e

    def load_enabled_plugins(
        self, enabled_list: List[str], continue_on_error: bool = True
    ) -> Dict[str, BaseTabPlugin]:
        """Load all enabled plugins from configuration.

        This method attempts to load plugins in dependency order to ensure
        that required plugins are loaded before plugins that depend on them.

        Args:
            enabled_list: List of plugin IDs to load
            continue_on_error: If True, continue loading other plugins after
                             failures. If False, stop on first error.

        Returns:
            Dict[str, BaseTabPlugin]: Successfully loaded plugins (plugin_id -> instance)

        Note:
            - Failed plugins are logged but don't stop the process if continue_on_error=True
            - Dependency ordering is attempted but may not be perfect if plugins aren't
              registered yet
        """
        loaded = {}
        failed = []

        self.logger.info(f"Loading {len(enabled_list)} enabled plugins...")

        for plugin_id in enabled_list:
            try:
                plugin = self.load_plugin(plugin_id)
                if plugin:
                    metadata = plugin.get_metadata()
                    loaded[metadata.plugin_id] = plugin
            except PluginLoadError as e:
                failed.append(plugin_id)
                self.logger.warning(f"Failed to load plugin '{plugin_id}': {e}")
                if not continue_on_error:
                    raise

        self.logger.info(
            f"Plugin loading complete: {len(loaded)} succeeded, {len(failed)} failed"
        )

        if failed:
            self.logger.warning(f"Failed plugins: {failed}")

        return loaded

    def unload_plugin(self, plugin_id: str):
        """Unload a plugin and cleanup resources.

        This method:
        1. Calls plugin.cleanup() to release resources
        2. Unregisters from TabRegistry
        3. Removes from loaded_plugins
        4. Optionally removes from sys.modules (for hot reload)

        Args:
            plugin_id: ID of plugin to unload

        Note:
            This does NOT check if other plugins depend on it.
            Use registry.check_dependents() first if needed.
        """
        if plugin_id not in self.loaded_plugins:
            self.logger.warning(f"Plugin '{plugin_id}' not loaded, cannot unload")
            return

        plugin = self.loaded_plugins[plugin_id]

        # Cleanup plugin resources
        try:
            plugin.cleanup()
            self.logger.debug(f"Cleaned up plugin '{plugin_id}'")
        except Exception as e:
            self.logger.error(
                f"Error during cleanup of plugin '{plugin_id}': {e}",
                exc_info=True
            )

        # Unregister from registry
        try:
            self.registry.unregister(plugin_id)
        except Exception as e:
            self.logger.error(
                f"Error unregistering plugin '{plugin_id}': {e}",
                exc_info=True
            )

        # Remove from loaded plugins
        del self.loaded_plugins[plugin_id]

        self.logger.info(f"Unloaded plugin '{plugin_id}'")

    def reload_plugin(self, plugin_id: str) -> Optional[BaseTabPlugin]:
        """Reload a plugin (for development).

        This is useful during development to reload a plugin after code changes
        without restarting the application.

        Args:
            plugin_id: ID of plugin to reload

        Returns:
            Optional[BaseTabPlugin]: Reloaded plugin instance or None if failed

        Warning:
            Hot reloading can cause issues with Qt objects. Use with caution.
        """
        # Unload if currently loaded
        if plugin_id in self.loaded_plugins:
            self.unload_plugin(plugin_id)

        # Clear from failed plugins to allow retry
        if plugin_id in self._failed_plugins:
            del self._failed_plugins[plugin_id]

        # Clear module cache
        module_name = f"bmlibrarian.gui.qt.plugins.{plugin_id}.plugin"
        if module_name in sys.modules:
            del sys.modules[module_name]
            self.logger.debug(f"Cleared module cache for '{plugin_id}'")

        # Reload
        try:
            return self.load_plugin(plugin_id)
        except PluginLoadError as e:
            self.logger.error(f"Failed to reload plugin '{plugin_id}': {e}")
            return None

    def get_plugin_info(self, plugin_id: str) -> Optional[Dict[str, any]]:
        """Get information about a plugin.

        Args:
            plugin_id: ID of plugin

        Returns:
            Dict with plugin information or None if not loaded
        """
        if plugin_id not in self.loaded_plugins:
            return None

        plugin = self.loaded_plugins[plugin_id]
        metadata = plugin.get_metadata()

        return {
            "plugin_id": metadata.plugin_id,
            "display_name": metadata.display_name,
            "description": metadata.description,
            "version": metadata.version,
            "icon": metadata.icon,
            "requires": metadata.requires,
            "is_active": plugin.is_active(),
            "has_widget": plugin.get_widget() is not None,
        }

    def get_failed_plugins(self) -> Dict[str, str]:
        """Get dictionary of failed plugins and their error messages.

        Returns:
            Dict[str, str]: plugin_id -> error_message
        """
        return self._failed_plugins.copy()

    def clear_failed_plugins(self):
        """Clear the failed plugins cache.

        This allows retry attempts for plugins that previously failed to load.
        """
        self._failed_plugins.clear()
        self.logger.debug("Cleared failed plugins cache")
