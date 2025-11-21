"""
Counter-statement generation component for PaperChecker.

Generates semantically precise negations of research claims. This is a key step
in the PaperChecker workflow, creating counter-statements that can be used to
search for contradictory evidence.

The generator produces logical negations rather than simple grammatical negations:
- Comparative claims (X > Y) become (Y >= X)
- Effect claims (X reduces Y) become (X doesn't reduce Y or X increases Y)
- Association claims become negated associations
"""

import logging
import re
import time
from typing import Any, Dict

import ollama

from ..data_models import Statement

logger = logging.getLogger(__name__)

# Configuration Constants
DEFAULT_TEMPERATURE: float = 0.3
DEFAULT_OLLAMA_URL: str = "http://localhost:11434"
DEFAULT_MAX_RETRIES: int = 3
DEFAULT_RETRY_DELAY_SECONDS: float = 1.0
MIN_COUNTER_STATEMENT_LENGTH: int = 10


class CounterStatementGenerator:
    """
    Generates counter-statements that negate original research claims.

    This component creates semantically precise negations that maintain
    scientific validity. For example:
    - "X is superior to Y" -> "Y is superior or equivalent to X"
    - "X reduces Y by 30%" -> "X does not significantly reduce Y"
    - "High-dose aspirin prevents stroke" -> "High-dose aspirin does not prevent stroke"

    Attributes:
        model: Ollama model name to use for generation
        temperature: LLM temperature (lower = more deterministic)
        host: Ollama server URL
        client: Ollama client instance
    """

    def __init__(
        self,
        model: str,
        temperature: float = DEFAULT_TEMPERATURE,
        host: str = DEFAULT_OLLAMA_URL,
    ):
        """
        Initialize CounterStatementGenerator.

        Args:
            model: Ollama model name (e.g., "gpt-oss:20b")
            temperature: LLM temperature (lower = more deterministic)
            host: Ollama server URL
        """
        self.model = model
        self.temperature = temperature
        self.host = host.rstrip("/")
        self.client = ollama.Client(host=self.host)

    def generate(self, statement: Statement) -> str:
        """
        Generate counter-statement for a given statement.

        Creates a semantically precise negation of the original statement
        that can be used to search for contradictory evidence.

        Args:
            statement: Original Statement object to negate

        Returns:
            Negated statement text

        Raises:
            ValueError: If statement is invalid
            RuntimeError: If generation fails
        """
        logger.info(f"Generating counter-statement for: {statement.text[:50]}...")

        # Validate input
        if not statement.text or not statement.text.strip():
            raise ValueError("Statement text cannot be empty")

        prompt = self._build_negation_prompt(statement)

        try:
            response = self._call_llm(prompt)
            counter_text = self._parse_response(response)

            logger.info(f"Generated counter-statement: {counter_text[:50]}...")
            return counter_text

        except ValueError:
            # Re-raise ValueError as-is (validation errors)
            raise
        except Exception as e:
            logger.error(f"Counter-statement generation failed: {e}", exc_info=True)
            raise RuntimeError(f"Failed to generate counter-statement: {e}") from e

    def _build_negation_prompt(self, statement: Statement) -> str:
        """
        Build prompt for generating counter-statement.

        Creates a comprehensive prompt that guides the LLM to produce
        semantically precise negations rather than simple grammatical ones.

        Args:
            statement: Original Statement object

        Returns:
            Formatted prompt string
        """
        return f"""You are an expert medical researcher. Your task is to create a semantically precise NEGATION of a research claim.

**Important Guidelines:**
1. Maintain scientific precision - don't just add "not"
2. Consider the logical opposite, not just grammatical negation
3. For comparative claims (X > Y), the negation is (Y >= X)
4. For effect claims (X reduces Y), the negation is (X doesn't reduce Y OR X increases Y)
5. For association claims, negate the association
6. Keep the same level of specificity as the original
7. The negation should be a complete, standalone statement

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

- Original: "Vitamin D supplementation improves bone density in elderly patients"
  Negation: "Vitamin D supplementation does not improve bone density in elderly patients"

- Original: "Early intervention leads to better outcomes"
  Negation: "Early intervention does not lead to better outcomes compared to delayed intervention"

**Output Format:**
Return ONLY the negated statement text, nothing else. No JSON, no explanation, just the counter-statement.

**Counter-Statement:**"""

    def _call_llm(
        self,
        prompt: str,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_delay: float = DEFAULT_RETRY_DELAY_SECONDS,
    ) -> str:
        """
        Call Ollama API with prompt using the ollama library.

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

            log_msg = f"Ollama request to {self.model}"
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
                logger.info(f"Ollama response received in {response_time:.2f}ms")
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

    def _parse_response(self, response: str) -> str:
        """
        Extract counter-statement from LLM response.

        Cleans up the response by removing common prefixes, quotes, and
        other formatting artifacts.

        Args:
            response: Raw LLM response string

        Returns:
            Cleaned counter-statement text

        Raises:
            ValueError: If response is too short or empty
        """
        # Clean up response
        counter = response.strip()

        # Remove common prefixes (case-insensitive)
        prefixes = [
            "Counter-statement:",
            "Counter statement:",
            "Negation:",
            "The negated statement is:",
            "Here is the counter-statement:",
            "The counter-statement is:",
            "Negated statement:",
        ]
        counter_lower = counter.lower()
        for prefix in prefixes:
            if counter_lower.startswith(prefix.lower()):
                counter = counter[len(prefix):].strip()
                counter_lower = counter.lower()

        # Remove quotes if present
        if counter.startswith('"') and counter.endswith('"'):
            counter = counter[1:-1].strip()
        elif counter.startswith("'") and counter.endswith("'"):
            counter = counter[1:-1].strip()

        # Remove leading dash or bullet
        if counter.startswith("- "):
            counter = counter[2:].strip()

        # Validate length
        if not counter or len(counter) < MIN_COUNTER_STATEMENT_LENGTH:
            raise ValueError(
                f"Generated counter-statement too short or empty "
                f"(minimum {MIN_COUNTER_STATEMENT_LENGTH} characters, got {len(counter)})"
            )

        return counter

    def test_connection(self) -> bool:
        """
        Test connection to Ollama server.

        Returns:
            True if connection successful, False otherwise
        """
        try:
            self.client.list()
            return True
        except Exception:
            return False
