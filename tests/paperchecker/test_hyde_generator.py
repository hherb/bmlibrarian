"""
Unit tests for HyDEGenerator component.

Tests cover:
    1. Initialization and configuration
    2. Input validation
    3. Prompt construction for hypothetical abstracts
    4. JSON response parsing
    5. Abstract and keyword validation
    6. Error handling
"""

import json
import pytest
from unittest.mock import MagicMock, patch

from bmlibrarian.paperchecker.components.hyde_generator import (
    HyDEGenerator,
    DEFAULT_NUM_ABSTRACTS,
    DEFAULT_MAX_KEYWORDS,
    DEFAULT_TEMPERATURE,
    DEFAULT_OLLAMA_URL,
    MIN_ABSTRACT_LENGTH,
)
from bmlibrarian.paperchecker.data_models import Statement


# ==================== INITIALIZATION TESTS ====================

class TestHyDEGeneratorInit:
    """Test HyDEGenerator initialization."""

    @patch('bmlibrarian.paperchecker.components.hyde_generator.ollama.Client')
    def test_init_with_defaults(self, mock_client_class: MagicMock) -> None:
        """Test initialization with default parameters."""
        generator = HyDEGenerator(model="test-model")

        assert generator.model == "test-model"
        assert generator.num_abstracts == DEFAULT_NUM_ABSTRACTS
        assert generator.max_keywords == DEFAULT_MAX_KEYWORDS
        assert generator.temperature == DEFAULT_TEMPERATURE
        assert generator.host == DEFAULT_OLLAMA_URL

    @patch('bmlibrarian.paperchecker.components.hyde_generator.ollama.Client')
    def test_init_with_custom_parameters(self, mock_client_class: MagicMock) -> None:
        """Test initialization with custom parameters."""
        generator = HyDEGenerator(
            model="custom-model",
            num_abstracts=5,
            max_keywords=15,
            temperature=0.7,
            host="http://custom-host:11434"
        )

        assert generator.model == "custom-model"
        assert generator.num_abstracts == 5
        assert generator.max_keywords == 15
        assert generator.temperature == 0.7


# ==================== CONSTANTS TESTS ====================

class TestHyDEGeneratorConstants:
    """Test module constants are properly defined."""

    def test_default_num_abstracts_positive(self) -> None:
        """Test DEFAULT_NUM_ABSTRACTS is positive."""
        assert DEFAULT_NUM_ABSTRACTS > 0

    def test_default_max_keywords_positive(self) -> None:
        """Test DEFAULT_MAX_KEYWORDS is positive."""
        assert DEFAULT_MAX_KEYWORDS > 0

    def test_min_abstract_length_reasonable(self) -> None:
        """Test MIN_ABSTRACT_LENGTH is reasonable."""
        assert MIN_ABSTRACT_LENGTH >= 50
        assert MIN_ABSTRACT_LENGTH <= 500


# ==================== INPUT VALIDATION TESTS ====================

class TestInputValidation:
    """Test input validation for generate method."""

    @patch('bmlibrarian.paperchecker.components.hyde_generator.ollama.Client')
    def test_generate_raises_on_empty_counter_text(
        self,
        mock_client_class: MagicMock,
        sample_statement: Statement
    ) -> None:
        """Test that empty counter text raises ValueError."""
        generator = HyDEGenerator(model="test-model")

        with pytest.raises(ValueError, match="cannot be empty"):
            generator.generate(sample_statement, "")

    @patch('bmlibrarian.paperchecker.components.hyde_generator.ollama.Client')
    def test_generate_raises_on_whitespace_counter_text(
        self,
        mock_client_class: MagicMock,
        sample_statement: Statement
    ) -> None:
        """Test that whitespace-only counter text raises ValueError."""
        generator = HyDEGenerator(model="test-model")

        with pytest.raises(ValueError, match="cannot be empty"):
            generator.generate(sample_statement, "   \n\t  ")


# ==================== PROMPT CONSTRUCTION TESTS ====================

class TestPromptConstruction:
    """Test prompt building for HyDE generation."""

    @patch('bmlibrarian.paperchecker.components.hyde_generator.ollama.Client')
    def test_prompt_contains_original_statement(
        self,
        mock_client_class: MagicMock,
        sample_statement: Statement
    ) -> None:
        """Test that prompt contains original statement."""
        generator = HyDEGenerator(model="test-model")
        counter_text = "Test counter-statement"

        prompt = generator._build_hyde_prompt(sample_statement, counter_text)

        assert sample_statement.text in prompt

    @patch('bmlibrarian.paperchecker.components.hyde_generator.ollama.Client')
    def test_prompt_contains_counter_statement(
        self,
        mock_client_class: MagicMock,
        sample_statement: Statement
    ) -> None:
        """Test that prompt contains counter-statement."""
        generator = HyDEGenerator(model="test-model")
        counter_text = "Test counter-statement for the prompt"

        prompt = generator._build_hyde_prompt(sample_statement, counter_text)

        assert counter_text in prompt

    @patch('bmlibrarian.paperchecker.components.hyde_generator.ollama.Client')
    def test_prompt_specifies_num_abstracts(
        self,
        mock_client_class: MagicMock,
        sample_statement: Statement
    ) -> None:
        """Test that prompt specifies number of abstracts."""
        generator = HyDEGenerator(model="test-model", num_abstracts=3)

        prompt = generator._build_hyde_prompt(sample_statement, "counter")

        assert "3" in prompt

    @patch('bmlibrarian.paperchecker.components.hyde_generator.ollama.Client')
    def test_prompt_specifies_max_keywords(
        self,
        mock_client_class: MagicMock,
        sample_statement: Statement
    ) -> None:
        """Test that prompt specifies max keywords."""
        generator = HyDEGenerator(model="test-model", max_keywords=12)

        prompt = generator._build_hyde_prompt(sample_statement, "counter")

        assert "12" in prompt

    @patch('bmlibrarian.paperchecker.components.hyde_generator.ollama.Client')
    def test_prompt_requests_json_format(
        self,
        mock_client_class: MagicMock,
        sample_statement: Statement
    ) -> None:
        """Test that prompt requests JSON output format."""
        generator = HyDEGenerator(model="test-model")

        prompt = generator._build_hyde_prompt(sample_statement, "counter")

        assert "JSON" in prompt
        assert "hyde_abstracts" in prompt
        assert "keywords" in prompt


# ==================== RESPONSE PARSING TESTS ====================

class TestResponseParsing:
    """Test HyDE response parsing."""

    @patch('bmlibrarian.paperchecker.components.hyde_generator.ollama.Client')
    def test_parse_valid_response(
        self,
        mock_client_class: MagicMock,
        hyde_generation_response: str
    ) -> None:
        """Test parsing a valid JSON response."""
        generator = HyDEGenerator(model="test-model")

        result = generator._parse_response(hyde_generation_response)

        assert "hyde_abstracts" in result
        assert "keywords" in result
        assert len(result["hyde_abstracts"]) > 0
        assert len(result["keywords"]) > 0

    @patch('bmlibrarian.paperchecker.components.hyde_generator.ollama.Client')
    def test_parse_raises_on_missing_hyde_abstracts(
        self,
        mock_client_class: MagicMock
    ) -> None:
        """Test that missing hyde_abstracts raises ValueError."""
        generator = HyDEGenerator(model="test-model")
        response = json.dumps({"keywords": ["test"]})

        with pytest.raises(ValueError, match="hyde_abstracts"):
            generator._parse_response(response)

    @patch('bmlibrarian.paperchecker.components.hyde_generator.ollama.Client')
    def test_parse_raises_on_missing_keywords(
        self,
        mock_client_class: MagicMock
    ) -> None:
        """Test that missing keywords raises ValueError."""
        generator = HyDEGenerator(model="test-model")
        response = json.dumps({"hyde_abstracts": ["test abstract " * 20]})

        with pytest.raises(ValueError, match="keywords"):
            generator._parse_response(response)

    @patch('bmlibrarian.paperchecker.components.hyde_generator.ollama.Client')
    def test_parse_filters_short_abstracts(
        self,
        mock_client_class: MagicMock
    ) -> None:
        """Test that abstracts below MIN_ABSTRACT_LENGTH are filtered."""
        generator = HyDEGenerator(model="test-model")
        response = json.dumps({
            "hyde_abstracts": [
                "Too short",
                "A" * MIN_ABSTRACT_LENGTH + " valid abstract"
            ],
            "keywords": ["test keyword"]
        })

        result = generator._parse_response(response)

        assert len(result["hyde_abstracts"]) == 1
        assert "valid abstract" in result["hyde_abstracts"][0]

    @patch('bmlibrarian.paperchecker.components.hyde_generator.ollama.Client')
    def test_parse_respects_max_limits(
        self,
        mock_client_class: MagicMock
    ) -> None:
        """Test that parsing respects num_abstracts and max_keywords limits."""
        generator = HyDEGenerator(
            model="test-model",
            num_abstracts=1,
            max_keywords=2
        )
        response = json.dumps({
            "hyde_abstracts": [
                "A" * MIN_ABSTRACT_LENGTH + " abstract one",
                "B" * MIN_ABSTRACT_LENGTH + " abstract two"
            ],
            "keywords": ["keyword1", "keyword2", "keyword3", "keyword4"]
        })

        result = generator._parse_response(response)

        assert len(result["hyde_abstracts"]) <= 1
        assert len(result["keywords"]) <= 2

    @patch('bmlibrarian.paperchecker.components.hyde_generator.ollama.Client')
    def test_parse_raises_on_no_valid_abstracts(
        self,
        mock_client_class: MagicMock
    ) -> None:
        """Test that no valid abstracts raises ValueError."""
        generator = HyDEGenerator(model="test-model")
        response = json.dumps({
            "hyde_abstracts": ["short", "also short"],
            "keywords": ["test"]
        })

        with pytest.raises(ValueError, match="No valid HyDE"):
            generator._parse_response(response)

    @patch('bmlibrarian.paperchecker.components.hyde_generator.ollama.Client')
    def test_parse_raises_on_no_valid_keywords(
        self,
        mock_client_class: MagicMock
    ) -> None:
        """Test that no valid keywords raises ValueError."""
        generator = HyDEGenerator(model="test-model")
        response = json.dumps({
            "hyde_abstracts": ["A" * MIN_ABSTRACT_LENGTH + " valid"],
            "keywords": ["", "  "]
        })

        with pytest.raises(ValueError, match="No valid keywords"):
            generator._parse_response(response)


# ==================== JSON EXTRACTION TESTS ====================

class TestJsonExtraction:
    """Test JSON extraction from various response formats."""

    @patch('bmlibrarian.paperchecker.components.hyde_generator.ollama.Client')
    def test_extract_json_from_code_block(
        self,
        mock_client_class: MagicMock
    ) -> None:
        """Test extracting JSON from ```json code block."""
        generator = HyDEGenerator(model="test-model")
        response = '''Some text
```json
{"test": "value"}
```
More text'''

        result = generator._extract_json(response)
        assert json.loads(result) == {"test": "value"}

    @patch('bmlibrarian.paperchecker.components.hyde_generator.ollama.Client')
    def test_extract_json_from_raw_response(
        self,
        mock_client_class: MagicMock
    ) -> None:
        """Test extracting JSON when response is raw JSON."""
        generator = HyDEGenerator(model="test-model")
        response = '{"hyde_abstracts": [], "keywords": []}'

        result = generator._extract_json(response)
        data = json.loads(result)
        assert "hyde_abstracts" in data

    @patch('bmlibrarian.paperchecker.components.hyde_generator.ollama.Client')
    def test_extract_json_with_nested_structure(
        self,
        mock_client_class: MagicMock
    ) -> None:
        """Test extracting nested JSON correctly."""
        generator = HyDEGenerator(model="test-model")
        response = 'Here is the result: {"outer": {"inner": ["a", "b"]}} done'

        result = generator._extract_json(response)
        data = json.loads(result)
        assert data["outer"]["inner"] == ["a", "b"]


# ==================== CONNECTION TEST ====================

class TestConnectionTest:
    """Test connection testing functionality."""

    @patch('bmlibrarian.paperchecker.components.hyde_generator.ollama.Client')
    def test_test_connection_success(self, mock_client_class: MagicMock) -> None:
        """Test successful connection test."""
        mock_client = MagicMock()
        mock_client.list.return_value = {"models": []}
        mock_client_class.return_value = mock_client

        generator = HyDEGenerator(model="test-model")
        result = generator.test_connection()

        assert result is True

    @patch('bmlibrarian.paperchecker.components.hyde_generator.ollama.Client')
    def test_test_connection_failure(self, mock_client_class: MagicMock) -> None:
        """Test failed connection test."""
        mock_client = MagicMock()
        mock_client.list.side_effect = Exception("Connection refused")
        mock_client_class.return_value = mock_client

        generator = HyDEGenerator(model="test-model")
        result = generator.test_connection()

        assert result is False


# ==================== INTEGRATION TESTS ====================

class TestGenerateIntegration:
    """Integration tests for the generate method."""

    @patch('bmlibrarian.paperchecker.components.hyde_generator.ollama.Client')
    def test_generate_full_workflow(
        self,
        mock_client_class: MagicMock,
        sample_statement: Statement,
        hyde_generation_response: str
    ) -> None:
        """Test complete generation workflow."""
        mock_client = MagicMock()
        mock_client.chat.return_value = {
            "message": {"content": hyde_generation_response}
        }
        mock_client_class.return_value = mock_client

        generator = HyDEGenerator(model="test-model")
        result = generator.generate(sample_statement, "test counter-statement")

        assert "hyde_abstracts" in result
        assert "keywords" in result
        assert isinstance(result["hyde_abstracts"], list)
        assert isinstance(result["keywords"], list)

    @patch('bmlibrarian.paperchecker.components.hyde_generator.ollama.Client')
    def test_generate_wraps_llm_errors(
        self,
        mock_client_class: MagicMock,
        sample_statement: Statement
    ) -> None:
        """Test that LLM errors are wrapped in RuntimeError."""
        mock_client = MagicMock()
        mock_client.chat.side_effect = Exception("Network error")
        mock_client_class.return_value = mock_client

        generator = HyDEGenerator(model="test-model")

        with pytest.raises(RuntimeError, match="Failed to generate HyDE"):
            generator.generate(sample_statement, "test counter")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
