"""
Input Validators for BMLibrarian Qt Widgets.

Reusable validation functions for user input across Qt GUI components.
All validators are pure functions that return (is_valid, error_message) tuples.

This module provides centralized validation that can be used by multiple widgets
including PDFUploadWidget, Paper Weight Lab, Paper Checker Lab, etc.
"""

import re
from pathlib import Path
from typing import Optional

# =============================================================================
# Validation Constants
# =============================================================================

# PMID validation (PubMed IDs are positive integers, typically 1-8 digits)
PMID_MIN_VALUE = 1
PMID_MAX_VALUE = 99999999  # 8 digits max

# Publication year validation
YEAR_MIN_VALUE = 1800  # Oldest reasonable publication year
YEAR_MAX_VALUE = 2100  # Future upper bound for pre-prints

# DOI pattern (basic validation: 10.xxxx/...)
DOI_VALIDATION_PATTERN = r'^10\.\d{4,}/\S+$'

# PDF file size limit (in megabytes)
PDF_MAX_FILE_SIZE_MB = 50  # Warn for files larger than 50MB
PDF_MAX_FILE_SIZE_BYTES = PDF_MAX_FILE_SIZE_MB * 1024 * 1024

# Worker thread termination timeout
WORKER_TERMINATE_TIMEOUT_MS = 3000  # Maximum wait time for worker termination


def validate_pmid(value: str) -> tuple[bool, Optional[str]]:
    """
    Validate a PubMed ID (PMID).

    PMIDs must be positive integers between PMID_MIN_VALUE and PMID_MAX_VALUE.
    Empty strings are valid (optional field).

    Args:
        value: The PMID string to validate

    Returns:
        Tuple of (is_valid, error_message). error_message is None if valid.
    """
    value = value.strip()
    if not value:
        return True, None  # Empty is valid (optional field)

    if not value.isdigit():
        return False, "PMID must be a numeric value (digits only)"

    try:
        pmid_int = int(value)
        if pmid_int < PMID_MIN_VALUE:
            return False, f"PMID must be at least {PMID_MIN_VALUE}"
        if pmid_int > PMID_MAX_VALUE:
            return False, f"PMID cannot exceed {PMID_MAX_VALUE}"
        return True, None
    except ValueError:
        return False, "PMID must be a valid integer"


def validate_doi(value: str) -> tuple[bool, Optional[str]]:
    """
    Validate a Digital Object Identifier (DOI).

    DOIs must match the pattern: 10.xxxx/...
    Empty strings are valid (optional field).

    Args:
        value: The DOI string to validate

    Returns:
        Tuple of (is_valid, error_message). error_message is None if valid.
    """
    value = value.strip()
    if not value:
        return True, None  # Empty is valid (optional field)

    if not re.match(DOI_VALIDATION_PATTERN, value):
        return False, (
            "DOI must start with '10.' followed by a registrant code "
            "and suffix (e.g., 10.1234/example)"
        )

    return True, None


def validate_year(value: str) -> tuple[bool, Optional[str]]:
    """
    Validate a publication year.

    Years must be integers between YEAR_MIN_VALUE and YEAR_MAX_VALUE.
    Empty strings are valid (optional field).

    Args:
        value: The year string to validate

    Returns:
        Tuple of (is_valid, error_message). error_message is None if valid.
    """
    value = value.strip()
    if not value:
        return True, None  # Empty is valid (optional field)

    if not value.isdigit():
        return False, "Year must be a numeric value (digits only)"

    try:
        year_int = int(value)
        if year_int < YEAR_MIN_VALUE:
            return False, f"Year cannot be earlier than {YEAR_MIN_VALUE}"
        if year_int > YEAR_MAX_VALUE:
            return False, f"Year cannot be later than {YEAR_MAX_VALUE}"
        return True, None
    except ValueError:
        return False, "Year must be a valid integer"


def validate_title(value: str) -> tuple[bool, Optional[str]]:
    """
    Validate a document title.

    Titles cannot be empty or whitespace-only.

    Args:
        value: The title string to validate

    Returns:
        Tuple of (is_valid, error_message). error_message is None if valid.
    """
    value = value.strip()
    if not value:
        return False, "Title is required and cannot be empty"

    return True, None


def validate_pdf_file(file_path: Path) -> tuple[bool, Optional[str]]:
    """
    Validate a PDF file exists and check its size.

    Files larger than PDF_MAX_FILE_SIZE_BYTES will generate a warning.
    This returns False for files that are too large, but processing
    can still continue if the user chooses.

    Args:
        file_path: Path to the PDF file

    Returns:
        Tuple of (is_valid_or_warning_only, message).
        - (True, None) if valid and within size limits
        - (False, error_msg) if file doesn't exist or is not a PDF
        - (True, warning_msg) if file is very large but can proceed
    """
    if not file_path.exists():
        return False, "File does not exist"

    if not file_path.suffix.lower() == '.pdf':
        return False, "File must have .pdf extension"

    file_size = file_path.stat().st_size

    if file_size == 0:
        return False, "PDF file is empty (0 bytes)"

    if file_size > PDF_MAX_FILE_SIZE_BYTES:
        size_mb = file_size / (1024 * 1024)
        return True, (
            f"PDF file is {size_mb:.1f}MB, which exceeds the recommended "
            f"limit of {PDF_MAX_FILE_SIZE_MB}MB. Processing may be slow "
            "or consume significant memory."
        )

    return True, None


def classify_extraction_error(error: Exception) -> tuple[str, str]:
    """
    Classify an extraction error and provide user-friendly guidance.

    Args:
        error: The exception that occurred

    Returns:
        Tuple of (error_category, user_message)
    """
    error_str = str(error).lower()

    if 'connect' in error_str or 'connection' in error_str:
        return (
            "connection",
            "Cannot connect to the AI service (Ollama). "
            "Please ensure Ollama is running and try again."
        )

    if 'timeout' in error_str:
        return (
            "timeout",
            "The AI service took too long to respond. "
            "The PDF may be too complex or the service is overloaded."
        )

    if 'memory' in error_str or 'oom' in error_str:
        return (
            "memory",
            "Ran out of memory processing this PDF. "
            "Try with a smaller file or restart the application."
        )

    if 'pdf' in error_str or 'corrupt' in error_str or 'extract' in error_str:
        return (
            "extraction",
            "Could not extract text from the PDF. "
            "The file may be scanned, image-based, or corrupted."
        )

    if 'database' in error_str or 'sql' in error_str or 'postgres' in error_str:
        return (
            "database",
            "Database error occurred. "
            "Please check the database connection and try again."
        )

    # Generic fallback
    return (
        "unknown",
        f"An unexpected error occurred: {error}\n\n"
        "You can still manually enter metadata to create a document."
    )


__all__ = [
    # Constants
    'PMID_MIN_VALUE',
    'PMID_MAX_VALUE',
    'YEAR_MIN_VALUE',
    'YEAR_MAX_VALUE',
    'DOI_VALIDATION_PATTERN',
    'PDF_MAX_FILE_SIZE_MB',
    'PDF_MAX_FILE_SIZE_BYTES',
    'WORKER_TERMINATE_TIMEOUT_MS',
    # Validators
    'validate_pmid',
    'validate_doi',
    'validate_year',
    'validate_title',
    'validate_pdf_file',
    'classify_extraction_error',
]
