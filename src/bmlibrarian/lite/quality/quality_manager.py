"""
Quality Manager: Orchestrates tiered quality assessment.

Combines Tier 1 (metadata), Tier 2 (Haiku), and Tier 3 (Sonnet)
into a unified assessment workflow with intelligent tier selection.

Assessment Flow:
1. Tier 1: Always check PubMed metadata first (free, instant)
2. Tier 2: LLM classification via Haiku if metadata inconclusive
3. Tier 3: Detailed assessment via Sonnet if explicitly requested

The manager respects QualityFilter settings to determine which
tiers to use and when to fall back to more expensive options.
"""

import logging
from typing import Optional, Callable

from ..data_models import LiteDocument
from ..config import LiteConfig
from ..constants import (
    METADATA_HIGH_CONFIDENCE,
    QUALITY_CLASSIFIER_MODEL,
    QUALITY_ASSESSOR_MODEL,
)
from .data_models import (
    QualityTier,
    QualityFilter,
    QualityAssessment,
)
from .metadata_filter import MetadataFilter
from .study_classifier import LiteStudyClassifier
from .quality_agent import LiteQualityAgent

logger = logging.getLogger(__name__)


# Minimum confidence to accept metadata result without LLM fallback
METADATA_ACCEPTANCE_THRESHOLD = 0.9


class QualityManager:
    """
    Orchestrates tiered quality assessment.

    Assessment flow:
    1. Tier 1: Check PubMed metadata (free, instant)
    2. Tier 2: LLM classification via Haiku (if needed)
    3. Tier 3: Detailed assessment via Sonnet (if requested)

    The manager intelligently selects which tier to use based on:
    - Filter settings (use_metadata_only, use_llm_classification, etc.)
    - Metadata confidence level
    - Document classification status

    Attributes:
        config: BMLibrarian Lite configuration
        metadata_filter: Tier 1 metadata filter
        study_classifier: Tier 2 Haiku classifier
        quality_agent: Tier 3 Sonnet assessor
    """

    def __init__(
        self,
        config: Optional[LiteConfig] = None,
        classification_model: Optional[str] = None,
        assessment_model: Optional[str] = None,
    ) -> None:
        """
        Initialize the quality manager.

        Args:
            config: BMLibrarian Lite configuration
            classification_model: Model for Tier 2 (default: Haiku)
            assessment_model: Model for Tier 3 (default: Sonnet)
        """
        self.config = config or LiteConfig()
        self.metadata_filter = MetadataFilter()
        self.study_classifier = LiteStudyClassifier(
            self.config,
            model=classification_model or QUALITY_CLASSIFIER_MODEL,
        )
        self.quality_agent = LiteQualityAgent(
            self.config,
            model=assessment_model or QUALITY_ASSESSOR_MODEL,
        )

    def assess_document(
        self,
        document: LiteDocument,
        filter_settings: QualityFilter,
    ) -> QualityAssessment:
        """
        Assess document quality using tiered approach.

        The assessment follows this logic:
        1. Always try metadata first (free)
        2. If use_metadata_only is True, return metadata result
        3. If metadata has high confidence, use it (unless detailed requested)
        4. If use_llm_classification is True and metadata inconclusive, use Haiku
        5. If use_detailed_assessment is True, use Sonnet for full assessment

        Args:
            document: The document to assess
            filter_settings: Quality filter configuration

        Returns:
            QualityAssessment from appropriate tier
        """
        # Tier 1: Always try metadata first (free)
        metadata_result = self.metadata_filter.assess(document)
        logger.debug(
            f"Tier 1 result: {metadata_result.study_design.value} "
            f"(confidence: {metadata_result.confidence:.2f})"
        )

        # User wants metadata only - return immediately
        if filter_settings.use_metadata_only:
            return metadata_result

        # If metadata has high confidence and is classified, use it
        metadata_is_confident = (
            metadata_result.confidence >= METADATA_ACCEPTANCE_THRESHOLD
            and metadata_result.quality_tier != QualityTier.UNCLASSIFIED
        )

        if metadata_is_confident:
            # Unless detailed assessment is explicitly requested
            if filter_settings.use_detailed_assessment:
                logger.debug("Tier 3: Detailed assessment requested despite confident metadata")
                return self.quality_agent.assess_quality(document)
            return metadata_result

        # Tier 2: LLM classification for unclassified/low-confidence
        if filter_settings.use_llm_classification:
            classification = self.study_classifier.classify(document)
            logger.debug(
                f"Tier 2 result: {classification.study_design.value} "
                f"(confidence: {classification.confidence:.2f})"
            )

            # Tier 3: Detailed assessment if requested
            if filter_settings.use_detailed_assessment:
                logger.debug("Tier 3: Detailed assessment requested")
                return self.quality_agent.assess_quality(document)

            # Convert classification to assessment
            return QualityAssessment.from_classification(classification)

        # Fallback to metadata result (even if low confidence)
        return metadata_result

    def filter_documents(
        self,
        documents: list[LiteDocument],
        filter_settings: QualityFilter,
        progress_callback: Optional[Callable[[int, int, QualityAssessment], None]] = None,
    ) -> tuple[list[LiteDocument], list[QualityAssessment]]:
        """
        Filter documents based on quality criteria.

        Processes all documents through the tiered assessment system
        and returns only those that pass the filter criteria.

        Args:
            documents: List of documents to filter
            filter_settings: Quality filter configuration
            progress_callback: Optional callback(current, total, assessment)

        Returns:
            Tuple of (filtered_documents, all_assessments)
        """
        filtered: list[LiteDocument] = []
        assessments: list[QualityAssessment] = []

        total = len(documents)
        for i, doc in enumerate(documents):
            assessment = self.assess_document(doc, filter_settings)
            assessments.append(assessment)

            if assessment.passes_filter(filter_settings):
                filtered.append(doc)

            if progress_callback:
                progress_callback(i + 1, total, assessment)

        logger.info(
            f"Quality filtering: {len(filtered)}/{len(documents)} documents passed"
        )
        return filtered, assessments

    def get_assessment_summary(
        self,
        assessments: list[QualityAssessment],
    ) -> dict:
        """
        Generate summary statistics for assessments.

        Provides an overview of assessment results including
        distribution by tier, study design, and assessment source.

        Args:
            assessments: List of quality assessments

        Returns:
            Dictionary with summary statistics
        """
        if not assessments:
            return {
                "total": 0,
                "by_quality_tier": {},
                "by_study_design": {},
                "by_assessment_tier": {
                    "metadata": 0,
                    "haiku": 0,
                    "sonnet": 0,
                    "unclassified": 0,
                },
                "avg_confidence": 0.0,
            }

        tier_counts: dict[str, int] = {}
        design_counts: dict[str, int] = {}
        tier_sources = {1: 0, 2: 0, 3: 0, 0: 0}

        for assessment in assessments:
            # Count by quality tier
            tier_name = assessment.quality_tier.name
            tier_counts[tier_name] = tier_counts.get(tier_name, 0) + 1

            # Count by study design
            design_name = assessment.study_design.value
            design_counts[design_name] = design_counts.get(design_name, 0) + 1

            # Count by assessment source tier
            tier_sources[assessment.assessment_tier] = (
                tier_sources.get(assessment.assessment_tier, 0) + 1
            )

        avg_confidence = sum(a.confidence for a in assessments) / len(assessments)

        return {
            "total": len(assessments),
            "by_quality_tier": tier_counts,
            "by_study_design": design_counts,
            "by_assessment_tier": {
                "metadata": tier_sources[1],
                "haiku": tier_sources[2],
                "sonnet": tier_sources[3],
                "unclassified": tier_sources[0],
            },
            "avg_confidence": avg_confidence,
        }

    def get_tier_distribution(
        self,
        assessments: list[QualityAssessment],
    ) -> dict[QualityTier, int]:
        """
        Get distribution of assessments by quality tier.

        Args:
            assessments: List of quality assessments

        Returns:
            Dictionary mapping QualityTier to count
        """
        distribution: dict[QualityTier, int] = {}
        for tier in QualityTier:
            distribution[tier] = 0

        for assessment in assessments:
            distribution[assessment.quality_tier] = (
                distribution.get(assessment.quality_tier, 0) + 1
            )

        return distribution

    def get_design_distribution(
        self,
        assessments: list[QualityAssessment],
    ) -> dict[str, int]:
        """
        Get distribution of assessments by study design.

        Args:
            assessments: List of quality assessments

        Returns:
            Dictionary mapping study design value to count
        """
        distribution: dict[str, int] = {}
        for assessment in assessments:
            design = assessment.study_design.value
            distribution[design] = distribution.get(design, 0) + 1
        return distribution
