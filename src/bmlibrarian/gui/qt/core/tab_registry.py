"""Central registry for all tab plugins.

This module provides the TabRegistry class which maintains a central registry
of all loaded plugins and provides dependency validation.
"""

from typing import Dict, Optional, List, Set
from ..plugins.base_tab import BaseTabPlugin, TabPluginMetadata
import logging


class DependencyError(Exception):
    """Raised when plugin dependencies cannot be satisfied."""
    pass


class CircularDependencyError(DependencyError):
    """Raised when circular dependencies are detected."""
    pass


class TabRegistry:
    """Central registry for all tab plugins.

    This class maintains a registry of all loaded plugins and their metadata,
    providing methods for registration, lookup, and dependency validation.

    Features:
    - Plugin registration and unregistration
    - Metadata lookup
    - Dependency validation
    - Circular dependency detection
    - Plugin listing
    """

    def __init__(self):
        """Initialize an empty registry."""
        self._plugins: Dict[str, BaseTabPlugin] = {}
        self._metadata: Dict[str, TabPluginMetadata] = {}
        self.logger = logging.getLogger("bmlibrarian.gui.qt.core.TabRegistry")

    def register(self, plugin: BaseTabPlugin):
        """Register a plugin.

        Args:
            plugin: The plugin instance to register

        Raises:
            ValueError: If plugin ID is already registered
            DependencyError: If dependencies cannot be satisfied
            CircularDependencyError: If circular dependencies detected
        """
        metadata = plugin.get_metadata()
        plugin_id = metadata.plugin_id

        if plugin_id in self._plugins:
            raise ValueError(f"Plugin '{plugin_id}' is already registered")

        # Validate dependencies before registering
        self._validate_dependencies_for_registration(metadata)

        # Check for circular dependencies
        self._check_circular_dependencies(metadata)

        self._plugins[plugin_id] = plugin
        self._metadata[plugin_id] = metadata

        self.logger.info(f"Registered plugin '{plugin_id}' v{metadata.version}")

    def unregister(self, plugin_id: str):
        """Unregister a plugin.

        Args:
            plugin_id: ID of plugin to unregister

        Note:
            This does NOT check if other plugins depend on this plugin.
            Use check_dependents() first if you need to verify.
        """
        if plugin_id in self._plugins:
            del self._plugins[plugin_id]
            del self._metadata[plugin_id]
            self.logger.info(f"Unregistered plugin '{plugin_id}'")

    def get_plugin(self, plugin_id: str) -> Optional[BaseTabPlugin]:
        """Get a plugin by ID.

        Args:
            plugin_id: ID of plugin to retrieve

        Returns:
            Optional[BaseTabPlugin]: The plugin instance or None if not found
        """
        return self._plugins.get(plugin_id)

    def get_metadata(self, plugin_id: str) -> Optional[TabPluginMetadata]:
        """Get plugin metadata.

        Args:
            plugin_id: ID of plugin

        Returns:
            Optional[TabPluginMetadata]: The metadata or None if not found
        """
        return self._metadata.get(plugin_id)

    def list_plugins(self) -> List[str]:
        """List all registered plugin IDs.

        Returns:
            List[str]: List of plugin IDs in registration order
        """
        return list(self._plugins.keys())

    def validate_dependencies(self, plugin_id: str) -> bool:
        """Check if plugin dependencies are satisfied.

        Args:
            plugin_id: ID of plugin to check

        Returns:
            bool: True if all dependencies are satisfied, False otherwise
        """
        metadata = self._metadata.get(plugin_id)
        if not metadata:
            return False

        for required_id in metadata.requires:
            if required_id not in self._plugins:
                return False

        return True

    def get_missing_dependencies(self, plugin_id: str) -> List[str]:
        """Get list of missing dependencies for a plugin.

        Args:
            plugin_id: ID of plugin to check

        Returns:
            List[str]: List of missing plugin IDs
        """
        metadata = self._metadata.get(plugin_id)
        if not metadata:
            return []

        missing = []
        for required_id in metadata.requires:
            if required_id not in self._plugins:
                missing.append(required_id)

        return missing

    def get_dependents(self, plugin_id: str) -> List[str]:
        """Get list of plugins that depend on this plugin.

        Args:
            plugin_id: ID of plugin to check

        Returns:
            List[str]: List of plugin IDs that require this plugin
        """
        dependents = []
        for pid, metadata in self._metadata.items():
            if plugin_id in metadata.requires:
                dependents.append(pid)
        return dependents

    def check_dependents(self, plugin_id: str) -> bool:
        """Check if any plugins depend on this plugin.

        Args:
            plugin_id: ID of plugin to check

        Returns:
            bool: True if other plugins depend on it, False otherwise
        """
        return len(self.get_dependents(plugin_id)) > 0

    def _validate_dependencies_for_registration(self, metadata: TabPluginMetadata):
        """Validate that dependencies exist before registering.

        Args:
            metadata: Plugin metadata to validate

        Raises:
            DependencyError: If required dependencies are not registered
        """
        missing = []
        for required_id in metadata.requires:
            if required_id not in self._plugins:
                missing.append(required_id)

        if missing:
            raise DependencyError(
                f"Plugin '{metadata.plugin_id}' has missing dependencies: {missing}"
            )

    def _check_circular_dependencies(self, metadata: TabPluginMetadata):
        """Check for circular dependencies.

        This performs a depth-first search to detect cycles in the dependency graph.

        Args:
            metadata: Plugin metadata to check

        Raises:
            CircularDependencyError: If circular dependency detected
        """
        plugin_id = metadata.plugin_id
        visited: Set[str] = set()
        path: Set[str] = set()

        def dfs(current_id: str) -> bool:
            """Depth-first search for cycle detection."""
            if current_id in path:
                return True  # Cycle detected
            if current_id in visited:
                return False  # Already checked this branch

            visited.add(current_id)
            path.add(current_id)

            # Check dependencies of current plugin
            current_metadata = self._metadata.get(current_id)
            if current_metadata:
                for dep_id in current_metadata.requires:
                    if dfs(dep_id):
                        return True

            # For the new plugin being registered, check its dependencies
            if current_id == plugin_id:
                for dep_id in metadata.requires:
                    if dfs(dep_id):
                        return True

            path.remove(current_id)
            return False

        if dfs(plugin_id):
            raise CircularDependencyError(
                f"Circular dependency detected involving plugin '{plugin_id}'"
            )

    def get_dependency_order(self, plugin_ids: List[str]) -> List[str]:
        """Get plugins in dependency order (dependencies first).

        Uses topological sort to order plugins so that dependencies are
        loaded before plugins that require them.

        Args:
            plugin_ids: List of plugin IDs to order

        Returns:
            List[str]: Plugin IDs in dependency order

        Raises:
            CircularDependencyError: If circular dependency exists
            ValueError: If unknown plugin ID encountered
        """
        # Build dependency graph
        graph: Dict[str, List[str]] = {}
        in_degree: Dict[str, int] = {}

        for plugin_id in plugin_ids:
            if plugin_id not in self._metadata:
                raise ValueError(f"Unknown plugin ID: {plugin_id}")

            graph[plugin_id] = self._metadata[plugin_id].requires.copy()
            in_degree[plugin_id] = 0

        # Calculate in-degrees
        for plugin_id in plugin_ids:
            for dep_id in graph[plugin_id]:
                if dep_id in in_degree:
                    in_degree[dep_id] += 1

        # Kahn's algorithm for topological sort
        queue = [pid for pid in plugin_ids if in_degree[pid] == 0]
        result = []

        while queue:
            current = queue.pop(0)
            result.append(current)

            for dep_id in graph[current]:
                if dep_id in in_degree:
                    in_degree[dep_id] -= 1
                    if in_degree[dep_id] == 0:
                        queue.append(dep_id)

        if len(result) != len(plugin_ids):
            raise CircularDependencyError(
                "Circular dependency detected - cannot determine load order"
            )

        # Reverse to get dependencies first
        return list(reversed(result))

    def validate_version_compatibility(self, plugin_id: str, required_version: str) -> bool:
        """Validate that a plugin meets version requirements.

        Note: This is a basic implementation. For production use, consider
        using packaging.version for proper semantic version comparison.

        Args:
            plugin_id: Plugin to check
            required_version: Required version (e.g., "1.0.0", ">=1.2.0")

        Returns:
            bool: True if version compatible, False otherwise
        """
        metadata = self._metadata.get(plugin_id)
        if not metadata:
            return False

        # Simple exact match for now
        # TODO: Implement proper semantic versioning with operators
        # (>=, <=, ==, !=, ~=, etc.) using packaging.version
        return metadata.version == required_version

    def get_registry_stats(self) -> Dict[str, any]:
        """Get statistics about registered plugins.

        Returns:
            Dict with plugin counts and dependency information
        """
        return {
            "total_plugins": len(self._plugins),
            "plugin_ids": list(self._plugins.keys()),
            "total_dependencies": sum(
                len(m.requires) for m in self._metadata.values()
            ),
            "plugins_with_dependencies": sum(
                1 for m in self._metadata.values() if m.requires
            ),
        }
