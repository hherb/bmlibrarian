"""
General settings widget for BMLibrarian Qt configuration.

Handles Ollama server, database, and CLI default settings.
"""

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QLineEdit,
    QSpinBox,
    QDoubleSpinBox,
    QLabel,
    QGroupBox,
    QScrollArea,
    QCheckBox,
)
from PySide6.QtCore import Qt
from typing import Optional

from ...resources.styles import get_font_scale


class GeneralSettingsWidget(QWidget):
    """
    General settings configuration widget.

    Provides fields for:
    - Ollama server URL
    - PostgreSQL database connection
    - CLI default settings
    """

    def __init__(self, config: dict, parent: Optional[QWidget] = None):
        """
        Initialize general settings widget.

        Args:
            config: Current configuration dictionary
            parent: Optional parent widget
        """
        super().__init__(parent)
        self.scale = get_font_scale()
        self.config = config
        self._setup_ui()
        self._load_values()

    def _setup_ui(self):
        """Setup the user interface."""
        s = self.scale
        # Create scroll area for the form
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)

        container = QWidget()
        main_layout = QVBoxLayout(container)
        main_layout.setContentsMargins(s['padding_medium'], s['padding_medium'], s['padding_medium'], s['padding_medium'])

        # Ollama Settings Group
        ollama_group = self._create_ollama_group()
        main_layout.addWidget(ollama_group)

        # Database Settings Group
        database_group = self._create_database_group()
        main_layout.addWidget(database_group)

        # CLI Defaults Group
        cli_group = self._create_cli_defaults_group()
        main_layout.addWidget(cli_group)

        # PDF Discovery Settings Group
        discovery_group = self._create_discovery_group()
        main_layout.addWidget(discovery_group)

        main_layout.addStretch()

        scroll.setWidget(container)

        # Set scroll area as main widget
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll)

    def _create_ollama_group(self) -> QGroupBox:
        """
        Create Ollama settings group.

        Returns:
            Ollama settings group box
        """
        group = QGroupBox("Ollama Server Settings")
        layout = QFormLayout()

        # Ollama URL
        self.ollama_url_input = QLineEdit()
        self.ollama_url_input.setPlaceholderText("http://localhost:11434")
        layout.addRow("Ollama URL:", self.ollama_url_input)

        # Default model (informational)
        info_label = QLabel(
            "Note: Individual agent models are configured in their respective tabs."
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #7f8c8d; font-style: italic;")
        layout.addRow("", info_label)

        group.setLayout(layout)
        return group

    def _create_database_group(self) -> QGroupBox:
        """
        Create database settings group.

        Returns:
            Database settings group box
        """
        group = QGroupBox("PostgreSQL Database Settings")
        layout = QFormLayout()

        # Database name
        self.db_name_input = QLineEdit()
        self.db_name_input.setPlaceholderText("knowledgebase")
        layout.addRow("Database Name:", self.db_name_input)

        # Host
        self.db_host_input = QLineEdit()
        self.db_host_input.setPlaceholderText("localhost")
        layout.addRow("Host:", self.db_host_input)

        # Port
        self.db_port_input = QSpinBox()
        self.db_port_input.setRange(1, 65535)
        self.db_port_input.setValue(5432)
        layout.addRow("Port:", self.db_port_input)

        # User
        self.db_user_input = QLineEdit()
        self.db_user_input.setPlaceholderText("postgres")
        layout.addRow("User:", self.db_user_input)

        # Password (masked)
        self.db_password_input = QLineEdit()
        self.db_password_input.setEchoMode(QLineEdit.Password)
        self.db_password_input.setPlaceholderText("database password")
        layout.addRow("Password:", self.db_password_input)

        # Info note
        info_label = QLabel(
            "Note: Database settings are typically configured via environment variables (.env file)."
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #7f8c8d; font-style: italic;")
        layout.addRow("", info_label)

        group.setLayout(layout)
        return group

    def _create_cli_defaults_group(self) -> QGroupBox:
        """
        Create CLI defaults group.

        Returns:
            CLI defaults group box
        """
        group = QGroupBox("CLI Default Settings")
        layout = QFormLayout()

        # Max search results
        self.max_results_input = QSpinBox()
        self.max_results_input.setRange(1, 10000)
        self.max_results_input.setValue(100)
        self.max_results_input.setToolTip(
            "Default maximum number of search results"
        )
        layout.addRow("Max Search Results:", self.max_results_input)

        # Document score threshold
        self.score_threshold_input = QDoubleSpinBox()
        self.score_threshold_input.setRange(1.0, 5.0)
        self.score_threshold_input.setSingleStep(0.5)
        self.score_threshold_input.setValue(2.5)
        self.score_threshold_input.setDecimals(1)
        self.score_threshold_input.setToolTip(
            "Minimum relevance score for document inclusion (1-5 scale)"
        )
        layout.addRow("Score Threshold:", self.score_threshold_input)

        # Search timeout
        self.search_timeout_input = QSpinBox()
        self.search_timeout_input.setRange(1, 300)
        self.search_timeout_input.setValue(30)
        self.search_timeout_input.setSuffix(" seconds")
        self.search_timeout_input.setToolTip(
            "Database query timeout in seconds"
        )
        layout.addRow("Search Timeout:", self.search_timeout_input)

        group.setLayout(layout)
        return group

    def _create_discovery_group(self) -> QGroupBox:
        """
        Create PDF discovery settings group.

        Returns:
            PDF discovery settings group box
        """
        group = QGroupBox("PDF Discovery Settings")
        layout = QFormLayout()

        # Prefer open access
        self.prefer_open_access_input = QCheckBox()
        self.prefer_open_access_input.setChecked(True)
        self.prefer_open_access_input.setToolTip(
            "Prioritize open access sources (PMC, Unpaywall) over paywalled content"
        )
        layout.addRow("Prefer Open Access:", self.prefer_open_access_input)

        # Use browser fallback
        self.use_browser_fallback_input = QCheckBox()
        self.use_browser_fallback_input.setChecked(True)
        self.use_browser_fallback_input.setToolTip(
            "Use browser automation to bypass Cloudflare and anti-bot protections"
        )
        layout.addRow("Use Browser Fallback:", self.use_browser_fallback_input)

        # Browser headless mode
        self.browser_headless_input = QCheckBox()
        self.browser_headless_input.setChecked(True)
        self.browser_headless_input.setToolTip(
            "Run browser in headless mode (no visible window)"
        )
        layout.addRow("Browser Headless:", self.browser_headless_input)

        # Discovery timeout
        self.discovery_timeout_input = QSpinBox()
        self.discovery_timeout_input.setRange(5, 120)
        self.discovery_timeout_input.setValue(30)
        self.discovery_timeout_input.setSuffix(" seconds")
        self.discovery_timeout_input.setToolTip(
            "HTTP request timeout for PDF discovery"
        )
        layout.addRow("Discovery Timeout:", self.discovery_timeout_input)

        # OpenAthens proxy for discovery
        self.use_openathens_proxy_input = QCheckBox()
        self.use_openathens_proxy_input.setChecked(False)
        self.use_openathens_proxy_input.setToolTip(
            "Use OpenAthens institutional proxy as last resort for paywalled PDFs.\n"
            "Requires OpenAthens to be enabled and configured above."
        )
        layout.addRow("Use OpenAthens for Discovery:", self.use_openathens_proxy_input)

        # Info note
        info_label = QLabel(
            "Note: The 'Find PDF' button uses these settings to search PMC, "
            "Unpaywall, DOI.org, and optionally OpenAthens for full-text PDFs."
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #7f8c8d; font-style: italic;")
        layout.addRow("", info_label)

        group.setLayout(layout)
        return group

    def _load_values(self):
        """Load values from configuration."""
        # Ollama settings
        ollama_url = self.config.get('ollama', {}).get('base_url', 'http://localhost:11434')
        self.ollama_url_input.setText(ollama_url)

        # Database settings (usually from .env, but can be in config)
        db_config = self.config.get('database', {})
        self.db_name_input.setText(db_config.get('name', 'knowledgebase'))
        self.db_host_input.setText(db_config.get('host', 'localhost'))
        self.db_port_input.setValue(db_config.get('port', 5432))
        self.db_user_input.setText(db_config.get('user', ''))
        # Don't load password for security

        # CLI defaults
        cli_config = self.config.get('cli', {})
        self.max_results_input.setValue(cli_config.get('max_search_results', 100))
        self.score_threshold_input.setValue(cli_config.get('document_score_threshold', 2.5))
        self.search_timeout_input.setValue(cli_config.get('search_timeout_seconds', 30))

        # Discovery settings
        discovery_config = self.config.get('discovery', {})
        self.prefer_open_access_input.setChecked(
            discovery_config.get('prefer_open_access', True)
        )
        self.use_browser_fallback_input.setChecked(
            discovery_config.get('use_browser_fallback', True)
        )
        self.browser_headless_input.setChecked(
            discovery_config.get('browser_headless', True)
        )
        self.discovery_timeout_input.setValue(
            discovery_config.get('timeout', 30)
        )
        self.use_openathens_proxy_input.setChecked(
            discovery_config.get('use_openathens_proxy', False)
        )

    def get_config(self) -> dict:
        """
        Get configuration from widget values.

        Returns:
            Configuration dictionary
        """
        return {
            'ollama': {
                'base_url': self.ollama_url_input.text(),
            },
            'database': {
                'name': self.db_name_input.text(),
                'host': self.db_host_input.text(),
                'port': self.db_port_input.value(),
                'user': self.db_user_input.text(),
                # Only include password if it was entered
                **(
                    {'password': self.db_password_input.text()}
                    if self.db_password_input.text()
                    else {}
                ),
            },
            'cli': {
                'max_search_results': self.max_results_input.value(),
                'document_score_threshold': self.score_threshold_input.value(),
                'search_timeout_seconds': self.search_timeout_input.value(),
            },
            'discovery': {
                'prefer_open_access': self.prefer_open_access_input.isChecked(),
                'use_browser_fallback': self.use_browser_fallback_input.isChecked(),
                'browser_headless': self.browser_headless_input.isChecked(),
                'timeout': self.discovery_timeout_input.value(),
                'use_openathens_proxy': self.use_openathens_proxy_input.isChecked(),
            },
        }

    def update_from_config(self, config: dict):
        """
        Update widget from configuration.

        Args:
            config: New configuration dictionary
        """
        self.config = config
        self._load_values()

    def get_ollama_url(self) -> str:
        """
        Get Ollama URL from input field.

        Returns:
            Ollama server URL
        """
        return self.ollama_url_input.text() or 'http://localhost:11434'
