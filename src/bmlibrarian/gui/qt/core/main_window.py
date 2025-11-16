"""Main application window for BMLibrarian Qt GUI.

This module provides the BMLibrarianMainWindow class which serves as the
main application window with plugin-based tabbed interface.
"""

from PySide6.QtWidgets import (
    QMainWindow, QTabWidget, QWidget, QVBoxLayout,
    QStatusBar, QMenuBar, QMenu, QMessageBox, QApplication
)
from PySide6.QtCore import Qt, Slot, QTimer
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence, QShortcut
from typing import Dict
import logging

from .plugin_manager import PluginManager, PluginLoadError
from .tab_registry import TabRegistry
from .config_manager import GUIConfigManager
from .event_bus import EventBus
from ..plugins.base_tab import BaseTabPlugin

# Import for agent cleanup
try:
    from ...workflow import cleanup_agents
    CLEANUP_AGENTS_AVAILABLE = True
except ImportError:
    CLEANUP_AGENTS_AVAILABLE = False
    cleanup_agents = None


class BMLibrarianMainWindow(QMainWindow):
    """Main application window with plugin-based tabs.

    This class provides:
    - Plugin-based tab system
    - Window geometry persistence
    - Menu bar with File/View/Help menus
    - Status bar for plugin messages
    - Tab navigation and management
    - Proper cleanup on close

    The window loads plugins specified in the configuration file and
    creates tabs for each plugin in the specified order.
    """

    def __init__(self):
        """Initialize the main window."""
        super().__init__()

        self.logger = logging.getLogger("bmlibrarian.gui.qt.core.MainWindow")

        # Initialize core components
        self.config_manager = GUIConfigManager()
        self.tab_registry = TabRegistry()
        self.plugin_manager = PluginManager(self.tab_registry)
        self.event_bus = EventBus()

        # Plugin tracking
        self.tabs: Dict[str, QWidget] = {}  # plugin_id -> widget
        self.tab_indices: Dict[str, int] = {}  # plugin_id -> tab index

        # Initialize BMLibrarian agents (for research workflow)
        self.agents = None
        self._initialize_agents()

        # Setup UI
        self._setup_ui()
        self._create_menu_bar()
        self._create_status_bar()
        self._setup_keyboard_shortcuts()

        # Load plugins
        self._load_plugins()

        # Restore window geometry
        self._restore_geometry()

        # Connect event bus signals
        self.event_bus.navigation_requested.connect(self._navigate_to_tab)
        self.event_bus.status_updated.connect(self._update_status)

        self.logger.info("Main window initialized")

    def _initialize_agents(self):
        """Initialize BMLibrarian agents in main thread (for research workflow)."""
        try:
            self.logger.info("Initializing BMLibrarian agents...")

            # Import initialize function from Flet GUI (framework-agnostic)
            from ...workflow import initialize_agents_in_main_thread

            # Initialize all agents
            self.agents = initialize_agents_in_main_thread()

            if self.agents:
                self.logger.info("✅ Agents initialized successfully")
            else:
                self.logger.warning("⚠️ Agent initialization returned None")

        except ImportError as e:
            self.logger.error(f"Failed to import required modules: {e}", exc_info=True)
            self.agents = None
        except ConnectionError as e:
            self.logger.error(f"Failed to connect to database or Ollama: {e}", exc_info=True)
            self.agents = None
        except (FileNotFoundError, ValueError) as e:
            self.logger.error(f"Configuration error: {e}", exc_info=True)
            self.agents = None
        except Exception as e:
            self.logger.error(f"Unexpected error during agent initialization: {e}", exc_info=True)
            self.agents = None

    def _setup_ui(self):
        """Setup the main window UI."""
        self.setWindowTitle("BMLibrarian - Biomedical Literature Research")

        # Set minimum size
        self.setMinimumSize(800, 600)

        # Create central widget with tab container
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)

        # Create tab widget
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabsClosable(False)
        self.tab_widget.setMovable(True)
        self.tab_widget.setDocumentMode(True)  # More native appearance
        self.tab_widget.currentChanged.connect(self._on_tab_changed)

        layout.addWidget(self.tab_widget)

        self.logger.debug("UI setup complete")

    def _create_menu_bar(self):
        """Create the application menu bar."""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("&File")

        # Export action (will be enabled by plugins as needed)
        self.export_action = QAction("&Export...", self)
        self.export_action.setShortcut("Ctrl+E")
        self.export_action.setEnabled(False)
        file_menu.addAction(self.export_action)

        file_menu.addSeparator()

        # Exit action
        exit_action = QAction("E&xit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # View menu
        view_menu = menubar.addMenu("&View")

        # Tab navigation submenu
        self.tabs_menu = view_menu.addMenu("&Tabs")
        # Will be populated after plugins are loaded

        view_menu.addSeparator()

        # Theme submenu
        theme_menu = view_menu.addMenu("&Theme")

        # Default theme action
        default_theme_action = QAction("&Light Theme", self)
        default_theme_action.setCheckable(True)
        default_theme_action.triggered.connect(lambda: self._change_theme("default"))
        theme_menu.addAction(default_theme_action)

        # Dark theme action
        dark_theme_action = QAction("&Dark Theme", self)
        dark_theme_action.setCheckable(True)
        dark_theme_action.triggered.connect(lambda: self._change_theme("dark"))
        theme_menu.addAction(dark_theme_action)

        # Set current theme as checked
        current_theme = self.config_manager.get_theme()
        if current_theme == "dark":
            dark_theme_action.setChecked(True)
        else:
            default_theme_action.setChecked(True)

        # Store theme actions for updating
        self.theme_actions = {
            "default": default_theme_action,
            "dark": dark_theme_action
        }

        view_menu.addSeparator()

        # Reload plugins action (for development)
        reload_action = QAction("&Reload Plugins", self)
        reload_action.setShortcut("Ctrl+R")
        reload_action.triggered.connect(self._reload_plugins)
        view_menu.addAction(reload_action)

        # Tools menu
        tools_menu = menubar.addMenu("&Tools")

        config_action = QAction("&Configuration...", self)
        config_action.setShortcut("Ctrl+,")
        config_action.triggered.connect(self._show_configuration)
        tools_menu.addAction(config_action)

        # Help menu
        help_menu = menubar.addMenu("&Help")

        about_action = QAction("&About BMLibrarian", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

        about_qt_action = QAction("About &Qt", self)
        about_qt_action.triggered.connect(QApplication.aboutQt)
        help_menu.addAction(about_qt_action)

        self.logger.debug("Menu bar created")

    def _create_status_bar(self):
        """Create the status bar."""
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")
        self.logger.debug("Status bar created")

    def _setup_keyboard_shortcuts(self):
        """Setup global keyboard shortcuts."""
        # Next tab (Ctrl+Tab)
        next_tab_shortcut = QShortcut(QKeySequence("Ctrl+Tab"), self)
        next_tab_shortcut.activated.connect(self._next_tab)

        # Previous tab (Ctrl+Shift+Tab)
        prev_tab_shortcut = QShortcut(QKeySequence("Ctrl+Shift+Tab"), self)
        prev_tab_shortcut.activated.connect(self._previous_tab)

        # Help (F1)
        help_shortcut = QShortcut(QKeySequence.StandardKey.HelpContents, self)
        help_shortcut.activated.connect(self._show_about)

        # Refresh current tab (F5)
        refresh_shortcut = QShortcut(QKeySequence.StandardKey.Refresh, self)
        refresh_shortcut.activated.connect(self._refresh_current_tab)

        # Quick theme toggle (Ctrl+Shift+T)
        theme_toggle_shortcut = QShortcut(QKeySequence("Ctrl+Shift+T"), self)
        theme_toggle_shortcut.activated.connect(self._toggle_theme)

        self.logger.debug("Keyboard shortcuts setup complete")

    def _load_plugins(self):
        """Load enabled plugins and create tabs."""
        config = self.config_manager.get_config()
        enabled_plugins = config.get("gui", {}).get("tabs", {}).get(
            "enabled_plugins", []
        )
        tab_order = config.get("gui", {}).get("tabs", {}).get(
            "tab_order", enabled_plugins
        )

        if not enabled_plugins:
            self.logger.warning("No plugins enabled in configuration")
            self.status_bar.showMessage("No plugins configured", 5000)
            return

        self.logger.info(f"Loading {len(enabled_plugins)} enabled plugins...")

        # Load all enabled plugins
        loaded_plugins = self.plugin_manager.load_enabled_plugins(
            enabled_plugins,
            continue_on_error=True
        )

        if not loaded_plugins:
            self.logger.error("No plugins loaded successfully")
            QMessageBox.warning(
                self,
                "No Plugins Loaded",
                "Failed to load any plugins. Check logs for details."
            )
            return

        # Create tabs in specified order
        for plugin_id in tab_order:
            if plugin_id in loaded_plugins:
                plugin = loaded_plugins[plugin_id]
                self._add_plugin_tab(plugin)

        # Set default tab
        default_tab = config.get("gui", {}).get("tabs", {}).get("default_tab", None)
        if default_tab and default_tab in self.tabs:
            index = self.tab_indices.get(default_tab, 0)
            self.tab_widget.setCurrentIndex(index)

        # Update tabs menu
        self._update_tabs_menu()

        # Show load summary
        failed_plugins = self.plugin_manager.get_failed_plugins()
        if failed_plugins:
            self.status_bar.showMessage(
                f"Loaded {len(loaded_plugins)} plugins "
                f"({len(failed_plugins)} failed)",
                5000
            )
        else:
            self.status_bar.showMessage(
                f"Loaded {len(loaded_plugins)} plugins",
                3000
            )

        self.logger.info(
            f"Plugin loading complete: {len(loaded_plugins)} loaded, "
            f"{len(failed_plugins)} failed"
        )

    def _add_plugin_tab(self, plugin: BaseTabPlugin):
        """Add a tab from a plugin.

        Args:
            plugin: Plugin instance to add as tab
        """
        metadata = plugin.get_metadata()
        plugin_id = metadata.plugin_id

        try:
            # Create widget
            widget = plugin.create_widget(self)

            # Connect plugin signals
            plugin.status_changed.connect(self._on_plugin_status_changed)
            plugin.request_navigation.connect(self._navigate_to_tab)

            # Add tab
            index = self.tab_widget.addTab(widget, metadata.display_name)

            # Store references
            self.tabs[plugin_id] = widget
            self.tab_indices[plugin_id] = index

            # Register with event bus
            self.event_bus.register_plugin(plugin_id)

            self.logger.info(f"Added tab for plugin '{plugin_id}'")

        except Exception as e:
            self.logger.error(
                f"Error adding tab for plugin '{plugin_id}': {e}",
                exc_info=True
            )
            QMessageBox.warning(
                self,
                "Plugin Error",
                f"Failed to create tab for plugin '{metadata.display_name}':\n{e}"
            )

    def _update_tabs_menu(self):
        """Update the tabs navigation menu."""
        self.tabs_menu.clear()

        for plugin_id, index in sorted(
            self.tab_indices.items(),
            key=lambda x: x[1]
        ):
            plugin = self.plugin_manager.loaded_plugins.get(plugin_id)
            if plugin:
                metadata = plugin.get_metadata()
                action = QAction(metadata.display_name, self)
                action.setShortcut(f"Alt+{index + 1}")
                action.triggered.connect(
                    lambda checked, pid=plugin_id: self._navigate_to_tab(pid)
                )
                self.tabs_menu.addAction(action)

    @Slot(int)
    def _on_tab_changed(self, index: int):
        """Handle tab change events.

        Args:
            index: Index of newly activated tab
        """
        if index < 0 or index >= self.tab_widget.count():
            return

        # Find plugin_id for this index
        current_plugin_id = None
        for plugin_id, tab_index in self.tab_indices.items():
            if tab_index == index:
                current_plugin_id = plugin_id
                break

        if not current_plugin_id:
            return

        # Deactivate all plugins
        for plugin_id, plugin in self.plugin_manager.loaded_plugins.items():
            if plugin_id != current_plugin_id:
                try:
                    plugin.on_tab_deactivated()
                except Exception as e:
                    self.logger.error(
                        f"Error deactivating plugin '{plugin_id}': {e}",
                        exc_info=True
                    )

        # Activate current plugin
        current_plugin = self.plugin_manager.loaded_plugins.get(current_plugin_id)
        if current_plugin:
            try:
                current_plugin.on_tab_activated()
            except Exception as e:
                self.logger.error(
                    f"Error activating plugin '{current_plugin_id}': {e}",
                    exc_info=True
                )

        self.logger.debug(f"Tab changed to '{current_plugin_id}'")

    @Slot(str)
    def _navigate_to_tab(self, plugin_id: str):
        """Navigate to a specific tab by plugin ID.

        Args:
            plugin_id: ID of plugin/tab to navigate to
        """
        if plugin_id in self.tab_indices:
            index = self.tab_indices[plugin_id]
            self.tab_widget.setCurrentIndex(index)
            self.logger.debug(f"Navigated to tab '{plugin_id}'")
        else:
            self.logger.warning(f"Cannot navigate to unknown tab '{plugin_id}'")

    @Slot(str)
    def _on_plugin_status_changed(self, message: str):
        """Update status bar with plugin messages.

        Args:
            message: Status message from plugin
        """
        self.status_bar.showMessage(message, 5000)

    @Slot(str)
    def _update_status(self, message: str):
        """Update status bar (from event bus).

        Args:
            message: Status message
        """
        self.status_bar.showMessage(message, 5000)

    def _restore_geometry(self):
        """Restore window geometry from config."""
        window_config = self.config_manager.get_window_config()

        width = window_config.get("width", 1400)
        height = window_config.get("height", 900)
        self.resize(width, height)

        # Restore position if saved
        if window_config.get("remember_geometry", True):
            x = window_config.get("x")
            y = window_config.get("y")
            if x is not None and y is not None:
                self.move(x, y)

            # Restore maximized state
            if window_config.get("maximized", False):
                self.showMaximized()

        self.logger.debug("Window geometry restored")

    def _save_geometry(self):
        """Save current window geometry to config."""
        window_config = self.config_manager.get_window_config()

        if window_config.get("remember_geometry", True):
            window_config["width"] = self.width()
            window_config["height"] = self.height()
            window_config["x"] = self.x()
            window_config["y"] = self.y()
            window_config["maximized"] = self.isMaximized()

            self.config_manager.set_window_config(window_config)
            self.logger.debug("Window geometry saved")

    @Slot()
    def _reload_plugins(self):
        """Reload all plugins (for development)."""
        reply = QMessageBox.question(
            self,
            "Reload Plugins",
            "This will reload all plugins. Unsaved data may be lost. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.logger.info("Reloading plugins...")
            # TODO: Implement full plugin reload
            self.status_bar.showMessage("Plugin reload not yet implemented", 3000)

    @Slot()
    def _show_configuration(self):
        """Show configuration dialog or navigate to configuration tab."""
        # Try to navigate to configuration tab first
        if "configuration" in self.tabs:
            self._navigate_to_tab("configuration")
        else:
            # TODO: Show standalone configuration dialog
            self.status_bar.showMessage(
                "Configuration tab not loaded",
                3000
            )

    @Slot()
    def _show_about(self):
        """Show about dialog."""
        about_text = """
        <h2>BMLibrarian</h2>
        <p><b>Biomedical Literature Research Platform</b></p>
        <p>Version 0.1.0</p>
        <p>A comprehensive Python library providing AI-powered access to
        biomedical literature databases.</p>
        <p>Built with PySide6 and PostgreSQL.</p>
        """

        QMessageBox.about(self, "About BMLibrarian", about_text)

    @Slot(str)
    def _change_theme(self, theme: str):
        """Change the application theme.

        Args:
            theme: Theme name ("default" or "dark")
        """
        # Save theme to configuration
        self.config_manager.set_theme(theme)

        # Update checked state of theme actions
        for theme_name, action in self.theme_actions.items():
            action.setChecked(theme_name == theme)

        # Show message about restart
        reply = QMessageBox.question(
            self,
            "Theme Changed",
            f"Theme changed to {theme}. Would you like to restart the application now to apply the new theme?\n\n"
            f"(You can continue using the current session, but the theme will be fully applied on next restart.)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            # Restart application
            self.logger.info("Restarting application to apply theme change...")
            QApplication.quit()
            # Note: The user will need to manually restart the application
            # A full auto-restart would require platform-specific code

        self.logger.info(f"Theme changed to '{theme}'")

    @Slot()
    def _next_tab(self):
        """Navigate to the next tab."""
        current_index = self.tab_widget.currentIndex()
        next_index = (current_index + 1) % self.tab_widget.count()
        self.tab_widget.setCurrentIndex(next_index)
        self.logger.debug(f"Navigated to next tab (index {next_index})")

    @Slot()
    def _previous_tab(self):
        """Navigate to the previous tab."""
        current_index = self.tab_widget.currentIndex()
        prev_index = (current_index - 1) % self.tab_widget.count()
        self.tab_widget.setCurrentIndex(prev_index)
        self.logger.debug(f"Navigated to previous tab (index {prev_index})")

    @Slot()
    def _refresh_current_tab(self):
        """Refresh the current tab."""
        current_index = self.tab_widget.currentIndex()

        # Find plugin_id for current tab
        current_plugin_id = None
        for plugin_id, tab_index in self.tab_indices.items():
            if tab_index == current_index:
                current_plugin_id = plugin_id
                break

        if not current_plugin_id:
            self.logger.warning("No plugin found for current tab")
            return

        # Get the plugin
        plugin = self.plugin_manager.loaded_plugins.get(current_plugin_id)
        if plugin:
            try:
                # Deactivate and reactivate to refresh
                plugin.on_tab_deactivated()
                plugin.on_tab_activated()
                self.status_bar.showMessage(f"Refreshed {current_plugin_id} tab", 2000)
                self.logger.debug(f"Refreshed tab '{current_plugin_id}'")
            except Exception as e:
                self.logger.error(
                    f"Error refreshing plugin '{current_plugin_id}': {e}",
                    exc_info=True
                )
                self.status_bar.showMessage(f"Error refreshing tab", 3000)

    @Slot()
    def _toggle_theme(self):
        """Toggle between light and dark themes."""
        current_theme = self.config_manager.get_theme()
        new_theme = "dark" if current_theme == "default" else "default"
        self._change_theme(new_theme)

    def closeEvent(self, event: QCloseEvent):
        """Handle window close event.

        Args:
            event: Close event
        """
        # Save geometry
        self._save_geometry()

        # Cleanup all plugins
        self.logger.info("Cleaning up plugins...")
        for plugin_id, plugin in self.plugin_manager.loaded_plugins.items():
            try:
                plugin.cleanup()
                self.event_bus.unregister_plugin(plugin_id)
                self.logger.debug(f"Cleaned up plugin '{plugin_id}'")
            except Exception as e:
                self.logger.error(
                    f"Error cleaning up plugin '{plugin_id}': {e}",
                    exc_info=True
                )

        # Cleanup agents (return audit connection to pool)
        if self.agents and CLEANUP_AGENTS_AVAILABLE:
            try:
                cleanup_agents(self.agents)
                self.logger.info("✅ Agents cleaned up")
            except Exception as e:
                self.logger.error(f"Error cleaning up agents: {e}", exc_info=True)
        elif self.agents and not CLEANUP_AGENTS_AVAILABLE:
            self.logger.warning("cleanup_agents not available - skipping agent cleanup")

        self.logger.info("Application closing")
        event.accept()
