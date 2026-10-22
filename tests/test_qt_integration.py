"""
Integration Tests for Qt GUI Workflow

Tests signal flow and integration between QtWorkflowExecutor and ResearchTabWidget.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import sys
from pathlib import Path

# Ensure src is in path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtTest import QSignalSpy

# Import the classes to test
from bmlibrarian.gui.qt.plugins.research.research_tab import ResearchTabWidget
from bmlibrarian.gui.qt.plugins.research.workflow_executor import QtWorkflowExecutor
from bmlibrarian.gui.qt.plugins.research.workflow_thread import WorkflowThread

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
        # Modal dialogs would block the test run
        for module in ('research_tab', 'workflow_handlers'):
            patcher = patch(
                f'bmlibrarian.gui.qt.plugins.research.{module}.QMessageBox'
            )
            patcher.start()
            self.addCleanup(patcher.stop)

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

    def test_workflow_executor_status_updates_ui(self):
        """Test that workflow executor status messages update UI."""
        # Setup: track progress label updates
        initial_text = self.widget.progress_label.text()

        # Test: emit status message from executor
        test_message = "Processing documents..."
        self.executor.status_message.emit(test_message)

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

    def test_workflow_error_signal_displays_error(self):
        """Test that workflow_error signal displays error in UI."""
        # Setup: track status label
        initial_text = self.widget.status_label.text()

        # Test: emit workflow error
        test_error = Exception("Test error message")
        self.executor.workflow_error.emit(test_error)

        # Allow Qt to process events
        QApplication.processEvents()

        # Verify: error displayed in status
        self.assertNotEqual(self.widget.status_label.text(), initial_text)
        # Status should contain error indication
        status_text = self.widget.status_label.text().lower()
        self.assertTrue('error' in status_text or 'failed' in status_text)

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

    def test_executor_cleanup_prevents_workflow_execution(self):
        """Test that executor cleanup prevents further workflow execution."""
        # Setup: cleanup executor
        self.executor.cleanup()

        # Setup: mock query agent (should not be called)
        self.executor.query_agent = Mock()

        # Test: attempt to execute workflow
        self.executor.execute_workflow()

        # Verify: workflow did not execute (query agent not called)
        self.executor.query_agent.convert_question.assert_not_called()

    # ========================================================================
    # Agent Error Scenario Tests
    # ========================================================================

    def test_agent_error_emits_workflow_error(self):
        """Test that agent errors emit workflow_error signal."""
        # Setup: signal spy
        spy = QSignalSpy(self.executor.workflow_error)

        # Setup: mock query agent that raises error
        self.executor.query_agent = Mock()
        self.executor.query_agent.convert_question.side_effect = Exception("Agent failed")
        self.executor.current_question = "Test question"

        # Test: execute workflow
        self.executor.execute_workflow()

        # Verify: workflow_error signal emitted
        self.assertEqual(spy.count(), 1)
        error = spy.at(0)[0]
        self.assertIsInstance(error, Exception)
        self.assertEqual(str(error), "Agent failed")

    def test_query_validation_error_emits_workflow_error(self):
        """Test that query validation errors emit workflow_error signal."""
        # Setup: signal spy
        spy = QSignalSpy(self.executor.workflow_error)

        # Setup: mock query agent returning None
        self.executor.query_agent = Mock()
        self.executor.query_agent.convert_question.return_value = None
        self.executor.current_question = "Test question"

        # Test: execute workflow
        self.executor.execute_workflow()

        # Verify: workflow_error signal emitted
        self.assertEqual(spy.count(), 1)
        error = spy.at(0)[0]
        self.assertIsInstance(error, ValueError)

    # ========================================================================
    # Multi-Agent Workflow Tests
    # ========================================================================

    def test_complete_workflow_signal_sequence(self):
        """Test that complete workflow emits signals in correct sequence."""
        # Setup: signal spies
        status_spy = QSignalSpy(self.executor.status_message)
        query_spy = QSignalSpy(self.executor.query_generated)
        docs_spy = QSignalSpy(self.executor.documents_found)
        scored_spy = QSignalSpy(self.executor.documents_scored)
        citations_spy = QSignalSpy(self.executor.citations_extracted)
        report_spy = QSignalSpy(self.executor.preliminary_report_generated)
        completed_spy = QSignalSpy(self.executor.workflow_completed)

        # Setup: mock all agents
        self.executor.query_agent = Mock()
        self.executor.query_agent.convert_question.return_value = "test & query"
        self.executor.query_agent.find_abstracts.return_value = [
            {'doc_id': 1, 'title': 'Paper 1', 'abstract': 'Abstract 1'}
        ]

        self.executor.scoring_agent = Mock()
        self.executor.scoring_agent.evaluate_document.return_value = {
            'score': 5,
            'reasoning': 'Highly relevant'
        }

        self.executor.citation_agent = Mock()
        self.executor.citation_agent.process_scored_documents_for_citations.return_value = [{
            'citation_id': 1,
            'doc_id': 1,
            'title': 'Paper 1',
            'passage': 'Test passage',
            'reasoning': 'Test reasoning'
        }]

        self.executor.reporting_agent = Mock()
        self.executor.reporting_agent.generate_citation_based_report.return_value = '# Test Report'

        self.executor.current_question = "Test question"

        # Test: execute complete workflow
        self.executor.execute_workflow()

        # Allow Qt to process all events
        QApplication.processEvents()

        # Verify: all major signals emitted
        self.assertGreater(status_spy.count(), 0, "Status messages should be emitted")
        self.assertEqual(query_spy.count(), 1, "Query should be generated once")
        self.assertEqual(docs_spy.count(), 1, "Documents should be found once")
        self.assertEqual(scored_spy.count(), 1, "Documents should be scored once")
        self.assertEqual(citations_spy.count(), 1, "Citations should be extracted once")
        self.assertEqual(report_spy.count(), 1, "Report should be generated once")
        self.assertEqual(completed_spy.count(), 1, "Workflow should complete once")


if __name__ == '__main__':
    unittest.main()
