"""
Statement extraction component for PaperChecker.

Extracts core research claims, hypotheses, and findings from medical abstracts
using LLM analysis. This is the first step in the PaperChecker workflow.

The extractor analyzes abstracts to identify the most important research claims,
categorizing them as hypotheses, findings, or conclusions.
"""

import json
import logging
import re
from typing import List

import requests

from ..data_models import Statement, VALID_STATEMENT_TYPES

logger = logging.getLogger(__name__)

# Configuration Constants
DEFAULT_MAX_STATEMENTS: int = 2
DEFAULT_TEMPERATURE: float = 0.3
DEFAULT_OLLAMA_URL: str = "http://localhost:11434"
DEFAULT_TIMEOUT_SECONDS: int = 120
MIN_ABSTRACT_LENGTH: int = 50


class StatementExtractor:
    """
    Extracts core statements from medical abstracts using LLM analysis.

    This component analyzes abstracts to identify the most important research
    claims, categorizing them as hypotheses, findings, or conclusions.

    Attributes:
        model: Ollama model name to use for extraction
        max_statements: Maximum number of statements to extract
        temperature: LLM temperature (lower = more deterministic)
        ollama_url: Ollama server URL
        timeout: Request timeout in seconds
    """

    def __init__(
        self,
        model: str,
        max_statements: int = DEFAULT_MAX_STATEMENTS,
        temperature: float = DEFAULT_TEMPERATURE,
        ollama_url: str = DEFAULT_OLLAMA_URL,
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
    ):
        """
        Initialize StatementExtractor.

        Args:
            model: Ollama model name (e.g., "gpt-oss:20b")
            max_statements: Maximum statements to extract (default: 2)
            temperature: LLM temperature (lower = more deterministic)
            ollama_url: Ollama server URL
            timeout: Request timeout in seconds
        """
        self.model = model
        self.max_statements = max_statements
        self.temperature = temperature
        self.ollama_url = ollama_url.rstrip("/")
        self.timeout = timeout

    def extract(self, abstract: str) -> List[Statement]:
        """
        Extract core statements from abstract.

        Analyzes the provided medical abstract and extracts the most important
        research claims, hypotheses, findings, or conclusions.

        Args:
            abstract: Medical abstract text

        Returns:
            List of Statement objects (up to max_statements)

        Raises:
            ValueError: If abstract is invalid or too short
            RuntimeError: If LLM extraction fails
        """
        logger.info(f"Extracting up to {self.max_statements} statements from abstract")

        # Validate input
        if not abstract or not abstract.strip():
            raise ValueError("Abstract cannot be empty")

        abstract = abstract.strip()
        if len(abstract) < MIN_ABSTRACT_LENGTH:
            raise ValueError(
                f"Abstract too short for meaningful extraction "
                f"(minimum {MIN_ABSTRACT_LENGTH} characters, got {len(abstract)})"
            )

        # Build prompt
        prompt = self._build_extraction_prompt(abstract)

        # Call LLM
        try:
            response = self._call_llm(prompt)
            statements = self._parse_response(response)

            logger.info(f"Successfully extracted {len(statements)} statements")
            return statements

        except ValueError:
            # Re-raise ValueError as-is (validation errors)
            raise
        except Exception as e:
            logger.error(f"Statement extraction failed: {e}", exc_info=True)
            raise RuntimeError(f"Failed to extract statements: {e}") from e

    def _build_extraction_prompt(self, abstract: str) -> str:
        """
        Build LLM prompt for statement extraction.

        Creates a comprehensive prompt that guides the LLM to extract
        specific, testable research claims from the abstract.

        Args:
            abstract: The abstract text to analyze

        Returns:
            Formatted prompt string
        """
        return f"""You are an expert medical researcher analyzing a scientific abstract. Your task is to extract the {self.max_statements} most important research claims from the abstract.

For each statement, identify:
1. The exact text of the claim (verbatim from abstract when possible)
2. Surrounding context (1-2 sentences before/after)
3. Statement type: "hypothesis", "finding", or "conclusion"
4. Your confidence in this extraction (0.0 to 1.0)

**Guidelines:**
- Focus on novel, specific, testable claims
- Prioritize findings and conclusions over background information
- Extract claims that could be fact-checked against scientific literature
- Prefer quantitative claims (e.g., "X reduces Y by 30%") over vague statements
- Avoid extracting methodological statements unless they represent key findings
- The statement text should be self-contained and understandable without the context

**Statement Types:**
- "hypothesis": A proposed explanation or prediction being tested
- "finding": An empirical result or observation from the study
- "conclusion": A summary interpretation or implication drawn from the findings

**Abstract:**
{abstract}

**Output Format:**
Return ONLY valid JSON in this exact format (no additional text, no markdown code blocks):
{{
  "statements": [
    {{
      "text": "The specific claim extracted",
      "context": "Surrounding sentences for context",
      "statement_type": "hypothesis|finding|conclusion",
      "confidence": 0.0-1.0
    }}
  ]
}}

Extract exactly {self.max_statements} statements. Return ONLY the JSON, nothing else."""

    def _call_llm(self, prompt: str) -> str:
        """
        Call Ollama API with prompt.

        Args:
            prompt: The prompt to send to the LLM

        Returns:
            LLM response text

        Raises:
            RuntimeError: If API call fails
        """
        try:
            response = requests.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "temperature": self.temperature,
                    "stream": False,
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
            return data.get("response", "")

        except requests.exceptions.Timeout:
            logger.error(f"Ollama API call timed out after {self.timeout}s")
            raise RuntimeError(f"LLM call timed out after {self.timeout} seconds")
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Failed to connect to Ollama at {self.ollama_url}: {e}")
            raise RuntimeError(
                f"Failed to connect to Ollama server at {self.ollama_url}"
            ) from e
        except requests.exceptions.RequestException as e:
            logger.error(f"Ollama API call failed: {e}")
            raise RuntimeError(f"LLM call failed: {e}") from e

    def _parse_response(self, response: str) -> List[Statement]:
        """
        Parse LLM response into Statement objects.

        Handles various LLM output formats, including responses with
        markdown code blocks or extra text.

        Args:
            response: Raw LLM response string

        Returns:
            List of Statement objects

        Raises:
            ValueError: If response cannot be parsed or contains invalid data
        """
        try:
            # Clean response
            response = response.strip()

            # Try to extract JSON from response
            json_str = self._extract_json(response)

            # Parse JSON
            data = json.loads(json_str)

            if "statements" not in data:
                raise ValueError("Response missing 'statements' key")

            if not isinstance(data["statements"], list):
                raise ValueError("'statements' must be a list")

            statements = []
            for i, stmt_data in enumerate(
                data["statements"][: self.max_statements], 1
            ):
                statement = self._parse_single_statement(stmt_data, i)
                if statement:
                    statements.append(statement)

            if not statements:
                raise ValueError("No valid statements extracted from response")

            return statements

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            logger.debug(f"Raw response: {response}")
            raise ValueError(f"Invalid JSON in LLM response: {e}") from e

    def _extract_json(self, response: str) -> str:
        """
        Extract JSON from response that may contain extra text or code blocks.

        Args:
            response: Raw response string

        Returns:
            Extracted JSON string
        """
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
        # Look for opening and closing braces
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
                        return response[start_idx : i + 1]

        # Return original response as fallback
        return response

    def _parse_single_statement(
        self, stmt_data: dict, order: int
    ) -> Statement | None:
        """
        Parse a single statement from the response data.

        Args:
            stmt_data: Dictionary containing statement data from LLM response
            order: Statement order (1, 2, etc.)

        Returns:
            Statement object, or None if parsing fails
        """
        # Check required fields
        required_fields = ["text", "statement_type", "confidence"]
        missing = [f for f in required_fields if f not in stmt_data]
        if missing:
            logger.warning(f"Statement {order} missing required fields: {missing}")
            return None

        # Validate and normalize statement type
        statement_type = stmt_data["statement_type"].lower().strip()
        if statement_type not in VALID_STATEMENT_TYPES:
            logger.warning(
                f"Statement {order} has invalid type '{statement_type}', "
                f"expected one of {VALID_STATEMENT_TYPES}"
            )
            # Try to infer type from common variations
            statement_type = self._normalize_statement_type(statement_type)
            if statement_type is None:
                return None

        # Validate confidence
        try:
            confidence = float(stmt_data["confidence"])
            if not 0.0 <= confidence <= 1.0:
                logger.warning(
                    f"Statement {order} has invalid confidence {confidence}, clamping"
                )
                confidence = max(0.0, min(1.0, confidence))
        except (ValueError, TypeError):
            logger.warning(
                f"Statement {order} has non-numeric confidence, defaulting to 0.5"
            )
            confidence = 0.5

        # Extract text and context
        text = stmt_data["text"].strip()
        if not text:
            logger.warning(f"Statement {order} has empty text")
            return None

        context = stmt_data.get("context", "").strip()

        # Create Statement object
        try:
            return Statement(
                text=text,
                context=context,
                statement_type=statement_type,
                confidence=confidence,
                statement_order=order,
            )
        except (AssertionError, ValueError) as e:
            logger.warning(f"Failed to create Statement {order}: {e}")
            return None

    def _normalize_statement_type(self, type_str: str) -> str | None:
        """
        Normalize statement type string to valid value.

        Handles common variations and typos in statement types.

        Args:
            type_str: Raw statement type string from LLM

        Returns:
            Normalized statement type, or None if unrecognizable
        """
        type_mapping = {
            # Hypothesis variations
            "hypothesis": "hypothesis",
            "hypotheses": "hypothesis",
            "hypo": "hypothesis",
            "prediction": "hypothesis",
            # Finding variations
            "finding": "finding",
            "findings": "finding",
            "result": "finding",
            "results": "finding",
            "observation": "finding",
            # Conclusion variations
            "conclusion": "conclusion",
            "conclusions": "conclusion",
            "interpretation": "conclusion",
            "implication": "conclusion",
            "summary": "conclusion",
        }

        normalized = type_mapping.get(type_str.lower().strip())
        if normalized:
            logger.debug(f"Normalized statement type '{type_str}' to '{normalized}'")
        return normalized

    def test_connection(self) -> bool:
        """
        Test connection to Ollama server.

        Returns:
            True if connection successful, False otherwise
        """
        try:
            response = requests.get(
                f"{self.ollama_url}/api/tags",
                timeout=10,
            )
            return response.status_code == 200
        except requests.exceptions.RequestException:
            return False
