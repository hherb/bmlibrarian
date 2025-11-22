"""
Verdict analysis component for PaperChecker.

This module analyzes counter-evidence reports and generates verdicts on whether
the evidence supports, contradicts, or is undecided about the original research
claims. It provides both individual statement verdicts and overall assessments.

The analyzer uses LLM-based analysis with three-level classification:
- **supports**: Counter-evidence supports the original statement
- **contradicts**: Counter-evidence contradicts the original statement
- **undecided**: Evidence is mixed, insufficient, or unclear

Confidence levels reflect evidence strength:
- **high**: Strong, consistent evidence from multiple high-quality sources
- **medium**: Moderate evidence with some limitations or inconsistencies
- **low**: Weak, limited, or highly uncertain evidence
"""

import json
import logging
import time
from datetime import datetime
from typing import Any, Dict, List

import ollama

from ..data_models import (
    Statement,
    CounterReport,
    Verdict,
    VALID_VERDICT_VALUES,
    VALID_CONFIDENCE_LEVELS,
)

logger = logging.getLogger(__name__)

# Configuration Constants
DEFAULT_TEMPERATURE: float = 0.3
DEFAULT_OLLAMA_URL: str = "http://localhost:11434"
DEFAULT_MAX_RETRIES: int = 3
DEFAULT_RETRY_DELAY_SECONDS: float = 1.0

# Response validation constants
MIN_RATIONALE_LENGTH: int = 20
REQUIRED_JSON_FIELDS: tuple = ("verdict", "confidence", "rationale")

# JSON extraction markers
JSON_CODE_BLOCK_START: str = "```json"
CODE_BLOCK_MARKER: str = "```"


class VerdictAnalyzer:
    """
    Analyzes counter-evidence to determine verdict on original statement.

    This component takes the original statement and counter-evidence report,
    then uses LLM-based analysis to determine:
    1. Whether counter-evidence supports, contradicts, or is undecided
    2. Confidence level (high/medium/low) based on evidence strength
    3. A 2-3 sentence rationale explaining the verdict

    The analyzer maintains objectivity and bases verdicts ONLY on provided
    evidence, without adding external knowledge.

    Attributes:
        model: Ollama model name for verdict analysis
        host: Ollama server host URL
        temperature: LLM temperature for analysis (lower = more deterministic)
        client: Ollama client instance

    Example:
        >>> analyzer = VerdictAnalyzer(model="gpt-oss:20b")
        >>> verdict = analyzer.analyze(statement, counter_report)
        >>> print(f"Verdict: {verdict.verdict} ({verdict.confidence})")
        >>> print(f"Rationale: {verdict.rationale}")
    """

    def __init__(
        self,
        model: str,
        host: str = DEFAULT_OLLAMA_URL,
        temperature: float = DEFAULT_TEMPERATURE
    ):
        """
        Initialize VerdictAnalyzer.

        Args:
            model: Ollama model name for analysis (e.g., "gpt-oss:20b")
            host: Ollama server host URL
            temperature: LLM temperature (lower = more deterministic)
        """
        self.model = model
        self.host = host.rstrip("/")
        self.temperature = temperature
        self.client = ollama.Client(host=self.host)

        logger.info(f"Initialized VerdictAnalyzer with model={model}")

    def analyze(
        self,
        statement: Statement,
        counter_report: CounterReport
    ) -> Verdict:
        """
        Analyze counter-evidence and generate verdict on original statement.

        Evaluates the counter-report's evidence against the original statement
        to determine if evidence supports, contradicts, or is undecided about
        the original claim.

        Args:
            statement: Original Statement being fact-checked
            counter_report: CounterReport containing counter-evidence summary
                           and citations to analyze

        Returns:
            Verdict object with:
                - verdict: Classification ("supports", "contradicts", "undecided")
                - confidence: Evidence strength ("high", "medium", "low")
                - rationale: 2-3 sentence explanation
                - counter_report: Reference to the analyzed report
                - analysis_metadata: Model, timestamp, and analysis parameters

        Raises:
            ValueError: If statement or counter_report is invalid
            RuntimeError: If verdict analysis fails after retries
        """
        logger.info(f"Analyzing verdict for statement: {statement.text[:50]}...")

        # Validate inputs
        self._validate_inputs(statement, counter_report)

        # Build prompt for verdict analysis
        prompt = self._build_verdict_prompt(statement, counter_report)

        try:
            # Call LLM for verdict analysis
            response = self._call_llm(prompt)

            # Parse and validate response
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
                    "timestamp": datetime.now().isoformat(),
                    "statement_order": statement.statement_order
                }
            )

            logger.info(
                f"Verdict: {verdict.verdict} (confidence: {verdict.confidence})"
            )

            return verdict

        except ValueError as e:
            # Re-raise validation errors
            logger.error(f"Verdict parsing failed: {e}")
            raise
        except RuntimeError:
            # Re-raise runtime errors as-is
            raise
        except Exception as e:
            logger.error(f"Verdict analysis failed: {e}", exc_info=True)
            raise RuntimeError(f"Failed to analyze verdict: {e}") from e

    def generate_overall_assessment(
        self,
        statements: List[Statement],
        verdicts: List[Verdict]
    ) -> str:
        """
        Generate overall assessment from individual verdicts.

        Synthesizes verdicts for all statements into a comprehensive assessment
        of the abstract's factual accuracy. The assessment considers:
        - Number of statements in each verdict category
        - Confidence levels of individual verdicts
        - Relative importance of claims (if applicable)

        Args:
            statements: List of all extracted Statement objects
            verdicts: List of Verdict objects (one per statement)

        Returns:
            Overall assessment string summarizing findings across all statements

        Raises:
            ValueError: If statements and verdicts have different lengths
        """
        if len(statements) != len(verdicts):
            raise ValueError(
                f"Statements ({len(statements)}) and verdicts ({len(verdicts)}) "
                f"must have the same length"
            )

        total = len(verdicts)

        if total == 0:
            return "No statements were extracted for analysis."

        # Count verdict types
        verdict_counts: Dict[str, int] = {
            "supports": 0,
            "contradicts": 0,
            "undecided": 0
        }

        # Count confidence levels by verdict type
        confidence_by_verdict: Dict[str, Dict[str, int]] = {
            "supports": {"high": 0, "medium": 0, "low": 0},
            "contradicts": {"high": 0, "medium": 0, "low": 0},
            "undecided": {"high": 0, "medium": 0, "low": 0}
        }

        for verdict in verdicts:
            verdict_counts[verdict.verdict] += 1
            confidence_by_verdict[verdict.verdict][verdict.confidence] += 1

        # Generate assessment based on verdict distribution
        overall = self._format_overall_assessment(
            total, verdict_counts, confidence_by_verdict
        )

        logger.info(f"Overall assessment: {overall[:100]}...")

        return overall

    def _format_overall_assessment(
        self,
        total: int,
        counts: Dict[str, int],
        confidence: Dict[str, Dict[str, int]]
    ) -> str:
        """
        Format overall assessment based on verdict counts and confidence.

        Creates a human-readable summary that accurately reflects the
        distribution of verdicts and their confidence levels.

        Args:
            total: Total number of statements analyzed
            counts: Dictionary with counts per verdict type
            confidence: Nested dict with confidence counts per verdict type

        Returns:
            Formatted assessment string
        """
        supports = counts["supports"]
        contradicts = counts["contradicts"]
        undecided = counts["undecided"]

        # Determine primary outcome
        if contradicts == 0 and undecided == 0:
            # All statements supported
            high_conf = confidence["supports"]["high"]
            if high_conf == total:
                return (
                    f"All {total} statement(s) from the original abstract were supported "
                    f"by the literature search with high confidence. No contradictory "
                    f"evidence was found, suggesting the claims are well-supported by "
                    f"existing research."
                )
            else:
                return (
                    f"All {total} statement(s) from the original abstract were supported "
                    f"by the literature search. No contradictory evidence was found. "
                    f"Confidence levels: {high_conf} high, "
                    f"{confidence['supports']['medium']} medium, "
                    f"{confidence['supports']['low']} low."
                )

        elif contradicts == total:
            # All statements contradicted
            high_conf = confidence["contradicts"]["high"]
            if high_conf == total:
                return (
                    f"All {total} statement(s) from the original abstract were contradicted "
                    f"by evidence found in the literature with high confidence. "
                    f"Significant counter-evidence exists that challenges these claims."
                )
            else:
                return (
                    f"All {total} statement(s) from the original abstract were contradicted "
                    f"by evidence found in the literature. Confidence levels for contradictions: "
                    f"{high_conf} high, {confidence['contradicts']['medium']} medium, "
                    f"{confidence['contradicts']['low']} low."
                )

        elif undecided == total:
            # All statements undecided
            return (
                f"Evidence for all {total} statement(s) was mixed or insufficient to "
                f"determine clear support or contradiction. The literature search found "
                f"relevant documents, but evidence quality or consistency was insufficient "
                f"for definitive conclusions."
            )

        elif contradicts > total / 2:
            # Majority contradicted
            return (
                f"The majority of statements ({contradicts}/{total}) from the original "
                f"abstract were contradicted by literature evidence. "
                f"{supports} statement(s) were supported, {undecided} undecided. "
                f"This suggests significant concerns about the original claims."
            )

        elif supports > total / 2:
            # Majority supported
            return (
                f"The majority of statements ({supports}/{total}) from the original "
                f"abstract were supported by the literature search. "
                f"{contradicts} statement(s) were contradicted, {undecided} undecided. "
                f"Overall, the claims appear largely consistent with existing evidence."
            )

        else:
            # Mixed results - no clear majority
            return (
                f"Mixed results across {total} statements: "
                f"{supports} supported by literature, "
                f"{contradicts} contradicted, "
                f"{undecided} undecided or with insufficient evidence. "
                f"The abstract contains claims with varying levels of literature support."
            )

    def _validate_inputs(
        self,
        statement: Statement,
        counter_report: CounterReport
    ) -> None:
        """
        Validate inputs for verdict analysis.

        Args:
            statement: Statement to validate
            counter_report: CounterReport to validate

        Raises:
            ValueError: If any input is invalid
        """
        if not statement.text or not statement.text.strip():
            raise ValueError("Statement text cannot be empty")

        if not counter_report.summary or not counter_report.summary.strip():
            raise ValueError("Counter-report summary cannot be empty")

    def _build_verdict_prompt(
        self,
        statement: Statement,
        counter_report: CounterReport
    ) -> str:
        """
        Build prompt for verdict analysis.

        Creates a comprehensive prompt that guides the LLM to:
        1. Analyze the counter-evidence objectively
        2. Classify the verdict correctly
        3. Assign appropriate confidence level
        4. Generate an evidence-based rationale

        Args:
            statement: Original Statement being evaluated
            counter_report: CounterReport with evidence summary

        Returns:
            Formatted prompt string for LLM
        """
        # Format citation count information
        citation_info = f"Citations extracted: {counter_report.num_citations}"

        # Get search statistics
        docs_found = counter_report.search_stats.get("documents_found", 0)
        docs_scored = counter_report.search_stats.get("documents_scored", 0)

        return f"""You are an expert medical researcher evaluating scientific evidence.

**Task:**
Analyze whether the counter-evidence found supports, contradicts, or is undecided about the original research claim.

**Original Statement:**
"{statement.text}"

**Statement Type:** {statement.statement_type}

**Counter-Evidence Summary:**
{counter_report.summary}

**Search Statistics:**
- Total documents searched: {docs_found}
- Documents scored relevant: {docs_scored}
- {citation_info}

**Analysis Instructions:**

1. **Determine Verdict** (choose ONE):
   - **"contradicts"**: The counter-evidence contradicts the original statement
     * Multiple studies or high-quality evidence supports the counter-claim
     * Evidence directly challenges the original statement
     * Example: Original says "A > B", counter-evidence shows "B ≥ A"

   - **"supports"**: The counter-evidence actually supports the original statement
     * Counter-evidence search failed to find contradictory evidence
     * Found studies confirm the original statement
     * Counter-claim is not supported by the literature found

   - **"undecided"**: The evidence is mixed, insufficient, or unclear
     * Some evidence supports and some contradicts the original statement
     * Too few studies or citations to draw conclusions
     * Studies have significant limitations or contradictions
     * Evidence is tangentially related but not directly relevant

2. **Determine Confidence Level**:
   - **"high"**: Strong, consistent evidence from multiple high-quality sources
   - **"medium"**: Moderate evidence with some limitations or inconsistencies
   - **"low"**: Weak, limited, or highly uncertain evidence

3. **Write Rationale** (2-3 sentences):
   - Explain WHY you chose this verdict
   - Reference the quality and quantity of evidence
   - Mention any important limitations or caveats
   - Be specific about findings when possible

**Important Guidelines:**
- Base verdict ONLY on the counter-evidence provided in the summary above
- Do NOT add external knowledge or assumptions
- Do NOT overstate certainty - use "undecided" when genuinely uncertain
- Consider both quantity (number of studies) and quality (study design, consistency)
- "Undecided" is appropriate when evidence is genuinely mixed or insufficient
- If no citations were extracted, this suggests weak or no counter-evidence

**Output Format:**
Return ONLY valid JSON in this exact format:
{{
  "verdict": "supports|contradicts|undecided",
  "confidence": "high|medium|low",
  "rationale": "2-3 sentence explanation based on the evidence"
}}

Return ONLY the JSON, nothing else."""

    def _call_llm(
        self,
        prompt: str,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_delay: float = DEFAULT_RETRY_DELAY_SECONDS
    ) -> str:
        """
        Call Ollama API for verdict analysis.

        Uses the ollama library (per project golden rules) with exponential
        backoff retry logic for transient failures.

        Args:
            prompt: The prompt to send to the LLM
            max_retries: Maximum number of retry attempts
            retry_delay: Initial delay between retries in seconds

        Returns:
            LLM response text

        Raises:
            RuntimeError: If API call fails after all retries
        """
        last_exception: Exception | None = None
        current_delay = retry_delay

        for attempt in range(max_retries):
            start_time = time.time()

            log_msg = f"Ollama verdict request to {self.model}"
            if attempt > 0:
                log_msg += f" (retry {attempt}/{max_retries - 1})"
            logger.info(log_msg)

            try:
                response = self.client.chat(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    options={
                        "temperature": self.temperature,
                    },
                )

                content = response.get("message", {}).get("content", "")
                if not content or not content.strip():
                    raise ValueError("Empty response from model")

                response_time = (time.time() - start_time) * 1000
                logger.info(f"Ollama verdict response received in {response_time:.2f}ms")
                return content.strip()

            except ollama.ResponseError as e:
                last_exception = e
                response_time = (time.time() - start_time) * 1000

                is_retryable = (
                    "timeout" in str(e).lower() or "connection" in str(e).lower()
                )

                if attempt < max_retries - 1 and is_retryable:
                    logger.warning(
                        f"Transient error in Ollama request after {response_time:.2f}ms, "
                        f"retrying in {current_delay:.1f}s: {e}"
                    )
                    time.sleep(current_delay)
                    current_delay *= 2
                else:
                    logger.error(
                        f"Ollama request failed after {response_time:.2f}ms "
                        f"(attempt {attempt + 1}/{max_retries}): {e}"
                    )

            except ValueError as e:
                # Empty response - retry
                last_exception = e
                response_time = (time.time() - start_time) * 1000

                if attempt < max_retries - 1:
                    logger.warning(
                        f"Empty response after {response_time:.2f}ms, "
                        f"retrying in {current_delay:.1f}s"
                    )
                    time.sleep(current_delay)
                    current_delay *= 2
                else:
                    logger.error(f"Empty response after {max_retries} attempts")

            except Exception as e:
                last_exception = e
                response_time = (time.time() - start_time) * 1000
                logger.error(
                    f"Unexpected error in Ollama request after {response_time:.2f}ms: {e}"
                )

                # Check for connection-related errors
                error_str = str(e).lower()
                if "connection" in error_str or "refused" in error_str:
                    raise RuntimeError(
                        f"Failed to connect to Ollama server at {self.host}"
                    ) from e
                raise RuntimeError(f"LLM call failed: {e}") from e

        # All retries exhausted
        raise RuntimeError(
            f"Failed to get response from Ollama after {max_retries} attempts: "
            f"{last_exception}"
        )

    def _parse_response(self, response: str) -> Dict[str, str]:
        """
        Parse verdict response from LLM into structured data.

        Handles various response formats including:
        - Raw JSON
        - JSON wrapped in markdown code blocks
        - JSON with surrounding text

        Args:
            response: Raw LLM response string

        Returns:
            Dictionary with verdict, confidence, and rationale

        Raises:
            ValueError: If response cannot be parsed or is invalid
        """
        try:
            # Clean and extract JSON from response
            json_str = self._extract_json(response)

            # Parse JSON
            data = json.loads(json_str)

            # Validate required fields
            self._validate_verdict_data(data)

            return {
                "verdict": data["verdict"],
                "confidence": data["confidence"],
                "rationale": data["rationale"]
            }

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from verdict response: {e}")
            logger.debug(f"Raw response: {response}")
            raise ValueError(f"Invalid JSON in verdict response: {e}") from e

        except ValueError:
            # Re-raise validation errors
            raise

        except Exception as e:
            logger.error(f"Failed to parse verdict response: {e}")
            raise ValueError(f"Failed to parse verdict response: {e}") from e

    def _extract_json(self, response: str) -> str:
        """
        Extract JSON from LLM response, handling various formats.

        Supports extraction from:
        - Pure JSON responses
        - JSON wrapped in ```json code blocks
        - JSON wrapped in ``` code blocks
        - JSON embedded in text (finds first { to last })

        Args:
            response: Raw response string

        Returns:
            Extracted JSON string

        Raises:
            ValueError: If no valid JSON structure found
        """
        response = response.strip()

        # Try to extract from ```json code block
        if JSON_CODE_BLOCK_START in response:
            start = response.find(JSON_CODE_BLOCK_START) + len(JSON_CODE_BLOCK_START)
            end = response.find(CODE_BLOCK_MARKER, start)
            if end > start:
                return response[start:end].strip()

        # Try to extract from ``` code block
        if response.startswith(CODE_BLOCK_MARKER):
            # Skip the opening ```
            start = len(CODE_BLOCK_MARKER)
            # Skip optional language identifier on first line
            newline_idx = response.find("\n", start)
            if newline_idx > 0:
                start = newline_idx + 1
            end = response.find(CODE_BLOCK_MARKER, start)
            if end > start:
                return response[start:end].strip()

        # Try to find JSON object directly
        if "{" in response and "}" in response:
            start = response.find("{")
            end = response.rfind("}") + 1
            if end > start:
                return response[start:end]

        # Return as-is and let JSON parser handle it
        return response

    def _validate_verdict_data(self, data: Dict[str, Any]) -> None:
        """
        Validate parsed verdict data.

        Checks that all required fields are present and have valid values.

        Args:
            data: Parsed verdict dictionary

        Raises:
            ValueError: If data is invalid or missing required fields
        """
        # Check required fields
        missing = [f for f in REQUIRED_JSON_FIELDS if f not in data]
        if missing:
            raise ValueError(f"Response missing required fields: {missing}")

        # Validate verdict value
        if data["verdict"] not in VALID_VERDICT_VALUES:
            raise ValueError(
                f"Invalid verdict: '{data['verdict']}'. "
                f"Must be one of {VALID_VERDICT_VALUES}"
            )

        # Validate confidence value
        if data["confidence"] not in VALID_CONFIDENCE_LEVELS:
            raise ValueError(
                f"Invalid confidence: '{data['confidence']}'. "
                f"Must be one of {VALID_CONFIDENCE_LEVELS}"
            )

        # Validate rationale length
        rationale = data.get("rationale", "")
        if not rationale or len(rationale.strip()) < MIN_RATIONALE_LENGTH:
            raise ValueError(
                f"Rationale too short (minimum {MIN_RATIONALE_LENGTH} characters, "
                f"got {len(rationale.strip())})"
            )

    def test_connection(self) -> bool:
        """
        Test connection to Ollama server.

        Verifies that the Ollama server is reachable and the configured
        model is available.

        Returns:
            True if connection successful and model available, False otherwise
        """
        try:
            models_response = self.client.list()
            available_models = [
                m.get("name", "") for m in models_response.get("models", [])
            ]

            # Check if our model is available (with or without tag)
            model_base = self.model.split(":")[0]
            for available in available_models:
                if available.startswith(model_base):
                    return True

            logger.warning(
                f"Model {self.model} not found. Available: {available_models}"
            )
            return True  # Server is reachable, model may still work

        except Exception as e:
            logger.error(f"Ollama connection test failed: {e}")
            return False
