"""
PDF utility functions for BMLibrarian Lite.

Pure functions for PDF file path management and document formatting:
- get_pdf_base_dir(): Get the base directory for PDF storage
- generate_pdf_path(): Generate standard PDF path for a document
- find_existing_pdf(): Check if a PDF already exists locally
- format_abstract_as_document(): Format abstract and citation as readable document
- extract_pdf_text(): Extract text from a PDF file

These functions are stateless and can be reused across different modules.

Usage:
    from bmlibrarian.lite.pdf_utils import (
        get_pdf_base_dir,
        generate_pdf_path,
        find_existing_pdf,
        format_abstract_as_document,
    )

    # Get PDF storage directory
    base_dir = get_pdf_base_dir()

    # Generate path for a document
    doc = {'doi': '10.1038/nature12373', 'year': 2023}
    pdf_path = generate_pdf_path(doc, base_dir)

    # Check for existing PDF
    existing = find_existing_pdf(doc, base_dir)
"""

import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Environment variable name for PDF base directory
PDF_BASE_DIR_ENV = 'PDF_BASE_DIR'

# Default PDF base directory relative to home
DEFAULT_PDF_BASE_DIR = 'knowledgebase/pdf'


def get_pdf_base_dir(env_var: str = PDF_BASE_DIR_ENV) -> Path:
    """
    Get the base directory for PDF storage.

    Uses PDF_BASE_DIR environment variable or defaults to ~/knowledgebase/pdf.

    Args:
        env_var: Environment variable name to check (default: PDF_BASE_DIR)

    Returns:
        Path to PDF base directory (expanded user path)

    Example:
        base_dir = get_pdf_base_dir()
        # Returns Path("/home/user/knowledgebase/pdf") or custom path from env
    """
    pdf_base = os.environ.get(env_var)
    if pdf_base:
        return Path(pdf_base).expanduser()
    return Path.home() / DEFAULT_PDF_BASE_DIR


def generate_pdf_path(
    doc_dict: Dict[str, Any],
    base_dir: Optional[Path] = None,
) -> Path:
    """
    Generate the standard PDF path for a document.

    Uses year-based folder structure with DOI-based or ID-based filename.
    Structure: {base_dir}/{year}/{filename}.pdf

    Args:
        doc_dict: Document dictionary with doi, year, id, publication_date, etc.
        base_dir: Base directory for PDF storage (default: from get_pdf_base_dir())

    Returns:
        Path where PDF should be stored

    Example:
        doc = {'doi': '10.1038/nature12373', 'year': 2023}
        path = generate_pdf_path(doc)
        # Returns Path("~/knowledgebase/pdf/2023/10.1038_nature12373.pdf")
    """
    if base_dir is None:
        base_dir = get_pdf_base_dir()

    # Extract year for subdirectory
    year = _extract_year(doc_dict)
    year_dir = str(year) if year else 'unknown'
    output_dir = base_dir / year_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    # Generate filename from DOI or document ID
    doi = doc_dict.get('doi')
    if doi:
        # DOI-based filename (replace slashes)
        safe_doi = doi.replace('/', '_').replace('\\', '_')
        filename = f"{safe_doi}.pdf"
    else:
        # Document ID-based filename
        doc_id = doc_dict.get('id', 'unknown')
        filename = f"doc_{doc_id}.pdf"

    return output_dir / filename


def _extract_year(doc_dict: Dict[str, Any]) -> Optional[int]:
    """
    Extract year from document dictionary.

    Checks 'year' field first, then tries to parse from 'publication_date'.

    Args:
        doc_dict: Document dictionary

    Returns:
        Year as integer or None if not found/parseable
    """
    year = doc_dict.get('year')
    if year:
        return int(year) if isinstance(year, (int, str)) else None

    pub_date = doc_dict.get('publication_date')
    if pub_date and isinstance(pub_date, str) and len(pub_date) >= 4:
        try:
            return int(pub_date[:4])
        except ValueError:
            pass

    return None


def find_existing_pdf(
    doc_dict: Dict[str, Any],
    base_dir: Optional[Path] = None,
) -> Optional[Path]:
    """
    Check if a PDF already exists locally for this document.

    Searches both the expected path and year-based subdirectories
    to find existing PDFs that may have been stored previously.

    Args:
        doc_dict: Document dictionary with doi, year, id, etc.
        base_dir: Base directory for PDF storage (default: from get_pdf_base_dir())

    Returns:
        Path to existing PDF if found, None otherwise

    Example:
        doc = {'doi': '10.1038/nature12373', 'year': 2023}
        existing = find_existing_pdf(doc)
        if existing:
            print(f"Found PDF at: {existing}")
    """
    if base_dir is None:
        base_dir = get_pdf_base_dir()

    # First check expected path
    expected_path = generate_pdf_path(doc_dict, base_dir)
    if expected_path.exists():
        logger.info(f"Found existing PDF at: {expected_path}")
        return expected_path

    # Also check by DOI in all year directories
    doi = doc_dict.get('doi')
    if doi:
        safe_doi = doi.replace('/', '_').replace('\\', '_')
        filename = f"{safe_doi}.pdf"

        # Search all year directories
        if base_dir.exists():
            for year_dir in base_dir.iterdir():
                if year_dir.is_dir():
                    pdf_path = year_dir / filename
                    if pdf_path.exists():
                        logger.info(f"Found existing PDF at: {pdf_path}")
                        return pdf_path

    return None


def format_abstract_as_document(
    title: Optional[str],
    authors: Optional[str],
    journal: Optional[str],
    year: Optional[int],
    doi: Optional[str],
    pmid: Optional[str],
    abstract: Optional[str],
    passage: Optional[str] = None,
    context: Optional[str] = None,
) -> str:
    """
    Format abstract and metadata as a readable markdown document.

    Creates a structured document from the abstract and metadata
    when full text is not available.

    Args:
        title: Document title
        authors: Formatted author string
        journal: Journal name
        year: Publication year
        doi: Digital Object Identifier
        pmid: PubMed ID
        abstract: Document abstract
        passage: Optional relevant passage from citation
        context: Optional additional context

    Returns:
        Formatted markdown document text

    Example:
        text = format_abstract_as_document(
            title="A Study on X",
            authors="Smith J, Johnson A",
            journal="Nature",
            year=2023,
            doi="10.1038/nature12373",
            pmid="12345678",
            abstract="This study investigates...",
            passage="The key finding was...",
        )
    """
    parts = []

    # Title
    parts.append(f"# {title or 'Untitled Document'}")
    parts.append("")

    # Authors and publication info
    if authors:
        parts.append(f"**Authors:** {authors}")
    if journal:
        parts.append(f"**Journal:** {journal}")
    if year:
        parts.append(f"**Year:** {year}")
    if doi:
        parts.append(f"**DOI:** {doi}")
    if pmid:
        parts.append(f"**PMID:** {pmid}")

    parts.append("")

    # Abstract
    parts.append("## Abstract")
    parts.append("")
    parts.append(abstract or "No abstract available.")
    parts.append("")

    # Relevant passage from citation
    if passage:
        parts.append("## Relevant Passage")
        parts.append("")
        parts.append(f"> {passage}")
        parts.append("")

    # Context if available
    if context:
        parts.append("## Context")
        parts.append("")
        parts.append(context)
        parts.append("")

    # Note about limited content
    parts.append("---")
    parts.append("")
    parts.append(
        "*Note: Full text was not available. This document contains only "
        "the abstract and citation information.*"
    )

    return "\n".join(parts)


def extract_pdf_text(pdf_path: Path) -> str:
    """
    Extract text from a PDF file.

    Uses PyMuPDF (fitz) to extract text from all pages.

    Args:
        pdf_path: Path to PDF file

    Returns:
        Extracted text from all pages, joined by double newlines

    Raises:
        FileNotFoundError: If PDF file doesn't exist
        Exception: If PDF cannot be opened or read

    Example:
        text = extract_pdf_text(Path("/path/to/paper.pdf"))
        print(f"Extracted {len(text)} characters")
    """
    import fitz

    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    pdf_doc = fitz.open(str(pdf_path))
    text_parts = []

    try:
        for page in pdf_doc:
            text_parts.append(page.get_text())
    finally:
        pdf_doc.close()

    return "\n\n".join(text_parts)


def get_progress_stage_message(stage: str, status: str) -> str:
    """
    Get a user-friendly message for PDF progress stages.

    Maps internal stage/status codes to human-readable messages.

    Args:
        stage: Current stage (discovery, download, browser_download, verification)
        status: Current status (starting, found, success, failed, etc.)

    Returns:
        User-friendly message string

    Example:
        msg = get_progress_stage_message('discovery', 'starting')
        # Returns "Searching for PDF sources..."
    """
    stage_messages = {
        'discovery': {
            'starting': "Searching for PDF sources...",
            'resolving': "Checking PDF sources...",
            'found': "Found PDF source!",
            'found_oa': "Found open access PDF!",
            'not_found': "No PDF sources found",
            'error': "Error searching for PDF",
        },
        'download': {
            'starting': "Downloading PDF...",
            'success': "Download complete!",
            'failed': "Download failed",
        },
        'browser_download': {
            'starting': "Downloading PDF (browser mode)...",
            'success': "Download complete!",
            'failed': "Browser download failed",
        },
        'verification': {
            'starting': "Verifying PDF content...",
            'success': "Verification complete",
            'mismatch': "Content verification failed",
            'skipped': "Verification skipped",
            'error': "Verification error",
        },
    }

    return stage_messages.get(stage, {}).get(
        status, f"{stage.replace('_', ' ').title()}: {status}"
    )
