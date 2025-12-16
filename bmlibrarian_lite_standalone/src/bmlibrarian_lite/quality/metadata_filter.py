"""
Tier 1: PubMed metadata-based quality filtering.

Uses publication types assigned by NLM indexers to classify
study design. This is free, instant, and reliable when available.
NLM indexers are domain experts, so their classifications carry
high confidence when present.
"""

import logging
from typing import Optional

from ..data_models import LiteDocument
from ..constants import (
    METADATA_HIGH_CONFIDENCE,
    METADATA_PARTIAL_MATCH_CONFIDENCE,
    METADATA_UNKNOWN_TYPE_CONFIDENCE,
    METADATA_NO_TYPE_CONFIDENCE,
)
from .data_models import (
    StudyDesign,
    QualityTier,
    QualityAssessment,
    DESIGN_TO_TIER,
)

logger = logging.getLogger(__name__)


# =============================================================================
# PubMed Publication Type to Study Design Mapping
# =============================================================================
# NLM assigns these during indexing - they are reliable when present.
# Source: https://www.nlm.nih.gov/mesh/pubtypes.html

PUBMED_TYPE_TO_DESIGN: dict[str, StudyDesign] = {
    # Tier 5: Systematic evidence synthesis
    "Meta-Analysis": StudyDesign.META_ANALYSIS,
    "Systematic Review": StudyDesign.SYSTEMATIC_REVIEW,
    # Tier 4: Experimental studies
    "Randomized Controlled Trial": StudyDesign.RCT,
    "Clinical Trial": StudyDesign.RCT,
    "Clinical Trial, Phase I": StudyDesign.RCT,
    "Clinical Trial, Phase II": StudyDesign.RCT,
    "Clinical Trial, Phase III": StudyDesign.RCT,
    "Clinical Trial, Phase IV": StudyDesign.RCT,
    "Controlled Clinical Trial": StudyDesign.RCT,
    "Pragmatic Clinical Trial": StudyDesign.RCT,
    "Equivalence Trial": StudyDesign.RCT,
    "Practice Guideline": StudyDesign.GUIDELINE,
    "Guideline": StudyDesign.GUIDELINE,
    "Consensus Development Conference": StudyDesign.GUIDELINE,
    "Consensus Development Conference, NIH": StudyDesign.GUIDELINE,
    # Tier 3: Controlled observational
    "Observational Study": StudyDesign.COHORT_PROSPECTIVE,
    "Multicenter Study": StudyDesign.COHORT_PROSPECTIVE,
    "Comparative Study": StudyDesign.COHORT_PROSPECTIVE,
    "Validation Study": StudyDesign.COHORT_PROSPECTIVE,
    "Twin Study": StudyDesign.COHORT_PROSPECTIVE,
    # Tier 2: Observational
    "Evaluation Study": StudyDesign.CROSS_SECTIONAL,
    "Clinical Study": StudyDesign.CROSS_SECTIONAL,
    # Tier 1: Anecdotal/opinion
    "Case Reports": StudyDesign.CASE_REPORT,
    "Editorial": StudyDesign.EDITORIAL,
    "Letter": StudyDesign.LETTER,
    "Comment": StudyDesign.COMMENT,
    "News": StudyDesign.EDITORIAL,
    "Personal Narrative": StudyDesign.EDITORIAL,
    "Biography": StudyDesign.EDITORIAL,
    "Historical Article": StudyDesign.EDITORIAL,
    "Interview": StudyDesign.EDITORIAL,
    "Introductory Journal Article": StudyDesign.EDITORIAL,
    "Lecture": StudyDesign.EDITORIAL,
    "Legal Case": StudyDesign.EDITORIAL,
    "Newspaper Article": StudyDesign.EDITORIAL,
    "Patient Education Handout": StudyDesign.EDITORIAL,
    # Special cases
    "Retracted Publication": StudyDesign.OTHER,
    "Published Erratum": StudyDesign.OTHER,
    "Review": StudyDesign.OTHER,  # Non-systematic review
}


# Priority order for when multiple publication types are present.
# Higher priority types override lower priority types.
# This ensures that an article marked as both "RCT" and "Multicenter Study"
# is classified as RCT (the more specific/higher evidence type).
TYPE_PRIORITY: list[str] = [
    # Highest priority - systematic evidence
    "Meta-Analysis",
    "Systematic Review",
    # High priority - experimental
    "Randomized Controlled Trial",
    "Clinical Trial, Phase IV",
    "Clinical Trial, Phase III",
    "Clinical Trial, Phase II",
    "Clinical Trial, Phase I",
    "Clinical Trial",
    "Controlled Clinical Trial",
    "Pragmatic Clinical Trial",
    "Equivalence Trial",
    "Practice Guideline",
    "Guideline",
    "Consensus Development Conference",
    "Consensus Development Conference, NIH",
    # Medium priority - observational
    "Multicenter Study",
    "Comparative Study",
    "Validation Study",
    "Observational Study",
    "Twin Study",
    "Evaluation Study",
    "Clinical Study",
    # Low priority - case level
    "Case Reports",
    # Lowest priority - opinion
    "Editorial",
    "Letter",
    "Comment",
]


class MetadataFilter:
    """
    Tier 1 quality filter using PubMed metadata.

    Classifies documents based on publication types assigned by
    NLM indexers. This is the fastest and cheapest filtering method,
    but not all documents have publication types assigned.

    Usage:
        filter = MetadataFilter()
        assessment = filter.assess(document)
        if assessment.quality_tier.value >= QualityTier.TIER_4_EXPERIMENTAL.value:
            # Document is at least RCT quality
            pass
    """

    def __init__(self) -> None:
        """Initialize the metadata filter."""
        self._type_to_design = PUBMED_TYPE_TO_DESIGN
        self._type_priority = TYPE_PRIORITY

    def assess(self, document: LiteDocument) -> QualityAssessment:
        """
        Assess document quality from PubMed metadata.

        Attempts to classify the study design based on PubMed
        publication types. Returns an unclassified assessment
        if no publication types are available.

        Args:
            document: The document to assess

        Returns:
            QualityAssessment with study design and confidence
        """
        pub_types = self._get_publication_types(document)

        if not pub_types:
            logger.debug(f"No publication types for document {document.id}")
            return QualityAssessment.unclassified()

        study_design, matched_type = self._classify_from_types(pub_types)

        if study_design == StudyDesign.UNKNOWN:
            # Has types but none matched our known list
            return QualityAssessment(
                assessment_tier=1,
                extraction_method="metadata",
                study_design=StudyDesign.UNKNOWN,
                quality_tier=QualityTier.UNCLASSIFIED,
                quality_score=0.0,
                confidence=METADATA_UNKNOWN_TYPE_CONFIDENCE,
                extraction_details=[
                    f"Publication types present but unrecognized: {pub_types}"
                ],
            )

        # Determine confidence based on match quality
        if matched_type in self._type_to_design:
            confidence = METADATA_HIGH_CONFIDENCE
        else:
            confidence = METADATA_PARTIAL_MATCH_CONFIDENCE

        logger.debug(
            f"Document {document.id} classified as {study_design.value} "
            f"from publication type '{matched_type}'"
        )

        return QualityAssessment.from_metadata(
            study_design=study_design,
            confidence=confidence,
            extraction_details=[
                f"Matched PubMed publication type: {matched_type}",
                f"All publication types: {pub_types}",
            ],
        )

    def _get_publication_types(self, document: LiteDocument) -> list[str]:
        """
        Extract publication types from document metadata.

        Checks multiple possible locations for publication types
        to handle different data source formats.

        Args:
            document: The document to extract types from

        Returns:
            List of publication type strings
        """
        pub_types: list[str] = []

        # Check document metadata dict
        if document.metadata:
            # Standard key
            if "publication_types" in document.metadata:
                types = document.metadata["publication_types"]
                if isinstance(types, list):
                    pub_types.extend(types)
                elif isinstance(types, str):
                    pub_types.append(types)

            # Alternative key (PubMed XML format)
            if "PublicationType" in document.metadata:
                types = document.metadata["PublicationType"]
                if isinstance(types, list):
                    pub_types.extend(types)
                elif isinstance(types, str):
                    pub_types.append(types)

            # Another alternative (some parsers)
            if "PublicationTypeList" in document.metadata:
                types = document.metadata["PublicationTypeList"]
                if isinstance(types, list):
                    pub_types.extend(types)

        # Deduplicate while preserving order
        seen: set[str] = set()
        unique_types: list[str] = []
        for pt in pub_types:
            pt_stripped = pt.strip()
            if pt_stripped and pt_stripped not in seen:
                seen.add(pt_stripped)
                unique_types.append(pt_stripped)

        return unique_types

    def _classify_from_types(
        self,
        pub_types: list[str],
    ) -> tuple[StudyDesign, Optional[str]]:
        """
        Classify study design from publication types.

        Uses priority ordering to select the most informative type
        when multiple are present. Falls back to partial matching
        if exact match is not found.

        Args:
            pub_types: List of publication type strings

        Returns:
            Tuple of (StudyDesign, matched_type_string)
        """
        # Normalize types for matching (case-sensitive comparison)
        normalized = {pt.strip(): pt for pt in pub_types}

        # Check in priority order (exact match)
        for priority_type in self._type_priority:
            if priority_type in normalized:
                design = self._type_to_design.get(priority_type, StudyDesign.UNKNOWN)
                return design, priority_type

        # Check for partial matches (some types have variants)
        for pub_type in normalized.keys():
            for known_type, design in self._type_to_design.items():
                # Case-insensitive substring match
                if known_type.lower() in pub_type.lower():
                    return design, pub_type

        return StudyDesign.UNKNOWN, None

    def get_tier_for_types(self, pub_types: list[str]) -> QualityTier:
        """
        Get quality tier for given publication types.

        Utility method for quick tier lookup without full assessment.

        Args:
            pub_types: List of publication type strings

        Returns:
            QualityTier for the publication types
        """
        design, _ = self._classify_from_types(pub_types)
        return DESIGN_TO_TIER.get(design, QualityTier.UNCLASSIFIED)

    def get_known_types(self) -> list[str]:
        """
        Get list of all known publication types.

        Useful for debugging and validation.

        Returns:
            List of recognized publication type strings
        """
        return list(self._type_to_design.keys())
