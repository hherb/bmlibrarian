"""
Paper Weight Rule-Based Extractors

Pure functions for extracting paper characteristics using rule-based methods:
- Study type extraction via keyword matching
- Sample size extraction via regex patterns
- Power calculation and confidence interval detection

All functions are stateless and can be tested in isolation.
"""

import re
import math
from typing import Optional, Dict, List, Any

from .paper_weight_models import (
    DimensionScore,
    DIMENSION_STUDY_DESIGN,
    DIMENSION_SAMPLE_SIZE,
)


# Priority order for study type detection (highest evidence level first)
STUDY_TYPE_PRIORITY = [
    'systematic_review',
    'meta_analysis',
    'rct',
    'interventional_single_arm',  # Open-label, single-arm interventional studies
    'cohort_prospective',
    'cohort_retrospective',
    'case_control',
    'cross_sectional',
    'case_series',
    'case_report'
]

# Default study type keywords
DEFAULT_STUDY_TYPE_KEYWORDS = {
    'systematic_review': ['systematic review', 'systematic literature review'],
    'meta_analysis': ['meta-analysis', 'meta analysis', 'pooled analysis'],
    'rct': [
        'randomized controlled trial', 'randomised controlled trial', 'RCT',
        'randomized trial', 'randomised trial', 'random allocation', 'randomly assigned'
    ],
    'interventional_single_arm': [
        'open-label', 'open-labeled', 'open label', 'open labeled',
        'single-arm trial', 'single-arm study', 'single arm trial', 'single arm study',
        'prospective protocol', 'prospective intervention',
        'uncontrolled trial', 'non-randomized trial', 'non-randomised trial',
        'before-and-after study', 'pre-post study', 'pretest-posttest'
    ],
    'cohort_prospective': [
        'prospective cohort', 'prospective study', 'longitudinal cohort',
        'followed prospectively', 'prospective follow-up', 'prospective observation'
    ],
    'cohort_retrospective': ['retrospective cohort', 'retrospective study'],
    'case_control': ['case-control', 'case control study'],
    'cross_sectional': ['cross-sectional', 'cross sectional study', 'prevalence study'],
    'case_series': ['case series', 'case-series'],
    'case_report': ['case report', 'case study']
}

# Default study type hierarchy scores
DEFAULT_STUDY_TYPE_HIERARCHY = {
    'systematic_review': 10.0,
    'meta_analysis': 10.0,
    'rct': 8.0,
    'interventional_single_arm': 7.0,  # Open-label, single-arm interventional studies
    'cohort_prospective': 6.0,
    'cohort_retrospective': 5.0,
    'case_control': 4.0,
    'cross_sectional': 3.0,
    'case_series': 2.0,
    'case_report': 1.0
}

# Sample size regex patterns
SAMPLE_SIZE_PATTERNS = [
    r'n\s*=\s*(\d+)',  # n = 450
    r'N\s*=\s*(\d+)',  # N = 450
    r'(\d+)\s+participants',  # 450 participants
    r'(\d+)\s+subjects',  # 450 subjects
    r'(\d+)\s+patients',  # 450 patients
    r'sample\s+size\s+of\s+(\d+)',  # sample size of 450
    r'total\s+of\s+(\d+)\s+(?:participants|subjects|patients)',  # total of 450 participants
    r'enrolled\s+(\d+)\s+(?:participants|subjects|patients)',  # enrolled 450 participants
    r'recruited\s+(\d+)\s+(?:participants|subjects|patients)',  # recruited 450 participants
]

# Power calculation keywords
POWER_CALCULATION_KEYWORDS = [
    'power calculation',
    'power analysis',
    'sample size calculation',
    'calculated sample size',
    'statistical power',
    'power to detect'
]

# Confidence interval patterns
CI_PATTERNS = [
    r'confidence interval',
    r'\bCI\b',
    r'95%\s*CI',
    r'\[\s*\d+\.?\d*\s*,\s*\d+\.?\d*\s*\]',  # [1.2, 3.4]
    r'\(\s*\d+\.?\d*\s*-\s*\d+\.?\d*\s*\)',  # (1.2-3.4)
]


def extract_text_context(text: str, keyword: str, context_chars: int = 50) -> str:
    """
    Extract text context around a keyword.

    Args:
        text: Full text to search
        keyword: Keyword to find
        context_chars: Characters to include before/after keyword

    Returns:
        Text snippet with context around keyword, empty string if not found
    """
    keyword_pos = text.find(keyword)
    if keyword_pos == -1:
        return ""

    start = max(0, keyword_pos - context_chars)
    end = min(len(text), keyword_pos + len(keyword) + context_chars)

    context = text[start:end]

    # Add ellipsis if truncated
    if start > 0:
        context = "..." + context
    if end < len(text):
        context = context + "..."

    return context


def find_sample_size(text: str, min_n: int = 5, max_n: int = 1000000) -> Optional[int]:
    """
    Find sample size in text using regex patterns.

    Returns largest number found (usually total sample size).

    Args:
        text: Text to search
        min_n: Minimum valid sample size (default: 5)
        max_n: Maximum valid sample size (default: 1,000,000)

    Returns:
        Sample size (int) or None if not found
    """
    found_sizes = []

    for pattern in SAMPLE_SIZE_PATTERNS:
        matches = re.finditer(pattern, text, re.IGNORECASE)
        for match in matches:
            size = int(match.group(1))
            # Filter out unrealistic values
            if min_n <= size <= max_n:
                found_sizes.append(size)

    if not found_sizes:
        return None

    # Return largest (usually total sample size)
    return max(found_sizes)


def calculate_sample_size_score(n: int, log_multiplier: float = 2.0) -> float:
    """
    Calculate sample size score using logarithmic scaling.

    Formula: min(10, log10(n) * log_multiplier)

    Args:
        n: Sample size
        log_multiplier: Multiplier for log10 score (default: 2.0)

    Returns:
        Score (0-10)
    """
    if n <= 0:
        return 0.0

    score = math.log10(n) * log_multiplier
    return min(10.0, max(0.0, score))


def has_power_calculation(text: str) -> bool:
    """
    Check if text mentions power calculation.

    Args:
        text: Text to search

    Returns:
        True if power calculation mentioned
    """
    text_lower = text.lower()
    return any(keyword in text_lower for keyword in POWER_CALCULATION_KEYWORDS)


def find_power_calc_context(text: str) -> str:
    """
    Find context around power calculation mention.

    Args:
        text: Text to search

    Returns:
        Context string around power calculation mention
    """
    text_lower = text.lower()
    for keyword in POWER_CALCULATION_KEYWORDS[:3]:  # Check first 3 most common
        if keyword in text_lower:
            return extract_text_context(text_lower, keyword)
    return ""


def has_ci_reporting(text: str) -> bool:
    """
    Check if text reports confidence intervals.

    Args:
        text: Text to search

    Returns:
        True if confidence intervals are reported
    """
    for pattern in CI_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


def extract_study_type(
    document: Dict[str, Any],
    keywords_config: Optional[Dict[str, List[str]]] = None,
    hierarchy_config: Optional[Dict[str, float]] = None,
    priority_order: Optional[List[str]] = None
) -> DimensionScore:
    """
    Extract study type using keyword matching.

    Matches keywords against abstract and methods section.
    Uses priority hierarchy: systematic review > RCT > cohort > etc.

    Args:
        document: Document dict with 'abstract' and optional 'methods_text' fields
        keywords_config: Dict mapping study types to keyword lists (optional)
        hierarchy_config: Dict mapping study types to scores (optional)
        priority_order: List of study types in priority order (optional)

    Returns:
        DimensionScore for study design with audit trail
    """
    # Use defaults if not provided
    if keywords_config is None:
        keywords_config = DEFAULT_STUDY_TYPE_KEYWORDS
    if hierarchy_config is None:
        hierarchy_config = DEFAULT_STUDY_TYPE_HIERARCHY
    if priority_order is None:
        priority_order = STUDY_TYPE_PRIORITY

    # Get text to search
    abstract = document.get('abstract', '') or ''
    methods = document.get('methods_text', '') or ''
    search_text = f"{abstract} {methods}".lower()

    # Try each study type in priority order
    for study_type in priority_order:
        keywords = keywords_config.get(study_type, [])
        for keyword in keywords:
            if keyword.lower() in search_text:
                # Found match - get score from hierarchy
                score = hierarchy_config.get(study_type, 5.0)

                # Create dimension score with audit trail
                dimension_score = DimensionScore(
                    dimension_name=DIMENSION_STUDY_DESIGN,
                    score=score
                )

                # Find evidence context
                evidence_text = extract_text_context(search_text, keyword.lower())

                dimension_score.add_detail(
                    component='study_type',
                    value=study_type,
                    contribution=score,
                    evidence=evidence_text,
                    reasoning=f"Matched keyword '{keyword}' indicating {study_type.replace('_', ' ')}"
                )

                return dimension_score

    # No match found - default to unknown
    dimension_score = DimensionScore(
        dimension_name=DIMENSION_STUDY_DESIGN,
        score=5.0  # Neutral score
    )
    dimension_score.add_detail(
        component='study_type',
        value='unknown',
        contribution=5.0,
        reasoning='No study type keywords matched - assigned neutral score'
    )

    return dimension_score


def extract_sample_size_dimension(
    document: Dict[str, Any],
    scoring_config: Optional[Dict[str, float]] = None
) -> DimensionScore:
    """
    Extract sample size and calculate dimension score.

    Uses regex patterns to find sample size mentions, applies logarithmic
    scoring, and adds bonuses for power calculation and CI reporting.

    Args:
        document: Document dict with 'abstract' and optional 'methods_text' fields
        scoring_config: Dict with 'log_multiplier', 'power_calculation_bonus',
                       'ci_reported_bonus' keys (optional)

    Returns:
        DimensionScore for sample size with audit trail
    """
    # Default scoring config
    if scoring_config is None:
        scoring_config = {
            'log_multiplier': 2.0,
            'power_calculation_bonus': 2.0,
            'ci_reported_bonus': 0.5
        }

    log_multiplier = scoring_config.get('log_multiplier', 2.0)
    power_bonus = scoring_config.get('power_calculation_bonus', 2.0)
    ci_bonus = scoring_config.get('ci_reported_bonus', 0.5)

    # Get text to search
    abstract = document.get('abstract', '') or ''
    methods = document.get('methods_text', '') or ''
    search_text = f"{abstract} {methods}"

    # Extract sample size
    sample_size = find_sample_size(search_text)

    if sample_size is None:
        # No sample size found
        dimension_score = DimensionScore(
            dimension_name=DIMENSION_SAMPLE_SIZE,
            score=0.0
        )
        dimension_score.add_detail(
            component='extracted_n',
            value='not_found',
            contribution=0.0,
            reasoning='No sample size could be extracted from text'
        )
        return dimension_score

    # Calculate base score using logarithmic scaling
    base_score = calculate_sample_size_score(sample_size, log_multiplier)

    # Create dimension score
    dimension_score = DimensionScore(
        dimension_name=DIMENSION_SAMPLE_SIZE,
        score=base_score
    )

    # Add base score detail
    dimension_score.add_detail(
        component='extracted_n',
        value=str(sample_size),
        contribution=base_score,
        reasoning=f"Log10({sample_size}) * {log_multiplier} = {base_score:.2f}"
    )

    # Check for power calculation
    if has_power_calculation(search_text):
        new_score = min(10.0, dimension_score.score + power_bonus)
        dimension_score.score = new_score
        dimension_score.add_detail(
            component='power_calculation',
            value='yes',
            contribution=power_bonus,
            evidence=find_power_calc_context(search_text),
            reasoning=f'Power calculation mentioned, bonus +{power_bonus}'
        )

    # Check for confidence interval reporting
    if has_ci_reporting(search_text):
        new_score = min(10.0, dimension_score.score + ci_bonus)
        dimension_score.score = new_score
        dimension_score.add_detail(
            component='ci_reporting',
            value='yes',
            contribution=ci_bonus,
            reasoning=f'Confidence intervals reported, bonus +{ci_bonus}'
        )

    return dimension_score


def get_extracted_sample_size(dimension_score: DimensionScore) -> Optional[int]:
    """
    Extract the numeric sample size from a sample size DimensionScore.

    Args:
        dimension_score: DimensionScore from extract_sample_size_dimension

    Returns:
        Sample size as integer, or None if not found/not numeric
    """
    if not dimension_score.details:
        return None

    extracted_value = dimension_score.details[0].extracted_value
    if extracted_value and extracted_value.isdigit():
        return int(extracted_value)
    return None


def get_extracted_study_type(dimension_score: DimensionScore) -> Optional[str]:
    """
    Extract the study type string from a study design DimensionScore.

    Args:
        dimension_score: DimensionScore from extract_study_type

    Returns:
        Study type string, or None if not found
    """
    if not dimension_score.details:
        return None
    return dimension_score.details[0].extracted_value


__all__ = [
    'STUDY_TYPE_PRIORITY',
    'DEFAULT_STUDY_TYPE_KEYWORDS',
    'DEFAULT_STUDY_TYPE_HIERARCHY',
    'SAMPLE_SIZE_PATTERNS',
    'POWER_CALCULATION_KEYWORDS',
    'CI_PATTERNS',
    'extract_text_context',
    'find_sample_size',
    'calculate_sample_size_score',
    'has_power_calculation',
    'find_power_calc_context',
    'has_ci_reporting',
    'extract_study_type',
    'extract_sample_size_dimension',
    'get_extracted_sample_size',
    'get_extracted_study_type',
]
