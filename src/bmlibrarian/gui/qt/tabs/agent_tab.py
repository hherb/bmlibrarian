"""
Agent Configuration Tab for BMLibrarian Qt GUI.
Mirrors functionality from bmlibrarian/gui/tabs/agent_tab.py
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox,
    QSlider, QGroupBox, QScrollArea, QFrame, QPushButton, QMessageBox
)
from PySide6.QtCore import Qt, Slot
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from ..plugins.settings.plugin import SettingsPlugin


class AgentConfigTab:
    """Agent-specific configuration tab for Qt GUI."""

    def __init__(self, settings_plugin: "SettingsPlugin", agent_key: str, display_name: str):
        """Initialize agent configuration tab.

        Args:
            settings_plugin: Parent settings plugin instance
            agent_key: Key for agent (e.g., 'query_agent')
            display_name: Display name for agent (e.g., 'Query Agent')
        """
        self.settings_plugin = settings_plugin
        self.config = settings_plugin.config
        self.agent_key = agent_key
        self.display_name = display_name
        self.controls = {}

        # Convert agent_key from 'query_agent' to 'query'
        self.agent_type = agent_key.replace('_agent', '')

    def build(self) -> QWidget:
        """Build the agent configuration tab content.

        Returns:
            QWidget containing all agent configuration controls
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
        scroll_layout.addWidget(self._build_model_section())
        scroll_layout.addWidget(self._create_divider())
        scroll_layout.addWidget(self._build_parameters_section())
        scroll_layout.addWidget(self._create_divider())
        scroll_layout.addWidget(self._build_advanced_section())
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

    def _build_model_section(self) -> QGroupBox:
        """Build model selection section."""
        group = QGroupBox(f"{self.display_name} - Model Selection")
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

        # Model selection row
        model_layout = QHBoxLayout()

        model_label = QLabel("Model:")
        model_label.setFixedWidth(100)
        model_layout.addWidget(model_label)

        # Get current model and available models
        current_model = self.config.get_model(self.agent_key)
        available_models = self._get_available_models()

        # Ensure current model is in list
        if current_model and current_model not in available_models:
            available_models.insert(0, current_model)

        self.controls['model'] = QComboBox()
        self.controls['model'].addItems(available_models)
        if current_model:
            index = self.controls['model'].findText(current_model)
            if index >= 0:
                self.controls['model'].setCurrentIndex(index)
        model_layout.addWidget(self.controls['model'], 1)

        # Refresh button
        refresh_btn = QPushButton("🔄")
        refresh_btn.setFixedWidth(40)
        refresh_btn.setToolTip("Refresh available models from Ollama")
        refresh_btn.clicked.connect(self._refresh_models)
        model_layout.addWidget(refresh_btn)

        layout.addLayout(model_layout)

        # Status label
        self.controls['model_status'] = QLabel(f"Loaded {len(available_models)} models from Ollama")
        self.controls['model_status'].setStyleSheet("color: #666666; font-size: 10pt;")
        layout.addWidget(self.controls['model_status'])

        group.setLayout(layout)
        return group

    def _build_parameters_section(self) -> QGroupBox:
        """Build agent parameters section."""
        group = QGroupBox("Parameters")
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
        layout.setSpacing(15)

        agent_config = self.config.get_agent_config(self.agent_type)

        # Temperature slider
        temp_layout = QHBoxLayout()
        temp_label = QLabel("Temperature:")
        temp_label.setFixedWidth(100)
        temp_layout.addWidget(temp_label)

        temp_value = agent_config.get('temperature', 0.1)
        self.controls['temperature'] = QSlider(Qt.Orientation.Horizontal)
        self.controls['temperature'].setMinimum(0)
        self.controls['temperature'].setMaximum(200)  # 0.0 to 2.0 in increments of 0.01
        self.controls['temperature'].setValue(int(temp_value * 100))
        self.controls['temperature'].setToolTip("Controls randomness (0.0 = deterministic, 2.0 = very random)")
        self.controls['temperature'].valueChanged.connect(self._on_temperature_changed)
        temp_layout.addWidget(self.controls['temperature'], 1)

        self.controls['temperature_text'] = QLabel(f"{temp_value:.2f}")
        self.controls['temperature_text'].setFixedWidth(50)
        self.controls['temperature_text'].setAlignment(Qt.AlignmentFlag.AlignRight)
        temp_layout.addWidget(self.controls['temperature_text'])

        layout.addLayout(temp_layout)

        # Top-p slider
        top_p_layout = QHBoxLayout()
        top_p_label = QLabel("Top-p:")
        top_p_label.setFixedWidth(100)
        top_p_layout.addWidget(top_p_label)

        top_p_value = agent_config.get('top_p', 0.9)
        self.controls['top_p'] = QSlider(Qt.Orientation.Horizontal)
        self.controls['top_p'].setMinimum(0)
        self.controls['top_p'].setMaximum(100)  # 0.0 to 1.0 in increments of 0.01
        self.controls['top_p'].setValue(int(top_p_value * 100))
        self.controls['top_p'].setToolTip("Nucleus sampling (0.0 = most focused, 1.0 = least focused)")
        self.controls['top_p'].valueChanged.connect(self._on_top_p_changed)
        top_p_layout.addWidget(self.controls['top_p'], 1)

        self.controls['top_p_text'] = QLabel(f"{top_p_value:.2f}")
        self.controls['top_p_text'].setFixedWidth(50)
        self.controls['top_p_text'].setAlignment(Qt.AlignmentFlag.AlignRight)
        top_p_layout.addWidget(self.controls['top_p_text'])

        layout.addLayout(top_p_layout)

        # Max tokens
        tokens_layout = QHBoxLayout()
        tokens_label = QLabel("Max Tokens:")
        tokens_label.setFixedWidth(100)
        tokens_layout.addWidget(tokens_label)

        self.controls['max_tokens'] = QLineEdit()
        self.controls['max_tokens'].setText(str(agent_config.get('max_tokens', 1000)))
        self.controls['max_tokens'].setFixedWidth(100)
        self.controls['max_tokens'].setToolTip("Maximum tokens to generate")
        tokens_layout.addWidget(self.controls['max_tokens'])
        tokens_layout.addStretch()

        layout.addLayout(tokens_layout)

        group.setLayout(layout)
        return group

    def _build_advanced_section(self) -> QGroupBox:
        """Build advanced settings section."""
        group = QGroupBox("Advanced Settings")
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

        agent_config = self.config.get_agent_config(self.agent_type)

        # Repeat penalty (if applicable)
        penalty_layout = QHBoxLayout()
        penalty_label = QLabel("Repeat Penalty:")
        penalty_label.setFixedWidth(150)
        penalty_layout.addWidget(penalty_label)

        self.controls['repeat_penalty'] = QLineEdit()
        self.controls['repeat_penalty'].setText(str(agent_config.get('repeat_penalty', 1.1)))
        self.controls['repeat_penalty'].setFixedWidth(100)
        self.controls['repeat_penalty'].setToolTip("Penalty for repeating tokens")
        penalty_layout.addWidget(self.controls['repeat_penalty'])
        penalty_layout.addStretch()

        layout.addLayout(penalty_layout)

        # Agent-specific settings hint
        hint_label = QLabel("💡 Additional agent-specific settings may be available in the config file.")
        hint_label.setWordWrap(True)
        hint_label.setStyleSheet("color: #666666; font-size: 9pt; font-style: italic;")
        layout.addWidget(hint_label)

        group.setLayout(layout)
        return group

    def _get_available_models(self) -> List[str]:
        """Get available models from Ollama.

        Returns:
            List of available model names
        """
        try:
            import ollama
            host = self.config.get_ollama_config()['host']
            client = ollama.Client(host=host)
            models_response = client.list()
            return [model.model for model in models_response.models]
        except Exception as e:
            print(f"Error fetching models: {e}")
            return ['gpt-oss:20b', 'medgemma4B_it_q8:latest']  # Defaults

    @Slot()
    def _refresh_models(self):
        """Refresh available models from Ollama."""
        try:
            models = self._get_available_models()
            current_model = self.controls['model'].currentText()

            self.controls['model'].clear()
            self.controls['model'].addItems(models)

            # Restore selection if still available
            if current_model:
                index = self.controls['model'].findText(current_model)
                if index >= 0:
                    self.controls['model'].setCurrentIndex(index)

            self.controls['model_status'].setText(f"Loaded {len(models)} models from Ollama")
            self.controls['model_status'].setStyleSheet("color: #00AA00; font-size: 10pt;")

        except Exception as e:
            self.controls['model_status'].setText(f"Error: {str(e)}")
            self.controls['model_status'].setStyleSheet("color: #AA0000; font-size: 10pt;")

    @Slot(int)
    def _on_temperature_changed(self, value: int):
        """Handle temperature slider changes."""
        temp_value = value / 100.0
        self.controls['temperature_text'].setText(f"{temp_value:.2f}")

    @Slot(int)
    def _on_top_p_changed(self, value: int):
        """Handle top-p slider changes."""
        top_p_value = value / 100.0
        self.controls['top_p_text'].setText(f"{top_p_value:.2f}")

    def update_config(self):
        """Update configuration from UI controls."""
        try:
            # Get agent config section
            from bmlibrarian.config import get_config
            config = get_config()

            # Ensure agents section exists
            if 'agents' not in config._config:
                config._config['agents'] = {}
            if self.agent_type not in config._config['agents']:
                config._config['agents'][self.agent_type] = {}

            agent_config = config._config['agents'][self.agent_type]

            # Update model
            agent_config['model'] = self.controls['model'].currentText()

            # Update parameters
            agent_config['temperature'] = self.controls['temperature'].value() / 100.0
            agent_config['top_p'] = self.controls['top_p'].value() / 100.0
            agent_config['max_tokens'] = int(self.controls['max_tokens'].text())
            agent_config['repeat_penalty'] = float(self.controls['repeat_penalty'].text())

        except (ValueError, KeyError) as e:
            print(f"Error updating config from agent tab: {e}")

    def refresh(self):
        """Refresh UI controls with current configuration values."""
        agent_config = self.config.get_agent_config(self.agent_type)

        # Update model selection
        current_model = self.config.get_model(self.agent_key)
        if current_model:
            index = self.controls['model'].findText(current_model)
            if index >= 0:
                self.controls['model'].setCurrentIndex(index)

        # Update parameters
        temp_value = agent_config.get('temperature', 0.1)
        self.controls['temperature'].setValue(int(temp_value * 100))
        self.controls['temperature_text'].setText(f"{temp_value:.2f}")

        top_p_value = agent_config.get('top_p', 0.9)
        self.controls['top_p'].setValue(int(top_p_value * 100))
        self.controls['top_p_text'].setText(f"{top_p_value:.2f}")

        self.controls['max_tokens'].setText(str(agent_config.get('max_tokens', 1000)))
        self.controls['repeat_penalty'].setText(str(agent_config.get('repeat_penalty', 1.1)))
