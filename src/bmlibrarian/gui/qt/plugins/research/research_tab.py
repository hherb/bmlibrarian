"""
Research tab widget for BMLibrarian Qt GUI.

Main interface for research workflow execution.
"""

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QTextEdit,
    QLabel,
    QScrollArea,
    QSplitter,
    QMessageBox,
)
from PySide6.QtCore import Qt, Signal, Slot
from typing import Optional
from ...widgets.collapsible_section import CollapsibleSection
from ...widgets.markdown_viewer import MarkdownViewer
from ...widgets.document_card import DocumentCard
from ...widgets.citation_card import CitationCard
from ...utils.threading import create_progress_worker, WorkerSignals
from PySide6.QtCore import QThreadPool


class ResearchTabWidget(QWidget):
    """
    Main research workflow widget.

    Provides interface for:
    - Research question input
    - Workflow execution with progress
    - Document and citation display
    - Report preview and export
    """

    # Signals
    status_message = Signal(str)  # Status updates
    workflow_started = Signal()  # Workflow execution started
    workflow_completed = Signal(dict)  # Workflow completed with results
    workflow_error = Signal(Exception)  # Workflow error occurred

    def __init__(self, parent: Optional[QWidget] = None):
        """
        Initialize research tab.

        Args:
            parent: Optional parent widget
        """
        super().__init__(parent)

        self.threadpool = QThreadPool.globalInstance()
        self.current_results = {}

        self._setup_ui()

    def _setup_ui(self):
        """Setup the user interface."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)

        # Question input section
        question_section = self._create_question_section()
        main_layout.addWidget(question_section)

        # Main content area with splitter
        splitter = QSplitter(Qt.Horizontal)

        # Left panel: Workflow and documents
        left_panel = self._create_left_panel()
        splitter.addWidget(left_panel)

        # Right panel: Report preview
        right_panel = self._create_right_panel()
        splitter.addWidget(right_panel)

        # Set splitter sizes (40% left, 60% right)
        splitter.setSizes([400, 600])

        main_layout.addWidget(splitter)

    def _create_question_section(self) -> QWidget:
        """
        Create research question input section.

        Returns:
            Question input widget
        """
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 10)

        # Label
        label = QLabel("<b>Research Question:</b>")
        layout.addWidget(label)

        # Question input
        self.question_input = QTextEdit()
        self.question_input.setPlaceholderText(
            "Enter your biomedical research question here...\n\n"
            "Example: What are the cardiovascular benefits of regular exercise?"
        )
        self.question_input.setMaximumHeight(100)
        layout.addWidget(self.question_input)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.start_button = QPushButton("Start Research")
        self.start_button.clicked.connect(self._on_start_research)
        self.start_button.setStyleSheet(
            """
            QPushButton {
                background-color: #3498db;
                color: white;
                font-weight: bold;
                padding: 8px 16px;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
            QPushButton:disabled {
                background-color: #bdc3c7;
            }
        """
        )
        button_layout.addWidget(self.start_button)

        self.clear_button = QPushButton("Clear")
        self.clear_button.clicked.connect(self._on_clear)
        button_layout.addWidget(self.clear_button)

        layout.addLayout(button_layout)

        return widget

    def _create_left_panel(self) -> QWidget:
        """
        Create left panel with workflow and documents.

        Returns:
            Left panel widget
        """
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 5, 0)

        # Workflow section
        self.workflow_section = CollapsibleSection("Workflow Progress", expanded=True)
        self.workflow_content = QLabel(
            "Click 'Start Research' to begin the multi-agent workflow."
        )
        self.workflow_content.setWordWrap(True)
        self.workflow_content.setStyleSheet("padding: 10px;")
        self.workflow_section.set_content_widget(self.workflow_content)
        layout.addWidget(self.workflow_section)

        # Documents section
        self.documents_section = CollapsibleSection("Documents", expanded=False)
        self.documents_scroll = QScrollArea()
        self.documents_scroll.setWidgetResizable(True)
        self.documents_container = QWidget()
        self.documents_layout = QVBoxLayout(self.documents_container)
        self.documents_layout.addStretch()
        self.documents_scroll.setWidget(self.documents_container)
        self.documents_section.set_content_widget(self.documents_scroll)
        layout.addWidget(self.documents_section)

        return widget

    def _create_right_panel(self) -> QWidget:
        """
        Create right panel with report preview.

        Returns:
            Right panel widget
        """
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(5, 0, 0, 0)

        # Report section
        report_label = QLabel("<b>Research Report:</b>")
        layout.addWidget(report_label)

        # Markdown viewer
        self.report_viewer = MarkdownViewer()
        self.report_viewer.set_markdown("*Report will appear here after workflow completes.*")
        layout.addWidget(self.report_viewer)

        # Export button
        export_layout = QHBoxLayout()
        export_layout.addStretch()

        self.export_button = QPushButton("Export Report")
        self.export_button.clicked.connect(self._on_export_report)
        self.export_button.setEnabled(False)
        export_layout.addWidget(self.export_button)

        layout.addLayout(export_layout)

        return widget

    @Slot()
    def _on_start_research(self):
        """Handle start research button click."""
        # Get question
        question = self.question_input.toPlainText().strip()

        if not question:
            QMessageBox.warning(self, "No Question", "Please enter a research question.")
            return

        # Disable button
        self.start_button.setEnabled(False)
        self.status_message.emit("Starting research workflow...")

        # Update workflow display
        self.workflow_content.setText("Executing multi-agent workflow...\n\nThis is a demo implementation.")

        # Create mock workflow worker
        worker = create_progress_worker(self._execute_workflow_mock, question)
        worker.signals.progress.connect(self._on_workflow_progress)
        worker.signals.status.connect(self._on_workflow_status)
        worker.signals.result.connect(self._on_workflow_complete)
        worker.signals.error.connect(self._on_workflow_error)
        worker.signals.finished.connect(lambda: self.start_button.setEnabled(True))

        # Start worker
        self.threadpool.start(worker)
        self.workflow_started.emit()

    def _execute_workflow_mock(self, progress_signal, status_signal):
        """
        Mock workflow execution (to be replaced with real implementation).

        Args:
            progress_signal: Signal for progress updates
            status_signal: Signal for status updates

        Returns:
            Mock results dictionary
        """
        import time

        # Simulate workflow steps
        steps = [
            "Generating database query...",
            "Searching documents...",
            "Scoring document relevance...",
            "Extracting citations...",
            "Generating report...",
        ]

        for i, step in enumerate(steps):
            status_signal.emit(step)
            progress_signal.emit(int((i + 1) / len(steps) * 100))
            time.sleep(0.5)  # Simulate work

        # Return mock results
        return {
            "question": "What are the cardiovascular benefits of exercise?",
            "documents": [
                {
                    "title": "Exercise and Heart Health: A Meta-Analysis",
                    "authors": ["Smith, J.", "Johnson, A."],
                    "year": "2023",
                    "journal": "Cardiology Today",
                    "pmid": "12345678",
                    "relevance_score": 4.5,
                }
            ],
            "report": """# Research Report: Cardiovascular Benefits of Exercise

## Summary

Regular physical exercise has been consistently demonstrated to provide significant cardiovascular benefits.

## Key Findings

1. **Reduced cardiovascular disease risk**: Regular exercise reduces the risk of heart disease by approximately 30-40%.

2. **Improved cardiac function**: Exercise strengthens the heart muscle and improves overall cardiac output.

3. **Blood pressure reduction**: Moderate exercise can reduce systolic blood pressure by 5-10 mmHg.

## Citations

- Smith, J. et al. (2023). Exercise and Heart Health: A Meta-Analysis. *Cardiology Today*.

## Conclusion

The evidence strongly supports regular physical exercise as a key component of cardiovascular health maintenance.

---

*This is a demonstration report. Full multi-agent workflow integration coming soon.*
""",
        }

    @Slot(int)
    def _on_workflow_progress(self, progress: int):
        """
        Handle workflow progress update.

        Args:
            progress: Progress percentage (0-100)
        """
        self.workflow_content.setText(f"Workflow Progress: {progress}%")

    @Slot(str)
    def _on_workflow_status(self, status: str):
        """
        Handle workflow status update.

        Args:
            status: Status message
        """
        self.workflow_content.setText(f"{status}")
        self.status_message.emit(status)

    @Slot(object)
    def _on_workflow_complete(self, results: dict):
        """
        Handle workflow completion.

        Args:
            results: Workflow results dictionary
        """
        self.current_results = results

        # Update workflow status
        self.workflow_content.setText("✅ Workflow completed successfully!")
        self.workflow_section.set_header_color("#27ae60")

        # Display documents
        self._display_documents(results.get("documents", []))

        # Display report
        report = results.get("report", "*No report generated.*")
        self.report_viewer.set_markdown(report)

        # Enable export
        self.export_button.setEnabled(True)

        # Emit completion signal
        self.workflow_completed.emit(results)
        self.status_message.emit("Research workflow completed!")

    @Slot(Exception)
    def _on_workflow_error(self, error: Exception):
        """
        Handle workflow error.

        Args:
            error: Exception that occurred
        """
        self.workflow_content.setText(f"❌ Error: {str(error)}")
        self.workflow_section.set_header_color("#e74c3c")

        QMessageBox.critical(
            self, "Workflow Error", f"An error occurred during workflow execution:\n\n{str(error)}"
        )

        self.workflow_error.emit(error)
        self.status_message.emit(f"Workflow error: {str(error)}")

    def _display_documents(self, documents: list):
        """
        Display documents in the documents section.

        Args:
            documents: List of document dictionaries
        """
        # Clear existing documents
        while self.documents_layout.count() > 1:  # Keep stretch at end
            item = self.documents_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Add document cards
        for doc in documents:
            card = DocumentCard(doc)
            self.documents_layout.insertWidget(self.documents_layout.count() - 1, card)

        # Expand documents section
        self.documents_section.expand()

    @Slot()
    def _on_clear(self):
        """Handle clear button click."""
        self.question_input.clear()
        self.workflow_content.setText("Click 'Start Research' to begin the multi-agent workflow.")
        self.workflow_section.set_header_color("#e8e8e8")
        self.report_viewer.set_markdown("*Report will appear here after workflow completes.*")
        self.export_button.setEnabled(False)
        self.current_results = {}

        # Clear documents
        while self.documents_layout.count() > 1:
            item = self.documents_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self.status_message.emit("Cleared research interface")

    @Slot()
    def _on_export_report(self):
        """Handle export report button click."""
        # TODO: Implement full export functionality with file dialog
        QMessageBox.information(
            self,
            "Export Report",
            "Export functionality will be implemented in a future update.\n\n"
            "For now, you can copy the report text from the preview.",
        )
