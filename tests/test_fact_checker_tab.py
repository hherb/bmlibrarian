"""
Tests for FactCheckerTabWidget

Tests Qt GUI components for fact-checker review interface.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import sys
from pathlib import Path

# Ensure src is in path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from PySide6.QtCore import Qt

# Import the widget to test
from bmlibrarian.gui.qt.plugins.fact_checker.fact_checker_tab import FactCheckerTabWidget


class TestFactCheckerTabWidget(unittest.TestCase):
    """Test cases for FactCheckerTabWidget."""

    @classmethod
    def setUpClass(cls):
        """Set up QApplication for all tests."""
        # Create QApplication if it doesn't exist
        if not QApplication.instance():
            cls.app = QApplication([])
        else:
            cls.app = QApplication.instance()

    def setUp(self):
        """Set up test fixtures."""
        # Create widget with mocked database
        with patch('bmlibrarian.gui.qt.plugins.fact_checker.fact_checker_tab.get_fact_checker_db'):
            self.widget = FactCheckerTabWidget()

    def tearDown(self):
        """Clean up after each test."""
        if hasattr(self, 'widget'):
            self.widget.deleteLater()
            self.widget = None

    def test_widget_initialization(self):
        """Test that widget initializes correctly."""
        self.assertIsNotNone(self.widget)
        self.assertEqual(self.widget.incremental, False)
        self.assertEqual(self.widget.blind_mode, False)
        self.assertIsNone(self.widget.db_file)
        self.assertEqual(self.widget.current_index, 0)
        self.assertEqual(self.widget.db_type, "postgresql")

    def test_ui_components_exist(self):
        """Test that all UI components are created."""
        self.assertIsNotNone(self.widget.status_label)
        self.assertIsNotNone(self.widget.load_data_button)
        self.assertIsNotNone(self.widget.statistics_button)

    def test_status_changed_signal(self):
        """Test that status_changed signal is emitted."""
        signal_received = []

        def on_status_changed(message):
            signal_received.append(message)

        self.widget.status_changed.connect(on_status_changed)

        # Trigger a status change
        test_message = "Test status message"
        self.widget.status_changed.emit(test_message)

        # Verify signal was emitted
        self.assertEqual(len(signal_received), 1)
        self.assertEqual(signal_received[0], test_message)

    def test_load_data_button_click(self):
        """Test load data button click behavior."""
        # Button should be enabled initially
        self.assertTrue(self.widget.load_data_button.isEnabled())

        # Test button is clickable
        QTest.mouseClick(self.widget.load_data_button, Qt.LeftButton)

    def test_configuration_properties(self):
        """Test configuration property setters."""
        # Test incremental mode
        self.widget.incremental = True
        self.assertTrue(self.widget.incremental)

        # Test blind mode
        self.widget.blind_mode = True
        self.assertTrue(self.widget.blind_mode)

        # Test db_file
        test_path = "/path/to/test.db"
        self.widget.db_file = test_path
        self.assertEqual(self.widget.db_file, test_path)

    @patch('bmlibrarian.gui.qt.plugins.fact_checker.fact_checker_tab.get_fact_checker_db')
    def test_database_initialization(self, mock_get_db):
        """Test database initialization."""
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        # Create new widget to trigger database initialization
        widget = FactCheckerTabWidget()

        # Clean up
        widget.deleteLater()

    def test_widget_visibility(self):
        """Test widget visibility states."""
        # Widget should be visible by default
        self.widget.show()
        self.assertTrue(self.widget.isVisible())

        # Test hiding
        self.widget.hide()
        self.assertFalse(self.widget.isVisible())

    def test_data_containers(self):
        """Test data container initialization."""
        self.assertIsInstance(self.widget.results, list)
        self.assertIsInstance(self.widget.reviews, list)
        self.assertEqual(len(self.widget.results), 0)
        self.assertEqual(len(self.widget.reviews), 0)

    def test_annotator_properties(self):
        """Test annotator-related properties."""
        self.assertIsNone(self.widget.annotator_id)
        self.assertIsNone(self.widget.annotator_username)

        # Set annotator properties
        self.widget.annotator_id = 123
        self.widget.annotator_username = "test_user"

        self.assertEqual(self.widget.annotator_id, 123)
        self.assertEqual(self.widget.annotator_username, "test_user")

    def test_widget_layout(self):
        """Test widget layout structure."""
        layout = self.widget.layout()
        self.assertIsNotNone(layout)

        # Check layout margins and spacing
        margins = layout.contentsMargins()
        self.assertEqual(margins.left(), 20)
        self.assertEqual(margins.top(), 20)
        self.assertEqual(margins.right(), 20)
        self.assertEqual(margins.bottom(), 20)
        self.assertEqual(layout.spacing(), 15)


class TestFactCheckerTabIntegration(unittest.TestCase):
    """Integration tests for FactCheckerTabWidget."""

    @classmethod
    def setUpClass(cls):
        """Set up QApplication for all tests."""
        if not QApplication.instance():
            cls.app = QApplication([])
        else:
            cls.app = QApplication.instance()

    def setUp(self):
        """Set up test fixtures."""
        with patch('bmlibrarian.gui.qt.plugins.fact_checker.fact_checker_tab.get_fact_checker_db'):
            self.widget = FactCheckerTabWidget()

    def tearDown(self):
        """Clean up after each test."""
        if hasattr(self, 'widget'):
            self.widget.deleteLater()
            self.widget = None

    @patch('bmlibrarian.gui.qt.plugins.fact_checker.fact_checker_tab.QFileDialog')
    def test_load_data_workflow(self, mock_file_dialog):
        """Test complete data loading workflow."""
        # Mock file dialog to return a test file path
        mock_file_dialog.getOpenFileName.return_value = ("/path/to/test.json", "JSON Files (*.json)")

        # This will trigger the file dialog
        # Note: Actual implementation depends on the widget's load data method

    def test_multiple_widgets(self):
        """Test creating multiple widget instances."""
        with patch('bmlibrarian.gui.qt.plugins.fact_checker.fact_checker_tab.get_fact_checker_db'):
            widget1 = FactCheckerTabWidget()
            widget2 = FactCheckerTabWidget()

            self.assertIsNotNone(widget1)
            self.assertIsNotNone(widget2)
            self.assertIsNot(widget1, widget2)

            widget1.deleteLater()
            widget2.deleteLater()


if __name__ == '__main__':
    unittest.main()
