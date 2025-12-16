"""
Tier 3: Detailed quality assessment using Claude Sonnet.

Provides comprehensive assessment including bias risk, strengths,
and limitations. This is optional and used when detailed assessment
is requested for high-value documents.

Cost: ~$0.003 per document
"""

import json
import logging
from typing import Optional

from ..agents.base import LiteBaseAgent
from ..data_models import LiteDocument
from ..config import LiteConfig
from ..constants import (
    QUALITY_ASSESSOR_MODEL,
    QUALITY_LLM_TEMPERATURE,
    QUALITY_ASSESSOR_MAX_TOKENS,
)
from .data_models import (
    StudyDesign,
    QualityTier,
    QualityAssessment,
    BiasRisk,
    DESIGN_TO_TIER,
    DESIGN_TO_SCORE,
)
from .study_classifier import STUDY_DESIGN_MAPPING

logger = logging.getLogger(__name__)


# System prompt for detailed quality assessment
ASSESSMENT_SYSTEM_PROMPT = """You are a research quality assessment expert.
Evaluate the methodological quality of biomedical research papers.

CRITICAL RULES:
1. Extract ONLY information that is ACTUALLY PRESENT in the text
2. DO NOT invent, assume, or fabricate any information
3. If information is unclear or not mentioned, use null or "unclear"
4. Focus on THIS study's methodology, not studies it references
5. Return ONLY valid JSON, no explanation"""


class LiteQualityAgent(LiteBaseAgent):
    """
    Comprehensive quality assessment using Claude Sonnet.

    Provides detailed evaluation including:
    - Study design classification
    - Evidence level (Oxford CEBM)
    - Design characteristics (randomization, blinding, etc.)
    - Risk of bias assessment (Cochrane RoB domains)
    - Methodological strengths and limitations

    This agent is more expensive than the classifier and should be used
    selectively for documents that require detailed assessment.

    Attributes:
        model: The LLM model to use for assessment
    """

    def __init__(
        self,
        config: Optional[LiteConfig] = None,
        model: Optional[str] = None,
    ) -> None:
        """
        Initialize the quality agent.

        Args:
            config: BMLibrarian Lite configuration
            model: Optional model override (default: from constants)
        """
        super().__init__(config)
        self.model = model or QUALITY_ASSESSOR_MODEL

    def assess_quality(self, document: LiteDocument) -> QualityAssessment:
        """
        Perform detailed quality assessment on a document.

        Args:
            document: The document to assess

        Returns:
            QualityAssessment with full details
        """
        # Prepare prompt with abstract (allow more text for detailed analysis)
        abstract = (document.abstract or "")[:4000]
        title = document.title or "Untitled"

        prompt = f"""Assess this research paper's methodological quality:

Title: {title}
Abstract: {abstract}

Return JSON:
{{
    "study_design": "systematic_review|meta_analysis|rct|cohort_prospective|cohort_retrospective|case_control|cross_sectional|case_series|case_report|editorial|letter|guideline|other",
    "quality_score": <1-10>,
    "evidence_level": "1a|1b|2a|2b|3a|3b|4|5|null",
    "design_characteristics": {{
        "randomized": true|false|null,
        "controlled": true|false|null,
        "blinded": "none"|"single"|"double"|"triple"|null,
        "prospective": true|false|null,
        "multicenter": true|false|null
    }},
    "sample_size": <number or null>,
    "bias_risk": {{
        "selection": "low"|"unclear"|"high",
        "performance": "low"|"unclear"|"high",
        "detection": "low"|"unclear"|"high",
        "attrition": "low"|"unclear"|"high",
        "reporting": "low"|"unclear"|"high"
    }},
    "strengths": ["2-3 methodological strengths"],
    "limitations": ["2-3 methodological limitations"],
    "confidence": <0.0 to 1.0>
}}

Focus on THIS study's methodology, not studies it references."""

        try:
            messages = [
                self._create_system_message(ASSESSMENT_SYSTEM_PROMPT),
                self._create_user_message(prompt),
            ]
            response = self._chat(
                messages=messages,
                temperature=QUALITY_LLM_TEMPERATURE,
                max_tokens=QUALITY_ASSESSOR_MAX_TOKENS,
                json_mode=True,
            )
            return self._parse_response(response)

        except Exception as e:
            logger.error(f"Quality assessment failed for document: {e}")
            return QualityAssessment.unclassified()

    def _parse_response(self, response: str) -> QualityAssessment:
        """
        Parse LLM response into QualityAssessment.

        Args:
            response: Raw LLM response string

        Returns:
            Parsed QualityAssessment
        """
        try:
            # Clean response
            cleaned = self._clean_json_response(response)
            data = json.loads(cleaned)

            # Parse study design
            design_str = data.get("study_design", "unknown").lower().strip()
            study_design = self._parse_study_design(design_str)

            # Parse design characteristics
            chars = data.get("design_characteristics", {})

            # Parse bias risk
            bias_risk = self._parse_bias_risk(data.get("bias_risk", {}))

            # Parse sample size
            sample_size = self._parse_sample_size(data.get("sample_size"))

            # Parse blinding
            is_blinded = self._parse_blinding(chars.get("blinded"))

            # Parse quality score (1-10 scale)
            quality_score = self._parse_quality_score(data.get("quality_score", 0))

            # Parse confidence
            confidence = self._parse_confidence(data.get("confidence", 0.5))

            return QualityAssessment(
                assessment_tier=3,
                extraction_method="llm_sonnet",
                study_design=study_design,
                quality_tier=DESIGN_TO_TIER.get(study_design, QualityTier.UNCLASSIFIED),
                quality_score=quality_score,
                evidence_level=data.get("evidence_level"),
                is_randomized=chars.get("randomized"),
                is_controlled=chars.get("controlled"),
                is_blinded=is_blinded,
                is_prospective=chars.get("prospective"),
                is_multicenter=chars.get("multicenter"),
                sample_size=sample_size,
                confidence=confidence,
                bias_risk=bias_risk,
                strengths=data.get("strengths", []),
                limitations=data.get("limitations", []),
                extraction_details=["Detailed assessment via Claude Sonnet"],
            )

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON response: {e}")
            return QualityAssessment.unclassified()

    def _clean_json_response(self, response: str) -> str:
        """
        Clean LLM response by removing markdown code blocks.

        Args:
            response: Raw response string

        Returns:
            Cleaned JSON string
        """
        cleaned = response.strip()
        if cleaned.startswith("```"):
            parts = cleaned.split("```")
            if len(parts) >= 2:
                cleaned = parts[1]
                if cleaned.startswith("json"):
                    cleaned = cleaned[4:]
        cleaned = cleaned.strip()
        return cleaned

    def _parse_study_design(self, design_str: str) -> StudyDesign:
        """
        Parse study design string to enum.

        Args:
            design_str: Study design as lowercase string

        Returns:
            StudyDesign enum value
        """
        return STUDY_DESIGN_MAPPING.get(design_str, StudyDesign.UNKNOWN)

    def _parse_bias_risk(self, bias_data: dict) -> BiasRisk:
        """
        Parse bias risk data into BiasRisk dataclass.

        Args:
            bias_data: Dictionary with bias domain values

        Returns:
            BiasRisk instance
        """
        valid_values = ("low", "unclear", "high")

        def validate_bias(value: Optional[str]) -> str:
            if value is None:
                return "unclear"
            normalized = str(value).lower().strip()
            return normalized if normalized in valid_values else "unclear"

        return BiasRisk(
            selection=validate_bias(bias_data.get("selection")),
            performance=validate_bias(bias_data.get("performance")),
            detection=validate_bias(bias_data.get("detection")),
            attrition=validate_bias(bias_data.get("attrition")),
            reporting=validate_bias(bias_data.get("reporting")),
        )

    def _parse_blinding(self, value: Optional[str]) -> Optional[str]:
        """
        Parse and validate blinding value.

        Args:
            value: Raw blinding value from response

        Returns:
            Validated blinding string or None
        """
        if value is None:
            return None
        normalized = str(value).lower().strip()
        valid_values = ("none", "single", "double", "triple")
        return normalized if normalized in valid_values else None

    def _parse_sample_size(self, value: Optional[int | str]) -> Optional[int]:
        """
        Parse sample size to integer.

        Args:
            value: Raw sample size value

        Returns:
            Integer sample size or None
        """
        if value is None:
            return None
        try:
            return int(value)
        except (ValueError, TypeError):
            return None

    def _parse_quality_score(self, value: float | str) -> float:
        """
        Parse and clamp quality score.

        Args:
            value: Raw quality score value

        Returns:
            Quality score clamped to 0.0-10.0 range
        """
        try:
            score = float(value)
            return max(0.0, min(10.0, score))
        except (ValueError, TypeError):
            return 0.0

    def _parse_confidence(self, value: float | str) -> float:
        """
        Parse and clamp confidence value.

        Args:
            value: Raw confidence value

        Returns:
            Confidence clamped to 0.0-1.0 range
        """
        try:
            conf = float(value)
            return max(0.0, min(1.0, conf))
        except (ValueError, TypeError):
            return 0.5

    def _get_model(self) -> str:
        """
        Override to use assessor-specific model.

        Returns:
            Model string with provider prefix
        """
        provider = self.config.llm.provider
        return f"{provider}:{self.model}"
