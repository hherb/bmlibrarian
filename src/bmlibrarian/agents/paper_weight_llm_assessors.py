"""
Paper Weight LLM-Based Assessors

Functions for LLM-based assessment of paper quality:
- Methodological quality assessment (randomization, blinding, etc.)
- Risk of bias assessment (selection, performance, detection, reporting)
- Integration with existing StudyAssessmentAgent output

All score calculators are stateless pure functions.
Prompts are imported from paper_weight_prompts module.
"""

import logging
from typing import Dict, Any, Optional

from .paper_weight_models import (
    DimensionScore,
    DIMENSION_METHODOLOGICAL_QUALITY,
    DIMENSION_RISK_OF_BIAS,
)
from .paper_weight_prompts import (
    build_methodological_quality_prompt,
    build_risk_of_bias_prompt,
)


logger = logging.getLogger(__name__)

# Maximum text length for LLM prompts
DEFAULT_MAX_TEXT_LENGTH = 8000

# Score constants for methodological quality extraction from StudyAssessmentAgent
# These values match the scoring rubric in the LLM prompts
RANDOMIZATION_SCORE = 2.0  # Points for proper randomization
DOUBLE_BLIND_SCORE = 2.0   # Points for double-blind design
SINGLE_BLIND_SCORE = 1.0   # Points for single-blind design
REMAINING_COMPONENTS_MAX = 5.0  # Max points for other MQ components (allocation, protocol, ITT, attrition)
QUALITY_SCORE_MAX = 10.0   # Maximum quality score from StudyAssessmentAgent


def prepare_text_for_analysis(
    document: Dict[str, Any],
    max_length: int = DEFAULT_MAX_TEXT_LENGTH
) -> str:
    """
    Prepare document text for LLM analysis.

    Combines title, abstract and full text (if available), limits length
    to avoid token limits.

    Args:
        document: Document dict with 'title', 'abstract', 'full_text' fields
        max_length: Maximum characters to include (default: 8000)

    Returns:
        Prepared text string suitable for LLM prompt
    """
    title = document.get('title', '') or ''
    abstract = document.get('abstract', '') or ''
    full_text = document.get('full_text', '') or ''

    # Prefer full text if available, otherwise use abstract
    if full_text:
        text = f"TITLE: {title}\n\nFULL TEXT:\n{full_text}"
    else:
        text = f"TITLE: {title}\n\nABSTRACT:\n{abstract}"

    # Limit to max_length characters to avoid token limits
    if len(text) > max_length:
        text = text[:max_length] + "\n\n[Text truncated...]"
        logger.debug(f"Truncated text to {max_length} characters")

    return text


def calculate_methodological_quality_score(components: Dict[str, Any]) -> DimensionScore:
    """
    Calculate methodological quality score from component assessments.

    Args:
        components: Parsed component assessments from LLM (dict with component names as keys)

    Returns:
        DimensionScore with full audit trail
    """
    dimension_score = DimensionScore(
        dimension_name=DIMENSION_METHODOLOGICAL_QUALITY,
        score=0.0
    )

    for component_name, component_data in components.items():
        if not isinstance(component_data, dict):
            continue

        score_contribution = float(component_data.get('score', 0.0))
        evidence = component_data.get('evidence', '')
        reasoning = component_data.get('reasoning', '')

        # Handle attrition_rate if present
        value = str(score_contribution)
        if component_name == 'attrition_handling':
            attrition_rate = component_data.get('attrition_rate')
            if attrition_rate is not None:
                value = f"{score_contribution} (attrition rate: {attrition_rate})"

        dimension_score.add_detail(
            component=component_name,
            value=value,
            contribution=score_contribution,
            evidence=evidence,
            reasoning=reasoning
        )

        dimension_score.score += score_contribution

    # Cap at 10.0
    dimension_score.score = min(10.0, dimension_score.score)

    return dimension_score


def calculate_risk_of_bias_score(components: Dict[str, Any]) -> DimensionScore:
    """
    Calculate risk of bias score from component assessments.

    Args:
        components: Parsed component assessments from LLM

    Returns:
        DimensionScore with full audit trail
    """
    dimension_score = DimensionScore(
        dimension_name=DIMENSION_RISK_OF_BIAS,
        score=0.0
    )

    for component_name, component_data in components.items():
        if not isinstance(component_data, dict):
            continue

        score_contribution = float(component_data.get('score', 0.0))
        risk_level = component_data.get('risk_level', 'unknown')
        evidence = component_data.get('evidence', '')
        reasoning = component_data.get('reasoning', '')

        dimension_score.add_detail(
            component=component_name,
            value=f"{risk_level} risk ({score_contribution})",
            contribution=score_contribution,
            evidence=evidence,
            reasoning=reasoning
        )

        dimension_score.score += score_contribution

    # Cap at 10.0
    dimension_score.score = min(10.0, dimension_score.score)

    return dimension_score


# =============================================================================
# StudyAssessmentAgent Integration Functions
# =============================================================================

# Risk level to score mapping (inverted: high risk = low score)
RISK_LEVEL_SCORES = {
    'low': 2.5,
    'moderate': 1.25,
    'high': 0.0,
    'unclear': 0.625  # Between moderate and high
}


def extract_mq_from_study_assessment(
    study_assessment: Dict[str, Any]
) -> Optional[DimensionScore]:
    """
    Extract methodological quality from StudyAssessmentAgent output.

    If StudyAssessmentAgent has already analyzed the paper, reuse
    relevant assessments to avoid duplicate LLM calls.

    Args:
        study_assessment: Output from StudyAssessmentAgent (as dict)

    Returns:
        DimensionScore for methodological quality, or None if extraction fails
    """
    try:
        dimension_score = DimensionScore(
            dimension_name=DIMENSION_METHODOLOGICAL_QUALITY,
            score=0.0
        )

        total_score = 0.0

        # Extract randomization from is_randomized
        is_randomized = study_assessment.get('is_randomized', False)
        if is_randomized:
            dimension_score.add_detail(
                component='randomization',
                value='yes',
                contribution=RANDOMIZATION_SCORE,
                reasoning='Extracted from StudyAssessmentAgent: is_randomized=True'
            )
            total_score += RANDOMIZATION_SCORE
        else:
            dimension_score.add_detail(
                component='randomization',
                value='no',
                contribution=0.0,
                reasoning='Extracted from StudyAssessmentAgent: is_randomized=False or not specified'
            )

        # Extract blinding
        is_double_blinded = study_assessment.get('is_double_blinded', False)
        is_blinded = study_assessment.get('is_blinded', False)
        if is_double_blinded:
            dimension_score.add_detail(
                component='blinding',
                value='double-blind',
                contribution=DOUBLE_BLIND_SCORE,
                reasoning='Extracted from StudyAssessmentAgent: is_double_blinded=True'
            )
            total_score += DOUBLE_BLIND_SCORE
        elif is_blinded:
            dimension_score.add_detail(
                component='blinding',
                value='single-blind',
                contribution=SINGLE_BLIND_SCORE,
                reasoning='Extracted from StudyAssessmentAgent: is_blinded=True (not double)'
            )
            total_score += SINGLE_BLIND_SCORE
        else:
            dimension_score.add_detail(
                component='blinding',
                value='no blinding',
                contribution=0.0,
                reasoning='Extracted from StudyAssessmentAgent: no blinding detected'
            )

        # Check quality_score to estimate remaining components
        quality_score_raw = study_assessment.get('quality_score', REMAINING_COMPONENTS_MAX)
        quality_score = float(quality_score_raw) if quality_score_raw is not None else REMAINING_COMPONENTS_MAX
        quality_score = max(0.0, min(QUALITY_SCORE_MAX, quality_score))

        # Map quality_score (0-10) to remaining components estimate
        remaining_proportion = quality_score / QUALITY_SCORE_MAX
        remaining_estimate = REMAINING_COMPONENTS_MAX * remaining_proportion

        dimension_score.add_detail(
            component='other_components',
            value=f'estimated from quality_score={quality_score:.1f}',
            contribution=remaining_estimate,
            reasoning=(
                f'Estimated from StudyAssessmentAgent quality_score ({quality_score:.1f}/10) - '
                'covers allocation concealment, protocol registration, ITT analysis, and attrition handling'
            )
        )
        total_score += remaining_estimate

        dimension_score.score = min(10.0, total_score)

        logger.info(
            f"Extracted methodological quality from StudyAssessmentAgent: score={dimension_score.score:.2f}/10"
        )

        return dimension_score

    except Exception as e:
        logger.warning(f"Failed to extract MQ from StudyAssessmentAgent: {e}")
        return None


def extract_rob_from_study_assessment(
    study_assessment: Dict[str, Any]
) -> Optional[DimensionScore]:
    """
    Extract risk of bias from StudyAssessmentAgent output.

    Args:
        study_assessment: Output from StudyAssessmentAgent (as dict)

    Returns:
        DimensionScore for risk of bias, or None if extraction fails
    """
    try:
        dimension_score = DimensionScore(
            dimension_name=DIMENSION_RISK_OF_BIAS,
            score=0.0
        )

        total_score = 0.0

        # Extract selection bias
        selection_risk = study_assessment.get('selection_bias_risk', 'unclear')
        if selection_risk:
            selection_score = RISK_LEVEL_SCORES.get(selection_risk.lower(), 0.625)
            dimension_score.add_detail(
                component='selection_bias',
                value=f'{selection_risk} risk ({selection_score})',
                contribution=selection_score,
                reasoning=f'Extracted from StudyAssessmentAgent: selection_bias_risk={selection_risk}'
            )
            total_score += selection_score

        # Extract performance bias
        performance_risk = study_assessment.get('performance_bias_risk', 'unclear')
        if performance_risk:
            performance_score = RISK_LEVEL_SCORES.get(performance_risk.lower(), 0.625)
            dimension_score.add_detail(
                component='performance_bias',
                value=f'{performance_risk} risk ({performance_score})',
                contribution=performance_score,
                reasoning=f'Extracted from StudyAssessmentAgent: performance_bias_risk={performance_risk}'
            )
            total_score += performance_score

        # Extract detection bias
        detection_risk = study_assessment.get('detection_bias_risk', 'unclear')
        if detection_risk:
            detection_score = RISK_LEVEL_SCORES.get(detection_risk.lower(), 0.625)
            dimension_score.add_detail(
                component='detection_bias',
                value=f'{detection_risk} risk ({detection_score})',
                contribution=detection_score,
                reasoning=f'Extracted from StudyAssessmentAgent: detection_bias_risk={detection_risk}'
            )
            total_score += detection_score

        # Extract reporting bias
        reporting_risk = study_assessment.get('reporting_bias_risk', 'unclear')
        if reporting_risk:
            reporting_score = RISK_LEVEL_SCORES.get(reporting_risk.lower(), 0.625)
            dimension_score.add_detail(
                component='reporting_bias',
                value=f'{reporting_risk} risk ({reporting_score})',
                contribution=reporting_score,
                reasoning=f'Extracted from StudyAssessmentAgent: reporting_bias_risk={reporting_risk}'
            )
            total_score += reporting_score

        dimension_score.score = min(10.0, total_score)

        logger.info(
            f"Extracted risk of bias from StudyAssessmentAgent: score={dimension_score.score:.2f}/10"
        )

        return dimension_score

    except Exception as e:
        logger.warning(f"Failed to extract RoB from StudyAssessmentAgent: {e}")
        return None


def create_error_dimension_score(
    dimension_name: str,
    error_message: str,
    default_score: float = 5.0
) -> DimensionScore:
    """
    Create a dimension score indicating an error occurred.

    Args:
        dimension_name: Name of the dimension
        error_message: Error message to include
        default_score: Default score to assign (default: 5.0 neutral)

    Returns:
        DimensionScore with error information
    """
    dimension_score = DimensionScore(
        dimension_name=dimension_name,
        score=default_score
    )
    dimension_score.add_detail(
        component='error',
        value='assessment_failed',
        contribution=default_score,
        reasoning=f'LLM assessment failed: {error_message}'
    )
    return dimension_score


__all__ = [
    'DEFAULT_MAX_TEXT_LENGTH',
    'RISK_LEVEL_SCORES',
    'prepare_text_for_analysis',
    'build_methodological_quality_prompt',
    'build_risk_of_bias_prompt',
    'calculate_methodological_quality_score',
    'calculate_risk_of_bias_score',
    'extract_mq_from_study_assessment',
    'extract_rob_from_study_assessment',
    'create_error_dimension_score',
]
