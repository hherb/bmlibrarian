"""Document data structure models for BMLibrarian.

Provides TypedDict definitions and validation utilities for document data structures
used throughout the BMLibrarian system. Replaces ad-hoc dict validation with
structured, type-safe models.
"""

from typing import TypedDict, List, Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


class DocumentDict(TypedDict, total=False):
    """Standard document dictionary structure.

    Used throughout BMLibrarian for representing biomedical literature documents
    from the PostgreSQL database.

    Fields:
        id: Unique document identifier (required)
        title: Document title (required)
        abstract: Document abstract text (required)
        authors: List of author names
        publication_date: Publication date string
        year: Publication year
        journal: Journal name
        doi: Digital Object Identifier
        pmid: PubMed ID
        pmc_id: PubMed Central ID
        full_text: Full text content (if available)
        keywords: List of keywords/MeSH terms
        metadata: Additional metadata dictionary
    """
    # Required fields
    id: str
    title: str
    abstract: str

    # Optional fields
    authors: List[str]
    publication_date: str
    year: int
    journal: str
    doi: str
    pmid: str
    pmc_id: str
    full_text: str
    keywords: List[str]
    metadata: Dict[str, Any]


class ScoreResult(TypedDict):
    """Document scoring result structure.

    Returned by DocumentScoringAgent for each scored document.

    Fields:
        score: Relevance score (1-5 scale, where 5 is most relevant)
        reasoning: Explanation of the score
    """
    score: int
    reasoning: str


class ScoredDocument(TypedDict):
    """Combined document and score result.

    Tuple-like structure used in workflow for documents with scores.

    Fields:
        document: The document dictionary
        score_result: The scoring result
    """
    document: DocumentDict
    score_result: ScoreResult


def validate_document(doc: Dict[str, Any], strict: bool = False) -> bool:
    """Validate that a dictionary has required document fields.

    Args:
        doc: Dictionary to validate
        strict: If True, raises ValueError on validation failure.
                If False, logs warning and returns False.

    Returns:
        True if document is valid, False otherwise

    Raises:
        ValueError: If strict=True and validation fails

    Examples:
        >>> doc = {"id": "123", "title": "Test", "abstract": "..."}
        >>> validate_document(doc)
        True

        >>> invalid = {"title": "Missing ID"}
        >>> validate_document(invalid)
        False
    """
    required_fields = ['id', 'title', 'abstract']

    for field in required_fields:
        if field not in doc:
            msg = f"Document missing required field: {field}"
            if strict:
                raise ValueError(msg)
            else:
                logger.warning(f"{msg}. Document: {doc.get('id', 'unknown')}")
                return False

    # Validate field types
    if not isinstance(doc['id'], str) or not doc['id'].strip():
        msg = "Document ID must be a non-empty string"
        if strict:
            raise ValueError(msg)
        else:
            logger.warning(msg)
            return False

    if not isinstance(doc['title'], str) or not doc['title'].strip():
        msg = "Document title must be a non-empty string"
        if strict:
            raise ValueError(msg)
        else:
            logger.warning(f"{msg}. Document ID: {doc.get('id', 'unknown')}")
            return False

    if not isinstance(doc['abstract'], str):
        msg = "Document abstract must be a string"
        if strict:
            raise ValueError(msg)
        else:
            logger.warning(f"{msg}. Document ID: {doc.get('id', 'unknown')}")
            return False

    return True


def validate_score_result(result: Dict[str, Any], strict: bool = False) -> bool:
    """Validate that a dictionary is a valid scoring result.

    Args:
        result: Dictionary to validate
        strict: If True, raises ValueError on validation failure.
                If False, logs warning and returns False.

    Returns:
        True if result is valid, False otherwise

    Raises:
        ValueError: If strict=True and validation fails

    Examples:
        >>> result = {"score": 4, "reasoning": "Highly relevant"}
        >>> validate_score_result(result)
        True

        >>> invalid = {"score": 10, "reasoning": "Invalid score"}
        >>> validate_score_result(invalid)
        False
    """
    if 'score' not in result:
        msg = "Score result missing required field: score"
        if strict:
            raise ValueError(msg)
        else:
            logger.warning(msg)
            return False

    if 'reasoning' not in result:
        msg = "Score result missing required field: reasoning"
        if strict:
            raise ValueError(msg)
        else:
            logger.warning(msg)
            return False

    # Validate score range (1-5)
    score = result['score']
    if not isinstance(score, int) or not (1 <= score <= 5):
        msg = f"Score must be an integer between 1 and 5, got: {score}"
        if strict:
            raise ValueError(msg)
        else:
            logger.warning(msg)
            return False

    # Validate reasoning
    if not isinstance(result['reasoning'], str) or not result['reasoning'].strip():
        msg = "Reasoning must be a non-empty string"
        if strict:
            raise ValueError(msg)
        else:
            logger.warning(msg)
            return False

    return True


def get_document_year(doc: Dict[str, Any]) -> Optional[int]:
    """Extract publication year from document.

    Tries multiple fields: 'year', 'publication_date'.

    Args:
        doc: Document dictionary

    Returns:
        Publication year as integer, or None if not found

    Examples:
        >>> doc = {"year": 2023, "title": "Test"}
        >>> get_document_year(doc)
        2023

        >>> doc = {"publication_date": "2023-05-15"}
        >>> get_document_year(doc)
        2023
    """
    # Try 'year' field first
    if 'year' in doc and isinstance(doc['year'], int):
        return doc['year']

    # Try extracting from publication_date
    if 'publication_date' in doc and isinstance(doc['publication_date'], str):
        try:
            # Try to extract year from date string (YYYY-MM-DD or YYYY)
            date_str = doc['publication_date']
            if '-' in date_str:
                year_str = date_str.split('-')[0]
            else:
                year_str = date_str[:4]

            year = int(year_str)
            if 1900 <= year <= 2100:  # Sanity check
                return year
        except (ValueError, IndexError):
            pass

    return None


def format_authors(doc: Dict[str, Any], max_authors: int = 3) -> str:
    """Format author list for display.

    Args:
        doc: Document dictionary
        max_authors: Maximum number of authors to display before "et al."

    Returns:
        Formatted author string

    Examples:
        >>> doc = {"authors": ["Smith J", "Jones M"]}
        >>> format_authors(doc)
        'Smith J, Jones M'

        >>> doc = {"authors": ["A", "B", "C", "D", "E"]}
        >>> format_authors(doc, max_authors=3)
        'A, B, C, et al.'
    """
    if 'authors' not in doc or not doc['authors']:
        return "Unknown"

    authors = doc['authors']
    if not isinstance(authors, list):
        return "Unknown"

    if len(authors) <= max_authors:
        return ", ".join(authors)
    else:
        return ", ".join(authors[:max_authors]) + ", et al."


def truncate_abstract(abstract: str, max_length: int = 500) -> str:
    """Truncate abstract to maximum length.

    Args:
        abstract: Abstract text
        max_length: Maximum length (default: 500 characters)

    Returns:
        Truncated abstract with ellipsis if needed

    Examples:
        >>> truncate_abstract("Short abstract")
        'Short abstract'

        >>> long_text = "A" * 600
        >>> result = truncate_abstract(long_text, 500)
        >>> len(result)
        503
        >>> result.endswith('...')
        True
    """
    if len(abstract) <= max_length:
        return abstract

    return abstract[:max_length] + "..."


def create_document_summary(doc: Dict[str, Any], include_abstract: bool = False) -> str:
    """Create a human-readable summary of a document.

    Args:
        doc: Document dictionary
        include_abstract: Include abstract in summary (default: False)

    Returns:
        Formatted document summary

    Examples:
        >>> doc = {
        ...     "id": "123",
        ...     "title": "Test Study",
        ...     "authors": ["Smith J"],
        ...     "year": 2023,
        ...     "journal": "Nature"
        ... }
        >>> summary = create_document_summary(doc)
        >>> "Test Study" in summary
        True
    """
    parts = []

    # Title
    title = doc.get('title', 'Untitled Document')
    parts.append(f"**{title}**")

    # Authors and year
    author_str = format_authors(doc)
    year = get_document_year(doc)
    year_str = f"({year})" if year else ""

    parts.append(f"{author_str} {year_str}".strip())

    # Journal
    if 'journal' in doc and doc['journal']:
        parts.append(f"*{doc['journal']}*")

    # Abstract (if requested)
    if include_abstract and 'abstract' in doc:
        abstract = truncate_abstract(doc['abstract'], 300)
        parts.append(f"\n{abstract}")

    return "\n".join(parts)
