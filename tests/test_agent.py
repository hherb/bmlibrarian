"""
Unit tests for the agent module.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock

from bmlib.llm import LLMResponse as BmlibResponse

from bmlibrarian.agents import QueryAgent
from bmlibrarian.llm import LLMClient, Provider, qualify_model_string
from bmlibrarian.llm.constants import DEFAULT_MAX_RETRIES


class TestQueryAgent:
    """Test cases for QueryAgent class."""

    def test_init_default_params(self):
        """Test QueryAgent initialization with default parameters."""
        agent = QueryAgent()
        assert agent.model == "medgemma4B_it_q8:latest"
        assert agent.host == "http://localhost:11434"
        assert isinstance(agent.client, LLMClient)

    def test_init_custom_params(self):
        """Test QueryAgent initialization with custom parameters."""
        agent = QueryAgent(model="custom-model", host="http://custom-host:8080")
        assert agent.model == "custom-model"
        assert agent.host == "http://custom-host:8080"

    def test_convert_question_empty_input(self):
        """Test convert_question raises ValueError for empty input."""
        agent = QueryAgent()

        with pytest.raises(ValueError, match="Question cannot be empty"):
            agent.convert_question("")

        with pytest.raises(ValueError, match="Question cannot be empty"):
            agent.convert_question("   ")

    @patch('bmlib.llm.client.LLMClient.chat')
    def test_convert_question_success(self, mock_chat):
        """Test successful question conversion."""
        # Setup mock
        mock_chat.return_value = BmlibResponse(
            content='diabetes & (kidney | renal) & function',
            model="test",
            input_tokens=10,
            output_tokens=5
        )

        agent = QueryAgent()
        question = "How does diabetes affect kidney function?"
        result = agent.convert_question(question)

        # Post-processing strips whitespace around the operators
        assert result == "diabetes&(kidney|renal)&function"

        mock_chat.assert_called_once()
        kwargs = mock_chat.call_args.kwargs
        assert kwargs['model'] == qualify_model_string(agent.model)
        assert kwargs['temperature'] == 0.1

        messages = kwargs['messages']
        assert len(messages) == 2
        assert messages[0].role == 'system'
        assert messages[1].role == 'user'
        assert messages[1].content == question

    @patch('bmlibrarian.llm.client.time.sleep')  # keep retry backoff instant
    @patch('bmlib.llm.client.LLMClient.chat')
    def test_convert_question_propagates_llm_failure(self, mock_chat, _mock_sleep):
        """
        A provider fault must reach the caller, not be swallowed.

        Asserting the retry count as well keeps this from passing trivially:
        the error type alone would still match if the request were never
        retried, or if the agent returned a fabricated query instead.
        """
        mock_chat.side_effect = RuntimeError("provider unavailable")

        agent = QueryAgent()

        with pytest.raises(RuntimeError, match="provider unavailable"):
            agent.convert_question("test question")

        assert mock_chat.call_count == DEFAULT_MAX_RETRIES

    @patch('bmlibrarian.llm.client.time.sleep')  # keep retry backoff instant
    @patch('bmlib.llm.client.LLMClient.chat')
    def test_convert_question_propagates_exhausted_providers(
        self, mock_chat, _mock_sleep,
    ):
        """
        ConnectionError is the LLM layer's "all providers failed" signal.

        It must reach the caller as such rather than being downgraded to a
        generic failure or an empty query.
        """
        mock_chat.side_effect = ConnectionError("all providers exhausted")

        agent = QueryAgent()

        with pytest.raises(ConnectionError, match="all providers exhausted"):
            agent.convert_question("test question")

    def test_validate_tsquery_valid_queries(self):
        """Test _validate_tsquery with valid queries."""
        agent = QueryAgent()

        valid_queries = [
            "diabetes & kidney",
            "(covid | coronavirus) & vaccine",
            "aspirin & (cardiovascular | cardiac)",
            "cancer & treatment & (chemotherapy | radiation)",
            "simple"
        ]

        for query in valid_queries:
            assert agent._validate_tsquery(query), f"Query should be valid: {query}"

    def test_validate_tsquery_invalid_queries(self):
        """Test _validate_tsquery with invalid queries."""
        agent = QueryAgent()

        invalid_queries = [
            "",  # empty
            "diabetes & (kidney",  # unbalanced parentheses
            "covid) & vaccine",  # unbalanced parentheses
            "diabetes && kidney",  # double operator
            "covid || vaccine",  # double operator
            "diabetes &| kidney",  # mixed operators
            "covid |& vaccine"  # mixed operators
        ]

        for query in invalid_queries:
            assert not agent._validate_tsquery(query), f"Query should be invalid: {query}"

    @patch('bmlibrarian.llm.client.LLMClient.test_provider')
    @patch('bmlibrarian.llm.client.LLMClient.list_models')
    def test_test_connection_success(self, mock_list_models, mock_test_provider):
        """Test successful connection test."""
        mock_test_provider.return_value = True
        mock_list_models.return_value = {'ollama': ['medgemma4B_it_q8:latest', 'other-model']}

        agent = QueryAgent()
        result = agent.test_connection()

        assert result is True
        # The configured model is looked up against its own provider
        mock_test_provider.assert_called_once_with(Provider.OLLAMA)
        mock_list_models.assert_called_once_with(Provider.OLLAMA)

    @patch('bmlibrarian.llm.client.LLMClient.test_provider')
    @patch('bmlibrarian.llm.client.LLMClient.list_models')
    def test_test_connection_model_not_found(self, mock_list_models, mock_test_provider):
        """Test connection test when model is not available."""
        mock_test_provider.return_value = True
        mock_list_models.return_value = {'ollama': ['other-model', 'another-model']}

        agent = QueryAgent()
        result = agent.test_connection()

        assert result is False

    @patch('bmlibrarian.llm.client.LLMClient.test_provider')
    def test_test_connection_error(self, mock_test_provider):
        """Test connection test handles errors."""
        mock_test_provider.side_effect = Exception("Connection failed")

        agent = QueryAgent()
        result = agent.test_connection()

        assert result is False

    @patch('bmlibrarian.llm.client.LLMClient.test_provider')
    @patch('bmlibrarian.llm.client.LLMClient.list_models')
    def test_get_available_models_success(self, mock_list_models, mock_test_provider):
        """Test successful retrieval of available models."""
        mock_list_models.return_value = {'ollama': ['medgemma4B_it_q8:latest', 'mistral', 'codellama']}

        agent = QueryAgent()
        result = agent.get_available_models()

        expected = ['medgemma4B_it_q8:latest', 'mistral', 'codellama']
        assert result == expected

    @patch('bmlibrarian.llm.client.LLMClient.list_models')
    def test_get_available_models_error(self, mock_list_models):
        """Test get_available_models handles errors."""
        mock_list_models.side_effect = Exception("Connection failed")

        agent = QueryAgent()

        with pytest.raises(ConnectionError, match="Failed to connect to LLM provider"):
            agent.get_available_models()


@pytest.mark.integration
class TestQueryAgentIntegration:
    """Integration tests for QueryAgent (require Ollama server)."""

    def test_real_connection(self):
        """Test connection to real Ollama server (if available)."""
        agent = QueryAgent()

        # This test will be skipped if Ollama is not running
        try:
            result = agent.test_connection()
            # If we get here, Ollama is running
            assert isinstance(result, bool)
        except Exception:
            pytest.skip("Ollama server not available")

    def test_real_query_conversion(self):
        """Test real query conversion with Ollama server (if available)."""
        agent = QueryAgent()

        try:
            if not agent.test_connection():
                pytest.skip("Ollama server not available or model not found")

            result = agent.convert_question("What are the effects of aspirin on heart disease?")

            # Basic checks on the result
            assert isinstance(result, str)
            assert len(result) > 0
            assert 'aspirin' in result.lower()
            assert ('heart' in result.lower() or 'cardiac' in result.lower() or 'cardiovascular' in result.lower())

        except Exception:
            pytest.skip("Ollama server not available or connection failed")
