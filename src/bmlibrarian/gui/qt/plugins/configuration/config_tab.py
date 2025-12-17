"""
Configuration tab widget for BMLibrarian Qt GUI.

Main interface for configuration and settings.
Supports both JSON file storage and database-backed user settings.
"""

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QTabWidget,
    QMessageBox,
    QFileDialog,
    QLabel,
    QFrame,
)
from PySide6.QtCore import Qt, Signal, Slot
from typing import Optional
import json
import logging
from pathlib import Path

from .general_settings_widget import GeneralSettingsWidget
from .agent_config_widget import AgentConfigWidget
from .query_generation_widget import QueryGenerationWidget
from .....config import get_config, DEFAULT_CONFIG
from .....llm import list_ollama_models
from ...resources.styles import get_font_scale
from ...resources.styles.stylesheet_generator import StylesheetGenerator

logger = logging.getLogger(__name__)


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

        self.scale = get_font_scale()

        # Load current configuration
        # get_config() returns a BMLibrarianConfig object, but we need a dict
        bmlib_config = get_config()
        # Convert to dict by accessing the internal _config
        if hasattr(bmlib_config, '_config'):
            self.config = bmlib_config._config.copy()
        else:
            # Fallback: create a basic config structure
            self.config = DEFAULT_CONFIG.copy()

        self.config_widgets = {}

        self._setup_ui()

    def _setup_ui(self):
        """Setup the user interface."""
        s = self.scale
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(s['padding_medium'], s['padding_medium'], s['padding_medium'], s['padding_medium'])

        # Add database sync status bar
        self._create_sync_status_bar(main_layout)

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

        # Load available models from Ollama on startup
        self._load_initial_models()

    def _create_sync_status_bar(self, parent_layout: QVBoxLayout) -> None:
        """Create the database sync status bar.

        Shows whether the user is authenticated and settings are database-backed.

        Args:
            parent_layout: Parent layout to add the status bar to
        """
        s = self.scale
        bmlib_config = get_config()

        # Create status frame
        status_frame = QFrame()
        status_frame.setFrameShape(QFrame.Shape.StyledPanel)
        status_layout = QHBoxLayout(status_frame)
        status_layout.setContentsMargins(
            s['padding_small'], s['padding_small'],
            s['padding_small'], s['padding_small']
        )

        # Status label
        if bmlib_config.has_user_context():
            user_id = bmlib_config.get_user_id()
            status_text = f"✓ Database-backed settings (User ID: {user_id})"
            status_color = "#27ae60"  # Green
            self._db_sync_enabled = True
        else:
            status_text = "⚠ Using local JSON settings (not authenticated)"
            status_color = "#f39c12"  # Orange
            self._db_sync_enabled = False

        self.sync_status_label = QLabel(status_text)
        gen = StylesheetGenerator(s)
        self.sync_status_label.setStyleSheet(gen.label_stylesheet(color=status_color, bold=True))
        status_layout.addWidget(self.sync_status_label)

        status_layout.addStretch()

        # Sync buttons (only enabled when authenticated)
        self.sync_to_db_btn = QPushButton("Sync to Database")
        self.sync_to_db_btn.clicked.connect(self._sync_to_database)
        self.sync_to_db_btn.setEnabled(self._db_sync_enabled)
        self.sync_to_db_btn.setToolTip(
            "Save current settings to database" if self._db_sync_enabled
            else "Login required for database sync"
        )
        status_layout.addWidget(self.sync_to_db_btn)

        self.sync_from_db_btn = QPushButton("Sync from Database")
        self.sync_from_db_btn.clicked.connect(self._sync_from_database)
        self.sync_from_db_btn.setEnabled(self._db_sync_enabled)
        self.sync_from_db_btn.setToolTip(
            "Load settings from database" if self._db_sync_enabled
            else "Login required for database sync"
        )
        status_layout.addWidget(self.sync_from_db_btn)

        parent_layout.addWidget(status_frame)

    def _create_button_layout(self) -> QHBoxLayout:
        """
        Create action button layout.

        Returns:
            Button layout
        """
        s = self.scale
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        # Save to default location button
        save_default_btn = QPushButton("Save to ~/.bmlibrarian")
        save_default_btn.clicked.connect(self._save_to_default)
        # Styling handled by centralized theme
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
        # Styling handled by centralized theme
        button_layout.addWidget(reset_btn)

        # Test Connection button
        test_btn = QPushButton("Test Connection")
        test_btn.clicked.connect(self._test_connection)
        gen = StylesheetGenerator(s)
        test_btn.setStyleSheet(gen.button_stylesheet(
            bg_color="#3498db",
            hover_color="#2980b9"
        ))
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
        """Save configuration to default location (~/.bmlibrarian/config.json).

        If user is authenticated, also syncs to database automatically.
        """
        try:
            config = self._collect_config()
            bmlib_config = get_config()

            # Update the BMLibrarianConfig with collected settings
            for category, settings in config.items():
                if isinstance(settings, dict):
                    for key, value in settings.items():
                        bmlib_config.set(f"{category}.{key}", value)

            # Export to JSON file
            config_path = Path.home() / ".bmlibrarian" / "config.json"
            bmlib_config.export_to_json(config_path)

            # If authenticated, also sync to database
            sync_msg = ""
            if bmlib_config.has_user_context():
                try:
                    bmlib_config.sync_to_database()
                    sync_msg = " and synced to database"
                    logger.info("Configuration synced to database")
                except Exception as db_e:
                    logger.warning(f"Failed to sync to database: {db_e}")
                    sync_msg = " (database sync failed)"

            self.status_message.emit(f"Configuration saved to ~/.bmlibrarian/config.json{sync_msg}")
            self.config_saved.emit(str(config_path))

            QMessageBox.information(
                self,
                "Success",
                f"Configuration saved to ~/.bmlibrarian/config.json{sync_msg}",
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
            ollama_url = self.general_widget.get_ollama_url()

            # Use centralized utility function
            models = list_ollama_models(host=ollama_url)

            if not models:
                raise ConnectionError("Could not retrieve models from Ollama server")

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

        except Exception as e:
            QMessageBox.critical(
                self,
                "Connection Failed",
                f"Failed to connect to Ollama server:\n\n{str(e)}",
            )
            self.status_message.emit(f"Ollama connection failed: {str(e)}")

    @Slot()
    def _sync_to_database(self) -> None:
        """Sync current configuration to database.

        Requires user to be authenticated.
        """
        if not self._db_sync_enabled:
            QMessageBox.warning(
                self,
                "Authentication Required",
                "You must be logged in to sync settings to the database."
            )
            return

        try:
            config = self._collect_config()
            bmlib_config = get_config()

            # Update the BMLibrarianConfig with collected settings
            for category, settings in config.items():
                if isinstance(settings, dict):
                    for key, value in settings.items():
                        bmlib_config.set(f"{category}.{key}", value)

            # Sync to database
            bmlib_config.sync_to_database()

            self.status_message.emit("Configuration synced to database")
            logger.info("Configuration synced to database successfully")

            QMessageBox.information(
                self,
                "Success",
                "Configuration has been synced to the database."
            )

        except Exception as e:
            error_msg = f"Failed to sync to database: {str(e)}"
            QMessageBox.critical(self, "Error", error_msg)
            self.status_message.emit(error_msg)
            logger.error(error_msg)

    @Slot()
    def _sync_from_database(self) -> None:
        """Load configuration from database and update UI.

        Requires user to be authenticated.
        """
        if not self._db_sync_enabled:
            QMessageBox.warning(
                self,
                "Authentication Required",
                "You must be logged in to sync settings from the database."
            )
            return

        try:
            bmlib_config = get_config()

            # Sync from database (this updates the internal config)
            bmlib_config._sync_from_database()

            # Get the updated config and refresh UI
            if hasattr(bmlib_config, '_config'):
                config = bmlib_config._config.copy()
            else:
                config = DEFAULT_CONFIG.copy()

            # Update all widgets with loaded config
            for widget in self.config_widgets.values():
                if hasattr(widget, 'update_from_config'):
                    widget.update_from_config(config)

            self.config = config
            self.config_changed.emit(config)
            self.status_message.emit("Configuration loaded from database")
            logger.info("Configuration synced from database successfully")

            QMessageBox.information(
                self,
                "Success",
                "Configuration has been loaded from the database."
            )

        except Exception as e:
            error_msg = f"Failed to sync from database: {str(e)}"
            QMessageBox.critical(self, "Error", error_msg)
            self.status_message.emit(error_msg)
            logger.error(error_msg)

    def _load_initial_models(self):
        """Load available models from Ollama on startup."""
        try:
            ollama_url = self.general_widget.get_ollama_url()
            model_names = list_ollama_models(host=ollama_url)

            if model_names:
                self._update_all_model_widgets(model_names)
                logger.info(f"Loaded {len(model_names)} models from Ollama on startup")
            else:
                logger.warning("No models found on Ollama server during startup")

        except Exception as e:
            # Don't show error dialog on startup, just log it
            logger.warning(f"Could not load Ollama models on startup: {e}")

    def _update_all_model_widgets(self, model_names: list[str]):
        """
        Update all widgets that have model selection with the available models.

        Args:
            model_names: List of available model names from Ollama
        """
        for key, widget in self.config_widgets.items():
            if hasattr(widget, 'update_model_list'):
                widget.update_model_list(model_names)

    def refresh_models(self):
        """Refresh available models from Ollama server."""
        try:
            ollama_url = self.general_widget.get_ollama_url()

            # Use centralized utility function
            model_names = list_ollama_models(host=ollama_url)

            if not model_names:
                self.status_message.emit("No models found on Ollama server")
                return

            # Update all widgets with model selection
            self._update_all_model_widgets(model_names)

            self.status_message.emit(
                f"Refreshed {len(model_names)} models from Ollama"
            )

        except Exception as e:
            self.status_message.emit(f"Failed to refresh models: {str(e)}")
