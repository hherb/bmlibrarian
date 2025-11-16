"""
Query Lab Tab Widget for BMLibrarian Qt GUI.

Interactive interface for experimenting with QueryAgent and natural language
to PostgreSQL query conversion.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QGroupBox, QSlider, QLineEdit, QComboBox,
    QFileDialog, QMessageBox, QSpinBox, QFormLayout
)
from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtGui import QFont
from typing import Optional, Dict, Any
import json
from pathlib import Path

from bmlibrarian.agents import QueryAgent, AgentOrchestrator
from bmlibrarian.config import get_config


class QueryGenerationWorker(QThread):
    """Worker thread for query generation to prevent UI blocking."""

    result_ready = Signal(dict)
    error_occurred = Signal(str)

    def __init__(self, query_agent: QueryAgent, human_query: str):
        """
        Initialize worker thread.

        Args:
            query_agent: QueryAgent instance
            human_query: Human language question
        """
        super().__init__()
        self.query_agent = query_agent
        self.human_query = human_query

    def run(self):
        """Execute query generation in background thread."""
        try:
            # Generate query using QueryAgent
            result_query = self.query_agent.convert_question(self.human_query)

            # Emit result
            self.result_ready.emit({
                'query': result_query,
                'explanation': 'Query generated successfully using QueryAgent'
            })
        except Exception as e:
            self.error_occurred.emit(str(e))


class QueryLabTabWidget(QWidget):
    """Main Query Lab tab widget."""

    status_message = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None):
        """
        Initialize Query Lab tab.

        Args:
            parent: Optional parent widget
        """
        super().__init__(parent)

        self.config = get_config()
        self.query_agent: Optional[QueryAgent] = None
        self.orchestrator: Optional[AgentOrchestrator] = None
        self.worker: Optional[QueryGenerationWorker] = None

        # UI Components
        self.model_combo: Optional[QComboBox] = None
        self.temperature_slider: Optional[QSlider] = None
        self.top_p_slider: Optional[QSlider] = None
        self.max_tokens_spin: Optional[QSpinBox] = None
        self.human_query_edit: Optional[QTextEdit] = None
        self.postgres_query_edit: Optional[QTextEdit] = None
        self.explanation_edit: Optional[QTextEdit] = None
        self.status_label: Optional[QLabel] = None
        self.stats_label: Optional[QLabel] = None
        self.agent_status_label: Optional[QLabel] = None

        self._init_agent()
        self._setup_ui()

    def _init_agent(self):
        """Initialize QueryAgent with orchestrator."""
        try:
            self.orchestrator = AgentOrchestrator(max_workers=2)

            # Get configuration
            default_model = self.config.get_model('query_agent') or "medgemma4B_it_q8:latest"
            agent_config = self.config.get_agent_config('query')
            host = self.config.get_ollama_config()['host']

            self.query_agent = QueryAgent(
                model=default_model,
                host=host,
                temperature=agent_config.get('temperature', 0.1),
                top_p=agent_config.get('top_p', 0.9),
                orchestrator=self.orchestrator,
                show_model_info=True
            )
        except Exception as e:
            print(f"Warning: Failed to initialize QueryAgent: {e}")
            self.query_agent = None

    def _setup_ui(self):
        """Setup the user interface."""
        # Main layout
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(20)

        # Left panel: Configuration
        config_panel = self._create_config_panel()
        main_layout.addWidget(config_panel)

        # Right panel: Query I/O
        query_panel = self._create_query_panel()
        main_layout.addLayout(query_panel)

        # Set proportions (1:2 ratio)
        main_layout.setStretch(0, 1)
        main_layout.setStretch(1, 2)

    def _create_config_panel(self) -> QGroupBox:
        """
        Create configuration panel.

        Returns:
            Configuration panel group box
        """
        group = QGroupBox("Configuration")
        layout = QVBoxLayout(group)
        layout.setSpacing(15)

        # Model Selection
        model_layout = QVBoxLayout()
        model_label = QLabel("Query Agent Model:")
        model_label.setFont(QFont("", 10, QFont.Bold))
        model_layout.addWidget(model_label)

        model_row = QHBoxLayout()
        self.model_combo = QComboBox()
        self.model_combo.setMinimumWidth(200)
        self._refresh_models()
        model_row.addWidget(self.model_combo)

        refresh_btn = QPushButton("↻")
        refresh_btn.setMaximumWidth(40)
        refresh_btn.setToolTip("Refresh available models")
        refresh_btn.clicked.connect(self._on_refresh_models)
        model_row.addWidget(refresh_btn)
        model_layout.addLayout(model_row)
        layout.addLayout(model_layout)

        # Parameters
        params_label = QLabel("Parameters:")
        params_label.setFont(QFont("", 10, QFont.Bold))
        layout.addWidget(params_label)

        # Temperature
        temp_layout = QVBoxLayout()
        self.temperature_slider = QSlider(Qt.Horizontal)
        self.temperature_slider.setMinimum(0)
        self.temperature_slider.setMaximum(200)
        agent_config = self.config.get_agent_config('query')
        self.temperature_slider.setValue(int(agent_config.get('temperature', 0.1) * 100))
        self.temperature_slider.setTickPosition(QSlider.TicksBelow)
        self.temperature_slider.setTickInterval(20)

        temp_value_label = QLabel(f"Temperature: {self.temperature_slider.value() / 100:.2f}")
        self.temperature_slider.valueChanged.connect(
            lambda v: temp_value_label.setText(f"Temperature: {v / 100:.2f}")
        )

        temp_layout.addWidget(temp_value_label)
        temp_layout.addWidget(self.temperature_slider)
        layout.addLayout(temp_layout)

        # Top-p
        top_p_layout = QVBoxLayout()
        self.top_p_slider = QSlider(Qt.Horizontal)
        self.top_p_slider.setMinimum(0)
        self.top_p_slider.setMaximum(100)
        self.top_p_slider.setValue(int(agent_config.get('top_p', 0.9) * 100))
        self.top_p_slider.setTickPosition(QSlider.TicksBelow)
        self.top_p_slider.setTickInterval(10)

        top_p_value_label = QLabel(f"Top-p: {self.top_p_slider.value() / 100:.2f}")
        self.top_p_slider.valueChanged.connect(
            lambda v: top_p_value_label.setText(f"Top-p: {v / 100:.2f}")
        )

        top_p_layout.addWidget(top_p_value_label)
        top_p_layout.addWidget(self.top_p_slider)
        layout.addLayout(top_p_layout)

        # Max Tokens
        max_tokens_layout = QFormLayout()
        self.max_tokens_spin = QSpinBox()
        self.max_tokens_spin.setMinimum(10)
        self.max_tokens_spin.setMaximum(1000)
        self.max_tokens_spin.setValue(agent_config.get('max_tokens', 100))
        max_tokens_layout.addRow("Max Tokens:", self.max_tokens_spin)
        layout.addLayout(max_tokens_layout)

        layout.addStretch()

        # Agent Status
        layout.addWidget(QLabel("─" * 30))
        agent_ready = self.query_agent is not None
        status_text = "✅ Agent Ready" if agent_ready else "⚠️ Simulation Mode"
        status_color = "green" if agent_ready else "orange"

        self.agent_status_label = QLabel(status_text)
        self.agent_status_label.setStyleSheet(f"color: {status_color}; font-weight: bold;")
        layout.addWidget(self.agent_status_label)

        return group

    def _create_query_panel(self) -> QVBoxLayout:
        """
        Create query input/output panel.

        Returns:
            Query panel layout
        """
        layout = QVBoxLayout()

        # Title
        title = QLabel("Query Laboratory")
        title_font = QFont("", 14, QFont.Bold)
        title.setFont(title_font)
        layout.addWidget(title)

        # Human language input
        layout.addWidget(QLabel("Human Language Question:"))
        self.human_query_edit = QTextEdit()
        self.human_query_edit.setPlaceholderText(
            "Enter your medical research question in natural language...\n\n"
            "Example: What are the cardiovascular benefits of exercise?"
        )
        self.human_query_edit.setMaximumHeight(120)
        self.human_query_edit.textChanged.connect(self._on_query_text_changed)
        layout.addWidget(self.human_query_edit)

        # Generated PostgreSQL query
        layout.addWidget(QLabel("Generated PostgreSQL Query:"))
        self.postgres_query_edit = QTextEdit()
        self.postgres_query_edit.setPlaceholderText("Generated query will appear here...")
        self.postgres_query_edit.setReadOnly(True)
        self.postgres_query_edit.setMaximumHeight(150)
        self.postgres_query_edit.setStyleSheet(
            "background-color: #f5f5f5; font-family: 'Courier New', monospace;"
        )
        layout.addWidget(self.postgres_query_edit)

        # Explanation
        layout.addWidget(QLabel("Query Explanation:"))
        self.explanation_edit = QTextEdit()
        self.explanation_edit.setPlaceholderText("Explanation of the generated query...")
        self.explanation_edit.setReadOnly(True)
        self.explanation_edit.setMaximumHeight(100)
        self.explanation_edit.setStyleSheet("background-color: #e8f4f8;")
        layout.addWidget(self.explanation_edit)

        # Status and stats
        status_layout = QHBoxLayout()
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color: gray;")
        status_layout.addWidget(self.status_label)

        status_layout.addStretch()

        self.stats_label = QLabel("")
        self.stats_label.setStyleSheet("color: gray; font-size: 9pt;")
        status_layout.addWidget(self.stats_label)
        layout.addLayout(status_layout)

        # Control buttons
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)

        generate_btn = QPushButton("Generate Query")
        generate_btn.setStyleSheet(
            "background-color: #27ae60; color: white; padding: 10px 20px; font-weight: bold;"
        )
        generate_btn.clicked.connect(self._on_generate_query)
        button_layout.addWidget(generate_btn)

        clear_btn = QPushButton("Clear All")
        clear_btn.clicked.connect(self._on_clear_all)
        button_layout.addWidget(clear_btn)

        save_btn = QPushButton("Save Example")
        save_btn.clicked.connect(self._on_save_example)
        button_layout.addWidget(save_btn)

        load_btn = QPushButton("Load Example")
        load_btn.clicked.connect(self._on_load_example)
        button_layout.addWidget(load_btn)

        test_btn = QPushButton("Test Connection")
        test_btn.setStyleSheet(
            "background-color: #3498db; color: white; padding: 10px 20px;"
        )
        test_btn.clicked.connect(self._on_test_connection)
        button_layout.addWidget(test_btn)

        layout.addLayout(button_layout)

        return layout

    def _refresh_models(self):
        """Refresh available models from Ollama."""
        try:
            import ollama
            host = self.config.get_ollama_config()['host']
            client = ollama.Client(host=host)
            models_response = client.list()

            models = sorted([model.model for model in models_response.models])

            # Get current selection
            current_model = self.model_combo.currentText() if self.model_combo else None

            # Update combo box
            if self.model_combo:
                self.model_combo.clear()
                self.model_combo.addItems(models)

                # Restore selection if still available
                if current_model and current_model in models:
                    self.model_combo.setCurrentText(current_model)
                elif models:
                    # Select configured model or first available
                    configured_model = self.config.get_model('query_agent')
                    if configured_model and configured_model in models:
                        self.model_combo.setCurrentText(configured_model)
                    else:
                        self.model_combo.setCurrentIndex(0)
        except Exception as e:
            print(f"Failed to refresh models: {e}")
            # Fallback models
            if self.model_combo:
                self.model_combo.clear()
                self.model_combo.addItems([
                    "medgemma4B_it_q8:latest",
                    "medgemma-27b-text-it-Q8_0:latest",
                    "gpt-oss:20b"
                ])

    def _on_refresh_models(self):
        """Handle model refresh button click."""
        self._refresh_models()
        self.status_message.emit("Models refreshed")
        QMessageBox.information(self, "Success", "Models refreshed successfully!")

    def _on_query_text_changed(self):
        """Handle query text change."""
        text = self.human_query_edit.toPlainText()
        if text:
            char_count = len(text)
            word_count = len(text.split())
            self.stats_label.setText(f"Input: {char_count} chars, {word_count} words")
        else:
            self.stats_label.setText("")

    def _on_generate_query(self):
        """Generate PostgreSQL query from human language input."""
        human_query = self.human_query_edit.toPlainText().strip()

        if not human_query:
            QMessageBox.warning(self, "Warning", "Please enter a research question.")
            return

        if not self.query_agent:
            QMessageBox.warning(
                self,
                "Warning",
                "QueryAgent is not available. Running in simulation mode."
            )
            self._simulate_query_generation(human_query)
            return

        # Update status
        self.status_label.setText("Generating...")
        self.status_label.setStyleSheet("color: blue; font-weight: bold;")
        self.status_message.emit("Generating query...")

        # Run in background thread
        self.worker = QueryGenerationWorker(self.query_agent, human_query)
        self.worker.result_ready.connect(self._on_query_result)
        self.worker.error_occurred.connect(self._on_query_error)
        self.worker.start()

    def _on_query_result(self, result: Dict[str, str]):
        """
        Handle query generation result.

        Args:
            result: Dictionary with 'query' and 'explanation' keys
        """
        # Display results
        self.postgres_query_edit.setPlainText(result.get('query', ''))
        self.explanation_edit.setPlainText(result.get('explanation', ''))

        # Update stats
        query_len = len(result.get('query', ''))
        current_stats = self.stats_label.text()
        self.stats_label.setText(f"{current_stats} | Output: {query_len} chars")

        # Success status
        self.status_label.setText("✅ Generated")
        self.status_label.setStyleSheet("color: green; font-weight: bold;")
        self.status_message.emit("Query generated successfully")

    def _on_query_error(self, error: str):
        """
        Handle query generation error.

        Args:
            error: Error message
        """
        self.status_label.setText(f"❌ Error")
        self.status_label.setStyleSheet("color: red; font-weight: bold;")
        self.explanation_edit.setPlainText(f"Error: {error}")
        self.status_message.emit(f"Query generation failed: {error}")

        QMessageBox.critical(self, "Error", f"Query generation failed:\n\n{error}")

    def _simulate_query_generation(self, human_query: str):
        """
        Simulate query generation for testing.

        Args:
            human_query: Human language question
        """
        # Simple simulation
        words = human_query.lower().replace(',', '').replace('.', '').replace('?', '').split()
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
                      'of', 'with', 'by', 'is', 'are', 'was', 'were', 'what', 'how', 'when'}
        meaningful_words = [w for w in words if w not in stop_words and len(w) > 2][:6]

        query_terms = ' & '.join(meaningful_words)
        simulated_query = f"to_tsquery('english', '{query_terms}')"

        self.postgres_query_edit.setPlainText(simulated_query)
        self.explanation_edit.setPlainText(
            f"Simulated query generation (QueryAgent not available).\n"
            f"Extracted {len(meaningful_words)} key terms from your question."
        )

        self.status_label.setText("⚠️ Simulated")
        self.status_label.setStyleSheet("color: orange; font-weight: bold;")

    def _on_clear_all(self):
        """Clear all input and output fields."""
        self.human_query_edit.clear()
        self.postgres_query_edit.clear()
        self.explanation_edit.clear()
        self.stats_label.clear()
        self.status_label.setText("Ready")
        self.status_label.setStyleSheet("color: gray;")
        self.status_message.emit("Cleared all fields")

    def _on_save_example(self):
        """Save current query as an example."""
        human_query = self.human_query_edit.toPlainText()
        postgres_query = self.postgres_query_edit.toPlainText()

        if not human_query.strip() or not postgres_query.strip():
            QMessageBox.warning(
                self,
                "Warning",
                "Both human query and generated query must be present to save."
            )
            return

        example = {
            'human_query': human_query,
            'postgres_query': postgres_query,
            'model': self.model_combo.currentText(),
            'temperature': self.temperature_slider.value() / 100,
            'top_p': self.top_p_slider.value() / 100,
            'max_tokens': self.max_tokens_spin.value()
        }

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Query Example",
            str(Path.home() / "query_example.json"),
            "JSON Files (*.json)"
        )

        if file_path:
            try:
                with open(file_path, 'w') as f:
                    json.dump(example, f, indent=2)

                QMessageBox.information(self, "Success", f"Example saved to {file_path}")
                self.status_message.emit(f"Example saved to {file_path}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save example:\n\n{str(e)}")

    def _on_load_example(self):
        """Load a saved example."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Query Example",
            str(Path.home()),
            "JSON Files (*.json)"
        )

        if file_path:
            try:
                with open(file_path, 'r') as f:
                    example = json.load(f)

                # Load data
                self.human_query_edit.setPlainText(example.get('human_query', ''))
                self.postgres_query_edit.setPlainText(example.get('postgres_query', ''))

                # Load settings if available
                if 'model' in example:
                    index = self.model_combo.findText(example['model'])
                    if index >= 0:
                        self.model_combo.setCurrentIndex(index)

                if 'temperature' in example:
                    self.temperature_slider.setValue(int(example['temperature'] * 100))

                if 'top_p' in example:
                    self.top_p_slider.setValue(int(example['top_p'] * 100))

                if 'max_tokens' in example:
                    self.max_tokens_spin.setValue(example['max_tokens'])

                self.status_label.setText("Example loaded")
                self.status_label.setStyleSheet("color: green;")
                QMessageBox.information(self, "Success", "Example loaded successfully!")
                self.status_message.emit(f"Example loaded from {file_path}")

            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to load example:\n\n{str(e)}")

    def _on_test_connection(self):
        """Test connection to database and Ollama."""
        try:
            import ollama
            host = self.config.get_ollama_config()['host']
            client = ollama.Client(host=host)
            models_response = client.list()
            model_count = len(models_response.models)

            agent_status = "✅ QueryAgent initialized" if self.query_agent else "❌ QueryAgent not initialized"

            QMessageBox.information(
                self,
                "Connection Test Results",
                f"Ollama Server: ✅ Connected to {host}\n"
                f"Available Models: {model_count} models found\n"
                f"QueryAgent: {agent_status}"
            )
            self.status_message.emit("Connection test successful")

        except Exception as e:
            QMessageBox.critical(
                self,
                "Connection Test Failed",
                f"Connection test failed:\n\n{str(e)}"
            )
            self.status_message.emit(f"Connection test failed: {str(e)}")

    def cleanup(self):
        """Cleanup resources when tab is closed."""
        if self.worker and self.worker.isRunning():
            self.worker.terminate()
            self.worker.wait()

        if self.orchestrator:
            # Cleanup orchestrator if needed
            pass
