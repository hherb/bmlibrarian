# Step 4: Statement Extraction Implementation

## Context

Core PaperCheckerAgent structure (Step 3) is now defined. We need to implement the first workflow step: extracting core statements from medical abstracts.

## Objective

Implement the StatementExtractor component and the `_extract_statements()` method that:
- Analyzes abstracts for key research claims
- Identifies hypotheses, findings, and conclusions
- Extracts configurable number of statements (default: 2)
- Provides confidence scores for extractions
- Handles edge cases (short abstracts, unclear claims)

## Requirements

- LLM-based extraction using configured model
- Structured output parsing (JSON)
- Confidence scoring
- Comprehensive prompt engineering
- Error handling for malformed LLM outputs

## Implementation Location

Create: `src/bmlibrarian/paperchecker/components/statement_extractor.py`

## Component Design

```python
"""
Statement extraction component for PaperChecker

Extracts core research claims, hypotheses, and findings from medical abstracts.
"""

import json
import logging
from typing import List, Dict, Any
import requests

from ..data_models import Statement

logger = logging.getLogger(__name__)


class StatementExtractor:
    """
    Extracts core statements from medical abstracts using LLM analysis

    This component analyzes abstracts to identify the most important research
    claims, categorizing them as hypotheses, findings, or conclusions.
    """

    def __init__(
        self,
        model: str,
        max_statements: int = 2,
        temperature: float = 0.3,
        ollama_url: str = "http://localhost:11434"
    ):
        """
        Initialize StatementExtractor

        Args:
            model: Ollama model name
            max_statements: Maximum statements to extract (default: 2)
            temperature: LLM temperature (lower = more deterministic)
            ollama_url: Ollama server URL
        """
        self.model = model
        self.max_statements = max_statements
        self.temperature = temperature
        self.ollama_url = ollama_url

    def extract(self, abstract: str) -> List[Statement]:
        """
        Extract core statements from abstract

        Args:
            abstract: Medical abstract text

        Returns:
            List of Statement objects (up to max_statements)

        Raises:
            ValueError: If abstract is invalid
            RuntimeError: If LLM extraction fails
        """
        logger.info(f"Extracting up to {self.max_statements} statements from abstract")

        # Validate input
        if not abstract or len(abstract.strip()) < 50:
            raise ValueError("Abstract too short for meaningful extraction")

        # Build prompt
        prompt = self._build_extraction_prompt(abstract)

        # Call LLM
        try:
            response = self._call_llm(prompt)
            statements = self._parse_response(response, abstract)

            logger.info(f"Successfully extracted {len(statements)} statements")
            return statements

        except Exception as e:
            logger.error(f"Statement extraction failed: {e}", exc_info=True)
            raise RuntimeError(f"Failed to extract statements: {e}") from e

    def _build_extraction_prompt(self, abstract: str) -> str:
        """Build LLM prompt for statement extraction"""
        return f"""You are an expert medical researcher analyzing a scientific abstract. Your task is to extract the {self.max_statements} most important research claims from the abstract.

For each statement, identify:
1. The exact text of the claim (verbatim from abstract when possible)
2. Surrounding context (1-2 sentences before/after)
3. Statement type: "hypothesis", "finding", or "conclusion"
4. Your confidence in this extraction (0.0 to 1.0)

**Guidelines:**
- Focus on novel, specific, testable claims
- Prioritize findings and conclusions over background
- Extract claims that could be fact-checked against literature
- Prefer quantitative claims (e.g., "X reduces Y by 30%") over vague ones
- Avoid extracting methodological statements unless they're key findings

**Abstract:**
{abstract}

**Output Format:**
Return ONLY valid JSON in this exact format (no additional text):
{{
  "statements": [
    {{
      "text": "The specific claim extracted",
      "context": "Surrounding sentences for context",
      "statement_type": "hypothesis|finding|conclusion",
      "confidence": 0.0-1.0,
      "statement_order": 1
    }},
    ...
  ]
}}

Extract exactly {self.max_statements} statements. Return ONLY the JSON, nothing else."""

    def _call_llm(self, prompt: str) -> str:
        """Call Ollama API with prompt"""
        try:
            response = requests.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "temperature": self.temperature,
                    "stream": False
                },
                timeout=120
            )
            response.raise_for_status()
            data = response.json()
            return data.get("response", "")

        except requests.exceptions.RequestException as e:
            logger.error(f"Ollama API call failed: {e}")
            raise RuntimeError(f"LLM call failed: {e}") from e

    def _parse_response(self, response: str, original_abstract: str) -> List[Statement]:
        """Parse LLM response into Statement objects"""
        try:
            # Extract JSON from response (might have extra text)
            response = response.strip()

            # Try to find JSON block
            if "```json" in response:
                start = response.find("```json") + 7
                end = response.find("```", start)
                response = response[start:end].strip()
            elif "```" in response:
                start = response.find("```") + 3
                end = response.find("```", start)
                response = response[start:end].strip()

            # Parse JSON
            data = json.loads(response)

            if "statements" not in data:
                raise ValueError("Response missing 'statements' key")

            statements = []
            for i, stmt_data in enumerate(data["statements"][:self.max_statements], 1):
                # Validate required fields
                if not all(k in stmt_data for k in ["text", "statement_type", "confidence"]):
                    logger.warning(f"Statement {i} missing required fields, skipping")
                    continue

                # Create Statement object
                statement = Statement(
                    text=stmt_data["text"].strip(),
                    context=stmt_data.get("context", "").strip(),
                    statement_type=stmt_data["statement_type"],
                    confidence=float(stmt_data["confidence"]),
                    statement_order=i
                )

                statements.append(statement)

            if not statements:
                raise ValueError("No valid statements extracted")

            return statements

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            logger.debug(f"Raw response: {response}")
            raise ValueError(f"Invalid JSON in LLM response: {e}") from e

        except Exception as e:
            logger.error(f"Failed to parse response: {e}")
            raise ValueError(f"Failed to parse extraction response: {e}") from e
```

## Integration with PaperCheckerAgent

Update `src/bmlibrarian/paperchecker/agent.py`:

```python
def _extract_statements(self, abstract: str) -> List[Statement]:
    """
    Step 1: Extract core statements from abstract

    Uses StatementExtractor to identify the most important research claims
    in the abstract for fact-checking.

    Args:
        abstract: The abstract text

    Returns:
        List of Statement objects (up to max_statements)
    """
    try:
        statements = self.statement_extractor.extract(abstract)

        logger.info(
            f"Extracted {len(statements)} statements: "
            f"{[s.statement_type for s in statements]}"
        )

        return statements

    except ValueError as e:
        logger.error(f"Invalid abstract for extraction: {e}")
        raise

    except RuntimeError as e:
        logger.error(f"Extraction failed: {e}")
        raise
```

## Component Module Structure

Create `src/bmlibrarian/paperchecker/components/__init__.py`:

```python
"""
PaperChecker workflow components

This package contains the modular components that implement each step
of the PaperChecker workflow.
"""

from .statement_extractor import StatementExtractor

__all__ = [
    "StatementExtractor"
]
```

## Testing Strategy

Create `tests/test_statement_extractor.py`:

```python
"""Tests for StatementExtractor component"""

import pytest
from bmlibrarian.paperchecker.components import StatementExtractor
from bmlibrarian.paperchecker.data_models import Statement


@pytest.fixture
def extractor():
    """Create StatementExtractor instance"""
    return StatementExtractor(
        model="gpt-oss:20b",
        max_statements=2,
        temperature=0.3
    )


@pytest.fixture
def sample_abstract():
    """Sample medical abstract for testing"""
    return """
    Background: Type 2 diabetes management requires effective long-term
    glycemic control. Objective: To compare the efficacy of metformin versus
    GLP-1 receptor agonists in long-term outcomes. Methods: Retrospective
    cohort study of 10,000 patients over 5 years. Results: Metformin
    demonstrated superior HbA1c reduction (1.5% vs 1.2%, p<0.001) and lower
    cardiovascular events (HR 0.75, 95% CI 0.65-0.85). Conclusion: Metformin
    shows superior long-term efficacy compared to GLP-1 agonists for T2DM.
    """


def test_extract_valid_abstract(extractor, sample_abstract):
    """Test extraction from valid abstract"""
    statements = extractor.extract(sample_abstract)

    assert len(statements) <= 2
    assert all(isinstance(s, Statement) for s in statements)
    assert all(s.statement_type in ["hypothesis", "finding", "conclusion"]
               for s in statements)
    assert all(0.0 <= s.confidence <= 1.0 for s in statements)
    assert all(s.statement_order >= 1 for s in statements)


def test_extract_short_abstract(extractor):
    """Test extraction fails on too-short abstract"""
    with pytest.raises(ValueError, match="too short"):
        extractor.extract("Very short abstract.")


def test_extract_empty_abstract(extractor):
    """Test extraction fails on empty abstract"""
    with pytest.raises(ValueError):
        extractor.extract("")


def test_extract_respects_max_statements(sample_abstract):
    """Test that extraction respects max_statements limit"""
    extractor = StatementExtractor(
        model="gpt-oss:20b",
        max_statements=1,
        temperature=0.3
    )

    statements = extractor.extract(sample_abstract)
    assert len(statements) <= 1


def test_statement_types_valid(extractor, sample_abstract):
    """Test that statement types are valid"""
    statements = extractor.extract(sample_abstract)

    valid_types = {"hypothesis", "finding", "conclusion"}
    for statement in statements:
        assert statement.statement_type in valid_types


def test_confidence_scores_valid(extractor, sample_abstract):
    """Test that confidence scores are in valid range"""
    statements = extractor.extract(sample_abstract)

    for statement in statements:
        assert 0.0 <= statement.confidence <= 1.0


def test_statement_order_sequential(extractor, sample_abstract):
    """Test that statement orders are sequential"""
    statements = extractor.extract(sample_abstract)

    orders = [s.statement_order for s in statements]
    assert orders == list(range(1, len(statements) + 1))


def test_extraction_deterministic(extractor, sample_abstract):
    """Test that low temperature gives consistent results"""
    # Run extraction twice
    statements1 = extractor.extract(sample_abstract)
    statements2 = extractor.extract(sample_abstract)

    # Should extract same number of statements
    assert len(statements1) == len(statements2)

    # Statement types should be similar (allowing some variation)
    types1 = [s.statement_type for s in statements1]
    types2 = [s.statement_type for s in statements2]
    # At least 50% overlap expected
    overlap = len(set(types1) & set(types2)) / len(types1)
    assert overlap >= 0.5
```

## Prompt Engineering Guidelines

### Key Prompt Elements:

1. **Role Definition**: "You are an expert medical researcher"
2. **Task Clarity**: "Extract the N most important research claims"
3. **Output Format**: Explicit JSON schema with examples
4. **Guidelines**: Specific rules for what to extract/avoid
5. **Constraints**: "Return ONLY valid JSON, nothing else"

### Prompt Iteration Strategy:

1. **Initial Testing**: Test on 10 diverse abstracts
2. **Failure Analysis**: Identify common parsing errors
3. **Refinement**: Adjust prompt based on failures
4. **Validation**: Re-test on same abstracts
5. **Production**: Deploy with confidence

### Common Issues and Solutions:

| Issue | Solution |
|-------|----------|
| LLM adds commentary | Add "Return ONLY the JSON, nothing else" |
| Invalid JSON | Add explicit schema and format example |
| Extracts background info | Add "Prioritize findings and conclusions" |
| Vague statements | Add "Prefer quantitative, testable claims" |
| Too many statements | Add "Extract exactly N statements" |

## Success Criteria

- [ ] StatementExtractor component implemented
- [ ] Prompt engineering complete and tested
- [ ] JSON parsing robust to LLM variations
- [ ] Integration with PaperCheckerAgent working
- [ ] All unit tests passing (>90% coverage)
- [ ] Tested on 10+ diverse abstracts
- [ ] Error handling comprehensive
- [ ] Logging informative
- [ ] Documentation complete

## Next Steps

After completing this step, proceed to:
- **Step 5**: Counter-Statement Generation (05_COUNTER_STATEMENT_GENERATION.md)
- Implement the `_generate_counter_statements()` method
