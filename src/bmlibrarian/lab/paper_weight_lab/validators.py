"""
Paper Weight Laboratory - Input Validators

Reusable validation functions for user input in the Paper Weight Lab.
All validators are pure functions that return (is_valid, error_message) tuples.
"""

import re
from pathlib import Path
from typing import Tuple, Optional

from .constants import (
    PMID_MIN_VALUE,
    PMID_MAX_VALUE,
    YEAR_MIN_VALUE,
    YEAR_MAX_VALUE,
    DOI_PATTERN,
    PDF_MAX_FILE_SIZE_BYTES,
    PDF_MAX_FILE_SIZE_MB,
)


def validate_pmid(value: str) -> Tuple[bool, Optional[str]]:
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


def validate_doi(value: str) -> Tuple[bool, Optional[str]]:
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

    if not re.match(DOI_PATTERN, value):
        return False, "DOI must start with '10.' followed by a registrant code and suffix (e.g., 10.1234/example)"

    return True, None


def validate_year(value: str) -> Tuple[bool, Optional[str]]:
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


def validate_pdf_file_size(file_path: Path) -> Tuple[bool, Optional[str]]:
    """
    Validate PDF file size is within acceptable limits.

    Files larger than PDF_MAX_FILE_SIZE_BYTES will generate a warning.
    This returns False for files that are too large, but processing
    can still continue if the user chooses.

    Args:
        file_path: Path to the PDF file

    Returns:
        Tuple of (is_within_limit, warning_message).
        warning_message is None if within limits.
    """
    if not file_path.exists():
        return False, "File does not exist"

    file_size = file_path.stat().st_size

    if file_size > PDF_MAX_FILE_SIZE_BYTES:
        size_mb = file_size / (1024 * 1024)
        return False, (
            f"PDF file is {size_mb:.1f}MB, which exceeds the recommended "
            f"limit of {PDF_MAX_FILE_SIZE_MB}MB. Processing may be slow "
            "or consume significant memory."
        )

    return True, None


def validate_title(value: str) -> Tuple[bool, Optional[str]]:
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


__all__ = [
    'validate_pmid',
    'validate_doi',
    'validate_year',
    'validate_pdf_file_size',
    'validate_title',
]
