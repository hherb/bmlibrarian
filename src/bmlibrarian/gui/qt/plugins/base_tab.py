"""Base class for all tab plugins in the PySide6 GUI.

This module provides the abstract base class that all tab plugins must inherit from.
It defines the standard interface for plugin lifecycle, configuration, and communication.
"""

from abc import ABC, abstractmethod, ABCMeta
from typing import Optional, Dict, Any, List
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Signal, QObject
import logging


# Create a combined metaclass to resolve QObject + ABC conflict
class QABCMeta(type(QObject), ABCMeta):
    """Combined metaclass for classes that need both QObject and ABC functionality.

    This resolves the metaclass conflict that occurs when a class tries to inherit
    from both QObject (which has Qt's meta-object system) and ABC (which uses ABCMeta).
    """
    pass


class TabPluginMetadata:
    """Metadata for a tab plugin.

    This class encapsulates all metadata about a plugin including its ID,
    display name, version, dependencies, and optional icon.
    """

    def __init__(
        self,
        plugin_id: str,
        display_name: str,
        description: str,
        version: str,
        icon: Optional[str] = None,
        requires: Optional[List[str]] = None
    ):
        """Initialize plugin metadata.

        Args:
            plugin_id: Unique identifier for the plugin (e.g., "research", "search")
            display_name: Human-readable name shown in UI (e.g., "Research Workflow")
            description: Brief description of plugin functionality
            version: Plugin version string (e.g., "1.0.0")
            icon: Optional icon filename (looked up in resources/icons/)
            requires: Optional list of plugin IDs this plugin depends on
        """
        self.plugin_id = plugin_id
        self.display_name = display_name
        self.description = description
        self.version = version
        self.icon = icon
        self.requires = requires or []


class BaseTabPlugin(QObject, ABC, metaclass=QABCMeta):
    """Abstract base class for all tab plugins.

    This class defines the standard interface that all tab plugins must implement.
    It includes lifecycle management, configuration, and inter-plugin communication
    through Qt signals.

    Lifecycle:
        1. Plugin instantiated by PluginManager
        2. get_metadata() called to retrieve plugin information
        3. create_widget() called to create the UI widget
        4. on_tab_activated() called when user navigates to tab
        5. on_tab_deactivated() called when user leaves tab
        6. cleanup() called when plugin is unloaded or app closes

    Memory Management:
        Plugins should implement cleanup() to:
        - Disconnect signals
        - Release database connections
        - Clear caches
        - Stop background threads
        - Delete temporary files
    """

    # Signals for inter-tab communication
    request_navigation = Signal(str)  # Navigate to another tab (emit plugin_id)
    status_changed = Signal(str)      # Update status bar (emit message)
    data_updated = Signal(dict)       # Share data with other tabs (emit data dict)

    def __init__(self):
        """Initialize the base plugin.

        Subclasses should call super().__init__() first, then initialize
        their own resources.
        """
        super().__init__()
        self.logger = logging.getLogger(f"bmlibrarian.gui.qt.plugins.{self.__class__.__name__}")
        self._is_active = False
        self._widget = None

    @abstractmethod
    def get_metadata(self) -> TabPluginMetadata:
        """Return plugin metadata.

        This method must be implemented by all plugins to provide information
        about the plugin including its ID, display name, version, and dependencies.

        Returns:
            TabPluginMetadata: Metadata object describing this plugin

        Example:
            return TabPluginMetadata(
                plugin_id="research",
                display_name="Research Workflow",
                description="Medical research workflow interface",
                version="1.0.0",
                icon="research.png",
                requires=[]
            )
        """
        pass

    @abstractmethod
    def create_widget(self, parent: Optional[QWidget] = None) -> QWidget:
        """Create and return the main widget for this tab.

        This method is called once when the tab is first added to the main window.
        The widget should contain all UI elements for the tab.

        Args:
            parent: Optional parent widget (usually the QTabWidget)

        Returns:
            QWidget: The main widget to display in the tab

        Example:
            widget = QWidget(parent)
            layout = QVBoxLayout(widget)
            layout.addWidget(QLabel("Tab content"))
            return widget
        """
        pass

    @abstractmethod
    def on_tab_activated(self):
        """Called when this tab becomes active.

        Use this method to:
        - Update UI with latest data
        - Resume background operations
        - Emit status messages
        - Refresh content if needed

        Example:
            self._is_active = True
            self.status_changed.emit("Research tab activated")
            self._refresh_data()
        """
        pass

    @abstractmethod
    def on_tab_deactivated(self):
        """Called when this tab is deactivated (user navigates away).

        Use this method to:
        - Pause non-critical background operations
        - Save current state
        - Release resources that aren't needed when inactive

        Note: This is NOT the same as cleanup() - the tab may be reactivated.

        Example:
            self._is_active = False
            self._pause_background_tasks()
        """
        pass

    def get_config(self) -> Dict[str, Any]:
        """Get plugin-specific configuration.

        Override this method to provide default configuration values or
        to return the current configuration state.

        Returns:
            Dict[str, Any]: Configuration dictionary

        Example:
            return {
                "show_workflow_steps": True,
                "auto_scroll": True,
                "max_results": 100
            }
        """
        return {}

    def set_config(self, config: Dict[str, Any]):
        """Update plugin configuration.

        Override this method to handle configuration updates from the
        configuration manager. The plugin should update its behavior
        based on the new configuration.

        Args:
            config: New configuration dictionary

        Example:
            self.show_workflow_steps = config.get("show_workflow_steps", True)
            self._update_ui_visibility()
        """
        pass

    def cleanup(self):
        """Cleanup resources when plugin is unloaded.

        This method is called when:
        - The application is closing
        - The plugin is being hot-reloaded (development)
        - The plugin is being disabled by the user

        IMPORTANT: Plugins MUST implement proper cleanup to avoid:
        - Memory leaks
        - Database connection leaks
        - Thread leaks
        - Temporary file accumulation

        Subclasses should override this method and:
        1. Disconnect all signals
        2. Close database connections
        3. Stop background threads
        4. Clear caches
        5. Delete temporary files
        6. Call super().cleanup() at the end

        Example:
            # Disconnect signals
            try:
                self.data_updated.disconnect()
                self.status_changed.disconnect()
            except RuntimeError:
                pass  # Already disconnected

            # Stop threads
            if self.threadpool:
                self.threadpool.clear()
                self.threadpool.waitForDone(5000)

            # Close connections
            for conn in self.db_connections:
                conn.close()

            # Call parent cleanup
            super().cleanup()
        """
        # Disconnect all signals to prevent memory leaks
        try:
            self.request_navigation.disconnect()
        except RuntimeError:
            pass  # Signal not connected

        try:
            self.status_changed.disconnect()
        except RuntimeError:
            pass

        try:
            self.data_updated.disconnect()
        except RuntimeError:
            pass

        self.logger.debug(f"Plugin '{self.get_metadata().plugin_id}' cleaned up")

    def is_active(self) -> bool:
        """Check if this plugin's tab is currently active.

        Returns:
            bool: True if tab is active, False otherwise
        """
        return self._is_active

    def get_widget(self) -> Optional[QWidget]:
        """Get the widget created by create_widget().

        Returns:
            Optional[QWidget]: The widget if created, None otherwise
        """
        return self._widget
