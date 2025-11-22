"""
Unit tests for VerdictAnalyzer component.

Tests the verdict analysis functionality including:
- Verdict prompt construction
- JSON response parsing (various formats)
- Verdict validation logic
- Overall assessment generation
- Error handling and edge cases
"""

import pytest
from unittest.mock import Mock, patch, MagicMock

from bmlibrarian.paperchecker.components.verdict_analyzer import (
    VerdictAnalyzer,
    DEFAULT_TEMPERATURE,
    DEFAULT_OLLAMA_URL,
    MIN_RATIONALE_LENGTH,
)
from bmlibrarian.paperchecker.data_models import (
    Statement,
    CounterReport,
    ExtractedCitation,
    Verdict,
    VALID_VERDICT_VALUES,
    VALID_CONFIDENCE_LEVELS,
)


# ==================== Fixtures ====================


@pytest.fixture
def analyzer():
    """Create VerdictAnalyzer instance with mock client."""
    with patch('bmlibrarian.paperchecker.components.verdict_analyzer.ollama.Client'):
        return VerdictAnalyzer(model="gpt-oss:20b", temperature=0.3)


@pytest.fixture
def sample_statement():
    """Create sample Statement for testing."""
    return Statement(
        text="Metformin is superior to GLP-1 agonists for glycemic control",
        context="This finding is based on multiple RCTs.",
        statement_type="finding",
        confidence=0.9,
        statement_order=1
    )


@pytest.fixture
def sample_citation():
    """Create sample ExtractedCitation for testing."""
    return ExtractedCitation(
        doc_id=12345,
        passage="GLP-1 agonists showed superior HbA1c reduction compared to metformin (p<0.001).",
        relevance_score=5,
        full_citation="Smith J, Johnson A. GLP-1 vs Metformin study. JAMA. 2023;329(5):401-410.",
        metadata={"pmid": 12345678, "doi": "10.1001/jama.2023.0001", "year": 2023},
        citation_order=1
    )


@pytest.fixture
def sample_counter_report(sample_citation):
    """Create sample CounterReport for testing."""
    return CounterReport(
        summary="Multiple randomized controlled trials demonstrate that GLP-1 receptor agonists achieve superior glycemic control compared to metformin monotherapy. A 2023 meta-analysis found statistically significant differences in HbA1c reduction [1].",
        num_citations=1,
        citations=[sample_citation],
        search_stats={
            "documents_found": 50,
            "documents_scored": 25,
            "citations_extracted": 1
        },
        generation_metadata={"model": "gpt-oss:20b"}
    )


@pytest.fixture
def empty_counter_report():
    """Create CounterReport with no citations for testing."""
    return CounterReport(
        summary="No substantial evidence was found in the literature database to support the counter-claim.",
        num_citations=0,
        citations=[],
        search_stats={
            "documents_found": 30,
            "documents_scored": 5,
            "citations_extracted": 0
        },
        generation_metadata={"model": "gpt-oss:20b"}
    )


def create_verdict(verdict_type: str, confidence: str, counter_report: CounterReport) -> Verdict:
    """Helper to create Verdict objects for testing."""
    return Verdict(
        verdict=verdict_type,
        rationale=f"Test rationale for {verdict_type} verdict with {confidence} confidence.",
        confidence=confidence,
        counter_report=counter_report,
        analysis_metadata={"model": "gpt-oss:20b"}
    )


# ==================== Initialization Tests ====================


class TestVerdictAnalyzerInit:
    """Tests for VerdictAnalyzer initialization."""

    def test_init_with_defaults(self):
        """Test initialization with default parameters."""
        with patch('bmlibrarian.paperchecker.components.verdict_analyzer.ollama.Client') as mock_client:
            analyzer = VerdictAnalyzer(model="gpt-oss:20b")

            assert analyzer.model == "gpt-oss:20b"
            assert analyzer.temperature == DEFAULT_TEMPERATURE
            assert analyzer.host == DEFAULT_OLLAMA_URL.rstrip("/")
            mock_client.assert_called_once_with(host=DEFAULT_OLLAMA_URL.rstrip("/"))

    def test_init_with_custom_parameters(self):
        """Test initialization with custom parameters."""
        with patch('bmlibrarian.paperchecker.components.verdict_analyzer.ollama.Client') as mock_client:
            analyzer = VerdictAnalyzer(
                model="custom-model:latest",
                host="http://custom-host:11434/",
                temperature=0.5
            )

            assert analyzer.model == "custom-model:latest"
            assert analyzer.temperature == 0.5
            assert analyzer.host == "http://custom-host:11434"  # Trailing slash stripped
            mock_client.assert_called_once_with(host="http://custom-host:11434")

    def test_init_strips_trailing_slash_from_host(self):
        """Test that trailing slash is stripped from host URL."""
        with patch('bmlibrarian.paperchecker.components.verdict_analyzer.ollama.Client'):
            analyzer = VerdictAnalyzer(model="test", host="http://localhost:11434/")
            assert analyzer.host == "http://localhost:11434"


# ==================== Prompt Building Tests ====================


class TestBuildVerdictPrompt:
    """Tests for _build_verdict_prompt method."""

    def test_prompt_contains_statement_text(self, analyzer, sample_statement, sample_counter_report):
        """Test that prompt includes the original statement text."""
        prompt = analyzer._build_verdict_prompt(sample_statement, sample_counter_report)
        assert sample_statement.text in prompt

    def test_prompt_contains_statement_type(self, analyzer, sample_statement, sample_counter_report):
        """Test that prompt includes statement type."""
        prompt = analyzer._build_verdict_prompt(sample_statement, sample_counter_report)
        assert sample_statement.statement_type in prompt

    def test_prompt_contains_counter_report_summary(self, analyzer, sample_statement, sample_counter_report):
        """Test that prompt includes counter-report summary."""
        prompt = analyzer._build_verdict_prompt(sample_statement, sample_counter_report)
        assert sample_counter_report.summary in prompt

    def test_prompt_contains_search_statistics(self, analyzer, sample_statement, sample_counter_report):
        """Test that prompt includes search statistics."""
        prompt = analyzer._build_verdict_prompt(sample_statement, sample_counter_report)
        assert str(sample_counter_report.search_stats["documents_found"]) in prompt
        assert str(sample_counter_report.search_stats["documents_scored"]) in prompt
        assert str(sample_counter_report.num_citations) in prompt

    def test_prompt_contains_verdict_instructions(self, analyzer, sample_statement, sample_counter_report):
        """Test that prompt contains verdict classification instructions."""
        prompt = analyzer._build_verdict_prompt(sample_statement, sample_counter_report)

        # Check for verdict options
        assert '"contradicts"' in prompt
        assert '"supports"' in prompt
        assert '"undecided"' in prompt

        # Check for confidence options
        assert '"high"' in prompt
        assert '"medium"' in prompt
        assert '"low"' in prompt

    def test_prompt_specifies_json_output_format(self, analyzer, sample_statement, sample_counter_report):
        """Test that prompt specifies JSON output format."""
        prompt = analyzer._build_verdict_prompt(sample_statement, sample_counter_report)

        assert "JSON" in prompt
        assert "verdict" in prompt
        assert "confidence" in prompt
        assert "rationale" in prompt


# ==================== JSON Extraction Tests ====================


class TestExtractJson:
    """Tests for _extract_json method."""

    def test_extract_pure_json(self, analyzer):
        """Test extracting pure JSON response."""
        response = '{"verdict": "contradicts", "confidence": "high", "rationale": "Test rationale."}'
        result = analyzer._extract_json(response)
        assert '"verdict": "contradicts"' in result

    def test_extract_json_with_code_block(self, analyzer):
        """Test extracting JSON from ```json code block."""
        response = '''Here is the analysis:
```json
{"verdict": "supports", "confidence": "medium", "rationale": "Evidence supports claim."}
```
'''
        result = analyzer._extract_json(response)
        assert '"verdict": "supports"' in result
        assert "Here is the analysis" not in result

    def test_extract_json_with_plain_code_block(self, analyzer):
        """Test extracting JSON from ``` code block without language."""
        response = '''```
{"verdict": "undecided", "confidence": "low", "rationale": "Mixed evidence."}
```'''
        result = analyzer._extract_json(response)
        assert '"verdict": "undecided"' in result

    def test_extract_json_embedded_in_text(self, analyzer):
        """Test extracting JSON embedded in surrounding text."""
        response = '''After careful analysis, my verdict is:
{"verdict": "contradicts", "confidence": "high", "rationale": "Strong counter-evidence."}
Please note the limitations above.'''
        result = analyzer._extract_json(response)
        assert result.startswith('{')
        assert result.endswith('}')
        assert '"verdict": "contradicts"' in result

    def test_extract_json_with_whitespace(self, analyzer):
        """Test extracting JSON with surrounding whitespace."""
        response = '''
{"verdict": "supports", "confidence": "medium", "rationale": "Test."}
   '''
        result = analyzer._extract_json(response)
        assert '"verdict": "supports"' in result

    def test_extract_json_multiline_format(self, analyzer):
        """Test extracting properly formatted multiline JSON."""
        response = '''{
  "verdict": "contradicts",
  "confidence": "high",
  "rationale": "Multiple studies show strong evidence against the original claim."
}'''
        result = analyzer._extract_json(response)
        assert '"verdict": "contradicts"' in result


# ==================== Response Validation Tests ====================


class TestValidateVerdictData:
    """Tests for _validate_verdict_data method."""

    def test_valid_data_passes_validation(self, analyzer):
        """Test that valid verdict data passes validation."""
        data = {
            "verdict": "contradicts",
            "confidence": "high",
            "rationale": "The counter-evidence strongly contradicts the original statement based on multiple RCTs."
        }
        # Should not raise
        analyzer._validate_verdict_data(data)

    def test_missing_verdict_field_raises_error(self, analyzer):
        """Test that missing verdict field raises ValueError."""
        data = {
            "confidence": "high",
            "rationale": "Test rationale that is long enough to pass."
        }
        with pytest.raises(ValueError, match="missing required fields"):
            analyzer._validate_verdict_data(data)

    def test_missing_confidence_field_raises_error(self, analyzer):
        """Test that missing confidence field raises ValueError."""
        data = {
            "verdict": "contradicts",
            "rationale": "Test rationale that is long enough to pass."
        }
        with pytest.raises(ValueError, match="missing required fields"):
            analyzer._validate_verdict_data(data)

    def test_missing_rationale_field_raises_error(self, analyzer):
        """Test that missing rationale field raises ValueError."""
        data = {
            "verdict": "contradicts",
            "confidence": "high"
        }
        with pytest.raises(ValueError, match="missing required fields"):
            analyzer._validate_verdict_data(data)

    def test_invalid_verdict_value_raises_error(self, analyzer):
        """Test that invalid verdict value raises ValueError."""
        data = {
            "verdict": "maybe",  # Invalid
            "confidence": "high",
            "rationale": "Test rationale that is long enough."
        }
        with pytest.raises(ValueError, match="Invalid verdict"):
            analyzer._validate_verdict_data(data)

    def test_invalid_confidence_value_raises_error(self, analyzer):
        """Test that invalid confidence value raises ValueError."""
        data = {
            "verdict": "contradicts",
            "confidence": "very_high",  # Invalid
            "rationale": "Test rationale that is long enough."
        }
        with pytest.raises(ValueError, match="Invalid confidence"):
            analyzer._validate_verdict_data(data)

    def test_short_rationale_raises_error(self, analyzer):
        """Test that too-short rationale raises ValueError."""
        data = {
            "verdict": "contradicts",
            "confidence": "high",
            "rationale": "Short"  # Too short
        }
        with pytest.raises(ValueError, match="Rationale too short"):
            analyzer._validate_verdict_data(data)

    def test_empty_rationale_raises_error(self, analyzer):
        """Test that empty rationale raises ValueError."""
        data = {
            "verdict": "contradicts",
            "confidence": "high",
            "rationale": "   "  # Only whitespace
        }
        with pytest.raises(ValueError, match="Rationale too short"):
            analyzer._validate_verdict_data(data)

    def test_all_valid_verdict_values(self, analyzer):
        """Test that all valid verdict values pass validation."""
        for verdict_value in VALID_VERDICT_VALUES:
            data = {
                "verdict": verdict_value,
                "confidence": "medium",
                "rationale": "This is a sufficiently long rationale for testing purposes."
            }
            # Should not raise
            analyzer._validate_verdict_data(data)

    def test_all_valid_confidence_values(self, analyzer):
        """Test that all valid confidence values pass validation."""
        for confidence_value in VALID_CONFIDENCE_LEVELS:
            data = {
                "verdict": "contradicts",
                "confidence": confidence_value,
                "rationale": "This is a sufficiently long rationale for testing purposes."
            }
            # Should not raise
            analyzer._validate_verdict_data(data)

    def test_rationale_exactly_at_minimum_length(self, analyzer):
        """Test rationale at exactly minimum length passes."""
        data = {
            "verdict": "contradicts",
            "confidence": "high",
            "rationale": "A" * MIN_RATIONALE_LENGTH
        }
        # Should not raise
        analyzer._validate_verdict_data(data)


# ==================== Parse Response Tests ====================


class TestParseResponse:
    """Tests for _parse_response method."""

    def test_parse_valid_json_response(self, analyzer):
        """Test parsing valid JSON response."""
        response = '{"verdict": "contradicts", "confidence": "high", "rationale": "Strong evidence supports contradiction."}'
        result = analyzer._parse_response(response)

        assert result["verdict"] == "contradicts"
        assert result["confidence"] == "high"
        assert "Strong evidence" in result["rationale"]

    def test_parse_json_with_code_block(self, analyzer):
        """Test parsing JSON wrapped in code block."""
        response = '''```json
{
  "verdict": "supports",
  "confidence": "medium",
  "rationale": "No contradictory evidence was found in the literature search."
}
```'''
        result = analyzer._parse_response(response)

        assert result["verdict"] == "supports"
        assert result["confidence"] == "medium"

    def test_parse_invalid_json_raises_error(self, analyzer):
        """Test that invalid JSON raises ValueError."""
        response = "This is not valid JSON at all"
        with pytest.raises(ValueError, match="Invalid JSON"):
            analyzer._parse_response(response)

    def test_parse_json_missing_field_raises_error(self, analyzer):
        """Test that JSON missing required field raises ValueError."""
        response = '{"verdict": "contradicts", "confidence": "high"}'  # Missing rationale
        with pytest.raises(ValueError, match="missing required fields"):
            analyzer._parse_response(response)

    def test_parse_json_with_invalid_verdict_raises_error(self, analyzer):
        """Test that JSON with invalid verdict raises ValueError."""
        response = '{"verdict": "invalid", "confidence": "high", "rationale": "Test rationale that is long enough."}'
        with pytest.raises(ValueError, match="Invalid verdict"):
            analyzer._parse_response(response)


# ==================== Overall Assessment Tests ====================


class TestGenerateOverallAssessment:
    """Tests for generate_overall_assessment method."""

    def test_all_statements_supported_high_confidence(self, analyzer, sample_counter_report):
        """Test assessment when all statements are supported with high confidence."""
        statements = [
            Statement(text="Stmt 1", context="", statement_type="finding", confidence=0.9, statement_order=1),
            Statement(text="Stmt 2", context="", statement_type="finding", confidence=0.9, statement_order=2)
        ]
        verdicts = [
            create_verdict("supports", "high", sample_counter_report),
            create_verdict("supports", "high", sample_counter_report)
        ]

        result = analyzer.generate_overall_assessment(statements, verdicts)

        assert "supported" in result.lower()
        assert "high confidence" in result.lower()
        assert "2" in result  # Number of statements

    def test_all_statements_supported_mixed_confidence(self, analyzer, sample_counter_report):
        """Test assessment when all statements are supported with mixed confidence."""
        statements = [
            Statement(text="Stmt 1", context="", statement_type="finding", confidence=0.9, statement_order=1),
            Statement(text="Stmt 2", context="", statement_type="finding", confidence=0.9, statement_order=2)
        ]
        verdicts = [
            create_verdict("supports", "high", sample_counter_report),
            create_verdict("supports", "medium", sample_counter_report)
        ]

        result = analyzer.generate_overall_assessment(statements, verdicts)

        assert "supported" in result.lower()
        assert "2" in result

    def test_all_statements_contradicted(self, analyzer, sample_counter_report):
        """Test assessment when all statements are contradicted."""
        statements = [
            Statement(text="Stmt 1", context="", statement_type="finding", confidence=0.9, statement_order=1),
            Statement(text="Stmt 2", context="", statement_type="finding", confidence=0.9, statement_order=2)
        ]
        verdicts = [
            create_verdict("contradicts", "high", sample_counter_report),
            create_verdict("contradicts", "high", sample_counter_report)
        ]

        result = analyzer.generate_overall_assessment(statements, verdicts)

        assert "contradicted" in result.lower()
        assert "high confidence" in result.lower()

    def test_all_statements_undecided(self, analyzer, sample_counter_report):
        """Test assessment when all statements are undecided."""
        statements = [
            Statement(text="Stmt 1", context="", statement_type="finding", confidence=0.9, statement_order=1),
            Statement(text="Stmt 2", context="", statement_type="finding", confidence=0.9, statement_order=2)
        ]
        verdicts = [
            create_verdict("undecided", "low", sample_counter_report),
            create_verdict("undecided", "low", sample_counter_report)
        ]

        result = analyzer.generate_overall_assessment(statements, verdicts)

        assert "mixed" in result.lower() or "undecided" in result.lower() or "insufficient" in result.lower()

    def test_majority_contradicted(self, analyzer, sample_counter_report):
        """Test assessment when majority of statements are contradicted."""
        statements = [
            Statement(text="Stmt 1", context="", statement_type="finding", confidence=0.9, statement_order=1),
            Statement(text="Stmt 2", context="", statement_type="finding", confidence=0.9, statement_order=2),
            Statement(text="Stmt 3", context="", statement_type="finding", confidence=0.9, statement_order=3)
        ]
        verdicts = [
            create_verdict("contradicts", "high", sample_counter_report),
            create_verdict("contradicts", "medium", sample_counter_report),
            create_verdict("supports", "low", sample_counter_report)
        ]

        result = analyzer.generate_overall_assessment(statements, verdicts)

        assert "majority" in result.lower()
        assert "contradicted" in result.lower()
        assert "2/3" in result or "2" in result

    def test_majority_supported(self, analyzer, sample_counter_report):
        """Test assessment when majority of statements are supported."""
        statements = [
            Statement(text="Stmt 1", context="", statement_type="finding", confidence=0.9, statement_order=1),
            Statement(text="Stmt 2", context="", statement_type="finding", confidence=0.9, statement_order=2),
            Statement(text="Stmt 3", context="", statement_type="finding", confidence=0.9, statement_order=3)
        ]
        verdicts = [
            create_verdict("supports", "high", sample_counter_report),
            create_verdict("supports", "medium", sample_counter_report),
            create_verdict("contradicts", "low", sample_counter_report)
        ]

        result = analyzer.generate_overall_assessment(statements, verdicts)

        assert "majority" in result.lower()
        assert "supported" in result.lower()

    def test_mixed_results_no_majority(self, analyzer, sample_counter_report):
        """Test assessment with mixed results and no clear majority."""
        statements = [
            Statement(text="Stmt 1", context="", statement_type="finding", confidence=0.9, statement_order=1),
            Statement(text="Stmt 2", context="", statement_type="finding", confidence=0.9, statement_order=2),
            Statement(text="Stmt 3", context="", statement_type="finding", confidence=0.9, statement_order=3)
        ]
        verdicts = [
            create_verdict("supports", "medium", sample_counter_report),
            create_verdict("contradicts", "medium", sample_counter_report),
            create_verdict("undecided", "low", sample_counter_report)
        ]

        result = analyzer.generate_overall_assessment(statements, verdicts)

        assert "mixed" in result.lower()
        assert "1" in result  # At least one count should be present

    def test_empty_verdicts_list(self, analyzer):
        """Test assessment with empty verdicts list."""
        result = analyzer.generate_overall_assessment([], [])
        assert "no statements" in result.lower()

    def test_single_statement_supported(self, analyzer, sample_counter_report):
        """Test assessment with single supported statement."""
        statements = [
            Statement(text="Stmt 1", context="", statement_type="finding", confidence=0.9, statement_order=1)
        ]
        verdicts = [create_verdict("supports", "high", sample_counter_report)]

        result = analyzer.generate_overall_assessment(statements, verdicts)

        assert "1" in result
        assert "supported" in result.lower()

    def test_mismatched_lengths_raises_error(self, analyzer, sample_counter_report):
        """Test that mismatched lengths raise ValueError."""
        statements = [
            Statement(text="Stmt 1", context="", statement_type="finding", confidence=0.9, statement_order=1),
            Statement(text="Stmt 2", context="", statement_type="finding", confidence=0.9, statement_order=2)
        ]
        verdicts = [create_verdict("supports", "high", sample_counter_report)]  # Only 1 verdict for 2 statements

        with pytest.raises(ValueError, match="must have the same length"):
            analyzer.generate_overall_assessment(statements, verdicts)


# ==================== Full Analyze Method Tests ====================


class TestAnalyze:
    """Tests for analyze method with mocked LLM calls."""

    def test_analyze_returns_verdict_object(self, analyzer, sample_statement, sample_counter_report):
        """Test that analyze returns a Verdict object."""
        mock_response = {
            "message": {
                "content": '{"verdict": "contradicts", "confidence": "high", "rationale": "Strong evidence from multiple RCTs contradicts the original statement."}'
            }
        }
        analyzer.client.chat = Mock(return_value=mock_response)

        result = analyzer.analyze(sample_statement, sample_counter_report)

        assert isinstance(result, Verdict)
        assert result.verdict == "contradicts"
        assert result.confidence == "high"
        assert "Strong evidence" in result.rationale
        assert result.counter_report == sample_counter_report

    def test_analyze_includes_metadata(self, analyzer, sample_statement, sample_counter_report):
        """Test that analyze includes analysis metadata."""
        mock_response = {
            "message": {
                "content": '{"verdict": "supports", "confidence": "medium", "rationale": "No contradictory evidence found in literature."}'
            }
        }
        analyzer.client.chat = Mock(return_value=mock_response)

        result = analyzer.analyze(sample_statement, sample_counter_report)

        assert "model" in result.analysis_metadata
        assert "temperature" in result.analysis_metadata
        assert "timestamp" in result.analysis_metadata
        assert result.analysis_metadata["model"] == analyzer.model

    def test_analyze_with_empty_statement_raises_error(self, analyzer, sample_counter_report):
        """Test that empty statement raises ValueError."""
        empty_statement = Statement(
            text="   ",  # Whitespace only - will fail validation
            context="",
            statement_type="finding",
            confidence=0.9,
            statement_order=1
        )
        # Actually Statement with whitespace-only text should pass dataclass creation
        # but fail our validation
        with pytest.raises(ValueError, match="Statement text cannot be empty"):
            analyzer.analyze(empty_statement, sample_counter_report)

    def test_analyze_with_empty_counter_report_raises_error(self, analyzer, sample_statement):
        """Test that empty counter-report summary raises ValueError."""
        # Create a mock counter_report that bypasses dataclass validation
        # to test our analyzer's own validation
        mock_report = Mock()
        mock_report.summary = "   "  # Whitespace only
        mock_report.num_citations = 0
        mock_report.citations = []
        mock_report.search_stats = {}

        with pytest.raises(ValueError, match="Counter-report summary cannot be empty"):
            analyzer.analyze(sample_statement, mock_report)

    def test_analyze_calls_llm_with_correct_parameters(self, analyzer, sample_statement, sample_counter_report):
        """Test that analyze calls LLM with correct parameters."""
        mock_response = {
            "message": {
                "content": '{"verdict": "undecided", "confidence": "low", "rationale": "Evidence is mixed and inconclusive."}'
            }
        }
        analyzer.client.chat = Mock(return_value=mock_response)

        analyzer.analyze(sample_statement, sample_counter_report)

        # Verify chat was called
        analyzer.client.chat.assert_called_once()

        # Check call arguments
        call_args = analyzer.client.chat.call_args
        assert call_args.kwargs["model"] == analyzer.model
        assert "messages" in call_args.kwargs
        assert call_args.kwargs["options"]["temperature"] == analyzer.temperature


# ==================== Connection Test ====================


class TestTestConnection:
    """Tests for test_connection method."""

    def test_connection_success_with_model_available(self, analyzer):
        """Test connection when model is available."""
        analyzer.client.list = Mock(return_value={
            "models": [
                {"name": "gpt-oss:20b"},
                {"name": "llama2:latest"}
            ]
        })

        result = analyzer.test_connection()

        assert result is True

    def test_connection_success_without_exact_model_match(self, analyzer):
        """Test connection succeeds even without exact model match (server is reachable)."""
        analyzer.client.list = Mock(return_value={
            "models": [
                {"name": "other-model:latest"}
            ]
        })

        result = analyzer.test_connection()

        assert result is True  # Server is reachable

    def test_connection_failure_on_exception(self, analyzer):
        """Test connection returns False on exception."""
        analyzer.client.list = Mock(side_effect=Exception("Connection refused"))

        result = analyzer.test_connection()

        assert result is False


# ==================== Input Validation Tests ====================


class TestValidateInputs:
    """Tests for _validate_inputs method."""

    def test_valid_inputs_pass(self, analyzer, sample_statement, sample_counter_report):
        """Test that valid inputs pass validation."""
        # Should not raise
        analyzer._validate_inputs(sample_statement, sample_counter_report)

    def test_empty_statement_text_raises_error(self, analyzer, sample_counter_report):
        """Test that empty statement text raises ValueError."""
        # Need to bypass Statement's own validation to test this
        statement = Mock()
        statement.text = ""

        with pytest.raises(ValueError, match="Statement text cannot be empty"):
            analyzer._validate_inputs(statement, sample_counter_report)

    def test_whitespace_statement_text_raises_error(self, analyzer, sample_counter_report):
        """Test that whitespace-only statement text raises ValueError."""
        statement = Mock()
        statement.text = "   \n\t  "

        with pytest.raises(ValueError, match="Statement text cannot be empty"):
            analyzer._validate_inputs(statement, sample_counter_report)

    def test_empty_counter_report_summary_raises_error(self, analyzer, sample_statement):
        """Test that empty counter-report summary raises ValueError."""
        counter_report = Mock()
        counter_report.summary = ""

        with pytest.raises(ValueError, match="Counter-report summary cannot be empty"):
            analyzer._validate_inputs(sample_statement, counter_report)


# ==================== Edge Cases ====================


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_very_long_statement_text(self, analyzer, sample_counter_report):
        """Test handling of very long statement text."""
        long_text = "A" * 5000
        statement = Statement(
            text=long_text,
            context="",
            statement_type="finding",
            confidence=0.9,
            statement_order=1
        )

        prompt = analyzer._build_verdict_prompt(statement, sample_counter_report)
        assert long_text in prompt

    def test_unicode_in_statement(self, analyzer, sample_counter_report):
        """Test handling of unicode characters in statement."""
        unicode_statement = Statement(
            text="α-adrenergic agonists reduce β-cell function (p < 0.05)",
            context="Statistical significance: α = 0.05",
            statement_type="finding",
            confidence=0.9,
            statement_order=1
        )

        prompt = analyzer._build_verdict_prompt(unicode_statement, sample_counter_report)
        assert "α-adrenergic" in prompt
        assert "β-cell" in prompt

    def test_special_characters_in_json_response(self, analyzer):
        """Test parsing JSON with special characters."""
        response = '{"verdict": "contradicts", "confidence": "high", "rationale": "The p-value (p < 0.001) indicates statistical significance."}'
        result = analyzer._parse_response(response)
        assert "p < 0.001" in result["rationale"]

    def test_nested_quotes_in_rationale(self, analyzer):
        """Test parsing JSON with nested quotes in rationale."""
        response = '{"verdict": "supports", "confidence": "medium", "rationale": "As stated in the original: \\"metformin is first-line therapy\\", this remains supported."}'
        result = analyzer._parse_response(response)
        assert "rationale" in result

    def test_minimum_rationale_length_boundary(self, analyzer):
        """Test rationale exactly at minimum length."""
        exact_min_rationale = "A" * MIN_RATIONALE_LENGTH
        response = f'{{"verdict": "contradicts", "confidence": "high", "rationale": "{exact_min_rationale}"}}'

        result = analyzer._parse_response(response)
        assert len(result["rationale"]) == MIN_RATIONALE_LENGTH

    def test_counter_report_with_zero_search_stats(self, analyzer, sample_statement):
        """Test handling counter-report with zero in search stats."""
        report = CounterReport(
            summary="No evidence found due to search limitations.",
            num_citations=0,
            citations=[],
            search_stats={
                "documents_found": 0,
                "documents_scored": 0,
                "citations_extracted": 0
            },
            generation_metadata={}
        )

        prompt = analyzer._build_verdict_prompt(sample_statement, report)

        assert "0" in prompt  # Should include the zero counts

    def test_json_with_extra_fields_is_accepted(self, analyzer):
        """Test that JSON with extra fields is still parsed correctly."""
        response = '''{"verdict": "undecided", "confidence": "low", "rationale": "Evidence is insufficient for conclusions.", "extra_field": "ignored"}'''
        result = analyzer._parse_response(response)

        assert result["verdict"] == "undecided"
        assert result["confidence"] == "low"
        # Extra field should not cause issues
