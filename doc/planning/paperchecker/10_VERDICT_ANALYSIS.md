# Step 10: Verdict Analysis Implementation

## Context

Counter-reports have been generated (Step 9). Now we need to analyze whether the counter-evidence supports, contradicts, or is undecided about the original statement.

## Objective

Implement VerdictAnalyzer component that:
- Analyzes counter-report against original statement
- Classifies as supports/contradicts/undecided
- Provides confidence level (high/medium/low)
- Generates evidence-based rationale (2-3 sentences)
- Maintains objectivity and scientific rigor

## Requirements

- LLM-based analysis
- Three-level verdict classification
- Confidence scoring
- Rationale generation
- JSON structured output

## Implementation Location

Create: `src/bmlibrarian/paperchecker/components/verdict_analyzer.py`

## Component Design

```python
"""
Verdict analysis component for PaperChecker

Analyzes counter-evidence reports to determine if they support, contradict,
or are undecided about the original research claim.
"""

import json
import logging
from typing import Dict, Any
import requests

from ..data_models import Statement, CounterReport, Verdict

logger = logging.getLogger(__name__)


class VerdictAnalyzer:
    """
    Analyzes counter-evidence to determine verdict on original statement

    Three verdict categories:
    - **supports**: Counter-evidence supports the original statement (contradicts the counter-claim)
    - **contradicts**: Counter-evidence contradicts the original statement (supports the counter-claim)
    - **undecided**: Counter-evidence is mixed, insufficient, or unclear

    Three confidence levels:
    - **high**: Strong, consistent evidence; multiple high-quality studies
    - **medium**: Moderate evidence; some limitations or inconsistencies
    - **low**: Weak evidence; few studies or significant limitations
    """

    def __init__(
        self,
        model: str,
        temperature: float = 0.3,
        ollama_url: str = "http://localhost:11434"
    ):
        """
        Initialize VerdictAnalyzer

        Args:
            model: Ollama model name
            temperature: LLM temperature (lower = more deterministic)
            ollama_url: Ollama server URL
        """
        self.model = model
        self.temperature = temperature
        self.ollama_url = ollama_url

    def analyze(
        self, statement: Statement, counter_report: CounterReport
    ) -> Verdict:
        """
        Analyze counter-report to determine verdict on original statement

        Args:
            statement: Original Statement being evaluated
            counter_report: CounterReport with counter-evidence

        Returns:
            Verdict object with classification, confidence, and rationale

        Raises:
            RuntimeError: If verdict analysis fails
        """
        logger.info(f"Analyzing verdict for statement: {statement.text[:50]}...")

        # Build prompt
        prompt = self._build_verdict_prompt(statement, counter_report)

        try:
            # Call LLM
            response = self._call_llm(prompt)

            # Parse response
            verdict_data = self._parse_response(response)

            # Create Verdict object
            verdict = Verdict(
                verdict=verdict_data["verdict"],
                rationale=verdict_data["rationale"],
                confidence=verdict_data["confidence"],
                counter_report=counter_report,
                analysis_metadata={
                    "model": self.model,
                    "temperature": self.temperature,
                    "timestamp": datetime.now().isoformat()
                }
            )

            logger.info(
                f"Verdict: {verdict.verdict} (confidence: {verdict.confidence})"
            )

            return verdict

        except Exception as e:
            logger.error(f"Verdict analysis failed: {e}", exc_info=True)
            raise RuntimeError(f"Failed to analyze verdict: {e}") from e

    def _build_verdict_prompt(
        self, statement: Statement, counter_report: CounterReport
    ) -> str:
        """Build prompt for verdict analysis"""

        return f"""You are an expert medical researcher evaluating scientific evidence.

**Task:**
Analyze whether the counter-evidence found supports, contradicts, or is undecided about the original research claim.

**Original Statement:**
"{statement.text}"

**Counter-Evidence Summary:**
{counter_report.summary}

**References Found:**
- Total documents searched: {counter_report.search_stats['documents_found']}
- Documents scored relevant: {counter_report.search_stats['documents_scored']}
- Citations extracted: {counter_report.num_citations}

**Analysis Instructions:**

1. **Determine Verdict** (choose ONE):
   - **"contradicts"**: The counter-evidence contradicts the original statement
     * Multiple high-quality studies support the counter-claim
     * Evidence directly challenges the original statement
     * Example: Original says "A > B", counter-evidence shows "B ≥ A"

   - **"supports"**: The counter-evidence actually supports the original statement
     * Counter-evidence search failed to find contradictory evidence
     * Found studies confirm the original statement
     * Counter-claim is not supported by literature

   - **"undecided"**: The evidence is mixed, insufficient, or unclear
     * Some evidence for and against the original statement
     * Too few studies to draw conclusions
     * Studies have significant limitations or contradictions
     * Evidence is tangentially related but not directly relevant

2. **Determine Confidence Level**:
   - **"high"**: Strong, consistent evidence from multiple high-quality sources
   - **"medium"**: Moderate evidence with some limitations or inconsistencies
   - **"low"**: Weak, limited, or highly uncertain evidence

3. **Write Rationale** (2-3 sentences):
   - Explain WHY you chose this verdict
   - Reference the quality and quantity of evidence
   - Mention any limitations or caveats
   - Be specific about findings when possible

**Important Guidelines:**
- Base verdict ONLY on the counter-evidence provided
- Do NOT add external knowledge
- Do NOT overstate certainty
- Consider both quantity (# studies) and quality (study design, effect sizes)
- "Undecided" is appropriate when evidence is genuinely mixed or insufficient

**Output Format:**
Return ONLY valid JSON in this exact format:
{{
  "verdict": "supports|contradicts|undecided",
  "confidence": "high|medium|low",
  "rationale": "2-3 sentence explanation based on the evidence"
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
                timeout=90
            )
            response.raise_for_status()
            data = response.json()
            return data.get("response", "").strip()

        except requests.exceptions.RequestException as e:
            logger.error(f"Ollama API call failed: {e}")
            raise RuntimeError(f"LLM call failed: {e}") from e

    def _parse_response(self, response: str) -> Dict[str, str]:
        """Parse verdict response into structured data"""
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

            # Validate required fields
            required = ["verdict", "confidence", "rationale"]
            if not all(k in data for k in required):
                raise ValueError(f"Response missing required fields: {required}")

            # Validate verdict value
            if data["verdict"] not in ["supports", "contradicts", "undecided"]:
                raise ValueError(f"Invalid verdict: {data['verdict']}")

            # Validate confidence value
            if data["confidence"] not in ["high", "medium", "low"]:
                raise ValueError(f"Invalid confidence: {data['confidence']}")

            # Validate rationale length
            if len(data["rationale"].strip()) < 20:
                raise ValueError("Rationale too short")

            return data

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON: {e}")
            logger.debug(f"Raw response: {response}")
            raise ValueError(f"Invalid JSON in response: {e}") from e

        except Exception as e:
            logger.error(f"Failed to parse verdict response: {e}")
            raise ValueError(f"Failed to parse response: {e}") from e
```

## Integration with PaperCheckerAgent

Update `src/bmlibrarian/paperchecker/agent.py`:

```python
def _analyze_verdict(
    self, statement: Statement, counter_report: CounterReport
) -> Verdict:
    """
    Step 7: Analyze verdict on original statement

    Uses VerdictAnalyzer to determine if the counter-evidence supports,
    contradicts, or is undecided about the original statement.

    Args:
        statement: Original Statement being evaluated
        counter_report: CounterReport with counter-evidence

    Returns:
        Verdict object with classification, confidence, and rationale

    Raises:
        RuntimeError: If verdict analysis fails
    """
    try:
        verdict = self.verdict_analyzer.analyze(statement, counter_report)

        logger.info(
            f"Verdict: {verdict.verdict} ({verdict.confidence} confidence)\n"
            f"Rationale: {verdict.rationale}"
        )

        return verdict

    except RuntimeError as e:
        logger.error(f"Verdict analysis failed: {e}")
        raise

def _generate_overall_assessment(
    self, statements: List[Statement], verdicts: List[Verdict]
) -> str:
    """
    Step 8: Generate overall assessment across all statements

    Synthesizes verdicts for all statements into a single overall assessment
    of the abstract's factual accuracy.

    Args:
        statements: List of original Statement objects
        verdicts: List of Verdict objects (one per statement)

    Returns:
        Overall assessment string

    Raises:
        ValueError: If statements and verdicts length mismatch
    """
    if len(statements) != len(verdicts):
        raise ValueError("Statements and verdicts must have same length")

    # Count verdict types
    verdict_counts = {
        "supports": 0,
        "contradicts": 0,
        "undecided": 0
    }

    for verdict in verdicts:
        verdict_counts[verdict.verdict] += 1

    # Determine overall assessment
    total = len(verdicts)

    if verdict_counts["contradicts"] == 0:
        # No contradictory evidence found
        overall = (
            f"All {total} statement(s) from the original abstract were supported "
            f"by the literature search. No contradictory evidence was found."
        )
    elif verdict_counts["contradicts"] == total:
        # All statements contradicted
        overall = (
            f"All {total} statement(s) from the original abstract were contradicted "
            f"by evidence found in the literature. Significant counter-evidence exists."
        )
    elif verdict_counts["contradicts"] > total / 2:
        # Majority contradicted
        overall = (
            f"The majority of statements ({verdict_counts['contradicts']}/{total}) "
            f"from the original abstract were contradicted by literature evidence. "
            f"{verdict_counts['supports']} supported, {verdict_counts['undecided']} undecided."
        )
    elif verdict_counts["undecided"] == total:
        # All undecided
        overall = (
            f"Evidence for all {total} statement(s) was mixed or insufficient to "
            f"determine clear support or contradiction."
        )
    else:
        # Mixed results
        overall = (
            f"Mixed results across {total} statements: "
            f"{verdict_counts['supports']} supported by literature, "
            f"{verdict_counts['contradicts']} contradicted, "
            f"{verdict_counts['undecided']} undecided or insufficient evidence."
        )

    logger.info(f"Overall assessment: {overall}")

    return overall
```

## Testing Strategy

Create `tests/test_verdict_analyzer.py`:

```python
"""Tests for VerdictAnalyzer component"""

import pytest
from bmlibrarian.paperchecker.components import VerdictAnalyzer
from bmlibrarian.paperchecker.data_models import Statement, CounterReport, ExtractedCitation


@pytest.fixture
def analyzer():
    """Create VerdictAnalyzer instance"""
    return VerdictAnalyzer(model="gpt-oss:20b", temperature=0.3)


@pytest.fixture
def statement():
    """Sample statement"""
    return Statement(
        text="Metformin is superior to GLP-1 agonists",
        context="",
        statement_type="finding",
        confidence=0.9,
        statement_order=1
    )


@pytest.fixture
def strong_counter_report():
    """Counter-report with strong contradictory evidence"""
    citations = [
        ExtractedCitation(
            doc_id=1,
            passage="GLP-1 superior to metformin (p<0.001)",
            relevance_score=5,
            full_citation="Smith 2023",
            metadata={},
            citation_order=1
        ),
        ExtractedCitation(
            doc_id=2,
            passage="Meta-analysis shows GLP-1 better outcomes",
            relevance_score=5,
            full_citation="Jones 2022",
            metadata={},
            citation_order=2
        )
    ]

    return CounterReport(
        summary="Strong evidence from multiple RCTs shows GLP-1 superior...",
        num_citations=2,
        citations=citations,
        search_stats={"documents_found": 50, "documents_scored": 20, "citations_extracted": 2},
        generation_metadata={}
    )


@pytest.fixture
def weak_counter_report():
    """Counter-report with weak evidence"""
    return CounterReport(
        summary="Limited evidence suggests possible advantage for GLP-1, but studies are small...",
        num_citations=1,
        citations=[
            ExtractedCitation(
                doc_id=1,
                passage="Small study (n=50) suggested possible benefit",
                relevance_score=3,
                full_citation="Small 2021",
                metadata={},
                citation_order=1
            )
        ],
        search_stats={"documents_found": 10, "documents_scored": 2, "citations_extracted": 1},
        generation_metadata={}
    )


def test_analyze_strong_contradiction(analyzer, statement, strong_counter_report):
    """Test verdict analysis with strong contradictory evidence"""
    verdict = analyzer.analyze(statement, strong_counter_report)

    assert verdict.verdict == "contradicts"
    assert verdict.confidence in ["high", "medium"]
    assert len(verdict.rationale) > 20


def test_analyze_weak_evidence(analyzer, statement, weak_counter_report):
    """Test verdict analysis with weak evidence"""
    verdict = analyzer.analyze(statement, weak_counter_report)

    # Should be either undecided or low confidence contradiction
    assert verdict.verdict in ["undecided", "contradicts"]
    if verdict.verdict == "contradicts":
        assert verdict.confidence == "low"


def test_verdict_structure(analyzer, statement, strong_counter_report):
    """Test verdict object structure"""
    verdict = analyzer.analyze(statement, strong_counter_report)

    assert hasattr(verdict, "verdict")
    assert hasattr(verdict, "confidence")
    assert hasattr(verdict, "rationale")
    assert hasattr(verdict, "counter_report")
    assert hasattr(verdict, "analysis_metadata")

    # Verify valid values
    assert verdict.verdict in ["supports", "contradicts", "undecided"]
    assert verdict.confidence in ["high", "medium", "low"]


def test_build_verdict_prompt(analyzer, statement, strong_counter_report):
    """Test verdict prompt construction"""
    prompt = analyzer._build_verdict_prompt(statement, strong_counter_report)

    # Should contain original statement
    assert "Metformin is superior to GLP-1 agonists" in prompt

    # Should contain counter-evidence
    assert strong_counter_report.summary in prompt

    # Should contain search stats
    assert str(strong_counter_report.search_stats["documents_found"]) in prompt

    # Should contain instructions
    assert "verdict" in prompt.lower()
    assert "confidence" in prompt.lower()
    assert "rationale" in prompt.lower()


def test_parse_valid_response(analyzer):
    """Test parsing valid JSON response"""
    response = '''
    {
      "verdict": "contradicts",
      "confidence": "high",
      "rationale": "Multiple high-quality RCTs demonstrate clear superiority of GLP-1 over metformin with consistent findings."
    }
    '''

    data = analyzer._parse_response(response)

    assert data["verdict"] == "contradicts"
    assert data["confidence"] == "high"
    assert len(data["rationale"]) > 20


def test_parse_response_with_code_blocks(analyzer):
    """Test parsing response wrapped in code blocks"""
    response = '''```json
    {
      "verdict": "undecided",
      "confidence": "low",
      "rationale": "Evidence is mixed with limited high-quality studies."
    }
    ```'''

    data = analyzer._parse_response(response)

    assert data["verdict"] == "undecided"
    assert data["confidence"] == "low"


def test_parse_invalid_verdict(analyzer):
    """Test parsing with invalid verdict value"""
    response = '''{"verdict": "maybe", "confidence": "high", "rationale": "Test"}'''

    with pytest.raises(ValueError, match="Invalid verdict"):
        analyzer._parse_response(response)


def test_parse_invalid_confidence(analyzer):
    """Test parsing with invalid confidence value"""
    response = '''{"verdict": "contradicts", "confidence": "very high", "rationale": "Test"}'''

    with pytest.raises(ValueError, match="Invalid confidence"):
        analyzer._parse_response(response)


def test_parse_short_rationale(analyzer):
    """Test parsing with too-short rationale"""
    response = '''{"verdict": "contradicts", "confidence": "high", "rationale": "Short"}'''

    with pytest.raises(ValueError, match="too short"):
        analyzer._parse_response(response)
```

## Success Criteria

- [ ] VerdictAnalyzer component implemented
- [ ] Verdict classification logic working
- [ ] Confidence scoring appropriate
- [ ] Rationale generation meaningful
- [ ] Integration with PaperCheckerAgent complete
- [ ] Overall assessment generation working
- [ ] All unit tests passing
- [ ] Verdicts are objective and evidence-based
- [ ] JSON parsing robust to LLM variations

## Next Steps

After completing this step, proceed to:
- **Step 11**: Database Integration (11_DATABASE_INTEGRATION.md)
- Implement PaperCheckDB class for persisting all results
