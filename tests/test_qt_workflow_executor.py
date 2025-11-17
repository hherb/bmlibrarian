"""
Tests for QtWorkflowExecutor

Tests Qt GUI workflow orchestration and error handling.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock, call
import sys
from pathlib import Path

# Ensure src is in path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, Signal, QObject
from PySide6.QtTest import QSignalSpy

# Import the class to test
from bmlibrarian.gui.qt.plugins.research.workflow_executor import QtWorkflowExecutor


class TestQtWorkflowExecutor(unittest.TestCase):
    """Test cases for QtWorkflowExecutor."""

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
        # Create executor with mocked dependencies
        self.executor = QtWorkflowExecutor()

    def tearDown(self):
        """Clean up after each test."""
        if hasattr(self, 'executor'):
            self.executor.cleanup()
            self.executor.deleteLater()
            self.executor = None

    # ========================================================================
    # Initialization and Lifecycle Tests
    # ========================================================================

    def test_executor_initialization(self):
        """Test that executor initializes correctly."""
        self.assertIsNotNone(self.executor)
        self.assertTrue(self.executor._is_active)
        self.assertEqual(self.executor.current_question, "")
        self.assertEqual(len(self.executor.documents), 0)
        self.assertEqual(len(self.executor.scored_documents), 0)
        self.assertEqual(len(self.executor.citations), 0)

    def test_cleanup_marks_inactive(self):
        """Test that cleanup marks executor as inactive."""
        self.assertTrue(self.executor._is_active)
        self.executor.cleanup()
        self.assertFalse(self.executor._is_active)

    def test_cleanup_clears_state(self):
        """Test that cleanup clears workflow state."""
        # Set some state
        self.executor.current_question = "Test question"
        self.executor.documents = [{"doc_id": 1}]
        self.executor.scored_documents = [("doc", {"score": 5})]
        self.executor.citations = [{"citation": "test"}]
        self.executor.preliminary_report = "Test report"

        # Cleanup
        self.executor.cleanup()

        # Verify state cleared
        self.assertEqual(self.executor.current_question, "")
        self.assertEqual(len(self.executor.documents), 0)
        self.assertEqual(len(self.executor.scored_documents), 0)
        self.assertEqual(len(self.executor.citations), 0)
        self.assertEqual(self.executor.preliminary_report, "")

    # ========================================================================
    # Error Handling Tests
    # ========================================================================

    def test_generate_query_with_inactive_executor(self):
        """Test that generate_query raises RuntimeError when executor is inactive."""
        # Setup: mark executor as inactive
        self.executor._is_active = False
        self.executor.current_question = "Test question"

        # Mock query agent
        self.executor.query_agent = Mock()

        # Test: should raise RuntimeError
        with self.assertRaises(RuntimeError) as context:
            self.executor.generate_query()

        # Verify error message
        self.assertIn("not active", str(context.exception))

    def test_generate_query_without_agent(self):
        """Test that generate_query raises RuntimeError when QueryAgent is not initialized."""
        # Setup: no query agent
        self.executor.query_agent = None
        self.executor.current_question = "Test question"

        # Test: should raise RuntimeError
        with self.assertRaises(RuntimeError) as context:
            self.executor.generate_query()

        # Verify error message
        self.assertIn("QueryAgent not initialized", str(context.exception))

    def test_generate_query_with_empty_question(self):
        """Test that generate_query raises ValueError with empty question."""
        # Setup: mock query agent but empty question
        self.executor.query_agent = Mock()
        self.executor.current_question = ""

        # Test: should raise ValueError
        with self.assertRaises(ValueError) as context:
            self.executor.generate_query()

        # Verify error message
        self.assertIn("empty research question", str(context.exception))

    def test_execute_workflow_returns_early_when_inactive(self):
        """Test that execute_workflow returns early when executor is inactive."""
        # Setup: mark executor as inactive
        self.executor._is_active = False
        self.executor.current_question = "Test question"

        # Mock query agent that should NOT be called
        self.executor.query_agent = Mock()

        # Test: execute workflow
        self.executor.execute_workflow()

        # Verify: query agent was never called
        self.executor.query_agent.convert_question.assert_not_called()

    # ========================================================================
    # Signal Emission Tests
    # ========================================================================

    def test_query_generated_signal_emission(self):
        """Test that query_generated signal is emitted."""
        # Setup signal spy
        spy = QSignalSpy(self.executor.query_generated)

        # Setup: mock query agent
        mock_query = "cardiovascular & exercise"
        self.executor.query_agent = Mock()
        self.executor.query_agent.convert_question.return_value = mock_query
        self.executor.current_question = "Test question"

        # Test: generate query
        result = self.executor.generate_query()

        # Verify: signal emitted with correct query
        self.assertEqual(len(spy), 1)
        self.assertEqual(spy[0][0], mock_query)
        self.assertEqual(result, mock_query)

    def test_status_message_signal_emission(self):
        """Test that status_message signal is emitted during workflow."""
        # Setup signal spy
        spy = QSignalSpy(self.executor.status_message)

        # Setup: mock agents
        self.executor.query_agent = Mock()
        self.executor.query_agent.convert_question.return_value = "test & query"
        self.executor.query_agent.search_documents.return_value = []
        self.executor.current_question = "Test question"

        # Test: execute workflow (will emit status messages)
        self.executor.execute_workflow()

        # Verify: at least one status message emitted
        self.assertGreater(len(spy), 0)

    def test_workflow_error_signal_emission(self):
        """Test that workflow_error signal is emitted on error."""
        # Setup signal spy
        spy = QSignalSpy(self.executor.workflow_error)

        # Setup: mock query agent that raises exception
        self.executor.query_agent = Mock()
        self.executor.query_agent.convert_question.side_effect = Exception("Test error")
        self.executor.current_question = "Test question"

        # Test: execute workflow
        self.executor.execute_workflow()

        # Verify: error signal emitted
        self.assertEqual(len(spy), 1)
        error = spy[0][0]
        self.assertIsInstance(error, Exception)
        self.assertEqual(str(error), "Test error")

    # ========================================================================
    # Agent Initialization Tests
    # ========================================================================

    def test_initialize_agents(self):
        """Test that initialize_agents sets up all required agents."""
        # Mock the agent constructors
        with patch('bmlibrarian.gui.qt.plugins.research.workflow_executor.QueryAgent') as MockQueryAgent, \
             patch('bmlibrarian.gui.qt.plugins.research.workflow_executor.DocumentScoringAgent') as MockScoringAgent, \
             patch('bmlibrarian.gui.qt.plugins.research.workflow_executor.CitationFinderAgent') as MockCitationAgent, \
             patch('bmlibrarian.gui.qt.plugins.research.workflow_executor.ReportingAgent') as MockReportingAgent:

            # Create mock instances
            MockQueryAgent.return_value = Mock()
            MockScoringAgent.return_value = Mock()
            MockCitationAgent.return_value = Mock()
            MockReportingAgent.return_value = Mock()

            # Test: initialize agents
            self.executor.initialize_agents()

            # Verify: all agents initialized
            self.assertIsNotNone(self.executor.query_agent)
            self.assertIsNotNone(self.executor.scoring_agent)
            self.assertIsNotNone(self.executor.citation_agent)
            self.assertIsNotNone(self.executor.reporting_agent)

    # ========================================================================
    # Query Validation Tests
    # ========================================================================

    def test_generate_query_validates_return_value(self):
        """Test that generate_query validates query agent return value."""
        # Setup: mock query agent returning None
        self.executor.query_agent = Mock()
        self.executor.query_agent.convert_question.return_value = None
        self.executor.current_question = "Test question"

        # Test: should raise ValueError
        with self.assertRaises(ValueError) as context:
            self.executor.generate_query()

        # Verify error message
        self.assertIn("returned None", str(context.exception))

    def test_generate_query_validates_empty_string(self):
        """Test that generate_query validates empty query string."""
        # Setup: mock query agent returning empty string
        self.executor.query_agent = Mock()
        self.executor.query_agent.convert_question.return_value = "   "
        self.executor.current_question = "Test question"

        # Test: should raise ValueError
        with self.assertRaises(ValueError) as context:
            self.executor.generate_query()

        # Verify error message
        self.assertIn("empty query string", str(context.exception))

    def test_generate_query_validates_type(self):
        """Test that generate_query validates query type."""
        # Setup: mock query agent returning invalid type
        self.executor.query_agent = Mock()
        self.executor.query_agent.convert_question.return_value = 123  # Invalid: int instead of str
        self.executor.current_question = "Test question"

        # Test: should raise TypeError
        with self.assertRaises(TypeError) as context:
            self.executor.generate_query()

        # Verify error message
        self.assertIn("invalid type", str(context.exception))


if __name__ == '__main__':
    unittest.main()
