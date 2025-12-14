"""
Citation loading utilities for BMLibrarian Lite.

Provides helper functions for loading documents from citations:
- build_doc_metadata(): Build document metadata dictionary from citation
- build_abstract_text(): Format abstract as readable document

These pure functions help separate data transformation from UI logic.

Usage:
    from bmlibrarian.lite.gui.citation_loader import (
        build_doc_metadata,
        build_abstract_text,
    )

    # Build metadata for PDF discovery
    metadata = build_doc_metadata(citation)

    # Format abstract for display
    text = build_abstract_text(citation)
"""

from typing import Any, Dict, Optional

from ..pdf_utils import format_abstract_as_document


def build_doc_metadata(citation: 'Citation') -> Dict[str, Any]:
    """
    Build document metadata dictionary from a citation.

    Extracts relevant fields for PDF discovery and document tracking.

    Args:
        citation: Citation object containing document information

    Returns:
        Dictionary with document metadata fields

    Example:
        metadata = build_doc_metadata(citation)
        # {'id': 123, 'doi': '10.1038/...', 'pmid': '12345', ...}
    """
    doc = citation.document
    return {
        'id': doc.id,
        'doi': doc.doi,
        'pmid': doc.pmid,
        'pmcid': doc.pmc_id,
        'pmc_id': doc.pmc_id,
        'title': doc.title,
        'year': doc.year,
    }


def build_abstract_text(citation: 'Citation') -> str:
    """
    Build formatted abstract text from a citation.

    Creates a readable markdown document from the citation's document
    metadata and abstract, including the relevant passage.

    Args:
        citation: Citation object containing document and passage

    Returns:
        Formatted markdown text for display

    Example:
        text = build_abstract_text(citation)
        # Returns markdown with title, authors, abstract, and passage
    """
    doc = citation.document
    return format_abstract_as_document(
        title=doc.title,
        authors=doc.formatted_authors,
        journal=doc.journal,
        year=doc.year,
        doi=doc.doi,
        pmid=doc.pmid,
        abstract=doc.abstract,
        passage=citation.passage,
        context=citation.context,
    )


def has_pdf_identifiers(citation: 'Citation') -> bool:
    """
    Check if a citation has identifiers that can be used for PDF discovery.

    Args:
        citation: Citation object to check

    Returns:
        True if the citation has DOI, PMID, or PMC ID
    """
    doc = citation.document
    return bool(doc.doi or doc.pmid or doc.pmc_id)


def get_document_title(citation: 'Citation', default: str = "Untitled Document") -> str:
    """
    Get the document title from a citation.

    Args:
        citation: Citation object
        default: Default title if none is available

    Returns:
        Document title or default
    """
    return citation.document.title or default
