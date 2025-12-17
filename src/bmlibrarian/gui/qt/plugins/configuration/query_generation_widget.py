"""
Query generation settings widget for BMLibrarian Qt configuration.

Handles multi-model query generation settings.
"""

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QFormLayout,
    QComboBox,
    QSpinBox,
    QCheckBox,
    QLabel,
    QGroupBox,
    QScrollArea,
    QListWidget,
    QPushButton,
    QHBoxLayout,
)
from PySide6.QtCore import Qt
from typing import Optional

from ...resources.styles import get_font_scale


class QueryGenerationWidget(QWidget):
    """
    Query generation configuration widget.

    Provides fields for:
    - Multi-model query generation enable/disable
    - Model selection for query generation
    - Queries per model
    - Execution mode
    - De-duplication settings
    """

    def __init__(self, config: dict, parent: Optional[QWidget] = None):
        """
        Initialize query generation widget.

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
        # Create scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)

        container = QWidget()
        main_layout = QVBoxLayout(container)
        main_layout.setContentsMargins(s['padding_medium'], s['padding_medium'], s['padding_medium'], s['padding_medium'])

        # Enable/Disable Group
        enable_group = self._create_enable_group()
        main_layout.addWidget(enable_group)

        # Model Selection Group
        models_group = self._create_models_group()
        main_layout.addWidget(models_group)

        # Query Settings Group
        query_group = self._create_query_settings_group()
        main_layout.addWidget(query_group)

        # Advanced Settings Group
        advanced_group = self._create_advanced_group()
        main_layout.addWidget(advanced_group)

        main_layout.addStretch()

        scroll.setWidget(container)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll)

    def _create_enable_group(self) -> QGroupBox:
        """
        Create enable/disable group.

        Returns:
            Enable group box
        """
        s = self.scale
        group = QGroupBox("Multi-Model Query Generation")
        layout = QVBoxLayout()

        # Enable checkbox
        self.enabled_checkbox = QCheckBox("Enable multi-model query generation")
        self.enabled_checkbox.setToolTip(
            "Use multiple models to generate diverse database queries"
        )
        self.enabled_checkbox.stateChanged.connect(self._on_enabled_changed)
        layout.addWidget(self.enabled_checkbox)

        # Info label
        info_label = QLabel(
            "Multi-model query generation uses multiple AI models to create diverse "
            "queries, typically finding 20-40% more relevant documents. This increases "
            "processing time by 2-3x but improves research comprehensiveness."
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet(f"color: #7f8c8d; font-style: italic; padding: {s['padding_small']}px;")
        layout.addWidget(info_label)

        group.setLayout(layout)
        return group

    def _create_models_group(self) -> QGroupBox:
        """
        Create models selection group.

        Returns:
            Models group box
        """
        s = self.scale
        group = QGroupBox("Query Generation Models")
        layout = QVBoxLayout()

        # Models list
        label = QLabel("Models to use for query generation:")
        layout.addWidget(label)

        # Models list - starts empty, populated by parent via update_model_list()
        self.models_list = QListWidget()
        self.models_list.setSelectionMode(QListWidget.MultiSelection)
        # List height: 3 items × control height = good default
        self.models_list.setMaximumHeight(s['control_height_medium'] * 3)
        self.models_list.setToolTip(
            "Select 1-3 models to use for query generation (Ctrl+Click for multiple)"
        )
        layout.addWidget(self.models_list)

        # Info
        info_label = QLabel(
            "Recommended: Use 2-3 different models for best results. "
            "More models = more diverse queries but slower processing."
        )
        info_label.setWordWrap(True)
        info_label# Styling handled by centralized theme
        layout.addWidget(info_label)

        group.setLayout(layout)
        self.models_group = group  # Store reference for enable/disable
        return group

    def _create_query_settings_group(self) -> QGroupBox:
        """
        Create query settings group.

        Returns:
            Query settings group box
        """
        group = QGroupBox("Query Settings")
        layout = QFormLayout()

        # Queries per model
        self.queries_per_model_input = QSpinBox()
        self.queries_per_model_input.setRange(1, 3)
        self.queries_per_model_input.setValue(1)
        self.queries_per_model_input.setToolTip(
            "Number of queries to generate per model (1-3)"
        )
        layout.addRow("Queries per Model:", self.queries_per_model_input)

        # Execution mode
        self.execution_mode_combo = QComboBox()
        self.execution_mode_combo.addItems(["serial", "parallel"])
        self.execution_mode_combo.setCurrentText("serial")
        self.execution_mode_combo.setToolTip(
            "Serial: One model at a time (recommended for local Ollama)\n"
            "Parallel: All models simultaneously (for remote/high-capacity servers)"
        )
        layout.addRow("Execution Mode:", self.execution_mode_combo)

        group.setLayout(layout)
        self.query_group = group  # Store reference
        return group

    def _create_advanced_group(self) -> QGroupBox:
        """
        Create advanced settings group.

        Returns:
            Advanced settings group box
        """
        group = QGroupBox("Advanced Settings")
        layout = QVBoxLayout()

        # De-duplicate results
        self.deduplicate_checkbox = QCheckBox("De-duplicate results")
        self.deduplicate_checkbox.setChecked(True)
        self.deduplicate_checkbox.setToolTip(
            "Remove duplicate documents from different queries"
        )
        layout.addWidget(self.deduplicate_checkbox)

        # Show all queries
        self.show_queries_checkbox = QCheckBox("Show all generated queries to user")
        self.show_queries_checkbox.setChecked(True)
        self.show_queries_checkbox.setToolTip(
            "Display all generated SQL queries in the UI"
        )
        layout.addWidget(self.show_queries_checkbox)

        # Allow query selection
        self.allow_selection_checkbox = QCheckBox("Allow user to select queries")
        self.allow_selection_checkbox.setChecked(True)
        self.allow_selection_checkbox.setToolTip(
            "Let user choose which queries to execute"
        )
        layout.addWidget(self.allow_selection_checkbox)

        group.setLayout(layout)
        self.advanced_group = group  # Store reference
        return group

    def _load_values(self):
        """Load values from configuration."""
        qg_config = self.config.get('query_generation', {})

        # Enable/disable
        enabled = qg_config.get('multi_model_enabled', False)
        self.enabled_checkbox.setChecked(enabled)
        self._on_enabled_changed(Qt.Checked if enabled else Qt.Unchecked)

        # Models
        selected_models = qg_config.get('models', [])
        for i in range(self.models_list.count()):
            item = self.models_list.item(i)
            if item.text() in selected_models:
                item.setSelected(True)

        # Query settings
        self.queries_per_model_input.setValue(
            qg_config.get('queries_per_model', 1)
        )
        execution_mode = qg_config.get('execution_mode', 'serial')
        index = self.execution_mode_combo.findText(execution_mode)
        if index >= 0:
            self.execution_mode_combo.setCurrentIndex(index)

        # Advanced settings
        self.deduplicate_checkbox.setChecked(
            qg_config.get('deduplicate_results', True)
        )
        self.show_queries_checkbox.setChecked(
            qg_config.get('show_all_queries_to_user', True)
        )
        self.allow_selection_checkbox.setChecked(
            qg_config.get('allow_query_selection', True)
        )

    def _on_enabled_changed(self, state: int):
        """
        Handle enable/disable checkbox change.

        Args:
            state: Checkbox state
        """
        enabled = state == Qt.Checked

        # Enable/disable all dependent groups
        self.models_group.setEnabled(enabled)
        self.query_group.setEnabled(enabled)
        self.advanced_group.setEnabled(enabled)

    def get_config(self) -> dict:
        """
        Get configuration from widget values.

        Returns:
            Configuration dictionary
        """
        # Get selected models
        selected_models = [
            self.models_list.item(i).text()
            for i in range(self.models_list.count())
            if self.models_list.item(i).isSelected()
        ]

        return {
            'query_generation': {
                'multi_model_enabled': self.enabled_checkbox.isChecked(),
                'models': selected_models,
                'queries_per_model': self.queries_per_model_input.value(),
                'execution_mode': self.execution_mode_combo.currentText(),
                'deduplicate_results': self.deduplicate_checkbox.isChecked(),
                'show_all_queries_to_user': self.show_queries_checkbox.isChecked(),
                'allow_query_selection': self.allow_selection_checkbox.isChecked(),
            }
        }

    def update_from_config(self, config: dict):
        """
        Update widget from configuration.

        Args:
            config: New configuration dictionary
        """
        self.config = config
        self._load_values()

    def update_model_list(self, models: list[str]):
        """
        Update available models in the list widget.

        Preserves currently selected models when updating the list.

        Args:
            models: List of model names from Ollama
        """
        # Remember currently selected models
        selected_models = [
            self.models_list.item(i).text()
            for i in range(self.models_list.count())
            if self.models_list.item(i).isSelected()
        ]

        # Clear and repopulate
        self.models_list.clear()
        self.models_list.addItems(models)

        # Restore selections
        for i in range(self.models_list.count()):
            item = self.models_list.item(i)
            if item.text() in selected_models:
                item.setSelected(True)
