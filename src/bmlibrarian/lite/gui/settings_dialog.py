"""
Settings dialog for BMLibrarian Lite.

Provides configuration interface for:
- LLM settings (model selection)
- Embedding model settings
- PubMed API settings
- API keys
"""

import logging
import os
from typing import Optional

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QVBoxLayout,
    QFormLayout,
    QLineEdit,
    QComboBox,
    QGroupBox,
    QLabel,
    QDialogButtonBox,
    QDoubleSpinBox,
    QMessageBox,
    QSpinBox,
)

from bmlibrarian.gui.qt.resources.styles.dpi_scale import scaled

from ..config import LiteConfig
from ..embeddings import LiteEmbedder
from ..constants import (
    DEFAULT_LLM_MODEL,
    DEFAULT_LLM_TEMPERATURE,
    DEFAULT_LLM_MAX_TOKENS,
)

logger = logging.getLogger(__name__)

# Available Claude models
CLAUDE_MODELS = [
    "claude-sonnet-4-20250514",
    "claude-3-5-sonnet-20241022",
    "claude-3-haiku-20240307",
    "claude-3-opus-20240229",
]


class SettingsDialog(QDialog):
    """
    Settings configuration dialog.

    Allows users to configure:
    - LLM model and parameters
    - Embedding model
    - PubMed API credentials
    - Anthropic API key

    Attributes:
        config: Lite configuration to modify
    """

    def __init__(
        self,
        config: LiteConfig,
        parent: Optional[QDialog] = None,
    ) -> None:
        """
        Initialize the settings dialog.

        Args:
            config: Lite configuration to modify
            parent: Optional parent widget
        """
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("Settings")
        self.setMinimumWidth(scaled(450))

        self._setup_ui()
        self._load_config()

    def _setup_ui(self) -> None:
        """Set up the user interface."""
        layout = QVBoxLayout(self)
        layout.setSpacing(scaled(12))

        # LLM settings
        llm_group = QGroupBox("LLM Settings")
        llm_layout = QFormLayout(llm_group)

        self.model_combo = QComboBox()
        self.model_combo.addItems(CLAUDE_MODELS)
        self.model_combo.setToolTip("Claude model to use for text generation")
        llm_layout.addRow("Model:", self.model_combo)

        self.temperature_spin = QDoubleSpinBox()
        self.temperature_spin.setRange(0.0, 1.0)
        self.temperature_spin.setSingleStep(0.1)
        self.temperature_spin.setValue(DEFAULT_LLM_TEMPERATURE)
        self.temperature_spin.setToolTip(
            "Lower values are more focused, higher values more creative"
        )
        llm_layout.addRow("Temperature:", self.temperature_spin)

        self.max_tokens_spin = QSpinBox()
        self.max_tokens_spin.setRange(100, 8000)
        self.max_tokens_spin.setSingleStep(100)
        self.max_tokens_spin.setValue(DEFAULT_LLM_MAX_TOKENS)
        self.max_tokens_spin.setToolTip("Maximum tokens in generated response")
        llm_layout.addRow("Max Tokens:", self.max_tokens_spin)

        layout.addWidget(llm_group)

        # Embedding settings
        embed_group = QGroupBox("Embedding Settings")
        embed_layout = QFormLayout(embed_group)

        self.embed_combo = QComboBox()
        try:
            self.embed_combo.addItems(LiteEmbedder.list_supported_models())
        except Exception:
            self.embed_combo.addItem("BAAI/bge-small-en-v1.5")
        self.embed_combo.setToolTip("Embedding model for semantic search")
        embed_layout.addRow("Model:", self.embed_combo)

        embed_note = QLabel(
            "<small>Changing embedding model requires re-indexing documents</small>"
        )
        embed_layout.addRow(embed_note)

        layout.addWidget(embed_group)

        # PubMed settings
        pubmed_group = QGroupBox("PubMed Settings")
        pubmed_layout = QFormLayout(pubmed_group)

        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText("your.email@example.com (recommended)")
        self.email_input.setToolTip(
            "Email for NCBI identification (polite access)"
        )
        pubmed_layout.addRow("Email:", self.email_input)

        self.api_key_input = QLineEdit()
        self.api_key_input.setPlaceholderText("Optional - increases rate limit to 10/sec")
        self.api_key_input.setEchoMode(QLineEdit.Password)
        self.api_key_input.setToolTip(
            "NCBI API key for higher rate limits (optional)"
        )
        pubmed_layout.addRow("API Key:", self.api_key_input)

        layout.addWidget(pubmed_group)

        # API Keys
        api_group = QGroupBox("API Keys")
        api_layout = QFormLayout(api_group)

        self.anthropic_key_input = QLineEdit()
        self.anthropic_key_input.setEchoMode(QLineEdit.Password)
        self.anthropic_key_input.setPlaceholderText("sk-ant-...")
        self.anthropic_key_input.setToolTip("Anthropic API key for Claude")
        api_layout.addRow("Anthropic:", self.anthropic_key_input)

        # Load existing API key from environment
        existing_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if existing_key:
            self.anthropic_key_input.setPlaceholderText("(key is set)")

        api_note = QLabel(
            f"<small>API keys are stored securely in "
            f"{self.config.storage.env_file}</small>"
        )
        api_layout.addRow(api_note)

        layout.addWidget(api_group)

        # OpenAthens settings
        openathens_group = QGroupBox("OpenAthens Institutional Access")
        openathens_layout = QFormLayout(openathens_group)

        self.openathens_enabled = QCheckBox("Enable OpenAthens authentication")
        self.openathens_enabled.setToolTip(
            "Enable institutional access to paywalled PDFs via OpenAthens"
        )
        self.openathens_enabled.stateChanged.connect(self._on_openathens_enabled_changed)
        openathens_layout.addRow(self.openathens_enabled)

        self.openathens_url_input = QLineEdit()
        self.openathens_url_input.setPlaceholderText("https://go.openathens.net/redirector/yourinstitution.edu.au")
        self.openathens_url_input.setToolTip(
            "Your institution's OpenAthens Redirector URL or domain.\n"
            "Examples:\n"
            "- https://go.openathens.net/redirector/jcu.edu.au\n"
            "- jcu.edu.au (domain only - will auto-convert)"
        )
        openathens_layout.addRow("Redirector URL:", self.openathens_url_input)

        self.openathens_session_age = QSpinBox()
        self.openathens_session_age.setRange(1, 168)  # 1 hour to 1 week
        self.openathens_session_age.setValue(24)
        self.openathens_session_age.setSuffix(" hours")
        self.openathens_session_age.setToolTip(
            "Maximum session age before re-authentication required"
        )
        openathens_layout.addRow("Session Max Age:", self.openathens_session_age)

        openathens_note = QLabel(
            "<small>OpenAthens allows access to paywalled content through "
            "your institution's subscription. Find the OpenAthens Redirector URL "
            "on your library's website (search for 'OpenAthens Link Generator').<br>"
            "You can also just enter your institution's domain (e.g., jcu.edu.au).</small>"
        )
        openathens_note.setWordWrap(True)
        openathens_layout.addRow(openathens_note)

        layout.addWidget(openathens_group)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self._save_config)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _load_config(self) -> None:
        """Load current configuration into fields."""
        # LLM
        idx = self.model_combo.findText(self.config.llm.model)
        if idx >= 0:
            self.model_combo.setCurrentIndex(idx)
        else:
            # Model not in list, add it
            self.model_combo.addItem(self.config.llm.model)
            self.model_combo.setCurrentText(self.config.llm.model)

        self.temperature_spin.setValue(self.config.llm.temperature)
        self.max_tokens_spin.setValue(self.config.llm.max_tokens)

        # Embeddings
        idx = self.embed_combo.findText(self.config.embeddings.model)
        if idx >= 0:
            self.embed_combo.setCurrentIndex(idx)

        # PubMed
        self.email_input.setText(self.config.pubmed.email)
        if self.config.pubmed.api_key:
            self.api_key_input.setText(self.config.pubmed.api_key)

        # OpenAthens
        self.openathens_enabled.setChecked(self.config.openathens.enabled)
        self.openathens_url_input.setText(self.config.openathens.institution_url)
        self.openathens_session_age.setValue(self.config.openathens.session_max_age_hours)
        # Update field enabled state
        self._on_openathens_enabled_changed()

    def _save_config(self) -> None:
        """Save configuration and close dialog."""
        # Update config object
        self.config.llm.model = self.model_combo.currentText()
        self.config.llm.temperature = self.temperature_spin.value()
        self.config.llm.max_tokens = self.max_tokens_spin.value()

        self.config.embeddings.model = self.embed_combo.currentText()

        self.config.pubmed.email = self.email_input.text().strip()
        api_key = self.api_key_input.text().strip()
        self.config.pubmed.api_key = api_key if api_key else None

        # OpenAthens - validate URL or domain before saving
        openathens_url = self.openathens_url_input.text().strip()
        if self.openathens_enabled.isChecked() and openathens_url:
            # Allow either full HTTPS URL or domain-only input
            is_domain_only = (
                '.' in openathens_url and
                not openathens_url.startswith('http') and
                '/' not in openathens_url
            )
            if not is_domain_only and not openathens_url.startswith("https://"):
                QMessageBox.warning(
                    self,
                    "Invalid URL",
                    "OpenAthens URL must start with https:// for security,\n"
                    "or enter just your institution's domain (e.g., jcu.edu.au)."
                )
                return

        self.config.openathens.enabled = self.openathens_enabled.isChecked()
        self.config.openathens.institution_url = openathens_url
        self.config.openathens.session_max_age_hours = self.openathens_session_age.value()

        # Save to file
        self.config.save()

        # Handle Anthropic API key separately (in .env)
        anthropic_key = self.anthropic_key_input.text().strip()
        if anthropic_key:
            self._save_api_key("ANTHROPIC_API_KEY", anthropic_key)

        logger.info("Settings saved")
        self.accept()

    def _save_api_key(self, key: str, value: str) -> None:
        """
        Save an API key to .env file.

        Args:
            key: Environment variable name
            value: API key value
        """
        env_path = self.config.storage.env_file

        # Ensure directory exists
        env_path.parent.mkdir(parents=True, exist_ok=True)

        # Read existing .env
        lines = []
        if env_path.exists():
            with open(env_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()

        # Update or add key
        found = False
        for i, line in enumerate(lines):
            if line.startswith(f"{key}="):
                lines[i] = f"{key}={value}\n"
                found = True
                break

        if not found:
            lines.append(f"{key}={value}\n")

        # Write back
        with open(env_path, 'w', encoding='utf-8') as f:
            f.writelines(lines)

        # Set restrictive permissions
        try:
            env_path.chmod(0o600)
        except OSError:
            pass  # May fail on Windows

        # Also set in current environment
        os.environ[key] = value

    def _on_openathens_enabled_changed(self) -> None:
        """Handle OpenAthens enabled checkbox state change."""
        enabled = self.openathens_enabled.isChecked()
        self.openathens_url_input.setEnabled(enabled)
        self.openathens_session_age.setEnabled(enabled)
