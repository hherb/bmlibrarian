"""
Tier 2: Fast study design classification using Claude Haiku.

Provides accurate classification at minimal cost (~$0.00025/document)
for documents without high-confidence PubMed publication type metadata.

This classifier focuses on determining what study design THIS paper used,
ignoring any other studies mentioned in the abstract. This distinction is
critical because documents often reference other study types in their
literature review sections.
"""

import json
import logging
from typing import Optional, Callable

from ..agents.base import LiteBaseAgent
from ..data_models import LiteDocument
from ..config import LiteConfig
from ..constants import (
    QUALITY_CLASSIFIER_MODEL,
    QUALITY_LLM_TEMPERATURE,
    QUALITY_CLASSIFIER_MAX_TOKENS,
)
from .data_models import StudyDesign, StudyClassification

logger = logging.getLogger(__name__)


# System prompt for study classification - emphasizes classifying THIS study
CLASSIFICATION_SYSTEM_PROMPT = """You are a biomedical research classifier.
Your task is to classify the study design of research papers.

CRITICAL RULES:
1. Classify what THIS paper reports, NOT studies it references
2. Look for phrases like "we conducted", "this study", "our trial", "we analyzed"
3. Ignore phrases like "previous studies", "Smith et al. reported", "unlike RCTs"
4. If uncertain, return "other" with low confidence
5. Return ONLY valid JSON, no explanation"""


# Mapping from LLM response strings to StudyDesign enum
STUDY_DESIGN_MAPPING: dict[str, StudyDesign] = {
    "systematic_review": StudyDesign.SYSTEMATIC_REVIEW,
    "systematic review": StudyDesign.SYSTEMATIC_REVIEW,
    "meta_analysis": StudyDesign.META_ANALYSIS,
    "meta-analysis": StudyDesign.META_ANALYSIS,
    "metaanalysis": StudyDesign.META_ANALYSIS,
    "rct": StudyDesign.RCT,
    "randomized_controlled_trial": StudyDesign.RCT,
    "randomized controlled trial": StudyDesign.RCT,
    "randomised_controlled_trial": StudyDesign.RCT,
    "clinical_trial": StudyDesign.RCT,
    "clinical trial": StudyDesign.RCT,
    "cohort_prospective": StudyDesign.COHORT_PROSPECTIVE,
    "prospective_cohort": StudyDesign.COHORT_PROSPECTIVE,
    "prospective cohort": StudyDesign.COHORT_PROSPECTIVE,
    "cohort_retrospective": StudyDesign.COHORT_RETROSPECTIVE,
    "retrospective_cohort": StudyDesign.COHORT_RETROSPECTIVE,
    "retrospective cohort": StudyDesign.COHORT_RETROSPECTIVE,
    "retrospective": StudyDesign.COHORT_RETROSPECTIVE,
    "case_control": StudyDesign.CASE_CONTROL,
    "case-control": StudyDesign.CASE_CONTROL,
    "cross_sectional": StudyDesign.CROSS_SECTIONAL,
    "cross-sectional": StudyDesign.CROSS_SECTIONAL,
    "crosssectional": StudyDesign.CROSS_SECTIONAL,
    "case_series": StudyDesign.CASE_SERIES,
    "case series": StudyDesign.CASE_SERIES,
    "case_report": StudyDesign.CASE_REPORT,
    "case report": StudyDesign.CASE_REPORT,
    "editorial": StudyDesign.EDITORIAL,
    "letter": StudyDesign.LETTER,
    "comment": StudyDesign.COMMENT,
    "commentary": StudyDesign.COMMENT,
    "guideline": StudyDesign.GUIDELINE,
    "practice_guideline": StudyDesign.GUIDELINE,
    "practice guideline": StudyDesign.GUIDELINE,
    "other": StudyDesign.OTHER,
    "unknown": StudyDesign.UNKNOWN,
}


class LiteStudyClassifier(LiteBaseAgent):
    """
    Fast study design classification using Claude Haiku.

    This classifier provides accurate study design classification at minimal
    cost. It specifically focuses on classifying what study design THIS paper
    used, ignoring any other studies mentioned in the abstract.

    Attributes:
        model: The LLM model to use for classification
    """

    def __init__(
        self,
        config: Optional[LiteConfig] = None,
        model: Optional[str] = None,
    ) -> None:
        """
        Initialize the study classifier.

        Args:
            config: BMLibrarian Lite configuration
            model: Optional model override (default: from constants)
        """
        super().__init__(config)
        self.model = model or QUALITY_CLASSIFIER_MODEL

    def classify(self, document: LiteDocument) -> StudyClassification:
        """
        Classify study design for a document.

        Args:
            document: The document to classify

        Returns:
            StudyClassification with design and confidence
        """
        # Prepare prompt with truncated abstract to stay within limits
        abstract = (document.abstract or "")[:2000]
        title = document.title or "Untitled"

        prompt = f"""Classify THIS paper's study design:

Title: {title}
Abstract: {abstract}

Return JSON:
{{
    "study_design": "systematic_review|meta_analysis|rct|cohort_prospective|cohort_retrospective|case_control|cross_sectional|case_series|case_report|editorial|letter|guideline|other",
    "is_randomized": true|false|null,
    "is_blinded": "none"|"single"|"double"|"triple"|null,
    "sample_size": <number or null>,
    "confidence": <0.0 to 1.0>
}}

IMPORTANT: Classify what THIS study did, not studies it references."""

        try:
            messages = [
                self._create_system_message(CLASSIFICATION_SYSTEM_PROMPT),
                self._create_user_message(prompt),
            ]
            response = self._chat(
                messages=messages,
                temperature=QUALITY_LLM_TEMPERATURE,
                max_tokens=QUALITY_CLASSIFIER_MAX_TOKENS,
                json_mode=True,
            )
            return self._parse_response(response)

        except Exception as e:
            logger.error(f"Classification failed for document: {e}")
            return StudyClassification(
                study_design=StudyDesign.UNKNOWN,
                confidence=0.0,
                raw_response=str(e),
            )

    def _parse_response(self, response: str) -> StudyClassification:
        """
        Parse LLM response into StudyClassification.

        Args:
            response: Raw LLM response string

        Returns:
            Parsed StudyClassification
        """
        try:
            # Clean response (remove markdown code blocks if present)
            cleaned = self._clean_json_response(response)
            data = json.loads(cleaned)

            # Parse study design
            design_str = data.get("study_design", "unknown").lower().strip()
            study_design = self._parse_study_design(design_str)

            # Parse blinding - validate against known values
            is_blinded = self._parse_blinding(data.get("is_blinded"))

            # Parse sample size - convert to int safely
            sample_size = self._parse_sample_size(data.get("sample_size"))

            # Parse confidence - ensure valid range
            confidence = self._parse_confidence(data.get("confidence", 0.5))

            return StudyClassification(
                study_design=study_design,
                is_randomized=data.get("is_randomized"),
                is_blinded=is_blinded,
                sample_size=sample_size,
                confidence=confidence,
                raw_response=response,
            )

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON response: {e}")
            return StudyClassification(
                study_design=StudyDesign.UNKNOWN,
                confidence=0.0,
                raw_response=response,
            )

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
            # Remove opening code block
            parts = cleaned.split("```")
            if len(parts) >= 2:
                cleaned = parts[1]
                # Remove language identifier if present
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

    def classify_batch(
        self,
        documents: list[LiteDocument],
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> list[StudyClassification]:
        """
        Classify multiple documents.

        Args:
            documents: List of documents to classify
            progress_callback: Optional callback(current, total)

        Returns:
            List of classifications in same order as input
        """
        results = []
        total = len(documents)
        for i, doc in enumerate(documents):
            results.append(self.classify(doc))
            if progress_callback:
                progress_callback(i + 1, total)
        return results

    def _get_model(self) -> str:
        """
        Override to use classifier-specific model.

        Returns:
            Model string with provider prefix
        """
        provider = self.config.llm.provider
        return f"{provider}:{self.model}"
