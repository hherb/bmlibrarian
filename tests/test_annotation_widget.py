"""
Tests for AnnotationWidget

Tests annotation input widget for fact-checker review interface.
"""

import unittest
from unittest.mock import Mock, patch
import sys
from pathlib import Path

# Ensure src is in path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from PySide6.QtCore import Qt

# Import the widget to test
from bmlibrarian.gui.qt.plugins.fact_checker.annotation_widget import AnnotationWidget


class TestAnnotationWidget(unittest.TestCase):
    """Test cases for AnnotationWidget."""

    @classmethod
    def setUpClass(cls):
        """Set up QApplication for all tests."""
        if not QApplication.instance():
            cls.app = QApplication([])
        else:
            cls.app = QApplication.instance()

    def setUp(self):
        """Set up test fixtures."""
        self.widget = AnnotationWidget()

    def tearDown(self):
        """Clean up after each test."""
        if hasattr(self, 'widget'):
            self.widget.deleteLater()
            self.widget = None

    def test_widget_initialization(self):
        """Test that widget initializes correctly."""
        self.assertIsNotNone(self.widget)
        self.assertIsNotNone(self.widget.annotation_dropdown)
        self.assertIsNotNone(self.widget.confidence_dropdown)
        self.assertIsNotNone(self.widget.explanation_field)

    def test_annotation_dropdown_items(self):
        """Test annotation dropdown has correct items."""
        dropdown = self.widget.annotation_dropdown

        # Should have 5 items: N/A, Yes, No, Maybe, Unclear
        self.assertEqual(dropdown.count(), 5)

        # Verify item data
        self.assertEqual(dropdown.itemData(0), "n/a")
        self.assertEqual(dropdown.itemData(1), "yes")
        self.assertEqual(dropdown.itemData(2), "no")
        self.assertEqual(dropdown.itemData(3), "maybe")
        self.assertEqual(dropdown.itemData(4), "unclear")

        # Default should be N/A
        self.assertEqual(dropdown.currentIndex(), 0)
        self.assertEqual(dropdown.currentData(), "n/a")

    def test_confidence_dropdown_items(self):
        """Test confidence dropdown has correct items."""
        dropdown = self.widget.confidence_dropdown

        # Should have 4 items: Not Selected, High, Medium, Low
        self.assertEqual(dropdown.count(), 4)

        # Verify item data
        self.assertEqual(dropdown.itemData(0), "n/a")
        self.assertEqual(dropdown.itemData(1), "high")
        self.assertEqual(dropdown.itemData(2), "medium")
        self.assertEqual(dropdown.itemData(3), "low")

        # Default should be Not Selected
        self.assertEqual(dropdown.currentIndex(), 0)
        self.assertEqual(dropdown.currentData(), "n/a")

    def test_annotation_changed_signal(self):
        """Test that annotation_changed signal is emitted."""
        signal_received = []

        def on_annotation_changed(annotation, explanation, confidence):
            signal_received.append((annotation, explanation, confidence))

        self.widget.annotation_changed.connect(on_annotation_changed)

        # Change annotation
        self.widget.annotation_dropdown.setCurrentIndex(1)  # Set to "Yes"

        # Signal should have been emitted
        self.assertGreater(len(signal_received), 0)

    def test_set_annotation_value(self):
        """Test setting annotation programmatically."""
        # Set to "Yes"
        self.widget.annotation_dropdown.setCurrentIndex(1)
        self.assertEqual(self.widget.annotation_dropdown.currentData(), "yes")

        # Set to "No"
        self.widget.annotation_dropdown.setCurrentIndex(2)
        self.assertEqual(self.widget.annotation_dropdown.currentData(), "no")

        # Set to "Maybe"
        self.widget.annotation_dropdown.setCurrentIndex(3)
        self.assertEqual(self.widget.annotation_dropdown.currentData(), "maybe")

    def test_set_confidence_value(self):
        """Test setting confidence programmatically."""
        # Set to "High"
        self.widget.confidence_dropdown.setCurrentIndex(1)
        self.assertEqual(self.widget.confidence_dropdown.currentData(), "high")

        # Set to "Medium"
        self.widget.confidence_dropdown.setCurrentIndex(2)
        self.assertEqual(self.widget.confidence_dropdown.currentData(), "medium")

        # Set to "Low"
        self.widget.confidence_dropdown.setCurrentIndex(3)
        self.assertEqual(self.widget.confidence_dropdown.currentData(), "low")

    def test_explanation_field_text(self):
        """Test explanation field text input."""
        test_text = "This is my explanation for the annotation."

        self.widget.explanation_field.setPlainText(test_text)
        self.assertEqual(self.widget.explanation_field.toPlainText(), test_text)

    def test_explanation_field_placeholder(self):
        """Test explanation field has placeholder text."""
        placeholder = self.widget.explanation_field.placeholderText()
        self.assertIsNotNone(placeholder)
        self.assertTrue(len(placeholder) > 0)

    def test_clear_annotation(self):
        """Test resetting annotation to default state."""
        # Set some values
        self.widget.annotation_dropdown.setCurrentIndex(1)
        self.widget.confidence_dropdown.setCurrentIndex(1)
        self.widget.explanation_field.setPlainText("Test explanation")

        # Reset to defaults
        self.widget.annotation_dropdown.setCurrentIndex(0)
        self.widget.confidence_dropdown.setCurrentIndex(0)
        self.widget.explanation_field.clear()

        # Verify reset
        self.assertEqual(self.widget.annotation_dropdown.currentData(), "n/a")
        self.assertEqual(self.widget.confidence_dropdown.currentData(), "n/a")
        self.assertEqual(self.widget.explanation_field.toPlainText(), "")

    def test_widget_styling(self):
        """Test that widget has styling applied."""
        style_sheet = self.widget.styleSheet()
        self.assertIsNotNone(style_sheet)
        self.assertTrue(len(style_sheet) > 0)

    def test_widget_layout(self):
        """Test widget layout structure."""
        layout = self.widget.layout()
        self.assertIsNotNone(layout)

        # Check layout margins
        margins = layout.contentsMargins()
        self.assertEqual(margins.left(), 15)
        self.assertEqual(margins.top(), 15)
        self.assertEqual(margins.right(), 15)
        self.assertEqual(margins.bottom(), 15)

        # Check spacing
        self.assertEqual(layout.spacing(), 10)

    def test_explanation_field_height_constraints(self):
        """Test explanation field height constraints."""
        min_height = self.widget.explanation_field.minimumHeight()
        max_height = self.widget.explanation_field.maximumHeight()

        self.assertEqual(min_height, 80)
        self.assertEqual(max_height, 120)


class TestAnnotationWidgetInteraction(unittest.TestCase):
    """Test user interaction with AnnotationWidget."""

    @classmethod
    def setUpClass(cls):
        """Set up QApplication for all tests."""
        if not QApplication.instance():
            cls.app = QApplication([])
        else:
            cls.app = QApplication.instance()

    def setUp(self):
        """Set up test fixtures."""
        self.widget = AnnotationWidget()
        self.widget.show()

    def tearDown(self):
        """Clean up after each test."""
        if hasattr(self, 'widget'):
            self.widget.deleteLater()
            self.widget = None

    def test_annotation_dropdown_click(self):
        """Test clicking annotation dropdown."""
        dropdown = self.widget.annotation_dropdown

        # Click to open dropdown
        QTest.mouseClick(dropdown, Qt.LeftButton)

        # Should still be functional
        self.assertTrue(dropdown.isEnabled())

    def test_confidence_dropdown_click(self):
        """Test clicking confidence dropdown."""
        dropdown = self.widget.confidence_dropdown

        # Click to open dropdown
        QTest.mouseClick(dropdown, Qt.LeftButton)

        # Should still be functional
        self.assertTrue(dropdown.isEnabled())

    def test_explanation_field_typing(self):
        """Test typing in explanation field."""
        field = self.widget.explanation_field

        # Set focus
        field.setFocus()
        self.assertTrue(field.hasFocus())

        # Type some text
        test_text = "Test explanation text"
        field.setPlainText(test_text)

        self.assertEqual(field.toPlainText(), test_text)

    def test_complete_annotation_workflow(self):
        """Test complete annotation workflow."""
        signals_received = []

        def on_annotation_changed(annotation, explanation, confidence):
            signals_received.append({
                'annotation': annotation,
                'explanation': explanation,
                'confidence': confidence
            })

        self.widget.annotation_changed.connect(on_annotation_changed)

        # Complete workflow: select annotation, confidence, and add explanation
        self.widget.annotation_dropdown.setCurrentIndex(1)  # Yes
        self.widget.confidence_dropdown.setCurrentIndex(1)  # High
        self.widget.explanation_field.setPlainText("Strong evidence supports this.")

        # Verify final state
        self.assertEqual(self.widget.annotation_dropdown.currentData(), "yes")
        self.assertEqual(self.widget.confidence_dropdown.currentData(), "high")
        self.assertEqual(self.widget.explanation_field.toPlainText(), "Strong evidence supports this.")

    def test_signal_emission_on_change(self):
        """Test that signals are emitted on each change."""
        signal_count = []

        def on_annotation_changed(annotation, explanation, confidence):
            signal_count.append(1)

        self.widget.annotation_changed.connect(on_annotation_changed)

        # Make multiple changes
        initial_count = len(signal_count)
        self.widget.annotation_dropdown.setCurrentIndex(1)

        # Signal should have been emitted
        self.assertGreater(len(signal_count), initial_count)

    def test_multiple_widgets_independent(self):
        """Test that multiple widgets are independent."""
        widget2 = AnnotationWidget()

        # Set different values
        self.widget.annotation_dropdown.setCurrentIndex(1)  # Yes
        widget2.annotation_dropdown.setCurrentIndex(2)  # No

        # Verify independence
        self.assertEqual(self.widget.annotation_dropdown.currentData(), "yes")
        self.assertEqual(widget2.annotation_dropdown.currentData(), "no")

        widget2.deleteLater()


if __name__ == '__main__':
    unittest.main()
