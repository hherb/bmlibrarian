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
        # Create research tab widget (includes workflow executor)
        self.widget = ResearchTabWidget()
        self.executor = self.widget.workflow_executor

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
        # Setup: track status label updates
        initial_text = self.widget.status_label.text()

        # Test: emit status message from executor
        test_message = "Processing documents..."
        self.executor.status_message.emit(test_message)

        # Allow Qt to process events
        QApplication.processEvents()

        # Verify: status label updated
        self.assertNotEqual(self.widget.status_label.text(), initial_text)
        self.assertIn(test_message, self.widget.status_label.text())

    def test_query_generated_signal_updates_ui(self):
        """Test that query_generated signal updates UI query field."""
        # Setup: clear query input
        self.widget.query_input.clear()

        # Test: emit query_generated signal
        test_query = "cardiovascular & exercise"
        self.executor.query_generated.emit(test_query)

        # Allow Qt to process events
        QApplication.processEvents()

        # Verify: query input updated
        self.assertEqual(self.widget.query_input.text(), test_query)

    def test_workflow_completed_updates_tabs(self):
        """Test that workflow_completed signal updates tabs with results."""
        # Setup: mock results
        test_results = {
            'phase': 3,
            'milestone': 3,
            'status': 'preliminary_report_completed',
            'question': 'Test question',
            'query': 'test & query',
            'documents': [
                {'doc_id': 1, 'title': 'Paper 1', 'abstract': 'Abstract 1'}
            ],
            'scored_documents': [
                ({'doc_id': 1, 'title': 'Paper 1', 'abstract': 'Abstract 1'},
                 {'score': 5, 'reasoning': 'Highly relevant'})
            ],
            'citations': [
                {
                    'citation_id': 1,
                    'doc_id': 1,
                    'title': 'Paper 1',
                    'passage': 'Test passage',
                    'reasoning': 'Test reasoning'
                }
            ],
            'preliminary_report': '# Test Report\n\nTest content',
            'document_count': 1,
            'high_scoring_count': 1,
            'citation_count': 1,
            'report_length': 100
        }

        # Test: emit workflow_completed signal
        self.executor.workflow_completed.emit(test_results)

        # Allow Qt to process events
        QApplication.processEvents()

        # Verify: literature tab updated
        self.assertGreater(self.widget.literature_layout.count(), 0)

        # Verify: citations tab updated
        self.assertGreater(self.widget.citations_layout.count(), 0)

        # Verify: report tab updated (markdown viewer should have content)
        self.assertIsNotNone(self.widget.report_viewer.toPlainText())

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
        self.assertEqual(len(spy), 1)
        error = spy[0][0]
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
        self.assertEqual(len(spy), 1)
        error = spy[0][0]
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
        self.executor.query_agent.search_documents.return_value = [
            {'doc_id': 1, 'title': 'Paper 1', 'abstract': 'Abstract 1'}
        ]

        self.executor.scoring_agent = Mock()
        self.executor.scoring_agent.evaluate_document.return_value = {
            'score': 5,
            'reasoning': 'Highly relevant'
        }

        self.executor.citation_agent = Mock()
        self.executor.citation_agent.extract_citation.return_value = {
            'citation_id': 1,
            'doc_id': 1,
            'title': 'Paper 1',
            'passage': 'Test passage',
            'reasoning': 'Test reasoning'
        }

        self.executor.reporting_agent = Mock()
        self.executor.reporting_agent.generate_report.return_value = '# Test Report'

        self.executor.current_question = "Test question"

        # Test: execute complete workflow
        self.executor.execute_workflow()

        # Allow Qt to process all events
        QApplication.processEvents()

        # Verify: all major signals emitted
        self.assertGreater(len(status_spy), 0, "Status messages should be emitted")
        self.assertEqual(len(query_spy), 1, "Query should be generated once")
        self.assertEqual(len(docs_spy), 1, "Documents should be found once")
        self.assertEqual(len(scored_spy), 1, "Documents should be scored once")
        self.assertEqual(len(citations_spy), 1, "Citations should be extracted once")
        self.assertEqual(len(report_spy), 1, "Report should be generated once")
        self.assertEqual(len(completed_spy), 1, "Workflow should complete once")


if __name__ == '__main__':
    unittest.main()
