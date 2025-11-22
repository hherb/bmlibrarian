"""
Unit tests for StatementExtractor component.

Tests cover:
    1. Initialization and configuration
    2. Input validation (empty/short abstracts)
    3. Prompt construction
    4. LLM response parsing (valid JSON, code blocks, edge cases)
    5. Statement type normalization
    6. Retry logic for transient failures
    7. Connection testing
    8. Error handling
"""

import json
import pytest
from typing import Any, Dict
from unittest.mock import MagicMock, patch

from bmlibrarian.paperchecker.components.statement_extractor import (
    StatementExtractor,
    DEFAULT_MAX_STATEMENTS,
    DEFAULT_TEMPERATURE,
    DEFAULT_OLLAMA_URL,
    MIN_ABSTRACT_LENGTH,
    DEFAULT_CONFIDENCE,
    DEFAULT_MAX_RETRIES,
    DEFAULT_RETRY_DELAY_SECONDS,
)
from bmlibrarian.paperchecker.data_models import Statement, VALID_STATEMENT_TYPES


# ==================== INITIALIZATION TESTS ====================

class TestStatementExtractorInit:
    """Test StatementExtractor initialization."""

    @patch('bmlibrarian.paperchecker.components.statement_extractor.ollama.Client')
    def test_init_with_defaults(self, mock_client_class: MagicMock) -> None:
        """Test initialization with default parameters."""
        extractor = StatementExtractor(model="test-model")

        assert extractor.model == "test-model"
        assert extractor.max_statements == DEFAULT_MAX_STATEMENTS
        assert extractor.temperature == DEFAULT_TEMPERATURE
        assert extractor.host == DEFAULT_OLLAMA_URL
        mock_client_class.assert_called_once_with(host=DEFAULT_OLLAMA_URL)

    @patch('bmlibrarian.paperchecker.components.statement_extractor.ollama.Client')
    def test_init_with_custom_parameters(self, mock_client_class: MagicMock) -> None:
        """Test initialization with custom parameters."""
        extractor = StatementExtractor(
            model="custom-model:7b",
            max_statements=5,
            temperature=0.7,
            host="http://custom-host:11434"
        )

        assert extractor.model == "custom-model:7b"
        assert extractor.max_statements == 5
        assert extractor.temperature == 0.7
        assert extractor.host == "http://custom-host:11434"

    @patch('bmlibrarian.paperchecker.components.statement_extractor.ollama.Client')
    def test_init_strips_trailing_slash_from_host(
        self,
        mock_client_class: MagicMock
    ) -> None:
        """Test that trailing slash is stripped from host URL."""
        extractor = StatementExtractor(
            model="test-model",
            host="http://localhost:11434/"
        )

        assert extractor.host == "http://localhost:11434"


# ==================== CONSTANTS TESTS ====================

class TestStatementExtractorConstants:
    """Test module constants are properly defined."""

    def test_default_max_statements_positive(self) -> None:
        """Test DEFAULT_MAX_STATEMENTS is positive."""
        assert DEFAULT_MAX_STATEMENTS > 0

    def test_default_temperature_in_range(self) -> None:
        """Test DEFAULT_TEMPERATURE is in valid range."""
        assert 0.0 <= DEFAULT_TEMPERATURE <= 1.0

    def test_min_abstract_length_reasonable(self) -> None:
        """Test MIN_ABSTRACT_LENGTH is reasonable."""
        assert MIN_ABSTRACT_LENGTH >= 10
        assert MIN_ABSTRACT_LENGTH <= 200

    def test_default_confidence_in_range(self) -> None:
        """Test DEFAULT_CONFIDENCE is in valid range."""
        assert 0.0 <= DEFAULT_CONFIDENCE <= 1.0

    def test_retry_constants_positive(self) -> None:
        """Test retry constants are positive."""
        assert DEFAULT_MAX_RETRIES > 0
        assert DEFAULT_RETRY_DELAY_SECONDS > 0


# ==================== INPUT VALIDATION TESTS ====================

class TestInputValidation:
    """Test input validation for extract method."""

    @patch('bmlibrarian.paperchecker.components.statement_extractor.ollama.Client')
    def test_extract_raises_on_empty_abstract(
        self,
        mock_client_class: MagicMock
    ) -> None:
        """Test that empty abstract raises ValueError."""
        extractor = StatementExtractor(model="test-model")

        with pytest.raises(ValueError, match="cannot be empty"):
            extractor.extract("")

    @patch('bmlibrarian.paperchecker.components.statement_extractor.ollama.Client')
    def test_extract_raises_on_whitespace_only_abstract(
        self,
        mock_client_class: MagicMock
    ) -> None:
        """Test that whitespace-only abstract raises ValueError."""
        extractor = StatementExtractor(model="test-model")

        with pytest.raises(ValueError, match="cannot be empty"):
            extractor.extract("   \n\t  ")

    @patch('bmlibrarian.paperchecker.components.statement_extractor.ollama.Client')
    def test_extract_raises_on_short_abstract(
        self,
        mock_client_class: MagicMock
    ) -> None:
        """Test that abstract shorter than minimum raises ValueError."""
        extractor = StatementExtractor(model="test-model")
        short_text = "A" * (MIN_ABSTRACT_LENGTH - 1)

        with pytest.raises(ValueError, match="too short"):
            extractor.extract(short_text)

    @patch('bmlibrarian.paperchecker.components.statement_extractor.ollama.Client')
    def test_extract_accepts_minimum_length_abstract(
        self,
        mock_client_class: MagicMock,
        statement_extraction_response: str
    ) -> None:
        """Test that abstract at exactly minimum length is accepted."""
        mock_client = MagicMock()
        mock_client.chat.return_value = {
            "message": {"content": statement_extraction_response}
        }
        mock_client_class.return_value = mock_client

        extractor = StatementExtractor(model="test-model")
        min_length_text = "A" * MIN_ABSTRACT_LENGTH

        # Should not raise - will parse the response
        statements = extractor.extract(min_length_text)
        assert len(statements) > 0


# ==================== PROMPT CONSTRUCTION TESTS ====================

class TestPromptConstruction:
    """Test prompt building for statement extraction."""

    @patch('bmlibrarian.paperchecker.components.statement_extractor.ollama.Client')
    def test_build_extraction_prompt_contains_abstract(
        self,
        mock_client_class: MagicMock,
        sample_abstract: str
    ) -> None:
        """Test that prompt contains the abstract text."""
        extractor = StatementExtractor(model="test-model", max_statements=3)

        prompt = extractor._build_extraction_prompt(sample_abstract)

        assert sample_abstract in prompt

    @patch('bmlibrarian.paperchecker.components.statement_extractor.ollama.Client')
    def test_build_extraction_prompt_contains_max_statements(
        self,
        mock_client_class: MagicMock,
        sample_abstract: str
    ) -> None:
        """Test that prompt specifies max_statements."""
        extractor = StatementExtractor(model="test-model", max_statements=5)

        prompt = extractor._build_extraction_prompt(sample_abstract)

        assert "5" in prompt

    @patch('bmlibrarian.paperchecker.components.statement_extractor.ollama.Client')
    def test_build_extraction_prompt_requests_json_format(
        self,
        mock_client_class: MagicMock,
        sample_abstract: str
    ) -> None:
        """Test that prompt requests JSON output format."""
        extractor = StatementExtractor(model="test-model")

        prompt = extractor._build_extraction_prompt(sample_abstract)

        assert "JSON" in prompt
        assert "statements" in prompt

    @patch('bmlibrarian.paperchecker.components.statement_extractor.ollama.Client')
    def test_build_extraction_prompt_includes_statement_types(
        self,
        mock_client_class: MagicMock,
        sample_abstract: str
    ) -> None:
        """Test that prompt includes valid statement type descriptions."""
        extractor = StatementExtractor(model="test-model")

        prompt = extractor._build_extraction_prompt(sample_abstract)

        assert "hypothesis" in prompt.lower()
        assert "finding" in prompt.lower()
        assert "conclusion" in prompt.lower()


# ==================== RESPONSE PARSING TESTS ====================

class TestResponseParsing:
    """Test LLM response parsing."""

    @patch('bmlibrarian.paperchecker.components.statement_extractor.ollama.Client')
    def test_parse_valid_json_response(
        self,
        mock_client_class: MagicMock,
        statement_extraction_response: str
    ) -> None:
        """Test parsing a valid JSON response."""
        extractor = StatementExtractor(model="test-model")

        statements = extractor._parse_response(statement_extraction_response)

        assert len(statements) == 2
        assert all(isinstance(s, Statement) for s in statements)
        assert statements[0].statement_type == "conclusion"
        assert statements[1].statement_type == "finding"

    @patch('bmlibrarian.paperchecker.components.statement_extractor.ollama.Client')
    def test_parse_json_in_markdown_code_block(
        self,
        mock_client_class: MagicMock,
        json_in_markdown_response: str
    ) -> None:
        """Test parsing JSON wrapped in markdown code blocks."""
        extractor = StatementExtractor(model="test-model")

        statements = extractor._parse_response(json_in_markdown_response)

        assert len(statements) == 1
        assert statements[0].statement_type == "finding"
        assert statements[0].confidence == 0.85

    @patch('bmlibrarian.paperchecker.components.statement_extractor.ollama.Client')
    def test_parse_raises_on_malformed_json(
        self,
        mock_client_class: MagicMock,
        malformed_json_response: str
    ) -> None:
        """Test that malformed JSON raises ValueError."""
        extractor = StatementExtractor(model="test-model")

        with pytest.raises(ValueError, match="Invalid JSON"):
            extractor._parse_response(malformed_json_response)

    @patch('bmlibrarian.paperchecker.components.statement_extractor.ollama.Client')
    def test_parse_raises_on_missing_statements_key(
        self,
        mock_client_class: MagicMock
    ) -> None:
        """Test that missing 'statements' key raises ValueError."""
        extractor = StatementExtractor(model="test-model")
        response = json.dumps({"other_key": []})

        with pytest.raises(ValueError, match="'statements'"):
            extractor._parse_response(response)

    @patch('bmlibrarian.paperchecker.components.statement_extractor.ollama.Client')
    def test_parse_raises_on_no_valid_statements(
        self,
        mock_client_class: MagicMock
    ) -> None:
        """Test that response with no valid statements raises ValueError."""
        extractor = StatementExtractor(model="test-model")
        response = json.dumps({
            "statements": [
                {"text": "", "statement_type": "finding", "confidence": 0.8}
            ]
        })

        with pytest.raises(ValueError, match="No valid statements"):
            extractor._parse_response(response)

    @patch('bmlibrarian.paperchecker.components.statement_extractor.ollama.Client')
    def test_parse_respects_max_statements_limit(
        self,
        mock_client_class: MagicMock
    ) -> None:
        """Test that only max_statements are returned."""
        extractor = StatementExtractor(model="test-model", max_statements=1)
        response = json.dumps({
            "statements": [
                {"text": "Statement 1", "statement_type": "finding", "confidence": 0.8},
                {"text": "Statement 2", "statement_type": "finding", "confidence": 0.7},
            ]
        })

        statements = extractor._parse_response(response)

        assert len(statements) == 1
        assert "Statement 1" in statements[0].text


# ==================== STATEMENT TYPE NORMALIZATION TESTS ====================

class TestStatementTypeNormalization:
    """Test statement type normalization."""

    @patch('bmlibrarian.paperchecker.components.statement_extractor.ollama.Client')
    def test_normalize_valid_types(self, mock_client_class: MagicMock) -> None:
        """Test normalization of valid statement types."""
        extractor = StatementExtractor(model="test-model")

        for valid_type in VALID_STATEMENT_TYPES:
            normalized = extractor._normalize_statement_type(valid_type)
            assert normalized == valid_type

    @patch('bmlibrarian.paperchecker.components.statement_extractor.ollama.Client')
    def test_normalize_type_variations(self, mock_client_class: MagicMock) -> None:
        """Test normalization of common type variations."""
        extractor = StatementExtractor(model="test-model")

        # Plural variations
        assert extractor._normalize_statement_type("findings") == "finding"
        assert extractor._normalize_statement_type("conclusions") == "conclusion"
        assert extractor._normalize_statement_type("hypotheses") == "hypothesis"

        # Common synonyms
        assert extractor._normalize_statement_type("result") == "finding"
        assert extractor._normalize_statement_type("observation") == "finding"
        assert extractor._normalize_statement_type("prediction") == "hypothesis"
        assert extractor._normalize_statement_type("interpretation") == "conclusion"

    @patch('bmlibrarian.paperchecker.components.statement_extractor.ollama.Client')
    def test_normalize_returns_none_for_unknown_type(
        self,
        mock_client_class: MagicMock
    ) -> None:
        """Test that unknown types return None."""
        extractor = StatementExtractor(model="test-model")

        assert extractor._normalize_statement_type("unknown_type") is None
        assert extractor._normalize_statement_type("gibberish") is None


# ==================== JSON EXTRACTION TESTS ====================

class TestJsonExtraction:
    """Test JSON extraction from various response formats."""

    @patch('bmlibrarian.paperchecker.components.statement_extractor.ollama.Client')
    def test_extract_json_from_code_block(
        self,
        mock_client_class: MagicMock
    ) -> None:
        """Test extracting JSON from ```json code block."""
        extractor = StatementExtractor(model="test-model")
        response = '''Some text
```json
{"test": "value"}
```
More text'''

        result = extractor._extract_json(response)
        assert json.loads(result) == {"test": "value"}

    @patch('bmlibrarian.paperchecker.components.statement_extractor.ollama.Client')
    def test_extract_json_from_plain_code_block(
        self,
        mock_client_class: MagicMock
    ) -> None:
        """Test extracting JSON from ``` code block without language."""
        extractor = StatementExtractor(model="test-model")
        response = '''```
{"test": "value"}
```'''

        result = extractor._extract_json(response)
        assert json.loads(result) == {"test": "value"}

    @patch('bmlibrarian.paperchecker.components.statement_extractor.ollama.Client')
    def test_extract_json_from_raw_response(
        self,
        mock_client_class: MagicMock
    ) -> None:
        """Test extracting JSON when response is raw JSON."""
        extractor = StatementExtractor(model="test-model")
        response = '{"test": "value"}'

        result = extractor._extract_json(response)
        assert json.loads(result) == {"test": "value"}

    @patch('bmlibrarian.paperchecker.components.statement_extractor.ollama.Client')
    def test_extract_json_with_nested_braces(
        self,
        mock_client_class: MagicMock
    ) -> None:
        """Test extracting JSON with nested objects."""
        extractor = StatementExtractor(model="test-model")
        response = 'Prefix {"outer": {"inner": "value"}} Suffix'

        result = extractor._extract_json(response)
        data = json.loads(result)
        assert data["outer"]["inner"] == "value"


# ==================== SINGLE STATEMENT PARSING TESTS ====================

class TestSingleStatementParsing:
    """Test parsing individual statements from response data."""

    @patch('bmlibrarian.paperchecker.components.statement_extractor.ollama.Client')
    def test_parse_single_statement_success(
        self,
        mock_client_class: MagicMock
    ) -> None:
        """Test successful parsing of a single statement."""
        extractor = StatementExtractor(model="test-model")
        stmt_data = {
            "text": "Test statement text",
            "context": "Test context",
            "statement_type": "finding",
            "confidence": 0.85
        }

        statement = extractor._parse_single_statement(stmt_data, order=1)

        assert statement is not None
        assert statement.text == "Test statement text"
        assert statement.context == "Test context"
        assert statement.statement_type == "finding"
        assert statement.confidence == 0.85
        assert statement.statement_order == 1

    @patch('bmlibrarian.paperchecker.components.statement_extractor.ollama.Client')
    def test_parse_single_statement_missing_required_field(
        self,
        mock_client_class: MagicMock
    ) -> None:
        """Test that missing required field returns None."""
        extractor = StatementExtractor(model="test-model")
        stmt_data = {
            "text": "Test statement",
            # Missing statement_type and confidence
        }

        statement = extractor._parse_single_statement(stmt_data, order=1)

        assert statement is None

    @patch('bmlibrarian.paperchecker.components.statement_extractor.ollama.Client')
    def test_parse_single_statement_clamps_confidence(
        self,
        mock_client_class: MagicMock
    ) -> None:
        """Test that out-of-range confidence is clamped."""
        extractor = StatementExtractor(model="test-model")

        # Test confidence > 1.0
        stmt_data = {
            "text": "Test statement",
            "statement_type": "finding",
            "confidence": 1.5
        }
        statement = extractor._parse_single_statement(stmt_data, order=1)
        assert statement.confidence == 1.0

        # Test confidence < 0.0
        stmt_data["confidence"] = -0.5
        statement = extractor._parse_single_statement(stmt_data, order=1)
        assert statement.confidence == 0.0

    @patch('bmlibrarian.paperchecker.components.statement_extractor.ollama.Client')
    def test_parse_single_statement_uses_default_confidence(
        self,
        mock_client_class: MagicMock
    ) -> None:
        """Test that non-numeric confidence uses default."""
        extractor = StatementExtractor(model="test-model")
        stmt_data = {
            "text": "Test statement",
            "statement_type": "finding",
            "confidence": "high"  # Invalid - not numeric
        }

        statement = extractor._parse_single_statement(stmt_data, order=1)

        assert statement.confidence == DEFAULT_CONFIDENCE

    @patch('bmlibrarian.paperchecker.components.statement_extractor.ollama.Client')
    def test_parse_single_statement_empty_text_returns_none(
        self,
        mock_client_class: MagicMock
    ) -> None:
        """Test that empty text returns None."""
        extractor = StatementExtractor(model="test-model")
        stmt_data = {
            "text": "  ",
            "statement_type": "finding",
            "confidence": 0.8
        }

        statement = extractor._parse_single_statement(stmt_data, order=1)

        assert statement is None


# ==================== LLM CALL TESTS ====================

class TestLLMCall:
    """Test LLM API call functionality."""

    @patch('bmlibrarian.paperchecker.components.statement_extractor.ollama.Client')
    def test_call_llm_success(
        self,
        mock_client_class: MagicMock,
        statement_extraction_response: str
    ) -> None:
        """Test successful LLM call."""
        mock_client = MagicMock()
        mock_client.chat.return_value = {
            "message": {"content": statement_extraction_response}
        }
        mock_client_class.return_value = mock_client

        extractor = StatementExtractor(model="test-model")
        result = extractor._call_llm("test prompt")

        assert result == statement_extraction_response
        mock_client.chat.assert_called_once()

    @patch('bmlibrarian.paperchecker.components.statement_extractor.ollama.Client')
    @patch('bmlibrarian.paperchecker.components.statement_extractor.time.sleep')
    def test_call_llm_retries_on_empty_response(
        self,
        mock_sleep: MagicMock,
        mock_client_class: MagicMock
    ) -> None:
        """Test that empty responses trigger retry."""
        mock_client = MagicMock()
        # First call returns empty, second succeeds
        mock_client.chat.side_effect = [
            {"message": {"content": ""}},
            {"message": {"content": '{"statements": []}'}}
        ]
        mock_client_class.return_value = mock_client

        extractor = StatementExtractor(model="test-model")
        result = extractor._call_llm("test prompt", max_retries=3)

        assert result == '{"statements": []}'
        assert mock_client.chat.call_count == 2
        mock_sleep.assert_called_once()  # Should sleep between retries

    @patch('bmlibrarian.paperchecker.components.statement_extractor.ollama.Client')
    @patch('bmlibrarian.paperchecker.components.statement_extractor.time.sleep')
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

        extractor = StatementExtractor(model="test-model")

        with pytest.raises(RuntimeError, match="Failed to get response"):
            extractor._call_llm("test prompt", max_retries=3)


# ==================== CONNECTION TEST ====================

class TestConnectionTest:
    """Test connection testing functionality."""

    @patch('bmlibrarian.paperchecker.components.statement_extractor.ollama.Client')
    def test_test_connection_success(self, mock_client_class: MagicMock) -> None:
        """Test successful connection test."""
        mock_client = MagicMock()
        mock_client.list.return_value = {"models": []}
        mock_client_class.return_value = mock_client

        extractor = StatementExtractor(model="test-model")
        result = extractor.test_connection()

        assert result is True
        mock_client.list.assert_called_once()

    @patch('bmlibrarian.paperchecker.components.statement_extractor.ollama.Client')
    def test_test_connection_failure(self, mock_client_class: MagicMock) -> None:
        """Test failed connection test."""
        mock_client = MagicMock()
        mock_client.list.side_effect = Exception("Connection refused")
        mock_client_class.return_value = mock_client

        extractor = StatementExtractor(model="test-model")
        result = extractor.test_connection()

        assert result is False


# ==================== INTEGRATION TESTS ====================

class TestExtractIntegration:
    """Integration tests for the extract method."""

    @patch('bmlibrarian.paperchecker.components.statement_extractor.ollama.Client')
    def test_extract_full_workflow(
        self,
        mock_client_class: MagicMock,
        sample_abstract: str,
        statement_extraction_response: str
    ) -> None:
        """Test complete extraction workflow."""
        mock_client = MagicMock()
        mock_client.chat.return_value = {
            "message": {"content": statement_extraction_response}
        }
        mock_client_class.return_value = mock_client

        extractor = StatementExtractor(model="test-model", max_statements=2)
        statements = extractor.extract(sample_abstract)

        assert len(statements) == 2
        assert all(isinstance(s, Statement) for s in statements)
        assert all(s.statement_order > 0 for s in statements)

    @patch('bmlibrarian.paperchecker.components.statement_extractor.ollama.Client')
    def test_extract_wraps_llm_errors(
        self,
        mock_client_class: MagicMock,
        sample_abstract: str
    ) -> None:
        """Test that LLM errors are wrapped in RuntimeError."""
        mock_client = MagicMock()
        mock_client.chat.side_effect = Exception("Network error")
        mock_client_class.return_value = mock_client

        extractor = StatementExtractor(model="test-model")

        with pytest.raises(RuntimeError, match="Failed to extract statements"):
            extractor.extract(sample_abstract)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
