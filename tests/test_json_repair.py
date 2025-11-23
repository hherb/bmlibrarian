"""
Test JSON repair utilities for handling malformed LLM responses.

Tests cover common LLM JSON errors:
- Missing commas between array elements or object properties
- Trailing commas before closing brackets
- Single quotes instead of double quotes
- Unescaped newlines or tabs in strings
- Truncated JSON (missing closing brackets)
"""

import json
import pytest

from bmlibrarian.utils.json_repair import (
    repair_json,
    safe_json_loads,
    extract_and_repair_json,
    JSONRepairError,
)


class TestRepairJson:
    """Tests for the repair_json function."""

    def test_valid_json_unchanged(self) -> None:
        """Test that valid JSON is returned unchanged."""
        valid_json = '{"key": "value", "list": [1, 2, 3]}'
        result = repair_json(valid_json)
        assert result == valid_json

    def test_trailing_comma_in_object(self) -> None:
        """Test removal of trailing comma in object."""
        malformed = '{"key": "value", "key2": "value2",}'
        result = repair_json(malformed)
        parsed = json.loads(result)
        assert parsed == {"key": "value", "key2": "value2"}

    def test_trailing_comma_in_array(self) -> None:
        """Test removal of trailing comma in array."""
        malformed = '["a", "b", "c",]'
        result = repair_json(malformed)
        parsed = json.loads(result)
        assert parsed == ["a", "b", "c"]

    def test_single_quotes_to_double_quotes(self) -> None:
        """Test conversion of single quotes to double quotes."""
        malformed = "{'key': 'value'}"
        result = repair_json(malformed)
        parsed = json.loads(result)
        assert parsed == {"key": "value"}

    def test_unescaped_newline_in_string(self) -> None:
        """Test escaping of newlines in string values."""
        malformed = '{"text": "line1\nline2"}'
        result = repair_json(malformed)
        parsed = json.loads(result)
        assert parsed == {"text": "line1\nline2"}

    def test_unescaped_tab_in_string(self) -> None:
        """Test escaping of tabs in string values."""
        malformed = '{"text": "col1\tcol2"}'
        result = repair_json(malformed)
        parsed = json.loads(result)
        assert parsed == {"text": "col1\tcol2"}

    def test_truncated_json_array(self) -> None:
        """Test fixing truncated JSON array."""
        malformed = '["item1", "item2"'
        result = repair_json(malformed)
        parsed = json.loads(result)
        assert parsed == ["item1", "item2"]

    def test_truncated_json_object(self) -> None:
        """Test fixing truncated JSON object."""
        malformed = '{"key": "value"'
        result = repair_json(malformed)
        parsed = json.loads(result)
        assert parsed == {"key": "value"}

    def test_missing_comma_between_array_elements(self) -> None:
        """Test adding missing comma between array elements."""
        malformed = '["a" "b" "c"]'
        result = repair_json(malformed)
        parsed = json.loads(result)
        assert parsed == ["a", "b", "c"]

    def test_unquoted_keys(self) -> None:
        """Test quoting unquoted object keys."""
        malformed = '{key: "value", other_key: "value2"}'
        result = repair_json(malformed)
        parsed = json.loads(result)
        assert parsed == {"key": "value", "other_key": "value2"}

    def test_empty_json_raises_error(self) -> None:
        """Test that empty string raises ValueError."""
        with pytest.raises(ValueError, match="empty"):
            repair_json("")

    def test_whitespace_only_raises_error(self) -> None:
        """Test that whitespace-only string raises ValueError."""
        with pytest.raises(ValueError, match="empty"):
            repair_json("   \n\t  ")

    def test_unrepairable_json_raises_error(self) -> None:
        """Test that completely invalid JSON raises JSONRepairError."""
        with pytest.raises(JSONRepairError):
            repair_json("this is not json at all")

    def test_nested_json_with_issues(self) -> None:
        """Test repair of nested JSON with multiple issues."""
        malformed = """{
            'hyde_abstracts': [
                'First abstract text here',
                'Second abstract text here'
            ],
            'keywords': ['keyword1', 'keyword2',]
        }"""
        result = repair_json(malformed)
        parsed = json.loads(result)
        assert "hyde_abstracts" in parsed
        assert len(parsed["hyde_abstracts"]) == 2
        assert len(parsed["keywords"]) == 2


class TestSafeJsonLoads:
    """Tests for the safe_json_loads function."""

    def test_valid_json_parses_directly(self) -> None:
        """Test that valid JSON is parsed without repair."""
        valid = '{"name": "test", "value": 123}'
        result = safe_json_loads(valid)
        assert result == {"name": "test", "value": 123}

    def test_malformed_json_repaired_and_parsed(self) -> None:
        """Test that malformed JSON is repaired before parsing."""
        malformed = "{'name': 'test', 'value': 123,}"
        result = safe_json_loads(malformed)
        assert result == {"name": "test", "value": 123}

    def test_repair_disabled(self) -> None:
        """Test that repair can be disabled."""
        malformed = "{'name': 'test'}"
        with pytest.raises(ValueError, match="Invalid JSON"):
            safe_json_loads(malformed, repair=False)

    def test_empty_raises_error(self) -> None:
        """Test that empty string raises ValueError."""
        with pytest.raises(ValueError, match="empty"):
            safe_json_loads("")


class TestExtractAndRepairJson:
    """Tests for the extract_and_repair_json function."""

    def test_pure_json_response(self) -> None:
        """Test extraction from pure JSON response."""
        response = '{"key": "value"}'
        json_str, was_repaired = extract_and_repair_json(response)
        assert json.loads(json_str) == {"key": "value"}
        assert was_repaired is False

    def test_json_in_code_block(self) -> None:
        """Test extraction from markdown code block."""
        response = """Here is the response:
```json
{"key": "value"}
```
That was the JSON."""
        json_str, was_repaired = extract_and_repair_json(response)
        assert json.loads(json_str) == {"key": "value"}
        assert was_repaired is False

    def test_json_in_plain_code_block(self) -> None:
        """Test extraction from plain code block."""
        response = """Result:
```
{"key": "value"}
```"""
        json_str, was_repaired = extract_and_repair_json(response)
        assert json.loads(json_str) == {"key": "value"}
        assert was_repaired is False

    def test_json_embedded_in_text(self) -> None:
        """Test extraction of JSON embedded in text."""
        response = """The output is {"key": "value"} which shows the result."""
        json_str, was_repaired = extract_and_repair_json(response)
        assert json.loads(json_str) == {"key": "value"}
        assert was_repaired is False

    def test_malformed_json_in_code_block(self) -> None:
        """Test extraction and repair of malformed JSON in code block."""
        response = """```json
{'key': 'value', 'list': [1, 2, 3,]}
```"""
        json_str, was_repaired = extract_and_repair_json(response)
        parsed = json.loads(json_str)
        assert parsed == {"key": "value", "list": [1, 2, 3]}
        assert was_repaired is True

    def test_no_json_raises_error(self) -> None:
        """Test that response without JSON raises ValueError."""
        response = "This response contains no JSON data at all."
        with pytest.raises(ValueError, match="No JSON found"):
            extract_and_repair_json(response)

    def test_empty_response_raises_error(self) -> None:
        """Test that empty response raises ValueError."""
        with pytest.raises(ValueError, match="empty"):
            extract_and_repair_json("")


class TestRealWorldLLMErrors:
    """Tests for real-world LLM JSON errors."""

    def test_hyde_generator_typical_error(self) -> None:
        """Test fixing typical HyDE generator JSON error (missing comma)."""
        # This simulates the actual error that triggered this fix
        malformed = """{
  "hyde_abstracts": [
    "Background: Recent studies have challenged the established understanding of treatment X..."
    "Background: A meta-analysis of randomized controlled trials examining..."
  ],
  "keywords": [
    "treatment X efficacy",
    "randomized controlled trial"
  ]
}"""
        result = repair_json(malformed)
        parsed = json.loads(result)
        assert "hyde_abstracts" in parsed
        assert "keywords" in parsed
        assert len(parsed["hyde_abstracts"]) == 2

    def test_mixed_quote_styles(self) -> None:
        """Test handling mixed single and double quotes."""
        malformed = """{"name": 'John', 'age': 30}"""
        result = repair_json(malformed)
        parsed = json.loads(result)
        assert parsed["name"] == "John"
        assert parsed["age"] == 30

    def test_multi_line_string_values(self) -> None:
        """Test fixing multi-line string values with newlines."""
        malformed = """{
  "abstract": "This is line one.
This is line two.
This is line three."
}"""
        result = repair_json(malformed)
        parsed = json.loads(result)
        assert "line one" in parsed["abstract"]
        assert "line two" in parsed["abstract"]

    def test_complex_nested_structure(self) -> None:
        """Test repair of complex nested structure with multiple issues."""
        malformed = """{
  'statements': [
    {
      'text': 'First statement'
      'type': 'finding',
      'confidence': 0.9,
    },
    {
      'text': 'Second statement',
      'type': 'conclusion'
      'confidence': 0.8
    }
  ]
}"""
        result = repair_json(malformed)
        parsed = json.loads(result)
        assert len(parsed["statements"]) == 2
        assert parsed["statements"][0]["text"] == "First statement"
        assert parsed["statements"][1]["type"] == "conclusion"


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_deeply_nested_json(self) -> None:
        """Test repair of deeply nested JSON."""
        malformed = "{'a': {'b': {'c': {'d': 'value',}},},}"
        result = repair_json(malformed)
        parsed = json.loads(result)
        assert parsed["a"]["b"]["c"]["d"] == "value"

    def test_array_of_objects(self) -> None:
        """Test repair of array of objects with issues."""
        malformed = "[{'name': 'a'}, {'name': 'b',}]"
        result = repair_json(malformed)
        parsed = json.loads(result)
        assert len(parsed) == 2
        assert parsed[0]["name"] == "a"
        assert parsed[1]["name"] == "b"

    def test_special_characters_in_strings(self) -> None:
        """Test that special characters in strings are preserved."""
        valid = '{"text": "Special: @#$%^&*()_+-=[]{}|;:,.<>?"}'
        result = repair_json(valid)
        parsed = json.loads(result)
        assert "@#$%^&*" in parsed["text"]

    def test_unicode_in_strings(self) -> None:
        """Test that unicode characters are preserved."""
        valid = '{"text": "Unicode: émojis 🔬 日本語"}'
        result = repair_json(valid)
        parsed = json.loads(result)
        assert "émojis" in parsed["text"]
        assert "🔬" in parsed["text"]

    def test_boolean_and_null_values(self) -> None:
        """Test that boolean and null values are preserved."""
        malformed = "{'active': true, 'deleted': false, 'data': null,}"
        result = repair_json(malformed)
        parsed = json.loads(result)
        assert parsed["active"] is True
        assert parsed["deleted"] is False
        assert parsed["data"] is None

    def test_numeric_values(self) -> None:
        """Test that numeric values are preserved."""
        malformed = "{'int': 42, 'float': 3.14, 'negative': -10, 'scientific': 1.5e-10,}"
        result = repair_json(malformed)
        parsed = json.loads(result)
        assert parsed["int"] == 42
        assert parsed["float"] == 3.14
        assert parsed["negative"] == -10
        assert parsed["scientific"] == 1.5e-10
