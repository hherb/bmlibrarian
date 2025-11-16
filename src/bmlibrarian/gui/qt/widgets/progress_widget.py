"""
Progress indicator widgets for BMLibrarian Qt GUI.

Provides various progress indicators for long-running operations.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar,
    QFrame
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QFont
from typing import Optional


class ProgressWidget(QFrame):
    """
    Simple progress widget with progress bar and status text.

    Can be used inline or as a standalone widget.
    """

    def __init__(self, parent: Optional[QWidget] = None):
        """
        Initialize progress widget.

        Args:
            parent: Optional parent widget
        """
        super().__init__(parent)

        self.progress_bar: Optional[QProgressBar] = None
        self.status_label: Optional[QLabel] = None
        self.detail_label: Optional[QLabel] = None

        self._setup_ui()

    def _setup_ui(self):
        """Setup the user interface."""
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet(
            """
            ProgressWidget {
                background-color: #f8f9fa;
                border: 1px solid #dee2e6;
                border-radius: 4px;
                padding: 10px;
            }
            """
        )

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # Status label
        self.status_label = QLabel("Processing...")
        self.status_label.setFont(QFont("", 10, QFont.Bold))
        layout.addWidget(self.status_label)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        layout.addWidget(self.progress_bar)

        # Detail label
        self.detail_label = QLabel("")
        self.detail_label.setStyleSheet("color: #6c757d; font-size: 9pt;")
        self.detail_label.setWordWrap(True)
        layout.addWidget(self.detail_label)

    def set_progress(self, value: int, status: str = "", details: str = ""):
        """
        Update progress.

        Args:
            value: Progress value (0-100)
            status: Status message
            details: Optional detailed message
        """
        self.progress_bar.setValue(value)

        if status:
            self.status_label.setText(status)

        if details:
            self.detail_label.setText(details)

    def set_indeterminate(self, enabled: bool = True):
        """
        Set indeterminate mode (for unknown duration tasks).

        Args:
            enabled: Whether to enable indeterminate mode
        """
        if enabled:
            self.progress_bar.setRange(0, 0)
        else:
            self.progress_bar.setRange(0, 100)

    def reset(self):
        """Reset progress widget to initial state."""
        self.progress_bar.setValue(0)
        self.progress_bar.setRange(0, 100)
        self.status_label.setText("Ready")
        self.detail_label.setText("")


class StepProgressWidget(QFrame):
    """
    Multi-step progress indicator showing progress through workflow steps.

    Displays current step, total steps, and overall progress.
    """

    def __init__(self, total_steps: int, parent: Optional[QWidget] = None):
        """
        Initialize step progress widget.

        Args:
            total_steps: Total number of steps
            parent: Optional parent widget
        """
        super().__init__(parent)

        self.total_steps = total_steps
        self.current_step = 0

        self.step_label: Optional[QLabel] = None
        self.progress_bar: Optional[QProgressBar] = None
        self.step_name_label: Optional[QLabel] = None

        self._setup_ui()

    def _setup_ui(self):
        """Setup the user interface."""
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet(
            """
            StepProgressWidget {
                background-color: white;
                border: 2px solid #3498db;
                border-radius: 6px;
                padding: 15px;
            }
            """
        )

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Step counter
        self.step_label = QLabel(f"Step {self.current_step} of {self.total_steps}")
        self.step_label.setFont(QFont("", 11, QFont.Bold))
        self.step_label.setStyleSheet("color: #3498db;")
        layout.addWidget(self.step_label)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(self.total_steps)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet(
            """
            QProgressBar {
                border: 2px solid #e0e0e0;
                border-radius: 5px;
                text-align: center;
                height: 25px;
            }
            QProgressBar::chunk {
                background-color: #3498db;
                border-radius: 3px;
            }
            """
        )
        layout.addWidget(self.progress_bar)

        # Step name
        self.step_name_label = QLabel("")
        self.step_name_label.setFont(QFont("", 10))
        self.step_name_label.setStyleSheet("color: #555;")
        self.step_name_label.setWordWrap(True)
        layout.addWidget(self.step_name_label)

    def set_step(self, step_number: int, step_name: str = ""):
        """
        Set current step.

        Args:
            step_number: Current step number (1-indexed)
            step_name: Name/description of current step
        """
        self.current_step = step_number
        self.step_label.setText(f"Step {step_number} of {self.total_steps}")
        self.progress_bar.setValue(step_number)

        if step_name:
            self.step_name_label.setText(step_name)

    def complete(self):
        """Mark all steps as complete."""
        self.current_step = self.total_steps
        self.step_label.setText(f"Complete ({self.total_steps} steps)")
        self.step_label.setStyleSheet("color: #27ae60;")
        self.progress_bar.setValue(self.total_steps)
        self.step_name_label.setText("✅ All steps completed")

    def reset(self):
        """Reset to initial state."""
        self.current_step = 0
        self.step_label.setText(f"Step 0 of {self.total_steps}")
        self.step_label.setStyleSheet("color: #3498db;")
        self.progress_bar.setValue(0)
        self.step_name_label.setText("")


class SpinnerWidget(QWidget):
    """
    Animated spinner widget for indeterminate progress.

    Shows a simple text-based spinner animation.
    """

    def __init__(self, message: str = "Loading...", parent: Optional[QWidget] = None):
        """
        Initialize spinner widget.

        Args:
            message: Message to display with spinner
            parent: Optional parent widget
        """
        super().__init__(parent)

        self.message = message
        self.spinner_label: Optional[QLabel] = None
        self.message_label: Optional[QLabel] = None
        self.timer: Optional[QTimer] = None
        self.spinner_chars = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
        self.current_char_index = 0

        self._setup_ui()

    def _setup_ui(self):
        """Setup the user interface."""
        layout = QHBoxLayout(self)
        layout.setSpacing(10)

        # Spinner label
        self.spinner_label = QLabel(self.spinner_chars[0])
        self.spinner_label.setFont(QFont("", 16))
        self.spinner_label.setStyleSheet("color: #3498db;")
        layout.addWidget(self.spinner_label)

        # Message label
        self.message_label = QLabel(self.message)
        self.message_label.setFont(QFont("", 10))
        layout.addWidget(self.message_label)

        layout.addStretch()

        # Timer for animation
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._update_spinner)

    def start(self):
        """Start spinner animation."""
        self.timer.start(100)  # Update every 100ms

    def stop(self):
        """Stop spinner animation."""
        self.timer.stop()
        self.spinner_label.setText("✓")
        self.spinner_label.setStyleSheet("color: #27ae60;")

    def set_message(self, message: str):
        """
        Update spinner message.

        Args:
            message: New message
        """
        self.message = message
        self.message_label.setText(message)

    def _update_spinner(self):
        """Update spinner character."""
        self.current_char_index = (self.current_char_index + 1) % len(self.spinner_chars)
        self.spinner_label.setText(self.spinner_chars[self.current_char_index])


class CompactProgressWidget(QWidget):
    """
    Compact progress indicator for inline use.

    Minimal progress indicator suitable for embedding in other widgets.
    """

    def __init__(self, parent: Optional[QWidget] = None):
        """
        Initialize compact progress widget.

        Args:
            parent: Optional parent widget
        """
        super().__init__(parent)

        self.progress_bar: Optional[QProgressBar] = None

        self._setup_ui()

    def _setup_ui(self):
        """Setup the user interface."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximumHeight(10)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet(
            """
            QProgressBar {
                border: 1px solid #ddd;
                border-radius: 3px;
                background-color: #f0f0f0;
            }
            QProgressBar::chunk {
                background-color: #3498db;
                border-radius: 2px;
            }
            """
        )
        layout.addWidget(self.progress_bar)

    def set_progress(self, value: int):
        """
        Update progress.

        Args:
            value: Progress value (0-100)
        """
        self.progress_bar.setValue(value)

    def set_indeterminate(self, enabled: bool = True):
        """
        Set indeterminate mode.

        Args:
            enabled: Whether to enable indeterminate mode
        """
        if enabled:
            self.progress_bar.setRange(0, 0)
        else:
            self.progress_bar.setRange(0, 100)
