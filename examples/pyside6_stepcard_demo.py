#!/usr/bin/env python3
"""
PySide6 StepCard Widget Demo - Simplified Example

This focused demo shows just the StepCard widget pattern for easy understanding.
Run this first to see how the collapsible card works before the full GUI.
"""

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QPushButton,
    QLabel, QScrollArea
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
import sys

# Import the StepCard and related classes from the POC
# In production, these would be in separate modules
from pyside6_poc_research_gui import StepCard, WorkflowStep, StepStatus


class StepCardDemo(QMainWindow):
    """Simple demo window showing StepCard widgets in action."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("StepCard Widget Demo")
        self.setGeometry(200, 200, 800, 700)

        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # Header
        header = QLabel("StepCard Widget Demonstration")
        header.setFont(QFont("Arial", 16, QFont.Bold))
        header.setStyleSheet("color: #1976D2; padding: 10px;")
        main_layout.addWidget(header)

        # Info text
        info = QLabel(
            "Click on any card header to expand/collapse it.\n"
            "Click the buttons below to simulate different status changes."
        )
        info.setStyleSheet("color: #666; padding: 5px;")
        main_layout.addWidget(info)

        # Control buttons
        button_layout = QVBoxLayout()
        button_layout.setSpacing(5)

        run_button = QPushButton("▶️ Simulate Running All Steps")
        run_button.clicked.connect(self.simulate_running_steps)
        button_layout.addWidget(run_button)

        complete_button = QPushButton("✅ Complete All Steps")
        complete_button.clicked.connect(self.complete_all_steps)
        button_layout.addWidget(complete_button)

        error_button = QPushButton("❌ Simulate Error in Step 3")
        error_button.clicked.connect(self.simulate_error)
        button_layout.addWidget(error_button)

        reset_button = QPushButton("🔄 Reset All Steps")
        reset_button.clicked.connect(self.reset_all_steps)
        button_layout.addWidget(reset_button)

        main_layout.addLayout(button_layout)

        # Scrollable area for step cards
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setSpacing(10)

        # Create 5 step cards
        self.step_cards = []
        workflow_steps = [
            WorkflowStep.COLLECT_RESEARCH_QUESTION,
            WorkflowStep.GENERATE_AND_EDIT_QUERY,
            WorkflowStep.SEARCH_DOCUMENTS,
            WorkflowStep.SCORE_DOCUMENTS,
            WorkflowStep.EXTRACT_CITATIONS,
        ]

        for step in workflow_steps:
            card = StepCard(step)
            # Connect expand signal to see events (optional)
            card.expand_changed.connect(
                lambda expanded, s=step: print(f"{s.display_name} {'expanded' if expanded else 'collapsed'}")
            )
            self.step_cards.append(card)
            scroll_layout.addWidget(card)

        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll, 1)

    def reset_all_steps(self):
        """Reset all steps to pending."""
        for card in self.step_cards:
            card.update_status(StepStatus.PENDING, "Waiting to start...")

    def complete_all_steps(self):
        """Mark all steps as completed."""
        for card in self.step_cards:
            card.update_status(StepStatus.COMPLETED, f"{card.step.display_name} completed successfully!")

    def simulate_error(self):
        """Simulate an error in the third step."""
        if len(self.step_cards) > 2:
            self.step_cards[2].update_status(
                StepStatus.ERROR,
                "Database connection failed: Connection timeout after 30 seconds"
            )

    def simulate_running_steps(self):
        """Simulate running steps sequentially with progress bars."""
        self.reset_all_steps()

        # Use QTimer to simulate async execution
        self.current_step = 0
        self.step_timer = QTimer()
        self.step_timer.timeout.connect(self.run_next_step)
        self.step_timer.start(1500)  # Progress every 1.5 seconds

    def run_next_step(self):
        """Run the next step in the simulation."""
        if self.current_step > 0:
            # Complete previous step
            prev_card = self.step_cards[self.current_step - 1]
            prev_card.update_status(
                StepStatus.COMPLETED,
                f"{prev_card.step.display_name} completed successfully!"
            )

        if self.current_step < len(self.step_cards):
            # Start current step
            card = self.step_cards[self.current_step]
            card.update_status(
                StepStatus.RUNNING,
                f"Processing {card.step.display_name.lower()}..."
            )

            # Simulate progress for some steps
            if self.current_step in [2, 3]:  # Search and scoring steps
                # Simulate progress updates
                for i in range(1, 11):
                    QTimer.singleShot(
                        i * 100,
                        lambda idx=i, c=card: c.update_progress(idx, 10, f"Item {idx}")
                    )

            self.current_step += 1

        else:
            # All steps complete
            self.step_timer.stop()


def main():
    """Main entry point."""
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    window = StepCardDemo()
    window.show()

    sys.exit(app.exec())


if __name__ == '__main__':
    main()
