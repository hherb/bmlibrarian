"""
Navigation Widget for Fact-Checker Review.

Provides navigation controls and auto-save indicator.
"""

from typing import Optional
from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QPushButton,
    QLabel,
)
from PySide6.QtCore import Qt, Signal

# Import DPI-aware styling
from ...resources.styles import get_font_scale


class NavigationWidget(QWidget):
    """Widget for navigation controls."""

    # Signals
    previous_clicked = Signal()
    next_clicked = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        """
        Initialize navigation widget.

        Args:
            parent: Optional parent widget
        """
        super().__init__(parent)

        # DPI-aware scaling
        self.scale = get_font_scale()

        self._setup_ui()

    def _setup_ui(self):
        """Setup the user interface."""
        s = self.scale

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(s['spacing_medium'])

        # Previous button
        self.prev_button = QPushButton("← Previous")
        self.prev_button.setFixedWidth(int(s['control_height_medium'] * 3.3))
        self.prev_button.clicked.connect(self.previous_clicked.emit)
        self.prev_button.setStyleSheet(f"""
            QPushButton {{
                background-color: #757575;
                color: white;
                padding: {s['padding_small']}px {s['padding_large']}px;
                border: none;
                border-radius: {s['radius_small']}px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #616161;
            }}
            QPushButton:disabled {{
                background-color: #e0e0e0;
                color: #9e9e9e;
            }}
        """)
        layout.addWidget(self.prev_button)

        # Next button
        self.next_button = QPushButton("Next →")
        self.next_button.setFixedWidth(int(s['control_height_medium'] * 3.3))
        self.next_button.clicked.connect(self.next_clicked.emit)
        self.next_button.setStyleSheet(f"""
            QPushButton {{
                background-color: #1976d2;
                color: white;
                padding: {s['padding_small']}px {s['padding_large']}px;
                border: none;
                border-radius: {s['radius_small']}px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #1565c0;
            }}
            QPushButton:disabled {{
                background-color: #e0e0e0;
                color: #9e9e9e;
            }}
        """)
        layout.addWidget(self.next_button)

        # Stretch
        layout.addStretch()

        # Auto-save indicator
        auto_save_label = QLabel("✓ Annotations saved automatically to database")
        auto_save_label.setStyleSheet(f"color: #2e7d32; font-size: {s['font_small']}pt; font-style: italic;")
        layout.addWidget(auto_save_label)

    def set_button_states(self, can_go_previous: bool, can_go_next: bool):
        """
        Set enabled state of navigation buttons.

        Args:
            can_go_previous: Whether previous button should be enabled
            can_go_next: Whether next button should be enabled
        """
        self.prev_button.setEnabled(can_go_previous)
        self.next_button.setEnabled(can_go_next)
