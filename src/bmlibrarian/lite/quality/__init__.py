"""
Quality filtering module for BMLibrarian Lite.

This module provides quality assessment and filtering capabilities
for biomedical literature based on study design classification.

The module uses a tiered approach:
- Tier 1: PubMed metadata-based filtering (free, instant)
- Tier 2: LLM-based classification (Claude Haiku, ~$0.00025/doc)
- Tier 3: Detailed LLM assessment (Claude Sonnet, optional)

Usage:
    from bmlibrarian.lite.quality import (
        QualityTier,
        StudyDesign,
        QualityAssessment,
        MetadataFilter,
    )

    # Create filter and assess document
    filter = MetadataFilter()
    assessment = filter.assess(document)

    # Check if document meets quality threshold
    if assessment.quality_tier.value >= QualityTier.TIER_4_EXPERIMENTAL.value:
        print("Document is RCT-level quality or above")
"""

from .data_models import (
    # Enums
    StudyDesign,
    QualityTier,
    # Dataclasses
    QualityFilter,
    StudyClassification,
    BiasRisk,
    QualityAssessment,
    # Mappings
    DESIGN_TO_TIER,
    DESIGN_TO_SCORE,
    DESIGN_LABELS,
    TIER_LABELS,
)

from .metadata_filter import (
    MetadataFilter,
    PUBMED_TYPE_TO_DESIGN,
    TYPE_PRIORITY,
)

__all__ = [
    # Enums
    "StudyDesign",
    "QualityTier",
    # Dataclasses
    "QualityFilter",
    "StudyClassification",
    "BiasRisk",
    "QualityAssessment",
    # Mappings
    "DESIGN_TO_TIER",
    "DESIGN_TO_SCORE",
    "DESIGN_LABELS",
    "TIER_LABELS",
    # Metadata filter
    "MetadataFilter",
    "PUBMED_TYPE_TO_DESIGN",
    "TYPE_PRIORITY",
]
