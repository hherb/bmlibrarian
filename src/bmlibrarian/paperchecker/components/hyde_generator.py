"""
HyDE (Hypothetical Document Embeddings) generation for PaperChecker.

Generates hypothetical abstracts and keywords that would support counter-statements.
HyDE is a technique where we generate hypothetical documents that WOULD support
our counter-claim, then search for real documents similar to these hypotheticals.

This approach often finds more relevant evidence than direct keyword search because
the hypothetical documents capture the semantic structure and terminology that
real supporting evidence would use.
"""

import json
import logging
import re
import time
from typing import Dict, List

import ollama

from ..data_models import Statement

logger = logging.getLogger(__name__)

# Configuration Constants
DEFAULT_NUM_ABSTRACTS: int = 2
DEFAULT_MAX_KEYWORDS: int = 10
DEFAULT_TEMPERATURE: float = 0.3
DEFAULT_OLLAMA_URL: str = "http://localhost:11434"
DEFAULT_MAX_RETRIES: int = 3
DEFAULT_RETRY_DELAY_SECONDS: float = 1.0
MIN_ABSTRACT_LENGTH: int = 100


class HyDEGenerator:
    """
    Generates HyDE abstracts and keywords for counter-evidence search.

    HyDE (Hypothetical Document Embeddings) is a technique where we generate
    hypothetical abstracts that WOULD support our counter-claim, then search
    for documents similar to these hypothetical abstracts. This captures
    semantic similarity better than pure keyword search.

    Attributes:
        model: Ollama model name to use for generation
        num_abstracts: Number of hypothetical abstracts to generate
        max_keywords: Maximum number of keywords to generate
        temperature: LLM temperature (lower = more deterministic)
        host: Ollama server URL
        client: Ollama client instance
    """

    def __init__(
        self,
        model: str,
        num_abstracts: int = DEFAULT_NUM_ABSTRACTS,
        max_keywords: int = DEFAULT_MAX_KEYWORDS,
        temperature: float = DEFAULT_TEMPERATURE,
        host: str = DEFAULT_OLLAMA_URL,
    ):
        """
        Initialize HyDEGenerator.

        Args:
            model: Ollama model name (e.g., "gpt-oss:20b")
            num_abstracts: Number of hypothetical abstracts to generate (default: 2)
            max_keywords: Maximum keywords to generate (default: 10)
            temperature: LLM temperature (lower = more deterministic)
            host: Ollama server URL
        """
        self.model = model
        self.num_abstracts = num_abstracts
        self.max_keywords = max_keywords
        self.temperature = temperature
        self.host = host.rstrip("/")
        self.client = ollama.Client(host=self.host)

    def generate(
        self,
        original_statement: Statement,
        counter_text: str,
    ) -> Dict[str, List[str]]:
        """
        Generate HyDE abstracts and keywords for counter-statement.

        Creates hypothetical research abstracts that would support the
        counter-claim, along with targeted keywords for literature search.

        Args:
            original_statement: Original Statement object
            counter_text: The counter-statement text to generate materials for

        Returns:
            Dict with 'hyde_abstracts' (List[str]) and 'keywords' (List[str])

        Raises:
            ValueError: If inputs are invalid
            RuntimeError: If generation fails
        """
        logger.info("Generating HyDE materials for counter-statement")

        # Validate inputs
        if not counter_text or not counter_text.strip():
            raise ValueError("Counter-statement text cannot be empty")

        prompt = self._build_hyde_prompt(original_statement, counter_text)

        try:
            response = self._call_llm(prompt)
            materials = self._parse_response(response)

            logger.info(
                f"Generated {len(materials['hyde_abstracts'])} HyDE abstracts, "
                f"{len(materials['keywords'])} keywords"
            )

            return materials

        except ValueError:
            # Re-raise ValueError as-is (validation errors)
            raise
        except Exception as e:
            logger.error(f"HyDE generation failed: {e}", exc_info=True)
            raise RuntimeError(f"Failed to generate HyDE materials: {e}") from e

    def _build_hyde_prompt(self, statement: Statement, counter_text: str) -> str:
        """
        Build prompt for HyDE generation.

        Creates a comprehensive prompt that guides the LLM to generate
        realistic hypothetical abstracts and relevant keywords.

        Args:
            statement: Original Statement object
            counter_text: Counter-statement text

        Returns:
            Formatted prompt string
        """
        return f"""You are an expert medical researcher. Your task is to:
1. Generate {self.num_abstracts} hypothetical research abstracts that would SUPPORT the counter-statement
2. Generate up to {self.max_keywords} keywords for searching literature supporting the counter-statement

**Original Statement:** {statement.text}

**Counter-Statement:** {counter_text}

**Instructions for Hypothetical Abstracts:**
- Write realistic medical research abstracts (150-200 words each)
- Each abstract should follow standard structure: Background, Methods, Results, Conclusion
- Results should clearly support the counter-statement
- Use realistic statistical language (p-values, confidence intervals, effect sizes)
- Make them diverse in methodology (e.g., RCT, cohort study, meta-analysis, systematic review)
- Use appropriate medical terminology and clinical context
- Include realistic patient populations and sample sizes
- The abstracts should read as if they are from real published studies

**Instructions for Keywords:**
- Generate up to {self.max_keywords} search keywords/phrases
- Include relevant medical terminology, drug names, condition names
- Include methodology terms if relevant (e.g., "randomized controlled trial")
- Focus on terms that would find evidence SUPPORTING the counter-statement
- Order by importance (most important first)
- Mix specific terms with broader concepts
- Include both MeSH-style terms and natural language variations

**Output Format:**
Return ONLY valid JSON in this exact format (no additional text):
{{
  "hyde_abstracts": [
    "First hypothetical abstract text supporting the counter-statement...",
    "Second hypothetical abstract text with different methodology..."
  ],
  "keywords": [
    "most important keyword",
    "second keyword",
    "additional relevant terms..."
  ]
}}

Return ONLY the JSON, nothing else."""

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

    def _parse_response(self, response: str) -> Dict[str, List[str]]:
        """
        Parse HyDE response into abstracts and keywords.

        Extracts JSON from the response and validates the structure.

        Args:
            response: Raw LLM response string

        Returns:
            Dict with 'hyde_abstracts' and 'keywords' lists

        Raises:
            ValueError: If response cannot be parsed or is invalid
        """
        try:
            # Clean response and extract JSON
            json_str = self._extract_json(response)

            # Parse JSON
            data = json.loads(json_str)

            # Validate structure
            if "hyde_abstracts" not in data:
                raise ValueError("Response missing 'hyde_abstracts' key")
            if "keywords" not in data:
                raise ValueError("Response missing 'keywords' key")

            if not isinstance(data["hyde_abstracts"], list):
                raise ValueError("'hyde_abstracts' must be a list")
            if not isinstance(data["keywords"], list):
                raise ValueError("'keywords' must be a list")

            # Extract and validate abstracts
            hyde_abstracts = []
            for i, abstract in enumerate(data["hyde_abstracts"][:self.num_abstracts]):
                if isinstance(abstract, str) and len(abstract.strip()) >= MIN_ABSTRACT_LENGTH:
                    hyde_abstracts.append(abstract.strip())
                else:
                    logger.warning(
                        f"HyDE abstract {i+1} is too short or invalid, skipping"
                    )

            # Extract and validate keywords
            keywords = []
            for keyword in data["keywords"][:self.max_keywords]:
                if isinstance(keyword, str) and len(keyword.strip()) > 0:
                    keywords.append(keyword.strip())

            # Validate we have minimum required content
            if not hyde_abstracts:
                raise ValueError("No valid HyDE abstracts in response")
            if not keywords:
                raise ValueError("No valid keywords in response")

            return {
                "hyde_abstracts": hyde_abstracts,
                "keywords": keywords,
            }

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON: {e}")
            logger.debug(f"Raw response: {response}")
            raise ValueError(f"Invalid JSON in response: {e}") from e

    def _extract_json(self, response: str) -> str:
        """
        Extract JSON from response that may contain extra text or code blocks.

        Args:
            response: Raw response string

        Returns:
            Extracted JSON string
        """
        response = response.strip()

        # Try to find JSON in code blocks first
        if "```json" in response:
            match = re.search(r"```json\s*([\s\S]*?)\s*```", response)
            if match:
                return match.group(1).strip()

        if "```" in response:
            match = re.search(r"```\s*([\s\S]*?)\s*```", response)
            if match:
                content = match.group(1).strip()
                if content.startswith("{"):
                    return content

        # Try to find JSON object directly
        start_idx = response.find("{")
        if start_idx != -1:
            # Find matching closing brace
            brace_count = 0
            for i, char in enumerate(response[start_idx:], start_idx):
                if char == "{":
                    brace_count += 1
                elif char == "}":
                    brace_count -= 1
                    if brace_count == 0:
                        return response[start_idx:i + 1]

        # Return original response as fallback
        return response

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
