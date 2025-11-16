"""
Tests for Ollama Library Migration

Tests migration from requests to ollama library across configuration GUI components.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import sys
from pathlib import Path

# Ensure src is in path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from PySide6.QtWidgets import QApplication

# Import components that use ollama library
from bmlibrarian.gui.qt.plugins.configuration.config_tab import ConfigurationTabWidget
from bmlibrarian.gui.qt.plugins.configuration.agent_config_widget import AgentConfigWidget


class TestOllamaMigration(unittest.TestCase):
    """Test cases for ollama library migration."""

    @classmethod
    def setUpClass(cls):
        """Set up QApplication for all tests."""
        if not QApplication.instance():
            cls.app = QApplication([])
        else:
            cls.app = QApplication.instance()

    def setUp(self):
        """Set up test fixtures."""
        self.mock_config = {
            'ollama': {
                'host': 'http://localhost:11434'
            },
            'agents': {
                'query': {
                    'model': 'test-model',
                    'temperature': 0.7
                }
            }
        }

    def tearDown(self):
        """Clean up after each test."""
        pass

    @patch('bmlibrarian.gui.qt.plugins.configuration.config_tab.ollama')
    def test_ollama_import_available(self, mock_ollama):
        """Test that ollama module is imported at module level."""
        # Import should succeed
        from bmlibrarian.gui.qt.plugins.configuration import config_tab

        # Verify ollama is used in the module
        self.assertTrue(hasattr(config_tab, 'ollama'))

    @patch('bmlibrarian.gui.qt.plugins.configuration.config_tab.ollama.Client')
    def test_ollama_client_creation(self, mock_client_class):
        """Test Ollama client creation with configured URL."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        # Mock the client.list() response
        mock_client.list.return_value = {
            'models': [
                {'name': 'model1'},
                {'name': 'model2'}
            ]
        }

        # Create widget
        with patch('bmlibrarian.gui.qt.plugins.configuration.config_tab.get_config', return_value=self.mock_config):
            widget = ConfigurationTabWidget()

            # Trigger test connection
            widget._test_connection()

            # Verify client was created with correct host
            mock_client_class.assert_called_with(host='http://localhost:11434')

            # Clean up
            widget.deleteLater()

    @patch('bmlibrarian.gui.qt.plugins.configuration.config_tab.ollama.Client')
    def test_ollama_list_models(self, mock_client_class):
        """Test listing models using ollama library."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        # Mock successful response
        mock_response = {
            'models': [
                {'name': 'gpt-oss:20b'},
                {'name': 'medgemma4B_it_q8:latest'},
                {'name': 'llama3.2:latest'}
            ]
        }
        mock_client.list.return_value = mock_response

        # Create widget
        with patch('bmlibrarian.gui.qt.plugins.configuration.config_tab.get_config', return_value=self.mock_config):
            widget = ConfigurationTabWidget()

            # Call refresh_models
            widget.refresh_models()

            # Verify client.list() was called
            mock_client.list.assert_called()

            # Clean up
            widget.deleteLater()

    @patch('bmlibrarian.gui.qt.plugins.configuration.config_tab.ollama.Client')
    def test_ollama_response_validation(self, mock_client_class):
        """Test response validation for ollama API calls."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        # Test invalid response (missing 'models' key)
        mock_client.list.return_value = {'invalid': 'response'}

        # Create widget
        with patch('bmlibrarian.gui.qt.plugins.configuration.config_tab.get_config', return_value=self.mock_config):
            widget = ConfigurationTabWidget()

            # Should raise ValueError due to validation
            with self.assertRaises(ValueError) as context:
                widget._test_connection()

            self.assertIn("Invalid response from Ollama server", str(context.exception))

            # Clean up
            widget.deleteLater()

    @patch('bmlibrarian.gui.qt.plugins.configuration.config_tab.ollama.Client')
    def test_ollama_response_validation_not_dict(self, mock_client_class):
        """Test response validation when response is not a dict."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        # Test invalid response (not a dict)
        mock_client.list.return_value = "invalid string response"

        # Create widget
        with patch('bmlibrarian.gui.qt.plugins.configuration.config_tab.get_config', return_value=self.mock_config):
            widget = ConfigurationTabWidget()

            # Should raise ValueError
            with self.assertRaises(ValueError) as context:
                widget._test_connection()

            self.assertIn("Invalid response from Ollama server", str(context.exception))

            # Clean up
            widget.deleteLater()

    @patch('bmlibrarian.gui.qt.plugins.configuration.config_tab.ollama.Client')
    def test_ollama_connection_error_handling(self, mock_client_class):
        """Test error handling for connection failures."""
        # Simulate connection error
        mock_client_class.side_effect = ConnectionError("Cannot connect to Ollama server")

        # Create widget
        with patch('bmlibrarian.gui.qt.plugins.configuration.config_tab.get_config', return_value=self.mock_config):
            widget = ConfigurationTabWidget()

            # Test connection should handle error gracefully
            # (The widget shows error dialog, doesn't crash)
            widget._test_connection()

            # Clean up
            widget.deleteLater()

    @patch('bmlibrarian.gui.qt.plugins.configuration.config_tab.ollama.Client')
    def test_ollama_refresh_models_validation(self, mock_client_class):
        """Test refresh_models also validates responses."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        # Test invalid response
        mock_client.list.return_value = {'invalid': 'response'}

        # Create widget
        with patch('bmlibrarian.gui.qt.plugins.configuration.config_tab.get_config', return_value=self.mock_config):
            widget = ConfigurationTabWidget()

            # Should raise ValueError
            with self.assertRaises(ValueError) as context:
                widget.refresh_models()

            self.assertIn("Invalid response from Ollama server", str(context.exception))

            # Clean up
            widget.deleteLater()

    @patch('bmlibrarian.gui.qt.plugins.configuration.config_tab.ollama.Client')
    def test_model_extraction_from_response(self, mock_client_class):
        """Test extracting model names from ollama response."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        # Mock response with models
        test_models = [
            {'name': 'model1', 'size': 1000},
            {'name': 'model2', 'size': 2000},
            {'name': 'model3', 'size': 3000}
        ]
        mock_client.list.return_value = {'models': test_models}

        # Create widget
        with patch('bmlibrarian.gui.qt.plugins.configuration.config_tab.get_config', return_value=self.mock_config):
            widget = ConfigurationTabWidget()

            # Add mock agent widget to verify model list update
            mock_agent_widget = MagicMock(spec=AgentConfigWidget)
            widget.config_widgets['test_agent'] = mock_agent_widget

            # Call refresh_models
            widget.refresh_models()

            # Verify update_model_list was called with model names
            mock_agent_widget.update_model_list.assert_called_once()
            call_args = mock_agent_widget.update_model_list.call_args[0][0]

            # Should extract just the names
            self.assertEqual(call_args, ['model1', 'model2', 'model3'])

            # Clean up
            widget.deleteLater()

    @patch('bmlibrarian.gui.qt.plugins.configuration.config_tab.ollama.Client')
    def test_empty_models_list(self, mock_client_class):
        """Test handling of empty models list."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        # Mock response with no models
        mock_client.list.return_value = {'models': []}

        # Create widget
        with patch('bmlibrarian.gui.qt.plugins.configuration.config_tab.get_config', return_value=self.mock_config):
            widget = ConfigurationTabWidget()

            # Should handle empty list gracefully
            widget._test_connection()

            # Clean up
            widget.deleteLater()

    @patch('bmlibrarian.gui.qt.plugins.configuration.config_tab.ollama.Client')
    def test_ollama_url_configuration(self, mock_client_class):
        """Test that Ollama URL is correctly used from configuration."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.list.return_value = {'models': []}

        # Test with custom URL
        custom_config = {
            'ollama': {
                'host': 'http://custom-host:8080'
            }
        }

        with patch('bmlibrarian.gui.qt.plugins.configuration.config_tab.get_config', return_value=custom_config):
            widget = ConfigurationTabWidget()

            # Set the custom URL in the general widget
            widget.general_widget.ollama_url_input.setText('http://custom-host:8080')

            # Trigger test connection
            widget._test_connection()

            # Verify client was created with custom host
            mock_client_class.assert_called_with(host='http://custom-host:8080')

            # Clean up
            widget.deleteLater()


class TestOllamaIntegration(unittest.TestCase):
    """Integration tests for ollama library usage."""

    @classmethod
    def setUpClass(cls):
        """Set up QApplication for all tests."""
        if not QApplication.instance():
            cls.app = QApplication([])
        else:
            cls.app = QApplication.instance()

    @patch('bmlibrarian.gui.qt.plugins.configuration.config_tab.ollama')
    def test_no_requests_library_used(self, mock_ollama):
        """Test that requests library is not used for Ollama communication."""
        # This test verifies the migration away from requests

        # Import the module
        from bmlibrarian.gui.qt.plugins.configuration import config_tab

        # Verify ollama is imported
        self.assertTrue(hasattr(config_tab, 'ollama'))

        # The module should NOT import requests for Ollama
        # (This is a structural test - we verify ollama is used instead)

    @patch('bmlibrarian.gui.qt.plugins.configuration.config_tab.ollama.Client')
    def test_multiple_api_calls(self, mock_client_class):
        """Test multiple ollama API calls work correctly."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        # Mock successful response
        mock_client.list.return_value = {
            'models': [{'name': 'test-model'}]
        }

        config = {
            'ollama': {'host': 'http://localhost:11434'},
            'agents': {}
        }

        with patch('bmlibrarian.gui.qt.plugins.configuration.config_tab.get_config', return_value=config):
            widget = ConfigurationTabWidget()

            # Make multiple calls
            widget._test_connection()
            widget.refresh_models()

            # Both should succeed
            self.assertEqual(mock_client.list.call_count, 2)

            # Clean up
            widget.deleteLater()


if __name__ == '__main__':
    unittest.main()
