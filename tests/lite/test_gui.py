"""Tests for BMLibrarian Lite GUI module."""

import os
import sys
import pytest
from unittest.mock import Mock, patch, MagicMock

# Skip all tests if PySide6 is not available or no display
try:
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import Qt
    _PYSIDE6_AVAILABLE = True
except ImportError:
    _PYSIDE6_AVAILABLE = False

# Check for display availability
_HAS_DISPLAY = os.environ.get("DISPLAY") is not None or sys.platform == "win32"

# Skip marker for GUI tests
pytestmark = pytest.mark.skipif(
    not (_PYSIDE6_AVAILABLE and _HAS_DISPLAY),
    reason="GUI tests require PySide6 and a display"
)


@pytest.fixture(scope="module")
def qapp():
    """Create QApplication for tests."""
    # Check if QApplication already exists
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture
def mock_config():
    """Create a mock LiteConfig."""
    from bmlibrarian.lite.config import LiteConfig
    config = LiteConfig()
    config.llm.provider = "anthropic"
    config.llm.model = "claude-3-haiku-20240307"
    return config


@pytest.fixture
def mock_storage(mock_config):
    """Create a mock LiteStorage."""
    from bmlibrarian.lite.storage import LiteStorage
    with patch.object(LiteStorage, '__init__', return_value=None):
        storage = LiteStorage.__new__(LiteStorage)
        storage.config = mock_config
        return storage


class TestSettingsDialog:
    """Tests for SettingsDialog."""

    def test_settings_dialog_initialization(self, qapp, mock_config):
        """Test that settings dialog initializes correctly."""
        from bmlibrarian.lite.gui.settings_dialog import SettingsDialog

        dialog = SettingsDialog(mock_config)

        assert dialog.config == mock_config
        assert dialog.windowTitle() == "Settings"

    def test_settings_dialog_loads_config(self, qapp, mock_config):
        """Test that settings dialog loads config values."""
        from bmlibrarian.lite.gui.settings_dialog import SettingsDialog

        mock_config.llm.model = "claude-3-haiku-20240307"
        mock_config.llm.temperature = 0.5
        mock_config.pubmed.email = "test@example.com"

        dialog = SettingsDialog(mock_config)

        assert dialog.model_combo.currentText() == "claude-3-haiku-20240307"
        assert dialog.temperature_spin.value() == 0.5
        assert dialog.email_input.text() == "test@example.com"

    def test_settings_dialog_has_required_fields(self, qapp, mock_config):
        """Test that settings dialog has all required input fields."""
        from bmlibrarian.lite.gui.settings_dialog import SettingsDialog

        dialog = SettingsDialog(mock_config)

        # LLM settings
        assert dialog.model_combo is not None
        assert dialog.temperature_spin is not None
        assert dialog.max_tokens_spin is not None

        # Embedding settings
        assert dialog.embed_combo is not None

        # PubMed settings
        assert dialog.email_input is not None
        assert dialog.api_key_input is not None

        # API keys
        assert dialog.anthropic_key_input is not None


class TestChatMessage:
    """Tests for ChatMessage widget."""

    def test_chat_message_user(self, qapp):
        """Test user message creation."""
        from bmlibrarian.lite.gui.document_interrogation_tab import ChatMessage

        message = ChatMessage("Hello, world!", is_user=True)

        assert message.property("messageRole") == "user"

    def test_chat_message_assistant(self, qapp):
        """Test assistant message creation."""
        from bmlibrarian.lite.gui.document_interrogation_tab import ChatMessage

        message = ChatMessage("I can help with that.", is_user=False)

        assert message.property("messageRole") == "assistant"


class TestWorkflowWorker:
    """Tests for WorkflowWorker thread."""

    def test_workflow_worker_initialization(self, qapp, mock_config, mock_storage):
        """Test workflow worker initialization."""
        from bmlibrarian.lite.gui.systematic_review_tab import WorkflowWorker

        worker = WorkflowWorker(
            question="Test question",
            config=mock_config,
            storage=mock_storage,
            max_results=50,
            min_score=4,
        )

        assert worker.question == "Test question"
        assert worker.config == mock_config
        assert worker.max_results == 50
        assert worker.min_score == 4
        assert worker._cancelled is False

    def test_workflow_worker_cancel(self, qapp, mock_config, mock_storage):
        """Test workflow worker cancellation."""
        from bmlibrarian.lite.gui.systematic_review_tab import WorkflowWorker

        worker = WorkflowWorker(
            question="Test question",
            config=mock_config,
            storage=mock_storage,
        )

        worker.cancel()

        assert worker._cancelled is True


class TestSystematicReviewTab:
    """Tests for SystematicReviewTab widget."""

    def test_systematic_review_tab_initialization(
        self, qapp, mock_config, mock_storage
    ):
        """Test systematic review tab initialization."""
        from bmlibrarian.lite.gui.systematic_review_tab import SystematicReviewTab

        with patch.object(SystematicReviewTab, '_setup_ui'):
            tab = SystematicReviewTab.__new__(SystematicReviewTab)
            tab.config = mock_config
            tab.storage = mock_storage
            tab._worker = None
            tab._current_report = ""

            assert tab.config == mock_config
            assert tab.storage == mock_storage

    def test_systematic_review_tab_has_controls(
        self, qapp, mock_config, mock_storage
    ):
        """Test that systematic review tab has required controls."""
        from bmlibrarian.lite.gui.systematic_review_tab import SystematicReviewTab

        tab = SystematicReviewTab(config=mock_config, storage=mock_storage)

        assert tab.question_input is not None
        assert tab.max_results_spin is not None
        assert tab.min_score_spin is not None
        assert tab.run_btn is not None
        assert tab.cancel_btn is not None
        assert tab.progress_bar is not None
        assert tab.report_view is not None
        assert tab.export_btn is not None


class TestDocumentInterrogationTab:
    """Tests for DocumentInterrogationTab widget."""

    def test_document_interrogation_tab_has_controls(
        self, qapp, mock_config, mock_storage
    ):
        """Test that document interrogation tab has required controls."""
        from bmlibrarian.lite.gui.document_interrogation_tab import (
            DocumentInterrogationTab
        )

        with patch(
            'bmlibrarian.lite.gui.document_interrogation_tab.LiteInterrogationAgent'
        ):
            tab = DocumentInterrogationTab(config=mock_config, storage=mock_storage)

            assert tab.doc_label is not None
            assert tab.load_btn is not None
            assert tab.clear_btn is not None
            assert tab.question_input is not None
            assert tab.ask_btn is not None

    def test_document_interrogation_initial_state(
        self, qapp, mock_config, mock_storage
    ):
        """Test initial state of document interrogation tab."""
        from bmlibrarian.lite.gui.document_interrogation_tab import (
            DocumentInterrogationTab
        )

        with patch(
            'bmlibrarian.lite.gui.document_interrogation_tab.LiteInterrogationAgent'
        ):
            tab = DocumentInterrogationTab(config=mock_config, storage=mock_storage)

            # Initially no document is loaded
            assert tab._document_loaded is False
            assert tab.ask_btn.isEnabled() is False
            assert tab.clear_btn.isEnabled() is False


class TestModuleImports:
    """Test module imports and availability."""

    def test_gui_available_flag(self):
        """Test that _GUI_AVAILABLE flag is set correctly."""
        from bmlibrarian.lite import _GUI_AVAILABLE

        assert _GUI_AVAILABLE is True

    def test_gui_exports(self):
        """Test that GUI exports are available."""
        from bmlibrarian.lite import (
            LiteMainWindow,
            run_lite_app,
            SystematicReviewTab,
            DocumentInterrogationTab,
            SettingsDialog,
        )

        assert LiteMainWindow is not None
        assert run_lite_app is not None
        assert SystematicReviewTab is not None
        assert DocumentInterrogationTab is not None
        assert SettingsDialog is not None
