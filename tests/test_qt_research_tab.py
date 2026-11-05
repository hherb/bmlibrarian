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
from bmlibrarian.gui.qt.plugins.research.tab_updaters import clear_layout_widgets
from bmlibrarian.gui.qt.widgets.citation_card import CitationCard
from bmlibrarian.gui.qt.widgets.toast import ToastLevel

# Agents the research tab needs for its workflow executor (mocked: no Ollama/DB)
AGENT_NAMES = (
    'query_agent', 'scoring_agent', 'citation_agent',
    'reporting_agent', 'counterfactual_agent', 'editor_agent',
)


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
        # A modal dialog would block the test run; toasts are recorded
        patcher = patch('bmlibrarian.gui.qt.plugins.research.research_tab.QMessageBox')
        patcher.start()
        self.addCleanup(patcher.stop)
        toast_patcher = patch('bmlibrarian.gui.qt.plugins.research.research_tab.show_toast')
        self.show_toast = toast_patcher.start()
        self.addCleanup(toast_patcher.stop)

        # Without agents the tab has no workflow executor
        self.agents = {name: Mock() for name in AGENT_NAMES}
        self.widget = ResearchTabWidget(agents=self.agents)

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
        self.assertIsNotNone(self.widget.literature_refs.widgets['layout'])
        self.assertIsNotNone(self.widget.citations_refs.widgets['layout'])

    def test_no_agents_disables_workflow(self):
        """Test that the tab without agents has no workflow executor."""
        widget = ResearchTabWidget()
        try:
            self.assertIsNone(widget.workflow_executor)
        finally:
            widget.deleteLater()

    def test_ui_components_exist(self):
        """Test that all UI components are created."""
        self.assertIsNotNone(self.widget.question_input)
        self.assertIsNotNone(self.widget.start_button)
        self.assertIsNotNone(self.widget.status_label)
        self.assertIsNotNone(self.widget.research_tabs)

    # ========================================================================
    # Widget Cleanup Tests
    # ========================================================================

    def test_clear_layout_widgets_removes_all_widgets(self):
        """Test that clear_layout_widgets removes all widgets from layout."""
        # Setup: create test layout with widgets
        test_layout = QVBoxLayout()
        widgets = [QLabel(f"Label {i}") for i in range(5)]
        for widget in widgets:
            test_layout.addWidget(widget)

        # Verify layout has widgets
        self.assertEqual(test_layout.count(), 5)

        # Test: clear layout
        clear_layout_widgets(test_layout)

        # Verify: layout is empty
        self.assertEqual(test_layout.count(), 0)

    def test_clear_layout_widgets_disconnects_signals_safely(self):
        """Test that clear_layout_widgets handles signal disconnection safely."""
        # Setup: create test layout with widget that has signals
        test_layout = QVBoxLayout()
        test_widget = QLabel("Test")

        # Connect a test signal
        test_slot = Mock()
        test_widget.destroyed.connect(test_slot)

        test_layout.addWidget(test_widget)

        # Test: clear layout (should not raise exception)
        try:
            clear_layout_widgets(test_layout)
            success = True
        except Exception as e:
            success = False
            self.fail(f"clear_layout_widgets raised exception: {e}")

        # Verify: no exception raised
        self.assertTrue(success)

    def test_clear_layout_widgets_handles_already_deleted_widget(self):
        """Test that clear_layout_widgets handles already-deleted widgets."""
        # Setup: create test layout
        test_layout = QVBoxLayout()
        test_widget = QLabel("Test")
        test_layout.addWidget(test_widget)

        # Manually delete the widget first
        test_widget.deleteLater()
        QApplication.processEvents()  # Process deletion

        # Test: clear layout (should not raise exception)
        try:
            clear_layout_widgets(test_layout)
            success = True
        except RuntimeError:
            # RuntimeError is expected when widget is already deleted
            success = True
        except Exception as e:
            success = False
            self.fail(f"Unexpected exception: {e}")

        # Verify: handled gracefully
        self.assertTrue(success)

    def test_documents_found_replaces_literature_content(self):
        """Test that documents_found replaces existing Literature tab content."""
        layout = self.widget.literature_refs.widgets['layout']
        old_labels = [QLabel(f"Old {i}") for i in range(3)]
        for label in old_labels:
            layout.addWidget(label)

        docs = [{"id": 1, "title": "Test Paper 1", "abstract": "Abstract 1"}]
        self.widget._on_documents_found(docs)

        # Old widgets removed: one card plus trailing stretch remain
        remaining = [layout.itemAt(i).widget() for i in range(layout.count())]
        for label in old_labels:
            self.assertNotIn(label, remaining)
        self.assertEqual(layout.count(), 2)

    def test_documents_found_shows_empty_state(self):
        """Test that documents_found shows empty state when no documents."""
        self.widget._on_documents_found([])

        layout = self.widget.literature_refs.widgets['layout']
        self.assertGreater(layout.count(), 0)
        first_widget = layout.itemAt(0).widget()
        self.assertIsInstance(first_widget, QLabel)
        self.assertIn("No documents", first_widget.text())

    # ========================================================================
    # Citation Tab Tests
    # ========================================================================

    def test_citations_tab_shows_empty_state_initially(self):
        """Test that the Citations tab starts with an empty-state label."""
        layout = self.widget.citations_refs.widgets['layout']
        first_widget = layout.itemAt(0).widget()
        self.assertIsInstance(first_widget, QLabel)
        self.assertIs(first_widget, self.widget.citations_refs.widgets['empty_label'])

    def test_first_citation_replaces_empty_state(self):
        """Test that the first extracted citation removes the empty state."""
        empty_label = self.widget.citations_refs.widgets['empty_label']
        citation = {
            "document_id": 1,
            "document_title": "Test Paper",
            "passage": "Test passage",
            "summary": "Test summary",
            "relevance_score": 0.9,
        }
        self.widget._on_citation_extracted(citation, 1, 1)

        layout = self.widget.citations_refs.widgets['layout']
        widgets = [layout.itemAt(i).widget() for i in range(layout.count())]
        self.assertNotIn(empty_label, widgets)
        self.assertIsInstance(widgets[0], CitationCard)

    def test_citations_extracted_creates_citation_cards(self):
        """Test that each extracted citation adds a citation card."""
        citations = [
            {
                "document_id": i,
                "document_title": f"Paper {i}",
                "passage": f"Passage {i}",
                "summary": f"Summary {i}",
                "relevance_score": 0.9,
            }
            for i in (1, 2)
        ]
        for index, citation in enumerate(citations, 1):
            self.widget._on_citation_extracted(citation, index, len(citations))

        layout = self.widget.citations_refs.widgets['layout']
        cards = [
            layout.itemAt(i).widget() for i in range(layout.count())
            if isinstance(layout.itemAt(i).widget(), CitationCard)
        ]
        self.assertEqual(len(cards), 2)

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

    def test_start_without_question_shows_warning_toast(self):
        """An empty question is reported in a toast, not a modal (#332)."""
        from bmlibrarian.gui.qt.widgets.toast import ToastLevel

        self.widget.question_input.clear()
        with patch('bmlibrarian.gui.qt.plugins.research.workflow_thread.WorkflowThread') as MockThread:
            self.widget._on_start_research()

        MockThread.assert_not_called()
        self.show_toast.assert_called_once()
        _, message, level = self.show_toast.call_args.args
        self.assertIn("research question", message)
        self.assertEqual(level, ToastLevel.WARNING)
        from bmlibrarian.gui.qt.plugins.research import research_tab
        # mock_calls includes calls to child attributes like QMessageBox.warning
        self.assertEqual(research_tab.QMessageBox.mock_calls, [])

    def test_start_button_click_triggers_workflow(self):
        """Test that start button click starts a background WorkflowThread."""
        # Setup: set question
        self.widget.question_input.setPlainText("Test research question")

        # Test: click start button (thread mocked so no workflow really runs)
        with patch(
            'bmlibrarian.gui.qt.plugins.research.workflow_thread.WorkflowThread'
        ) as MockThread:
            QTest.mouseClick(self.widget.start_button, Qt.LeftButton)
            QApplication.processEvents()

        # Verify: thread created for the executor and question, then started
        MockThread.assert_called_once()
        kwargs = MockThread.call_args.kwargs
        self.assertIs(kwargs['executor'], self.widget.workflow_executor)
        self.assertEqual(kwargs['question'], "Test research question")
        MockThread.return_value.start.assert_called_once()
        self.assertTrue(self.widget.workflow_running)

    # ========================================================================
    # Settings change rebuilds agents (#330)
    # ========================================================================

    def _start_with_mocked_thread(self):
        """Click Start with WorkflowThread mocked; return the thread mock."""
        self.widget.question_input.setPlainText("Test research question")
        with patch(
            'bmlibrarian.gui.qt.plugins.research.workflow_thread.WorkflowThread'
        ) as MockThread:
            QTest.mouseClick(self.widget.start_button, Qt.LeftButton)
            QApplication.processEvents()
        return MockThread

    def test_settings_change_rebuilds_agents_and_executor_at_next_start(self):
        """The next research runs on new agents through a new executor."""
        audit_conn, db_manager = Mock(), Mock()
        self.agents['_audit_conn'] = audit_conn
        self.agents['_db_manager'] = db_manager
        old_orchestrator = Mock()
        self.agents['orchestrator'] = old_orchestrator
        old_executor = self.widget.workflow_executor
        old_executor_cleanup = patch.object(old_executor, 'cleanup').start()
        self.addCleanup(patch.stopall)
        new_agents = {name: Mock() for name in AGENT_NAMES}

        self.widget._reinitialize_agents()
        # Nothing is replaced until the next start (a running workflow keeps its executor)
        self.assertIs(self.widget.workflow_executor, old_executor)

        with patch(
            'bmlibrarian.agents.AgentFactory.create_all_agents', return_value=new_agents
        ) as create:
            MockThread = self._start_with_mocked_thread()

        create.assert_called_once_with(audit_conn=audit_conn)
        executor = MockThread.call_args.kwargs['executor']
        self.assertIsNot(executor, old_executor)
        self.assertIs(executor.agents['query_agent'], new_agents['query_agent'])
        self.assertIs(self.widget.agents['_audit_conn'], audit_conn)
        self.assertIs(self.widget.agents['_db_manager'], db_manager)
        # The old set is released
        old_executor_cleanup.assert_called_once()
        old_orchestrator.stop_processing.assert_called_once()

    def test_failed_rebuild_does_not_start_on_old_agents(self):
        """A failed rebuild aborts the start and is retried next time."""
        old_executor = self.widget.workflow_executor
        self.widget._reinitialize_agents()

        with patch(
            'bmlibrarian.agents.AgentFactory.create_all_agents',
            side_effect=RuntimeError("model missing"),
        ):
            MockThread = self._start_with_mocked_thread()

        MockThread.assert_not_called()
        self.assertFalse(self.widget.workflow_running)
        self.assertIs(self.widget.workflow_executor, old_executor)
        self.assertTrue(self.widget._agents_stale)
        _, message, level = self.show_toast.call_args.args
        self.assertIn("Settings not applied", message)
        self.assertIn("RuntimeError: model missing", message)
        self.assertEqual(level, ToastLevel.ERROR)

    # ========================================================================
    # Start-path notifications (#332)
    # ========================================================================

    def test_start_while_running_warns_and_starts_nothing(self):
        """A second Start during a run is refused with a warning toast."""
        self.widget.workflow_running = True
        self.widget.question_input.setPlainText("Test research question")
        with patch(
            'bmlibrarian.gui.qt.plugins.research.workflow_thread.WorkflowThread'
        ) as MockThread:
            self.widget._on_start_research()

        MockThread.assert_not_called()
        _, message, level = self.show_toast.call_args.args
        self.assertIn("already in progress", message)
        self.assertEqual(level, ToastLevel.WARNING)

    def test_start_without_executor_shows_error(self):
        """Without agents there is no executor; Start says so in an error toast."""
        self.widget.workflow_executor = None
        MockThread = self._start_with_mocked_thread()

        MockThread.assert_not_called()
        self.assertFalse(self.widget.workflow_running)
        _, message, level = self.show_toast.call_args.args
        self.assertIn("not initialized", message)
        self.assertEqual(level, ToastLevel.ERROR)

    def test_start_failure_resets_the_tab_and_reports_the_error(self):
        """If starting raises, Start works again and the error is shown and emitted."""
        errors = []
        self.widget.workflow_error.connect(errors.append)
        self.widget.question_input.setPlainText("Test research question")
        with patch(
            'bmlibrarian.gui.qt.plugins.research.workflow_thread.WorkflowThread',
            side_effect=TimeoutError(),
        ):
            self.widget._on_start_research()

        self.assertTrue(self.widget.start_button.isEnabled())
        self.assertFalse(self.widget.workflow_running)
        self.assertEqual(len(errors), 1)
        _, message, level = self.show_toast.call_args.args
        self.assertIn("Could not start the research workflow: TimeoutError", message)
        self.assertEqual(level, ToastLevel.ERROR)

    def test_start_emits_workflow_started(self):
        """workflow_started fires once the thread is started."""
        started = []
        self.widget.workflow_started.connect(lambda: started.append(True))
        self._start_with_mocked_thread()

        self.assertEqual(started, [True])

    def test_start_forgets_the_previous_report(self):
        """A new run cannot export the previous run's final report."""
        self.widget._on_final_report_generated("# Old report")
        save = self.widget.report_refs.widgets['save_markdown_button']
        self.assertTrue(save.isEnabled())

        self._start_with_mocked_thread()

        self.assertEqual(self.widget.final_report_markdown, "")
        self.assertFalse(save.isEnabled())
        self.assertFalse(self.widget.report_refs.widgets['export_json_button'].isEnabled())

    def test_new_research_forgets_the_report(self):
        """'New' clears the stored final report along with the results."""
        self.widget._on_final_report_generated("# Old report")
        self.widget._on_new_research()  # no results yet, so no confirmation

        self.assertEqual(self.widget.final_report_markdown, "")

    def test_main_settings_tab_marks_agents_stale(self):
        """Settings saved in the main Settings tab reach the research tab (#372)."""
        from bmlibrarian.gui.qt.plugins.settings.plugin import SettingsPlugin

        plugin = SettingsPlugin()  # the app's plugin manager keeps it alive
        settings = plugin.create_widget()
        self.addCleanup(settings.deleteLater)
        settings.agents_need_reinit.emit()
        self.assertTrue(self.widget._agents_stale)

    def test_main_settings_tab_save_marks_agents_stale(self):
        """Save (not only Apply) in the main Settings tab marks the agents stale."""
        from bmlibrarian.gui.qt.plugins.settings.plugin import SettingsPlugin

        plugin = SettingsPlugin()  # the app's plugin manager keeps it alive
        settings = plugin.create_widget()
        self.addCleanup(settings.deleteLater)
        module = 'bmlibrarian.gui.qt.plugins.settings.plugin'
        with patch(f'{module}.QMessageBox'), \
                patch.object(settings, '_update_config_from_ui'), \
                patch.object(settings.config, 'save_config'):
            settings._save_to_default()
        self.assertTrue(self.widget._agents_stale)

    def test_configuration_tab_save_marks_agents_stale(self):
        """A save in the Configuration tab reaches the research tab too."""
        from bmlibrarian.gui.qt.plugins.configuration.plugin import ConfigurationPlugin

        with patch(
            'bmlibrarian.gui.qt.plugins.configuration.config_tab.list_ollama_models',
            return_value=[],
        ):
            plugin = ConfigurationPlugin()  # the app's plugin manager keeps it alive
            config_widget = plugin.create_widget()
        self.addCleanup(config_widget.deleteLater)
        config_widget.config_saved.emit("config.json")
        self.assertTrue(self.widget._agents_stale)

    def test_cleanup_stops_listening_to_settings_events(self):
        """A cleaned-up research tab ignores later settings events."""
        from bmlibrarian.gui.qt.core.event_bus import EventBus, AGENTS_NEED_REINIT_EVENT

        self.widget.cleanup()
        EventBus().publish_data("settings", {"event": AGENTS_NEED_REINIT_EVENT})
        self.assertFalse(self.widget._agents_stale)

    def test_cleanup_tears_down_workflow_executor(self):
        """cleanup() releases the executor and is safe to call twice."""
        executor = self.widget.workflow_executor
        with patch.object(executor, 'cleanup') as executor_cleanup:
            self.widget.cleanup()
            self.widget.cleanup()

        executor_cleanup.assert_called_once()
        self.assertIsNone(self.widget.workflow_executor)


if __name__ == '__main__':
    unittest.main()
