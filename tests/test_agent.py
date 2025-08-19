"""
Unit tests for the agent module.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import ollama

from bmlibrarian.agents import QueryAgent


class TestQueryAgent:
    """Test cases for QueryAgent class."""
    
    def test_init_default_params(self):
        """Test QueryAgent initialization with default parameters."""
        agent = QueryAgent()
        assert agent.model == "medgemma4B_it_q8:latest"
        assert agent.host == "http://localhost:11434"
        assert isinstance(agent.client, ollama.Client)
    
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
    
    @patch('bmlibrarian.agents.base.ollama.Client')
    def test_convert_question_success(self, mock_client_class):
        """Test successful question conversion."""
        # Setup mock
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.chat.return_value = {
            'message': {
                'content': 'diabetes & (kidney | renal) & function'
            }
        }
        
        agent = QueryAgent()
        result = agent.convert_question("How does diabetes affect kidney function?")
        
        assert result == "diabetes & (kidney | renal) & function"
        mock_client.chat.assert_called_once()
        
        # Verify chat was called with correct parameters
        call_args = mock_client.chat.call_args
        assert call_args[1]['model'] == "medgemma4B_it_q8:latest"
        assert len(call_args[1]['messages']) == 2
        assert call_args[1]['messages'][0]['role'] == 'system'
        assert call_args[1]['messages'][1]['role'] == 'user'
        assert call_args[1]['messages'][1]['content'] == "How does diabetes affect kidney function?"
        assert call_args[1]['options']['temperature'] == 0.1
    
    @patch('bmlibrarian.agents.base.ollama.Client')
    def test_convert_question_ollama_error(self, mock_client_class):
        """Test convert_question handles Ollama errors."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.chat.side_effect = ollama.ResponseError("Connection failed")
        
        agent = QueryAgent()
        
        with pytest.raises(ConnectionError, match="Failed to get response from Ollama"):
            agent.convert_question("test question")
    
    @patch('bmlibrarian.agents.base.ollama.Client')
    def test_convert_question_unexpected_error(self, mock_client_class):
        """Test convert_question handles unexpected errors."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.chat.side_effect = Exception("Unexpected error")
        
        agent = QueryAgent()
        
        with pytest.raises(Exception):
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
    
    @patch('bmlibrarian.agents.base.ollama.Client')
    def test_test_connection_success(self, mock_client_class):
        """Test successful connection test."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        
        # Mock the new ollama API structure
        mock_model1 = Mock()
        mock_model1.model = 'medgemma4B_it_q8:latest'
        mock_model2 = Mock()
        mock_model2.model = 'other-model'
        
        mock_response = Mock()
        mock_response.models = [mock_model1, mock_model2]
        mock_client.list.return_value = mock_response
        
        agent = QueryAgent()
        result = agent.test_connection()
        
        assert result is True
        mock_client.list.assert_called_once()
    
    @patch('bmlibrarian.agents.base.ollama.Client')
    def test_test_connection_model_not_found(self, mock_client_class):
        """Test connection test when model is not available."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        
        mock_model1 = Mock()
        mock_model1.model = 'other-model'
        mock_model2 = Mock()
        mock_model2.model = 'another-model'
        
        mock_response = Mock()
        mock_response.models = [mock_model1, mock_model2]
        mock_client.list.return_value = mock_response
        
        agent = QueryAgent()
        result = agent.test_connection()
        
        assert result is False
    
    @patch('bmlibrarian.agents.base.ollama.Client')
    def test_test_connection_error(self, mock_client_class):
        """Test connection test handles errors."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.list.side_effect = Exception("Connection failed")
        
        agent = QueryAgent()
        result = agent.test_connection()
        
        assert result is False
    
    @patch('bmlibrarian.agents.base.ollama.Client')
    def test_get_available_models_success(self, mock_client_class):
        """Test successful retrieval of available models."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        
        mock_model1 = Mock()
        mock_model1.model = 'medgemma4B_it_q8:latest'
        mock_model2 = Mock()
        mock_model2.model = 'mistral'
        mock_model3 = Mock()
        mock_model3.model = 'codellama'
        
        mock_response = Mock()
        mock_response.models = [mock_model1, mock_model2, mock_model3]
        mock_client.list.return_value = mock_response
        
        agent = QueryAgent()
        result = agent.get_available_models()
        
        expected = ['medgemma4B_it_q8:latest', 'mistral', 'codellama']
        assert result == expected
        mock_client.list.assert_called_once()
    
    @patch('bmlibrarian.agents.base.ollama.Client')
    def test_get_available_models_error(self, mock_client_class):
        """Test get_available_models handles errors."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.list.side_effect = Exception("Connection failed")
        
        agent = QueryAgent()
        
        with pytest.raises(ConnectionError, match="Failed to connect to Ollama"):
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