"""
Tests for StatementExtractor component.

This module contains comprehensive tests for the statement extraction functionality,
including unit tests with mocked LLM responses and integration tests that can
optionally run against a real Ollama server.
"""

import json
import pytest
from unittest.mock import Mock, patch, MagicMock

import ollama

from bmlibrarian.paperchecker.components import StatementExtractor
from bmlibrarian.paperchecker.data_models import Statement, VALID_STATEMENT_TYPES


# Test Fixtures


@pytest.fixture
def extractor():
    """Create StatementExtractor instance with default settings."""
    return StatementExtractor(
        model="gpt-oss:20b",
        max_statements=2,
        temperature=0.3,
    )


@pytest.fixture
def extractor_single():
    """Create StatementExtractor that extracts only one statement."""
    return StatementExtractor(
        model="gpt-oss:20b",
        max_statements=1,
        temperature=0.3,
    )


@pytest.fixture
def sample_abstract():
    """Sample medical abstract for testing."""
    return """
    Background: Type 2 diabetes management requires effective long-term
    glycemic control. Objective: To compare the efficacy of metformin versus
    GLP-1 receptor agonists in long-term outcomes. Methods: Retrospective
    cohort study of 10,000 patients over 5 years. Results: Metformin
    demonstrated superior HbA1c reduction (1.5% vs 1.2%, p<0.001) and lower
    cardiovascular events (HR 0.75, 95% CI 0.65-0.85). Conclusion: Metformin
    shows superior long-term efficacy compared to GLP-1 agonists for T2DM.
    """


@pytest.fixture
def valid_llm_response():
    """Valid JSON response from LLM."""
    return json.dumps({
        "statements": [
            {
                "text": "Metformin demonstrated superior HbA1c reduction (1.5% vs 1.2%, p<0.001)",
                "context": "Results: Metformin demonstrated superior HbA1c reduction and lower cardiovascular events.",
                "statement_type": "finding",
                "confidence": 0.95,
            },
            {
                "text": "Metformin shows superior long-term efficacy compared to GLP-1 agonists for T2DM",
                "context": "Conclusion: Metformin shows superior long-term efficacy compared to GLP-1 agonists for T2DM.",
                "statement_type": "conclusion",
                "confidence": 0.90,
            },
        ]
    })


@pytest.fixture
def single_statement_response():
    """Valid JSON response with a single statement."""
    return json.dumps({
        "statements": [
            {
                "text": "Metformin demonstrated superior HbA1c reduction (1.5% vs 1.2%, p<0.001)",
                "context": "Results: Metformin demonstrated superior HbA1c reduction.",
                "statement_type": "finding",
                "confidence": 0.95,
            }
        ]
    })


# Unit Tests - Input Validation


class TestInputValidation:
    """Tests for input validation."""

    def test_extract_empty_abstract(self, extractor):
        """Test extraction fails on empty abstract."""
        with pytest.raises(ValueError, match="cannot be empty"):
            extractor.extract("")

    def test_extract_whitespace_only_abstract(self, extractor):
        """Test extraction fails on whitespace-only abstract."""
        with pytest.raises(ValueError, match="cannot be empty"):
            extractor.extract("   \n\t   ")

    def test_extract_short_abstract(self, extractor):
        """Test extraction fails on too-short abstract."""
        with pytest.raises(ValueError, match="too short"):
            extractor.extract("Very short abstract.")

    def test_extract_none_abstract(self, extractor):
        """Test extraction fails on None abstract."""
        with pytest.raises(ValueError, match="cannot be empty"):
            extractor.extract(None)

    def test_minimum_length_abstract(self, extractor, valid_llm_response):
        """Test that exactly minimum length abstract is accepted."""
        # Create abstract of exactly minimum length (50 chars)
        abstract = "A" * 50

        with patch.object(extractor, "_call_llm", return_value=valid_llm_response):
            # Should not raise ValueError about length
            statements = extractor.extract(abstract)
            assert len(statements) > 0


# Unit Tests - LLM Response Parsing


class TestResponseParsing:
    """Tests for LLM response parsing."""

    def test_parse_valid_response(self, extractor, sample_abstract, valid_llm_response):
        """Test parsing of valid LLM response."""
        with patch.object(extractor, "_call_llm", return_value=valid_llm_response):
            statements = extractor.extract(sample_abstract)

            assert len(statements) == 2
            assert all(isinstance(s, Statement) for s in statements)

    def test_parse_response_with_code_blocks(self, extractor, sample_abstract):
        """Test parsing response wrapped in markdown code blocks."""
        response_with_blocks = """Here's the extraction:
```json
{
  "statements": [
    {
      "text": "Test statement",
      "context": "Test context",
      "statement_type": "finding",
      "confidence": 0.85
    }
  ]
}
```
"""
        with patch.object(extractor, "_call_llm", return_value=response_with_blocks):
            statements = extractor.extract(sample_abstract)
            assert len(statements) == 1
            assert statements[0].text == "Test statement"

    def test_parse_response_with_extra_text(self, extractor, sample_abstract):
        """Test parsing response with text before/after JSON."""
        response_with_text = """Based on my analysis:
{
  "statements": [
    {
      "text": "Test statement",
      "context": "Context here",
      "statement_type": "conclusion",
      "confidence": 0.9
    }
  ]
}
I hope this helps!"""
        with patch.object(extractor, "_call_llm", return_value=response_with_text):
            statements = extractor.extract(sample_abstract)
            assert len(statements) == 1

    def test_parse_response_missing_statements_key(self, extractor, sample_abstract):
        """Test parsing fails when 'statements' key is missing."""
        invalid_response = json.dumps({"results": []})

        with patch.object(extractor, "_call_llm", return_value=invalid_response):
            with pytest.raises(ValueError, match="missing 'statements' key"):
                extractor.extract(sample_abstract)

    def test_parse_response_invalid_json(self, extractor, sample_abstract):
        """Test parsing fails on invalid JSON."""
        invalid_response = "This is not valid JSON at all"

        with patch.object(extractor, "_call_llm", return_value=invalid_response):
            with pytest.raises(ValueError, match="Invalid JSON"):
                extractor.extract(sample_abstract)

    def test_parse_response_empty_statements_list(self, extractor, sample_abstract):
        """Test parsing fails when statements list is empty."""
        empty_response = json.dumps({"statements": []})

        with patch.object(extractor, "_call_llm", return_value=empty_response):
            with pytest.raises(ValueError, match="No valid statements"):
                extractor.extract(sample_abstract)

    def test_parse_response_statements_not_list(self, extractor, sample_abstract):
        """Test parsing fails when statements is not a list."""
        invalid_response = json.dumps({"statements": "not a list"})

        with patch.object(extractor, "_call_llm", return_value=invalid_response):
            with pytest.raises(ValueError, match="must be a list"):
                extractor.extract(sample_abstract)


# Unit Tests - Statement Validation


class TestStatementValidation:
    """Tests for individual statement validation."""

    def test_statement_types_valid(self, extractor, sample_abstract, valid_llm_response):
        """Test that statement types are valid."""
        with patch.object(extractor, "_call_llm", return_value=valid_llm_response):
            statements = extractor.extract(sample_abstract)

            for statement in statements:
                assert statement.statement_type in VALID_STATEMENT_TYPES

    def test_confidence_scores_valid(self, extractor, sample_abstract, valid_llm_response):
        """Test that confidence scores are in valid range."""
        with patch.object(extractor, "_call_llm", return_value=valid_llm_response):
            statements = extractor.extract(sample_abstract)

            for statement in statements:
                assert 0.0 <= statement.confidence <= 1.0

    def test_statement_order_sequential(self, extractor, sample_abstract, valid_llm_response):
        """Test that statement orders are sequential."""
        with patch.object(extractor, "_call_llm", return_value=valid_llm_response):
            statements = extractor.extract(sample_abstract)

            orders = [s.statement_order for s in statements]
            assert orders == list(range(1, len(statements) + 1))

    def test_confidence_clamping_high(self, extractor, sample_abstract):
        """Test that confidence > 1.0 is clamped to 1.0."""
        response = json.dumps({
            "statements": [
                {
                    "text": "Test statement",
                    "context": "Context",
                    "statement_type": "finding",
                    "confidence": 1.5,  # Out of range (too high)
                }
            ]
        })

        with patch.object(extractor, "_call_llm", return_value=response):
            statements = extractor.extract(sample_abstract)
            assert statements[0].confidence == 1.0  # Should be clamped

    def test_confidence_clamping_low(self, extractor, sample_abstract):
        """Test that confidence < 0.0 is clamped to 0.0."""
        response = json.dumps({
            "statements": [
                {
                    "text": "Test statement",
                    "context": "Context",
                    "statement_type": "finding",
                    "confidence": -0.5,  # Out of range (negative)
                }
            ]
        })

        with patch.object(extractor, "_call_llm", return_value=response):
            statements = extractor.extract(sample_abstract)
            assert statements[0].confidence == 0.0  # Should be clamped

    def test_non_numeric_confidence_defaults(self, extractor, sample_abstract):
        """Test that non-numeric confidence defaults to 0.5."""
        response = json.dumps({
            "statements": [
                {
                    "text": "Test statement",
                    "context": "Context",
                    "statement_type": "finding",
                    "confidence": "high",  # Non-numeric
                }
            ]
        })

        with patch.object(extractor, "_call_llm", return_value=response):
            statements = extractor.extract(sample_abstract)
            assert statements[0].confidence == 0.5  # Default value

    def test_statement_type_normalization(self, extractor, sample_abstract):
        """Test that statement types are normalized."""
        response = json.dumps({
            "statements": [
                {
                    "text": "Test finding",
                    "context": "Context",
                    "statement_type": "FINDING",  # Uppercase
                    "confidence": 0.8,
                },
                {
                    "text": "Test result",
                    "context": "Context",
                    "statement_type": "result",  # Alternative name
                    "confidence": 0.8,
                },
            ]
        })

        with patch.object(extractor, "_call_llm", return_value=response):
            statements = extractor.extract(sample_abstract)
            assert all(s.statement_type == "finding" for s in statements)

    def test_missing_required_fields_skipped(self, extractor, sample_abstract):
        """Test that statements missing required fields are skipped."""
        response = json.dumps({
            "statements": [
                {
                    "text": "Valid statement",
                    "context": "Context",
                    "statement_type": "finding",
                    "confidence": 0.8,
                },
                {
                    "text": "Missing confidence",
                    "context": "Context",
                    "statement_type": "finding",
                    # confidence is missing
                },
            ]
        })

        with patch.object(extractor, "_call_llm", return_value=response):
            statements = extractor.extract(sample_abstract)
            # Only valid statement should be returned
            assert len(statements) == 1
            assert statements[0].text == "Valid statement"

    def test_empty_text_skipped(self, extractor, sample_abstract):
        """Test that statements with empty text are skipped."""
        response = json.dumps({
            "statements": [
                {
                    "text": "",  # Empty text
                    "context": "Context",
                    "statement_type": "finding",
                    "confidence": 0.8,
                },
                {
                    "text": "Valid statement",
                    "context": "Context",
                    "statement_type": "finding",
                    "confidence": 0.8,
                },
            ]
        })

        with patch.object(extractor, "_call_llm", return_value=response):
            statements = extractor.extract(sample_abstract)
            assert len(statements) == 1
            assert statements[0].text == "Valid statement"

    def test_whitespace_only_text_skipped(self, extractor, sample_abstract):
        """Test that statements with whitespace-only text are skipped."""
        response = json.dumps({
            "statements": [
                {
                    "text": "   \n\t   ",  # Whitespace only
                    "context": "Context",
                    "statement_type": "finding",
                    "confidence": 0.8,
                },
                {
                    "text": "Valid statement",
                    "context": "Context",
                    "statement_type": "finding",
                    "confidence": 0.8,
                },
            ]
        })

        with patch.object(extractor, "_call_llm", return_value=response):
            statements = extractor.extract(sample_abstract)
            assert len(statements) == 1
            assert statements[0].text == "Valid statement"

    def test_unrecognized_statement_type_skipped(self, extractor, sample_abstract):
        """Test that statements with unrecognized types are skipped."""
        response = json.dumps({
            "statements": [
                {
                    "text": "Statement with unknown type",
                    "context": "Context",
                    "statement_type": "unknown_type",  # Invalid type
                    "confidence": 0.8,
                },
                {
                    "text": "Valid statement",
                    "context": "Context",
                    "statement_type": "finding",
                    "confidence": 0.8,
                },
            ]
        })

        with patch.object(extractor, "_call_llm", return_value=response):
            statements = extractor.extract(sample_abstract)
            assert len(statements) == 1
            assert statements[0].text == "Valid statement"

    def test_missing_context_defaults_to_empty(self, extractor, sample_abstract):
        """Test that missing context field defaults to empty string."""
        response = json.dumps({
            "statements": [
                {
                    "text": "Statement without context",
                    # context is missing
                    "statement_type": "finding",
                    "confidence": 0.8,
                }
            ]
        })

        with patch.object(extractor, "_call_llm", return_value=response):
            statements = extractor.extract(sample_abstract)
            assert len(statements) == 1
            assert statements[0].context == ""


# Unit Tests - Max Statements Limit


class TestMaxStatements:
    """Tests for max_statements limit."""

    def test_respects_max_statements(self, extractor_single, sample_abstract, single_statement_response):
        """Test that extraction respects max_statements limit."""
        with patch.object(extractor_single, "_call_llm", return_value=single_statement_response):
            statements = extractor_single.extract(sample_abstract)
            assert len(statements) <= 1

    def test_truncates_excess_statements(self, extractor_single, sample_abstract):
        """Test that excess statements are truncated."""
        response = json.dumps({
            "statements": [
                {
                    "text": "Statement 1",
                    "context": "Context 1",
                    "statement_type": "finding",
                    "confidence": 0.9,
                },
                {
                    "text": "Statement 2",
                    "context": "Context 2",
                    "statement_type": "conclusion",
                    "confidence": 0.85,
                },
                {
                    "text": "Statement 3",
                    "context": "Context 3",
                    "statement_type": "hypothesis",
                    "confidence": 0.8,
                },
            ]
        })

        with patch.object(extractor_single, "_call_llm", return_value=response):
            statements = extractor_single.extract(sample_abstract)
            # Should only get 1 statement (max_statements=1)
            assert len(statements) == 1
            assert statements[0].text == "Statement 1"


# Unit Tests - Connection Testing


class TestConnectionTesting:
    """Tests for connection testing functionality."""

    def test_connection_success(self, extractor):
        """Test successful connection check."""
        mock_client = MagicMock()
        mock_client.list.return_value = {"models": []}
        extractor.client = mock_client

        assert extractor.test_connection() is True
        mock_client.list.assert_called_once()

    def test_connection_failure(self, extractor):
        """Test failed connection check."""
        mock_client = MagicMock()
        mock_client.list.side_effect = Exception("Connection refused")
        extractor.client = mock_client

        assert extractor.test_connection() is False


# Unit Tests - Error Handling


class TestErrorHandling:
    """Tests for error handling."""

    def test_llm_timeout(self, extractor, sample_abstract):
        """Test handling of LLM timeout."""
        with patch.object(
            extractor,
            "_call_llm",
            side_effect=RuntimeError("LLM call timed out after 120 seconds"),
        ):
            with pytest.raises(RuntimeError, match="timed out"):
                extractor.extract(sample_abstract)

    def test_llm_connection_error(self, extractor, sample_abstract):
        """Test handling of connection error."""
        with patch.object(
            extractor,
            "_call_llm",
            side_effect=RuntimeError("Failed to connect to Ollama server"),
        ):
            with pytest.raises(RuntimeError, match="connect"):
                extractor.extract(sample_abstract)

    def test_llm_ollama_response_error(self, extractor, sample_abstract):
        """Test handling of Ollama ResponseError."""
        mock_client = MagicMock()
        mock_client.chat.side_effect = ollama.ResponseError("Model not found")
        extractor.client = mock_client

        with pytest.raises(RuntimeError, match="Failed to get response"):
            extractor.extract(sample_abstract)

    def test_llm_connection_error_actual(self, extractor, sample_abstract):
        """Test actual connection error handling in _call_llm."""
        mock_client = MagicMock()
        mock_client.chat.side_effect = Exception("Connection refused")
        extractor.client = mock_client

        with pytest.raises(RuntimeError, match="Failed to connect"):
            extractor.extract(sample_abstract)

    def test_llm_empty_response_retries(self, extractor, sample_abstract):
        """Test that empty responses trigger retries."""
        mock_client = MagicMock()
        # Return empty response all 3 times (max_retries=3)
        mock_client.chat.return_value = {"message": {"content": ""}}
        extractor.client = mock_client

        with pytest.raises(RuntimeError, match="Failed to get response"):
            extractor.extract(sample_abstract)

        # Should have been called 3 times (initial + 2 retries)
        assert mock_client.chat.call_count == 3

    def test_llm_generic_error(self, extractor, sample_abstract):
        """Test handling of generic unexpected errors."""
        mock_client = MagicMock()
        mock_client.chat.side_effect = Exception("Unexpected error occurred")
        extractor.client = mock_client

        with pytest.raises(RuntimeError, match="LLM call failed"):
            extractor.extract(sample_abstract)


# Integration Tests - These require a running Ollama server


@pytest.mark.integration
class TestIntegration:
    """Integration tests requiring a running Ollama server."""

    @pytest.fixture
    def live_extractor(self):
        """Create extractor for live testing."""
        return StatementExtractor(
            model="gpt-oss:20b",
            max_statements=2,
            temperature=0.3,
        )

    def test_extract_from_real_abstract(self, live_extractor, sample_abstract):
        """Test extraction from a real abstract using actual LLM."""
        if not live_extractor.test_connection():
            pytest.skip("Ollama server not available")

        statements = live_extractor.extract(sample_abstract)

        assert len(statements) <= 2
        assert all(isinstance(s, Statement) for s in statements)
        assert all(s.statement_type in VALID_STATEMENT_TYPES for s in statements)
        assert all(0.0 <= s.confidence <= 1.0 for s in statements)
        assert all(s.statement_order >= 1 for s in statements)

    def test_extraction_deterministic(self, live_extractor, sample_abstract):
        """Test that low temperature gives consistent results."""
        if not live_extractor.test_connection():
            pytest.skip("Ollama server not available")

        # Run extraction twice
        statements1 = live_extractor.extract(sample_abstract)
        statements2 = live_extractor.extract(sample_abstract)

        # Should extract same number of statements
        assert len(statements1) == len(statements2)

        # Statement types should have some overlap
        types1 = {s.statement_type for s in statements1}
        types2 = {s.statement_type for s in statements2}
        # At least 50% overlap expected
        overlap = len(types1 & types2) / max(len(types1), 1)
        assert overlap >= 0.5


# Tests for JSON extraction helper


class TestJsonExtraction:
    """Tests for the JSON extraction helper method."""

    def test_extract_plain_json(self, extractor):
        """Test extraction of plain JSON."""
        response = '{"statements": []}'
        result = extractor._extract_json(response)
        assert result == '{"statements": []}'

    def test_extract_json_from_code_block(self, extractor):
        """Test extraction of JSON from code block."""
        response = '```json\n{"statements": []}\n```'
        result = extractor._extract_json(response)
        assert result == '{"statements": []}'

    def test_extract_json_from_plain_code_block(self, extractor):
        """Test extraction of JSON from plain code block."""
        response = '```\n{"statements": []}\n```'
        result = extractor._extract_json(response)
        assert result == '{"statements": []}'

    def test_extract_nested_json(self, extractor):
        """Test extraction of nested JSON objects."""
        response = '{"statements": [{"text": "test", "nested": {"key": "value"}}]}'
        result = extractor._extract_json(response)
        # Should find the complete JSON object
        assert '"nested"' in result


# Tests for Statement Type Normalization


class TestStatementTypeNormalization:
    """Tests for statement type normalization helper."""

    def test_normalize_hypothesis_variations(self, extractor):
        """Test normalization of hypothesis variations."""
        assert extractor._normalize_statement_type("hypothesis") == "hypothesis"
        assert extractor._normalize_statement_type("Hypothesis") == "hypothesis"
        assert extractor._normalize_statement_type("HYPOTHESES") == "hypothesis"
        assert extractor._normalize_statement_type("prediction") == "hypothesis"

    def test_normalize_finding_variations(self, extractor):
        """Test normalization of finding variations."""
        assert extractor._normalize_statement_type("finding") == "finding"
        assert extractor._normalize_statement_type("findings") == "finding"
        assert extractor._normalize_statement_type("result") == "finding"
        assert extractor._normalize_statement_type("observation") == "finding"

    def test_normalize_conclusion_variations(self, extractor):
        """Test normalization of conclusion variations."""
        assert extractor._normalize_statement_type("conclusion") == "conclusion"
        assert extractor._normalize_statement_type("conclusions") == "conclusion"
        assert extractor._normalize_statement_type("interpretation") == "conclusion"
        assert extractor._normalize_statement_type("implication") == "conclusion"

    def test_normalize_unknown_type(self, extractor):
        """Test normalization returns None for unknown types."""
        assert extractor._normalize_statement_type("unknown") is None
        assert extractor._normalize_statement_type("random") is None
