"""
Timer Widget for Fact-Checker Review.

Tracks time spent reviewing each statement with pause/resume functionality.
"""

import time
from typing import Optional
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont

# Import DPI-aware styling
from ...resources.styles import get_font_scale


class TimerWidget(QWidget):
    """Timer widget for tracking review time."""

    # Signals
    timer_updated = Signal(int)  # Emits elapsed seconds

    def __init__(self, parent: Optional[QWidget] = None):
        """
        Initialize timer widget.

        Args:
            parent: Optional parent widget
        """
        super().__init__(parent)

        # DPI-aware scaling
        self.scale = get_font_scale()

        # Timer state
        self._start_time: Optional[float] = None
        self._pause_time: Optional[float] = None
        self._elapsed_seconds: int = 0  # Cumulative time across sessions
        self._current_session_start: Optional[float] = None
        self._is_running: bool = False
        self._is_paused: bool = False

        # Qt timer for display updates
        self._update_timer = QTimer(self)
        self._update_timer.timeout.connect(self._update_display)

        self._setup_ui()

    def _setup_ui(self):
        """Setup the user interface."""
        s = self.scale

        layout = QVBoxLayout(self)
        layout.setContentsMargins(s['spacing_medium'], s['spacing_medium'], s['spacing_medium'], s['spacing_medium'])
        layout.setSpacing(s['spacing_tiny'])

        # Title
        title_layout = QHBoxLayout()
        title_label = QLabel("⏱ Review Time")
        title_label.setStyleSheet("font-weight: bold; color: #1976d2;")
        title_layout.addWidget(title_label)
        layout.addLayout(title_layout)

        # Timer display
        self.timer_display = QLabel("00:00")
        font = QFont()
        font.setPointSize(s['font_xlarge'])
        font.setBold(True)
        self.timer_display.setFont(font)
        self.timer_display.setAlignment(Qt.AlignCenter)
        self.timer_display.setStyleSheet("color: #0d47a1;")
        layout.addWidget(self.timer_display)

        # Pause/Resume button
        pause_layout = QHBoxLayout()
        pause_layout.addStretch()
        self.pause_button = QPushButton("⏸ Pause")
        self.pause_button.setFixedWidth(int(s['control_height_medium'] * 2.8))
        self.pause_button.clicked.connect(self._on_pause_click)
        self.pause_button.setStyleSheet(f"""
            QPushButton {{
                background-color: #1976d2;
                color: white;
                padding: {s['padding_tiny']}px;
                border: none;
                border-radius: {s['radius_small']}px;
            }}
            QPushButton:hover {{
                background-color: #1565c0;
            }}
        """)
        pause_layout.addWidget(self.pause_button)
        pause_layout.addStretch()
        layout.addLayout(pause_layout)

        # Status text
        self.status_text = QLabel("Timer ready")
        self.status_text.setAlignment(Qt.AlignCenter)
        self.status_text.setStyleSheet(f"font-size: {s['font_tiny']}pt; color: #666; font-style: italic;")
        layout.addWidget(self.status_text)

        # Style the widget
        self.setStyleSheet(f"""
            TimerWidget {{
                background-color: #e3f2fd;
                border: 1px solid #90caf9;
                border-radius: {s['radius_medium']}px;
            }}
        """)
        self.setFixedWidth(int(s['control_height_large'] * 5))

    def _format_time(self, seconds: int) -> str:
        """Format seconds as MM:SS."""
        mins = seconds // 60
        secs = seconds % 60
        return f"{mins:02d}:{secs:02d}"

    def _get_current_elapsed(self) -> int:
        """Get current elapsed time including any running session."""
        if not self._is_running:
            return self._elapsed_seconds

        if self._is_paused:
            # Paused - return time up to pause
            return self._elapsed_seconds

        # Running - add current session time
        current_session = int(time.time() - self._current_session_start)
        return self._elapsed_seconds + current_session

    def _update_display(self):
        """Update timer display."""
        s = self.scale

        elapsed = self._get_current_elapsed()
        self.timer_display.setText(self._format_time(elapsed))

        if self._is_paused:
            self.status_text.setText("⏸ Paused")
            self.status_text.setStyleSheet(f"font-size: {s['font_tiny']}pt; color: #f57c00; font-style: italic;")
        elif self._is_running:
            self.status_text.setText("⏱ Recording...")
            self.status_text.setStyleSheet(f"font-size: {s['font_tiny']}pt; color: #2e7d32; font-style: italic;")
        else:
            self.status_text.setText("Timer stopped")
            self.status_text.setStyleSheet(f"font-size: {s['font_tiny']}pt; color: #666; font-style: italic;")

        # Emit signal
        self.timer_updated.emit(elapsed)

    def start(self, previous_seconds: int = 0):
        """
        Start or restart the timer.

        Args:
            previous_seconds: Previously accumulated time for this statement
        """
        self._elapsed_seconds = previous_seconds
        self._current_session_start = time.time()
        self._is_running = True
        self._is_paused = False
        self._pause_time = None

        # Start update timer (update every second)
        self._update_timer.start(1000)

        self._update_display()

    def pause(self):
        """Pause the timer."""
        if not self._is_running or self._is_paused:
            return

        # Save elapsed time up to now
        current_session = int(time.time() - self._current_session_start)
        self._elapsed_seconds += current_session

        self._is_paused = True
        self._pause_time = time.time()
        self._update_display()

    def resume(self):
        """Resume the timer from pause."""
        if not self._is_paused:
            return

        # Start a new session from now
        self._current_session_start = time.time()
        self._is_paused = False
        self._pause_time = None
        self._update_display()

    def stop(self) -> int:
        """
        Stop the timer and return total elapsed seconds.

        Returns:
            Total elapsed seconds
        """
        if self._is_running and not self._is_paused:
            # Save current session time
            current_session = int(time.time() - self._current_session_start)
            self._elapsed_seconds += current_session

        self._is_running = False
        self._is_paused = False
        self._current_session_start = None
        self._pause_time = None

        # Stop update timer
        self._update_timer.stop()

        self._update_display()
        return self._elapsed_seconds

    def reset(self):
        """Reset the timer to zero."""
        self._elapsed_seconds = 0
        self._current_session_start = None
        self._is_running = False
        self._is_paused = False
        self._pause_time = None

        # Stop update timer
        self._update_timer.stop()

        self._update_display()

    def get_elapsed_seconds(self) -> int:
        """Get current elapsed seconds."""
        return self._get_current_elapsed()

    def is_running(self) -> bool:
        """Check if timer is running (not paused)."""
        return self._is_running and not self._is_paused

    def is_paused(self) -> bool:
        """Check if timer is paused."""
        return self._is_paused

    def _on_pause_click(self):
        """Handle pause/resume button click."""
        if self._is_paused:
            self.resume()
            self.pause_button.setText("⏸ Pause")
        else:
            self.pause()
            self.pause_button.setText("▶ Resume")
