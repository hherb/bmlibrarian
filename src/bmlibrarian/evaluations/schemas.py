"""
JSON schemas for evaluation data types.

Each evaluation type has a corresponding schema that defines the structure
of the evaluation_data JSONB column in evaluations.document_evaluations.

These schemas are used for:
1. Validation of evaluation data before storage
2. Documentation of expected data structures
3. Type hints for IDE support

Author: BMLibrarian
Date: 2025-12-07
"""

from typing import TypedDict, Optional, List, Dict, Any
from enum import Enum


class EvaluationType(Enum):
    """Evaluation types supported by the unified evaluation system."""
    RELEVANCE_SCORE = "relevance_score"
    QUALITY_ASSESSMENT = "quality_assessment"
    PRISMA_SUITABILITY = "prisma_suitability"
    PRISMA_ASSESSMENT = "prisma_assessment"
    PICO_EXTRACTION = "pico_extraction"
    PAPER_WEIGHT = "paper_weight"
    INCLUSION_DECISION = "inclusion_decision"


class RunType(Enum):
    """Run types for evaluation runs."""
    RELEVANCE_SCORING = "relevance_scoring"
    QUALITY_ASSESSMENT = "quality_assessment"
    PRISMA_ASSESSMENT = "prisma_assessment"
    PICO_EXTRACTION = "pico_extraction"
    PAPER_WEIGHT = "paper_weight"
    SYSTEMATIC_REVIEW = "systematic_review"


class RunStatus(Enum):
    """Status values for evaluation runs."""
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"


class CheckpointType(Enum):
    """Checkpoint types for run resumability."""
    SEARCH_PLANNING = "search_planning"
    SEARCH_EXECUTION = "search_execution"
    INITIAL_FILTERING = "initial_filtering"
    RELEVANCE_SCORING = "relevance_scoring"
    QUALITY_ASSESSMENT = "quality_assessment"
    CITATION_EXTRACTION = "citation_extraction"
    REPORT_GENERATION = "report_generation"
    COUNTERFACTUAL_SEARCH = "counterfactual_search"
    FINAL_REVIEW = "final_review"
    CUSTOM = "custom"


class UserDecision(Enum):
    """User decisions at checkpoints."""
    CONTINUE = "continue"
    PAUSE = "pause"
    ABORT = "abort"
    ADJUST_PARAMETERS = "adjust_parameters"
    REQUEST_MORE = "request_more"


# ============================================================================
# TypedDict schemas for evaluation_data structures
# ============================================================================

class RelevanceScoreData(TypedDict, total=False):
    """Schema for relevance_score evaluation_data."""
    score: float  # 1-5 scale
    rationale: str
    inclusion_decision: str  # 'include', 'exclude', 'maybe'
    key_terms_matched: List[str]
    relevance_factors: Dict[str, float]


class QualityAssessmentData(TypedDict, total=False):
    """Schema for quality_assessment evaluation_data."""
    study_design: str  # 'RCT', 'cohort', 'case-control', etc.
    methodology_score: float  # 0-10
    bias_risk_score: float  # 0-10 (lower is better)
    sample_size_score: float  # 0-10
    recency_score: float  # 0-10
    replication_status: str  # 'replicated', 'unreplicated', 'unknown'
    composite_score: float  # 0-100 weighted composite
    weights_used: Dict[str, float]
    strengths: List[str]
    limitations: List[str]


class PRISMASuitabilityData(TypedDict, total=False):
    """Schema for prisma_suitability evaluation_data."""
    is_systematic_review: bool
    is_meta_analysis: bool
    is_suitable: bool
    confidence: float  # 0-1
    rationale: str
    document_type_detected: str


class PRISMAAssessmentData(TypedDict, total=False):
    """Schema for prisma_assessment evaluation_data."""
    is_suitable: bool
    suitability_confidence: float
    item_scores: Dict[str, float]  # 27 items, each 0/1/2
    item_explanations: Dict[str, str]
    overall_compliance_score: float  # Sum of item scores
    overall_compliance_percentage: float  # 0-100
    missing_items: List[str]
    partial_items: List[str]
    fully_reported_items: List[str]


class PICOExtractionData(TypedDict, total=False):
    """Schema for pico_extraction evaluation_data."""
    population: str
    intervention: str
    comparison: str
    outcome: str
    study_type: str
    confidence_scores: Dict[str, float]  # Per-component confidence
    extraction_notes: str


class PaperWeightData(TypedDict, total=False):
    """Schema for paper_weight evaluation_data."""
    evidential_weight: float  # 0-10 scale
    weight_category: str  # 'high', 'moderate', 'low', 'minimal'
    study_type: str
    sample_size: Optional[int]
    effect_size: Optional[float]
    confidence_interval: Optional[str]
    factors: Dict[str, float]  # Individual weight factors
    rationale: str


class InclusionDecisionData(TypedDict, total=False):
    """Schema for inclusion_decision evaluation_data."""
    decision: str  # 'include', 'exclude', 'unclear'
    stage: str  # 'title_abstract', 'full_text', 'final'
    rationale: str
    exclusion_reasons: List[str]
    inclusion_criteria_met: Dict[str, bool]
    exclusion_criteria_met: Dict[str, bool]


# ============================================================================
# Schema registry for validation
# ============================================================================

EVALUATION_SCHEMAS: Dict[str, Dict[str, Any]] = {
    EvaluationType.RELEVANCE_SCORE.value: {
        "required_fields": ["score"],
        "optional_fields": ["rationale", "inclusion_decision", "key_terms_matched", "relevance_factors"],
        "score_range": (1, 5),
        "typed_dict": RelevanceScoreData,
    },
    EvaluationType.QUALITY_ASSESSMENT.value: {
        "required_fields": ["study_design", "composite_score"],
        "optional_fields": [
            "methodology_score", "bias_risk_score", "sample_size_score",
            "recency_score", "replication_status", "weights_used",
            "strengths", "limitations"
        ],
        "score_range": (0, 100),
        "typed_dict": QualityAssessmentData,
    },
    EvaluationType.PRISMA_SUITABILITY.value: {
        "required_fields": ["is_suitable", "confidence"],
        "optional_fields": [
            "is_systematic_review", "is_meta_analysis", "rationale",
            "document_type_detected"
        ],
        "score_range": (0, 1),  # Confidence
        "typed_dict": PRISMASuitabilityData,
    },
    EvaluationType.PRISMA_ASSESSMENT.value: {
        "required_fields": ["item_scores", "overall_compliance_percentage"],
        "optional_fields": [
            "is_suitable", "suitability_confidence", "item_explanations",
            "overall_compliance_score", "missing_items", "partial_items",
            "fully_reported_items"
        ],
        "score_range": (0, 100),  # Percentage
        "typed_dict": PRISMAAssessmentData,
    },
    EvaluationType.PICO_EXTRACTION.value: {
        "required_fields": ["population", "intervention", "outcome"],
        "optional_fields": [
            "comparison", "study_type", "confidence_scores", "extraction_notes"
        ],
        "score_range": None,  # No primary score
        "typed_dict": PICOExtractionData,
    },
    EvaluationType.PAPER_WEIGHT.value: {
        "required_fields": ["evidential_weight", "weight_category"],
        "optional_fields": [
            "study_type", "sample_size", "effect_size", "confidence_interval",
            "factors", "rationale"
        ],
        "score_range": (0, 10),
        "typed_dict": PaperWeightData,
    },
    EvaluationType.INCLUSION_DECISION.value: {
        "required_fields": ["decision", "stage"],
        "optional_fields": [
            "rationale", "exclusion_reasons", "inclusion_criteria_met",
            "exclusion_criteria_met"
        ],
        "score_range": None,  # No primary score
        "typed_dict": InclusionDecisionData,
    },
}


def validate_evaluation_data(
    evaluation_type: str,
    evaluation_data: Dict[str, Any],
    strict: bool = False
) -> tuple[bool, Optional[str]]:
    """
    Validate evaluation data against its schema.

    Args:
        evaluation_type: Type of evaluation (from EvaluationType enum)
        evaluation_data: The data to validate
        strict: If True, also check for unknown fields

    Returns:
        Tuple of (is_valid, error_message)
    """
    if evaluation_type not in EVALUATION_SCHEMAS:
        return False, f"Unknown evaluation type: {evaluation_type}"

    schema = EVALUATION_SCHEMAS[evaluation_type]

    # Check required fields
    for field in schema["required_fields"]:
        if field not in evaluation_data:
            return False, f"Missing required field: {field}"

    # Check for unknown fields in strict mode
    if strict:
        all_fields = set(schema["required_fields"]) | set(schema["optional_fields"])
        unknown = set(evaluation_data.keys()) - all_fields
        if unknown:
            return False, f"Unknown fields: {unknown}"

    # Validate score range if applicable
    if schema["score_range"] and "score" in evaluation_data:
        score = evaluation_data.get("score")
        if score is not None:
            min_score, max_score = schema["score_range"]
            if not (min_score <= score <= max_score):
                return False, f"Score {score} out of range [{min_score}, {max_score}]"

    return True, None


def get_primary_score_field(evaluation_type: str) -> Optional[str]:
    """
    Get the field name that contains the primary score for an evaluation type.

    Args:
        evaluation_type: Type of evaluation

    Returns:
        Field name for primary score, or None if no primary score
    """
    score_fields = {
        EvaluationType.RELEVANCE_SCORE.value: "score",
        EvaluationType.QUALITY_ASSESSMENT.value: "composite_score",
        EvaluationType.PRISMA_SUITABILITY.value: "confidence",
        EvaluationType.PRISMA_ASSESSMENT.value: "overall_compliance_percentage",
        EvaluationType.PICO_EXTRACTION.value: None,
        EvaluationType.PAPER_WEIGHT.value: "evidential_weight",
        EvaluationType.INCLUSION_DECISION.value: None,
    }
    return score_fields.get(evaluation_type)


def extract_primary_score(
    evaluation_type: str,
    evaluation_data: Dict[str, Any]
) -> Optional[float]:
    """
    Extract the primary score from evaluation data.

    Args:
        evaluation_type: Type of evaluation
        evaluation_data: The evaluation data dict

    Returns:
        Primary score value, or None if not applicable
    """
    field = get_primary_score_field(evaluation_type)
    if field is None:
        return None
    return evaluation_data.get(field)
