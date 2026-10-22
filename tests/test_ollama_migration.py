"""
Tests for Ollama access in the configuration GUI.

The configuration tab no longer talks to Ollama itself (first via requests,
then via the ollama library): it goes through the LLM abstraction layer's
``list_ollama_models()``. Response validation and the reachable/empty
distinction live there and are tested in tests/test_llm_module.py; these
tests cover how the configuration tab uses it.
"""

import unittest
from unittest.mock import patch, MagicMock
import sys
from pathlib import Path

# Ensure src is in path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from PySide6.QtWidgets import QApplication

from bmlibrarian.gui.qt.plugins.configuration import config_tab
from bmlibrarian.gui.qt.plugins.configuration.config_tab import ConfigurationTabWidget
from bmlibrarian.gui.qt.plugins.configuration.agent_config_widget import AgentConfigWidget

CONFIG_TAB = 'bmlibrarian.gui.qt.plugins.configuration.config_tab'
TEST_HOST = 'http://localhost:11434'


class _ConfigTabTestCase(unittest.TestCase):
    """Base class: QApplication, mocked model listing and no modal dialogs."""

    @classmethod
    def setUpClass(cls):
        """Set up QApplication for all tests."""
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        """Patch list_ollama_models and QMessageBox (modals would hang the suite)."""
        list_patcher = patch(f'{CONFIG_TAB}.list_ollama_models', return_value=[])
        box_patcher = patch(f'{CONFIG_TAB}.QMessageBox')
        self.mock_list_models = list_patcher.start()
        self.mock_message_box = box_patcher.start()
        self.addCleanup(patch.stopall)

    def _create_widget(self, host: str = TEST_HOST) -> ConfigurationTabWidget:
        """Create the widget, point it at ``host`` and forget startup calls."""
        widget = ConfigurationTabWidget()
        self.addCleanup(widget.deleteLater)
        widget.general_widget.ollama_url_input.setText(host)
        self.mock_list_models.reset_mock()
        return widget


class TestOllamaMigration(_ConfigTabTestCase):
    """Test cases for the configuration tab's Ollama access."""

    def test_uses_llm_abstraction_layer(self):
        """config_tab lists models via the LLM layer, not the ollama library."""
        self.assertTrue(hasattr(config_tab, 'list_ollama_models'))
        self.assertFalse(hasattr(config_tab, 'ollama'))

    def test_startup_loads_models(self):
        """Model dropdowns are populated from Ollama when the tab is built."""
        ConfigurationTabWidget().deleteLater()
        self.mock_list_models.assert_called_once()

    def test_test_connection_uses_configured_host(self):
        """Test connection queries the host entered in the general settings."""
        self.mock_list_models.return_value = ['model1', 'model2']
        widget = self._create_widget()

        widget._test_connection()

        self.mock_list_models.assert_called_with(host=TEST_HOST)
        self.mock_message_box.information.assert_called_once()
        self.mock_message_box.critical.assert_not_called()

    def test_ollama_list_models(self):
        """refresh_models() lists models via the LLM layer."""
        self.mock_list_models.return_value = ['gpt-oss:20b', 'medgemma4B_it_q8:latest']
        widget = self._create_widget()

        widget.refresh_models()

        self.mock_list_models.assert_called_once_with(host=TEST_HOST)

    def test_ollama_connection_error_handling(self):
        """An unreachable server is reported in an error dialog, not raised."""
        self.mock_list_models.side_effect = ConnectionError("Cannot connect to Ollama server")
        widget = self._create_widget()

        widget._test_connection()

        self.mock_message_box.critical.assert_called_once()
        self.mock_message_box.information.assert_not_called()

    def test_ollama_refresh_models_error_handling(self):
        """refresh_models() reports failures through the status signal."""
        self.mock_list_models.side_effect = ConnectionError("Cannot connect")
        widget = self._create_widget()
        messages = []
        widget.status_message.connect(messages.append)

        widget.refresh_models()

        self.assertTrue(any("Failed to refresh models" in m for m in messages))

    def test_model_extraction_from_response(self):
        """Model names are pushed to every agent widget."""
        self.mock_list_models.return_value = ['model1', 'model2', 'model3']
        widget = self._create_widget()
        mock_agent_widget = MagicMock(spec=AgentConfigWidget)
        widget.config_widgets['test_agent'] = mock_agent_widget

        widget.refresh_models()

        mock_agent_widget.update_model_list.assert_called_once_with(
            ['model1', 'model2', 'model3']
        )

    def test_empty_models_list(self):
        """A server with no models is reported as a failed connection."""
        self.mock_list_models.return_value = []
        widget = self._create_widget()

        widget._test_connection()

        self.mock_message_box.critical.assert_called_once()
        self.mock_message_box.information.assert_not_called()

    def test_ollama_url_configuration(self):
        """A custom Ollama URL is passed through to the model listing."""
        self.mock_list_models.return_value = ['model1']
        widget = self._create_widget(host='http://custom-host:8080')

        widget._test_connection()

        self.mock_list_models.assert_called_with(host='http://custom-host:8080')


class TestOllamaIntegration(_ConfigTabTestCase):
    """Integration tests for Ollama usage in the configuration tab."""

    def test_multiple_api_calls(self):
        """Repeated connection tests and refreshes each query the server."""
        self.mock_list_models.return_value = ['test-model']
        widget = self._create_widget()

        widget._test_connection()  # lists models, then refreshes them on success
        widget.refresh_models()

        self.assertEqual(self.mock_list_models.call_count, 3)


if __name__ == '__main__':
    unittest.main()
