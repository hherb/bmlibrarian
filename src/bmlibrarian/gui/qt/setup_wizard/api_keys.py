"""
API Keys configuration page for the Setup Wizard.

Contains the page for optional Anthropic and OpenAI API key configuration.
"""

import logging
import os
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from PySide6.QtWidgets import (
    QWizardPage,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QGroupBox,
    QCheckBox,
    QFrame,
)

from ....utils.path_utils import write_private_text
from ..resources.styles.dpi_scale import get_font_scale
from .utils import (
    find_project_root,
    create_frame_stylesheet,
    create_muted_label_stylesheet,
)
from .constants import (
    COLOR_MUTED,
    FRAME_NOTE_BG,
    FRAME_NOTE_BORDER,
    FRAME_WARNING_BG,
    FRAME_WARNING_BORDER,
)

if TYPE_CHECKING:
    from .wizard import SetupWizard

logger = logging.getLogger(__name__)


class APIKeysPage(QWizardPage):
    """
    Page for configuring optional API keys.

    Allows users to optionally configure:
    - Anthropic API key (for Claude models)
    - OpenAI API key (for GPT models)

    These are optional and can be skipped. Keys are stored in .env file.
    """

    def __init__(self, parent: Optional["SetupWizard"] = None):
        """Initialize API keys page."""
        super().__init__(parent)
        self._wizard = parent
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the API keys page UI."""
        scale = get_font_scale()

        self.setTitle("Optional API Keys")
        self.setSubTitle(
            "Configure optional API keys for external AI services. "
            "These are not required if you're using Ollama for local inference."
        )

        layout = QVBoxLayout(self)
        layout.setSpacing(scale["spacing_large"])

        # Info note
        note_frame = QFrame()
        note_frame.setObjectName("apiKeysNote")
        note_frame.setStyleSheet(
            create_frame_stylesheet(scale, FRAME_NOTE_BG, FRAME_NOTE_BORDER, "apiKeysNote")
        )

        note_layout = QVBoxLayout(note_frame)
        note_label = QLabel(
            "BMLibrarian primarily uses local LLMs via Ollama. "
            "However, you can optionally configure API keys for cloud-based AI services.\n\n"
            "These keys will be stored in your .env file with secure permissions (readable only by you)."
        )
        note_label.setWordWrap(True)
        note_layout.addWidget(note_label)
        layout.addWidget(note_frame)

        # Anthropic API Key group
        anthropic_group = QGroupBox("Anthropic (Claude)")
        anthropic_layout = QVBoxLayout(anthropic_group)
        anthropic_layout.setSpacing(scale["spacing_medium"])

        anthropic_info = QLabel(
            "Get your API key from: https://console.anthropic.com/settings/keys"
        )
        anthropic_info.setStyleSheet(create_muted_label_stylesheet(COLOR_MUTED))
        anthropic_info.setWordWrap(True)
        anthropic_layout.addWidget(anthropic_info)

        anthropic_key_layout = QHBoxLayout()
        anthropic_key_label = QLabel("API Key:")
        anthropic_key_label.setMinimumWidth(scale["control_width_small"])
        self.anthropic_key_edit = QLineEdit()
        self.anthropic_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.anthropic_key_edit.setPlaceholderText("sk-ant-... (optional)")
        anthropic_key_layout.addWidget(anthropic_key_label)
        anthropic_key_layout.addWidget(self.anthropic_key_edit)
        anthropic_layout.addLayout(anthropic_key_layout)

        # Show/hide toggle for Anthropic key
        self.anthropic_show_check = QCheckBox("Show API key")
        self.anthropic_show_check.toggled.connect(self._toggle_anthropic_visibility)
        anthropic_layout.addWidget(self.anthropic_show_check)

        layout.addWidget(anthropic_group)

        # OpenAI API Key group
        openai_group = QGroupBox("OpenAI (GPT)")
        openai_layout = QVBoxLayout(openai_group)
        openai_layout.setSpacing(scale["spacing_medium"])

        openai_info = QLabel(
            "Get your API key from: https://platform.openai.com/api-keys"
        )
        openai_info.setStyleSheet(create_muted_label_stylesheet(COLOR_MUTED))
        openai_info.setWordWrap(True)
        openai_layout.addWidget(openai_info)

        openai_key_layout = QHBoxLayout()
        openai_key_label = QLabel("API Key:")
        openai_key_label.setMinimumWidth(scale["control_width_small"])
        self.openai_key_edit = QLineEdit()
        self.openai_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.openai_key_edit.setPlaceholderText("sk-... (optional)")
        openai_key_layout.addWidget(openai_key_label)
        openai_key_layout.addWidget(self.openai_key_edit)
        openai_layout.addLayout(openai_key_layout)

        # Show/hide toggle for OpenAI key
        self.openai_show_check = QCheckBox("Show API key")
        self.openai_show_check.toggled.connect(self._toggle_openai_visibility)
        openai_layout.addWidget(self.openai_show_check)

        layout.addWidget(openai_group)

        # Save error (hidden until a save fails)
        self.error_frame = QFrame()
        self.error_frame.setObjectName("apiKeysError")
        self.error_frame.setStyleSheet(
            create_frame_stylesheet(scale, FRAME_WARNING_BG, FRAME_WARNING_BORDER, "apiKeysError")
        )
        self.error_frame.setVisible(False)
        error_layout = QVBoxLayout(self.error_frame)
        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        error_layout.addWidget(self.error_label)
        layout.addWidget(self.error_frame)

        layout.addStretch()

        # Register fields
        self.registerField("anthropic_api_key", self.anthropic_key_edit)
        self.registerField("openai_api_key", self.openai_key_edit)

    def _toggle_anthropic_visibility(self, checked: bool) -> None:
        """Toggle visibility of Anthropic API key."""
        if checked:
            self.anthropic_key_edit.setEchoMode(QLineEdit.EchoMode.Normal)
        else:
            self.anthropic_key_edit.setEchoMode(QLineEdit.EchoMode.Password)

    def _toggle_openai_visibility(self, checked: bool) -> None:
        """Toggle visibility of OpenAI API key."""
        if checked:
            self.openai_key_edit.setEchoMode(QLineEdit.EchoMode.Normal)
        else:
            self.openai_key_edit.setEchoMode(QLineEdit.EchoMode.Password)

    def validatePage(self) -> bool:
        """Validate the page and store values in wizard config.

        Returns:
            False if keys were entered but could not be saved (the reason is
            shown on the page), True otherwise
        """
        self.error_frame.setVisible(False)
        if self._wizard:
            anthropic_key = self.anthropic_key_edit.text().strip()
            openai_key = self.openai_key_edit.text().strip()

            self._wizard.set_config_value("anthropic_api_key", anthropic_key)
            self._wizard.set_config_value("openai_api_key", openai_key)

            # Append API keys to .env file if any are provided
            if anthropic_key or openai_key:
                try:
                    self._append_api_keys_to_env(anthropic_key, openai_key)
                except (OSError, ValueError) as e:
                    env_path = self._env_path()
                    logger.error(f"Failed to save API keys to {env_path}: {e}")
                    self.error_label.setText(
                        f"The API keys could not be saved to {env_path}: {e}\n\n"
                        "Fix the problem and press Next again, or clear both "
                        "key fields to continue without them."
                    )
                    self.error_frame.setVisible(True)
                    return False

        return True

    @staticmethod
    def _env_path() -> Path:
        """The .env file the keys go to.

        Returns:
            ``BMLIBRARIAN_ENV_FILE`` if set, else ``~/.bmlibrarian/.env``
        """
        custom_env_file = os.environ.get('BMLIBRARIAN_ENV_FILE')
        return Path(custom_env_file) if custom_env_file else Path.home() / ".bmlibrarian" / ".env"

    def _append_api_keys_to_env(self, anthropic_key: str, openai_key: str) -> None:
        """
        Write API keys to the selected .env file (``_env_path``), creating it
        if needed.

        Args:
            anthropic_key: Anthropic API key (may be empty)
            openai_key: OpenAI API key (may be empty)

        Raises:
            OSError: The .env file could not be read, created, restricted or
                written (the keys are then not saved; a replaced file keeps
                its old content). Failures on the secondary project .env are
                logged, not raised.
            ValueError: The existing .env file is not valid UTF-8.
        """
        api_keys_section = "\n# Optional API Keys (for cloud AI services)\n"

        if anthropic_key:
            api_keys_section += f"ANTHROPIC_API_KEY={anthropic_key}\n"

        if openai_key:
            api_keys_section += f"OPENAI_API_KEY={openai_key}\n"

        custom_env_file = os.environ.get('BMLIBRARIAN_ENV_FILE')
        env_path = self._env_path()

        existing_content = env_path.read_text(encoding="utf-8") if env_path.exists() else ""

        # Check if API keys section already exists
        if "# Optional API Keys" not in existing_content:
            # Append to file (created 0600 if missing, #472)
            env_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            write_private_text(env_path, api_keys_section, append=True)
            logger.info(f"Appended API keys to {env_path}")
        else:
            # Update existing API keys section
            lines = existing_content.split("\n")
            new_lines = []
            skip_until_next_section = False

            for line in lines:
                if line.startswith("# Optional API Keys"):
                    skip_until_next_section = True
                    continue
                if skip_until_next_section:
                    if line.startswith("#") and not line.startswith("# Optional"):
                        skip_until_next_section = False
                        new_lines.append(line)
                    elif line.startswith("ANTHROPIC_API_KEY") or line.startswith("OPENAI_API_KEY"):
                        continue
                    elif line.strip() == "":
                        continue
                    else:
                        skip_until_next_section = False
                        new_lines.append(line)
                else:
                    new_lines.append(line)

            # Add API keys section at the end
            new_content = "\n".join(new_lines).rstrip() + api_keys_section
            write_private_text(env_path, new_content)
            logger.info(f"Updated API keys in {env_path}")

        # Also append to the project .env if it exists and has no API-key
        # section yet (not with a custom env file). env_loader reads it only
        # when ~/.bmlibrarian/.env is missing, so this copy is for development.
        if not custom_env_file:
            project_env = find_project_root() / ".env"
            if project_env.exists():
                try:
                    project_content = project_env.read_text(encoding="utf-8")
                    if "# Optional API Keys" not in project_content:
                        write_private_text(project_env, api_keys_section, append=True)
                        logger.info(f"Appended API keys to {project_env}")
                except (OSError, ValueError) as e:
                    logger.warning(f"Could not update project .env: {e}")

        # Set environment variables for current session
        if anthropic_key:
            os.environ["ANTHROPIC_API_KEY"] = anthropic_key
        if openai_key:
            os.environ["OPENAI_API_KEY"] = openai_key
