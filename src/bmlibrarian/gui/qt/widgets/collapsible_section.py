"""
Collapsible section widget for BMLibrarian Qt GUI.

Provides an expandable/collapsible section with header and content area.
"""

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QSizePolicy,
)
from PySide6.QtCore import Qt, Signal, QPropertyAnimation, QEasingCurve
from typing import Optional

from ..resources.styles import get_font_scale


class CollapsibleSection(QWidget):
    """
    Collapsible section widget with header and expandable content.

    Useful for workflow steps, settings sections, etc.
    """

    # Signals
    expanded = Signal()  # Emitted when section is expanded
    collapsed = Signal()  # Emitted when section is collapsed
    toggled = Signal(bool)  # Emitted when toggle state changes (expanded=True)

    def __init__(
        self,
        title: str = "",
        parent: Optional[QWidget] = None,
        expanded: bool = True,
    ):
        """
        Initialize collapsible section.

        Args:
            title: Section title
            parent: Optional parent widget
            expanded: Initial expanded state
        """
        super().__init__(parent)

        self.scale = get_font_scale()  # Get DPI-aware scale
        self._expanded = expanded
        self._animation_duration = 200  # milliseconds

        # Create main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Create header widget
        s = self.scale  # Shorthand
        self.header_frame = QFrame()
        self.header_frame.setFrameShape(QFrame.StyledPanel)
        self.header_frame.setStyleSheet(
            f"""
            QFrame {{
                background-color: #e8e8e8;
                border: 1px solid #c0c0c0;
                border-radius: {s['radius_tiny']}px;
            }}
            QFrame:hover {{
                background-color: #d8d8d8;
            }}
        """
        )

        header_layout = QHBoxLayout(self.header_frame)
        header_layout.setContentsMargins(
            s['padding_medium'],
            s['padding_tiny'],
            s['padding_medium'],
            s['padding_tiny']
        )

        # Toggle button
        self.toggle_button = QPushButton("▼" if expanded else "▶")
        self.toggle_button.setFlat(True)
        self.toggle_button.setFixedSize(s['icon_small'], s['icon_small'])
        self.toggle_button.clicked.connect(self.toggle)
        self.toggle_button.setStyleSheet(
            f"""
            QPushButton {{
                border: none;
                background: transparent;
                font-size: {s['font_medium']}pt;
            }}
        """
        )

        # Title label
        self.title_label = QLabel(title)
        self.title_label.setStyleSheet(
            f"""
            QLabel {{
                font-weight: bold;
                font-size: {s['font_normal']}pt;
            }}
        """
        )

        header_layout.addWidget(self.toggle_button)
        header_layout.addWidget(self.title_label)
        header_layout.addStretch()

        main_layout.addWidget(self.header_frame)

        # Make header clickable
        self.header_frame.mousePressEvent = lambda e: self.toggle()

        # Create content widget
        self.content_frame = QFrame()
        self.content_frame.setFrameShape(QFrame.StyledPanel)
        self.content_frame.setStyleSheet(
            f"""
            QFrame {{
                background-color: white;
                border: 1px solid #c0c0c0;
                border-top: none;
                border-radius: 0 0 {s['radius_tiny']}px {s['radius_tiny']}px;
            }}
        """
        )

        self.content_layout = QVBoxLayout(self.content_frame)
        self.content_layout.setContentsMargins(
            s['spacing_large'],
            s['spacing_large'],
            s['spacing_large'],
            s['spacing_large']
        )

        main_layout.addWidget(self.content_frame)

        # Set initial state
        self.content_frame.setVisible(expanded)

    def set_title(self, title: str):
        """
        Set section title.

        Args:
            title: New title text
        """
        self.title_label.setText(title)

    def get_title(self) -> str:
        """
        Get section title.

        Returns:
            Current title text
        """
        return self.title_label.text()

    def set_content_widget(self, widget: QWidget):
        """
        Set the content widget.

        Args:
            widget: Widget to display in content area
        """
        # Clear existing widgets
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Add new widget
        self.content_layout.addWidget(widget)

    def add_content_widget(self, widget: QWidget):
        """
        Add a widget to the content area.

        Args:
            widget: Widget to add
        """
        self.content_layout.addWidget(widget)

    def toggle(self):
        """Toggle expanded/collapsed state."""
        self._expanded = not self._expanded
        self.content_frame.setVisible(self._expanded)
        self.toggle_button.setText("▼" if self._expanded else "▶")

        # Emit signals
        self.toggled.emit(self._expanded)
        if self._expanded:
            self.expanded.emit()
        else:
            self.collapsed.emit()

    def expand(self):
        """Expand the section."""
        if not self._expanded:
            self.toggle()

    def collapse(self):
        """Collapse the section."""
        if self._expanded:
            self.toggle()

    def is_expanded(self) -> bool:
        """
        Check if section is expanded.

        Returns:
            True if expanded, False otherwise
        """
        return self._expanded

    def set_header_color(self, color: str):
        """
        Set header background color.

        Args:
            color: CSS color string (e.g., "#3498db" or "blue")
        """
        s = self.scale
        self.header_frame.setStyleSheet(
            f"""
            QFrame {{
                background-color: {color};
                border: 1px solid #c0c0c0;
                border-radius: {s['radius_tiny']}px;
            }}
        """
        )
