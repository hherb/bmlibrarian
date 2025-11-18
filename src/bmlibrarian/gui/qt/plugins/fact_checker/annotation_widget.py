"""
Annotation Widget for Fact-Checker Review.

Handles user input for annotations and explanations.
"""

from typing import Optional, Callable
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QComboBox,
    QTextEdit,
)
from PySide6.QtCore import Qt, Signal

# Import DPI-aware styling
from ...resources.styles import get_font_scale


class AnnotationWidget(QWidget):
    """Widget for annotation input."""

    # Signals
    annotation_changed = Signal(str, str, str)  # annotation, explanation, confidence

    def __init__(self, parent: Optional[QWidget] = None):
        """
        Initialize annotation widget.

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

        layout = QVBoxLayout(self)
        layout.setContentsMargins(s['spacing_xlarge'], s['spacing_xlarge'], s['spacing_xlarge'], s['spacing_xlarge'])
        layout.setSpacing(s['spacing_medium'])

        # Title
        title = QLabel("Human Review")
        title.setStyleSheet(f"font-weight: bold; color: #2e7d32; font-size: {s['font_small']}pt;")
        layout.addWidget(title)

        # Annotation dropdown
        annotation_label = QLabel("Your Annotation:")
        layout.addWidget(annotation_label)

        self.annotation_dropdown = QComboBox()
        self.annotation_dropdown.addItem("N/A (Not Yet Annotated)", "n/a")
        self.annotation_dropdown.addItem("Yes", "yes")
        self.annotation_dropdown.addItem("No", "no")
        self.annotation_dropdown.addItem("Maybe", "maybe")
        self.annotation_dropdown.addItem("Unclear", "unclear")
        self.annotation_dropdown.setCurrentIndex(0)
        self.annotation_dropdown.currentIndexChanged.connect(self._on_annotation_change)
        layout.addWidget(self.annotation_dropdown)

        # Confidence dropdown
        confidence_label = QLabel("Confidence Level:")
        layout.addWidget(confidence_label)

        self.confidence_dropdown = QComboBox()
        self.confidence_dropdown.addItem("Not Selected", "n/a")
        self.confidence_dropdown.addItem("High", "high")
        self.confidence_dropdown.addItem("Medium", "medium")
        self.confidence_dropdown.addItem("Low", "low")
        self.confidence_dropdown.setCurrentIndex(0)
        self.confidence_dropdown.currentIndexChanged.connect(self._on_confidence_change)
        layout.addWidget(self.confidence_dropdown)

        # Explanation field
        explanation_label = QLabel("Explanation (optional):")
        layout.addWidget(explanation_label)

        self.explanation_field = QTextEdit()
        self.explanation_field.setPlaceholderText("Provide your reasoning...")
        self.explanation_field.setMinimumHeight(int(s['control_height_medium'] * 2.2))
        self.explanation_field.setMaximumHeight(int(s['control_height_medium'] * 3.3))
        self.explanation_field.textChanged.connect(self._on_explanation_change)
        layout.addWidget(self.explanation_field)

        # Style the widget
        self.setStyleSheet(f"""
            AnnotationWidget {{
                background-color: #e8f5e9;
                border: 2px solid #66bb6a;
                border-radius: {s['radius_medium']}px;
            }}
            QComboBox, QTextEdit {{
                background-color: white;
                border: 1px solid #ccc;
                padding: {s['padding_tiny']}px;
                border-radius: {s['radius_small']}px;
            }}
        """)

    def _on_annotation_change(self):
        """Handle annotation dropdown change."""
        annotation = self.annotation_dropdown.currentData()
        explanation = self.explanation_field.toPlainText()
        confidence = self.confidence_dropdown.currentData()
        self.annotation_changed.emit(annotation, explanation, confidence)

    def _on_confidence_change(self):
        """Handle confidence dropdown change."""
        annotation = self.annotation_dropdown.currentData()
        explanation = self.explanation_field.toPlainText()
        confidence = self.confidence_dropdown.currentData()
        self.annotation_changed.emit(annotation, explanation, confidence)

    def _on_explanation_change(self):
        """Handle explanation text change."""
        annotation = self.annotation_dropdown.currentData()
        explanation = self.explanation_field.toPlainText()
        confidence = self.confidence_dropdown.currentData()
        self.annotation_changed.emit(annotation, explanation, confidence)

    def set_annotation(self, annotation: str, explanation: str = "", confidence: str = ""):
        """
        Set annotation values programmatically.

        Args:
            annotation: Annotation value (yes/no/maybe/unclear or empty for N/A)
            explanation: Explanation text
            confidence: Confidence level (high/medium/low or empty for N/A)
        """
        # Block signals while updating to avoid triggering change events
        self.annotation_dropdown.blockSignals(True)
        self.confidence_dropdown.blockSignals(True)
        self.explanation_field.blockSignals(True)

        # Set annotation
        if not annotation or annotation == "":
            annotation = "n/a"
        idx = self.annotation_dropdown.findData(annotation.lower())
        if idx >= 0:
            self.annotation_dropdown.setCurrentIndex(idx)

        # Set explanation
        self.explanation_field.setPlainText(explanation if explanation else "")

        # Set confidence
        if not confidence or confidence == "":
            confidence = "n/a"
        idx = self.confidence_dropdown.findData(confidence.lower())
        if idx >= 0:
            self.confidence_dropdown.setCurrentIndex(idx)

        # Re-enable signals
        self.annotation_dropdown.blockSignals(False)
        self.confidence_dropdown.blockSignals(False)
        self.explanation_field.blockSignals(False)

    def get_annotation(self) -> str:
        """Get current annotation value, converting 'n/a' to empty string."""
        value = self.annotation_dropdown.currentData()
        return "" if value == "n/a" else value

    def get_explanation(self) -> str:
        """Get current explanation text."""
        return self.explanation_field.toPlainText()

    def get_confidence(self) -> str:
        """Get current confidence level, converting 'n/a' to empty string."""
        value = self.confidence_dropdown.currentData()
        return "" if value == "n/a" else value

    def clear(self):
        """Clear annotation inputs."""
        self.set_annotation("", "", "")
