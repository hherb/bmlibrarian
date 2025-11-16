"""
Main application window for BMLibrarian Qt GUI.

Implements the main window with plugin-based tabbed interface.
"""

from PySide6.QtWidgets import (
    QMainWindow,
    QTabWidget,
    QWidget,
    QVBoxLayout,
    QStatusBar,
    QMenuBar,
    QMessageBox,
)
from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QAction
from typing import Dict
from .plugin_manager import PluginManager
from .tab_registry import TabRegistry
from .config_manager import GUIConfigManager
from .event_bus import EventBus
from ..plugins.base_tab import BaseTabPlugin


class BMLibrarianMainWindow(QMainWindow):
    """Main application window with plugin-based tabs."""

    def __init__(self):
        """Initialize the main window."""
        super().__init__()

        # Initialize core components
        self.config_manager = GUIConfigManager()
        self.event_bus = EventBus()
        self.tab_registry = TabRegistry()
        self.plugin_manager = PluginManager(self.tab_registry)

        # Tab tracking
        self.tabs: Dict[str, QWidget] = {}
        self.current_plugin: BaseTabPlugin | None = None

        # Setup UI
        self._setup_ui()
        self._load_plugins()
        self._create_menu_bar()
        self._restore_geometry()

    def _setup_ui(self):
        """Setup the main window UI."""
        self.setWindowTitle("BMLibrarian - Biomedical Literature Research")

        # Create central widget with tab container
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)

        # Create tab widget
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabsClosable(False)
        self.tab_widget.setMovable(True)
        self.tab_widget.currentChanged.connect(self._on_tab_changed)

        layout.addWidget(self.tab_widget)

        # Create status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")

        # Connect event bus to status bar
        self.event_bus.status_update.connect(self._on_status_update)

    def _load_plugins(self):
        """Load enabled plugins and create tabs."""
        config = self.config_manager.get_config()
        enabled_plugins = config.get("gui", {}).get("tabs", {}).get("enabled_plugins", [])
        tab_order = config.get("gui", {}).get("tabs", {}).get("tab_order", enabled_plugins)

        # Load all enabled plugins
        loaded_plugins = self.plugin_manager.load_enabled_plugins(enabled_plugins)

        # Create tabs in specified order
        for plugin_id in tab_order:
            if plugin_id in loaded_plugins:
                self._add_plugin_tab(loaded_plugins[plugin_id])

        # Set default tab
        default_tab = config.get("gui", {}).get("tabs", {}).get("default_tab")
        if default_tab and default_tab in self.tabs:
            index = list(self.tabs.keys()).index(default_tab)
            self.tab_widget.setCurrentIndex(index)

    def _add_plugin_tab(self, plugin: BaseTabPlugin):
        """
        Add a tab from a plugin.

        Args:
            plugin: Plugin instance to add as tab
        """
        metadata = plugin.get_metadata()
        widget = plugin.create_widget(self)

        # Connect plugin signals to event bus
        plugin.status_changed.connect(
            lambda msg: self.event_bus.update_status(metadata.plugin_id, msg)
        )
        plugin.request_navigation.connect(self._navigate_to_tab)
        plugin.data_updated.connect(
            lambda data: self.event_bus.publish_data(metadata.plugin_id, data)
        )

        # Add tab
        index = self.tab_widget.addTab(widget, metadata.display_name)

        # TODO: Set tab icon if metadata.icon is provided
        # if metadata.icon:
        #     icon = QIcon(metadata.icon)
        #     self.tab_widget.setTabIcon(index, icon)

        self.tabs[metadata.plugin_id] = widget

    @Slot(int)
    def _on_tab_changed(self, index: int):
        """
        Handle tab change events.

        Args:
            index: Index of the newly activated tab
        """
        if index < 0:
            return

        # Get plugin ID for new tab
        plugin_id = list(self.tabs.keys())[index]
        plugin = self.plugin_manager.loaded_plugins.get(plugin_id)

        if not plugin:
            return

        # Deactivate previous plugin
        if self.current_plugin and self.current_plugin != plugin:
            try:
                self.current_plugin.on_tab_deactivated()
            except Exception as e:
                print(f"Error deactivating plugin: {e}")

        # Activate new plugin
        try:
            plugin.on_tab_activated()
            self.current_plugin = plugin
        except Exception as e:
            print(f"Error activating plugin: {e}")

    @Slot(str)
    def _navigate_to_tab(self, plugin_id: str):
        """
        Navigate to a specific tab by plugin ID.

        Args:
            plugin_id: ID of plugin to navigate to
        """
        if plugin_id in self.tabs:
            index = list(self.tabs.keys()).index(plugin_id)
            self.tab_widget.setCurrentIndex(index)

    @Slot(str, str)
    def _on_status_update(self, source: str, message: str):
        """
        Update status bar with plugin messages.

        Args:
            source: Plugin ID that sent the message
            message: Status message
        """
        self.status_bar.showMessage(f"[{source}] {message}", 5000)

    def _create_menu_bar(self):
        """Create the application menu bar."""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("&File")

        exit_action = QAction("E&xit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # View menu
        view_menu = menubar.addMenu("&View")

        # TODO: Implement tab configuration dialog
        # config_tabs_action = QAction("&Configure Tabs...", self)
        # config_tabs_action.triggered.connect(self._show_tab_configuration)
        # view_menu.addAction(config_tabs_action)

        # Help menu
        help_menu = menubar.addMenu("&Help")

        about_action = QAction("&About", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _restore_geometry(self):
        """Restore window geometry from config."""
        config = self.config_manager.get_config()
        window_config = config.get("gui", {}).get("window", {})

        width = window_config.get("width", 1400)
        height = window_config.get("height", 900)
        self.resize(width, height)

        # Restore position if available and remember_geometry is True
        if window_config.get("remember_geometry", True):
            pos_x = window_config.get("position_x")
            pos_y = window_config.get("position_y")
            if pos_x is not None and pos_y is not None:
                self.move(pos_x, pos_y)

    def _show_tab_configuration(self):
        """Show tab configuration dialog."""
        # TODO: Implement tab configuration dialog
        QMessageBox.information(
            self, "Tab Configuration", "Tab configuration dialog not yet implemented."
        )

    def _show_about(self):
        """Show about dialog."""
        about_text = """
        <h2>BMLibrarian</h2>
        <p>Biomedical Literature Research Application</p>
        <p>Version 0.1.0</p>
        <p>A comprehensive tool for AI-powered access to biomedical literature databases.</p>
        <p>Built with PySide6 and Qt for Python.</p>
        """
        QMessageBox.about(self, "About BMLibrarian", about_text)

    def closeEvent(self, event):
        """
        Handle window close event.

        Args:
            event: Close event
        """
        # Save geometry
        config = self.config_manager.get_config()
        if config.get("gui", {}).get("window", {}).get("remember_geometry", True):
            window_config = config.setdefault("gui", {}).setdefault("window", {})
            window_config["width"] = self.width()
            window_config["height"] = self.height()
            window_config["position_x"] = self.x()
            window_config["position_y"] = self.y()
            self.config_manager.save_config(config)

        # Cleanup plugins
        self.plugin_manager.unload_all_plugins()

        event.accept()
