"""
Unit tests for PRISMA 2020 Lab plugin.

Tests the PRISMA2020LabTabWidget and PRISMA2020AssessmentWorker classes.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
import sys

from bmlibrarian.gui.qt.plugins.prisma2020_lab.prisma2020_lab_tab import (
    PRISMA2020LabTabWidget,
    PRISMA2020AssessmentWorker
)
from bmlibrarian.gui.qt.plugins.prisma2020_lab.constants import (
    DOC_ID_MIN_VALUE,
    DOC_ID_MAX_VALUE,
    DEFAULT_PRISMA_MODEL,
    DEFAULT_TEMPERATURE,
    DEFAULT_TOP_P,
    DEFAULT_MAX_TOKENS,
    MIN_CONFIDENCE_LAB_MODE
)
from bmlibrarian.agents.prisma2020_agent import PRISMA2020Assessment


@pytest.fixture(scope="module")
def qapp():
    """Create QApplication instance for testing."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app
    # Don't quit the app here as it may be used by other tests


@pytest.fixture
def mock_config():
    """Create mock configuration."""
    config = Mock()
    config.get_ollama_config.return_value = {'host': 'http://localhost:11434'}
    config.get_model.return_value = 'gpt-oss:20b'
    config.get_agent_config.return_value = {
        'temperature': 0.1,
        'top_p': 0.9,
        'max_tokens': 4000
    }
    return config


@pytest.fixture
def mock_prisma_agent():
    """Create mock PRISMA2020Agent."""
    agent = Mock()
    agent.get_available_models.return_value = ['gpt-oss:20b', 'medgemma4B_it_q8:latest']

    # Create mock assessment
    assessment = Mock(spec=PRISMA2020Assessment)
    assessment.overall_compliance_percentage = 85.5
    assessment.total_applicable_items = 27
    assessment.fully_reported_items = 20
    assessment.partially_reported_items = 5
    assessment.not_reported_items = 2
    assessment.is_systematic_review = True
    assessment.is_meta_analysis = True
    assessment.suitability_rationale = "This is a systematic review and meta-analysis."
    assessment.get_compliance_category.return_value = "Good (75-89%)"

    agent.assess_prisma_compliance.return_value = assessment
    return agent


@pytest.fixture
def widget(qapp, mock_config):
    """Create PRISMA2020LabTabWidget for testing."""
    with patch('bmlibrarian.gui.qt.plugins.prisma2020_lab.prisma2020_lab_tab.get_config', return_value=mock_config):
        with patch('bmlibrarian.gui.qt.plugins.prisma2020_lab.prisma2020_lab_tab.AgentOrchestrator'):
            with patch('bmlibrarian.gui.qt.plugins.prisma2020_lab.prisma2020_lab_tab.PRISMA2020Agent'):
                widget = PRISMA2020LabTabWidget()
                yield widget
                widget.cleanup()


class TestPRISMA2020LabTabWidget:
    """Test suite for PRISMA2020LabTabWidget."""

    def test_widget_creation(self, widget):
        """Test that widget is created successfully."""
        assert widget is not None
        assert widget.scale > 0
        assert widget.config is not None

    def test_ui_components_exist(self, widget):
        """Test that all UI components are created."""
        assert widget.model_combo is not None
        assert widget.doc_id_input is not None
        assert widget.load_button is not None
        assert widget.clear_button is not None
        assert widget.refresh_button is not None
        assert widget.doc_title_label is not None
        assert widget.doc_metadata_label is not None
        assert widget.doc_abstract_edit is not None
        assert widget.assessment_scroll is not None
        assert widget.status_label is not None

    def test_doc_id_validator(self, widget):
        """Test that document ID validator has correct limits."""
        validator = widget.doc_id_input.validator()
        assert validator is not None
        assert validator.bottom() == DOC_ID_MIN_VALUE
        assert validator.top() == DOC_ID_MAX_VALUE

    def test_config_validation_missing_ollama_host(self, qapp):
        """Test config validation fails with missing Ollama host."""
        bad_config = Mock()
        bad_config.get_ollama_config.return_value = {}

        with patch('bmlibrarian.gui.qt.plugins.prisma2020_lab.prisma2020_lab_tab.get_config', return_value=bad_config):
            with pytest.raises(ValueError, match="Missing required configuration: Ollama host"):
                PRISMA2020LabTabWidget()

    def test_config_validation_success(self, widget):
        """Test config validation succeeds with valid config."""
        # Widget creation should succeed (fixture already validates)
        assert widget.config is not None

    def test_clear_all(self, widget):
        """Test clearing all fields."""
        # Set some values
        widget.doc_id_input.setText("12345")
        widget.doc_title_label.setText("Test Document")
        widget.doc_metadata_label.setText("Year: 2023")
        widget.doc_abstract_edit.setPlainText("Test abstract")

        # Clear all
        widget._clear_all()

        # Verify all fields are cleared
        assert widget.doc_id_input.text() == ""
        assert widget.doc_title_label.text() == "No document loaded"
        assert widget.doc_metadata_label.text() == ""
        assert widget.doc_abstract_edit.toPlainText() == ""
        assert widget.current_document is None
        assert widget.current_assessment is None

    def test_clear_layout(self, widget):
        """Test recursive layout clearing."""
        from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel

        # Create a test layout with nested widgets
        test_widget = QWidget()
        test_layout = QVBoxLayout(test_widget)
        test_layout.addWidget(QLabel("Test 1"))
        test_layout.addWidget(QLabel("Test 2"))

        # Clear the layout
        widget._clear_layout(test_layout)

        # Verify layout is empty
        assert test_layout.count() == 0

    def test_score_color_thresholds(self, widget):
        """Test score color mapping."""
        from bmlibrarian.gui.qt.plugins.prisma2020_lab.constants import SCORE_COLORS

        # Fully reported (≥1.9)
        assert widget._get_score_color(2.0) == SCORE_COLORS[2.0]
        assert widget._get_score_color(1.9) == SCORE_COLORS[2.0]

        # Partially reported (≥0.9)
        assert widget._get_score_color(1.0) == SCORE_COLORS[1.0]
        assert widget._get_score_color(0.9) == SCORE_COLORS[1.0]

        # Not reported (<0.9)
        assert widget._get_score_color(0.0) == SCORE_COLORS[0.0]
        assert widget._get_score_color(0.5) == SCORE_COLORS[0.0]

    def test_score_text_caching(self, widget):
        """Test score text display caching."""
        # Clear cache first
        widget._score_display_cache.clear()

        # First call should cache
        text1 = widget._get_score_text(2.0)
        assert 2.0 in widget._score_display_cache

        # Second call should use cache
        text2 = widget._get_score_text(2.0)
        assert text1 == text2
        assert text1 == "✓ Fully Reported (2.0)"

    def test_compliance_color_thresholds(self, widget):
        """Test compliance color mapping."""
        from bmlibrarian.gui.qt.plugins.prisma2020_lab.constants import COMPLIANCE_COLORS

        # Excellent (≥90%)
        assert widget._get_compliance_color(95.0) == COMPLIANCE_COLORS['excellent']
        assert widget._get_compliance_color(90.0) == COMPLIANCE_COLORS['excellent']

        # Good (75-89%)
        assert widget._get_compliance_color(80.0) == COMPLIANCE_COLORS['good']
        assert widget._get_compliance_color(75.0) == COMPLIANCE_COLORS['good']

        # Adequate (60-74%)
        assert widget._get_compliance_color(65.0) == COMPLIANCE_COLORS['adequate']
        assert widget._get_compliance_color(60.0) == COMPLIANCE_COLORS['adequate']

        # Poor (40-59%)
        assert widget._get_compliance_color(50.0) == COMPLIANCE_COLORS['poor']
        assert widget._get_compliance_color(40.0) == COMPLIANCE_COLORS['poor']

        # Very poor (<40%)
        assert widget._get_compliance_color(30.0) == COMPLIANCE_COLORS['very_poor']

    @patch('bmlibrarian.gui.qt.plugins.prisma2020_lab.prisma2020_lab_tab.fetch_documents_by_ids')
    def test_load_document_not_found(self, mock_fetch, widget):
        """Test loading non-existent document."""
        mock_fetch.return_value = []

        widget.doc_id_input.setText("99999")

        with patch.object(widget, 'QMessageBox') as mock_msgbox:
            widget._load_document()

        assert widget.current_document is None

    @patch('bmlibrarian.gui.qt.plugins.prisma2020_lab.prisma2020_lab_tab.fetch_documents_by_ids')
    def test_load_document_success(self, mock_fetch, widget):
        """Test successful document loading."""
        test_doc = {
            'id': 12345,
            'title': 'Test Systematic Review',
            'year': 2023,
            'pmid': '12345678',
            'doi': '10.1234/test',
            'abstract': 'This is a test abstract for a systematic review.'
        }
        mock_fetch.return_value = [test_doc]

        widget.doc_id_input.setText("12345")

        # Mock the agent
        widget.prisma_agent = Mock()
        widget.prisma_agent.assess_prisma_compliance = Mock()

        widget._load_document()

        assert widget.current_document == test_doc
        assert widget.doc_title_label.text() == test_doc['title']

    def test_display_document(self, widget):
        """Test document display."""
        test_doc = {
            'id': 12345,
            'title': 'Test Document',
            'year': 2023,
            'pmid': '12345678',
            'doi': '10.1234/test',
            'abstract': 'Test abstract'
        }

        widget.current_document = test_doc
        widget._display_document()

        assert widget.doc_title_label.text() == 'Test Document'
        assert 'Year: 2023' in widget.doc_metadata_label.text()
        assert 'PMID: 12345678' in widget.doc_metadata_label.text()
        assert 'DOI: 10.1234/test' in widget.doc_metadata_label.text()
        assert widget.doc_abstract_edit.toPlainText() == 'Test abstract'

    def test_worker_cleanup_on_new_assessment(self, widget):
        """Test that previous worker is terminated before starting new one."""
        # Create a mock running worker
        mock_worker = Mock()
        mock_worker.isRunning.return_value = True
        widget.worker = mock_worker

        # Setup for new assessment
        test_doc = {'id': 12345, 'title': 'Test', 'abstract': 'Test'}
        widget.current_document = test_doc
        widget.prisma_agent = Mock()

        with patch('bmlibrarian.gui.qt.plugins.prisma2020_lab.prisma2020_lab_tab.fetch_documents_by_ids', return_value=[test_doc]):
            with patch('bmlibrarian.gui.qt.plugins.prisma2020_lab.prisma2020_lab_tab.PRISMA2020AssessmentWorker'):
                widget.doc_id_input.setText("12345")
                widget._load_document()

        # Verify old worker was terminated
        mock_worker.terminate.assert_called_once()
        mock_worker.wait.assert_called_once()

    def test_cleanup(self, widget):
        """Test cleanup method."""
        # Setup mock worker
        mock_worker = Mock()
        mock_worker.isRunning.return_value = True
        widget.worker = mock_worker

        # Setup mock orchestrator
        mock_orchestrator = Mock()
        widget.orchestrator = mock_orchestrator

        widget.cleanup()

        # Verify cleanup
        mock_worker.terminate.assert_called_once()
        mock_worker.wait.assert_called_once()
        mock_orchestrator.shutdown.assert_called_once()


class TestPRISMA2020AssessmentWorker:
    """Test suite for PRISMA2020AssessmentWorker."""

    def test_worker_creation(self, mock_prisma_agent):
        """Test worker thread creation."""
        test_doc = {'id': 12345, 'title': 'Test', 'abstract': 'Test'}
        worker = PRISMA2020AssessmentWorker(mock_prisma_agent, test_doc)

        assert worker.prisma_agent == mock_prisma_agent
        assert worker.document == test_doc

    def test_worker_successful_assessment(self, mock_prisma_agent, qapp):
        """Test successful assessment execution."""
        test_doc = {'id': 12345, 'title': 'Test', 'abstract': 'Test'}
        worker = PRISMA2020AssessmentWorker(mock_prisma_agent, test_doc)

        # Mock signals
        result_ready_mock = Mock()
        error_occurred_mock = Mock()
        worker.result_ready.connect(result_ready_mock)
        worker.error_occurred.connect(error_occurred_mock)

        # Run worker
        worker.run()

        # Verify assessment was called with correct parameters
        mock_prisma_agent.assess_prisma_compliance.assert_called_once()
        call_args = mock_prisma_agent.assess_prisma_compliance.call_args
        assert call_args[1]['document'] == test_doc
        assert call_args[1]['min_confidence'] == MIN_CONFIDENCE_LAB_MODE

    def test_worker_assessment_error(self, qapp):
        """Test assessment error handling."""
        # Create agent that raises exception
        error_agent = Mock()
        error_agent.assess_prisma_compliance.side_effect = Exception("Test error")

        test_doc = {'id': 12345, 'title': 'Test', 'abstract': 'Test'}
        worker = PRISMA2020AssessmentWorker(error_agent, test_doc)

        # Mock signals
        result_ready_mock = Mock()
        error_occurred_mock = Mock()
        worker.result_ready.connect(result_ready_mock)
        worker.error_occurred.connect(error_occurred_mock)

        # Run worker
        worker.run()

        # Verify error was emitted (signals are queued in Qt, so we check the mock wasn't called)
        assert not result_ready_mock.called

    def test_worker_no_results(self, qapp):
        """Test handling of no assessment results."""
        # Create agent that returns None
        none_agent = Mock()
        none_agent.assess_prisma_compliance.return_value = None

        test_doc = {'id': 12345, 'title': 'Test', 'abstract': 'Test'}
        worker = PRISMA2020AssessmentWorker(none_agent, test_doc)

        # Mock signals
        result_ready_mock = Mock()
        error_occurred_mock = Mock()
        worker.result_ready.connect(result_ready_mock)
        worker.error_occurred.connect(error_occurred_mock)

        # Run worker
        worker.run()

        # Verify no result was emitted
        assert not result_ready_mock.called


class TestPRISMA2020LabPluginIntegration:
    """Integration tests for PRISMA 2020 Lab plugin."""

    @patch('bmlibrarian.gui.qt.plugins.prisma2020_lab.prisma2020_lab_tab.fetch_documents_by_ids')
    @patch('bmlibrarian.gui.qt.plugins.prisma2020_lab.prisma2020_lab_tab.PRISMA2020Agent')
    def test_full_assessment_workflow(self, mock_agent_class, mock_fetch, widget, mock_prisma_agent):
        """Test complete assessment workflow from document load to display."""
        # Setup
        test_doc = {
            'id': 12345,
            'title': 'Test Systematic Review',
            'year': 2023,
            'abstract': 'Test abstract'
        }
        mock_fetch.return_value = [test_doc]
        widget.prisma_agent = mock_prisma_agent

        # Load document
        widget.doc_id_input.setText("12345")
        widget._load_document()

        # Verify document loaded
        assert widget.current_document == test_doc

        # Simulate assessment completion
        assessment = mock_prisma_agent.assess_prisma_compliance.return_value
        widget._on_assessment_complete(assessment)

        # Verify assessment stored
        assert widget.current_assessment == assessment

    def test_model_refresh_and_change(self, widget, mock_prisma_agent):
        """Test model refresh and change functionality."""
        widget.prisma_agent = mock_prisma_agent

        # Refresh models
        widget._refresh_models()

        # Verify models were fetched
        mock_prisma_agent.get_available_models.assert_called_once()

        # Verify combo box populated
        assert widget.model_combo.count() > 0

    def test_invalid_document_id_input(self, widget):
        """Test handling of invalid document ID input."""
        # Test empty input
        widget.doc_id_input.setText("")

        with patch('bmlibrarian.gui.qt.plugins.prisma2020_lab.prisma2020_lab_tab.QMessageBox') as mock_msgbox:
            widget._load_document()
            # Should show warning (but we can't easily verify QMessageBox calls)

        # Test non-numeric input (validator should prevent this, but test anyway)
        widget.doc_id_input.setText("abc")
        # Validator should reject non-numeric input

    def test_constants_usage(self, widget):
        """Test that constants are properly used throughout the plugin."""
        # Verify default model constant
        assert DEFAULT_PRISMA_MODEL == "gpt-oss:20b"

        # Verify document ID limits
        assert DOC_ID_MIN_VALUE == 1
        assert DOC_ID_MAX_VALUE == 2147483647

        # Verify lab mode confidence
        assert MIN_CONFIDENCE_LAB_MODE == 0.0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
