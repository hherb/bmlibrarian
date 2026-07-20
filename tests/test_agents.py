"""
Unit tests for BMLibrarian agents module.

Tests the BaseAgent, QueryAgent, and DocumentScoringAgent classes
with mocked LLM responses to ensure functionality without requiring
a running LLM server.
"""

import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from datetime import date

from bmlib.llm import LLMResponse as BmlibResponse

from bmlibrarian.agents import BaseAgent, QueryAgent, DocumentScoringAgent
from bmlibrarian.agents.scoring_agent import ScoringResult
from bmlibrarian.llm import LLMClient


class TestBaseAgent:
    """Test the BaseAgent base class functionality."""

    def test_abstract_methods(self):
        """Test that BaseAgent cannot be instantiated due to abstract methods."""
        with pytest.raises(TypeError):
            BaseAgent("test-model")

    @patch('bmlib.llm.client.LLMClient.chat')
    def test_initialization(self, mock_chat):
        """Test BaseAgent initialization with custom parameters."""

        # Create a concrete implementation for testing
        class TestAgent(BaseAgent):
            def get_agent_type(self):
                return "test_agent"

        agent = TestAgent(
            model="test-model",
            host="http://test:8080",
            temperature=0.5,
            top_p=0.8
        )

        assert agent.model == "test-model"
        assert agent.host == "http://test:8080"
        assert agent.temperature == 0.5
        assert agent.top_p == 0.8
        # The host must reach the client, not merely be recorded on the agent
        assert agent.client.ollama_host == "http://test:8080"
        assert isinstance(agent.client, LLMClient)

    @patch('bmlib.llm.client.LLMClient.chat')
    def test_callback_functionality(self, mock_chat):
        """Test callback system."""

        class TestAgent(BaseAgent):
            def get_agent_type(self):
                return "test_agent"

        callback_mock = Mock()
        agent = TestAgent("test-model", callback=callback_mock)

        # Test callback is called
        agent._call_callback("test_step", "test_data")
        callback_mock.assert_called_once_with("test_step", "test_data")

        # Test callback error handling
        callback_mock.side_effect = Exception("Callback error")
        agent._call_callback("test_step", "test_data")  # Should not raise


class TestQueryAgent:
    """Test the QueryAgent specialized class."""

    @patch('bmlib.llm.client.LLMClient.chat')
    def test_initialization(self, mock_chat):
        """Test QueryAgent initialization with defaults."""
        agent = QueryAgent()

        assert agent.model == "medgemma4B_it_q8:latest"
        assert agent.host == "http://localhost:11434"
        assert agent.temperature == 0.1
        assert agent.get_agent_type() == "query_agent"

    @patch('bmlib.llm.client.LLMClient.chat')
    def test_convert_question_success(self, mock_chat):
        """Test successful question conversion."""
        # Mock bmlib response
        mock_chat.return_value = BmlibResponse(
            content='aspirin & (cardiovascular | cardiac) & disease',
            model="test",
            input_tokens=10,
            output_tokens=5
        )

        agent = QueryAgent()
        result = agent.convert_question("Effects of aspirin on heart disease")

        # After query post-processing (clean_quotes, fix_malformed_syntax),
        # spaces around the operators are normalized by fix_tsquery_syntax
        assert result == "aspirin&(cardiovascular|cardiac)&disease"

    @patch('bmlib.llm.client.LLMClient.chat')
    def test_convert_question_empty(self, mock_chat):
        """Test conversion with empty question."""
        agent = QueryAgent()

        with pytest.raises(ValueError, match="Question cannot be empty"):
            agent.convert_question("")

        with pytest.raises(ValueError, match="Question cannot be empty"):
            agent.convert_question("   ")

    @patch('bmlib.llm.client.LLMClient.chat')
    def test_clean_quotes(self, mock_chat):
        """Test quote cleaning functionality."""
        agent = QueryAgent()

        # Test surrounding quote removal and phrase quoting
        assert agent._clean_quotes('"test query"') == "'test query'"
        assert agent._clean_quotes("'test query'") == "'test query'"

        # Test multi-word phrase quoting
        assert agent._clean_quotes("myocardial infarction") == "'myocardial infarction'"
        assert agent._clean_quotes("covid vaccine effectiveness") == "'covid vaccine effectiveness'"

        # Test apostrophe escaping within phrases
        assert agent._clean_quotes("Alzheimer's disease") == "'Alzheimer''s disease'"

        # Test the problematic case from the error report
        problematic_query = '"\'type 2 diabetes\'" & ("treatment" | "management" | "therapy") & ("medication" | "drug" | "insulin" | "\'oral agent\'")"'
        expected_clean = "'type 2 diabetes' & (treatment | management | therapy) & (medication | drug | insulin | 'oral agent')"
        assert agent._clean_quotes(problematic_query) == expected_clean

    def test_validate_tsquery(self):
        """Test tsquery validation."""
        agent = QueryAgent.__new__(QueryAgent)  # Create without __init__

        # Valid queries
        assert agent._validate_tsquery("aspirin & heart") == True
        assert agent._validate_tsquery("(covid | coronavirus) & vaccine") == True

        # Invalid queries
        assert agent._validate_tsquery("") == False
        assert agent._validate_tsquery("aspirin && heart") == False  # Invalid operator
        assert agent._validate_tsquery("(unbalanced parens") == False

    @patch('bmlibrarian.agents.query_agent.search_hybrid')
    @patch('bmlib.llm.client.LLMClient.chat')
    def test_find_abstracts(self, mock_chat, mock_search_hybrid):
        """Test find_abstracts method.

        find_abstracts() retrieves via search_hybrid(), not the legacy
        database.find_abstracts(). Patching the wrong target lets the real
        hybrid search run against the production database.
        """
        # Mock bmlib response
        mock_chat.return_value = BmlibResponse(
            content='covid & vaccine',
            model="test",
            input_tokens=10,
            output_tokens=5
        )

        # Mock database results — search_hybrid returns (documents, metadata)
        mock_docs = [
            {'title': 'Test Document 1', 'abstract': 'Test abstract 1'},
            {'title': 'Test Document 2', 'abstract': 'Test abstract 2'}
        ]
        mock_search_hybrid.return_value = (mock_docs, {'strategies_used': ['bm25']})

        agent = QueryAgent()
        results = list(agent.find_abstracts("COVID vaccine effectiveness"))

        assert len(results) == 2
        assert results[0]['title'] == 'Test Document 1'

        # Verify the search function was called with both the original question
        # (for semantic search) and the generated tsquery (for BM25/fulltext).
        mock_search_hybrid.assert_called_once()
        call_kwargs = mock_search_hybrid.call_args[1]
        assert call_kwargs['search_text'] == "COVID vaccine effectiveness"
        assert 'covid' in call_kwargs['query_text'].lower()


class TestDocumentScoringAgent:
    """Test the DocumentScoringAgent specialized class."""

    @patch('bmlib.llm.client.LLMClient.chat')
    def test_initialization(self, mock_chat):
        """Test DocumentScoringAgent initialization."""
        agent = DocumentScoringAgent()

        assert agent.model == "gpt-oss:20b"
        assert agent.get_agent_type() == "document_scoring_agent"

    @patch('bmlib.llm.client.LLMClient.chat')
    def test_evaluate_document_success(self, mock_chat):
        """Test successful document evaluation."""
        # Mock bmlib response with valid JSON
        mock_chat.return_value = BmlibResponse(
            content=json.dumps({
                "score": 4,
                "reasoning": "Document addresses COVID vaccine effectiveness with clinical data."
            }),
            model="test",
            input_tokens=10,
            output_tokens=5
        )

        agent = DocumentScoringAgent()

        document = {
            'title': 'COVID-19 Vaccine Efficacy Study',
            'abstract': 'This study evaluates vaccine effectiveness...',
            'authors': ['Smith, J.', 'Doe, A.'],
            'publication_date': '2021-06-15'
        }

        result = agent.evaluate_document("How effective are COVID vaccines?", document)

        assert isinstance(result, dict)
        assert result['score'] == 4
        assert "clinical data" in result['reasoning']
        assert 0 <= result['score'] <= 5

    @patch('bmlib.llm.client.LLMClient.chat')
    def test_evaluate_document_invalid_inputs(self, mock_chat):
        """Test document evaluation with invalid inputs."""
        agent = DocumentScoringAgent()

        # Test empty question
        with pytest.raises(ValueError, match="User question cannot be empty"):
            agent.evaluate_document("", {'title': 'Test', 'abstract': 'Test'})

        # Test invalid document
        with pytest.raises(ValueError, match="Document must be a non-empty dictionary"):
            agent.evaluate_document("Test question", None)

        # Test missing title
        with pytest.raises(ValueError, match="Document must contain 'title' field"):
            agent.evaluate_document("Test question", {'abstract': 'Test'})

    @patch('bmlib.llm.client.LLMClient.chat')
    def test_evaluate_document_invalid_json(self, mock_chat):
        """Test handling of invalid JSON response."""
        mock_chat.return_value = BmlibResponse(
            content='Invalid JSON response',
            model="test",
            input_tokens=10,
            output_tokens=5
        )

        agent = DocumentScoringAgent()
        document = {'title': 'Test', 'abstract': 'Test'}

        with pytest.raises(ValueError, match="Model returned invalid JSON"):
            agent.evaluate_document("Test question", document)

    @patch('bmlib.llm.client.LLMClient.chat')
    def test_batch_evaluate_documents(self, mock_chat):
        """Test batch evaluation of multiple documents."""
        # Mock bmlib responses
        mock_chat.side_effect = [
            BmlibResponse(content=json.dumps({"score": 4, "reasoning": "Good match"}), model="test", input_tokens=10, output_tokens=5),
            BmlibResponse(content=json.dumps({"score": 2, "reasoning": "Partial match"}), model="test", input_tokens=10, output_tokens=5),
            BmlibResponse(content=json.dumps({"score": 5, "reasoning": "Perfect match"}), model="test", input_tokens=10, output_tokens=5),
        ]

        agent = DocumentScoringAgent()

        documents = [
            {'title': 'Doc 1', 'abstract': 'Abstract 1'},
            {'title': 'Doc 2', 'abstract': 'Abstract 2'},
            {'title': 'Doc 3', 'abstract': 'Abstract 3'}
        ]

        results = agent.batch_evaluate_documents("Test question", documents)

        assert len(results) == 3
        assert results[0][1]['score'] == 4
        assert results[1][1]['score'] == 2
        assert results[2][1]['score'] == 5

    @patch('bmlib.llm.client.LLMClient.chat')
    def test_get_top_documents(self, mock_chat):
        """Test getting top-k documents based on scores."""
        # Mock responses with varying scores
        mock_chat.side_effect = [
            BmlibResponse(content=json.dumps({"score": 1, "reasoning": "Low relevance"}), model="test", input_tokens=10, output_tokens=5),
            BmlibResponse(content=json.dumps({"score": 4, "reasoning": "High relevance"}), model="test", input_tokens=10, output_tokens=5),
            BmlibResponse(content=json.dumps({"score": 3, "reasoning": "Medium relevance"}), model="test", input_tokens=10, output_tokens=5),
            BmlibResponse(content=json.dumps({"score": 5, "reasoning": "Perfect match"}), model="test", input_tokens=10, output_tokens=5),
        ]

        agent = DocumentScoringAgent()

        documents = [
            {'title': 'Low Doc', 'abstract': 'Low relevance'},
            {'title': 'High Doc', 'abstract': 'High relevance'},
            {'title': 'Medium Doc', 'abstract': 'Medium relevance'},
            {'title': 'Perfect Doc', 'abstract': 'Perfect match'}
        ]

        # Get top 2 documents with min_score=2
        top_docs = agent.get_top_documents("Test question", documents, top_k=2, min_score=2)

        # Should return Perfect Doc (score 5) and High Doc (score 4)
        assert len(top_docs) == 2
        assert top_docs[0][0]['title'] == 'Perfect Doc'  # Highest score first
        assert top_docs[0][1]['score'] == 5
        assert top_docs[1][0]['title'] == 'High Doc'
        assert top_docs[1][1]['score'] == 4

    @patch('bmlib.llm.client.LLMClient.chat')
    def test_fallback_parsing(self, mock_chat):
        """Test fallback parsing for malformed JSON responses."""
        # Mock malformed JSON responses that should trigger fallbacks.
        # Note: The scoring agent has internal retry logic for incomplete responses,
        # so responses must pass the completeness check (contain '"score"' or end with '}')
        # to avoid consuming extra mock responses via retries.
        mock_chat.side_effect = [
            BmlibResponse(content='{\n    "score": 3,\n    "reasoning": "Partial match', model="test", input_tokens=10, output_tokens=5),
            BmlibResponse(content='{ "score": 4, "reasoning": "Good response" }', model="test", input_tokens=10, output_tokens=5),
            BmlibResponse(content='"score": 2, reasoning: Basic relevance}', model="test", input_tokens=10, output_tokens=5),
        ]

        agent = DocumentScoringAgent()
        document = {'title': 'Test Doc', 'abstract': 'Test abstract'}

        # Test incomplete JSON - should use fallback
        result1 = agent.evaluate_document("Test question", document)
        assert result1['score'] == 3
        assert result1['reasoning'] in ["Partial match", "Score extracted from malformed response"]

        # Test valid JSON - should work normally
        result2 = agent.evaluate_document("Test question", document)
        assert result2['score'] == 4
        assert result2['reasoning'] == "Good response"

        # Test non-JSON format - should use fallback
        result3 = agent.evaluate_document("Test question", document)
        assert result3['score'] == 2
        assert "Basic relevance" in result3['reasoning'] or "malformed response" in result3['reasoning']


# Backward compatibility tests removed since agent.py was removed


if __name__ == "__main__":
    pytest.main([__file__])
