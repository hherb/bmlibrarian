"""
Unit tests for VerdictAnalyzer component.

Tests cover:
    1. Initialization and configuration
    2. Input validation
    3. Prompt construction for verdict analysis
    4. Response parsing and validation
    5. Overall assessment generation
    6. Verdict and confidence validation
    7. Error handling
"""

import json
import pytest
from typing import Any, Dict
from unittest.mock import MagicMock, patch

from bmlibrarian.paperchecker.components.verdict_analyzer import (
    VerdictAnalyzer,
    DEFAULT_TEMPERATURE,
    DEFAULT_OLLAMA_URL,
    MIN_RATIONALE_LENGTH,
    REQUIRED_JSON_FIELDS,
)
from bmlibrarian.paperchecker.data_models import (
    Statement,
    CounterReport,
    Verdict,
    VALID_VERDICT_VALUES,
    VALID_CONFIDENCE_LEVELS,
)


# ==================== INITIALIZATION TESTS ====================

class TestVerdictAnalyzerInit:
    """Test VerdictAnalyzer initialization."""

    @patch('bmlibrarian.paperchecker.components.verdict_analyzer.ollama.Client')
    def test_init_with_defaults(self, mock_client_class: MagicMock) -> None:
        """Test initialization with default parameters."""
        analyzer = VerdictAnalyzer(model="test-model")

        assert analyzer.model == "test-model"
        assert analyzer.temperature == DEFAULT_TEMPERATURE
        assert analyzer.host == DEFAULT_OLLAMA_URL

    @patch('bmlibrarian.paperchecker.components.verdict_analyzer.ollama.Client')
    def test_init_with_custom_parameters(self, mock_client_class: MagicMock) -> None:
        """Test initialization with custom parameters."""
        analyzer = VerdictAnalyzer(
            model="custom-model",
            host="http://custom:11434",
            temperature=0.5
        )

        assert analyzer.model == "custom-model"
        assert analyzer.host == "http://custom:11434"
        assert analyzer.temperature == 0.5

    @patch('bmlibrarian.paperchecker.components.verdict_analyzer.ollama.Client')
    def test_init_strips_trailing_slash(self, mock_client_class: MagicMock) -> None:
        """Test that trailing slash is stripped from host URL."""
        analyzer = VerdictAnalyzer(
            model="test-model",
            host="http://localhost:11434/"
        )

        assert analyzer.host == "http://localhost:11434"


# ==================== CONSTANTS TESTS ====================

class TestVerdictAnalyzerConstants:
    """Test module constants are properly defined."""

    def test_min_rationale_length_positive(self) -> None:
        """Test MIN_RATIONALE_LENGTH is positive."""
        assert MIN_RATIONALE_LENGTH > 0

    def test_required_fields_complete(self) -> None:
        """Test REQUIRED_JSON_FIELDS contains expected fields."""
        assert "verdict" in REQUIRED_JSON_FIELDS
        assert "confidence" in REQUIRED_JSON_FIELDS
        assert "rationale" in REQUIRED_JSON_FIELDS


# ==================== INPUT VALIDATION TESTS ====================

class TestInputValidation:
    """Test input validation for analyze method."""

    @patch('bmlibrarian.paperchecker.components.verdict_analyzer.ollama.Client')
    def test_validate_raises_on_empty_statement_text(
        self,
        mock_client_class: MagicMock,
        sample_counter_report: CounterReport
    ) -> None:
        """Test that empty statement text raises ValueError."""
        analyzer = VerdictAnalyzer(model="test-model")

        empty_stmt = Statement(
            text="",
            context="Some context",
            statement_type="finding",
            confidence=0.8,
            statement_order=1
        )

        with pytest.raises(ValueError, match="cannot be empty"):
            analyzer._validate_inputs(empty_stmt, sample_counter_report)

    @patch('bmlibrarian.paperchecker.components.verdict_analyzer.ollama.Client')
    def test_validate_raises_on_whitespace_counter_report_summary(
        self,
        mock_client_class: MagicMock,
        sample_statement: Statement,
        sample_counter_report: CounterReport
    ) -> None:
        """Test that whitespace-only counter-report summary raises ValueError."""
        analyzer = VerdictAnalyzer(model="test-model")

        # Create a valid report and then test with whitespace summary
        # Note: CounterReport validates summary at creation time, so we test via analyze
        # which calls _validate_inputs internally
        with pytest.raises((ValueError, AssertionError)):
            # CounterReport asserts non-empty summary during creation
            CounterReport(
                summary="   ",  # Whitespace only
                num_citations=0,
                citations=[],
                search_stats={},
                generation_metadata={}
            )


# ==================== PROMPT CONSTRUCTION TESTS ====================

class TestPromptConstruction:
    """Test prompt building for verdict analysis."""

    @patch('bmlibrarian.paperchecker.components.verdict_analyzer.ollama.Client')
    def test_prompt_contains_statement_text(
        self,
        mock_client_class: MagicMock,
        sample_statement: Statement,
        sample_counter_report: CounterReport
    ) -> None:
        """Test that prompt contains statement text."""
        analyzer = VerdictAnalyzer(model="test-model")

        prompt = analyzer._build_verdict_prompt(sample_statement, sample_counter_report)

        assert sample_statement.text in prompt

    @patch('bmlibrarian.paperchecker.components.verdict_analyzer.ollama.Client')
    def test_prompt_contains_counter_report_summary(
        self,
        mock_client_class: MagicMock,
        sample_statement: Statement,
        sample_counter_report: CounterReport
    ) -> None:
        """Test that prompt contains counter-report summary."""
        analyzer = VerdictAnalyzer(model="test-model")

        prompt = analyzer._build_verdict_prompt(sample_statement, sample_counter_report)

        assert sample_counter_report.summary in prompt

    @patch('bmlibrarian.paperchecker.components.verdict_analyzer.ollama.Client')
    def test_prompt_includes_verdict_options(
        self,
        mock_client_class: MagicMock,
        sample_statement: Statement,
        sample_counter_report: CounterReport
    ) -> None:
        """Test that prompt includes all verdict options."""
        analyzer = VerdictAnalyzer(model="test-model")

        prompt = analyzer._build_verdict_prompt(sample_statement, sample_counter_report)

        for verdict in VALID_VERDICT_VALUES:
            assert verdict in prompt

    @patch('bmlibrarian.paperchecker.components.verdict_analyzer.ollama.Client')
    def test_prompt_includes_confidence_options(
        self,
        mock_client_class: MagicMock,
        sample_statement: Statement,
        sample_counter_report: CounterReport
    ) -> None:
        """Test that prompt includes all confidence options."""
        analyzer = VerdictAnalyzer(model="test-model")

        prompt = analyzer._build_verdict_prompt(sample_statement, sample_counter_report)

        for conf in VALID_CONFIDENCE_LEVELS:
            assert conf in prompt


# ==================== RESPONSE PARSING TESTS ====================

class TestResponseParsing:
    """Test verdict response parsing."""

    @patch('bmlibrarian.paperchecker.components.verdict_analyzer.ollama.Client')
    def test_parse_valid_response(
        self,
        mock_client_class: MagicMock,
        verdict_analysis_response: str
    ) -> None:
        """Test parsing a valid JSON response."""
        analyzer = VerdictAnalyzer(model="test-model")

        result = analyzer._parse_response(verdict_analysis_response)

        assert result["verdict"] == "contradicts"
        assert result["confidence"] == "high"
        assert len(result["rationale"]) >= MIN_RATIONALE_LENGTH

    @patch('bmlibrarian.paperchecker.components.verdict_analyzer.ollama.Client')
    def test_parse_raises_on_missing_verdict(
        self,
        mock_client_class: MagicMock
    ) -> None:
        """Test that missing verdict field raises ValueError."""
        analyzer = VerdictAnalyzer(model="test-model")
        response = json.dumps({
            "confidence": "high",
            "rationale": "A" * MIN_RATIONALE_LENGTH
        })

        with pytest.raises(ValueError, match="missing required fields"):
            analyzer._parse_response(response)

    @patch('bmlibrarian.paperchecker.components.verdict_analyzer.ollama.Client')
    def test_parse_raises_on_invalid_verdict(
        self,
        mock_client_class: MagicMock
    ) -> None:
        """Test that invalid verdict value raises ValueError."""
        analyzer = VerdictAnalyzer(model="test-model")
        response = json.dumps({
            "verdict": "invalid_verdict",
            "confidence": "high",
            "rationale": "A" * MIN_RATIONALE_LENGTH
        })

        with pytest.raises(ValueError, match="Invalid verdict"):
            analyzer._parse_response(response)

    @patch('bmlibrarian.paperchecker.components.verdict_analyzer.ollama.Client')
    def test_parse_raises_on_invalid_confidence(
        self,
        mock_client_class: MagicMock
    ) -> None:
        """Test that invalid confidence value raises ValueError."""
        analyzer = VerdictAnalyzer(model="test-model")
        response = json.dumps({
            "verdict": "contradicts",
            "confidence": "very_high",  # Invalid
            "rationale": "A" * MIN_RATIONALE_LENGTH
        })

        with pytest.raises(ValueError, match="Invalid confidence"):
            analyzer._parse_response(response)

    @patch('bmlibrarian.paperchecker.components.verdict_analyzer.ollama.Client')
    def test_parse_raises_on_short_rationale(
        self,
        mock_client_class: MagicMock
    ) -> None:
        """Test that too-short rationale raises ValueError."""
        analyzer = VerdictAnalyzer(model="test-model")
        response = json.dumps({
            "verdict": "contradicts",
            "confidence": "high",
            "rationale": "Short"  # Too short
        })

        with pytest.raises(ValueError, match="Rationale too short"):
            analyzer._parse_response(response)


# ==================== JSON EXTRACTION TESTS ====================

class TestJsonExtraction:
    """Test JSON extraction from various response formats."""

    @patch('bmlibrarian.paperchecker.components.verdict_analyzer.ollama.Client')
    def test_extract_from_code_block(self, mock_client_class: MagicMock) -> None:
        """Test extracting JSON from ```json code block."""
        analyzer = VerdictAnalyzer(model="test-model")
        response = '''Here is the verdict:
```json
{"verdict": "supports", "confidence": "high", "rationale": "Test rationale here."}
```
'''
        result = analyzer._extract_json(response)
        data = json.loads(result)
        assert data["verdict"] == "supports"

    @patch('bmlibrarian.paperchecker.components.verdict_analyzer.ollama.Client')
    def test_extract_from_raw_json(self, mock_client_class: MagicMock) -> None:
        """Test extracting raw JSON response."""
        analyzer = VerdictAnalyzer(model="test-model")
        response = '{"verdict": "undecided", "confidence": "low", "rationale": "Test."}'

        result = analyzer._extract_json(response)
        data = json.loads(result)
        assert data["verdict"] == "undecided"

    @patch('bmlibrarian.paperchecker.components.verdict_analyzer.ollama.Client')
    def test_extract_from_embedded_json(self, mock_client_class: MagicMock) -> None:
        """Test extracting JSON embedded in text."""
        analyzer = VerdictAnalyzer(model="test-model")
        response = 'The analysis is: {"verdict": "contradicts"} as shown above.'

        result = analyzer._extract_json(response)
        data = json.loads(result)
        assert data["verdict"] == "contradicts"


# ==================== OVERALL ASSESSMENT TESTS ====================

class TestOverallAssessment:
    """Test overall assessment generation."""

    @patch('bmlibrarian.paperchecker.components.verdict_analyzer.ollama.Client')
    def test_assessment_raises_on_length_mismatch(
        self,
        mock_client_class: MagicMock,
        sample_statement: Statement,
        sample_verdict: Verdict
    ) -> None:
        """Test that mismatched lengths raise ValueError."""
        analyzer = VerdictAnalyzer(model="test-model")

        with pytest.raises(ValueError, match="same length"):
            analyzer.generate_overall_assessment(
                statements=[sample_statement],
                verdicts=[sample_verdict, sample_verdict]  # 2 verdicts for 1 statement
            )

    @patch('bmlibrarian.paperchecker.components.verdict_analyzer.ollama.Client')
    def test_assessment_empty_verdicts(
        self,
        mock_client_class: MagicMock
    ) -> None:
        """Test assessment with no verdicts."""
        analyzer = VerdictAnalyzer(model="test-model")

        result = analyzer.generate_overall_assessment(
            statements=[],
            verdicts=[]
        )

        assert "No statements" in result

    @patch('bmlibrarian.paperchecker.components.verdict_analyzer.ollama.Client')
    def test_assessment_all_supported(
        self,
        mock_client_class: MagicMock,
        sample_statement: Statement,
        sample_counter_report: CounterReport
    ) -> None:
        """Test assessment when all statements are supported."""
        analyzer = VerdictAnalyzer(model="test-model")

        verdict = Verdict(
            verdict="supports",
            rationale="The evidence supports the claim.",
            confidence="high",
            counter_report=sample_counter_report,
            analysis_metadata={}
        )

        result = analyzer.generate_overall_assessment(
            statements=[sample_statement],
            verdicts=[verdict]
        )

        assert "supported" in result.lower()

    @patch('bmlibrarian.paperchecker.components.verdict_analyzer.ollama.Client')
    def test_assessment_all_contradicted(
        self,
        mock_client_class: MagicMock,
        sample_statement: Statement,
        sample_counter_report: CounterReport
    ) -> None:
        """Test assessment when all statements are contradicted."""
        analyzer = VerdictAnalyzer(model="test-model")

        verdict = Verdict(
            verdict="contradicts",
            rationale="The evidence contradicts the claim.",
            confidence="high",
            counter_report=sample_counter_report,
            analysis_metadata={}
        )

        result = analyzer.generate_overall_assessment(
            statements=[sample_statement],
            verdicts=[verdict]
        )

        assert "contradicted" in result.lower()

    @patch('bmlibrarian.paperchecker.components.verdict_analyzer.ollama.Client')
    def test_assessment_all_undecided(
        self,
        mock_client_class: MagicMock,
        sample_statement: Statement,
        sample_counter_report: CounterReport
    ) -> None:
        """Test assessment when all statements are undecided."""
        analyzer = VerdictAnalyzer(model="test-model")

        verdict = Verdict(
            verdict="undecided",
            rationale="The evidence is mixed or insufficient.",
            confidence="low",
            counter_report=sample_counter_report,
            analysis_metadata={}
        )

        result = analyzer.generate_overall_assessment(
            statements=[sample_statement],
            verdicts=[verdict]
        )

        assert "mixed" in result.lower() or "insufficient" in result.lower()


# ==================== CONNECTION TEST ====================

class TestConnectionTest:
    """Test connection testing functionality."""

    @patch('bmlibrarian.paperchecker.components.verdict_analyzer.ollama.Client')
    def test_test_connection_success(self, mock_client_class: MagicMock) -> None:
        """Test successful connection test."""
        mock_client = MagicMock()
        mock_client.list.return_value = {
            "models": [{"name": "test-model"}]
        }
        mock_client_class.return_value = mock_client

        analyzer = VerdictAnalyzer(model="test-model")
        result = analyzer.test_connection()

        assert result is True

    @patch('bmlibrarian.paperchecker.components.verdict_analyzer.ollama.Client')
    def test_test_connection_failure(self, mock_client_class: MagicMock) -> None:
        """Test failed connection test."""
        mock_client = MagicMock()
        mock_client.list.side_effect = Exception("Connection refused")
        mock_client_class.return_value = mock_client

        analyzer = VerdictAnalyzer(model="test-model")
        result = analyzer.test_connection()

        assert result is False


# ==================== INTEGRATION TESTS ====================

class TestAnalyzeIntegration:
    """Integration tests for the analyze method."""

    @patch('bmlibrarian.paperchecker.components.verdict_analyzer.ollama.Client')
    def test_analyze_full_workflow(
        self,
        mock_client_class: MagicMock,
        sample_statement: Statement,
        sample_counter_report: CounterReport,
        verdict_analysis_response: str
    ) -> None:
        """Test complete analysis workflow."""
        mock_client = MagicMock()
        mock_client.chat.return_value = {
            "message": {"content": verdict_analysis_response}
        }
        mock_client_class.return_value = mock_client

        analyzer = VerdictAnalyzer(model="test-model")
        result = analyzer.analyze(sample_statement, sample_counter_report)

        assert isinstance(result, Verdict)
        assert result.verdict in VALID_VERDICT_VALUES
        assert result.confidence in VALID_CONFIDENCE_LEVELS
        assert result.counter_report is sample_counter_report

    @patch('bmlibrarian.paperchecker.components.verdict_analyzer.ollama.Client')
    def test_analyze_wraps_llm_errors(
        self,
        mock_client_class: MagicMock,
        sample_statement: Statement,
        sample_counter_report: CounterReport
    ) -> None:
        """Test that LLM errors are wrapped in RuntimeError."""
        mock_client = MagicMock()
        mock_client.chat.side_effect = Exception("Network error")
        mock_client_class.return_value = mock_client

        analyzer = VerdictAnalyzer(model="test-model")

        with pytest.raises(RuntimeError, match="LLM call failed"):
            analyzer.analyze(sample_statement, sample_counter_report)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
