"""
Integration Tests for Qt GUI Workflow

Tests signal flow between WorkflowThread, QtWorkflowExecutor and ResearchTabWidget.
"""

import unittest
import pytest
from unittest.mock import Mock, patch, MagicMock
import sys
from pathlib import Path

# Ensure src is in path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

# Import the classes to test
from bmlibrarian.gui.qt.plugins.research.research_tab import ResearchTabWidget
from bmlibrarian.gui.qt.plugins.research.workflow_thread import WorkflowThread

# The settings/configuration tabs list Ollama models when built.
pytestmark = pytest.mark.usefixtures("offline_model_list")

# Agents the research tab needs for its workflow executor (mocked: no Ollama/DB)
AGENT_NAMES = (
    'query_agent', 'scoring_agent', 'citation_agent',
    'reporting_agent', 'counterfactual_agent', 'editor_agent',
)


class TestQtIntegration(unittest.TestCase):
    """Integration test cases for Qt GUI workflow."""

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
        # A modal dialog would block the test run; toasts are recorded
        patcher = patch('bmlibrarian.gui.qt.plugins.research.research_tab.QMessageBox')
        patcher.start()
        self.addCleanup(patcher.stop)
        toast_patcher = patch(
            'bmlibrarian.gui.qt.plugins.research.workflow_handlers.show_toast'
        )
        self.show_toast = toast_patcher.start()
        self.addCleanup(toast_patcher.stop)

        # Create research tab widget (creates the workflow executor from agents)
        agents = {name: Mock() for name in AGENT_NAMES}
        self.widget = ResearchTabWidget(agents=agents)
        self.executor = self.widget.workflow_executor

    def _attach_workflow_thread(self) -> WorkflowThread:
        """Wire a (not started) WorkflowThread to the tab as a real run would."""
        thread = WorkflowThread(executor=self.executor, question="Test question")
        self.widget.workflow_thread = thread
        self.widget._connect_workflow_thread_signals()
        self.addCleanup(thread.deleteLater)
        return thread

    def tearDown(self):
        """Clean up after each test."""
        if hasattr(self, 'widget'):
            self.widget.deleteLater()
            self.widget = None
        if hasattr(self, 'executor'):
            self.executor = None

    # ========================================================================
    # Signal Flow Tests
    # ========================================================================

    def test_workflow_status_updates_ui(self):
        """Test that the thread's status messages update the UI."""
        thread = self._attach_workflow_thread()
        initial_text = self.widget.progress_label.text()

        # Test: emit status message from the thread
        test_message = "Processing documents..."
        thread.status_message.emit(test_message)

        # Allow Qt to process events
        QApplication.processEvents()

        # Verify: progress label shows the status message
        self.assertNotEqual(self.widget.progress_label.text(), initial_text)
        self.assertIn(test_message, self.widget.progress_label.text())

    def test_query_generated_signal_updates_ui(self):
        """Test that the thread's query_generated signal fills the Search tab."""
        # Step results reach the tab from WorkflowThread, not the executor
        thread = self._attach_workflow_thread()
        query_display = self.widget.search_refs.widgets['query_text_display']
        query_display.clear()

        # Test: emit query_generated signal
        test_query = "cardiovascular & exercise"
        thread.query_generated.emit(test_query)

        # Allow Qt to process events
        QApplication.processEvents()

        # Verify: query display updated
        self.assertEqual(query_display.toPlainText(), test_query)

    def test_workflow_signals_update_tabs(self):
        """Test that thread step and completion signals update the tabs."""
        thread = self._attach_workflow_thread()
        doc = {'id': 1, 'title': 'Paper 1', 'abstract': 'Abstract 1'}
        citation = {
            'document_id': 1,
            'document_title': 'Paper 1',
            'passage': 'Test passage',
            'summary': 'Test summary',
            'relevance_score': 0.9,
        }
        report = '# Test Report\n\nTest content'
        results = {
            'status': 'completed',
            'question': 'Test question',
            'document_count': 1,
            'citation_count': 1,
        }

        # Test: emit the signals a successful run emits
        thread.documents_found.emit([doc])
        thread.citation_extracted.emit(citation, 1, 1)
        thread.preliminary_report_generated.emit(report)
        thread.workflow_completed.emit(results)
        QApplication.processEvents()

        # Verify: literature tab has the document card (plus stretch)
        literature_layout = self.widget.literature_refs.widgets['layout']
        self.assertGreater(literature_layout.count(), 1)

        # Verify: citations tab no longer shows its empty state
        citations_layout = self.widget.citations_refs.widgets['layout']
        empty_label = self.widget.citations_refs.widgets['empty_label']
        widgets = [citations_layout.itemAt(i).widget() for i in range(citations_layout.count())]
        self.assertNotIn(empty_label, widgets)

        # Verify: completion updates status and stores results
        self.assertEqual(self.widget.status_label.text(), "Completed")
        self.assertEqual(self.widget.current_results, results)

    def test_workflow_error_shows_error_toast(self):
        """A failed run sets the error status and shows an error toast, not a modal (#332)."""
        from bmlibrarian.gui.qt.widgets.toast import ToastLevel

        thread = self._attach_workflow_thread()

        # Test: emit workflow error
        thread.workflow_error.emit(Exception("Test error message"))
        QApplication.processEvents()

        # Verify: error displayed in status and in a toast
        self.assertEqual(self.widget.status_label.text(), "Error")
        self.assertTrue(self.widget.start_button.isEnabled())
        self.show_toast.assert_called_once()
        _, message, level = self.show_toast.call_args.args
        self.assertIn("Test error message", message)
        self.assertEqual(level, ToastLevel.ERROR)

    def test_workflow_error_names_an_exception_with_no_message(self):
        """An exception with an empty message still says what failed."""
        thread = self._attach_workflow_thread()

        thread.workflow_error.emit(TimeoutError())
        QApplication.processEvents()

        _, message, _ = self.show_toast.call_args.args
        self.assertEqual(message, "Research workflow failed: TimeoutError")

    def test_workflow_warning_shows_warning_toast(self):
        """A step that failed without stopping the run is shown as a warning."""
        from bmlibrarian.gui.qt.widgets.toast import ToastLevel

        thread = self._attach_workflow_thread()
        thread.workflow_warning.emit("Counterfactual analysis failed")
        QApplication.processEvents()

        self.show_toast.assert_called_once()
        _, message, level = self.show_toast.call_args.args
        self.assertEqual(message, "Counterfactual analysis failed")
        self.assertEqual(level, ToastLevel.WARNING)

    def test_early_end_explains_why_there_is_no_report(self):
        """no_documents / no_scores / no_citations runs say why they stopped."""
        from bmlibrarian.gui.qt.plugins.research.workflow_handlers import EARLY_END_MESSAGES
        from bmlibrarian.gui.qt.widgets.toast import ToastLevel

        thread = self._attach_workflow_thread()
        for status, expected in EARLY_END_MESSAGES.items():
            self.show_toast.reset_mock()
            thread.workflow_completed.emit({'status': status, 'document_count': 0})
            QApplication.processEvents()

            self.show_toast.assert_called_once()
            _, message, level = self.show_toast.call_args.args
            self.assertEqual(message, expected)
            self.assertEqual(level, ToastLevel.WARNING)
            self.assertEqual(self.widget.status_label.text(), "Completed - no report")

    def test_full_completion_shows_no_toast(self):
        """A normal completion needs no notification beyond the status line."""
        thread = self._attach_workflow_thread()
        thread.workflow_completed.emit({'status': 'completed', 'document_count': 3})
        QApplication.processEvents()

        self.show_toast.assert_not_called()
        self.assertEqual(self.widget.status_label.text(), "Completed")

    # ========================================================================
    # Lifecycle Integration Tests
    # ========================================================================

    def test_widget_cleanup_cleans_executor(self):
        """Test that widget cleanup also cleans up executor."""
        # Setup: verify executor is active
        self.assertTrue(self.executor._is_active)

        # Test: cleanup widget
        self.widget.cleanup()

        # Verify: executor marked inactive
        self.assertFalse(self.executor._is_active)

    def test_executor_cleanup_prevents_query_generation(self):
        """Test that executor cleanup prevents further query generation."""
        self.executor.cleanup()
        self.executor.query_agent = Mock()
        self.executor.current_question = "Test question"

        with self.assertRaises(RuntimeError):
            self.executor.generate_query()

        self.executor.query_agent.convert_question.assert_not_called()


if __name__ == '__main__':
    unittest.main()
