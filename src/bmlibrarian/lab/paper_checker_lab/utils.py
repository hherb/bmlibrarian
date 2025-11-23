"""
PaperChecker Laboratory - Pure Utility Functions

Reusable pure functions for text formatting, display preparation, and data transformation.
These functions have no side effects and are easily testable.

This module can be imported without Qt dependencies.
"""

from typing import Optional, List, Dict, Any, Tuple, Union
from datetime import datetime

from .constants import (
    SCORE_DECIMALS, AUTHOR_DISPLAY_MAX_LENGTH, TITLE_DISPLAY_MAX_LENGTH,
    PASSAGE_PREVIEW_LENGTH, MIN_ABSTRACT_LENGTH, MAX_ABSTRACT_LENGTH,
    PMID_MAX_LENGTH, WORKFLOW_STEPS, WORKFLOW_STEP_COUNT,
    VERDICT_COLORS, CONFIDENCE_COLORS, STATEMENT_TYPE_COLORS, SEARCH_STRATEGY_COLORS
)


# =============================================================================
# Input Validation Functions
# =============================================================================

def validate_abstract(abstract: str) -> Tuple[bool, str]:
    """
    Validate abstract text for processing.

    Args:
        abstract: Abstract text to validate

    Returns:
        Tuple of (is_valid, error_message). error_message is empty if valid.
    """
    if not abstract:
        return False, "Abstract text is required"

    stripped = abstract.strip()
    if not stripped:
        return False, "Abstract text cannot be empty or whitespace only"

    if len(stripped) < MIN_ABSTRACT_LENGTH:
        return False, f"Abstract must be at least {MIN_ABSTRACT_LENGTH} characters"

    if len(stripped) > MAX_ABSTRACT_LENGTH:
        return False, f"Abstract exceeds maximum length of {MAX_ABSTRACT_LENGTH} characters"

    return True, ""


def validate_pmid(pmid_str: str) -> Tuple[bool, Optional[int], str]:
    """
    Validate and parse a PMID string.

    Args:
        pmid_str: PMID string to validate

    Returns:
        Tuple of (is_valid, parsed_pmid, error_message).
        parsed_pmid is None if invalid.
    """
    if not pmid_str:
        return False, None, "PMID is required"

    stripped = pmid_str.strip()
    if not stripped:
        return False, None, "PMID cannot be empty"

    if not stripped.isdigit():
        return False, None, "PMID must contain only digits"

    if len(stripped) > PMID_MAX_LENGTH:
        return False, None, f"PMID exceeds maximum length of {PMID_MAX_LENGTH} digits"

    pmid = int(stripped)
    if pmid <= 0:
        return False, None, "PMID must be a positive integer"

    return True, pmid, ""


# =============================================================================
# Verdict and Confidence Formatting
# =============================================================================

def format_verdict_display(verdict: str) -> Tuple[str, str]:
    """
    Format verdict for display with appropriate color.

    Args:
        verdict: Verdict string ("supports", "contradicts", "undecided")

    Returns:
        Tuple of (display_text, color_hex)
    """
    display_map = {
        "supports": "Supports",
        "contradicts": "Contradicts",
        "undecided": "Undecided"
    }
    display_text = display_map.get(verdict.lower(), verdict.title())
    color = VERDICT_COLORS.get(verdict.lower(), VERDICT_COLORS["undecided"])
    return display_text, color


def format_confidence_display(confidence: str) -> Tuple[str, str]:
    """
    Format confidence level for display with appropriate color.

    Args:
        confidence: Confidence string ("high", "medium", "low")

    Returns:
        Tuple of (display_text, color_hex)
    """
    display_map = {
        "high": "High",
        "medium": "Medium",
        "low": "Low"
    }
    display_text = display_map.get(confidence.lower(), confidence.title())
    color = CONFIDENCE_COLORS.get(confidence.lower(), CONFIDENCE_COLORS["medium"])
    return display_text, color


def format_statement_type_display(statement_type: str) -> Tuple[str, str]:
    """
    Format statement type for display with appropriate color.

    Args:
        statement_type: Statement type ("hypothesis", "finding", "conclusion")

    Returns:
        Tuple of (display_text, color_hex)
    """
    display_map = {
        "hypothesis": "Hypothesis",
        "finding": "Finding",
        "conclusion": "Conclusion"
    }
    display_text = display_map.get(statement_type.lower(), statement_type.title())
    color = STATEMENT_TYPE_COLORS.get(statement_type.lower(), STATEMENT_TYPE_COLORS["finding"])
    return display_text, color


def format_search_strategy_display(strategy: str) -> Tuple[str, str]:
    """
    Format search strategy name for display with color.

    Args:
        strategy: Strategy name ("semantic", "hyde", "keyword")

    Returns:
        Tuple of (display_text, color_hex)
    """
    display_map = {
        "semantic": "Semantic",
        "hyde": "HyDE",
        "keyword": "Keyword"
    }
    display_text = display_map.get(strategy.lower(), strategy.title())
    color = SEARCH_STRATEGY_COLORS.get(strategy.lower(), SEARCH_STRATEGY_COLORS["semantic"])
    return display_text, color


# =============================================================================
# Score Formatting
# =============================================================================

def format_score(score: Union[int, float], decimals: int = SCORE_DECIMALS) -> str:
    """
    Format a relevance score for display.

    Args:
        score: Numeric score value (1-5)
        decimals: Number of decimal places

    Returns:
        Formatted score string (e.g., "4.5")
    """
    return f"{score:.{decimals}f}"


def format_score_badge(score: Union[int, float]) -> Tuple[str, str]:
    """
    Format score as a badge with color based on value.

    Args:
        score: Numeric score value (1-5)

    Returns:
        Tuple of (formatted_score, color_hex)
    """
    formatted = format_score(score)

    # Color based on score value
    if score >= 4:
        color = CONFIDENCE_COLORS["high"]  # Green for high scores
    elif score >= 3:
        color = CONFIDENCE_COLORS["medium"]  # Orange for medium
    else:
        color = CONFIDENCE_COLORS["low"]  # Red for low

    return formatted, color


# =============================================================================
# Text Truncation with Full Text Preservation
# =============================================================================

def truncate_with_ellipsis(
    text: str,
    max_length: int,
    ellipsis: str = '...'
) -> Tuple[str, bool]:
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
    if truncate_at < 0:
        truncate_at = 0
    return text[:truncate_at] + ellipsis, True


def truncate_authors(authors: Optional[Union[str, List[str]]]) -> str:
    """
    Truncate authors string for display.

    Args:
        authors: Author string or list of authors (may be long)

    Returns:
        Truncated authors string with ellipsis if needed
    """
    if not authors:
        return ''

    # Handle list of authors (from PostgreSQL array)
    if isinstance(authors, list):
        authors = ', '.join(str(a) for a in authors if a)

    truncated, _ = truncate_with_ellipsis(authors, AUTHOR_DISPLAY_MAX_LENGTH)
    return truncated


def truncate_title(title: Optional[str]) -> str:
    """
    Truncate title for compact display.

    Args:
        title: Document title

    Returns:
        Truncated title with ellipsis if needed
    """
    if not title:
        return ''

    truncated, _ = truncate_with_ellipsis(title, TITLE_DISPLAY_MAX_LENGTH)
    return truncated


def truncate_passage(passage: Optional[str]) -> Tuple[str, bool]:
    """
    Truncate citation passage for preview display.

    Args:
        passage: Citation passage text

    Returns:
        Tuple of (truncated_text, was_truncated)
    """
    if not passage:
        return '', False

    return truncate_with_ellipsis(passage, PASSAGE_PREVIEW_LENGTH)


# =============================================================================
# Datetime Formatting
# =============================================================================

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


def format_duration(seconds: float) -> str:
    """
    Format duration in seconds for display.

    Args:
        seconds: Duration in seconds

    Returns:
        Human-readable duration string
    """
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f}m"
    else:
        hours = seconds / 3600
        return f"{hours:.1f}h"


# =============================================================================
# Metadata Formatting
# =============================================================================

def format_document_metadata(
    authors: Optional[Union[str, List[str]]] = None,
    year: Optional[int] = None,
    pmid: Optional[int] = None,
    doi: Optional[str] = None,
    journal: Optional[str] = None
) -> str:
    """
    Format document metadata for display.

    Args:
        authors: Author string or list
        year: Publication year
        pmid: PubMed ID
        doi: Digital Object Identifier
        journal: Journal name

    Returns:
        Formatted metadata string with pipe separators
    """
    parts = []

    if authors:
        parts.append(truncate_authors(authors))
    if year:
        parts.append(str(year))
    if journal:
        parts.append(journal)
    if pmid:
        parts.append(f"PMID: {pmid}")
    if doi:
        parts.append(f"DOI: {doi}")

    return ' | '.join(parts)


def format_ama_citation(
    authors: Optional[Union[str, List[str]]],
    title: Optional[str],
    journal: Optional[str],
    year: Optional[int],
    doi: Optional[str] = None,
    max_authors: int = 3
) -> str:
    """
    Format citation in AMA style.

    Args:
        authors: Author(s)
        title: Paper title
        journal: Journal name
        year: Publication year
        doi: DOI if available
        max_authors: Maximum authors before "et al"

    Returns:
        AMA-formatted citation string
    """
    parts = []

    # Format authors
    if authors:
        if isinstance(authors, list):
            if len(authors) > max_authors:
                author_str = ', '.join(authors[:max_authors]) + ', et al'
            else:
                author_str = ', '.join(authors)
        else:
            author_str = authors
        parts.append(author_str)

    # Title
    if title:
        parts.append(title)

    # Journal and year
    if journal:
        if year:
            parts.append(f"{journal}. {year}")
        else:
            parts.append(journal)
    elif year:
        parts.append(str(year))

    # DOI
    if doi:
        parts.append(f"doi:{doi}")

    return '. '.join(parts)


# =============================================================================
# Search Statistics Formatting
# =============================================================================

def format_search_stats(search_results: Any) -> Dict[str, Any]:
    """
    Format search results statistics for display.

    Args:
        search_results: SearchResults object with strategy counts

    Returns:
        Dict with formatted statistics
    """
    stats = {
        'semantic_count': len(getattr(search_results, 'semantic_docs', [])),
        'hyde_count': len(getattr(search_results, 'hyde_docs', [])),
        'keyword_count': len(getattr(search_results, 'keyword_docs', [])),
        'deduplicated_count': len(getattr(search_results, 'deduplicated_docs', [])),
    }

    # Calculate unique contribution per strategy
    provenance = getattr(search_results, 'provenance', {})
    stats['unique_by_strategy'] = count_unique_by_strategy(provenance)

    return stats


def count_unique_by_strategy(provenance: Dict[int, List[str]]) -> Dict[str, int]:
    """
    Count documents unique to each search strategy.

    Args:
        provenance: Dict mapping doc_id to list of strategies that found it

    Returns:
        Dict mapping strategy name to count of docs found only by that strategy
    """
    unique_counts = {'semantic': 0, 'hyde': 0, 'keyword': 0}

    for doc_id, strategies in provenance.items():
        if len(strategies) == 1:
            strategy = strategies[0].lower()
            if strategy in unique_counts:
                unique_counts[strategy] += 1

    return unique_counts


def format_provenance_display(strategies: List[str]) -> str:
    """
    Format provenance strategies for display.

    Args:
        strategies: List of strategy names that found the document

    Returns:
        Formatted string like "Semantic, HyDE"
    """
    display_names = []
    for strategy in strategies:
        display, _ = format_search_strategy_display(strategy)
        display_names.append(display)
    return ', '.join(display_names)


# =============================================================================
# Workflow Progress
# =============================================================================

def get_workflow_step_index(step_name: str) -> int:
    """
    Get the index of a workflow step by name.

    Args:
        step_name: Name of the workflow step

    Returns:
        Index of the step, or -1 if not found
    """
    # Try exact match first
    try:
        return WORKFLOW_STEPS.index(step_name)
    except ValueError:
        pass

    # Try case-insensitive partial match
    step_lower = step_name.lower()
    for i, ws in enumerate(WORKFLOW_STEPS):
        if step_lower in ws.lower() or ws.lower() in step_lower:
            return i

    return -1


def calculate_workflow_progress(step_index: int) -> float:
    """
    Calculate workflow progress as a fraction.

    Args:
        step_index: Current step index (0-based)

    Returns:
        Progress as float from 0.0 to 1.0
    """
    if step_index < 0:
        return 0.0
    if step_index >= WORKFLOW_STEP_COUNT:
        return 1.0
    return (step_index + 1) / WORKFLOW_STEP_COUNT


def map_agent_progress_to_step(step_name: str, progress: float) -> Tuple[int, str]:
    """
    Map agent progress callback to workflow step.

    Args:
        step_name: Step name from agent callback
        progress: Progress fraction from agent

    Returns:
        Tuple of (step_index, display_step_name)
    """
    step_index = get_workflow_step_index(step_name)
    if step_index >= 0:
        return step_index, WORKFLOW_STEPS[step_index]

    # Default to initializing if unknown
    return 0, WORKFLOW_STEPS[0]


# =============================================================================
# Data Extraction Helpers
# =============================================================================

def extract_year_from_date(publication_date: Optional[Any]) -> Optional[int]:
    """
    Extract year from various date formats.

    Args:
        publication_date: Date in various formats (datetime, string, int)

    Returns:
        Year as integer, or None if extraction fails
    """
    if publication_date is None:
        return None

    if isinstance(publication_date, datetime):
        return publication_date.year

    if isinstance(publication_date, int):
        # Assume it's already a year if 4 digits
        if 1900 <= publication_date <= 2100:
            return publication_date
        return None

    if isinstance(publication_date, str):
        # Try to extract 4-digit year
        import re
        match = re.search(r'\b(19|20)\d{2}\b', publication_date)
        if match:
            return int(match.group())

    return None


def safe_get_nested(data: Dict[str, Any], *keys: str, default: Any = None) -> Any:
    """
    Safely get nested dictionary value.

    Args:
        data: Dictionary to search
        *keys: Sequence of keys to traverse
        default: Default value if key path not found

    Returns:
        Value at key path, or default
    """
    current = data
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key, default)
        if current is None:
            return default
    return current


# =============================================================================
# Module Exports
# =============================================================================

__all__ = [
    # Validation
    'validate_abstract',
    'validate_pmid',
    # Verdict/confidence formatting
    'format_verdict_display',
    'format_confidence_display',
    'format_statement_type_display',
    'format_search_strategy_display',
    # Score formatting
    'format_score',
    'format_score_badge',
    # Truncation
    'truncate_with_ellipsis',
    'truncate_authors',
    'truncate_title',
    'truncate_passage',
    # Datetime
    'format_datetime',
    'format_duration',
    # Metadata
    'format_document_metadata',
    'format_ama_citation',
    # Search stats
    'format_search_stats',
    'count_unique_by_strategy',
    'format_provenance_display',
    # Workflow
    'get_workflow_step_index',
    'calculate_workflow_progress',
    'map_agent_progress_to_step',
    # Data extraction
    'extract_year_from_date',
    'safe_get_nested',
]
