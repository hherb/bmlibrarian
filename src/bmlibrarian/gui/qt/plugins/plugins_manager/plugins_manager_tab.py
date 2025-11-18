"""Plugins Manager tab widget for managing BMLibrarian plugins."""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QCheckBox, QGroupBox, QMessageBox
)
from PySide6.QtCore import Qt, Slot
from typing import Dict, List
import logging


class PluginCard(QFrame):
    """Card widget displaying information about a single plugin."""

    def __init__(self, plugin_id: str, metadata: Dict, is_enabled: bool,
                 on_toggle_callback, parent=None):
        """Initialize the plugin card.

        Args:
            plugin_id: ID of the plugin
            metadata: Plugin metadata dictionary
            is_enabled: Whether plugin is currently enabled
            on_toggle_callback: Callback function when toggle is changed
            parent: Parent widget
        """
        super().__init__(parent)
        self.plugin_id = plugin_id
        self.metadata = metadata
        self.on_toggle_callback = on_toggle_callback

        self._build_ui(is_enabled)
        self.setFrameStyle(QFrame.Shape.Box | QFrame.Shadow.Raised)
        self.setLineWidth(1)

    def _build_ui(self, is_enabled: bool):
        """Build the card UI.

        Args:
            is_enabled: Whether plugin is currently enabled
        """
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        # Left side: Plugin info
        info_layout = QVBoxLayout()

        # Plugin name and version
        name_label = QLabel(f"<b>{self.metadata.get('display_name', self.plugin_id)}</b>")
        name_label.setStyleSheet("font-size: 14pt;")
        info_layout.addWidget(name_label)

        version_label = QLabel(f"Version: {self.metadata.get('version', 'Unknown')}")
        version_label.setStyleSheet("color: gray;")
        info_layout.addWidget(version_label)

        # Description
        description = self.metadata.get('description', 'No description available')
        desc_label = QLabel(description)
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("margin-top: 5px;")
        info_layout.addWidget(desc_label)

        # Plugin ID
        id_label = QLabel(f"Plugin ID: {self.plugin_id}")
        id_label.setStyleSheet("color: gray; font-size: 9pt; margin-top: 5px;")
        info_layout.addWidget(id_label)

        # Dependencies (if any)
        requires = self.metadata.get('requires', [])
        if requires:
            deps_label = QLabel(f"Dependencies: {', '.join(requires)}")
            deps_label.setStyleSheet("color: gray; font-size: 9pt;")
            info_layout.addWidget(deps_label)

        # Status
        if self.metadata.get('loaded', False):
            status_label = QLabel("Status: Loaded")
            status_label.setStyleSheet("color: green; font-weight: bold;")
        elif self.metadata.get('failed', False):
            error_msg = self.metadata.get('error', 'Unknown error')
            status_label = QLabel(f"Status: Failed - {error_msg}")
            status_label.setStyleSheet("color: red; font-weight: bold;")
        else:
            status_label = QLabel("Status: Not loaded")
            status_label.setStyleSheet("color: orange;")
        info_layout.addWidget(status_label)

        info_layout.addStretch()

        layout.addLayout(info_layout, stretch=1)

        # Right side: Enable/Disable toggle
        toggle_layout = QVBoxLayout()
        toggle_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight)

        self.enable_checkbox = QCheckBox("Enabled")
        self.enable_checkbox.setChecked(is_enabled)
        self.enable_checkbox.stateChanged.connect(self._on_toggle_changed)
        toggle_layout.addWidget(self.enable_checkbox)

        layout.addLayout(toggle_layout)

    @Slot(int)
    def _on_toggle_changed(self, state: int):
        """Handle toggle state change.

        Args:
            state: New checkbox state
        """
        is_enabled = (state == Qt.CheckState.Checked.value)
        self.on_toggle_callback(self.plugin_id, is_enabled)

    def set_enabled(self, enabled: bool):
        """Set the enabled state of the checkbox.

        Args:
            enabled: Whether to enable the checkbox
        """
        self.enable_checkbox.setChecked(enabled)


class PluginsManagerTab(QWidget):
    """Main widget for the Plugins Manager tab."""

    def __init__(self, plugin, parent=None):
        """Initialize the plugins manager tab.

        Args:
            plugin: Parent plugin instance
            parent: Parent widget
        """
        super().__init__(parent)
        self.plugin = plugin
        self.logger = logging.getLogger("bmlibrarian.gui.qt.plugins.PluginsManagerTab")

        # Get references to main window components
        from ...core.config_manager import GUIConfigManager
        from ...core.plugin_manager import PluginManager
        from ...core.tab_registry import TabRegistry

        # Get the plugin manager and config manager from the parent window
        # IMPORTANT: Use the same config_manager instance to avoid overwriting changes
        main_window = self._get_main_window()
        if main_window:
            self.plugin_manager = main_window.plugin_manager
            self.tab_widget = main_window.tab_widget
            self.main_window = main_window
            self.config_manager = main_window.config_manager
        else:
            self.logger.error("Could not find main window")
            self.plugin_manager = None
            self.tab_widget = None
            self.main_window = None
            # Fallback: create new instance (but this shouldn't happen)
            self.config_manager = GUIConfigManager()

        self.plugin_cards: Dict[str, PluginCard] = {}

        self._build_ui()
        self._load_plugin_list()

    def _get_main_window(self):
        """Get the main window instance.

        Returns:
            Main window instance or None
        """
        parent = self.parent()
        while parent:
            if parent.__class__.__name__ == "BMLibrarianMainWindow":
                return parent
            parent = parent.parent()
        return None

    def _build_ui(self):
        """Build the user interface."""
        layout = QVBoxLayout(self)

        # Header
        header = QLabel("<h1>Plugin Manager</h1>")
        layout.addWidget(header)

        description = QLabel(
            "Manage BMLibrarian Qt GUI plugins. Enable or disable plugins to customize your workspace. "
            "Changes take effect after restarting the application."
        )
        description.setWordWrap(True)
        description.setStyleSheet("margin-bottom: 10px;")
        layout.addWidget(description)

        # Refresh button
        refresh_button = QPushButton("Refresh Plugin List")
        refresh_button.clicked.connect(self._refresh_plugins)
        layout.addWidget(refresh_button)

        # Scroll area for plugin cards
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        # Container widget for cards
        self.cards_container = QWidget()
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        scroll_area.setWidget(self.cards_container)
        layout.addWidget(scroll_area)

    def _load_plugin_list(self):
        """Load and display all available plugins."""
        if not self.plugin_manager:
            self.logger.error("Plugin manager not available")
            return

        # Clear existing cards
        for card in self.plugin_cards.values():
            self.cards_layout.removeWidget(card)
            card.deleteLater()
        self.plugin_cards.clear()

        # Get enabled plugins from config
        enabled_plugins = self.config_manager.get_enabled_plugins()

        # Discover all available plugins
        discovered_plugins = self.plugin_manager.discover_plugins()
        self.logger.info(f"Discovered {len(discovered_plugins)} plugins")

        # Get loaded plugins
        loaded_plugins = self.plugin_manager.loaded_plugins
        failed_plugins = self.plugin_manager.get_failed_plugins()

        # Create cards for all discovered plugins
        for plugin_id in sorted(discovered_plugins):
            is_enabled = plugin_id in enabled_plugins

            # Get metadata if plugin is loaded
            metadata = {}
            if plugin_id in loaded_plugins:
                plugin_instance = loaded_plugins[plugin_id]
                plugin_metadata = plugin_instance.get_metadata()
                metadata = {
                    'display_name': plugin_metadata.display_name,
                    'description': plugin_metadata.description,
                    'version': plugin_metadata.version,
                    'requires': plugin_metadata.requires,
                    'loaded': True,
                    'failed': False
                }
            elif plugin_id in failed_plugins:
                metadata = {
                    'display_name': plugin_id.replace('_', ' ').title(),
                    'description': 'Plugin failed to load',
                    'version': 'Unknown',
                    'requires': [],
                    'loaded': False,
                    'failed': True,
                    'error': failed_plugins[plugin_id]
                }
            else:
                # Plugin discovered but not loaded
                metadata = {
                    'display_name': plugin_id.replace('_', ' ').title(),
                    'description': 'Plugin available but not enabled',
                    'version': 'Unknown',
                    'requires': [],
                    'loaded': False,
                    'failed': False
                }

            # Create card
            card = PluginCard(
                plugin_id=plugin_id,
                metadata=metadata,
                is_enabled=is_enabled,
                on_toggle_callback=self._on_plugin_toggled,
                parent=self.cards_container
            )
            self.plugin_cards[plugin_id] = card
            self.cards_layout.addWidget(card)

        # Add stretch at the end
        self.cards_layout.addStretch()

        self.logger.info(f"Loaded {len(self.plugin_cards)} plugin cards")

    @Slot()
    def _refresh_plugins(self):
        """Refresh the plugin list."""
        self.logger.info("Refreshing plugin list...")
        self._load_plugin_list()
        if self.plugin:
            self.plugin.status_changed.emit("Plugin list refreshed")

    def _on_plugin_toggled(self, plugin_id: str, is_enabled: bool):
        """Handle plugin enable/disable toggle.

        Args:
            plugin_id: ID of the plugin being toggled
            is_enabled: New enabled state
        """
        self.logger.info(f"Plugin '{plugin_id}' toggled: {is_enabled}")

        # Get current enabled plugins
        enabled_plugins = self.config_manager.get_enabled_plugins()

        # Update enabled plugins list
        if is_enabled:
            if plugin_id not in enabled_plugins:
                enabled_plugins.append(plugin_id)
                self.logger.info(f"Added '{plugin_id}' to enabled plugins")
        else:
            if plugin_id in enabled_plugins:
                enabled_plugins.remove(plugin_id)
                self.logger.info(f"Removed '{plugin_id}' from enabled plugins")

        # Save updated configuration
        self.config_manager.set_enabled_plugins(enabled_plugins)

        # Also update tab order to include new plugin
        tab_order = self.config_manager.get_tab_order()
        if is_enabled and plugin_id not in tab_order:
            tab_order.append(plugin_id)
            self.config_manager.set_tab_order(tab_order)

        # Show message about restart requirement
        action_text = "enabled" if is_enabled else "disabled"
        QMessageBox.information(
            self,
            "Plugin Configuration Updated",
            f"Plugin '{plugin_id}' has been {action_text}.\n\n"
            f"Please restart the application for changes to take effect."
        )

        # Update status
        if self.plugin:
            self.plugin.status_changed.emit(
                f"Plugin '{plugin_id}' {action_text} - restart required"
            )

    def on_activated(self):
        """Called when tab is activated."""
        self.logger.debug("Plugins manager tab activated")
        # Refresh plugin list when tab is activated
        self._refresh_plugins()

    def on_deactivated(self):
        """Called when tab is deactivated."""
        self.logger.debug("Plugins manager tab deactivated")
