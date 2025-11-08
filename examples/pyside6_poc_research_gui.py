#!/usr/bin/env python3
"""
PySide6 Proof-of-Concept: BMLibrarian Research GUI Migration

Demonstrates key patterns for migrating from Flet to PySide6:
- Custom collapsible StepCard widget with status tracking
- Tabbed interface with workflow, documents, and report tabs
- Threading with signals/slots for long-running operations
- Markdown rendering for reports
- Progress bars and status updates
- File save dialogs

This POC shows the architecture and patterns - not a complete implementation.
"""

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QTextEdit, QLineEdit, QProgressBar,
    QTabWidget, QGroupBox, QScrollArea, QFileDialog, QCheckBox,
    QSpinBox, QFrame, QMessageBox
)
from PySide6.QtCore import (
    Qt, Signal, QThread, QTimer, QPropertyAnimation, QEasingCurve
)
from PySide6.QtGui import QIcon, QColor, QPalette, QFont
import sys
import time
from enum import Enum, auto
from typing import Optional, List
from dataclasses import dataclass


# ============================================================================
# Workflow Step Definitions (mimics your WorkflowStep enum)
# ============================================================================

class WorkflowStep(Enum):
    """Workflow steps matching BMLibrarian architecture."""
    COLLECT_RESEARCH_QUESTION = auto()
    GENERATE_AND_EDIT_QUERY = auto()
    SEARCH_DOCUMENTS = auto()
    REVIEW_SEARCH_RESULTS = auto()
    SCORE_DOCUMENTS = auto()
    EXTRACT_CITATIONS = auto()
    GENERATE_REPORT = auto()
    PERFORM_COUNTERFACTUAL_ANALYSIS = auto()
    SEARCH_CONTRADICTORY_EVIDENCE = auto()
    EDIT_COMPREHENSIVE_REPORT = auto()
    EXPORT_REPORT = auto()

    @property
    def display_name(self) -> str:
        """Human-readable display name."""
        names = {
            self.COLLECT_RESEARCH_QUESTION: "Research Question Collection",
            self.GENERATE_AND_EDIT_QUERY: "Query Generation & Editing",
            self.SEARCH_DOCUMENTS: "Document Search",
            self.REVIEW_SEARCH_RESULTS: "Search Results Review",
            self.SCORE_DOCUMENTS: "Document Relevance Scoring",
            self.EXTRACT_CITATIONS: "Citation Extraction",
            self.GENERATE_REPORT: "Report Generation",
            self.PERFORM_COUNTERFACTUAL_ANALYSIS: "Counterfactual Analysis",
            self.SEARCH_CONTRADICTORY_EVIDENCE: "Contradictory Evidence Search",
            self.EDIT_COMPREHENSIVE_REPORT: "Comprehensive Report Editing",
            self.EXPORT_REPORT: "Report Export",
        }
        return names.get(self, self.name.replace('_', ' ').title())

    @property
    def description(self) -> str:
        """Step description."""
        descs = {
            self.COLLECT_RESEARCH_QUESTION: "Collect the research question from user",
            self.GENERATE_AND_EDIT_QUERY: "Generate PostgreSQL query and allow editing",
            self.SEARCH_DOCUMENTS: "Execute database search using the query",
            self.SCORE_DOCUMENTS: "Score documents (1-5) for relevance",
            self.EXTRACT_CITATIONS: "Extract relevant passages from documents",
            self.GENERATE_REPORT: "Generate medical publication-style report",
        }
        return descs.get(self, "Processing step")


# ============================================================================
# Status Icons and Colors
# ============================================================================

class StepStatus(Enum):
    """Step status states."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    ERROR = "error"
    WAITING = "waiting"


def get_status_color(status: StepStatus) -> QColor:
    """Get color for status."""
    colors = {
        StepStatus.PENDING: QColor(180, 180, 180),      # Gray
        StepStatus.RUNNING: QColor(33, 150, 243),       # Blue
        StepStatus.COMPLETED: QColor(76, 175, 80),      # Green
        StepStatus.ERROR: QColor(244, 67, 54),          # Red
        StepStatus.WAITING: QColor(255, 152, 0),        # Orange
    }
    return colors.get(status, QColor(128, 128, 128))


def get_status_icon(status: StepStatus) -> str:
    """Get unicode icon for status."""
    icons = {
        StepStatus.PENDING: "⭕",
        StepStatus.RUNNING: "▶️",
        StepStatus.COMPLETED: "✅",
        StepStatus.ERROR: "❌",
        StepStatus.WAITING: "⏸️",
    }
    return icons.get(status, "•")


# ============================================================================
# Custom StepCard Widget (collapsible with status)
# ============================================================================

class StepCard(QWidget):
    """
    Collapsible card widget representing a workflow step.

    Key features demonstrated:
    - Custom widget with internal state
    - Collapsible/expandable UI
    - Status tracking with visual feedback
    - Progress bar integration
    - Signal emission for user interactions
    """

    # Signal emitted when expand/collapse state changes
    expand_changed = Signal(bool)

    def __init__(self, step: WorkflowStep, parent=None):
        super().__init__(parent)
        self.step = step
        self.status = StepStatus.PENDING
        self.content_text = "Waiting to start..."
        self.expanded = False

        self._init_ui()

    def _init_ui(self):
        """Initialize the UI components."""
        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(0)

        # Header (always visible, clickable to expand/collapse)
        self.header_frame = QFrame()
        self.header_frame.setFrameStyle(QFrame.StyledPanel | QFrame.Raised)
        self.header_frame.setStyleSheet("""
            QFrame {
                background-color: #f5f5f5;
                border: 1px solid #ddd;
                border-radius: 4px;
                padding: 8px;
            }
            QFrame:hover {
                background-color: #eeeeee;
            }
        """)
        self.header_frame.setCursor(Qt.PointingHandCursor)

        # Make header clickable
        self.header_frame.mousePressEvent = lambda e: self.toggle_expand()

        header_layout = QHBoxLayout(self.header_frame)
        header_layout.setContentsMargins(8, 8, 8, 8)

        # Status icon
        self.status_label = QLabel(get_status_icon(self.status))
        self.status_label.setFont(QFont("Arial", 12))
        header_layout.addWidget(self.status_label)

        # Title and description
        title_layout = QVBoxLayout()
        self.title_label = QLabel(self.step.display_name)
        self.title_label.setFont(QFont("Arial", 11, QFont.Bold))
        title_layout.addWidget(self.title_label)

        self.desc_label = QLabel(self.step.description)
        self.desc_label.setFont(QFont("Arial", 9))
        self.desc_label.setStyleSheet("color: #666;")
        title_layout.addWidget(self.desc_label)

        header_layout.addLayout(title_layout, 1)

        # Expand/collapse indicator
        self.expand_indicator = QLabel("▼")
        self.expand_indicator.setAlignment(Qt.AlignCenter)
        header_layout.addWidget(self.expand_indicator)

        main_layout.addWidget(self.header_frame)

        # Content area (collapsible)
        self.content_widget = QWidget()
        self.content_widget.setVisible(False)

        content_layout = QVBoxLayout(self.content_widget)
        content_layout.setContentsMargins(10, 5, 10, 5)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p% (%v/%m)")
        content_layout.addWidget(self.progress_bar)

        # Content text area
        self.content_display = QTextEdit()
        self.content_display.setReadOnly(True)
        self.content_display.setMaximumHeight(150)
        self.content_display.setStyleSheet("""
            QTextEdit {
                background-color: #fafafa;
                border: 1px solid #ddd;
                border-radius: 3px;
                padding: 8px;
            }
        """)
        self.content_display.setPlainText(self.content_text)
        content_layout.addWidget(self.content_display)

        main_layout.addWidget(self.content_widget)

    def toggle_expand(self):
        """Toggle expanded/collapsed state."""
        self.expanded = not self.expanded
        self.content_widget.setVisible(self.expanded)
        self.expand_indicator.setText("▲" if self.expanded else "▼")
        self.expand_changed.emit(self.expanded)

    def set_expanded(self, expanded: bool):
        """Programmatically set expanded state."""
        if self.expanded != expanded:
            self.toggle_expand()

    def update_status(self, status: StepStatus, content: Optional[str] = None):
        """Update step status and optionally content."""
        self.status = status

        # Update status icon and color
        self.status_label.setText(get_status_icon(status))
        color = get_status_color(status)
        self.status_label.setStyleSheet(f"color: rgb({color.red()}, {color.green()}, {color.blue()});")

        # Update content if provided
        if content is not None:
            self.content_text = content
            self.content_display.setPlainText(content)

        # Show/hide progress bar based on status
        self.progress_bar.setVisible(status == StepStatus.RUNNING)

        # Auto-expand when running or error
        if status in (StepStatus.RUNNING, StepStatus.ERROR) and not self.expanded:
            self.set_expanded(True)

    def update_progress(self, current: int, total: int, item_name: str = ""):
        """Update progress bar."""
        if total > 0:
            self.progress_bar.setMaximum(total)
            self.progress_bar.setValue(current)
            self.progress_bar.setVisible(True)

            if item_name:
                self.progress_bar.setFormat(f"{current}/{total} - {item_name}")


# ============================================================================
# Worker Thread for Simulated Workflow (demonstrates threading with signals)
# ============================================================================

class WorkflowWorker(QThread):
    """
    Worker thread for executing workflow steps.

    Demonstrates Qt threading pattern:
    - Runs in separate thread to keep GUI responsive
    - Emits signals to update GUI (thread-safe)
    - Can be stopped gracefully
    """

    # Signals for communication with main thread
    step_started = Signal(WorkflowStep)
    step_progress = Signal(WorkflowStep, int, int, str)  # step, current, total, item_name
    step_completed = Signal(WorkflowStep, str)  # step, result_text
    step_error = Signal(WorkflowStep, str)  # step, error_message
    workflow_finished = Signal(str)  # final_report

    def __init__(self, research_question: str, max_results: int):
        super().__init__()
        self.research_question = research_question
        self.max_results = max_results
        self.is_running = True

    def run(self):
        """Execute the workflow (simulated for demo)."""
        try:
            # Step 1: Collect research question
            self.step_started.emit(WorkflowStep.COLLECT_RESEARCH_QUESTION)
            time.sleep(0.5)
            self.step_completed.emit(
                WorkflowStep.COLLECT_RESEARCH_QUESTION,
                f"Research question: {self.research_question}"
            )

            if not self.is_running:
                return

            # Step 2: Generate query
            self.step_started.emit(WorkflowStep.GENERATE_AND_EDIT_QUERY)
            time.sleep(1.0)
            query = f"SELECT * FROM documents WHERE text_search @@ to_tsquery('cardiovascular & exercise')"
            self.step_completed.emit(
                WorkflowStep.GENERATE_AND_EDIT_QUERY,
                f"Generated SQL query:\n{query}"
            )

            if not self.is_running:
                return

            # Step 3: Search documents (with progress)
            self.step_started.emit(WorkflowStep.SEARCH_DOCUMENTS)
            for i in range(10):
                if not self.is_running:
                    return
                time.sleep(0.2)
                self.step_progress.emit(
                    WorkflowStep.SEARCH_DOCUMENTS,
                    i + 1, 10,
                    f"Document {i+1}"
                )
            self.step_completed.emit(
                WorkflowStep.SEARCH_DOCUMENTS,
                f"Found {self.max_results} documents matching the query"
            )

            if not self.is_running:
                return

            # Step 4: Score documents (with progress)
            self.step_started.emit(WorkflowStep.SCORE_DOCUMENTS)
            num_to_score = min(20, self.max_results)
            for i in range(num_to_score):
                if not self.is_running:
                    return
                time.sleep(0.15)
                self.step_progress.emit(
                    WorkflowStep.SCORE_DOCUMENTS,
                    i + 1, num_to_score,
                    f"Scoring doc {i+1}"
                )
            self.step_completed.emit(
                WorkflowStep.SCORE_DOCUMENTS,
                f"Scored {num_to_score} documents. 15 documents above threshold (score ≥ 3.0)"
            )

            if not self.is_running:
                return

            # Step 5: Extract citations
            self.step_started.emit(WorkflowStep.EXTRACT_CITATIONS)
            time.sleep(1.5)
            self.step_completed.emit(
                WorkflowStep.EXTRACT_CITATIONS,
                "Extracted 23 relevant citations from 15 high-scoring documents"
            )

            if not self.is_running:
                return

            # Step 6: Generate report
            self.step_started.emit(WorkflowStep.GENERATE_REPORT)
            time.sleep(2.0)
            report = self._generate_mock_report()
            self.step_completed.emit(
                WorkflowStep.GENERATE_REPORT,
                "Generated comprehensive medical literature report"
            )

            # Workflow complete
            self.workflow_finished.emit(report)

        except Exception as e:
            self.step_error.emit(WorkflowStep.GENERATE_REPORT, str(e))

    def stop(self):
        """Stop the workflow gracefully."""
        self.is_running = False

    def _generate_mock_report(self) -> str:
        """Generate a mock markdown report."""
        return f"""# Research Report: {self.research_question}

## Summary

This report synthesizes evidence from 23 citations extracted from 15 high-quality studies
regarding the cardiovascular benefits of exercise.

## Key Findings

### 1. Cardiovascular Risk Reduction

Regular aerobic exercise has been consistently associated with reduced cardiovascular disease
risk (Smith et al., 2023). A meta-analysis of 47 studies found that individuals engaging in
150 minutes of moderate-intensity exercise per week showed a 30% reduction in cardiovascular
events compared to sedentary controls.

### 2. Blood Pressure Effects

Exercise training demonstrates significant antihypertensive effects, with reductions of 5-7 mmHg
in systolic blood pressure observed across multiple randomized controlled trials (Johnson et al., 2023).

### 3. Lipid Profile Improvements

Regular physical activity favorably modulates lipid profiles, increasing HDL cholesterol by
3-5 mg/dL and reducing triglycerides by 10-15% (Williams et al., 2024).

## Conclusion

The evidence strongly supports regular aerobic exercise as a cornerstone intervention for
cardiovascular health improvement and disease prevention.

## References

1. Smith A, et al. (2023). "Exercise and cardiovascular risk: A systematic review." *JAMA Cardiology*.
2. Johnson B, et al. (2023). "Blood pressure responses to exercise training." *Circulation*.
3. Williams C, et al. (2024). "Physical activity and lipid metabolism." *European Heart Journal*.

---
*Report generated by BMLibrarian on {time.strftime('%Y-%m-%d %H:%M:%S')}*
"""


# ============================================================================
# Main Research GUI Window
# ============================================================================

class ResearchGUI(QMainWindow):
    """
    Main research GUI window demonstrating PySide6 patterns.

    Key demonstrations:
    - QMainWindow with menubar, toolbar, statusbar
    - QTabWidget for organizing interface
    - Layout management (QVBoxLayout, QHBoxLayout)
    - Threading with worker and signals/slots
    - Markdown rendering (using QTextEdit with markdown support)
    - File dialogs for saving reports
    """

    def __init__(self):
        super().__init__()
        self.workflow_worker: Optional[WorkflowWorker] = None
        self.step_cards: dict[WorkflowStep, StepCard] = {}
        self.current_report = ""

        self._init_ui()

    def _init_ui(self):
        """Initialize the user interface."""
        self.setWindowTitle("BMLibrarian Research Assistant - PySide6 POC")
        self.setGeometry(100, 100, 1200, 900)

        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)

        # Header
        header_label = QLabel("BMLibrarian Research Assistant")
        header_label.setFont(QFont("Arial", 18, QFont.Bold))
        header_label.setStyleSheet("color: #1976D2; padding: 10px;")
        main_layout.addWidget(header_label)

        # Control section
        controls_group = self._create_controls_section()
        main_layout.addWidget(controls_group)

        # Tabbed interface
        self.tabs = QTabWidget()
        self.tabs.setTabPosition(QTabWidget.North)

        # Tab 1: Workflow Progress
        workflow_tab = self._create_workflow_tab()
        self.tabs.addTab(workflow_tab, "📊 Workflow Progress")

        # Tab 2: Documents (placeholder for demo)
        documents_tab = self._create_documents_tab()
        self.tabs.addTab(documents_tab, "📄 Documents")

        # Tab 3: Report Preview
        report_tab = self._create_report_tab()
        self.tabs.addTab(report_tab, "📝 Report")

        main_layout.addWidget(self.tabs, 1)  # Stretch factor 1 = expand

        # Status bar
        self.statusBar().showMessage("Ready to start research")

    def _create_controls_section(self) -> QGroupBox:
        """Create the controls section (question input, settings, start button)."""
        group = QGroupBox("Research Configuration")
        layout = QVBoxLayout()

        # Research question input
        question_layout = QHBoxLayout()
        question_layout.addWidget(QLabel("Research Question:"))
        self.question_input = QLineEdit()
        self.question_input.setPlaceholderText("Enter your medical research question...")
        self.question_input.setText("What are the cardiovascular benefits of exercise?")
        question_layout.addWidget(self.question_input, 1)
        layout.addLayout(question_layout)

        # Settings row
        settings_layout = QHBoxLayout()

        # Max results
        settings_layout.addWidget(QLabel("Max Results:"))
        self.max_results_spin = QSpinBox()
        self.max_results_spin.setRange(10, 1000)
        self.max_results_spin.setValue(100)
        self.max_results_spin.setSuffix(" docs")
        settings_layout.addWidget(self.max_results_spin)

        settings_layout.addSpacing(20)

        # Interactive mode toggle
        self.interactive_checkbox = QCheckBox("Interactive mode")
        self.interactive_checkbox.setChecked(False)
        settings_layout.addWidget(self.interactive_checkbox)

        settings_layout.addSpacing(20)

        # Counterfactual analysis toggle
        self.counterfactual_checkbox = QCheckBox("Comprehensive counterfactual analysis")
        self.counterfactual_checkbox.setChecked(True)
        settings_layout.addWidget(self.counterfactual_checkbox)

        settings_layout.addStretch()
        layout.addLayout(settings_layout)

        # Start button
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.start_button = QPushButton("▶ Start Research")
        self.start_button.setMinimumWidth(150)
        self.start_button.setMinimumHeight(40)
        self.start_button.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:pressed {
                background-color: #3d8b40;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
        """)
        self.start_button.clicked.connect(self.on_start_research)
        button_layout.addWidget(self.start_button)

        self.stop_button = QPushButton("⏹ Stop")
        self.stop_button.setMinimumWidth(100)
        self.stop_button.setMinimumHeight(40)
        self.stop_button.setEnabled(False)
        self.stop_button.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #da190b;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
        """)
        self.stop_button.clicked.connect(self.on_stop_research)
        button_layout.addWidget(self.stop_button)

        layout.addLayout(button_layout)

        group.setLayout(layout)
        return group

    def _create_workflow_tab(self) -> QWidget:
        """Create the workflow progress tab with step cards."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Scrollable area for step cards
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setSpacing(8)

        # Create step cards for main workflow steps
        workflow_steps = [
            WorkflowStep.COLLECT_RESEARCH_QUESTION,
            WorkflowStep.GENERATE_AND_EDIT_QUERY,
            WorkflowStep.SEARCH_DOCUMENTS,
            WorkflowStep.SCORE_DOCUMENTS,
            WorkflowStep.EXTRACT_CITATIONS,
            WorkflowStep.GENERATE_REPORT,
        ]

        for step in workflow_steps:
            card = StepCard(step)
            self.step_cards[step] = card
            scroll_layout.addWidget(card)

        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll)

        return widget

    def _create_documents_tab(self) -> QWidget:
        """Create documents tab (placeholder for demo)."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        label = QLabel("Document list would appear here.\n\n"
                      "In full implementation, this would show:\n"
                      "- Search results with expandable abstracts\n"
                      "- Scored documents with relevance ratings\n"
                      "- Citations with highlighted passages\n\n"
                      "Using QTableView with custom model for efficient display.")
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet("color: #666; font-size: 12px;")
        layout.addWidget(label)

        return widget

    def _create_report_tab(self) -> QWidget:
        """Create report preview tab with markdown rendering."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Toolbar for report actions
        toolbar_layout = QHBoxLayout()
        toolbar_layout.addStretch()

        save_button = QPushButton("💾 Save Report")
        save_button.clicked.connect(self.on_save_report)
        toolbar_layout.addWidget(save_button)

        layout.addLayout(toolbar_layout)

        # Report preview area with markdown support
        self.report_preview = QTextEdit()
        self.report_preview.setReadOnly(True)

        # Enable markdown rendering
        # Note: For production, you'd use QTextDocument with markdown parser
        # or integrate a proper markdown rendering library
        self.report_preview.setMarkdown("*No report generated yet. Start a research workflow to generate a report.*")

        layout.addWidget(self.report_preview)

        return widget

    # ========================================================================
    # Event Handlers
    # ========================================================================

    def on_start_research(self):
        """Handle start research button click."""
        question = self.question_input.text().strip()

        if not question:
            QMessageBox.warning(self, "Input Required", "Please enter a research question.")
            return

        # Disable start button, enable stop button
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)

        # Reset all step cards
        for card in self.step_cards.values():
            card.update_status(StepStatus.PENDING, "Waiting to start...")

        # Update status bar
        self.statusBar().showMessage("Starting research workflow...")

        # Switch to workflow tab
        self.tabs.setCurrentIndex(0)

        # Create and start worker thread
        self.workflow_worker = WorkflowWorker(
            research_question=question,
            max_results=self.max_results_spin.value()
        )

        # Connect signals to slots
        self.workflow_worker.step_started.connect(self.on_step_started)
        self.workflow_worker.step_progress.connect(self.on_step_progress)
        self.workflow_worker.step_completed.connect(self.on_step_completed)
        self.workflow_worker.step_error.connect(self.on_step_error)
        self.workflow_worker.workflow_finished.connect(self.on_workflow_finished)

        # Start the worker thread
        self.workflow_worker.start()

    def on_stop_research(self):
        """Handle stop button click."""
        if self.workflow_worker and self.workflow_worker.isRunning():
            self.workflow_worker.stop()
            self.workflow_worker.wait()  # Wait for thread to finish

            self.statusBar().showMessage("Workflow stopped by user")
            self.start_button.setEnabled(True)
            self.stop_button.setEnabled(False)

    def on_step_started(self, step: WorkflowStep):
        """Handle step started signal from worker."""
        if step in self.step_cards:
            self.step_cards[step].update_status(
                StepStatus.RUNNING,
                f"Processing {step.display_name.lower()}..."
            )
        self.statusBar().showMessage(f"Running: {step.display_name}")

    def on_step_progress(self, step: WorkflowStep, current: int, total: int, item_name: str):
        """Handle progress update signal from worker."""
        if step in self.step_cards:
            self.step_cards[step].update_progress(current, total, item_name)

    def on_step_completed(self, step: WorkflowStep, result_text: str):
        """Handle step completed signal from worker."""
        if step in self.step_cards:
            self.step_cards[step].update_status(StepStatus.COMPLETED, result_text)
        self.statusBar().showMessage(f"Completed: {step.display_name}")

    def on_step_error(self, step: WorkflowStep, error_message: str):
        """Handle step error signal from worker."""
        if step in self.step_cards:
            self.step_cards[step].update_status(
                StepStatus.ERROR,
                f"Error: {error_message}"
            )
        self.statusBar().showMessage(f"Error in {step.display_name}")

        # Re-enable start button
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)

    def on_workflow_finished(self, report: str):
        """Handle workflow finished signal from worker."""
        self.current_report = report

        # Update report preview
        self.report_preview.setMarkdown(report)

        # Switch to report tab
        self.tabs.setCurrentIndex(2)

        # Update status
        self.statusBar().showMessage("Workflow completed successfully!")

        # Re-enable start button
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)

        # Show completion message
        QMessageBox.information(
            self,
            "Workflow Complete",
            "Research workflow completed successfully!\n\nThe report is now available in the Report tab."
        )

    def on_save_report(self):
        """Handle save report button click."""
        if not self.current_report:
            QMessageBox.warning(self, "No Report", "No report available to save. Run a research workflow first.")
            return

        # Show file save dialog
        file_path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Save Report",
            "bmlibrarian_report.md",
            "Markdown Files (*.md);;Text Files (*.txt);;All Files (*)"
        )

        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(self.current_report)

                self.statusBar().showMessage(f"Report saved to {file_path}")
                QMessageBox.information(self, "Success", f"Report saved successfully to:\n{file_path}")

            except Exception as e:
                QMessageBox.critical(self, "Save Error", f"Failed to save report:\n{str(e)}")


# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    """Main entry point for the POC application."""
    app = QApplication(sys.argv)

    # Set application-wide style
    app.setStyle("Fusion")

    # Create and show main window
    window = ResearchGUI()
    window.show()

    sys.exit(app.exec())


if __name__ == '__main__':
    main()
