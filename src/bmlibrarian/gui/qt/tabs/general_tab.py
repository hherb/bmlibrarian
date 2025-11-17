"""
General Settings Tab for BMLibrarian Qt GUI.
Mirrors functionality from bmlibrarian/gui/tabs/general_tab.py
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QCheckBox, QGroupBox, QScrollArea, QFrame
)
from PySide6.QtCore import Qt
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..plugins.settings.plugin import SettingsPlugin


class GeneralSettingsTab:
    """General settings configuration tab for Qt GUI."""

    def __init__(self, settings_plugin: "SettingsPlugin"):
        """Initialize general settings tab.

        Args:
            settings_plugin: Parent settings plugin instance
        """
        self.settings_plugin = settings_plugin
        self.config = settings_plugin.config
        self.controls = {}

    def build(self) -> QWidget:
        """Build the general settings tab content.

        Returns:
            QWidget containing all general settings controls
        """
        # Main widget with scroll area
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        # Create scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setSpacing(15)
        scroll_layout.setContentsMargins(15, 15, 15, 15)

        # Build sections
        scroll_layout.addWidget(self._build_ollama_section())
        scroll_layout.addWidget(self._create_divider())
        scroll_layout.addWidget(self._build_database_section())
        scroll_layout.addWidget(self._create_divider())
        scroll_layout.addWidget(self._build_cli_section())
        scroll_layout.addStretch()

        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll)

        return widget

    def _create_divider(self) -> QFrame:
        """Create a horizontal divider line."""
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        return line

    def _build_ollama_section(self) -> QGroupBox:
        """Build Ollama configuration section."""
        group = QGroupBox("Ollama Settings")
        group.setStyleSheet("""
            QGroupBox {
                font-size: 12pt;
                font-weight: bold;
                border: 2px solid #CCCCCC;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)

        layout = QVBoxLayout()
        layout.setSpacing(10)

        ollama_config = self.config.get_ollama_config()

        # Ollama Host
        host_layout = QHBoxLayout()
        host_label = QLabel("Ollama Host:")
        host_label.setFixedWidth(150)
        self.controls['ollama_host'] = QLineEdit()
        self.controls['ollama_host'].setText(ollama_config.get('host', 'http://localhost:11434'))
        self.controls['ollama_host'].setPlaceholderText("e.g., http://localhost:11434")
        host_layout.addWidget(host_label)
        host_layout.addWidget(self.controls['ollama_host'])
        layout.addLayout(host_layout)

        # Timeout and Retries row
        params_layout = QHBoxLayout()

        # Timeout
        timeout_label = QLabel("Timeout (seconds):")
        timeout_label.setFixedWidth(150)
        self.controls['ollama_timeout'] = QLineEdit()
        self.controls['ollama_timeout'].setText(str(ollama_config.get('timeout', 120)))
        self.controls['ollama_timeout'].setFixedWidth(100)
        params_layout.addWidget(timeout_label)
        params_layout.addWidget(self.controls['ollama_timeout'])

        params_layout.addSpacing(30)

        # Max Retries
        retries_label = QLabel("Max Retries:")
        retries_label.setFixedWidth(100)
        self.controls['ollama_retries'] = QLineEdit()
        self.controls['ollama_retries'].setText(str(ollama_config.get('max_retries', 3)))
        self.controls['ollama_retries'].setFixedWidth(100)
        params_layout.addWidget(retries_label)
        params_layout.addWidget(self.controls['ollama_retries'])

        params_layout.addStretch()
        layout.addLayout(params_layout)

        group.setLayout(layout)
        return group

    def _build_database_section(self) -> QGroupBox:
        """Build database configuration section."""
        group = QGroupBox("Database Settings")
        group.setStyleSheet("""
            QGroupBox {
                font-size: 12pt;
                font-weight: bold;
                border: 2px solid #CCCCCC;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)

        layout = QVBoxLayout()
        layout.setSpacing(10)

        db_config = self.config.get_database_config()

        # Max Results and Batch Size row
        params_layout = QHBoxLayout()

        # Max Results
        max_results_label = QLabel("Max Results Per Query:")
        max_results_label.setFixedWidth(150)
        self.controls['max_results'] = QLineEdit()
        self.controls['max_results'].setText(str(db_config.get('max_results_per_query', 10)))
        self.controls['max_results'].setFixedWidth(100)
        params_layout.addWidget(max_results_label)
        params_layout.addWidget(self.controls['max_results'])

        params_layout.addSpacing(30)

        # Batch Size
        batch_label = QLabel("Batch Size:")
        batch_label.setFixedWidth(100)
        self.controls['batch_size'] = QLineEdit()
        self.controls['batch_size'].setText(str(db_config.get('batch_size', 50)))
        self.controls['batch_size'].setFixedWidth(100)
        params_layout.addWidget(batch_label)
        params_layout.addWidget(self.controls['batch_size'])

        params_layout.addStretch()
        layout.addLayout(params_layout)

        # Use Ranking checkbox
        self.controls['use_ranking'] = QCheckBox("Use document ranking")
        self.controls['use_ranking'].setChecked(db_config.get('use_ranking', False))
        self.controls['use_ranking'].setToolTip("Enable document ranking algorithms")
        layout.addWidget(self.controls['use_ranking'])

        group.setLayout(layout)
        return group

    def _build_cli_section(self) -> QGroupBox:
        """Build CLI configuration section."""
        group = QGroupBox("CLI Settings")
        group.setStyleSheet("""
            QGroupBox {
                font-size: 12pt;
                font-weight: bold;
                border: 2px solid #CCCCCC;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)

        layout = QVBoxLayout()
        layout.setSpacing(10)

        search_config = self.config.get_search_config()

        # Max Search Results and Display Limit row
        params_layout = QHBoxLayout()

        # Max Search Results
        max_search_label = QLabel("Max Search Results:")
        max_search_label.setFixedWidth(150)
        self.controls['max_search_results'] = QLineEdit()
        self.controls['max_search_results'].setText(str(search_config.get('max_results', 100)))
        self.controls['max_search_results'].setFixedWidth(100)
        params_layout.addWidget(max_search_label)
        params_layout.addWidget(self.controls['max_search_results'])

        params_layout.addSpacing(30)

        # Display Limit
        display_label = QLabel("Display Limit:")
        display_label.setFixedWidth(100)
        self.controls['display_limit'] = QLineEdit()
        self.controls['display_limit'].setText(str(search_config.get('display_limit', 20)))
        self.controls['display_limit'].setFixedWidth(100)
        params_layout.addWidget(display_label)
        params_layout.addWidget(self.controls['display_limit'])

        params_layout.addStretch()
        layout.addLayout(params_layout)

        group.setLayout(layout)
        return group

    def update_config(self):
        """Update configuration from UI controls."""
        try:
            # Update Ollama config
            ollama_config = self.config.get_ollama_config()
            ollama_config['host'] = self.controls['ollama_host'].text()
            ollama_config['timeout'] = int(self.controls['ollama_timeout'].text())
            ollama_config['max_retries'] = int(self.controls['ollama_retries'].text())

            # Update Database config
            db_config = self.config.get_database_config()
            db_config['max_results_per_query'] = int(self.controls['max_results'].text())
            db_config['batch_size'] = int(self.controls['batch_size'].text())
            db_config['use_ranking'] = self.controls['use_ranking'].isChecked()

            # Update CLI/Search config
            search_config = self.config.get_search_config()
            search_config['max_results'] = int(self.controls['max_search_results'].text())
            search_config['display_limit'] = int(self.controls['display_limit'].text())

        except ValueError as e:
            print(f"Error updating config from general settings: {e}")

    def refresh(self):
        """Refresh UI controls with current configuration values."""
        ollama_config = self.config.get_ollama_config()
        self.controls['ollama_host'].setText(ollama_config.get('host', 'http://localhost:11434'))
        self.controls['ollama_timeout'].setText(str(ollama_config.get('timeout', 120)))
        self.controls['ollama_retries'].setText(str(ollama_config.get('max_retries', 3)))

        db_config = self.config.get_database_config()
        self.controls['max_results'].setText(str(db_config.get('max_results_per_query', 10)))
        self.controls['batch_size'].setText(str(db_config.get('batch_size', 50)))
        self.controls['use_ranking'].setChecked(db_config.get('use_ranking', False))

        search_config = self.config.get_search_config()
        self.controls['max_search_results'].setText(str(search_config.get('max_results', 100)))
        self.controls['display_limit'].setText(str(search_config.get('display_limit', 20)))
