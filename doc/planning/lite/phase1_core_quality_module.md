# Phase 1: Core Quality Module

## Overview

This phase establishes the foundation for quality filtering in BMLibrarian Lite by implementing:
1. Data models for quality assessment
2. PubMed metadata-based filtering (Tier 1)

## Directory Structure

```
src/bmlibrarian/lite/quality/
├── __init__.py
├── data_models.py      # This phase
├── metadata_filter.py  # This phase
├── study_classifier.py # Phase 2
├── quality_agent.py    # Phase 2
└── quality_manager.py  # Phase 2
```

---

## Step 1: Create Module Structure

### 1.1 Create the quality directory

```bash
mkdir -p src/bmlibrarian/lite/quality
```

### 1.2 Create `__init__.py`

```python
# src/bmlibrarian/lite/quality/__init__.py
"""
Quality filtering module for BMLibrarian Lite.

Provides tiered quality assessment:
- Tier 1: PubMed metadata filtering (free, instant)
- Tier 2: LLM classification via Claude Haiku (cheap, accurate)
- Tier 3: Detailed assessment via Claude Sonnet (optional)
"""

from .data_models import (
    StudyDesign,
    QualityTier,
    QualityFilter,
    QualityAssessment,
    StudyClassification,
)
from .metadata_filter import MetadataFilter

__all__ = [
    "StudyDesign",
    "QualityTier",
    "QualityFilter",
    "QualityAssessment",
    "StudyClassification",
    "MetadataFilter",
]
```

---

## Step 2: Implement Data Models

### 2.1 File: `data_models.py`

```python
# src/bmlibrarian/lite/quality/data_models.py
"""Data models for quality assessment in BMLibrarian Lite."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class StudyDesign(Enum):
    """Study design classification following evidence hierarchy."""

    SYSTEMATIC_REVIEW = "systematic_review"
    META_ANALYSIS = "meta_analysis"
    RCT = "rct"
    COHORT_PROSPECTIVE = "cohort_prospective"
    COHORT_RETROSPECTIVE = "cohort_retrospective"
    CASE_CONTROL = "case_control"
    CROSS_SECTIONAL = "cross_sectional"
    CASE_SERIES = "case_series"
    CASE_REPORT = "case_report"
    EDITORIAL = "editorial"
    LETTER = "letter"
    COMMENT = "comment"
    GUIDELINE = "guideline"
    OTHER = "other"
    UNKNOWN = "unknown"


class QualityTier(Enum):
    """
    Quality tier for filtering based on evidence hierarchy.

    Higher values indicate higher quality evidence.
    """

    TIER_5_SYNTHESIS = 5      # Systematic reviews, meta-analyses
    TIER_4_EXPERIMENTAL = 4   # RCTs, clinical trials, guidelines
    TIER_3_CONTROLLED = 3     # Controlled observational studies
    TIER_2_OBSERVATIONAL = 2  # Observational studies
    TIER_1_ANECDOTAL = 1      # Case reports, editorials, letters
    UNCLASSIFIED = 0          # Could not classify


# Mapping from study design to quality tier
DESIGN_TO_TIER: dict[StudyDesign, QualityTier] = {
    StudyDesign.SYSTEMATIC_REVIEW: QualityTier.TIER_5_SYNTHESIS,
    StudyDesign.META_ANALYSIS: QualityTier.TIER_5_SYNTHESIS,
    StudyDesign.RCT: QualityTier.TIER_4_EXPERIMENTAL,
    StudyDesign.GUIDELINE: QualityTier.TIER_4_EXPERIMENTAL,
    StudyDesign.COHORT_PROSPECTIVE: QualityTier.TIER_3_CONTROLLED,
    StudyDesign.COHORT_RETROSPECTIVE: QualityTier.TIER_3_CONTROLLED,
    StudyDesign.CASE_CONTROL: QualityTier.TIER_3_CONTROLLED,
    StudyDesign.CROSS_SECTIONAL: QualityTier.TIER_2_OBSERVATIONAL,
    StudyDesign.CASE_SERIES: QualityTier.TIER_1_ANECDOTAL,
    StudyDesign.CASE_REPORT: QualityTier.TIER_1_ANECDOTAL,
    StudyDesign.EDITORIAL: QualityTier.TIER_1_ANECDOTAL,
    StudyDesign.LETTER: QualityTier.TIER_1_ANECDOTAL,
    StudyDesign.COMMENT: QualityTier.TIER_1_ANECDOTAL,
    StudyDesign.OTHER: QualityTier.UNCLASSIFIED,
    StudyDesign.UNKNOWN: QualityTier.UNCLASSIFIED,
}


# Mapping from study design to quality score (0-10)
DESIGN_TO_SCORE: dict[StudyDesign, float] = {
    StudyDesign.SYSTEMATIC_REVIEW: 10.0,
    StudyDesign.META_ANALYSIS: 10.0,
    StudyDesign.RCT: 8.0,
    StudyDesign.GUIDELINE: 8.0,
    StudyDesign.COHORT_PROSPECTIVE: 6.0,
    StudyDesign.COHORT_RETROSPECTIVE: 5.0,
    StudyDesign.CASE_CONTROL: 4.0,
    StudyDesign.CROSS_SECTIONAL: 3.0,
    StudyDesign.CASE_SERIES: 2.0,
    StudyDesign.CASE_REPORT: 1.0,
    StudyDesign.EDITORIAL: 1.0,
    StudyDesign.LETTER: 1.0,
    StudyDesign.COMMENT: 1.0,
    StudyDesign.OTHER: 0.0,
    StudyDesign.UNKNOWN: 0.0,
}


@dataclass
class QualityFilter:
    """
    User-specified quality filter settings.

    Controls which documents pass quality filtering and
    how deeply to assess document quality.
    """

    # Minimum quality tier to include
    minimum_tier: QualityTier = QualityTier.UNCLASSIFIED

    # Specific requirements
    require_blinding: bool = False
    require_randomization: bool = False
    minimum_sample_size: Optional[int] = None

    # Assessment depth options
    use_metadata_only: bool = False      # Tier 1 only (free, fast, less complete)
    use_llm_classification: bool = True  # Tier 2: Haiku for unclassified docs
    use_detailed_assessment: bool = False  # Tier 3: Sonnet for full quality report

    def passes_tier(self, tier: QualityTier) -> bool:
        """Check if a quality tier passes the minimum threshold."""
        return tier.value >= self.minimum_tier.value


@dataclass
class StudyClassification:
    """
    Result from fast LLM classification (Tier 2).

    Contains essential study design information without
    full quality assessment details.
    """

    study_design: StudyDesign
    is_randomized: Optional[bool] = None
    is_blinded: Optional[str] = None  # "none", "single", "double", "triple"
    sample_size: Optional[int] = None
    confidence: float = 0.0

    # Raw response for debugging
    raw_response: Optional[str] = None


@dataclass
class BiasRisk:
    """Risk of bias assessment across domains."""

    selection: str = "unclear"      # "low", "unclear", "high"
    performance: str = "unclear"
    detection: str = "unclear"
    attrition: str = "unclear"
    reporting: str = "unclear"


@dataclass
class QualityAssessment:
    """
    Complete quality assessment result.

    Contains all quality-related information about a document,
    regardless of which tier provided the assessment.
    """

    # Source of assessment
    assessment_tier: int  # 1 (metadata), 2 (Haiku), or 3 (Sonnet)
    extraction_method: str  # "metadata", "llm_haiku", "llm_sonnet"

    # Core classification
    study_design: StudyDesign
    quality_tier: QualityTier
    quality_score: float  # 0-10

    # Evidence level (Oxford CEBM hierarchy)
    evidence_level: Optional[str] = None  # "1a", "1b", "2a", etc.

    # Design characteristics
    is_randomized: Optional[bool] = None
    is_controlled: Optional[bool] = None
    is_blinded: Optional[str] = None  # "none", "single", "double", "triple"
    is_prospective: Optional[bool] = None
    is_multicenter: Optional[bool] = None
    sample_size: Optional[int] = None

    # Assessment confidence
    confidence: float = 0.0

    # Detailed assessment (Tier 3 only)
    bias_risk: Optional[BiasRisk] = None
    strengths: Optional[list[str]] = None
    limitations: Optional[list[str]] = None

    # Audit trail
    extraction_details: list[str] = field(default_factory=list)

    def passes_filter(self, filter_settings: QualityFilter) -> bool:
        """Check if this assessment passes all filter criteria."""
        # Tier check
        if not filter_settings.passes_tier(self.quality_tier):
            return False

        # Blinding requirement
        if filter_settings.require_blinding:
            if self.is_blinded in [None, "none"]:
                return False

        # Randomization requirement
        if filter_settings.require_randomization:
            if not self.is_randomized:
                return False

        # Sample size requirement
        if filter_settings.minimum_sample_size is not None:
            if self.sample_size is None:
                return False
            if self.sample_size < filter_settings.minimum_sample_size:
                return False

        return True

    @classmethod
    def from_metadata(
        cls,
        study_design: StudyDesign,
        confidence: float,
        extraction_details: Optional[list[str]] = None
    ) -> "QualityAssessment":
        """Create assessment from PubMed metadata (Tier 1)."""
        return cls(
            assessment_tier=1,
            extraction_method="metadata",
            study_design=study_design,
            quality_tier=DESIGN_TO_TIER.get(study_design, QualityTier.UNCLASSIFIED),
            quality_score=DESIGN_TO_SCORE.get(study_design, 0.0),
            confidence=confidence,
            extraction_details=extraction_details or ["Classified from PubMed publication type"]
        )

    @classmethod
    def from_classification(
        cls,
        classification: "StudyClassification"
    ) -> "QualityAssessment":
        """Create assessment from LLM classification (Tier 2)."""
        return cls(
            assessment_tier=2,
            extraction_method="llm_haiku",
            study_design=classification.study_design,
            quality_tier=DESIGN_TO_TIER.get(classification.study_design, QualityTier.UNCLASSIFIED),
            quality_score=DESIGN_TO_SCORE.get(classification.study_design, 0.0),
            is_randomized=classification.is_randomized,
            is_blinded=classification.is_blinded,
            sample_size=classification.sample_size,
            confidence=classification.confidence,
            extraction_details=["Fast classification via Claude Haiku"]
        )

    @classmethod
    def unclassified(cls) -> "QualityAssessment":
        """Create an unclassified assessment."""
        return cls(
            assessment_tier=0,
            extraction_method="none",
            study_design=StudyDesign.UNKNOWN,
            quality_tier=QualityTier.UNCLASSIFIED,
            quality_score=0.0,
            confidence=0.0,
            extraction_details=["Could not classify document"]
        )
```

---

## Step 3: Implement Metadata Filter

### 3.1 File: `metadata_filter.py`

```python
# src/bmlibrarian/lite/quality/metadata_filter.py
"""
Tier 1: PubMed metadata-based quality filtering.

Uses publication types assigned by NLM indexers to classify
study design. This is free, instant, and reliable when available.
"""

import logging
from typing import Optional

from ..data_models import LiteDocument
from .data_models import (
    StudyDesign,
    QualityTier,
    QualityAssessment,
    DESIGN_TO_TIER,
)

logger = logging.getLogger(__name__)


# PubMed publication types mapped to study designs
# NLM assigns these during indexing - they are reliable when present
PUBMED_TYPE_TO_DESIGN: dict[str, StudyDesign] = {
    # Tier 5: Systematic evidence synthesis
    "Meta-Analysis": StudyDesign.META_ANALYSIS,
    "Systematic Review": StudyDesign.SYSTEMATIC_REVIEW,

    # Tier 4: Experimental studies
    "Randomized Controlled Trial": StudyDesign.RCT,
    "Clinical Trial": StudyDesign.RCT,  # Conservative: treat as RCT
    "Clinical Trial, Phase I": StudyDesign.RCT,
    "Clinical Trial, Phase II": StudyDesign.RCT,
    "Clinical Trial, Phase III": StudyDesign.RCT,
    "Clinical Trial, Phase IV": StudyDesign.RCT,
    "Controlled Clinical Trial": StudyDesign.RCT,
    "Pragmatic Clinical Trial": StudyDesign.RCT,
    "Practice Guideline": StudyDesign.GUIDELINE,
    "Guideline": StudyDesign.GUIDELINE,

    # Tier 3: Controlled observational
    "Observational Study": StudyDesign.COHORT_PROSPECTIVE,  # Conservative
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
    "Retracted Publication": StudyDesign.OTHER,
}


# Priority order for when multiple publication types are present
# Higher priority types override lower priority types
TYPE_PRIORITY: list[str] = [
    "Meta-Analysis",
    "Systematic Review",
    "Randomized Controlled Trial",
    "Clinical Trial, Phase IV",
    "Clinical Trial, Phase III",
    "Clinical Trial, Phase II",
    "Clinical Trial, Phase I",
    "Clinical Trial",
    "Controlled Clinical Trial",
    "Pragmatic Clinical Trial",
    "Practice Guideline",
    "Guideline",
    "Multicenter Study",
    "Comparative Study",
    "Validation Study",
    "Observational Study",
    "Twin Study",
    "Evaluation Study",
    "Clinical Study",
    "Case Reports",
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
    """

    def __init__(self):
        """Initialize the metadata filter."""
        self._type_to_design = PUBMED_TYPE_TO_DESIGN
        self._type_priority = TYPE_PRIORITY

    def assess(self, document: LiteDocument) -> QualityAssessment:
        """
        Assess document quality from PubMed metadata.

        Args:
            document: The document to assess

        Returns:
            QualityAssessment with study design and confidence
        """
        pub_types = self._get_publication_types(document)

        if not pub_types:
            # No publication types available
            return QualityAssessment.unclassified()

        # Find highest priority matching type
        study_design, matched_type = self._classify_from_types(pub_types)

        if study_design == StudyDesign.UNKNOWN:
            return QualityAssessment(
                assessment_tier=1,
                extraction_method="metadata",
                study_design=StudyDesign.UNKNOWN,
                quality_tier=QualityTier.UNCLASSIFIED,
                quality_score=0.0,
                confidence=0.3,  # Low confidence - has types but none matched
                extraction_details=[
                    f"Publication types present but unrecognized: {pub_types}"
                ]
            )

        # NLM indexers are experts - high confidence
        confidence = 0.95

        return QualityAssessment.from_metadata(
            study_design=study_design,
            confidence=confidence,
            extraction_details=[
                f"Matched PubMed publication type: {matched_type}",
                f"All publication types: {pub_types}"
            ]
        )

    def _get_publication_types(self, document: LiteDocument) -> list[str]:
        """
        Extract publication types from document metadata.

        Args:
            document: The document to extract types from

        Returns:
            List of publication type strings
        """
        # Try different possible locations for publication types
        pub_types = []

        # Check document metadata dict
        if hasattr(document, 'metadata') and document.metadata:
            if 'publication_types' in document.metadata:
                types = document.metadata['publication_types']
                if isinstance(types, list):
                    pub_types.extend(types)
                elif isinstance(types, str):
                    pub_types.append(types)

            if 'PublicationType' in document.metadata:
                types = document.metadata['PublicationType']
                if isinstance(types, list):
                    pub_types.extend(types)
                elif isinstance(types, str):
                    pub_types.append(types)

        # Check direct attribute
        if hasattr(document, 'publication_types') and document.publication_types:
            if isinstance(document.publication_types, list):
                pub_types.extend(document.publication_types)
            elif isinstance(document.publication_types, str):
                pub_types.append(document.publication_types)

        # Deduplicate while preserving order
        seen = set()
        unique_types = []
        for pt in pub_types:
            if pt not in seen:
                seen.add(pt)
                unique_types.append(pt)

        return unique_types

    def _classify_from_types(
        self,
        pub_types: list[str]
    ) -> tuple[StudyDesign, Optional[str]]:
        """
        Classify study design from publication types.

        Uses priority ordering to select the most informative type
        when multiple are present.

        Args:
            pub_types: List of publication type strings

        Returns:
            Tuple of (StudyDesign, matched_type_string)
        """
        # Normalize types for matching
        normalized = {pt.strip(): pt for pt in pub_types}

        # Check in priority order
        for priority_type in self._type_priority:
            if priority_type in normalized:
                design = self._type_to_design.get(priority_type, StudyDesign.UNKNOWN)
                return design, priority_type

        # Check for partial matches (some types have variants)
        for pub_type, original in normalized.items():
            for known_type, design in self._type_to_design.items():
                if known_type.lower() in pub_type.lower():
                    return design, original

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
```

---

## Step 4: Add Constants

### 4.1 Update `constants.py`

Add to `src/bmlibrarian/lite/constants.py`:

```python
# Quality filtering constants
DEFAULT_MINIMUM_QUALITY_TIER = 0  # No filtering (include all)
DEFAULT_USE_METADATA_ONLY = False
DEFAULT_USE_LLM_CLASSIFICATION = True
DEFAULT_USE_DETAILED_ASSESSMENT = False

# Model selection for quality classification
DEFAULT_CLASSIFICATION_MODEL = "claude-3-haiku-20240307"
DEFAULT_ASSESSMENT_MODEL = "claude-sonnet-4-20250514"

# UI options
DEFAULT_SHOW_QUALITY_BADGES = True
DEFAULT_INCLUDE_QUALITY_IN_REPORTS = True
```

---

## Step 5: Unit Tests

### 5.1 File: `tests/lite/quality/test_data_models.py`

```python
"""Tests for quality assessment data models."""

import pytest

from bmlibrarian.lite.quality.data_models import (
    StudyDesign,
    QualityTier,
    QualityFilter,
    QualityAssessment,
    StudyClassification,
    DESIGN_TO_TIER,
    DESIGN_TO_SCORE,
)


class TestStudyDesign:
    """Tests for StudyDesign enum."""

    def test_all_designs_have_tier_mapping(self):
        """Every study design should map to a quality tier."""
        for design in StudyDesign:
            assert design in DESIGN_TO_TIER

    def test_all_designs_have_score_mapping(self):
        """Every study design should map to a quality score."""
        for design in StudyDesign:
            assert design in DESIGN_TO_SCORE
            assert 0.0 <= DESIGN_TO_SCORE[design] <= 10.0


class TestQualityTier:
    """Tests for QualityTier enum."""

    def test_tier_ordering(self):
        """Higher tiers should have higher values."""
        assert QualityTier.TIER_5_SYNTHESIS.value > QualityTier.TIER_4_EXPERIMENTAL.value
        assert QualityTier.TIER_4_EXPERIMENTAL.value > QualityTier.TIER_3_CONTROLLED.value
        assert QualityTier.TIER_3_CONTROLLED.value > QualityTier.TIER_2_OBSERVATIONAL.value
        assert QualityTier.TIER_2_OBSERVATIONAL.value > QualityTier.TIER_1_ANECDOTAL.value
        assert QualityTier.TIER_1_ANECDOTAL.value > QualityTier.UNCLASSIFIED.value


class TestQualityFilter:
    """Tests for QualityFilter."""

    def test_default_filter_accepts_all(self):
        """Default filter should accept any quality tier."""
        filter_settings = QualityFilter()
        assert filter_settings.passes_tier(QualityTier.TIER_5_SYNTHESIS)
        assert filter_settings.passes_tier(QualityTier.TIER_1_ANECDOTAL)
        assert filter_settings.passes_tier(QualityTier.UNCLASSIFIED)

    def test_rct_filter(self):
        """Filter requiring RCT+ should reject lower tiers."""
        filter_settings = QualityFilter(minimum_tier=QualityTier.TIER_4_EXPERIMENTAL)
        assert filter_settings.passes_tier(QualityTier.TIER_5_SYNTHESIS)
        assert filter_settings.passes_tier(QualityTier.TIER_4_EXPERIMENTAL)
        assert not filter_settings.passes_tier(QualityTier.TIER_3_CONTROLLED)
        assert not filter_settings.passes_tier(QualityTier.TIER_1_ANECDOTAL)


class TestQualityAssessment:
    """Tests for QualityAssessment."""

    def test_from_metadata(self):
        """Test creating assessment from metadata."""
        assessment = QualityAssessment.from_metadata(
            study_design=StudyDesign.RCT,
            confidence=0.95
        )
        assert assessment.assessment_tier == 1
        assert assessment.extraction_method == "metadata"
        assert assessment.study_design == StudyDesign.RCT
        assert assessment.quality_tier == QualityTier.TIER_4_EXPERIMENTAL
        assert assessment.quality_score == 8.0
        assert assessment.confidence == 0.95

    def test_from_classification(self):
        """Test creating assessment from LLM classification."""
        classification = StudyClassification(
            study_design=StudyDesign.SYSTEMATIC_REVIEW,
            is_randomized=None,
            sample_size=23,
            confidence=0.92
        )
        assessment = QualityAssessment.from_classification(classification)
        assert assessment.assessment_tier == 2
        assert assessment.extraction_method == "llm_haiku"
        assert assessment.quality_tier == QualityTier.TIER_5_SYNTHESIS
        assert assessment.sample_size == 23

    def test_passes_filter_tier(self):
        """Test tier filtering."""
        assessment = QualityAssessment.from_metadata(
            study_design=StudyDesign.COHORT_PROSPECTIVE,
            confidence=0.9
        )

        # Should pass tier 3 filter
        filter_3 = QualityFilter(minimum_tier=QualityTier.TIER_3_CONTROLLED)
        assert assessment.passes_filter(filter_3)

        # Should fail tier 4 filter
        filter_4 = QualityFilter(minimum_tier=QualityTier.TIER_4_EXPERIMENTAL)
        assert not assessment.passes_filter(filter_4)

    def test_passes_filter_sample_size(self):
        """Test sample size filtering."""
        assessment = QualityAssessment.from_metadata(
            study_design=StudyDesign.RCT,
            confidence=0.9
        )
        assessment.sample_size = 50

        filter_small = QualityFilter(minimum_sample_size=30)
        assert assessment.passes_filter(filter_small)

        filter_large = QualityFilter(minimum_sample_size=100)
        assert not assessment.passes_filter(filter_large)
```

### 5.2 File: `tests/lite/quality/test_metadata_filter.py`

```python
"""Tests for PubMed metadata-based quality filter."""

import pytest
from unittest.mock import MagicMock

from bmlibrarian.lite.quality.metadata_filter import MetadataFilter
from bmlibrarian.lite.quality.data_models import (
    StudyDesign,
    QualityTier,
)


class TestMetadataFilter:
    """Tests for MetadataFilter."""

    @pytest.fixture
    def filter(self):
        """Create a metadata filter instance."""
        return MetadataFilter()

    def _create_mock_document(self, pub_types: list[str]):
        """Create a mock document with publication types."""
        doc = MagicMock()
        doc.metadata = {"publication_types": pub_types}
        doc.publication_types = pub_types
        return doc

    def test_rct_classification(self, filter):
        """RCT publication type should classify as RCT."""
        doc = self._create_mock_document(["Randomized Controlled Trial"])
        assessment = filter.assess(doc)

        assert assessment.study_design == StudyDesign.RCT
        assert assessment.quality_tier == QualityTier.TIER_4_EXPERIMENTAL
        assert assessment.confidence >= 0.9

    def test_systematic_review_classification(self, filter):
        """Systematic Review should classify as highest tier."""
        doc = self._create_mock_document(["Systematic Review"])
        assessment = filter.assess(doc)

        assert assessment.study_design == StudyDesign.SYSTEMATIC_REVIEW
        assert assessment.quality_tier == QualityTier.TIER_5_SYNTHESIS

    def test_meta_analysis_classification(self, filter):
        """Meta-Analysis should classify as highest tier."""
        doc = self._create_mock_document(["Meta-Analysis"])
        assessment = filter.assess(doc)

        assert assessment.study_design == StudyDesign.META_ANALYSIS
        assert assessment.quality_tier == QualityTier.TIER_5_SYNTHESIS

    def test_case_report_classification(self, filter):
        """Case Report should classify as lowest tier."""
        doc = self._create_mock_document(["Case Reports"])
        assessment = filter.assess(doc)

        assert assessment.study_design == StudyDesign.CASE_REPORT
        assert assessment.quality_tier == QualityTier.TIER_1_ANECDOTAL

    def test_editorial_classification(self, filter):
        """Editorial should classify as lowest tier."""
        doc = self._create_mock_document(["Editorial"])
        assessment = filter.assess(doc)

        assert assessment.study_design == StudyDesign.EDITORIAL
        assert assessment.quality_tier == QualityTier.TIER_1_ANECDOTAL

    def test_multiple_types_priority(self, filter):
        """When multiple types present, use highest priority."""
        # RCT + Case Report should classify as RCT
        doc = self._create_mock_document([
            "Case Reports",
            "Randomized Controlled Trial",
            "Multicenter Study"
        ])
        assessment = filter.assess(doc)

        assert assessment.study_design == StudyDesign.RCT
        assert assessment.quality_tier == QualityTier.TIER_4_EXPERIMENTAL

    def test_no_publication_types(self, filter):
        """Document without publication types should be unclassified."""
        doc = MagicMock()
        doc.metadata = {}
        doc.publication_types = None

        assessment = filter.assess(doc)

        assert assessment.study_design == StudyDesign.UNKNOWN
        assert assessment.quality_tier == QualityTier.UNCLASSIFIED
        assert assessment.confidence == 0.0

    def test_unknown_publication_type(self, filter):
        """Unknown publication type should be unclassified with low confidence."""
        doc = self._create_mock_document(["Some Unknown Type"])
        assessment = filter.assess(doc)

        assert assessment.study_design == StudyDesign.UNKNOWN
        assert assessment.quality_tier == QualityTier.UNCLASSIFIED
        assert assessment.confidence < 0.5  # Low confidence

    def test_extraction_details_included(self, filter):
        """Assessment should include extraction details for audit."""
        doc = self._create_mock_document(["Randomized Controlled Trial"])
        assessment = filter.assess(doc)

        assert len(assessment.extraction_details) > 0
        assert any("Randomized Controlled Trial" in d for d in assessment.extraction_details)
```

---

## Verification Checklist

After implementing Phase 1, verify:

- [ ] `src/bmlibrarian/lite/quality/` directory exists
- [ ] `__init__.py` exports all public classes
- [ ] `data_models.py` implements all dataclasses
- [ ] `metadata_filter.py` implements MetadataFilter
- [ ] All study designs map to tiers and scores
- [ ] Unit tests pass: `uv run pytest tests/lite/quality/ -v`
- [ ] No type errors: `uv run mypy src/bmlibrarian/lite/quality/`

---

## Next Steps

After Phase 1 is complete, proceed to **Phase 2: LLM Classification** which implements:
- `LiteStudyClassifier` (Tier 2 - Haiku)
- `LiteQualityAgent` (Tier 3 - Sonnet)
- `QualityManager` (orchestrator)
