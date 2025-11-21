"""
Paper Weight Laboratory - Pure Utility Functions

Reusable pure functions for text formatting, display preparation, and data transformation.
These functions have no side effects and are easily testable.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime

from .constants import SCORE_DECIMALS, AUTHOR_DISPLAY_MAX_LENGTH


# =============================================================================
# Text Formatting Functions
# =============================================================================

def format_dimension_name(dimension: str) -> str:
    """
    Format dimension name for display (e.g., 'study_design' -> 'Study Design').

    Args:
        dimension: Internal dimension name with underscores

    Returns:
        Human-readable dimension name with title case
    """
    return dimension.replace('_', ' ').title()


def format_score(score: float, decimals: int = SCORE_DECIMALS) -> str:
    """
    Format a score for display.

    Args:
        score: Numeric score value
        decimals: Number of decimal places

    Returns:
        Formatted score string (e.g., "7.50")
    """
    return f"{score:.{decimals}f}"


def format_score_with_max(score: float, max_score: float = 10.0) -> str:
    """
    Format a score with maximum for display (e.g., "7.50/10").

    Args:
        score: Numeric score value
        max_score: Maximum possible score

    Returns:
        Formatted string like "7.50/10"
    """
    return f"{format_score(score)}/{int(max_score)}"


def format_datetime(dt: datetime, fmt: str = '%Y-%m-%d %H:%M') -> str:
    """
    Format datetime for display.

    Args:
        dt: Datetime object
        fmt: strftime format string

    Returns:
        Formatted datetime string
    """
    return dt.strftime(fmt)


# =============================================================================
# Text Truncation with Full Text Preservation
# =============================================================================

def truncate_with_ellipsis(
    text: str,
    max_length: int,
    ellipsis: str = '...'
) -> tuple[str, bool]:
    """
    Truncate text if it exceeds max_length, appending ellipsis.

    This function returns both the truncated text AND a flag indicating
    whether truncation occurred, so the caller can provide access to full text.

    Args:
        text: Text to potentially truncate
        max_length: Maximum length before truncation
        ellipsis: String to append when truncating

    Returns:
        Tuple of (displayed_text, was_truncated)
    """
    if not text:
        return '', False

    if len(text) <= max_length:
        return text, False

    truncate_at = max_length - len(ellipsis)
    return text[:truncate_at] + ellipsis, True


def truncate_authors(authors: Optional[str]) -> str:
    """
    Truncate authors string for display.

    Args:
        authors: Author string (may be long)

    Returns:
        Truncated authors string with ellipsis if needed
    """
    if not authors:
        return ''

    truncated, _ = truncate_with_ellipsis(authors, AUTHOR_DISPLAY_MAX_LENGTH)
    return truncated


# =============================================================================
# Metadata Formatting
# =============================================================================

def format_document_metadata(
    authors: Optional[str] = None,
    year: Optional[int] = None,
    pmid: Optional[int] = None,
    doi: Optional[str] = None
) -> str:
    """
    Format document metadata for display.

    Args:
        authors: Author string
        year: Publication year
        pmid: PubMed ID
        doi: Digital Object Identifier

    Returns:
        Formatted metadata string with pipe separators
    """
    parts = []

    if authors:
        parts.append(truncate_authors(authors))
    if year:
        parts.append(str(year))
    if pmid:
        parts.append(f"PMID: {pmid}")
    if doi:
        parts.append(f"DOI: {doi}")

    return ' | '.join(parts)


def format_recent_assessment_display(
    title: Optional[str],
    final_weight: float,
    max_title_length: int = 60
) -> str:
    """
    Format a recent assessment for dropdown display.

    Args:
        title: Document title
        final_weight: Assessment score
        max_title_length: Maximum title length before truncation

    Returns:
        Formatted string like "[7.5] Paper Title..."
    """
    display_title = title or 'No title'
    truncated, was_truncated = truncate_with_ellipsis(display_title, max_title_length)

    return f"[{final_weight:.1f}] {truncated}"


# =============================================================================
# Data Transformation Functions
# =============================================================================

def extract_dimension_score_data(result: Any, dimension: str) -> Dict[str, Any]:
    """
    Extract dimension score data from a PaperWeightResult.

    Args:
        result: PaperWeightResult object
        dimension: Dimension name

    Returns:
        Dict with 'score', 'details', 'display_name'
    """
    dim_score = getattr(result, dimension)
    return {
        'score': dim_score.score,
        'details': dim_score.details,
        'display_name': format_dimension_name(dimension)
    }


def prepare_tree_item_data(
    component: str,
    value: Optional[str],
    score: float,
    evidence: Optional[str],
    reasoning: Optional[str]
) -> Dict[str, Any]:
    """
    Prepare data for a tree widget item.

    Returns both display values and full values for tooltips.
    NO truncation is applied - callers should set tooltips with full values.

    Args:
        component: Component name
        value: Extracted value
        score: Score contribution
        evidence: Evidence text
        reasoning: LLM reasoning

    Returns:
        Dict with display data and full text for tooltips
    """
    return {
        'component': component,
        'value': value or '',
        'score': format_score(score),
        'evidence': evidence or '',
        'reasoning': reasoning or '',
    }


# =============================================================================
# Weight Validation
# =============================================================================

def validate_weights_sum(weights: Dict[str, float], tolerance: float = 0.01) -> tuple[bool, float]:
    """
    Validate that weights sum to 1.0.

    Args:
        weights: Dict of dimension weights
        tolerance: Acceptable deviation from 1.0

    Returns:
        Tuple of (is_valid, actual_sum)
    """
    total = sum(weights.values())
    is_valid = abs(total - 1.0) <= tolerance
    return is_valid, total


def slider_value_to_weight(slider_value: int, precision: int = 100) -> float:
    """
    Convert slider integer value to weight float.

    Args:
        slider_value: Integer from slider (0-100)
        precision: Divisor to get weight

    Returns:
        Weight as float (0.00-1.00)
    """
    return slider_value / precision


def weight_to_slider_value(weight: float, precision: int = 100) -> int:
    """
    Convert weight float to slider integer value.

    Args:
        weight: Weight as float (0.00-1.00)
        precision: Multiplier for slider value

    Returns:
        Integer for slider (0-100)
    """
    return int(weight * precision)


__all__ = [
    # Text formatting
    'format_dimension_name',
    'format_score',
    'format_score_with_max',
    'format_datetime',
    # Truncation
    'truncate_with_ellipsis',
    'truncate_authors',
    # Metadata
    'format_document_metadata',
    'format_recent_assessment_display',
    # Data transformation
    'extract_dimension_score_data',
    'prepare_tree_item_data',
    # Weights
    'validate_weights_sum',
    'slider_value_to_weight',
    'weight_to_slider_value',
]
