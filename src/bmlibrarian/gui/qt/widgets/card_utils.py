"""
Utility functions and type definitions for document and citation cards.

This module provides common formatting functions, type validation,
and data structures for card widgets in the BMLibrarian Qt GUI.
"""

from typing import TypedDict, Optional, List, Any, Union
from datetime import datetime
import re


class DocumentData(TypedDict, total=False):
    """Type definition for document card data."""

    document_id: int
    title: str
    authors: Union[str, List[str]]
    journal: str
    year: Union[int, str]
    pmid: Union[int, str]
    doi: str
    abstract: str
    relevance_score: float
    publication_date: str


class CitationData(TypedDict, total=False):
    """Type definition for citation card data."""

    document_id: int
    title: str
    authors: Union[str, List[str]]
    year: Union[int, str]
    pmid: Union[int, str]
    doi: str
    passage: str
    quote: str
    journal: str
    relevance_score: float


def validate_document_data(data: Any) -> DocumentData:
    """
    Validate and normalize document data.

    Args:
        data: Raw document data (dict or object)

    Returns:
        Validated DocumentData dictionary

    Raises:
        TypeError: If data is not a dictionary
        ValueError: If required fields are missing
    """
    if not isinstance(data, dict):
        raise TypeError(f"Document data must be a dictionary, got {type(data).__name__}")

    # Ensure at least a title exists
    if 'title' not in data and 'document_id' not in data:
        raise ValueError("Document data must contain at least 'title' or 'document_id'")

    return data  # TypedDict is not enforced at runtime, just type hints


def validate_citation_data(data: Any) -> CitationData:
    """
    Validate and normalize citation data.

    Args:
        data: Raw citation data (dict or object)

    Returns:
        Validated CitationData dictionary

    Raises:
        TypeError: If data is not a dictionary
        ValueError: If required fields are missing
    """
    if not isinstance(data, dict):
        raise TypeError(f"Citation data must be a dictionary, got {type(data).__name__}")

    # Ensure at least title and passage/quote exist
    if 'title' not in data:
        raise ValueError("Citation data must contain 'title'")

    if 'passage' not in data and 'quote' not in data:
        raise ValueError("Citation data must contain 'passage' or 'quote'")

    return data


def extract_year(year_data: Union[int, str, None]) -> str:
    """
    Extract and format year from various input formats.

    Args:
        year_data: Year as int, string, or None

    Returns:
        Formatted year string, or empty string if invalid

    Examples:
        >>> extract_year(2023)
        '2023'
        >>> extract_year("2023-01-15")
        '2023'
        >>> extract_year("2023")
        '2023'
        >>> extract_year(None)
        ''
    """
    if year_data is None:
        return ""

    if isinstance(year_data, int):
        return str(year_data)

    if isinstance(year_data, str):
        # Try to extract 4-digit year
        year_match = re.search(r'\b(19|20)\d{2}\b', year_data)
        if year_match:
            return year_match.group(0)
        # If it's just a number string
        if year_data.isdigit() and len(year_data) == 4:
            return year_data

    return ""


def format_authors(
    authors: Union[str, List[str], None],
    max_authors: int = 3,
    et_al: bool = True
) -> str:
    """
    Format author list for display.

    Args:
        authors: Author data as string or list of strings
        max_authors: Maximum number of authors to display
        et_al: Whether to add "et al." for truncated lists

    Returns:
        Formatted author string

    Examples:
        >>> format_authors(["Smith J", "Jones A", "Brown B"])
        'Smith J, Jones A, Brown B'
        >>> format_authors(["Smith J", "Jones A", "Brown B", "Davis C"], max_authors=2)
        'Smith J, Jones A et al.'
        >>> format_authors("Smith J, Jones A")
        'Smith J, Jones A'
    """
    if not authors:
        return "Unknown authors"

    if isinstance(authors, str):
        # Already formatted string
        return authors

    if isinstance(authors, list):
        if not authors:
            return "Unknown authors"

        # Take first N authors
        displayed_authors = authors[:max_authors]
        result = ", ".join(displayed_authors)

        # Add et al. if truncated
        if et_al and len(authors) > max_authors:
            result += " et al."

        return result

    return "Unknown authors"


def format_journal_year(journal: Optional[str], year: Optional[Union[int, str]]) -> str:
    """
    Format journal and year for display.

    Args:
        journal: Journal name
        year: Publication year

    Returns:
        Formatted "Journal (Year)" string

    Examples:
        >>> format_journal_year("Nature", 2023)
        'Nature (2023)'
        >>> format_journal_year("Nature", None)
        'Nature'
        >>> format_journal_year(None, 2023)
        '(2023)'
    """
    journal_text = journal if journal else ""
    year_str = extract_year(year)
    year_text = f" ({year_str})" if year_str else ""

    return f"{journal_text}{year_text}".strip()


def format_document_ids(
    pmid: Optional[Union[int, str]] = None,
    doi: Optional[str] = None,
    doc_id: Optional[int] = None,
    separator: str = " | "
) -> str:
    """
    Format document identifiers (PMID, DOI, internal ID) for display.

    Args:
        pmid: PubMed ID
        doi: Digital Object Identifier
        doc_id: Internal document ID
        separator: String to separate multiple IDs

    Returns:
        Formatted ID string

    Examples:
        >>> format_document_ids(pmid=12345678, doi="10.1234/example")
        'PMID: 12345678 | DOI: 10.1234/example'
        >>> format_document_ids(pmid=12345678)
        'PMID: 12345678'
    """
    id_parts = []

    if pmid:
        id_parts.append(f"PMID: {pmid}")

    if doi:
        id_parts.append(f"DOI: {doi}")

    if doc_id and not pmid:
        # Only show internal ID if PMID not available
        id_parts.append(f"ID: {doc_id}")

    return separator.join(id_parts)


def truncate_text(text: str, max_length: int = 200, suffix: str = "...") -> str:
    """
    Truncate text to maximum length with suffix.

    Args:
        text: Text to truncate
        max_length: Maximum length including suffix
        suffix: String to append to truncated text

    Returns:
        Truncated text

    Examples:
        >>> truncate_text("This is a very long text", max_length=10)
        'This is...'
    """
    if not text or len(text) <= max_length:
        return text

    return text[:max_length - len(suffix)] + suffix


def html_escape(text: str) -> str:
    """
    Escape HTML special characters for safe display.

    Args:
        text: Text to escape

    Returns:
        HTML-escaped text
    """
    if not text:
        return ""

    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#39;"))


def format_relevance_score(score: Optional[float], max_score: float = 5.0) -> str:
    """
    Format relevance score for display.

    Args:
        score: Relevance score value
        max_score: Maximum possible score

    Returns:
        Formatted score string

    Examples:
        >>> format_relevance_score(4.5)
        'Relevance Score: 4.5/5'
        >>> format_relevance_score(None)
        ''
    """
    if score is None:
        return ""

    return f"Relevance Score: {score:.1f}/{max_score:.0f}"


def format_similarity_score(score: Optional[float]) -> str:
    """
    Format semantic similarity score for display.

    Similarity scores are in 0-1 range, displayed as percentage.

    Args:
        score: Similarity score value (0.0 to 1.0)

    Returns:
        Formatted similarity string

    Examples:
        >>> format_similarity_score(0.85)
        'Similarity: 85%'
        >>> format_similarity_score(None)
        ''
    """
    if score is None:
        return ""

    percentage = score * 100
    return f"Similarity: {percentage:.0f}%"
