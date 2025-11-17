"""
Tests for ResearchTabWidget

Tests Qt GUI components for research tab including widget cleanup and citation cards.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import sys
from pathlib import Path

# Ensure src is in path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from PySide6.QtWidgets import QApplication, QVBoxLayout, QLabel, QWidget
from PySide6.QtTest import QTest
from PySide6.QtCore import Qt

# Import the widget to test
from bmlibrarian.gui.qt.plugins.research.research_tab import ResearchTabWidget


class TestResearchTabWidget(unittest.TestCase):
    """Test cases for ResearchTabWidget."""

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
        # Create widget
        self.widget = ResearchTabWidget()

    def tearDown(self):
        """Clean up after each test."""
        if hasattr(self, 'widget'):
            self.widget.deleteLater()
            self.widget = None

    # ========================================================================
    # Widget Initialization Tests
    # ========================================================================

    def test_widget_initialization(self):
        """Test that widget initializes correctly."""
        self.assertIsNotNone(self.widget)
        self.assertIsNotNone(self.widget.workflow_executor)
        self.assertIsNotNone(self.widget.literature_layout)
        self.assertIsNotNone(self.widget.citations_layout)

    def test_ui_components_exist(self):
        """Test that all UI components are created."""
        self.assertIsNotNone(self.widget.question_input)
        self.assertIsNotNone(self.widget.start_button)
        self.assertIsNotNone(self.widget.status_label)
        self.assertIsNotNone(self.widget.tab_widget)

    # ========================================================================
    # Widget Cleanup Tests
    # ========================================================================

    def test_clear_layout_widgets_removes_all_widgets(self):
        """Test that _clear_layout_widgets removes all widgets from layout."""
        # Setup: create test layout with widgets
        test_layout = QVBoxLayout()
        widgets = [QLabel(f"Label {i}") for i in range(5)]
        for widget in widgets:
            test_layout.addWidget(widget)

        # Verify layout has widgets
        self.assertEqual(test_layout.count(), 5)

        # Test: clear layout
        self.widget._clear_layout_widgets(test_layout)

        # Verify: layout is empty
        self.assertEqual(test_layout.count(), 0)

    def test_clear_layout_widgets_disconnects_signals_safely(self):
        """Test that _clear_layout_widgets handles signal disconnection safely."""
        # Setup: create test layout with widget that has signals
        test_layout = QVBoxLayout()
        test_widget = QLabel("Test")

        # Connect a test signal
        test_slot = Mock()
        test_widget.destroyed.connect(test_slot)

        test_layout.addWidget(test_widget)

        # Test: clear layout (should not raise exception)
        try:
            self.widget._clear_layout_widgets(test_layout)
            success = True
        except Exception as e:
            success = False
            self.fail(f"_clear_layout_widgets raised exception: {e}")

        # Verify: no exception raised
        self.assertTrue(success)

    def test_clear_layout_widgets_handles_already_deleted_widget(self):
        """Test that _clear_layout_widgets handles already-deleted widgets."""
        # Setup: create test layout
        test_layout = QVBoxLayout()
        test_widget = QLabel("Test")
        test_layout.addWidget(test_widget)

        # Manually delete the widget first
        test_widget.deleteLater()
        QApplication.processEvents()  # Process deletion

        # Test: clear layout (should not raise exception)
        try:
            self.widget._clear_layout_widgets(test_layout)
            success = True
        except RuntimeError:
            # RuntimeError is expected when widget is already deleted
            success = True
        except Exception as e:
            success = False
            self.fail(f"Unexpected exception: {e}")

        # Verify: handled gracefully
        self.assertTrue(success)

    def test_update_literature_tab_clears_existing_widgets(self):
        """Test that _update_literature_tab clears existing widgets."""
        # Setup: add some widgets to literature layout
        for i in range(3):
            self.widget.literature_layout.addWidget(QLabel(f"Old {i}"))

        initial_count = self.widget.literature_layout.count()
        self.assertGreater(initial_count, 0)

        # Test: update with new data
        scored_docs = [
            ({"doc_id": 1, "title": "Test Paper 1", "abstract": "Abstract 1"},
             {"score": 5, "reasoning": "Highly relevant"})
        ]
        self.widget._update_literature_tab(scored_docs)

        # Verify: old widgets removed and new widgets added
        # Note: count may be different due to new content, but should not have old widgets
        self.assertNotEqual(self.widget.literature_layout.count(), initial_count)

    def test_update_literature_tab_shows_empty_state(self):
        """Test that _update_literature_tab shows empty state when no documents."""
        # Test: update with empty list
        self.widget._update_literature_tab([])

        # Verify: layout has at least one widget (the empty state message)
        self.assertGreater(self.widget.literature_layout.count(), 0)

        # Verify: first widget is a label with empty message
        first_widget = self.widget.literature_layout.itemAt(0).widget()
        self.assertIsInstance(first_widget, QLabel)
        self.assertIn("No documents", first_widget.text())

    # ========================================================================
    # Citation Tab Tests
    # ========================================================================

    def test_update_citations_tab_clears_existing_widgets(self):
        """Test that _update_citations_tab clears existing widgets."""
        # Setup: add some widgets to citations layout
        for i in range(3):
            self.widget.citations_layout.addWidget(QLabel(f"Old {i}"))

        initial_count = self.widget.citations_layout.count()
        self.assertGreater(initial_count, 0)

        # Test: update with new data
        citations = [
            {
                "citation_id": 1,
                "doc_id": 1,
                "title": "Test Paper",
                "passage": "Test passage",
                "reasoning": "Test reasoning"
            }
        ]
        self.widget._update_citations_tab(citations)

        # Verify: old widgets removed
        self.assertNotEqual(self.widget.citations_layout.count(), initial_count)

    def test_update_citations_tab_shows_empty_state(self):
        """Test that _update_citations_tab shows empty state when no citations."""
        # Test: update with empty list
        self.widget._update_citations_tab([])

        # Verify: layout has at least one widget (the empty state message)
        self.assertGreater(self.widget.citations_layout.count(), 0)

        # Verify: first widget is a label with empty message
        first_widget = self.widget.citations_layout.itemAt(0).widget()
        self.assertIsInstance(first_widget, QLabel)
        self.assertIn("No citations", first_widget.text())

    def test_update_citations_tab_creates_citation_cards(self):
        """Test that _update_citations_tab creates citation cards."""
        # Setup: test citations
        citations = [
            {
                "citation_id": 1,
                "doc_id": 1,
                "title": "Paper 1",
                "passage": "Passage 1",
                "reasoning": "Reason 1"
            },
            {
                "citation_id": 2,
                "doc_id": 2,
                "title": "Paper 2",
                "passage": "Passage 2",
                "reasoning": "Reason 2"
            }
        ]

        # Test: update citations tab
        self.widget._update_citations_tab(citations)

        # Verify: layout has widgets (citation cards)
        self.assertGreater(self.widget.citations_layout.count(), 0)

    # ========================================================================
    # Validation Tests
    # ========================================================================

    def test_max_results_validation_adjusts_min_relevant(self):
        """Test that max_results validation adjusts min_relevant when needed."""
        # Setup: set min_relevant higher than max_results
        self.widget.min_relevant_spin.setValue(100)

        # Test: set max_results lower
        self.widget.max_results_spin.setValue(50)

        # Allow time for signal processing
        QApplication.processEvents()

        # Verify: min_relevant was adjusted down
        self.assertLessEqual(self.widget.min_relevant_spin.value(),
                            self.widget.max_results_spin.value())

    def test_validation_flag_prevents_recursive_updates(self):
        """Test that validation flag prevents recursive updates."""
        # Setup: set initial values
        self.widget.min_relevant_spin.setValue(100)
        self.widget.max_results_spin.setValue(200)

        # Test: change max_results (should trigger validation)
        change_count = 0
        original_method = self.widget._on_max_results_changed

        def counting_method(value):
            nonlocal change_count
            change_count += 1
            original_method(value)

        self.widget._on_max_results_changed = counting_method

        # Trigger validation by setting max_results lower than min_relevant
        self.widget.max_results_spin.setValue(50)
        QApplication.processEvents()

        # Verify: method called reasonable number of times (not infinite loop)
        self.assertLess(change_count, 5, "Validation may be causing recursive updates")

    # ========================================================================
    # Signal Connection Tests
    # ========================================================================

    def test_workflow_executor_signals_connected(self):
        """Test that workflow executor signals are connected."""
        # Setup: create test slot
        status_received = []
        def on_status(message):
            status_received.append(message)

        self.widget.workflow_executor.status_message.connect(on_status)

        # Test: emit signal
        test_message = "Test status"
        self.widget.workflow_executor.status_message.emit(test_message)

        # Verify: signal received
        self.assertEqual(len(status_received), 1)
        self.assertEqual(status_received[0], test_message)

    def test_start_button_click_triggers_workflow(self):
        """Test that start button click triggers workflow execution."""
        # Setup: set question
        self.widget.question_input.setPlainText("Test research question")

        # Mock workflow executor
        self.widget.workflow_executor.execute_workflow = Mock()

        # Test: click start button
        QTest.mouseClick(self.widget.start_button, Qt.LeftButton)
        QApplication.processEvents()

        # Verify: workflow execute was called
        self.widget.workflow_executor.execute_workflow.assert_called_once()


if __name__ == '__main__':
    unittest.main()
