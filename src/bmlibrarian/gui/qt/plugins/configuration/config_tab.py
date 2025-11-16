"""
Configuration tab widget for BMLibrarian Qt GUI.

Main interface for configuration and settings.
"""

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QTabWidget,
    QMessageBox,
    QFileDialog,
)
from PySide6.QtCore import Qt, Signal, Slot
from typing import Optional
import json
from pathlib import Path

from .general_settings_widget import GeneralSettingsWidget
from .agent_config_widget import AgentConfigWidget
from .query_generation_widget import QueryGenerationWidget
from .....config import get_config, save_config, DEFAULT_CONFIG


class ConfigurationTabWidget(QWidget):
    """
    Main configuration widget with sub-tabs.

    Provides interface for:
    - General settings (Ollama, database)
    - Agent configuration (each agent type)
    - Query generation settings
    - Save/load/reset functionality
    """

    # Signals
    status_message = Signal(str)
    config_changed = Signal(dict)
    config_saved = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None):
        """
        Initialize configuration tab.

        Args:
            parent: Optional parent widget
        """
        super().__init__(parent)

        self.config = get_config()
        self.config_widgets = {}

        self._setup_ui()

    def _setup_ui(self):
        """Setup the user interface."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)

        # Create tab widget for configuration sections
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabPosition(QTabWidget.North)

        # General Settings Tab
        self.general_widget = GeneralSettingsWidget(self.config)
        self.config_widgets['general'] = self.general_widget
        self.tab_widget.addTab(self.general_widget, "General Settings")

        # Agent Configuration Tabs
        agent_names = [
            ('query', 'Query Agent'),
            ('scoring', 'Scoring Agent'),
            ('citation', 'Citation Agent'),
            ('reporting', 'Reporting Agent'),
            ('counterfactual', 'Counterfactual Agent'),
            ('editor', 'Editor Agent'),
            ('fact_checker', 'Fact Checker Agent'),
        ]

        for agent_id, agent_display_name in agent_names:
            agent_widget = AgentConfigWidget(agent_id, agent_display_name, self.config)
            self.config_widgets[agent_id] = agent_widget
            self.tab_widget.addTab(agent_widget, agent_display_name)

        # Query Generation Settings Tab
        self.query_gen_widget = QueryGenerationWidget(self.config)
        self.config_widgets['query_generation'] = self.query_gen_widget
        self.tab_widget.addTab(self.query_gen_widget, "Query Generation")

        main_layout.addWidget(self.tab_widget)

        # Action buttons
        button_layout = self._create_button_layout()
        main_layout.addLayout(button_layout)

    def _create_button_layout(self) -> QHBoxLayout:
        """
        Create action button layout.

        Returns:
            Button layout
        """
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        # Save to default location button
        save_default_btn = QPushButton("Save to ~/.bmlibrarian")
        save_default_btn.clicked.connect(self._save_to_default)
        save_default_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #27ae60;
                color: white;
                font-weight: bold;
                padding: 8px 16px;
                border: none;
                border-radius: 4px;
                min-width: 180px;
            }
            QPushButton:hover {
                background-color: #229954;
            }
        """
        )
        button_layout.addWidget(save_default_btn)

        # Save As button
        save_as_btn = QPushButton("Save As...")
        save_as_btn.clicked.connect(self._save_config_as)
        button_layout.addWidget(save_as_btn)

        # Load button
        load_btn = QPushButton("Load Configuration")
        load_btn.clicked.connect(self._load_config)
        button_layout.addWidget(load_btn)

        # Reset button
        reset_btn = QPushButton("Reset to Defaults")
        reset_btn.clicked.connect(self._reset_to_defaults)
        reset_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #e67e22;
                color: white;
                padding: 8px 16px;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #d35400;
            }
        """
        )
        button_layout.addWidget(reset_btn)

        # Test Connection button
        test_btn = QPushButton("Test Connection")
        test_btn.clicked.connect(self._test_connection)
        test_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #3498db;
                color: white;
                padding: 8px 16px;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
        """
        )
        button_layout.addWidget(test_btn)

        button_layout.addStretch()

        return button_layout

    def _collect_config(self) -> dict:
        """
        Collect configuration from all widgets.

        Returns:
            Complete configuration dictionary
        """
        config = {}

        # Collect from each widget
        for widget_name, widget in self.config_widgets.items():
            if hasattr(widget, 'get_config'):
                widget_config = widget.get_config()
                config.update(widget_config)

        return config

    @Slot()
    def _save_to_default(self):
        """Save configuration to default location (~/.bmlibrarian/config.json)."""
        try:
            config = self._collect_config()

            # Save using config module
            save_config(config)

            self.status_message.emit("Configuration saved to ~/.bmlibrarian/config.json")
            self.config_saved.emit(str(Path.home() / ".bmlibrarian" / "config.json"))

            QMessageBox.information(
                self,
                "Success",
                "Configuration saved to ~/.bmlibrarian/config.json",
            )

        except Exception as e:
            QMessageBox.critical(
                self, "Error", f"Failed to save configuration: {str(e)}"
            )
            self.status_message.emit(f"Error saving configuration: {str(e)}")

    @Slot()
    def _save_config_as(self):
        """Save configuration to a user-specified file."""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Configuration As",
            str(Path.home()),
            "JSON Files (*.json);;All Files (*)",
        )

        if file_path:
            try:
                config = self._collect_config()

                with open(file_path, 'w') as f:
                    json.dump(config, f, indent=2)

                self.status_message.emit(f"Configuration saved to {file_path}")
                self.config_saved.emit(file_path)

                QMessageBox.information(
                    self, "Success", f"Configuration saved to {file_path}"
                )

            except Exception as e:
                QMessageBox.critical(
                    self, "Error", f"Failed to save configuration: {str(e)}"
                )
                self.status_message.emit(f"Error saving configuration: {str(e)}")

    @Slot()
    def _load_config(self):
        """Load configuration from a file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Configuration",
            str(Path.home()),
            "JSON Files (*.json);;All Files (*)",
        )

        if file_path:
            try:
                with open(file_path, 'r') as f:
                    config = json.load(f)

                # Update all widgets with loaded config
                for widget in self.config_widgets.values():
                    if hasattr(widget, 'update_from_config'):
                        widget.update_from_config(config)

                self.config = config
                self.config_changed.emit(config)
                self.status_message.emit(f"Configuration loaded from {file_path}")

                QMessageBox.information(
                    self, "Success", f"Configuration loaded from {file_path}"
                )

            except Exception as e:
                QMessageBox.critical(
                    self, "Error", f"Failed to load configuration: {str(e)}"
                )
                self.status_message.emit(f"Error loading configuration: {str(e)}")

    @Slot()
    def _reset_to_defaults(self):
        """Reset all settings to defaults."""
        reply = QMessageBox.question(
            self,
            "Confirm Reset",
            "Are you sure you want to reset all settings to defaults?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if reply == QMessageBox.Yes:
            # Update all widgets with default config
            for widget in self.config_widgets.values():
                if hasattr(widget, 'update_from_config'):
                    widget.update_from_config(DEFAULT_CONFIG)

            self.config = DEFAULT_CONFIG.copy()
            self.config_changed.emit(self.config)
            self.status_message.emit("Configuration reset to defaults")

            QMessageBox.information(
                self, "Success", "Configuration reset to defaults"
            )

    @Slot()
    def _test_connection(self):
        """Test connection to Ollama server."""
        self.status_message.emit("Testing Ollama connection...")

        try:
            import requests

            ollama_url = self.general_widget.get_ollama_url()
            response = requests.get(f"{ollama_url}/api/tags", timeout=5)

            if response.status_code == 200:
                models = response.json().get('models', [])
                model_count = len(models)

                QMessageBox.information(
                    self,
                    "Connection Successful",
                    f"Connected to Ollama server!\n\n"
                    f"Available models: {model_count}\n"
                    f"Server: {ollama_url}",
                )
                self.status_message.emit(
                    f"Ollama connection successful ({model_count} models)"
                )

                # Refresh models in agent widgets
                self.refresh_models()
            else:
                raise ConnectionError(f"Server returned status {response.status_code}")

        except Exception as e:
            QMessageBox.critical(
                self,
                "Connection Failed",
                f"Failed to connect to Ollama server:\n\n{str(e)}",
            )
            self.status_message.emit(f"Ollama connection failed: {str(e)}")

    def refresh_models(self):
        """Refresh available models from Ollama server."""
        try:
            import requests

            ollama_url = self.general_widget.get_ollama_url()
            response = requests.get(f"{ollama_url}/api/tags", timeout=5)

            if response.status_code == 200:
                models = response.json().get('models', [])
                model_names = [model.get('name', '') for model in models]

                # Update agent config widgets with new model list
                for key, widget in self.config_widgets.items():
                    if isinstance(widget, AgentConfigWidget):
                        widget.update_model_list(model_names)

                self.status_message.emit(
                    f"Refreshed {len(model_names)} models from Ollama"
                )

        except Exception as e:
            self.status_message.emit(f"Failed to refresh models: {str(e)}")
