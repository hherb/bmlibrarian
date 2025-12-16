"""
Data models for quality assessment in BMLibrarian Lite.

Provides type-safe dataclasses and enums for quality filtering,
study design classification, and assessment results. These models
follow the evidence hierarchy used in evidence-based medicine.
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from functools import total_ordering
from typing import Optional, Any

from ..constants import VALID_BIAS_RISK_VALUES

logger = logging.getLogger(__name__)


class StudyDesign(Enum):
    """
    Study design classification following evidence hierarchy.

    Values represent the type of study design used in a research paper.
    The evidence hierarchy generally ranks these from highest to lowest
    quality of evidence for interventional questions.
    """

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


@total_ordering
class QualityTier(Enum):
    """
    Quality tier for filtering based on evidence hierarchy.

    Higher values indicate higher quality evidence. This simplified
    hierarchy is based on the Oxford Centre for Evidence-Based Medicine
    levels of evidence.

    Tier 5: Systematic evidence synthesis (highest)
    Tier 4: Experimental studies (RCTs, clinical trials)
    Tier 3: Controlled observational studies
    Tier 2: Observational studies
    Tier 1: Anecdotal/opinion (lowest)
    Tier 0: Unclassified

    This enum supports comparison operators (>, <, >=, <=) via @total_ordering,
    allowing direct comparison: `QualityTier.TIER_5_SYNTHESIS > QualityTier.TIER_3_CONTROLLED`
    """

    TIER_5_SYNTHESIS = 5
    TIER_4_EXPERIMENTAL = 4
    TIER_3_CONTROLLED = 3
    TIER_2_OBSERVATIONAL = 2
    TIER_1_ANECDOTAL = 1
    UNCLASSIFIED = 0

    def __lt__(self, other: "QualityTier") -> bool:
        """
        Less-than comparison based on tier value.

        Args:
            other: Another QualityTier to compare against

        Returns:
            True if this tier is lower quality than other
        """
        if not isinstance(other, QualityTier):
            return NotImplemented
        return self.value < other.value

    def __eq__(self, other: object) -> bool:
        """
        Equality comparison.

        Args:
            other: Another object to compare against

        Returns:
            True if both are the same QualityTier
        """
        if not isinstance(other, QualityTier):
            return NotImplemented
        return self.value == other.value

    def __hash__(self) -> int:
        """Return hash based on value for dict/set usage."""
        return hash(self.value)


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


# Mapping from study design to quality score (0-10 scale)
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


# Human-readable labels for study designs
DESIGN_LABELS: dict[StudyDesign, str] = {
    StudyDesign.SYSTEMATIC_REVIEW: "Systematic Review",
    StudyDesign.META_ANALYSIS: "Meta-Analysis",
    StudyDesign.RCT: "Randomized Controlled Trial",
    StudyDesign.GUIDELINE: "Clinical Guideline",
    StudyDesign.COHORT_PROSPECTIVE: "Prospective Cohort Study",
    StudyDesign.COHORT_RETROSPECTIVE: "Retrospective Cohort Study",
    StudyDesign.CASE_CONTROL: "Case-Control Study",
    StudyDesign.CROSS_SECTIONAL: "Cross-Sectional Study",
    StudyDesign.CASE_SERIES: "Case Series",
    StudyDesign.CASE_REPORT: "Case Report",
    StudyDesign.EDITORIAL: "Editorial",
    StudyDesign.LETTER: "Letter",
    StudyDesign.COMMENT: "Comment",
    StudyDesign.OTHER: "Other",
    StudyDesign.UNKNOWN: "Unknown",
}


# Human-readable labels for quality tiers
TIER_LABELS: dict[QualityTier, str] = {
    QualityTier.TIER_5_SYNTHESIS: "Systematic Evidence Synthesis",
    QualityTier.TIER_4_EXPERIMENTAL: "Experimental Studies",
    QualityTier.TIER_3_CONTROLLED: "Controlled Observational Studies",
    QualityTier.TIER_2_OBSERVATIONAL: "Observational Studies",
    QualityTier.TIER_1_ANECDOTAL: "Case Reports / Opinion",
    QualityTier.UNCLASSIFIED: "Unclassified",
}


@dataclass
class QualityFilter:
    """
    User-specified quality filter settings.

    Controls which documents pass quality filtering and
    how deeply to assess document quality.

    Attributes:
        minimum_tier: Minimum quality tier to include
        require_blinding: Only include blinded studies
        require_randomization: Only include randomized studies
        minimum_sample_size: Minimum sample size required
        use_metadata_only: Use only PubMed metadata (Tier 1)
        use_llm_classification: Use LLM for unclassified (Tier 2)
        use_detailed_assessment: Request full quality assessment (Tier 3)
    """

    minimum_tier: QualityTier = QualityTier.UNCLASSIFIED
    require_blinding: bool = False
    require_randomization: bool = False
    minimum_sample_size: Optional[int] = None
    use_metadata_only: bool = False
    use_llm_classification: bool = True
    use_detailed_assessment: bool = False

    def passes_tier(self, tier: QualityTier) -> bool:
        """
        Check if a quality tier passes the minimum threshold.

        Uses direct enum comparison via QualityTier's __ge__ method
        (enabled by @total_ordering decorator).

        Args:
            tier: Quality tier to check

        Returns:
            True if tier meets or exceeds minimum
        """
        # Direct enum comparison - clearer and type-safe
        return tier >= self.minimum_tier

    def to_dict(self) -> dict[str, Any]:
        """
        Convert to dictionary for serialization.

        Returns:
            Dictionary representation
        """
        return {
            "minimum_tier": self.minimum_tier.value,
            "require_blinding": self.require_blinding,
            "require_randomization": self.require_randomization,
            "minimum_sample_size": self.minimum_sample_size,
            "use_metadata_only": self.use_metadata_only,
            "use_llm_classification": self.use_llm_classification,
            "use_detailed_assessment": self.use_detailed_assessment,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "QualityFilter":
        """
        Create from dictionary.

        Args:
            data: Dictionary representation

        Returns:
            QualityFilter instance
        """
        return cls(
            minimum_tier=QualityTier(data.get("minimum_tier", 0)),
            require_blinding=data.get("require_blinding", False),
            require_randomization=data.get("require_randomization", False),
            minimum_sample_size=data.get("minimum_sample_size"),
            use_metadata_only=data.get("use_metadata_only", False),
            use_llm_classification=data.get("use_llm_classification", True),
            use_detailed_assessment=data.get("use_detailed_assessment", False),
        )


@dataclass
class StudyClassification:
    """
    Result from fast LLM classification (Tier 2).

    Contains essential study design information without
    full quality assessment details. This lightweight
    structure is returned by the fast Haiku classifier.

    Attributes:
        study_design: Classified study design
        is_randomized: Whether the study was randomized
        is_blinded: Blinding level (none/single/double/triple)
        sample_size: Number of participants
        confidence: Classifier confidence (0-1)
        raw_response: Raw LLM response for debugging
    """

    study_design: StudyDesign
    is_randomized: Optional[bool] = None
    is_blinded: Optional[str] = None
    sample_size: Optional[int] = None
    confidence: float = 0.0
    raw_response: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """
        Convert to dictionary for serialization.

        Returns:
            Dictionary representation
        """
        return {
            "study_design": self.study_design.value,
            "is_randomized": self.is_randomized,
            "is_blinded": self.is_blinded,
            "sample_size": self.sample_size,
            "confidence": self.confidence,
        }


@dataclass
class BiasRisk:
    """
    Risk of bias assessment across domains.

    Based on Cochrane Risk of Bias tool domains.
    Values are "low", "unclear", or "high".

    Attributes:
        selection: Selection bias risk
        performance: Performance bias risk
        detection: Detection bias risk
        attrition: Attrition bias risk
        reporting: Reporting bias risk
    """

    selection: str = "unclear"
    performance: str = "unclear"
    detection: str = "unclear"
    attrition: str = "unclear"
    reporting: str = "unclear"

    def to_dict(self) -> dict[str, str]:
        """
        Convert to dictionary for serialization.

        Returns:
            Dictionary with bias domain values
        """
        return {
            "selection": self.selection,
            "performance": self.performance,
            "detection": self.detection,
            "attrition": self.attrition,
            "reporting": self.reporting,
        }

    @classmethod
    def _validate_bias_value(cls, value: str, domain: str) -> str:
        """
        Validate and normalize a bias risk value.

        Args:
            value: The bias risk value to validate
            domain: The domain name (for error messages)

        Returns:
            Validated bias risk value (defaults to "unclear" if invalid)
        """
        normalized = str(value).lower().strip()
        if normalized in VALID_BIAS_RISK_VALUES:
            return normalized
        # Log invalid value and default to "unclear"
        logger.warning(
            f"BiasRisk: Invalid value '{value}' for domain '{domain}', "
            f"expected one of: {', '.join(sorted(VALID_BIAS_RISK_VALUES))}. "
            "Defaulting to 'unclear'."
        )
        return "unclear"

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> "BiasRisk":
        """
        Create from dictionary with validation.

        All bias risk values are validated against VALID_BIAS_RISK_VALUES
        ("low", "unclear", "high"). Invalid values are logged and replaced
        with "unclear" to maintain scientific integrity.

        Args:
            data: Dictionary with bias domain values

        Returns:
            BiasRisk instance with validated values
        """
        return cls(
            selection=cls._validate_bias_value(
                data.get("selection", "unclear"), "selection"
            ),
            performance=cls._validate_bias_value(
                data.get("performance", "unclear"), "performance"
            ),
            detection=cls._validate_bias_value(
                data.get("detection", "unclear"), "detection"
            ),
            attrition=cls._validate_bias_value(
                data.get("attrition", "unclear"), "attrition"
            ),
            reporting=cls._validate_bias_value(
                data.get("reporting", "unclear"), "reporting"
            ),
        )


@dataclass
class QualityAssessment:
    """
    Complete quality assessment result.

    Contains all quality-related information about a document,
    regardless of which tier provided the assessment. This is
    the primary output of the quality filtering system.

    Attributes:
        assessment_tier: Source tier (1=metadata, 2=Haiku, 3=Sonnet)
        extraction_method: Method used (metadata/llm_haiku/llm_sonnet)
        study_design: Classified study design
        quality_tier: Assigned quality tier
        quality_score: Quality score (0-10)
        evidence_level: Oxford CEBM level (optional)
        is_randomized: Whether study was randomized
        is_controlled: Whether study had control group
        is_blinded: Blinding level
        is_prospective: Whether study was prospective
        is_multicenter: Whether study was multicenter
        sample_size: Number of participants
        confidence: Assessment confidence (0-1)
        bias_risk: Detailed bias assessment (Tier 3 only)
        strengths: Methodological strengths (Tier 3 only)
        limitations: Methodological limitations (Tier 3 only)
        extraction_details: Audit trail of how assessment was made
    """

    assessment_tier: int
    extraction_method: str
    study_design: StudyDesign
    quality_tier: QualityTier
    quality_score: float
    evidence_level: Optional[str] = None
    is_randomized: Optional[bool] = None
    is_controlled: Optional[bool] = None
    is_blinded: Optional[str] = None
    is_prospective: Optional[bool] = None
    is_multicenter: Optional[bool] = None
    sample_size: Optional[int] = None
    confidence: float = 0.0
    bias_risk: Optional[BiasRisk] = None
    strengths: Optional[list[str]] = None
    limitations: Optional[list[str]] = None
    extraction_details: list[str] = field(default_factory=list)

    def passes_filter(self, filter_settings: QualityFilter) -> bool:
        """
        Check if this assessment passes all filter criteria.

        Args:
            filter_settings: Filter to check against

        Returns:
            True if all criteria are met
        """
        # Tier check
        if not filter_settings.passes_tier(self.quality_tier):
            return False

        # Blinding requirement
        if filter_settings.require_blinding:
            if self.is_blinded is None or self.is_blinded == "none":
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

    @property
    def design_label(self) -> str:
        """
        Get human-readable study design label.

        Returns:
            Study design label string
        """
        return DESIGN_LABELS.get(self.study_design, "Unknown")

    @property
    def tier_label(self) -> str:
        """
        Get human-readable quality tier label.

        Returns:
            Quality tier label string
        """
        return TIER_LABELS.get(self.quality_tier, "Unclassified")

    def to_dict(self) -> dict[str, Any]:
        """
        Convert to dictionary for serialization.

        Returns:
            Dictionary representation
        """
        return {
            "assessment_tier": self.assessment_tier,
            "extraction_method": self.extraction_method,
            "study_design": self.study_design.value,
            "quality_tier": self.quality_tier.value,
            "quality_score": self.quality_score,
            "evidence_level": self.evidence_level,
            "is_randomized": self.is_randomized,
            "is_controlled": self.is_controlled,
            "is_blinded": self.is_blinded,
            "is_prospective": self.is_prospective,
            "is_multicenter": self.is_multicenter,
            "sample_size": self.sample_size,
            "confidence": self.confidence,
            "bias_risk": self.bias_risk.to_dict() if self.bias_risk else None,
            "strengths": self.strengths,
            "limitations": self.limitations,
            "extraction_details": self.extraction_details,
        }

    @classmethod
    def from_metadata(
        cls,
        study_design: StudyDesign,
        confidence: float,
        extraction_details: Optional[list[str]] = None,
    ) -> "QualityAssessment":
        """
        Create assessment from PubMed metadata (Tier 1).

        Args:
            study_design: Classified study design
            confidence: Classification confidence
            extraction_details: Details of how classification was made

        Returns:
            QualityAssessment from metadata
        """
        return cls(
            assessment_tier=1,
            extraction_method="metadata",
            study_design=study_design,
            quality_tier=DESIGN_TO_TIER.get(study_design, QualityTier.UNCLASSIFIED),
            quality_score=DESIGN_TO_SCORE.get(study_design, 0.0),
            confidence=confidence,
            extraction_details=extraction_details
            or ["Classified from PubMed publication type"],
        )

    @classmethod
    def from_classification(cls, classification: StudyClassification) -> "QualityAssessment":
        """
        Create assessment from LLM classification (Tier 2).

        Args:
            classification: StudyClassification from Haiku

        Returns:
            QualityAssessment from classification
        """
        return cls(
            assessment_tier=2,
            extraction_method="llm_haiku",
            study_design=classification.study_design,
            quality_tier=DESIGN_TO_TIER.get(
                classification.study_design, QualityTier.UNCLASSIFIED
            ),
            quality_score=DESIGN_TO_SCORE.get(classification.study_design, 0.0),
            is_randomized=classification.is_randomized,
            is_blinded=classification.is_blinded,
            sample_size=classification.sample_size,
            confidence=classification.confidence,
            extraction_details=["Fast classification via Claude Haiku"],
        )

    @classmethod
    def unclassified(cls) -> "QualityAssessment":
        """
        Create an unclassified assessment.

        Use when classification cannot be determined.

        Returns:
            Unclassified QualityAssessment
        """
        return cls(
            assessment_tier=0,
            extraction_method="none",
            study_design=StudyDesign.UNKNOWN,
            quality_tier=QualityTier.UNCLASSIFIED,
            quality_score=0.0,
            confidence=0.0,
            extraction_details=["Could not classify document"],
        )
