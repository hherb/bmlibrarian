"""
Summary Generator for Paper Reviewer

Generates brief 2-3 sentence summaries and extracts core hypotheses from papers.
"""

import json
import logging
from typing import Dict, Any, Optional, Callable, Tuple

from ..base import BaseAgent
from ...config import get_model, get_agent_config, get_ollama_host

logger = logging.getLogger(__name__)


# Constants
MAX_TEXT_LENGTH = 12000  # Maximum characters to analyze
DEFAULT_TEMPERATURE = 0.1  # Low temperature for consistent output
DEFAULT_MAX_TOKENS = 1500


class SummaryGenerator(BaseAgent):
    """
    Generates brief summaries and extracts core hypotheses from papers.

    Uses LLM to:
    1. Generate a concise 2-3 sentence summary
    2. Extract the core statement/hypothesis
    """

    VERSION = "1.0.0"

    def __init__(
        self,
        model: Optional[str] = None,
        host: Optional[str] = None,
        temperature: float = DEFAULT_TEMPERATURE,
        top_p: float = 0.9,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        callback: Optional[Callable[[str, str], None]] = None,
        orchestrator: Optional[Any] = None,
        show_model_info: bool = True,
    ):
        """
        Initialize the SummaryGenerator.

        Args:
            model: LLM model name (default: from config)
            host: Ollama server host URL (default: from config)
            temperature: Model temperature (default: 0.1)
            top_p: Model top-p sampling parameter
            max_tokens: Maximum tokens for response
            callback: Optional callback for progress updates
            orchestrator: Optional orchestrator for queue-based processing
            show_model_info: Whether to display model information
        """
        # Get defaults from config if not provided
        if model is None:
            model = get_model('paper_reviewer')
        if host is None:
            host = get_ollama_host()

        super().__init__(
            model=model,
            host=host,
            temperature=temperature,
            top_p=top_p,
            callback=callback,
            orchestrator=orchestrator,
            show_model_info=show_model_info,
        )

        self.max_tokens = max_tokens

    def get_agent_type(self) -> str:
        """Get the agent type identifier."""
        return "summary_generator"

    def generate_summary(
        self,
        document: Dict[str, Any],
        include_methodology: bool = True,
    ) -> Tuple[str, float]:
        """
        Generate a concise 2-3 sentence summary of the paper.

        Args:
            document: Document dictionary with title, abstract, and optionally full_text
            include_methodology: Whether to mention methodology in summary

        Returns:
            Tuple of (summary_text, confidence_score)
        """
        self._call_callback("summary_started", "Generating brief summary")

        # Get text to analyze
        text = self._get_analysis_text(document)
        if not text:
            logger.warning("No text available for summarization")
            return "No text available for summarization.", 0.0

        title = document.get('title', 'Untitled')

        prompt = f"""You are a medical research summarizer. Create a brief 2-3 sentence summary of this paper.

Paper Title: {title}

Paper Text:
{text}

INSTRUCTIONS:
1. Summarize in exactly 2-3 sentences (no more, no less)
2. First sentence: What type of study and what population/topic
3. Second sentence: Main intervention/method and key finding
4. Optional third sentence: Important implication or limitation

Requirements:
- Be specific with numbers and results where available
- Use past tense for completed studies
- Avoid vague phrases like "this study examines" - state what was found
- Keep it under 100 words total

Response format (JSON only):
{{
    "summary": "Your 2-3 sentence summary here",
    "confidence": 0.85
}}

The confidence score (0.0-1.0) reflects:
- 0.9-1.0: Clear, complete information available
- 0.7-0.8: Good information but some details missing
- 0.5-0.6: Limited information, summary may be incomplete
- <0.5: Insufficient information for accurate summary

Respond ONLY with valid JSON. No additional text."""

        try:
            result = self._generate_and_parse_json(
                prompt,
                max_retries=3,
                retry_context="summary generation",
                num_predict=self.max_tokens,
            )

            summary = result.get('summary', '').strip()
            confidence = float(result.get('confidence', 0.7))

            self._call_callback(
                "summary_completed",
                f"Generated summary ({len(summary)} chars, confidence: {confidence:.0%})"
            )

            return summary, confidence

        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Failed to generate summary: {e}")
            return "Failed to generate summary due to processing error.", 0.0

    def extract_hypothesis(
        self,
        document: Dict[str, Any],
    ) -> Tuple[str, float]:
        """
        Extract the core statement/hypothesis from the paper.

        Args:
            document: Document dictionary with title, abstract, and optionally full_text

        Returns:
            Tuple of (hypothesis_text, confidence_score)
        """
        self._call_callback("hypothesis_started", "Extracting core hypothesis")

        # Get text to analyze
        text = self._get_analysis_text(document)
        if not text:
            logger.warning("No text available for hypothesis extraction")
            return "No hypothesis could be extracted.", 0.0

        title = document.get('title', 'Untitled')

        prompt = f"""You are a medical research analyst. Extract the core statement or hypothesis from this paper.

Paper Title: {title}

Paper Text:
{text}

INSTRUCTIONS:
1. Identify the main claim, hypothesis, or central statement of the paper
2. Express it as a clear, testable statement
3. If it's an observational study without explicit hypothesis, state what the study claims to show
4. For systematic reviews/meta-analyses, state the main conclusion

Types of core statements to identify:
- **Primary hypothesis**: "Drug X reduces mortality in patients with condition Y"
- **Main finding claim**: "Higher levels of marker Z are associated with increased risk of disease W"
- **Intervention effect**: "Intervention A is more effective than intervention B for outcome C"
- **Causal claim**: "Factor X contributes to the development of condition Y"

Requirements:
- Be specific and testable
- Include the direction of effect if applicable (increases, decreases, is associated with)
- Include the population/context if specified
- Keep to 1-2 sentences maximum

Response format (JSON only):
{{
    "hypothesis": "The core statement/hypothesis here",
    "hypothesis_type": "primary_hypothesis|main_finding|intervention_effect|causal_claim|other",
    "confidence": 0.85,
    "reasoning": "Brief explanation of why this was identified as the core statement"
}}

The confidence score (0.0-1.0) reflects:
- 0.9-1.0: Explicitly stated hypothesis/conclusion
- 0.7-0.8: Clear main finding, implicitly stated
- 0.5-0.6: Inferred from results, not explicitly stated
- <0.5: Unclear or ambiguous

Respond ONLY with valid JSON. No additional text."""

        try:
            result = self._generate_and_parse_json(
                prompt,
                max_retries=3,
                retry_context="hypothesis extraction",
                num_predict=self.max_tokens,
            )

            hypothesis = result.get('hypothesis', '').strip()
            confidence = float(result.get('confidence', 0.7))
            hypothesis_type = result.get('hypothesis_type', 'other')

            self._call_callback(
                "hypothesis_completed",
                f"Extracted {hypothesis_type} hypothesis (confidence: {confidence:.0%})"
            )

            logger.info(
                f"Extracted hypothesis type '{hypothesis_type}' with confidence {confidence:.2f}"
            )

            return hypothesis, confidence

        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Failed to extract hypothesis: {e}")
            return "Failed to extract hypothesis due to processing error.", 0.0

    def generate_summary_and_hypothesis(
        self,
        document: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Generate both summary and hypothesis in a single call for efficiency.

        Args:
            document: Document dictionary with title, abstract, and optionally full_text

        Returns:
            Dictionary with summary, hypothesis, and confidence scores
        """
        self._call_callback("analysis_started", "Generating summary and extracting hypothesis")

        # Get text to analyze
        text = self._get_analysis_text(document)
        if not text:
            logger.warning("No text available for analysis")
            return {
                'summary': "No text available for analysis.",
                'summary_confidence': 0.0,
                'hypothesis': "No hypothesis could be extracted.",
                'hypothesis_confidence': 0.0,
                'hypothesis_type': 'unknown',
            }

        title = document.get('title', 'Untitled')

        prompt = f"""You are a medical research analyst. Analyze this paper to:
1. Generate a brief 2-3 sentence summary
2. Extract the core statement/hypothesis

Paper Title: {title}

Paper Text:
{text}

INSTRUCTIONS FOR SUMMARY:
- Exactly 2-3 sentences (no more, no less)
- First sentence: Study type and population/topic
- Second sentence: Main method and key finding
- Third sentence (optional): Important implication
- Be specific with numbers where available

INSTRUCTIONS FOR HYPOTHESIS:
- Identify the main claim, hypothesis, or central statement
- Express as a clear, testable statement
- Include direction of effect (increases, decreases, associated with)
- Keep to 1-2 sentences maximum

Response format (JSON only):
{{
    "summary": "Your 2-3 sentence summary here",
    "summary_confidence": 0.85,
    "hypothesis": "The core statement/hypothesis here",
    "hypothesis_type": "primary_hypothesis|main_finding|intervention_effect|causal_claim|other",
    "hypothesis_confidence": 0.85
}}

Confidence scores (0.0-1.0):
- 0.9-1.0: Clear, explicit information
- 0.7-0.8: Good but some inference needed
- 0.5-0.6: Limited information
- <0.5: Insufficient information

Respond ONLY with valid JSON. No additional text."""

        try:
            result = self._generate_and_parse_json(
                prompt,
                max_retries=3,
                retry_context="summary and hypothesis extraction",
                num_predict=self.max_tokens,
            )

            summary = result.get('summary', '').strip()
            summary_confidence = float(result.get('summary_confidence', 0.7))
            hypothesis = result.get('hypothesis', '').strip()
            hypothesis_confidence = float(result.get('hypothesis_confidence', 0.7))
            hypothesis_type = result.get('hypothesis_type', 'other')

            self._call_callback(
                "analysis_completed",
                f"Generated summary and extracted {hypothesis_type} hypothesis"
            )

            return {
                'summary': summary,
                'summary_confidence': summary_confidence,
                'hypothesis': hypothesis,
                'hypothesis_confidence': hypothesis_confidence,
                'hypothesis_type': hypothesis_type,
            }

        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Failed to analyze paper: {e}")
            return {
                'summary': "Failed to generate summary.",
                'summary_confidence': 0.0,
                'hypothesis': "Failed to extract hypothesis.",
                'hypothesis_confidence': 0.0,
                'hypothesis_type': 'error',
            }

    def _get_analysis_text(self, document: Dict[str, Any]) -> str:
        """
        Get the best available text for analysis.

        Prefers full_text if available and substantial, otherwise uses abstract.

        Args:
            document: Document dictionary

        Returns:
            Text string for analysis (truncated if necessary)
        """
        full_text = document.get('full_text', '')
        abstract = document.get('abstract', '')

        # Prefer full text if available and substantial
        if full_text and len(full_text) > len(abstract):
            text = full_text
        elif abstract:
            text = abstract
        else:
            # Fall back to any text field
            text = document.get('content', '') or document.get('text', '')

        # Truncate if too long
        if len(text) > MAX_TEXT_LENGTH:
            text = text[:MAX_TEXT_LENGTH] + "..."
            logger.debug(f"Truncated text to {MAX_TEXT_LENGTH} characters")

        return text


__all__ = ['SummaryGenerator']
