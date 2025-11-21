# Step 5: Counter-Statement Generation Implementation

## Context

Statement extraction (Step 4) is now complete. We need to generate counter-statements that negate the extracted claims, along with HyDE abstracts and keywords for searching.

## Objective

Implement CounterStatementGenerator and HyDEGenerator components that:
- Generate semantically precise negations of original statements
- Create hypothetical abstracts supporting counter-claims (HyDE)
- Generate targeted keyword lists for literature search
- Handle complex logical negations (not just adding "not")

## Requirements

- LLM-based generation using configured model
- Semantic precision in negations
- Multiple HyDE abstracts per statement (default: 2)
- Keyword diversity (up to 10 keywords)
- JSON structured output

## Implementation Location

Create:
- `src/bmlibrarian/paperchecker/components/counter_statement_generator.py`
- `src/bmlibrarian/paperchecker/components/hyde_generator.py`

## Component 1: CounterStatementGenerator

```python
"""
Counter-statement generation component for PaperChecker

Generates semantically precise negations of research claims.
"""

import json
import logging
from typing import Dict, Any
import requests

from ..data_models import Statement, CounterStatement

logger = logging.getLogger(__name__)


class CounterStatementGenerator:
    """
    Generates counter-statements that negate original research claims

    This component creates semantically precise negations that maintain
    scientific validity. For example:
    - "X is superior to Y" → "Y is superior or equivalent to X"
    - "X reduces Y by 30%" → "X does not significantly reduce Y" or "X increases Y"
    """

    def __init__(
        self,
        model: str,
        temperature: float = 0.3,
        ollama_url: str = "http://localhost:11434"
    ):
        self.model = model
        self.temperature = temperature
        self.ollama_url = ollama_url

    def generate(self, statement: Statement) -> str:
        """
        Generate counter-statement for a given statement

        Args:
            statement: Original Statement object

        Returns:
            Negated statement text

        Raises:
            RuntimeError: If generation fails
        """
        logger.info(f"Generating counter-statement for: {statement.text[:50]}...")

        prompt = self._build_negation_prompt(statement)

        try:
            response = self._call_llm(prompt)
            counter_text = self._parse_response(response)

            logger.info(f"Generated counter-statement: {counter_text[:50]}...")
            return counter_text

        except Exception as e:
            logger.error(f"Counter-statement generation failed: {e}", exc_info=True)
            raise RuntimeError(f"Failed to generate counter-statement: {e}") from e

    def _build_negation_prompt(self, statement: Statement) -> str:
        """Build prompt for generating counter-statement"""
        return f"""You are an expert medical researcher. Your task is to create a semantically precise NEGATION of a research claim.

**Important Guidelines:**
1. Maintain scientific precision - don't just add "not"
2. Consider the logical opposite, not just grammatical negation
3. For comparative claims (X > Y), the negation is (Y ≥ X)
4. For effect claims (X reduces Y), the negation is (X doesn't reduce Y OR X increases Y)
5. For association claims, negate the association
6. Keep the same level of specificity as the original

**Original Statement:**
Type: {statement.statement_type}
Text: {statement.text}

**Context:** {statement.context if statement.context else "N/A"}

**Examples of Good Negations:**
- Original: "Metformin is superior to GLP-1 agonists"
  Negation: "GLP-1 agonists are superior or equivalent to metformin"

- Original: "Exercise reduces cardiovascular risk by 30%"
  Negation: "Exercise does not significantly reduce cardiovascular risk"

- Original: "High-dose aspirin prevents stroke"
  Negation: "High-dose aspirin does not prevent stroke or increases stroke risk"

**Output Format:**
Return ONLY the negated statement text, nothing else. No JSON, no explanation, just the counter-statement.

**Counter-Statement:**"""

    def _call_llm(self, prompt: str) -> str:
        """Call Ollama API"""
        try:
            response = requests.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "temperature": self.temperature,
                    "stream": False
                },
                timeout=60
            )
            response.raise_for_status()
            data = response.json()
            return data.get("response", "").strip()

        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"LLM call failed: {e}") from e

    def _parse_response(self, response: str) -> str:
        """Extract counter-statement from response"""
        # Clean up response
        counter = response.strip()

        # Remove common prefixes
        prefixes = [
            "Counter-statement:",
            "Negation:",
            "The negated statement is:",
            "Here is the counter-statement:"
        ]
        for prefix in prefixes:
            if counter.lower().startswith(prefix.lower()):
                counter = counter[len(prefix):].strip()

        # Remove quotes if present
        if counter.startswith('"') and counter.endswith('"'):
            counter = counter[1:-1]

        if not counter or len(counter) < 10:
            raise ValueError("Generated counter-statement too short or empty")

        return counter
```

## Component 2: HyDEGenerator

```python
"""
HyDE (Hypothetical Document Embeddings) generation for PaperChecker

Generates hypothetical abstracts and keywords that would support counter-statements.
"""

import json
import logging
from typing import List, Dict, Any
import requests

from ..data_models import Statement, CounterStatement

logger = logging.getLogger(__name__)


class HyDEGenerator:
    """
    Generates HyDE abstracts and keywords for counter-evidence search

    HyDE (Hypothetical Document Embeddings) is a technique where we generate
    hypothetical abstracts that WOULD support our counter-claim, then search
    for documents similar to these hypothetical abstracts.
    """

    def __init__(
        self,
        model: str,
        num_abstracts: int = 2,
        max_keywords: int = 10,
        temperature: float = 0.3,
        ollama_url: str = "http://localhost:11434"
    ):
        self.model = model
        self.num_abstracts = num_abstracts
        self.max_keywords = max_keywords
        self.temperature = temperature
        self.ollama_url = ollama_url

    def generate(
        self,
        original_statement: Statement,
        counter_text: str
    ) -> Dict[str, Any]:
        """
        Generate HyDE abstracts and keywords for counter-statement

        Args:
            original_statement: Original Statement object
            counter_text: The counter-statement text

        Returns:
            Dict with 'hyde_abstracts' and 'keywords' keys

        Raises:
            RuntimeError: If generation fails
        """
        logger.info(f"Generating HyDE materials for counter-statement")

        prompt = self._build_hyde_prompt(original_statement, counter_text)

        try:
            response = self._call_llm(prompt)
            materials = self._parse_response(response)

            logger.info(
                f"Generated {len(materials['hyde_abstracts'])} HyDE abstracts, "
                f"{len(materials['keywords'])} keywords"
            )

            return materials

        except Exception as e:
            logger.error(f"HyDE generation failed: {e}", exc_info=True)
            raise RuntimeError(f"Failed to generate HyDE materials: {e}") from e

    def _build_hyde_prompt(self, statement: Statement, counter_text: str) -> str:
        """Build prompt for HyDE generation"""
        return f"""You are an expert medical researcher. Your task is to:
1. Generate {self.num_abstracts} hypothetical research abstracts that would SUPPORT the counter-statement
2. Generate up to {self.max_keywords} keywords for searching literature supporting the counter-statement

**Original Statement:** {statement.text}

**Counter-Statement:** {counter_text}

**Instructions for Hypothetical Abstracts:**
- Write realistic medical research abstracts (150-200 words)
- Include Background, Methods, Results, Conclusion
- Results should clearly support the counter-statement
- Use realistic statistical language (p-values, confidence intervals, effect sizes)
- Make them diverse in methodology (RCT, cohort study, meta-analysis, etc.)

**Instructions for Keywords:**
- Generate {self.max_keywords} search keywords/phrases
- Include medical terminology, drug names, condition names
- Include methodology terms (if relevant)
- Focus on terms that would find evidence SUPPORTING the counter-statement
- Order by importance (most important first)

**Output Format:**
Return ONLY valid JSON in this exact format:
{{
  "hyde_abstracts": [
    "First hypothetical abstract text...",
    "Second hypothetical abstract text..."
  ],
  "keywords": [
    "keyword1",
    "keyword2",
    ...
  ]
}}

Return ONLY the JSON, nothing else."""

    def _call_llm(self, prompt: str) -> str:
        """Call Ollama API"""
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
            raise RuntimeError(f"LLM call failed: {e}") from e

    def _parse_response(self, response: str) -> Dict[str, Any]:
        """Parse HyDE response into abstracts and keywords"""
        try:
            # Extract JSON from response
            response = response.strip()

            if "```json" in response:
                start = response.find("```json") + 7
                end = response.find("```", start)
                response = response[start:end].strip()
            elif "```" in response:
                start = response.find("```") + 3
                end = response.find("```", start)
                response = response[start:end].strip()

            data = json.loads(response)

            # Validate structure
            if "hyde_abstracts" not in data or "keywords" not in data:
                raise ValueError("Response missing required keys")

            # Limit to configured maximums
            hyde_abstracts = data["hyde_abstracts"][:self.num_abstracts]
            keywords = data["keywords"][:self.max_keywords]

            if not hyde_abstracts or not keywords:
                raise ValueError("Empty abstracts or keywords list")

            return {
                "hyde_abstracts": hyde_abstracts,
                "keywords": keywords
            }

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON: {e}")
            logger.debug(f"Raw response: {response}")
            raise ValueError(f"Invalid JSON in response: {e}") from e

        except Exception as e:
            logger.error(f"Failed to parse response: {e}")
            raise ValueError(f"Failed to parse HyDE response: {e}") from e
```

## Integration with PaperCheckerAgent

Update `src/bmlibrarian/paperchecker/agent.py`:

```python
def _generate_counter_statements(
    self, statements: List[Statement]
) -> List[CounterStatement]:
    """
    Step 2: Generate counter-statements for all extracted statements

    For each statement, generates:
    - Semantically precise negation
    - HyDE abstracts that would support the counter-claim
    - Keywords for literature search

    Args:
        statements: List of extracted Statement objects

    Returns:
        List of CounterStatement objects with search materials
    """
    counter_statements = []

    for i, statement in enumerate(statements, 1):
        logger.info(f"Generating counter-statement {i}/{len(statements)}")

        try:
            # Generate negation
            negated_text = self.counter_generator.generate(statement)

            # Generate HyDE materials
            hyde_materials = self.hyde_generator.generate(statement, negated_text)

            # Create CounterStatement object
            counter_stmt = CounterStatement(
                original_statement=statement,
                negated_text=negated_text,
                hyde_abstracts=hyde_materials["hyde_abstracts"],
                keywords=hyde_materials["keywords"],
                generation_metadata={
                    "model": self.model,
                    "temperature": self.agent_config.get("temperature", 0.3),
                    "timestamp": datetime.now().isoformat()
                }
            )

            counter_statements.append(counter_stmt)

            logger.info(
                f"Counter-statement generated: {negated_text[:50]}... "
                f"({len(hyde_materials['hyde_abstracts'])} HyDE, "
                f"{len(hyde_materials['keywords'])} keywords)"
            )

        except Exception as e:
            logger.error(f"Failed to generate counter-statement for statement {i}: {e}")
            raise RuntimeError(f"Counter-statement generation failed: {e}") from e

    return counter_statements
```

## Testing Strategy

Create `tests/test_counter_statement_generator.py`:

```python
"""Tests for counter-statement generation components"""

import pytest
from bmlibrarian.paperchecker.components import (
    CounterStatementGenerator,
    HyDEGenerator
)
from bmlibrarian.paperchecker.data_models import Statement


@pytest.fixture
def statement_comparative():
    """Statement with comparative claim"""
    return Statement(
        text="Metformin is superior to GLP-1 agonists in long-term T2DM outcomes",
        context="...",
        statement_type="finding",
        confidence=0.9,
        statement_order=1
    )


@pytest.fixture
def statement_effect():
    """Statement with effect claim"""
    return Statement(
        text="Exercise reduces cardiovascular risk by 30%",
        context="...",
        statement_type="finding",
        confidence=0.85,
        statement_order=1
    )


def test_counter_generator_comparative(statement_comparative):
    """Test counter-statement generation for comparative claims"""
    generator = CounterStatementGenerator(model="gpt-oss:20b", temperature=0.3)
    counter = generator.generate(statement_comparative)

    assert len(counter) > 10
    assert "glp-1" in counter.lower() or "glp1" in counter.lower()
    assert "metformin" in counter.lower()
    # Should be a logical negation, not just adding "not"
    assert counter != f"not {statement_comparative.text}"


def test_counter_generator_effect(statement_effect):
    """Test counter-statement generation for effect claims"""
    generator = CounterStatementGenerator(model="gpt-oss:20b", temperature=0.3)
    counter = generator.generate(statement_effect)

    assert len(counter) > 10
    assert "exercise" in counter.lower()
    assert "cardiovascular" in counter.lower()


def test_hyde_generator(statement_comparative):
    """Test HyDE abstract and keyword generation"""
    generator = HyDEGenerator(
        model="gpt-oss:20b",
        num_abstracts=2,
        max_keywords=10,
        temperature=0.3
    )

    counter_text = "GLP-1 agonists are superior or equivalent to metformin"
    materials = generator.generate(statement_comparative, counter_text)

    assert "hyde_abstracts" in materials
    assert "keywords" in materials
    assert len(materials["hyde_abstracts"]) == 2
    assert len(materials["keywords"]) <= 10
    assert all(len(abstract) > 100 for abstract in materials["hyde_abstracts"])


def test_hyde_abstracts_realistic(statement_comparative):
    """Test that HyDE abstracts are realistic"""
    generator = HyDEGenerator(
        model="gpt-oss:20b",
        num_abstracts=2,
        max_keywords=10
    )

    counter_text = "GLP-1 agonists are superior to metformin"
    materials = generator.generate(statement_comparative, counter_text)

    # Check for common abstract sections
    abstracts = materials["hyde_abstracts"]
    for abstract in abstracts:
        # Should have some structure
        assert len(abstract) > 100
        # Likely has medical terminology
        assert any(term in abstract.lower() for term in
                   ["patient", "study", "result", "method", "conclusion"])


def test_hyde_keywords_relevant(statement_effect):
    """Test that keywords are relevant"""
    generator = HyDEGenerator(model="gpt-oss:20b", max_keywords=10)

    counter_text = "Exercise does not reduce cardiovascular risk"
    materials = generator.generate(statement_effect, counter_text)

    keywords = materials["keywords"]
    assert len(keywords) > 0

    # Keywords should relate to the topic
    keywords_lower = [k.lower() for k in keywords]
    assert any("exercise" in k or "physical" in k for k in keywords_lower)
    assert any("cardiovascular" in k or "cardiac" in k or "heart" in k
               for k in keywords_lower)
```

## Success Criteria

- [ ] CounterStatementGenerator implemented
- [ ] HyDEGenerator implemented
- [ ] Semantic negation logic working correctly
- [ ] HyDE abstracts realistic and diverse
- [ ] Keywords relevant and ordered by importance
- [ ] Integration with PaperCheckerAgent complete
- [ ] All unit tests passing
- [ ] Tested on diverse statement types
- [ ] Error handling robust
- [ ] Logging comprehensive

## Next Steps

After completing this step, proceed to:
- **Step 6**: HyDE Generation (integrated above)
- **Step 7**: Multi-Strategy Search (07_MULTI_STRATEGY_SEARCH.md)
- Implement the SearchCoordinator for semantic, HyDE, and keyword search
