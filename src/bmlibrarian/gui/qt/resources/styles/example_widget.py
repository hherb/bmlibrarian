"""
Example widget demonstrating DPI-aware font-relative styling system.

This example shows how to properly use the centralized styling system
to create widgets that automatically adapt to different screen DPIs and
user font preferences.

Run this file directly to see a demo window:
    python -m bmlibrarian.gui.qt.resources.styles.example_widget
"""

from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QTextEdit, QGroupBox
)
from PySide6.QtCore import Qt
import sys

from .dpi_scale import get_font_scale
from .stylesheet_generator import StylesheetGenerator, apply_button_style


class ExampleWidget(QWidget):
    """Example widget using DPI-aware styling."""

    def __init__(self):
        super().__init__()
        # Get scale dictionary once in __init__ for efficiency
        self.scale = get_font_scale()
        self.stylesheet_gen = StylesheetGenerator()
        self._setup_ui()

    def _setup_ui(self):
        """Setup UI with DPI-aware dimensions."""
        s = self.scale  # Shorthand for cleaner code

        # Main layout with scaled margins
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(
            s['spacing_large'],
            s['spacing_large'],
            s['spacing_large'],
            s['spacing_large']
        )
        main_layout.setSpacing(s['spacing_medium'])

        # Window title
        self.setWindowTitle("DPI-Aware Styling Example")
        self.setMinimumWidth(max(400, int(s['char_width'] * 60)))

        # Header section
        header = self._create_header_section()
        main_layout.addWidget(header)

        # Button examples
        buttons = self._create_button_section()
        main_layout.addWidget(buttons)

        # Input examples
        inputs = self._create_input_section()
        main_layout.addWidget(inputs)

        # Info section showing scale values
        info = self._create_info_section()
        main_layout.addWidget(info)

    def _create_header_section(self) -> QWidget:
        """Create header section demonstrating header styling."""
        s = self.scale

        group = QGroupBox("Header Styles")
        layout = QVBoxLayout(group)

        # Large header
        large_header = QLabel("Large Header (font_large)")
        large_header.setStyleSheet(f"""
            QLabel {{
                font-size: {s['font_large']}pt;
                font-weight: bold;
                padding: {s['padding_small']}px;
                background-color: #E0E0E0;
                border-radius: {s['radius_small']}px;
            }}
        """)
        layout.addWidget(large_header)

        # Medium header
        medium_header = QLabel("Medium Header (font_medium)")
        medium_header.setStyleSheet(f"""
            QLabel {{
                font-size: {s['font_medium']}pt;
                font-weight: bold;
                padding: {s['padding_tiny']}px;
            }}
        """)
        layout.addWidget(medium_header)

        # Normal text
        normal_text = QLabel("Normal text (font_normal) - System default size")
        normal_text.setStyleSheet(f"""
            QLabel {{
                font-size: {s['font_normal']}pt;
            }}
        """)
        layout.addWidget(normal_text)

        # Small text
        small_text = QLabel("Small text (font_small) - For secondary information")
        small_text.setStyleSheet(f"""
            QLabel {{
                font-size: {s['font_small']}pt;
                color: #666;
            }}
        """)
        layout.addWidget(small_text)

        return group

    def _create_button_section(self) -> QWidget:
        """Create button section demonstrating button styling."""
        s = self.scale

        group = QGroupBox("Button Styles")
        layout = QHBoxLayout(group)
        layout.setSpacing(s['spacing_medium'])

        # Primary button using StylesheetGenerator
        primary_btn = QPushButton("Primary (Generator)")
        primary_btn.setFixedHeight(s['control_height_medium'])
        primary_btn.setStyleSheet(self.stylesheet_gen.button_stylesheet())
        layout.addWidget(primary_btn)

        # Success button using convenience function
        success_btn = QPushButton("Success (Convenience)")
        success_btn.setFixedHeight(s['control_height_medium'])
        apply_button_style(success_btn, bg_color="#4CAF50", hover_color="#45A049")
        layout.addWidget(success_btn)

        # Custom button with manual f-string
        custom_btn = QPushButton("Custom (Manual)")
        custom_btn.setFixedHeight(s['control_height_large'])
        custom_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #FF5722;
                color: white;
                border-radius: {s['radius_medium']}px;
                font-size: {s['font_medium']}pt;
                padding: {s['padding_medium']}px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #E64A19;
            }}
        """)
        layout.addWidget(custom_btn)

        return group

    def _create_input_section(self) -> QWidget:
        """Create input section demonstrating input styling."""
        s = self.scale

        group = QGroupBox("Input Styles")
        layout = QVBoxLayout(group)
        layout.setSpacing(s['spacing_small'])

        # Text input with StylesheetGenerator
        input1 = QTextEdit()
        input1.setPlaceholderText("Input with StylesheetGenerator")
        input1.setFixedHeight(s['control_height_large'])
        input1.setStyleSheet(self.stylesheet_gen.input_stylesheet())
        layout.addWidget(input1)

        # Custom styled input
        input2 = QTextEdit()
        input2.setPlaceholderText("Custom styled input with border focus")
        input2.setFixedHeight(s['control_height_large'])
        input2.setStyleSheet(f"""
            QTextEdit {{
                border: 2px solid #CCC;
                border-radius: {s['radius_medium']}px;
                padding: {s['padding_small']}px;
                font-size: {s['font_medium']}pt;
                background-color: #FAFAFA;
            }}
            QTextEdit:focus {{
                border: 2px solid #2196F3;
                background-color: white;
            }}
        """)
        layout.addWidget(input2)

        return group

    def _create_info_section(self) -> QWidget:
        """Create info section showing current scale values."""
        s = self.scale

        group = QGroupBox("Current DPI Scale Values")
        layout = QVBoxLayout(group)

        info_text = f"""
<b>Base Measurements:</b><br>
• Base font size: {s['base_font_size']}pt<br>
• Line height: {s['base_line_height']}px<br>
• Char width: {s['char_width']}px<br>
<br>
<b>Font Sizes (points):</b><br>
• Small: {s['font_small']}pt | Medium: {s['font_medium']}pt | Large: {s['font_large']}pt<br>
<br>
<b>Spacing (pixels):</b><br>
• Small: {s['spacing_small']}px | Medium: {s['spacing_medium']}px | Large: {s['spacing_large']}px<br>
<br>
<b>Control Heights (pixels):</b><br>
• Small: {s['control_height_small']}px | Medium: {s['control_height_medium']}px | Large: {s['control_height_large']}px
        """

        info_label = QLabel(info_text)
        info_label.setTextFormat(Qt.RichText)
        info_label.setStyleSheet(f"""
            QLabel {{
                font-size: {s['font_small']}pt;
                padding: {s['padding_medium']}px;
                background-color: #F5F5F5;
                border-radius: {s['radius_small']}px;
            }}
        """)
        layout.addWidget(info_label)

        return group


def main():
    """Run example widget demo."""
    app = QApplication(sys.argv)

    window = ExampleWidget()
    window.show()

    sys.exit(app.exec())


if __name__ == '__main__':
    main()
