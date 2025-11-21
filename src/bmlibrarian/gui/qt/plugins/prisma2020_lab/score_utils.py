"""
Pure utility functions for PRISMA 2020 score and compliance color calculations.

These functions are stateless and can be reused across different UI components.
"""

from functools import lru_cache

from .constants import (
    SCORE_COLORS,
    COMPLIANCE_COLORS,
    COMPLIANCE_BG_COLORS,
    SCORE_FULLY_REPORTED_THRESHOLD,
    SCORE_PARTIALLY_REPORTED_THRESHOLD,
    COMPLIANCE_EXCELLENT_THRESHOLD,
    COMPLIANCE_GOOD_THRESHOLD,
    COMPLIANCE_ADEQUATE_THRESHOLD,
    COMPLIANCE_POOR_THRESHOLD,
    SYMBOL_FULLY_REPORTED,
    SYMBOL_PARTIALLY_REPORTED,
    SYMBOL_NOT_REPORTED,
)


def get_score_color(score: float) -> str:
    """
    Get color based on PRISMA item score.

    Args:
        score: Score value (0.0 = not reported, 1.0 = partial, 2.0 = fully reported)

    Returns:
        Hex color string for the score level
    """
    if score >= SCORE_FULLY_REPORTED_THRESHOLD:
        return SCORE_COLORS[2.0]
    elif score >= SCORE_PARTIALLY_REPORTED_THRESHOLD:
        return SCORE_COLORS[1.0]
    else:
        return SCORE_COLORS[0.0]


@lru_cache(maxsize=128)
def get_score_text(score: float) -> str:
    """
    Get text description for score with symbol.

    Uses LRU cache for performance since scores are typically discrete values.

    Args:
        score: Score value (0.0-2.0)

    Returns:
        Formatted string with symbol and score description
    """
    if score >= SCORE_FULLY_REPORTED_THRESHOLD:
        return f"{SYMBOL_FULLY_REPORTED} Fully Reported ({score:.1f})"
    elif score >= SCORE_PARTIALLY_REPORTED_THRESHOLD:
        return f"{SYMBOL_PARTIALLY_REPORTED} Partial ({score:.1f})"
    else:
        return f"{SYMBOL_NOT_REPORTED} Not Reported ({score:.1f})"


def get_compliance_color(percentage: float) -> str:
    """
    Get color based on overall compliance percentage.

    Args:
        percentage: Compliance percentage (0-100)

    Returns:
        Hex color string for the compliance level
    """
    if percentage >= COMPLIANCE_EXCELLENT_THRESHOLD:
        return COMPLIANCE_COLORS['excellent']
    elif percentage >= COMPLIANCE_GOOD_THRESHOLD:
        return COMPLIANCE_COLORS['good']
    elif percentage >= COMPLIANCE_ADEQUATE_THRESHOLD:
        return COMPLIANCE_COLORS['adequate']
    elif percentage >= COMPLIANCE_POOR_THRESHOLD:
        return COMPLIANCE_COLORS['poor']
    else:
        return COMPLIANCE_COLORS['very_poor']


def get_compliance_bg_color(category: str) -> str:
    """
    Get background color based on compliance category string.

    Args:
        category: Compliance category string from PRISMA2020Assessment.get_compliance_category()

    Returns:
        Hex color string for background
    """
    if '≥90%' in category:
        return COMPLIANCE_BG_COLORS['excellent']
    elif '75-89%' in category:
        return COMPLIANCE_BG_COLORS['good']
    elif '60-74%' in category:
        return COMPLIANCE_BG_COLORS['adequate']
    elif '40-59%' in category:
        return COMPLIANCE_BG_COLORS['poor']
    else:
        return COMPLIANCE_BG_COLORS['very_poor']


def format_compliance_stats(
    total_items: int,
    fully_reported: int,
    partially_reported: int,
    not_reported: int
) -> str:
    """
    Format compliance statistics as a single-line summary string.

    Args:
        total_items: Total number of applicable items assessed
        fully_reported: Number of fully reported items
        partially_reported: Number of partially reported items
        not_reported: Number of not reported items

    Returns:
        Formatted statistics string
    """
    return (
        f"Items Assessed: {total_items} | "
        f"Fully Reported: {fully_reported} | "
        f"Partially Reported: {partially_reported} | "
        f"Not Reported: {not_reported}"
    )


def format_document_type_display(is_systematic_review: bool, is_meta_analysis: bool) -> str:
    """
    Format document type for display with checkmarks.

    Args:
        is_systematic_review: Whether document is a systematic review
        is_meta_analysis: Whether document is a meta-analysis

    Returns:
        Formatted document type string
    """
    doc_types = []
    if is_systematic_review:
        doc_types.append("✓ Systematic Review")
    if is_meta_analysis:
        doc_types.append("✓ Meta-Analysis")

    return " | ".join(doc_types) if doc_types else "Not a systematic review or meta-analysis"
