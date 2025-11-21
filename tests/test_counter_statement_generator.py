"""
Unit tests for counter-statement generation components.

Tests the CounterStatementGenerator and HyDEGenerator components that implement
Step 5 of the PaperChecker workflow.
"""

import json
import pytest
from unittest.mock import MagicMock, patch

from bmlibrarian.paperchecker.data_models import Statement
from bmlibrarian.paperchecker.components import CounterStatementGenerator, HyDEGenerator


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def statement_comparative():
    """Statement with comparative claim."""
    return Statement(
        text="Metformin is superior to GLP-1 agonists in long-term T2DM outcomes",
        context="Prior studies have shown mixed results. Metformin is superior to GLP-1 agonists in long-term T2DM outcomes. This finding has significant implications.",
        statement_type="finding",
        confidence=0.9,
        statement_order=1
    )


@pytest.fixture
def statement_effect():
    """Statement with effect claim."""
    return Statement(
        text="Exercise reduces cardiovascular risk by 30%",
        context="Multiple cohort studies suggest protective effects. Exercise reduces cardiovascular risk by 30%. This effect is consistent across populations.",
        statement_type="finding",
        confidence=0.85,
        statement_order=1
    )


@pytest.fixture
def statement_association():
    """Statement with association claim."""
    return Statement(
        text="High vitamin D levels are associated with reduced cancer risk",
        context="Observational data support this association. High vitamin D levels are associated with reduced cancer risk. The mechanism remains unclear.",
        statement_type="hypothesis",
        confidence=0.75,
        statement_order=1
    )


@pytest.fixture
def statement_conclusion():
    """Statement with conclusion type."""
    return Statement(
        text="Early intervention in sepsis leads to better patient outcomes",
        context="Based on our analysis. Early intervention in sepsis leads to better patient outcomes. Clinical guidelines should be updated.",
        statement_type="conclusion",
        confidence=0.88,
        statement_order=1
    )


@pytest.fixture
def mock_ollama_client():
    """Mock ollama client for testing without real API calls."""
    with patch('bmlibrarian.paperchecker.components.counter_statement_generator.ollama.Client') as mock:
        yield mock


@pytest.fixture
def mock_hyde_ollama_client():
    """Mock ollama client for HyDE testing."""
    with patch('bmlibrarian.paperchecker.components.hyde_generator.ollama.Client') as mock:
        yield mock


# =============================================================================
# CounterStatementGenerator Tests
# =============================================================================

class TestCounterStatementGenerator:
    """Tests for CounterStatementGenerator component."""

    def test_initialization(self, mock_ollama_client):
        """Test generator initializes with correct parameters."""
        generator = CounterStatementGenerator(
            model="gpt-oss:20b",
            temperature=0.3,
            host="http://localhost:11434"
        )
        assert generator.model == "gpt-oss:20b"
        assert generator.temperature == 0.3
        assert generator.host == "http://localhost:11434"

    def test_initialization_strips_trailing_slash(self, mock_ollama_client):
        """Test that trailing slash is stripped from host URL."""
        generator = CounterStatementGenerator(
            model="test-model",
            host="http://localhost:11434/"
        )
        assert generator.host == "http://localhost:11434"

    def test_empty_statement_raises_value_error(self, mock_ollama_client):
        """Test that empty statement text raises ValueError."""
        generator = CounterStatementGenerator(model="test-model")
        empty_statement = Statement(
            text="",
            context="Context",
            statement_type="finding",
            confidence=0.9,
            statement_order=1
        )
        # Statement validation should catch this, but test generator's validation too
        with pytest.raises(ValueError, match="Statement text cannot be empty"):
            generator.generate(empty_statement)

    def test_whitespace_only_statement_raises_value_error(self, mock_ollama_client):
        """Test that whitespace-only statement raises ValueError."""
        generator = CounterStatementGenerator(model="test-model")
        # Create a statement and modify text to whitespace
        stmt = Statement(
            text="Valid text",
            context="Context",
            statement_type="finding",
            confidence=0.9,
            statement_order=1
        )
        stmt.text = "   "  # Bypass validation by modifying after creation
        with pytest.raises(ValueError, match="Statement text cannot be empty"):
            generator.generate(stmt)

    def test_parse_response_removes_common_prefixes(self, mock_ollama_client):
        """Test that common prefixes are removed from response."""
        generator = CounterStatementGenerator(model="test-model")

        prefixes_to_test = [
            "Counter-statement: GLP-1 agonists are superior",
            "counter statement: GLP-1 agonists are superior",
            "Negation: GLP-1 agonists are superior",
            "The negated statement is: GLP-1 agonists are superior",
            "Here is the counter-statement: GLP-1 agonists are superior",
        ]

        for response in prefixes_to_test:
            result = generator._parse_response(response)
            assert result == "GLP-1 agonists are superior"

    def test_parse_response_removes_quotes(self, mock_ollama_client):
        """Test that surrounding quotes are removed."""
        generator = CounterStatementGenerator(model="test-model")

        assert generator._parse_response('"Counter statement here"') == "Counter statement here"
        assert generator._parse_response("'Counter statement here'") == "Counter statement here"

    def test_parse_response_removes_bullet_prefix(self, mock_ollama_client):
        """Test that bullet/dash prefix is removed."""
        generator = CounterStatementGenerator(model="test-model")

        result = generator._parse_response("- Counter statement here")
        assert result == "Counter statement here"

    def test_parse_response_rejects_short_response(self, mock_ollama_client):
        """Test that too-short responses are rejected."""
        generator = CounterStatementGenerator(model="test-model")

        with pytest.raises(ValueError, match="too short or empty"):
            generator._parse_response("Short")

    def test_parse_response_rejects_empty_response(self, mock_ollama_client):
        """Test that empty responses are rejected."""
        generator = CounterStatementGenerator(model="test-model")

        with pytest.raises(ValueError, match="too short or empty"):
            generator._parse_response("")

        with pytest.raises(ValueError, match="too short or empty"):
            generator._parse_response("   ")

    def test_build_negation_prompt_includes_statement_info(self, mock_ollama_client, statement_comparative):
        """Test that prompt includes statement text, type, and context."""
        generator = CounterStatementGenerator(model="test-model")

        prompt = generator._build_negation_prompt(statement_comparative)

        assert statement_comparative.text in prompt
        assert statement_comparative.statement_type in prompt
        assert statement_comparative.context in prompt
        assert "logical opposite" in prompt.lower()
        assert "semantically precise" in prompt.lower()

    def test_build_negation_prompt_handles_empty_context(self, mock_ollama_client):
        """Test that prompt handles empty context gracefully."""
        generator = CounterStatementGenerator(model="test-model")
        stmt = Statement(
            text="Test statement",
            context="",
            statement_type="finding",
            confidence=0.9,
            statement_order=1
        )

        prompt = generator._build_negation_prompt(stmt)
        assert "N/A" in prompt

    def test_generate_success(self, mock_ollama_client, statement_comparative):
        """Test successful counter-statement generation."""
        mock_client_instance = MagicMock()
        mock_client_instance.chat.return_value = {
            "message": {
                "content": "GLP-1 agonists are superior or equivalent to metformin in long-term T2DM outcomes"
            }
        }
        mock_ollama_client.return_value = mock_client_instance

        generator = CounterStatementGenerator(model="gpt-oss:20b")
        result = generator.generate(statement_comparative)

        assert len(result) > 10
        assert "GLP-1" in result or "glp" in result.lower()
        mock_client_instance.chat.assert_called_once()

    def test_generate_handles_llm_error(self, mock_ollama_client, statement_comparative):
        """Test that LLM errors are handled gracefully."""
        mock_client_instance = MagicMock()
        mock_client_instance.chat.side_effect = Exception("Connection failed")
        mock_ollama_client.return_value = mock_client_instance

        generator = CounterStatementGenerator(model="gpt-oss:20b")

        with pytest.raises(RuntimeError, match="Failed to generate counter-statement"):
            generator.generate(statement_comparative)

    def test_test_connection_success(self, mock_ollama_client):
        """Test connection test when successful."""
        mock_client_instance = MagicMock()
        mock_client_instance.list.return_value = {"models": []}
        mock_ollama_client.return_value = mock_client_instance

        generator = CounterStatementGenerator(model="test-model")
        assert generator.test_connection() is True

    def test_test_connection_failure(self, mock_ollama_client):
        """Test connection test when failed."""
        mock_client_instance = MagicMock()
        mock_client_instance.list.side_effect = Exception("Connection refused")
        mock_ollama_client.return_value = mock_client_instance

        generator = CounterStatementGenerator(model="test-model")
        assert generator.test_connection() is False


# =============================================================================
# HyDEGenerator Tests
# =============================================================================

class TestHyDEGenerator:
    """Tests for HyDEGenerator component."""

    def test_initialization(self, mock_hyde_ollama_client):
        """Test generator initializes with correct parameters."""
        generator = HyDEGenerator(
            model="gpt-oss:20b",
            num_abstracts=2,
            max_keywords=10,
            temperature=0.3,
            host="http://localhost:11434"
        )
        assert generator.model == "gpt-oss:20b"
        assert generator.num_abstracts == 2
        assert generator.max_keywords == 10
        assert generator.temperature == 0.3

    def test_initialization_with_defaults(self, mock_hyde_ollama_client):
        """Test generator uses correct defaults."""
        generator = HyDEGenerator(model="test-model")
        assert generator.num_abstracts == 2  # Default
        assert generator.max_keywords == 10  # Default
        assert generator.temperature == 0.3  # Default

    def test_empty_counter_text_raises_value_error(self, mock_hyde_ollama_client, statement_comparative):
        """Test that empty counter text raises ValueError."""
        generator = HyDEGenerator(model="test-model")

        with pytest.raises(ValueError, match="Counter-statement text cannot be empty"):
            generator.generate(statement_comparative, "")

        with pytest.raises(ValueError, match="Counter-statement text cannot be empty"):
            generator.generate(statement_comparative, "   ")

    def test_build_hyde_prompt_includes_required_info(self, mock_hyde_ollama_client, statement_comparative):
        """Test that prompt includes original statement and counter-statement."""
        generator = HyDEGenerator(model="test-model", num_abstracts=2, max_keywords=10)
        counter_text = "GLP-1 agonists are superior to metformin"

        prompt = generator._build_hyde_prompt(statement_comparative, counter_text)

        assert statement_comparative.text in prompt
        assert counter_text in prompt
        assert "2" in prompt  # num_abstracts
        assert "10" in prompt  # max_keywords
        assert "hypothetical" in prompt.lower()
        assert "json" in prompt.lower()

    def test_parse_response_valid_json(self, mock_hyde_ollama_client):
        """Test parsing valid JSON response."""
        generator = HyDEGenerator(model="test-model", num_abstracts=2, max_keywords=5)

        response = json.dumps({
            "hyde_abstracts": [
                "Background: This is a hypothetical abstract supporting the counter-claim with sufficient length to pass validation. Methods: We conducted a randomized trial. Results: Findings support the counter-statement. Conclusion: The evidence is clear.",
                "Background: Second hypothetical abstract with different methodology and also sufficient length. Methods: Meta-analysis approach. Results: Strong effect observed. Conclusion: Confirms the counter-statement."
            ],
            "keywords": ["keyword1", "keyword2", "keyword3", "keyword4", "keyword5"]
        })

        result = generator._parse_response(response)

        assert "hyde_abstracts" in result
        assert "keywords" in result
        assert len(result["hyde_abstracts"]) == 2
        assert len(result["keywords"]) == 5

    def test_parse_response_extracts_json_from_code_block(self, mock_hyde_ollama_client):
        """Test parsing JSON from markdown code block."""
        generator = HyDEGenerator(model="test-model", num_abstracts=2, max_keywords=3)

        # Abstract must be at least 100 characters
        long_abstract = "Background: This is a hypothetical abstract. Methods: We conducted a study with many participants. Results: The findings were significant and support our hypothesis. Conclusion: The counter-claim is valid."
        response = f"""Here is the JSON:
```json
{{
  "hyde_abstracts": [
    "{long_abstract}"
  ],
  "keywords": ["term1", "term2"]
}}
```
"""
        result = generator._parse_response(response)
        assert len(result["hyde_abstracts"]) == 1
        assert len(result["keywords"]) == 2

    def test_parse_response_limits_abstracts(self, mock_hyde_ollama_client):
        """Test that abstracts are limited to num_abstracts."""
        generator = HyDEGenerator(model="test-model", num_abstracts=1, max_keywords=10)

        response = json.dumps({
            "hyde_abstracts": [
                "First abstract with sufficient length to pass the minimum character validation check that requires 100 characters.",
                "Second abstract with sufficient length but should be ignored because num_abstracts is set to 1.",
                "Third abstract that should also be ignored because we only want one abstract maximum."
            ],
            "keywords": ["kw1", "kw2"]
        })

        result = generator._parse_response(response)
        assert len(result["hyde_abstracts"]) == 1

    def test_parse_response_limits_keywords(self, mock_hyde_ollama_client):
        """Test that keywords are limited to max_keywords."""
        generator = HyDEGenerator(model="test-model", num_abstracts=2, max_keywords=3)

        response = json.dumps({
            "hyde_abstracts": [
                "Abstract with sufficient length to pass the minimum character validation check that requires 100 characters."
            ],
            "keywords": ["kw1", "kw2", "kw3", "kw4", "kw5"]
        })

        result = generator._parse_response(response)
        assert len(result["keywords"]) == 3

    def test_parse_response_filters_short_abstracts(self, mock_hyde_ollama_client):
        """Test that abstracts shorter than minimum are filtered."""
        generator = HyDEGenerator(model="test-model", num_abstracts=2, max_keywords=5)

        response = json.dumps({
            "hyde_abstracts": [
                "Too short",  # Should be filtered
                "This is a sufficiently long abstract that should pass the minimum length validation check of 100 characters or more."
            ],
            "keywords": ["kw1", "kw2"]
        })

        result = generator._parse_response(response)
        assert len(result["hyde_abstracts"]) == 1

    def test_parse_response_filters_empty_keywords(self, mock_hyde_ollama_client):
        """Test that empty keywords are filtered."""
        generator = HyDEGenerator(model="test-model", num_abstracts=2, max_keywords=5)

        response = json.dumps({
            "hyde_abstracts": [
                "This is a sufficiently long abstract that should pass the minimum length validation check of 100 characters or more."
            ],
            "keywords": ["kw1", "", "  ", "kw2"]
        })

        result = generator._parse_response(response)
        assert len(result["keywords"]) == 2

    def test_parse_response_missing_hyde_abstracts_raises_error(self, mock_hyde_ollama_client):
        """Test that missing hyde_abstracts key raises error."""
        generator = HyDEGenerator(model="test-model")

        response = json.dumps({"keywords": ["kw1"]})

        with pytest.raises(ValueError, match="missing 'hyde_abstracts'"):
            generator._parse_response(response)

    def test_parse_response_missing_keywords_raises_error(self, mock_hyde_ollama_client):
        """Test that missing keywords key raises error."""
        generator = HyDEGenerator(model="test-model")

        response = json.dumps({"hyde_abstracts": ["abstract"]})

        with pytest.raises(ValueError, match="missing 'keywords'"):
            generator._parse_response(response)

    def test_parse_response_no_valid_abstracts_raises_error(self, mock_hyde_ollama_client):
        """Test that having no valid abstracts raises error."""
        generator = HyDEGenerator(model="test-model")

        response = json.dumps({
            "hyde_abstracts": ["short", "also short"],  # All too short
            "keywords": ["kw1", "kw2"]
        })

        with pytest.raises(ValueError, match="No valid HyDE abstracts"):
            generator._parse_response(response)

    def test_parse_response_no_valid_keywords_raises_error(self, mock_hyde_ollama_client):
        """Test that having no valid keywords raises error."""
        generator = HyDEGenerator(model="test-model")

        response = json.dumps({
            "hyde_abstracts": [
                "This is a sufficiently long abstract that should pass the minimum length validation check of 100 characters or more."
            ],
            "keywords": ["", "  "]  # All empty
        })

        with pytest.raises(ValueError, match="No valid keywords"):
            generator._parse_response(response)

    def test_parse_response_invalid_json_raises_error(self, mock_hyde_ollama_client):
        """Test that invalid JSON raises error."""
        generator = HyDEGenerator(model="test-model")

        with pytest.raises(ValueError, match="Invalid JSON"):
            generator._parse_response("not valid json {")

    def test_generate_success(self, mock_hyde_ollama_client, statement_comparative):
        """Test successful HyDE generation."""
        mock_client_instance = MagicMock()
        mock_client_instance.chat.return_value = {
            "message": {
                "content": json.dumps({
                    "hyde_abstracts": [
                        "Background: Comparative studies of diabetes medications have yielded inconsistent results. We conducted a multi-center randomized trial comparing GLP-1 agonists to metformin in type 2 diabetes mellitus. Methods: Patients were randomized to receive either treatment for 24 months. Results: GLP-1 agonists showed superior HbA1c reduction. Conclusion: GLP-1 agonists are at least equivalent to metformin.",
                        "Background: Meta-analysis of diabetes treatment outcomes is needed. Methods: Systematic review of RCTs comparing GLP-1 agonists and metformin. Results: Pooled analysis favors GLP-1 agonists for long-term outcomes. Conclusion: Evidence supports non-inferiority of GLP-1 agonists."
                    ],
                    "keywords": [
                        "GLP-1 receptor agonists",
                        "metformin comparison",
                        "type 2 diabetes mellitus",
                        "long-term outcomes",
                        "cardiovascular outcomes"
                    ]
                })
            }
        }
        mock_hyde_ollama_client.return_value = mock_client_instance

        generator = HyDEGenerator(model="gpt-oss:20b")
        result = generator.generate(
            statement_comparative,
            "GLP-1 agonists are superior or equivalent to metformin"
        )

        assert "hyde_abstracts" in result
        assert "keywords" in result
        assert len(result["hyde_abstracts"]) == 2
        assert len(result["keywords"]) == 5
        mock_client_instance.chat.assert_called_once()

    def test_generate_handles_llm_error(self, mock_hyde_ollama_client, statement_comparative):
        """Test that LLM errors are handled gracefully."""
        mock_client_instance = MagicMock()
        mock_client_instance.chat.side_effect = Exception("Connection failed")
        mock_hyde_ollama_client.return_value = mock_client_instance

        generator = HyDEGenerator(model="gpt-oss:20b")

        with pytest.raises(RuntimeError, match="Failed to generate HyDE materials"):
            generator.generate(statement_comparative, "Counter statement text")

    def test_test_connection_success(self, mock_hyde_ollama_client):
        """Test connection test when successful."""
        mock_client_instance = MagicMock()
        mock_client_instance.list.return_value = {"models": []}
        mock_hyde_ollama_client.return_value = mock_client_instance

        generator = HyDEGenerator(model="test-model")
        assert generator.test_connection() is True

    def test_test_connection_failure(self, mock_hyde_ollama_client):
        """Test connection test when failed."""
        mock_client_instance = MagicMock()
        mock_client_instance.list.side_effect = Exception("Connection refused")
        mock_hyde_ollama_client.return_value = mock_client_instance

        generator = HyDEGenerator(model="test-model")
        assert generator.test_connection() is False


# =============================================================================
# Integration-style Tests (with mocked LLM)
# =============================================================================

class TestCounterStatementWorkflow:
    """Integration-style tests for the counter-statement generation workflow."""

    def test_comparative_claim_generates_logical_negation(self, mock_ollama_client, statement_comparative):
        """Test that comparative claims get logical negations."""
        mock_client_instance = MagicMock()
        mock_client_instance.chat.return_value = {
            "message": {
                "content": "GLP-1 agonists are superior or equivalent to metformin in long-term T2DM outcomes"
            }
        }
        mock_ollama_client.return_value = mock_client_instance

        generator = CounterStatementGenerator(model="gpt-oss:20b")
        result = generator.generate(statement_comparative)

        # Should be a logical negation, not just adding "not"
        assert result != f"not {statement_comparative.text}"
        assert len(result) > 10

    def test_effect_claim_generates_logical_negation(self, mock_ollama_client, statement_effect):
        """Test that effect claims get appropriate negations."""
        mock_client_instance = MagicMock()
        mock_client_instance.chat.return_value = {
            "message": {
                "content": "Exercise does not significantly reduce cardiovascular risk"
            }
        }
        mock_ollama_client.return_value = mock_client_instance

        generator = CounterStatementGenerator(model="gpt-oss:20b")
        result = generator.generate(statement_effect)

        assert len(result) > 10
        assert "exercise" in result.lower()

    def test_hyde_abstracts_are_realistic(self, mock_hyde_ollama_client, statement_comparative):
        """Test that HyDE abstracts have realistic structure."""
        mock_client_instance = MagicMock()
        mock_client_instance.chat.return_value = {
            "message": {
                "content": json.dumps({
                    "hyde_abstracts": [
                        "Background: Prior studies show mixed results. Methods: We conducted a randomized controlled trial with 500 patients over 24 months. Results: GLP-1 agonists demonstrated non-inferior glycemic control with additional weight loss benefits. Conclusion: GLP-1 agonists are a viable alternative to metformin for first-line therapy.",
                        "Background: Systematic review of diabetes treatment. Methods: Meta-analysis of 12 RCTs. Results: Pooled data shows equivalent HbA1c reduction with improved cardiovascular outcomes for GLP-1 agonists. Conclusion: Evidence supports GLP-1 agonists as first-line treatment."
                    ],
                    "keywords": ["GLP-1 agonists", "metformin", "type 2 diabetes"]
                })
            }
        }
        mock_hyde_ollama_client.return_value = mock_client_instance

        generator = HyDEGenerator(model="gpt-oss:20b")
        result = generator.generate(
            statement_comparative,
            "GLP-1 agonists are superior or equivalent to metformin"
        )

        # Abstracts should have structure
        for abstract in result["hyde_abstracts"]:
            assert len(abstract) > 100
            # Should have some common abstract terms
            abstract_lower = abstract.lower()
            has_structure = any(term in abstract_lower for term in
                ["background", "methods", "results", "conclusion", "study", "trial"])
            assert has_structure

    def test_keywords_are_relevant(self, mock_hyde_ollama_client, statement_effect):
        """Test that generated keywords are relevant to the statement."""
        mock_client_instance = MagicMock()
        mock_client_instance.chat.return_value = {
            "message": {
                "content": json.dumps({
                    "hyde_abstracts": [
                        "Background: The relationship between physical activity and cardiovascular disease has been extensively studied. Methods: We performed a meta-analysis of cohort studies. Results: Exercise showed no significant reduction in cardiovascular events. Conclusion: The cardioprotective effect of exercise may be overestimated."
                    ],
                    "keywords": [
                        "exercise cardiovascular",
                        "physical activity heart disease",
                        "cardiovascular risk reduction",
                        "exercise ineffective",
                        "heart disease prevention"
                    ]
                })
            }
        }
        mock_hyde_ollama_client.return_value = mock_client_instance

        generator = HyDEGenerator(model="gpt-oss:20b")
        result = generator.generate(
            statement_effect,
            "Exercise does not significantly reduce cardiovascular risk"
        )

        keywords = result["keywords"]
        assert len(keywords) > 0

        # At least some keywords should be relevant
        keywords_lower = [k.lower() for k in keywords]
        has_exercise_term = any("exercise" in k or "physical" in k for k in keywords_lower)
        has_cardiac_term = any("cardiovascular" in k or "cardiac" in k or "heart" in k for k in keywords_lower)
        assert has_exercise_term or has_cardiac_term


class TestEdgeCases:
    """Edge case tests for counter-statement generation."""

    def test_statement_with_unicode_characters(self, mock_ollama_client):
        """Test handling of unicode characters in statement."""
        mock_client_instance = MagicMock()
        mock_client_instance.chat.return_value = {
            "message": {
                "content": "α-tocopherol does not improve outcomes in β-carotene studies"
            }
        }
        mock_ollama_client.return_value = mock_client_instance

        stmt = Statement(
            text="α-tocopherol improves outcomes in β-carotene studies",
            context="Greek letter test",
            statement_type="finding",
            confidence=0.9,
            statement_order=1
        )

        generator = CounterStatementGenerator(model="test-model")
        result = generator.generate(stmt)

        assert len(result) > 10

    def test_very_long_statement(self, mock_ollama_client):
        """Test handling of very long statements."""
        mock_client_instance = MagicMock()
        mock_client_instance.chat.return_value = {
            "message": {
                "content": "This counter-statement negates the very long original claim"
            }
        }
        mock_ollama_client.return_value = mock_client_instance

        long_text = "This is a very long statement " * 50
        stmt = Statement(
            text=long_text,
            context="Long text context",
            statement_type="finding",
            confidence=0.9,
            statement_order=1
        )

        generator = CounterStatementGenerator(model="test-model")
        result = generator.generate(stmt)

        assert len(result) > 10

    def test_statement_with_special_medical_terminology(self, mock_ollama_client):
        """Test handling of complex medical terminology."""
        mock_client_instance = MagicMock()
        mock_client_instance.chat.return_value = {
            "message": {
                "content": "Anti-VEGF therapy does not improve outcomes in age-related macular degeneration"
            }
        }
        mock_ollama_client.return_value = mock_client_instance

        stmt = Statement(
            text="Anti-VEGF therapy improves visual acuity in age-related macular degeneration",
            context="Ophthalmology study context",
            statement_type="finding",
            confidence=0.92,
            statement_order=1
        )

        generator = CounterStatementGenerator(model="test-model")
        result = generator.generate(stmt)

        assert len(result) > 10
        assert "VEGF" in result or "vegf" in result.lower()

    def test_extract_json_handles_malformed_code_blocks(self, mock_hyde_ollama_client):
        """Test JSON extraction with malformed code blocks."""
        generator = HyDEGenerator(model="test-model")

        # Test with unclosed code block
        response = '```json\n{"hyde_abstracts": ["' + 'A' * 100 + '"], "keywords": ["kw"]}'
        result = generator._extract_json(response)
        assert "hyde_abstracts" in result

    def test_extract_json_finds_json_without_code_block(self, mock_hyde_ollama_client):
        """Test JSON extraction when no code block is present."""
        generator = HyDEGenerator(model="test-model")

        response = 'Here is the response: {"hyde_abstracts": ["' + 'A' * 100 + '"], "keywords": ["kw"]}'
        result = generator._extract_json(response)

        # Should find and extract the JSON object
        data = json.loads(result)
        assert "hyde_abstracts" in data
