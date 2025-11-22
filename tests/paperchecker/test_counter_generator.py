"""
Unit tests for CounterStatementGenerator component.

Tests cover:
    1. Initialization and configuration
    2. Input validation
    3. Prompt construction for semantic negation
    4. Response parsing and cleaning
    5. Retry logic
    6. Error handling
"""

import pytest
from unittest.mock import MagicMock, patch

from bmlibrarian.paperchecker.components.counter_statement_generator import (
    CounterStatementGenerator,
    DEFAULT_TEMPERATURE,
    DEFAULT_OLLAMA_URL,
    DEFAULT_MAX_RETRIES,
    DEFAULT_RETRY_DELAY_SECONDS,
    MIN_COUNTER_STATEMENT_LENGTH,
)
from bmlibrarian.paperchecker.data_models import Statement


# ==================== INITIALIZATION TESTS ====================

class TestCounterGeneratorInit:
    """Test CounterStatementGenerator initialization."""

    @patch('bmlibrarian.paperchecker.components.counter_statement_generator.ollama.Client')
    def test_init_with_defaults(self, mock_client_class: MagicMock) -> None:
        """Test initialization with default parameters."""
        generator = CounterStatementGenerator(model="test-model")

        assert generator.model == "test-model"
        assert generator.temperature == DEFAULT_TEMPERATURE
        assert generator.host == DEFAULT_OLLAMA_URL
        mock_client_class.assert_called_once_with(host=DEFAULT_OLLAMA_URL)

    @patch('bmlibrarian.paperchecker.components.counter_statement_generator.ollama.Client')
    def test_init_with_custom_parameters(self, mock_client_class: MagicMock) -> None:
        """Test initialization with custom parameters."""
        generator = CounterStatementGenerator(
            model="custom-model:7b",
            temperature=0.5,
            host="http://custom-host:11434"
        )

        assert generator.model == "custom-model:7b"
        assert generator.temperature == 0.5
        assert generator.host == "http://custom-host:11434"

    @patch('bmlibrarian.paperchecker.components.counter_statement_generator.ollama.Client')
    def test_init_strips_trailing_slash(self, mock_client_class: MagicMock) -> None:
        """Test that trailing slash is stripped from host URL."""
        generator = CounterStatementGenerator(
            model="test-model",
            host="http://localhost:11434/"
        )

        assert generator.host == "http://localhost:11434"


# ==================== CONSTANTS TESTS ====================

class TestCounterGeneratorConstants:
    """Test module constants are properly defined."""

    def test_temperature_in_range(self) -> None:
        """Test DEFAULT_TEMPERATURE is in valid range."""
        assert 0.0 <= DEFAULT_TEMPERATURE <= 1.0

    def test_min_length_reasonable(self) -> None:
        """Test MIN_COUNTER_STATEMENT_LENGTH is reasonable."""
        assert MIN_COUNTER_STATEMENT_LENGTH >= 5
        assert MIN_COUNTER_STATEMENT_LENGTH <= 100

    def test_retry_constants_positive(self) -> None:
        """Test retry constants are positive."""
        assert DEFAULT_MAX_RETRIES > 0
        assert DEFAULT_RETRY_DELAY_SECONDS > 0


# ==================== INPUT VALIDATION TESTS ====================

class TestInputValidation:
    """Test input validation for generate method."""

    @patch('bmlibrarian.paperchecker.components.counter_statement_generator.ollama.Client')
    def test_generate_raises_on_empty_statement_text(
        self,
        mock_client_class: MagicMock,
        sample_statement: Statement
    ) -> None:
        """Test that empty statement text raises ValueError."""
        generator = CounterStatementGenerator(model="test-model")

        # Create a statement with empty text
        empty_stmt = Statement(
            text="",
            context="Some context",
            statement_type="finding",
            confidence=0.8,
            statement_order=1
        )

        with pytest.raises(ValueError, match="cannot be empty"):
            generator.generate(empty_stmt)

    @patch('bmlibrarian.paperchecker.components.counter_statement_generator.ollama.Client')
    def test_generate_raises_on_whitespace_statement(
        self,
        mock_client_class: MagicMock
    ) -> None:
        """Test that whitespace-only statement raises ValueError."""
        generator = CounterStatementGenerator(model="test-model")

        whitespace_stmt = Statement(
            text="   ",
            context="Some context",
            statement_type="finding",
            confidence=0.8,
            statement_order=1
        )

        with pytest.raises(ValueError, match="cannot be empty"):
            generator.generate(whitespace_stmt)


# ==================== PROMPT CONSTRUCTION TESTS ====================

class TestPromptConstruction:
    """Test prompt building for counter-statement generation."""

    @patch('bmlibrarian.paperchecker.components.counter_statement_generator.ollama.Client')
    def test_prompt_contains_statement_text(
        self,
        mock_client_class: MagicMock,
        sample_statement: Statement
    ) -> None:
        """Test that prompt contains the original statement text."""
        generator = CounterStatementGenerator(model="test-model")

        prompt = generator._build_negation_prompt(sample_statement)

        assert sample_statement.text in prompt

    @patch('bmlibrarian.paperchecker.components.counter_statement_generator.ollama.Client')
    def test_prompt_contains_statement_type(
        self,
        mock_client_class: MagicMock,
        sample_statement: Statement
    ) -> None:
        """Test that prompt includes statement type."""
        generator = CounterStatementGenerator(model="test-model")

        prompt = generator._build_negation_prompt(sample_statement)

        assert sample_statement.statement_type in prompt

    @patch('bmlibrarian.paperchecker.components.counter_statement_generator.ollama.Client')
    def test_prompt_includes_negation_examples(
        self,
        mock_client_class: MagicMock,
        sample_statement: Statement
    ) -> None:
        """Test that prompt includes negation examples."""
        generator = CounterStatementGenerator(model="test-model")

        prompt = generator._build_negation_prompt(sample_statement)

        assert "Example" in prompt or "example" in prompt
        assert "Negation" in prompt or "negation" in prompt

    @patch('bmlibrarian.paperchecker.components.counter_statement_generator.ollama.Client')
    def test_prompt_includes_context_when_present(
        self,
        mock_client_class: MagicMock,
        sample_statement: Statement
    ) -> None:
        """Test that context is included when present."""
        generator = CounterStatementGenerator(model="test-model")

        prompt = generator._build_negation_prompt(sample_statement)

        assert sample_statement.context in prompt or "Context" in prompt


# ==================== RESPONSE PARSING TESTS ====================

class TestResponseParsing:
    """Test response parsing and cleaning."""

    @patch('bmlibrarian.paperchecker.components.counter_statement_generator.ollama.Client')
    def test_parse_clean_response(self, mock_client_class: MagicMock) -> None:
        """Test parsing a clean response."""
        generator = CounterStatementGenerator(model="test-model")

        result = generator._parse_response("This is a valid counter-statement.")

        assert result == "This is a valid counter-statement."

    @patch('bmlibrarian.paperchecker.components.counter_statement_generator.ollama.Client')
    def test_parse_removes_common_prefixes(
        self,
        mock_client_class: MagicMock
    ) -> None:
        """Test that common prefixes are removed."""
        generator = CounterStatementGenerator(model="test-model")

        prefixes_to_test = [
            "Counter-statement: The actual counter-statement here.",
            "Negation: The actual counter-statement here.",
            "The negated statement is: The actual counter-statement here.",
        ]

        for prefixed in prefixes_to_test:
            result = generator._parse_response(prefixed)
            assert "actual counter-statement" in result.lower() or "counter-statement here" in result.lower()

    @patch('bmlibrarian.paperchecker.components.counter_statement_generator.ollama.Client')
    def test_parse_removes_quotes(self, mock_client_class: MagicMock) -> None:
        """Test that surrounding quotes are removed."""
        generator = CounterStatementGenerator(model="test-model")

        result = generator._parse_response('"This is a quoted counter-statement."')
        assert result == "This is a quoted counter-statement."

        result = generator._parse_response("'This is a single-quoted statement.'")
        assert result == "This is a single-quoted statement."

    @patch('bmlibrarian.paperchecker.components.counter_statement_generator.ollama.Client')
    def test_parse_removes_leading_dash(self, mock_client_class: MagicMock) -> None:
        """Test that leading dash/bullet is removed."""
        generator = CounterStatementGenerator(model="test-model")

        result = generator._parse_response("- This is a bulleted statement.")
        assert result == "This is a bulleted statement."

    @patch('bmlibrarian.paperchecker.components.counter_statement_generator.ollama.Client')
    def test_parse_raises_on_too_short_response(
        self,
        mock_client_class: MagicMock
    ) -> None:
        """Test that too-short response raises ValueError."""
        generator = CounterStatementGenerator(model="test-model")

        short_text = "A" * (MIN_COUNTER_STATEMENT_LENGTH - 1)

        with pytest.raises(ValueError, match="too short"):
            generator._parse_response(short_text)

    @patch('bmlibrarian.paperchecker.components.counter_statement_generator.ollama.Client')
    def test_parse_raises_on_empty_response(
        self,
        mock_client_class: MagicMock
    ) -> None:
        """Test that empty response raises ValueError."""
        generator = CounterStatementGenerator(model="test-model")

        with pytest.raises(ValueError, match="too short"):
            generator._parse_response("")


# ==================== LLM CALL TESTS ====================

class TestLLMCall:
    """Test LLM API call functionality."""

    @patch('bmlibrarian.paperchecker.components.counter_statement_generator.ollama.Client')
    def test_call_llm_success(self, mock_client_class: MagicMock) -> None:
        """Test successful LLM call."""
        mock_client = MagicMock()
        mock_client.chat.return_value = {
            "message": {"content": "Generated counter-statement text."}
        }
        mock_client_class.return_value = mock_client

        generator = CounterStatementGenerator(model="test-model")
        result = generator._call_llm("test prompt")

        assert result == "Generated counter-statement text."
        mock_client.chat.assert_called_once()

    @patch('bmlibrarian.paperchecker.components.counter_statement_generator.ollama.Client')
    @patch('bmlibrarian.paperchecker.components.counter_statement_generator.time.sleep')
    def test_call_llm_retries_on_empty_response(
        self,
        mock_sleep: MagicMock,
        mock_client_class: MagicMock
    ) -> None:
        """Test that empty responses trigger retry."""
        mock_client = MagicMock()
        mock_client.chat.side_effect = [
            {"message": {"content": ""}},
            {"message": {"content": "Valid counter-statement response."}}
        ]
        mock_client_class.return_value = mock_client

        generator = CounterStatementGenerator(model="test-model")
        result = generator._call_llm("test prompt", max_retries=3)

        assert result == "Valid counter-statement response."
        assert mock_client.chat.call_count == 2

    @patch('bmlibrarian.paperchecker.components.counter_statement_generator.ollama.Client')
    @patch('bmlibrarian.paperchecker.components.counter_statement_generator.time.sleep')
    def test_call_llm_raises_after_max_retries(
        self,
        mock_sleep: MagicMock,
        mock_client_class: MagicMock
    ) -> None:
        """Test that RuntimeError is raised after max retries."""
        mock_client = MagicMock()
        mock_client.chat.side_effect = [
            {"message": {"content": ""}},
            {"message": {"content": ""}},
            {"message": {"content": ""}}
        ]
        mock_client_class.return_value = mock_client

        generator = CounterStatementGenerator(model="test-model")

        with pytest.raises(RuntimeError, match="Failed to get response"):
            generator._call_llm("test prompt", max_retries=3)


# ==================== CONNECTION TEST ====================

class TestConnectionTest:
    """Test connection testing functionality."""

    @patch('bmlibrarian.paperchecker.components.counter_statement_generator.ollama.Client')
    def test_test_connection_success(self, mock_client_class: MagicMock) -> None:
        """Test successful connection test."""
        mock_client = MagicMock()
        mock_client.list.return_value = {"models": []}
        mock_client_class.return_value = mock_client

        generator = CounterStatementGenerator(model="test-model")
        result = generator.test_connection()

        assert result is True

    @patch('bmlibrarian.paperchecker.components.counter_statement_generator.ollama.Client')
    def test_test_connection_failure(self, mock_client_class: MagicMock) -> None:
        """Test failed connection test."""
        mock_client = MagicMock()
        mock_client.list.side_effect = Exception("Connection refused")
        mock_client_class.return_value = mock_client

        generator = CounterStatementGenerator(model="test-model")
        result = generator.test_connection()

        assert result is False


# ==================== INTEGRATION TESTS ====================

class TestGenerateIntegration:
    """Integration tests for the generate method."""

    @patch('bmlibrarian.paperchecker.components.counter_statement_generator.ollama.Client')
    def test_generate_full_workflow(
        self,
        mock_client_class: MagicMock,
        sample_statement: Statement,
        counter_statement_response: str
    ) -> None:
        """Test complete generation workflow."""
        mock_client = MagicMock()
        mock_client.chat.return_value = {
            "message": {"content": counter_statement_response}
        }
        mock_client_class.return_value = mock_client

        generator = CounterStatementGenerator(model="test-model")
        result = generator.generate(sample_statement)

        assert len(result) >= MIN_COUNTER_STATEMENT_LENGTH
        assert isinstance(result, str)

    @patch('bmlibrarian.paperchecker.components.counter_statement_generator.ollama.Client')
    def test_generate_wraps_llm_errors(
        self,
        mock_client_class: MagicMock,
        sample_statement: Statement
    ) -> None:
        """Test that LLM errors are wrapped in RuntimeError."""
        mock_client = MagicMock()
        mock_client.chat.side_effect = Exception("Network error")
        mock_client_class.return_value = mock_client

        generator = CounterStatementGenerator(model="test-model")

        with pytest.raises(RuntimeError, match="Failed to generate"):
            generator.generate(sample_statement)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
