"""
Tests for QtWorkflowExecutor

Tests Qt GUI workflow orchestration and error handling.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock, call
import sys
from pathlib import Path

import pytest

# Ensure src is in path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Try to import Qt - skip tests if Qt libraries not available
try:
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import Qt, Signal, QObject
    PYSIDE6_AVAILABLE = True
except ImportError:
    PYSIDE6_AVAILABLE = False
    QApplication = None
    Signal = None

# Skip all tests in this module if PySide6 is not available
pytestmark = pytest.mark.skipif(
    not PYSIDE6_AVAILABLE,
    reason="PySide6 not available or Qt libraries missing"
)

# Import the class to test (only if PySide6 available)
if PYSIDE6_AVAILABLE:
    from bmlibrarian.gui.qt.plugins.research.workflow_executor import QtWorkflowExecutor
else:
    QtWorkflowExecutor = None


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

    # ========================================================================
    # Query and Methodology Tests
    # ========================================================================

    def test_generate_query_returns_and_stores_query(self):
        """generate_query returns the agent's query and keeps it for the methodology."""
        mock_query = "cardiovascular & exercise"
        self.executor.query_agent = Mock()
        self.executor.query_agent.convert_question.return_value = mock_query
        self.executor.current_question = "Test question"

        result = self.executor.generate_query()

        self.assertEqual(result, mock_query)
        self.assertEqual(self.executor.generated_query, mock_query)

    def test_methodology_metadata_counts_scored_documents(self):
        """The report's methodology reflects the scored documents and threshold."""
        self.executor.current_question = "Test question"
        self.executor.documents = [{'id': 1}, {'id': 2}, {'id': 3}]
        self.executor.scored_documents = [
            ({'id': 1}, {'score': 5}),
            ({'id': 2}, {'score': 3}),
            ({'id': 3}, {'score': 1}),
        ]
        self.executor.scoring_threshold = 3.0

        metadata = self.executor._generate_methodology_metadata()

        self.assertEqual(metadata.total_documents_found, 3)
        self.assertEqual(metadata.documents_by_score, {5: 1, 3: 1, 1: 1})
        self.assertEqual(metadata.documents_above_threshold, 2)
        self.assertEqual(metadata.documents_processed_for_citations, 2)

    # ========================================================================
    # Agent Initialization Tests
    # ========================================================================

    def test_agents_injected_via_constructor(self):
        """Test that agents passed to the constructor are wired up.

        The executor no longer creates its own agents (initialize_agents()
        was removed); the research tab injects an agents dict.
        """
        agents = {
            name: Mock() for name in (
                'query_agent', 'scoring_agent', 'citation_agent',
                'reporting_agent', 'counterfactual_agent', 'editor_agent',
            )
        }
        executor = QtWorkflowExecutor(agents=agents)
        try:
            self.assertIs(executor.query_agent, agents['query_agent'])
            self.assertIs(executor.scoring_agent, agents['scoring_agent'])
            self.assertIs(executor.citation_agent, agents['citation_agent'])
            self.assertIs(executor.reporting_agent, agents['reporting_agent'])
            self.assertIs(executor.editor_agent, agents['editor_agent'])
        finally:
            executor.cleanup()
            executor.deleteLater()

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
