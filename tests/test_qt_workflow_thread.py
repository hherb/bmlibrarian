"""
Tests for WorkflowThread

Tests background workflow execution, signal connectivity, and error handling.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import sys
from pathlib import Path
from typing import Dict, Any

import pytest

# Ensure src is in path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Try to import Qt - skip tests if Qt libraries not available
try:
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import Qt, Signal, QObject
    from PySide6.QtTest import QSignalSpy
    PYSIDE6_AVAILABLE = True
except ImportError:
    PYSIDE6_AVAILABLE = False
    QApplication = None
    Signal = None
    QSignalSpy = None

# Skip all tests in this module if PySide6 is not available
pytestmark = pytest.mark.skipif(
    not PYSIDE6_AVAILABLE,
    reason="PySide6 not available or Qt libraries missing"
)

# Import the classes to test (only if PySide6 available)
if PYSIDE6_AVAILABLE:
    from bmlibrarian.gui.qt.plugins.research.workflow_thread import WorkflowThread
    from bmlibrarian.gui.qt.plugins.research.workflow_executor import QtWorkflowExecutor
else:
    WorkflowThread = None
    QtWorkflowExecutor = None


class TestWorkflowThread(unittest.TestCase):
    """Test cases for WorkflowThread."""

    @classmethod
    def setUpClass(cls) -> None:
        """Set up QApplication for all tests."""
        # Create QApplication if it doesn't exist
        if not QApplication.instance():
            cls.app = QApplication([])
        else:
            cls.app = QApplication.instance()

    def setUp(self) -> None:
        """Set up test fixtures."""
        # Create mock executor
        self.mock_executor = Mock(spec=QtWorkflowExecutor)
        self.mock_executor._is_active = True
        self.mock_executor.current_question = ""
        self.mock_executor.max_results = 100

        # Setup mock agents on executor
        self.mock_executor.query_agent = Mock()
        self.mock_executor.scoring_agent = Mock()
        self.mock_executor.citation_agent = Mock()
        self.mock_executor.citation_agent.get_validation_stats.return_value = {
            'failed_citations': [], 'errors': 0
        }
        self.mock_executor.citation_agent.extraction_summary.return_value = "Extracted citations"
        self.mock_executor.reporting_agent = Mock()
        self.mock_executor.counterfactual_agent = Mock()
        self.mock_executor.editor_agent = Mock()

    def tearDown(self) -> None:
        """Clean up after each test."""
        pass

    # ========================================================================
    # Initialization Tests
    # ========================================================================

    def test_thread_initialization(self) -> None:
        """Test that WorkflowThread initializes correctly."""
        thread = WorkflowThread(
            executor=self.mock_executor,
            question="Test question",
            max_results=50,
            score_threshold=3.5,
            enable_counterfactual=True
        )

        self.assertEqual(thread.question, "Test question")
        self.assertEqual(thread.max_results, 50)
        self.assertEqual(thread.score_threshold, 3.5)
        self.assertTrue(thread.enable_counterfactual)
        self.assertFalse(thread._should_cancel)

        thread.deleteLater()

    def test_thread_default_parameters(self) -> None:
        """Test that WorkflowThread uses correct default parameters."""
        thread = WorkflowThread(
            executor=self.mock_executor,
            question="Test question"
        )

        self.assertEqual(thread.max_results, 100)
        self.assertEqual(thread.score_threshold, 3.0)
        self.assertFalse(thread.enable_counterfactual)

        thread.deleteLater()

    # ========================================================================
    # Cancellation Tests
    # ========================================================================

    def test_cancel_sets_flag(self) -> None:
        """Test that cancel() sets the cancellation flag."""
        thread = WorkflowThread(
            executor=self.mock_executor,
            question="Test question"
        )

        self.assertFalse(thread._should_cancel)
        thread.cancel()
        self.assertTrue(thread._should_cancel)

        thread.deleteLater()

    def test_check_cancellation_returns_true_when_cancelled(self) -> None:
        """Test that _check_cancellation returns True when cancelled."""
        thread = WorkflowThread(
            executor=self.mock_executor,
            question="Test question"
        )

        # Setup signal spy for workflow_cancelled
        spy = QSignalSpy(thread.workflow_cancelled)

        # Cancel and check
        thread._should_cancel = True
        result = thread._check_cancellation("test_step")

        self.assertTrue(result)
        self.assertEqual(spy.count(), 1)

        thread.deleteLater()

    def test_check_cancellation_returns_false_when_not_cancelled(self) -> None:
        """Test that _check_cancellation returns False when not cancelled."""
        thread = WorkflowThread(
            executor=self.mock_executor,
            question="Test question"
        )

        result = thread._check_cancellation("test_step")
        self.assertFalse(result)

        thread.deleteLater()

    # ========================================================================
    # Signal Emission Tests
    # ========================================================================

    def test_step_started_signal_emission(self) -> None:
        """Test that step_started signal is emitted correctly."""
        # Setup mock executor
        self.mock_executor.generate_query.return_value = "test & query"
        self.mock_executor.search_documents.return_value = []

        thread = WorkflowThread(
            executor=self.mock_executor,
            question="Test question"
        )

        # Setup signal spy
        spy = QSignalSpy(thread.step_started)

        # Run thread synchronously for testing
        thread.run()

        # Verify at least one step_started signal emitted
        self.assertGreater(spy.count(), 0)

        # First step should be "generate_query"
        first_step = spy.at(0)
        self.assertEqual(first_step[0], "generate_query")

        thread.deleteLater()

    def test_workflow_error_signal_on_exception(self) -> None:
        """Test that workflow_error signal is emitted when exception occurs."""
        # Setup mock executor to raise exception
        self.mock_executor.generate_query.side_effect = Exception("Test error")

        thread = WorkflowThread(
            executor=self.mock_executor,
            question="Test question"
        )

        # Setup signal spy
        spy = QSignalSpy(thread.workflow_error)

        # Run thread synchronously
        thread.run()

        # Verify error signal emitted
        self.assertEqual(spy.count(), 1)
        error = spy.at(0)[0]
        self.assertIsInstance(error, Exception)
        self.assertEqual(str(error), "Test error")

        thread.deleteLater()

    def test_workflow_completed_signal_on_success(self) -> None:
        """Test that workflow_completed signal is emitted on success."""
        # Setup mock executor for successful workflow
        self.mock_executor.generate_query.return_value = "test & query"
        self.mock_executor.search_documents.return_value = [
            {"doc_id": 1, "title": "Test Doc", "abstract": "Test abstract"}
        ]
        self.mock_executor.scoring_agent.evaluate_document.return_value = {
            "score": 4.0,
            "reasoning": "Relevant"
        }
        # The thread extracts citations per document via the citation agent
        self.mock_executor.citation_agent.extract_citation_from_document.return_value = Mock(
            passage="Test citation", document_id=1
        )
        self.mock_executor.generate_preliminary_report.return_value = "# Test Report"

        thread = WorkflowThread(
            executor=self.mock_executor,
            question="Test question",
            enable_counterfactual=False  # Disable for simpler test
        )

        # Setup signal spy
        spy = QSignalSpy(thread.workflow_completed)

        # Run thread synchronously
        thread.run()

        # Verify completion signal emitted
        self.assertEqual(spy.count(), 1)
        results = spy.at(0)[0]
        self.assertEqual(results['question'], "Test question")
        self.assertIn('documents', results)
        self.assertIn('citations', results)

        thread.deleteLater()

    def test_run_hands_scores_to_executor_for_methodology(self) -> None:
        """The report's methodology sees the scored documents and threshold (#332).

        Only the removed QtWorkflowExecutor.score_documents used to set
        executor.scored_documents, so every report showed an empty score
        distribution.
        """
        doc = {"doc_id": 1, "title": "Test Doc", "abstract": "Test abstract"}
        score = {"score": 4.0, "reasoning": "Relevant"}
        self.mock_executor.generate_query.return_value = "test & query"
        self.mock_executor.search_documents.return_value = [doc]
        self.mock_executor.scoring_agent.evaluate_document.return_value = score
        self.mock_executor.citation_agent.extract_citation_from_document.return_value = Mock(
            passage="Test citation", document_id=1
        )

        def report_from_executor_state(citations: list) -> str:
            """Record the state generate_preliminary_report would read."""
            self.assertEqual(self.mock_executor.scored_documents, [(doc, score)])
            self.assertEqual(self.mock_executor.scoring_threshold, 2.5)
            return "# Test Report"

        self.mock_executor.generate_preliminary_report.side_effect = report_from_executor_state

        thread = WorkflowThread(
            executor=self.mock_executor,
            question="Test question",
            score_threshold=2.5,
            enable_counterfactual=False,
        )
        errors = QSignalSpy(thread.workflow_error)
        thread.run()

        self.assertEqual(errors.count(), 0)
        self.mock_executor.generate_preliminary_report.assert_called_once()
        thread.deleteLater()

    def test_status_message_signal_emission(self) -> None:
        """Test that status_message signals are emitted during workflow."""
        # Setup mock executor
        self.mock_executor.generate_query.return_value = "test & query"
        self.mock_executor.search_documents.return_value = []

        thread = WorkflowThread(
            executor=self.mock_executor,
            question="Test question"
        )

        # Setup signal spy
        spy = QSignalSpy(thread.status_message)

        # Run thread synchronously
        thread.run()

        # Verify status messages emitted
        self.assertGreater(spy.count(), 0)

        thread.deleteLater()

    # ========================================================================
    # Error Handling Tests
    # ========================================================================

    def test_handles_query_generation_failure(self) -> None:
        """Test that thread handles query generation failure gracefully."""
        # Setup mock executor to return None query
        self.mock_executor.generate_query.return_value = None

        thread = WorkflowThread(
            executor=self.mock_executor,
            question="Test question"
        )

        # Setup signal spy
        error_spy = QSignalSpy(thread.workflow_error)

        # Run thread synchronously
        thread.run()

        # Verify error signal emitted
        self.assertEqual(error_spy.count(), 1)

        thread.deleteLater()

    def test_handles_empty_query_gracefully(self) -> None:
        """Test that thread handles empty query string."""
        # Setup mock executor to return empty query
        self.mock_executor.generate_query.return_value = "   "

        thread = WorkflowThread(
            executor=self.mock_executor,
            question="Test question"
        )

        # Setup signal spy
        error_spy = QSignalSpy(thread.workflow_error)

        # Run thread synchronously
        thread.run()

        # Verify error signal emitted
        self.assertEqual(error_spy.count(), 1)

        thread.deleteLater()

    def test_handles_scoring_exception(self) -> None:
        """Test that thread handles scoring exceptions gracefully."""
        # Setup mock executor
        self.mock_executor.generate_query.return_value = "test & query"
        self.mock_executor.search_documents.return_value = [
            {"doc_id": 1, "title": "Test", "abstract": "Test"}
        ]
        self.mock_executor.scoring_agent.evaluate_document.side_effect = Exception("Scoring failed")

        thread = WorkflowThread(
            executor=self.mock_executor,
            question="Test question"
        )

        # Setup signal spy
        error_spy = QSignalSpy(thread.workflow_error)

        # Run thread synchronously
        thread.run()

        # Verify error signal emitted
        self.assertEqual(error_spy.count(), 1)
        error = error_spy.at(0)[0]
        self.assertIn("Scoring failed", str(error))

        thread.deleteLater()

    # ========================================================================
    # Signal Connectivity Tests
    # ========================================================================

    def test_all_required_signals_exist(self) -> None:
        """Test that all required signals are defined on WorkflowThread."""
        thread = WorkflowThread(
            executor=self.mock_executor,
            question="Test question"
        )

        # Progress signals
        self.assertTrue(hasattr(thread, 'step_started'))
        self.assertTrue(hasattr(thread, 'step_progress'))
        self.assertTrue(hasattr(thread, 'step_completed'))
        self.assertTrue(hasattr(thread, 'status_message'))

        # Result signals
        self.assertTrue(hasattr(thread, 'query_generated'))
        self.assertTrue(hasattr(thread, 'documents_found'))
        self.assertTrue(hasattr(thread, 'documents_scored'))
        self.assertTrue(hasattr(thread, 'citations_extracted'))
        self.assertTrue(hasattr(thread, 'preliminary_report_generated'))
        self.assertTrue(hasattr(thread, 'counterfactual_analysis_complete'))
        self.assertTrue(hasattr(thread, 'final_report_generated'))

        # Completion signals
        self.assertTrue(hasattr(thread, 'workflow_completed'))
        self.assertTrue(hasattr(thread, 'workflow_error'))
        self.assertTrue(hasattr(thread, 'workflow_cancelled'))

        thread.deleteLater()

    def test_signals_are_qt_signals(self) -> None:
        """Test that all signals are proper Qt Signal objects."""
        # Check class-level signal definitions
        self.assertIsInstance(WorkflowThread.step_started, Signal)
        self.assertIsInstance(WorkflowThread.workflow_completed, Signal)
        self.assertIsInstance(WorkflowThread.workflow_error, Signal)
        self.assertIsInstance(WorkflowThread.workflow_cancelled, Signal)

    # ========================================================================
    # No Documents Scenario Tests
    # ========================================================================

    def test_handles_no_documents_found(self) -> None:
        """Test that thread handles case when no documents are found."""
        # Setup mock executor
        self.mock_executor.generate_query.return_value = "test & query"
        self.mock_executor.search_documents.return_value = []

        thread = WorkflowThread(
            executor=self.mock_executor,
            question="Test question"
        )

        # Setup signal spy
        completed_spy = QSignalSpy(thread.workflow_completed)

        # Run thread synchronously
        thread.run()

        # Verify completion signal emitted with status 'no_documents'
        self.assertEqual(completed_spy.count(), 1)
        results = completed_spy.at(0)[0]
        self.assertEqual(results['status'], 'no_documents')

        thread.deleteLater()

    def test_handles_no_scores(self) -> None:
        """Test that thread handles case when documents can't be scored."""
        # Setup mock executor
        self.mock_executor.generate_query.return_value = "test & query"
        self.mock_executor.search_documents.return_value = [
            {"doc_id": 1, "title": "Test", "abstract": "Test"}
        ]
        # Return None for scoring to simulate failure
        self.mock_executor.scoring_agent.evaluate_document.return_value = None

        thread = WorkflowThread(
            executor=self.mock_executor,
            question="Test question"
        )

        # Setup signal spy
        completed_spy = QSignalSpy(thread.workflow_completed)

        # Run thread synchronously
        thread.run()

        # Verify completion signal emitted with status 'no_scores'
        self.assertEqual(completed_spy.count(), 1)
        results = completed_spy.at(0)[0]
        self.assertEqual(results['status'], 'no_scores')

        thread.deleteLater()

    def test_handles_no_citations(self) -> None:
        """Test that thread handles case when no citations are extracted."""
        # Setup mock executor
        self.mock_executor.generate_query.return_value = "test & query"
        self.mock_executor.search_documents.return_value = [
            {"doc_id": 1, "title": "Test", "abstract": "Test"}
        ]
        self.mock_executor.scoring_agent.evaluate_document.return_value = {
            "score": 4.0,
            "reasoning": "Relevant"
        }
        self.mock_executor.citation_agent.extract_citation_from_document.return_value = None

        thread = WorkflowThread(
            executor=self.mock_executor,
            question="Test question"
        )

        # Setup signal spy
        completed_spy = QSignalSpy(thread.workflow_completed)

        # Run thread synchronously
        thread.run()

        # Verify completion signal emitted with status 'no_citations'
        self.assertEqual(completed_spy.count(), 1)
        results = completed_spy.at(0)[0]
        self.assertEqual(results['status'], 'no_citations')

        thread.deleteLater()

    def test_citation_summary_reports_rejections(self) -> None:
        """The thread reports rejected passages from this run only (#292)."""
        from bmlibrarian.agents.citation_agent import (
            REJECT_PASSAGE_EMPTY, REJECT_PASSAGE_NOT_FOUND, CitationFinderAgent,
        )

        abstract = "Aspirin reduces the risk of heart attack. It may increase bleeding."
        agent = CitationFinderAgent(model="gpt-oss:20b", show_model_info=False, max_retries=0)
        # A rejection from an earlier run must not be counted again.
        agent._validation_stats['failed_citations'].append({'reason': REJECT_PASSAGE_EMPTY})
        self.mock_executor.citation_agent = agent
        self.mock_executor.citation_extraction_threshold = 0.7
        documents = [
            ({'id': 1, 'title': 'a', 'abstract': abstract}, {'score': 4.0}),
            ({'id': 2, 'title': 'b', 'abstract': abstract}, {'score': 4.0}),
        ]
        responses = [
            {'has_relevant_content': True, 'relevant_passage': passage,
             'summary': 'Aspirin helps.', 'relevance_score': 0.9}
            for passage in ("Aspirin reduces the risk of heart attack.", "Statins lower cholesterol.")
        ]
        thread = WorkflowThread(executor=self.mock_executor, question="q")
        with patch.object(agent, 'test_connection', return_value=True), \
                patch.object(agent, '_generate_and_parse_json', side_effect=responses):
            citations = thread._extract_citations_progressive(documents, score_threshold=3.0)

        self.assertEqual(len(citations), 1)
        self.assertEqual(
            thread.citation_summary_text,
            f"Extracted 1 citations from 2 documents (1 rejected: {REJECT_PASSAGE_NOT_FOUND} ×1)"
        )
        thread.deleteLater()

    def _run_with_real_citation_agent(self, passages: list) -> tuple:
        """
        Run the whole workflow with a real CitationFinderAgent, one LLM passage per document.

        Returns:
            ``(thread, status_spy, summary_spy)``.
        """
        from bmlibrarian.agents.citation_agent import CitationFinderAgent

        abstract = "Aspirin reduces the risk of heart attack. It may increase bleeding."
        agent = CitationFinderAgent(model="gpt-oss:20b", show_model_info=False, max_retries=0)
        self.mock_executor.citation_agent = agent
        self.mock_executor.citation_extraction_threshold = 0.7
        self.mock_executor.generate_query.return_value = "aspirin"
        self.mock_executor.search_documents.return_value = [
            {'id': i, 'title': 't', 'abstract': abstract} for i in range(len(passages))
        ]
        self.mock_executor.scoring_agent.evaluate_document.return_value = {'score': 4.0}
        self.mock_executor.generate_preliminary_report.return_value = "# Report"
        responses = [
            {'has_relevant_content': True, 'relevant_passage': passage,
             'summary': 'Aspirin helps.', 'relevance_score': 0.9}
            for passage in passages
        ]
        thread = WorkflowThread(executor=self.mock_executor, question="q", enable_counterfactual=False)
        status_spy = QSignalSpy(thread.status_message)
        summary_spy = QSignalSpy(thread.citation_summary)
        with patch.object(agent, 'test_connection', return_value=True), \
                patch.object(agent, '_generate_and_parse_json', side_effect=responses):
            thread.run()
        return thread, status_spy, summary_spy

    def test_run_reports_rejections_when_no_citations(self) -> None:
        """With every passage rejected, the status line and Citations tab say why (#292)."""
        from bmlibrarian.agents.citation_agent import REJECT_PASSAGE_NOT_FOUND

        thread, status_spy, summary_spy = self._run_with_real_citation_agent(
            ["Statins lower cholesterol."]
        )

        summary = f"Extracted 0 citations from 1 documents (1 rejected: {REJECT_PASSAGE_NOT_FOUND} ×1)"
        self.assertEqual([summary_spy.at(i)[0] for i in range(summary_spy.count())], [summary])
        statuses = [status_spy.at(i)[0] for i in range(status_spy.count())]
        self.assertIn(f"⚠️ No citations could be extracted: {summary}", statuses)
        thread.deleteLater()

    def test_run_warns_when_some_passages_rejected(self) -> None:
        """A run with citations but also rejections gets a warning, not a tick (#292)."""
        from bmlibrarian.agents.citation_agent import REJECT_PASSAGE_NOT_FOUND

        thread, status_spy, _ = self._run_with_real_citation_agent(
            ["Aspirin reduces the risk of heart attack.", "Statins lower cholesterol."]
        )

        statuses = [status_spy.at(i)[0] for i in range(status_spy.count())]
        self.assertIn(
            f"⚠️ Extracted 1 citations from 2 documents (1 rejected: {REJECT_PASSAGE_NOT_FOUND} ×1)",
            statuses
        )
        thread.deleteLater()

    def test_citation_summary_counts_failures_in_the_thread(self) -> None:
        """A document that fails in the thread's own code counts as an error in the summary."""
        from bmlibrarian.agents.citation_agent import CitationFinderAgent

        agent = CitationFinderAgent(model="gpt-oss:20b", show_model_info=False, max_retries=0)
        self.mock_executor.citation_agent = agent
        broken = Mock(spec=['widened_from'])  # no .passage: building the display dict fails
        broken.widened_from = None
        thread = WorkflowThread(executor=self.mock_executor, question="q")
        with patch.object(agent, 'extract_citation_from_document', return_value=broken):
            thread._extract_citations_progressive(
                [({'id': 7, 'title': 'a', 'abstract': 'x'}, {'score': 4.0})], score_threshold=3.0
            )

        self.assertIn("1 failed with an error, see log", thread.citation_summary_text)
        self.assertTrue(thread.citation_problems)
        self.assertEqual(agent.get_validation_stats()['errored_documents'][0]['document_id'], 7)
        thread.deleteLater()

    # ========================================================================
    # Counterfactual Analysis Tests
    # ========================================================================

    def test_counterfactual_disabled(self) -> None:
        """Test that counterfactual analysis is skipped when disabled."""
        # Setup mock executor for successful workflow
        self.mock_executor.generate_query.return_value = "test & query"
        self.mock_executor.search_documents.return_value = [
            {"doc_id": 1, "title": "Test Doc", "abstract": "Test abstract"}
        ]
        self.mock_executor.scoring_agent.evaluate_document.return_value = {
            "score": 4.0,
            "reasoning": "Relevant"
        }
        # The thread extracts citations per document via the citation agent
        self.mock_executor.citation_agent.extract_citation_from_document.return_value = Mock(
            passage="Test citation", document_id=1
        )
        self.mock_executor.generate_preliminary_report.return_value = "# Test Report"

        thread = WorkflowThread(
            executor=self.mock_executor,
            question="Test question",
            enable_counterfactual=False
        )

        # Setup signal spy
        cf_spy = QSignalSpy(thread.counterfactual_analysis_complete)
        completed_spy = QSignalSpy(thread.workflow_completed)

        # Run thread synchronously
        thread.run()

        # Verify counterfactual signal NOT emitted
        self.assertEqual(cf_spy.count(), 0)

        # But workflow completed
        self.assertEqual(completed_spy.count(), 1)

        # Counterfactual results should be None
        results = completed_spy.at(0)[0]
        self.assertIsNone(results.get('counterfactual_results'))

        thread.deleteLater()


class TestWorkflowThreadDegradedSteps(unittest.TestCase):
    """Steps that fail without stopping the run must still be visible (#332 review)."""

    # Same QApplication and mocked executor as TestWorkflowThread (not
    # subclassed, which would run its tests twice)
    setUpClass = TestWorkflowThread.setUpClass
    setUp = TestWorkflowThread.setUp

    def _prime_successful_run(self) -> None:
        """Make every step up to the preliminary report succeed."""
        self.mock_executor.generate_query.return_value = "test & query"
        self.mock_executor.search_documents.return_value = [
            {"doc_id": 1, "title": "Test Doc", "abstract": "Test abstract"}
        ]
        self.mock_executor.scoring_agent.evaluate_document.return_value = {
            "score": 4.0, "reasoning": "Relevant"
        }
        self.mock_executor.citation_agent.extract_citation_from_document.return_value = Mock(
            passage="Test citation", document_id=1, widened_from=None
        )
        self.mock_executor.generate_preliminary_report.return_value = "# Preliminary"

    def _run(self, **kwargs) -> Dict[str, QSignalSpy]:
        """Run a thread synchronously and spy on its outcome signals."""
        thread = WorkflowThread(executor=self.mock_executor, question="Q", **kwargs)
        self.addCleanup(thread.deleteLater)
        spies = {
            name: QSignalSpy(getattr(thread, name))
            for name in ('final_report_generated', 'workflow_warning',
                         'workflow_completed', 'workflow_error')
        }
        thread.run()
        return spies

    def test_failed_final_report_publishes_the_preliminary_one(self) -> None:
        """If ReportBuilder raises, the preliminary report is emitted as final, with a warning."""
        self._prime_successful_run()
        self.mock_executor.counterfactual_agent.find_contradictory_literature.return_value = {
            'analysis': None, 'summary': {}
        }
        with patch(
            'bmlibrarian.gui.qt.plugins.research.workflow_thread.ReportBuilder'
        ) as builder:
            builder.return_value.build_final_report.side_effect = RuntimeError("boom")
            spies = self._run(enable_counterfactual=True)

        self.assertEqual(spies['final_report_generated'].count(), 1)
        self.assertEqual(spies['final_report_generated'].at(0)[0], "# Preliminary")
        self.assertEqual(spies['workflow_warning'].count(), 1)
        self.assertIn("RuntimeError: boom", spies['workflow_warning'].at(0)[0])
        self.assertEqual(spies['workflow_completed'].count(), 1)

    def test_empty_final_report_publishes_the_preliminary_one(self) -> None:
        """An empty ReportBuilder result also falls back visibly."""
        self._prime_successful_run()
        self.mock_executor.counterfactual_agent.find_contradictory_literature.return_value = {
            'analysis': None, 'summary': {}
        }
        with patch(
            'bmlibrarian.gui.qt.plugins.research.workflow_thread.ReportBuilder'
        ) as builder:
            builder.return_value.build_final_report.return_value = ""
            spies = self._run(enable_counterfactual=True)

        self.assertEqual(spies['final_report_generated'].at(0)[0], "# Preliminary")
        self.assertEqual(spies['workflow_warning'].count(), 1)

    def test_counterfactual_failure_warns(self) -> None:
        """A failed counterfactual analysis is reported, not just logged."""
        self._prime_successful_run()
        self.mock_executor.counterfactual_agent.find_contradictory_literature.side_effect = (
            TimeoutError()
        )
        spies = self._run(enable_counterfactual=True)

        self.assertEqual(spies['workflow_warning'].count(), 1)
        self.assertIn("TimeoutError", spies['workflow_warning'].at(0)[0])
        self.assertEqual(spies['final_report_generated'].at(0)[0], "# Preliminary")

    def test_empty_counterfactual_result_warns(self) -> None:
        """A counterfactual analysis that returns nothing is reported."""
        self._prime_successful_run()
        self.mock_executor.counterfactual_agent.find_contradictory_literature.return_value = None
        spies = self._run(enable_counterfactual=True)

        self.assertEqual(spies['workflow_warning'].count(), 1)
        self.assertIn("no result", spies['workflow_warning'].at(0)[0])

    def test_missing_citation_agent_is_an_error_not_an_empty_result(self) -> None:
        """No citation agent fails the run instead of reading as 'no citations'."""
        self._prime_successful_run()
        self.mock_executor.citation_agent = None
        spies = self._run(enable_counterfactual=False)

        self.assertEqual(spies['workflow_error'].count(), 1)
        self.assertEqual(spies['workflow_completed'].count(), 0)

    def test_missing_scoring_agent_is_a_clear_error(self) -> None:
        """No scoring agent fails the run with a message naming the agent."""
        self._prime_successful_run()
        self.mock_executor.scoring_agent = None
        spies = self._run(enable_counterfactual=False)

        self.assertEqual(spies['workflow_error'].count(), 1)
        self.assertIn("scoring agent", str(spies['workflow_error'].at(0)[0]))


class TestWorkflowThreadIntegration(unittest.TestCase):
    """Integration tests for WorkflowThread with ResearchTabWidget signal handlers."""

    @classmethod
    def setUpClass(cls) -> None:
        """Set up QApplication for all tests."""
        if not QApplication.instance():
            cls.app = QApplication([])
        else:
            cls.app = QApplication.instance()

    def test_signal_connectivity_pattern(self) -> None:
        """Test that signals can be connected using expected pattern."""
        # Create mock executor
        mock_executor = Mock(spec=QtWorkflowExecutor)
        mock_executor._is_active = True
        mock_executor.query_agent = Mock()
        mock_executor.scoring_agent = Mock()

        # Create thread
        thread = WorkflowThread(
            executor=mock_executor,
            question="Test question"
        )

        # Create mock handlers
        step_handler = Mock()
        error_handler = Mock()
        completed_handler = Mock()

        # Connect signals (simulating what ResearchTabWidget does)
        thread.step_started.connect(step_handler)
        thread.workflow_error.connect(error_handler)
        thread.workflow_completed.connect(completed_handler)

        # Setup mock to fail
        mock_executor.generate_query.side_effect = Exception("Test error")

        # Run thread synchronously
        thread.run()

        # Verify handlers were called
        step_handler.assert_called()  # At least one step should have started
        error_handler.assert_called_once()

        thread.deleteLater()

    def test_graceful_handling_if_executor_inactive(self) -> None:
        """Test that thread handles inactive executor gracefully."""
        # Create mock executor that becomes inactive
        mock_executor = Mock(spec=QtWorkflowExecutor)
        mock_executor._is_active = True
        mock_executor.query_agent = Mock()
        mock_executor.scoring_agent = Mock()

        # generate_query simulates executor becoming inactive
        def mock_generate_query():
            mock_executor._is_active = False
            raise RuntimeError("Workflow executor is not active")

        mock_executor.generate_query.side_effect = mock_generate_query

        thread = WorkflowThread(
            executor=mock_executor,
            question="Test question"
        )

        # Setup signal spy
        error_spy = QSignalSpy(thread.workflow_error)

        # Run thread synchronously
        thread.run()

        # Verify error signal emitted with appropriate error
        self.assertEqual(error_spy.count(), 1)
        error = error_spy.at(0)[0]
        self.assertIn("not active", str(error))

        thread.deleteLater()


if __name__ == '__main__':
    unittest.main()
