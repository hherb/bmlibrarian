"""
Settings Plugin for BMLibrarian Qt GUI.

Integrates configuration functionality into the Research GUI as a nested tab interface
within a single Settings tab. Mirrors functionality from bmlibrarian/gui/settings_tab.py
"""

import os
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QListWidget, QListWidgetItem, QStackedWidget, QMessageBox,
    QFileDialog, QFrame
)
from PySide6.QtCore import Qt, Slot, Signal
from typing import Dict, Optional

from bmlibrarian.config import get_config, DEFAULT_CONFIG
from bmlibrarian.llm import list_ollama_models
from ...tabs.general_tab import GeneralSettingsTab
from ...tabs.agent_tab import AgentConfigTab
from ...tabs.search_tab import SearchSettingsTab
from ..base_tab import BaseTabPlugin, TabPluginMetadata


class SettingsWidget(QWidget):
    """Settings widget with vertical navigation layout."""

    # Signal emitted when agents need reinitialization
    agents_need_reinit = Signal()

    def __init__(self, parent=None):
        """Initialize settings plugin.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)
        self.config = get_config()
        self.tab_objects: Dict[str, object] = {}  # Store tab references
        self.current_section = 'general'  # Track current section

        self._init_ui()

    def _init_ui(self):
        """Initialize the user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        # Header
        header_label = QLabel("⚙️ Settings & Configuration")
        header_label.setStyleSheet("font-size: 14pt; font-weight: bold; color: #1976D2;")
        layout.addWidget(header_label)

        # Main content area: navigation on left, content on right
        content_layout = QHBoxLayout()
        content_layout.setSpacing(15)

        # Left sidebar with navigation and action buttons
        left_sidebar = self._create_left_sidebar()
        content_layout.addWidget(left_sidebar)

        # Right content area with stacked widget for different tabs
        self.content_stack = QStackedWidget()
        self._create_sections()
        content_layout.addWidget(self.content_stack, 1)  # Expandable

        layout.addLayout(content_layout, 1)  # Expandable

    def _create_left_sidebar(self) -> QWidget:
        """Create left sidebar with navigation and action buttons.

        Returns:
            Widget containing navigation list and action buttons
        """
        sidebar = QWidget()
        sidebar.setFixedWidth(220)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(10)

        # Navigation list
        self.nav_list = QListWidget()
        self.nav_list.setStyleSheet("""
            QListWidget {
                border: 1px solid #CCCCCC;
                border-radius: 5px;
                background-color: #FAFAFA;
            }
            QListWidget::item {
                padding: 8px;
                border-radius: 3px;
            }
            QListWidget::item:selected {
                background-color: #E3F2FD;
                color: #1976D2;
            }
            QListWidget::item:hover {
                background-color: #F5F5F5;
            }
        """)
        self.nav_list.currentRowChanged.connect(self._on_nav_changed)

        # Add navigation items
        sections = [
            ("System", [
                ("general", "General"),
                ("search", "Search"),
            ]),
            ("Agents", [
                ("query_agent", "Query"),
                ("scoring_agent", "Scoring"),
                ("citation_agent", "Citation"),
                ("reporting_agent", "Reporting"),
                ("counterfactual_agent", "Counterfact."),
                ("editor_agent", "Editor"),
            ])
        ]

        for section_title, items in sections:
            # Add section header
            header_item = QListWidgetItem(f"━━ {section_title} ━━")
            header_item.setFlags(Qt.ItemFlag.NoItemFlags)  # Not selectable
            header_item.setForeground(Qt.GlobalColor.gray)
            self.nav_list.addItem(header_item)

            # Add section items
            for key, label in items:
                item = QListWidgetItem(f"  {label}")
                item.setData(Qt.ItemDataRole.UserRole, key)  # Store key as data
                self.nav_list.addItem(item)

        sidebar_layout.addWidget(self.nav_list, 1)  # Expandable

        # Action buttons
        actions_frame = self._create_action_buttons()
        sidebar_layout.addWidget(actions_frame)

        return sidebar

    def _create_action_buttons(self) -> QFrame:
        """Create action buttons for save/load/reset operations.

        Returns:
            Frame containing action buttons
        """
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background-color: #F5F5F5;
                border: 1px solid #CCCCCC;
                border-radius: 5px;
                padding: 10px;
            }
        """)
        layout = QVBoxLayout(frame)
        layout.setSpacing(8)

        # Apply Changes button
        apply_btn = QPushButton("✓ Apply Changes")
        apply_btn.setStyleSheet("""
            QPushButton {
                background-color: #1976D2;
                color: white;
                font-weight: bold;
                padding: 8px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #1565C0;
            }
        """)
        apply_btn.setToolTip("Apply configuration changes to current session")
        apply_btn.clicked.connect(self._apply_changes)
        layout.addWidget(apply_btn)

        # Save Config button
        save_btn = QPushButton("💾 Save Config")
        save_btn.setStyleSheet("""
            QPushButton {
                background-color: #43A047;
                color: white;
                font-weight: bold;
                padding: 8px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #388E3C;
            }
        """)
        save_btn.setToolTip("Save to ~/.bmlibrarian/config.json")
        save_btn.clicked.connect(self._save_to_default)
        layout.addWidget(save_btn)

        # Icon buttons row
        icon_layout = QHBoxLayout()
        icon_layout.setSpacing(5)

        # Save As button
        save_as_btn = QPushButton("💾")
        save_as_btn.setFixedWidth(45)
        save_as_btn.setToolTip("Save As...")
        save_as_btn.clicked.connect(self._save_config)
        icon_layout.addWidget(save_as_btn)

        # Load button
        load_btn = QPushButton("📁")
        load_btn.setFixedWidth(45)
        load_btn.setToolTip("Load Config")
        load_btn.clicked.connect(self._load_config)
        icon_layout.addWidget(load_btn)

        # Reset button
        reset_btn = QPushButton("🔄")
        reset_btn.setFixedWidth(45)
        reset_btn.setToolTip("Reset to Defaults")
        reset_btn.clicked.connect(self._reset_defaults)
        icon_layout.addWidget(reset_btn)

        # Test button
        test_btn = QPushButton("📡")
        test_btn.setFixedWidth(45)
        test_btn.setToolTip("Test Connection")
        test_btn.clicked.connect(self._test_connection)
        icon_layout.addWidget(test_btn)

        layout.addLayout(icon_layout)

        return frame

    def _create_sections(self):
        """Create content sections for each configuration area."""
        # General Settings
        general_tab = GeneralSettingsTab(self)
        self.tab_objects['general'] = general_tab
        self.content_stack.addWidget(general_tab.build())

        # Search Settings
        search_tab = SearchSettingsTab(self)
        self.tab_objects['search'] = search_tab
        self.content_stack.addWidget(search_tab.build())

        # Agent Configuration Sections
        agent_types = [
            ('query_agent', 'Query Agent'),
            ('scoring_agent', 'Scoring Agent'),
            ('citation_agent', 'Citation Agent'),
            ('reporting_agent', 'Reporting Agent'),
            ('counterfactual_agent', 'Counterfactual Agent'),
            ('editor_agent', 'Editor Agent')
        ]

        for agent_key, display_name in agent_types:
            agent_tab = AgentConfigTab(self, agent_key, display_name)
            self.tab_objects[agent_key] = agent_tab
            self.content_stack.addWidget(agent_tab.build())

    @Slot(int)
    def _on_nav_changed(self, index: int):
        """Handle navigation selection changes.

        Args:
            index: Selected row index in navigation list
        """
        item = self.nav_list.item(index)
        if item:
            key = item.data(Qt.ItemDataRole.UserRole)
            if key:  # Only switch if item has a key (not a header)
                self._switch_section(key)

    def _switch_section(self, section_key: str):
        """Switch to a different configuration section.

        Args:
            section_key: Key of the section to switch to
        """
        self.current_section = section_key

        # Find the index for the content stack
        section_keys = ['general', 'search',
                       'query_agent', 'scoring_agent', 'citation_agent',
                       'reporting_agent', 'counterfactual_agent', 'editor_agent']

        if section_key in section_keys:
            index = section_keys.index(section_key)
            self.content_stack.setCurrentIndex(index)

    @Slot()
    def _apply_changes(self):
        """Apply configuration changes to the current session without restart."""
        try:
            print("🔄 Applying configuration changes...")

            # Update config from UI
            self._update_config_from_ui()

            # Emit signal to parent to reinitialize agents
            self.agents_need_reinit.emit()

            # Show success message
            QMessageBox.information(
                self,
                "Changes Applied",
                "✅ Configuration changes have been applied!\n\n"
                "Agents will be reinitialized with new settings.\n"
                "Changes are active immediately.\n\n"
                "💡 Tip: Use 'Save Config' to persist changes to disk."
            )

        except Exception as ex:
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to apply changes:\n{str(ex)}"
            )

    @Slot()
    def _save_config(self):
        """Save current configuration to file."""
        try:
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "Save Configuration File",
                str(Path.home() / ".bmlibrarian" / "config.json"),
                "JSON Files (*.json)"
            )

            if file_path:
                # Update config from UI before saving
                self._update_config_from_ui()

                # Save configuration
                self.config.save_config(file_path)

                # Verify the file was created
                if os.path.exists(file_path):
                    file_size = os.path.getsize(file_path)
                    QMessageBox.information(
                        self,
                        "Success",
                        f"✅ Configuration saved to:\n{os.path.basename(file_path)}\n\n"
                        f"File size: {file_size} bytes"
                    )
                else:
                    QMessageBox.warning(
                        self,
                        "Warning",
                        "Configuration file was not created"
                    )

        except Exception as ex:
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to save configuration:\n{str(ex)}"
            )

    @Slot()
    def _load_config(self):
        """Load configuration from file."""
        try:
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                "Load Configuration File",
                str(Path.home() / ".bmlibrarian"),
                "JSON Files (*.json)"
            )

            if file_path:
                import json
                with open(file_path, 'r') as f:
                    config_data = json.load(f)

                # Update configuration
                self.config._merge_config(config_data)

                # Refresh all tabs
                self._refresh_all_tabs()

                QMessageBox.information(
                    self,
                    "Success",
                    "✅ Configuration loaded successfully!"
                )

        except Exception as ex:
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to load configuration:\n{str(ex)}"
            )

    @Slot()
    def _save_to_default(self):
        """Save configuration to default location ~/.bmlibrarian/config.json"""
        try:
            # Update config from UI before saving
            self._update_config_from_ui()

            # Save to default location
            self.config.save_config(None)

            # Get the actual path
            default_path = Path.home() / ".bmlibrarian" / "config.json"

            # Verify the file was created
            if default_path.exists():
                file_size = default_path.stat().st_size
                QMessageBox.information(
                    self,
                    "Configuration Saved",
                    f"✅ Your configuration has been saved successfully!\n\n"
                    f"Location: {default_path}\n"
                    f"Size: {file_size} bytes\n\n"
                    "Changes will be loaded on next application start.\n"
                    "Use 'Apply Changes' for immediate effect."
                )
            else:
                QMessageBox.warning(
                    self,
                    "Warning",
                    "Configuration file was not created at default location"
                )

        except Exception as ex:
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to save configuration:\n{str(ex)}"
            )

    @Slot()
    def _reset_defaults(self):
        """Reset configuration to defaults."""
        reply = QMessageBox.question(
            self,
            "Reset Configuration",
            "Are you sure you want to reset all settings to defaults?\n\n"
            "This will discard all current changes.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                # Reset to defaults
                self.config._config = DEFAULT_CONFIG.copy()
                self._refresh_all_tabs()

                QMessageBox.information(
                    self,
                    "Reset Complete",
                    "⚠️ Configuration reset to defaults!\n\n"
                    "Click 'Save Config' to persist changes."
                )

            except Exception as ex:
                QMessageBox.critical(
                    self,
                    "Error",
                    f"Failed to reset configuration:\n{str(ex)}"
                )

    @Slot()
    def _test_connection(self):
        """Test connection to Ollama server."""
        host = self.config.get_ollama_config()['host']

        try:
            # Use centralized utility function
            models = list_ollama_models(host=host)

            if models:
                QMessageBox.information(
                    self,
                    "Connection Test",
                    f"✅ Connected to {host}\n\n"
                    f"Found {len(models)} models:\n" +
                    "\n".join(f"  • {m}" for m in models[:5]) +
                    (f"\n  ... and {len(models) - 5} more" if len(models) > 5 else "")
                )
            else:
                QMessageBox.warning(
                    self,
                    "Connection Test",
                    f"✅ Connected to {host}\n\n"
                    "But no models are installed."
                )

        except Exception as ex:
            QMessageBox.critical(
                self,
                "Connection Test Failed",
                f"❌ Failed to connect to {host}\n\n"
                f"Error: {str(ex)}"
            )

    def _update_config_from_ui(self):
        """Update configuration from all UI components."""
        try:
            # Update general settings
            general_tab = self.tab_objects.get('general')
            if general_tab and hasattr(general_tab, 'update_config'):
                general_tab.update_config()

            # Update search settings
            search_tab = self.tab_objects.get('search')
            if search_tab and hasattr(search_tab, 'update_config'):
                search_tab.update_config()

            # Update agent tabs
            agent_types = ['query_agent', 'scoring_agent', 'citation_agent',
                          'reporting_agent', 'counterfactual_agent', 'editor_agent']
            for agent_key in agent_types:
                agent_tab = self.tab_objects.get(agent_key)
                if agent_tab and hasattr(agent_tab, 'update_config'):
                    agent_tab.update_config()

            print("✅ Configuration updated from UI")

        except Exception as ex:
            print(f"❌ Error updating config from UI: {ex}")

    def _refresh_all_tabs(self):
        """Refresh all tabs with current configuration."""
        for key, tab in self.tab_objects.items():
            if hasattr(tab, 'refresh'):
                tab.refresh()


class SettingsPlugin(BaseTabPlugin):
    """Plugin for Settings and Configuration interface."""

    def __init__(self):
        """Initialize Settings plugin."""
        super().__init__()
        self.settings_widget: Optional[SettingsWidget] = None

    def get_metadata(self) -> TabPluginMetadata:
        """
        Get plugin metadata.

        Returns:
            Plugin metadata including ID, name, and description
        """
        return TabPluginMetadata(
            plugin_id="settings",
            display_name="Settings",
            description="Configuration interface for BMLibrarian agents and system settings",
            version="1.0.0",
            icon="settings",
            requires=[]
        )

    def create_widget(self, parent: Optional[QWidget] = None) -> QWidget:
        """
        Create the main widget for this tab.

        Args:
            parent: Optional parent widget

        Returns:
            Main Settings widget
        """
        self.settings_widget = SettingsWidget(parent)

        # Connect signals
        self.settings_widget.agents_need_reinit.connect(
            lambda: self.status_changed.emit("Configuration updated - agents reinitialized")
        )

        return self.settings_widget

    def on_tab_activated(self):
        """Called when this tab becomes active."""
        self.status_changed.emit("Settings tab activated - Configure agents and system")

    def on_tab_deactivated(self):
        """Called when this tab is deactivated."""
        pass

    def cleanup(self):
        """Cleanup resources when plugin is unloaded."""
        if self.settings_widget:
            try:
                self.settings_widget.agents_need_reinit.disconnect()
            except RuntimeError:
                pass  # Already disconnected


def create_plugin() -> BaseTabPlugin:
    """
    Plugin factory function.

    Returns:
        Initialized SettingsPlugin instance
    """
    return SettingsPlugin()
