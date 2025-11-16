"""
Agent configuration widget for BMLibrarian Qt configuration.

Handles individual agent settings (model, temperature, parameters).
"""

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QFormLayout,
    QComboBox,
    QDoubleSpinBox,
    QSpinBox,
    QCheckBox,
    QLabel,
    QGroupBox,
    QScrollArea,
)
from PySide6.QtCore import Qt
from typing import Optional, List


class AgentConfigWidget(QWidget):
    """
    Agent configuration widget.

    Provides fields for:
    - Model selection
    - Temperature
    - Top-p
    - Agent-specific parameters
    """

    def __init__(
        self,
        agent_id: str,
        agent_display_name: str,
        config: dict,
        parent: Optional[QWidget] = None,
    ):
        """
        Initialize agent configuration widget.

        Args:
            agent_id: Agent identifier (e.g., 'query', 'scoring')
            agent_display_name: Human-readable agent name
            config: Current configuration dictionary
            parent: Optional parent widget
        """
        super().__init__(parent)
        self.agent_id = agent_id
        self.agent_display_name = agent_display_name
        self.config = config
        self._setup_ui()
        self._load_values()

    def _setup_ui(self):
        """Setup the user interface."""
        # Create scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)

        container = QWidget()
        main_layout = QVBoxLayout(container)
        main_layout.setContentsMargins(10, 10, 10, 10)

        # Model Settings Group
        model_group = self._create_model_group()
        main_layout.addWidget(model_group)

        # Parameters Group
        params_group = self._create_parameters_group()
        main_layout.addWidget(params_group)

        # Agent-specific settings
        if self.agent_id in ['scoring', 'citation']:
            specific_group = self._create_agent_specific_group()
            main_layout.addWidget(specific_group)

        main_layout.addStretch()

        scroll.setWidget(container)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll)

    def _create_model_group(self) -> QGroupBox:
        """
        Create model settings group.

        Returns:
            Model settings group box
        """
        group = QGroupBox("Model Settings")
        layout = QFormLayout()

        # Model selection
        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        self.model_combo.addItems([
            "gpt-oss:20b",
            "medgemma4B_it_q8:latest",
            "medgemma-27b-text-it-Q8_0:latest",
        ])
        self.model_combo.setToolTip("Select or enter a model name from Ollama")
        layout.addRow("Model:", self.model_combo)

        # Refresh models button hint
        info_label = QLabel(
            "Click 'Test Connection' to refresh available models from Ollama server."
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #7f8c8d; font-style: italic; font-size: 10pt;")
        layout.addRow("", info_label)

        group.setLayout(layout)
        return group

    def _create_parameters_group(self) -> QGroupBox:
        """
        Create model parameters group.

        Returns:
            Parameters group box
        """
        group = QGroupBox("Model Parameters")
        layout = QFormLayout()

        # Temperature
        self.temperature_input = QDoubleSpinBox()
        self.temperature_input.setRange(0.0, 2.0)
        self.temperature_input.setSingleStep(0.1)
        self.temperature_input.setValue(0.7)
        self.temperature_input.setDecimals(2)
        self.temperature_input.setToolTip(
            "Controls randomness: lower = more focused, higher = more creative (0.0-2.0)"
        )
        layout.addRow("Temperature:", self.temperature_input)

        # Top-p
        self.top_p_input = QDoubleSpinBox()
        self.top_p_input.setRange(0.0, 1.0)
        self.top_p_input.setSingleStep(0.05)
        self.top_p_input.setValue(0.9)
        self.top_p_input.setDecimals(2)
        self.top_p_input.setToolTip(
            "Nucleus sampling: controls diversity (0.0-1.0)"
        )
        layout.addRow("Top-p:", self.top_p_input)

        # Max tokens (optional, not all agents use it)
        self.max_tokens_input = QSpinBox()
        self.max_tokens_input.setRange(0, 100000)
        self.max_tokens_input.setValue(0)
        self.max_tokens_input.setSpecialValueText("Auto")
        self.max_tokens_input.setToolTip(
            "Maximum tokens to generate (0 = auto)"
        )
        layout.addRow("Max Tokens:", self.max_tokens_input)

        group.setLayout(layout)
        return group

    def _create_agent_specific_group(self) -> QGroupBox:
        """
        Create agent-specific settings group.

        Returns:
            Agent-specific settings group box
        """
        group = QGroupBox(f"{self.agent_display_name} Specific Settings")
        layout = QFormLayout()

        if self.agent_id == 'scoring':
            # Scoring agent specific settings
            self.batch_size_input = QSpinBox()
            self.batch_size_input.setRange(1, 1000)
            self.batch_size_input.setValue(50)
            self.batch_size_input.setToolTip(
                "Number of documents to process in each batch"
            )
            layout.addRow("Batch Size:", self.batch_size_input)

            self.score_threshold_input = QDoubleSpinBox()
            self.score_threshold_input.setRange(1.0, 5.0)
            self.score_threshold_input.setSingleStep(0.5)
            self.score_threshold_input.setValue(2.5)
            self.score_threshold_input.setDecimals(1)
            self.score_threshold_input.setToolTip(
                "Minimum score for document inclusion (1-5 scale)"
            )
            layout.addRow("Score Threshold:", self.score_threshold_input)

        elif self.agent_id == 'citation':
            # Citation agent specific settings
            self.max_citations_input = QSpinBox()
            self.max_citations_input.setRange(1, 100)
            self.max_citations_input.setValue(20)
            self.max_citations_input.setToolTip(
                "Maximum number of citations to extract per document"
            )
            layout.addRow("Max Citations:", self.max_citations_input)

            self.min_relevance_input = QDoubleSpinBox()
            self.min_relevance_input.setRange(1.0, 5.0)
            self.min_relevance_input.setSingleStep(0.5)
            self.min_relevance_input.setValue(3.0)
            self.min_relevance_input.setDecimals(1)
            self.min_relevance_input.setToolTip(
                "Minimum relevance score for citation extraction"
            )
            layout.addRow("Min Relevance:", self.min_relevance_input)

        group.setLayout(layout)
        return group

    def _load_values(self):
        """Load values from configuration."""
        agent_config = self.config.get('agents', {}).get(self.agent_id, {})

        # Model
        model = agent_config.get('model', 'gpt-oss:20b')
        index = self.model_combo.findText(model)
        if index >= 0:
            self.model_combo.setCurrentIndex(index)
        else:
            self.model_combo.setCurrentText(model)

        # Parameters
        self.temperature_input.setValue(agent_config.get('temperature', 0.7))
        self.top_p_input.setValue(agent_config.get('top_p', 0.9))
        self.max_tokens_input.setValue(agent_config.get('max_tokens', 0))

        # Agent-specific settings
        if self.agent_id == 'scoring':
            self.batch_size_input.setValue(agent_config.get('batch_size', 50))
            self.score_threshold_input.setValue(
                agent_config.get('score_threshold', 2.5)
            )
        elif self.agent_id == 'citation':
            self.max_citations_input.setValue(agent_config.get('max_citations', 20))
            self.min_relevance_input.setValue(
                agent_config.get('min_relevance', 3.0)
            )

    def get_config(self) -> dict:
        """
        Get configuration from widget values.

        Returns:
            Configuration dictionary
        """
        agent_config = {
            'model': self.model_combo.currentText(),
            'temperature': self.temperature_input.value(),
            'top_p': self.top_p_input.value(),
        }

        # Only include max_tokens if not auto (0)
        if self.max_tokens_input.value() > 0:
            agent_config['max_tokens'] = self.max_tokens_input.value()

        # Agent-specific settings
        if self.agent_id == 'scoring':
            agent_config['batch_size'] = self.batch_size_input.value()
            agent_config['score_threshold'] = self.score_threshold_input.value()
        elif self.agent_id == 'citation':
            agent_config['max_citations'] = self.max_citations_input.value()
            agent_config['min_relevance'] = self.min_relevance_input.value()

        return {'agents': {self.agent_id: agent_config}}

    def update_from_config(self, config: dict):
        """
        Update widget from configuration.

        Args:
            config: New configuration dictionary
        """
        self.config = config
        self._load_values()

    def update_model_list(self, models: List[str]):
        """
        Update available models in combo box.

        Args:
            models: List of model names from Ollama
        """
        current_model = self.model_combo.currentText()

        self.model_combo.clear()
        self.model_combo.addItems(models)

        # Restore previous selection if still available
        index = self.model_combo.findText(current_model)
        if index >= 0:
            self.model_combo.setCurrentIndex(index)
        else:
            # Set to current text even if not in list (custom model)
            self.model_combo.setCurrentText(current_model)
