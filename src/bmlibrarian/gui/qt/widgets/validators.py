"""
Input Validators for BMLibrarian Qt Widgets.

Reusable validation functions for user input across Qt GUI components.
All validators are pure functions that return (is_valid, error_message) tuples.

This module provides centralized validation that can be used by multiple widgets
including PDFUploadWidget, Paper Weight Lab, Paper Checker Lab, etc.
"""

import logging
import re
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

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
WORKER_TERMINATE_TIMEOUT_MS = 3000  # Maximum wait time for graceful worker termination
WORKER_FORCE_TERMINATE_TIMEOUT_MS = 5000  # Timeout after forced terminate() call

# LLM Input Sanitization Constants
LLM_MAX_TEXT_LENGTH = 100000  # Maximum characters to send to LLM (100K)
LLM_MAX_LINE_LENGTH = 10000   # Maximum length of a single line
LLM_TRUNCATION_SUFFIX = "\n\n[Text truncated due to length]"

# Form Validation Constants
VALIDATION_DEBOUNCE_MS = 300  # Debounce delay for form validation (milliseconds)


class DebouncedValidator:
    """
    A debounced validator that delays validation execution until input stops.

    This improves UX by avoiding validation on every keystroke, which can be
    distracting and computationally wasteful especially with long text.

    Usage:
        # In a QWidget subclass
        self._debounced_validator = DebouncedValidator(
            callback=self._validate_form,
            delay_ms=VALIDATION_DEBOUNCE_MS
        )
        self.title_edit.textChanged.connect(self._debounced_validator.trigger)

    The callback will be executed only after the user stops typing for
    `delay_ms` milliseconds.
    """

    def __init__(
        self,
        callback: Callable[[], None],
        delay_ms: int = VALIDATION_DEBOUNCE_MS
    ):
        """
        Initialize the debounced validator.

        Args:
            callback: The validation function to call after debounce delay.
                     Should take no arguments.
            delay_ms: Debounce delay in milliseconds (default: VALIDATION_DEBOUNCE_MS)
        """
        from PySide6.QtCore import QTimer

        self._callback = callback
        self._delay_ms = delay_ms
        self._timer = QTimer()
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._execute)

    def trigger(self, *args: Any) -> None:
        """
        Trigger a debounced validation.

        Called on each text change. Restarts the timer so the callback
        only fires after typing stops.

        Args:
            *args: Ignored (allows direct connection to Qt signals)
        """
        self._timer.stop()
        self._timer.start(self._delay_ms)

    def _execute(self) -> None:
        """Execute the validation callback."""
        try:
            self._callback()
        except Exception as e:
            logger.warning(f"Debounced validation failed: {e}")

    def cancel(self) -> None:
        """Cancel any pending validation."""
        self._timer.stop()

    def force_validate(self) -> None:
        """
        Force immediate validation, bypassing debounce.

        Useful for final validation before form submission.
        """
        self._timer.stop()
        self._execute()


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


class ValidationStatus:
    """
    Validation result status codes.

    Used by validate_pdf_file to distinguish between errors and warnings.
    """
    VALID = "valid"           # File is valid, no issues
    WARNING = "warning"       # File is valid but has warnings (e.g., large size)
    ERROR = "error"           # File is invalid (doesn't exist, wrong type, etc.)


def validate_pdf_file(file_path: Path) -> tuple[bool, Optional[str], str]:
    """
    Validate a PDF file exists and check its size.

    Files larger than PDF_MAX_FILE_SIZE_BYTES will generate a warning.
    Processing can still continue with warnings if the user chooses.

    Args:
        file_path: Path to the PDF file

    Returns:
        Tuple of (is_valid, message, status).
        - (True, None, ValidationStatus.VALID) if valid and within size limits
        - (False, error_msg, ValidationStatus.ERROR) if file doesn't exist or is not a PDF
        - (True, warning_msg, ValidationStatus.WARNING) if file is very large but can proceed

    Example:
        >>> is_valid, message, status = validate_pdf_file(Path("paper.pdf"))
        >>> if status == ValidationStatus.ERROR:
        ...     show_error(message)
        >>> elif status == ValidationStatus.WARNING:
        ...     if user_confirms(message):
        ...         proceed()
    """
    if not file_path.exists():
        return False, "File does not exist", ValidationStatus.ERROR

    if not file_path.suffix.lower() == '.pdf':
        return False, "File must have .pdf extension", ValidationStatus.ERROR

    file_size = file_path.stat().st_size

    if file_size == 0:
        return False, "PDF file is empty (0 bytes)", ValidationStatus.ERROR

    if file_size > PDF_MAX_FILE_SIZE_BYTES:
        size_mb = file_size / (1024 * 1024)
        return True, (
            f"PDF file is {size_mb:.1f}MB, which exceeds the recommended "
            f"limit of {PDF_MAX_FILE_SIZE_MB}MB. Processing may be slow "
            "or consume significant memory."
        ), ValidationStatus.WARNING

    return True, None, ValidationStatus.VALID


def classify_extraction_error(error: Exception) -> tuple[str, str]:
    """
    Classify an extraction error and provide user-friendly guidance.

    Covers common PDF processing errors including:
    - Network/connection issues (Ollama service)
    - Timeout errors (large/complex PDFs)
    - Memory issues (OOM conditions)
    - PDF format errors (encrypted, corrupted, scanned)
    - Permission/access errors
    - Database errors

    Args:
        error: The exception that occurred

    Returns:
        Tuple of (error_category, user_message)
    """
    error_str = str(error).lower()

    # Connection errors (Ollama/network)
    if 'connect' in error_str or 'connection' in error_str:
        return (
            "connection",
            "Cannot connect to the AI service (Ollama). "
            "Please ensure Ollama is running and try again."
        )

    # Timeout errors
    if 'timeout' in error_str:
        return (
            "timeout",
            "The AI service took too long to respond. "
            "The PDF may be too complex or the service is overloaded."
        )

    # Memory errors
    if 'memory' in error_str or 'oom' in error_str:
        return (
            "memory",
            "Ran out of memory processing this PDF. "
            "Try with a smaller file or restart the application."
        )

    # Encrypted/password-protected PDFs
    if 'encrypt' in error_str or 'password' in error_str or 'protected' in error_str:
        return (
            "encrypted",
            "This PDF is encrypted or password-protected. "
            "Please provide an unprotected version of the file."
        )

    # Permission/access errors
    if ('permission' in error_str or 'access denied' in error_str or
            'cannot read' in error_str or 'not readable' in error_str):
        return (
            "permission",
            "Cannot access this PDF file due to permission restrictions. "
            "Please check file permissions and try again."
        )

    # File format errors (not a valid PDF)
    if ('invalid pdf' in error_str or 'not a pdf' in error_str or
            'magic number' in error_str or 'file format' in error_str or
            'bad header' in error_str or 'malformed' in error_str):
        return (
            "format",
            "This file does not appear to be a valid PDF document. "
            "Please verify the file is not corrupted or renamed."
        )

    # General PDF extraction errors (scanned, image-based, corrupted)
    if 'pdf' in error_str or 'corrupt' in error_str or 'extract' in error_str:
        return (
            "extraction",
            "Could not extract text from the PDF. "
            "The file may be scanned, image-based, or corrupted."
        )

    # Database errors
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


def sanitize_llm_input(
    text: str,
    max_length: int = LLM_MAX_TEXT_LENGTH,
    max_line_length: int = LLM_MAX_LINE_LENGTH,
) -> str:
    """
    Sanitize text before sending to an LLM for metadata extraction.

    Performs the following sanitization steps:
    1. Removes control characters (except newline, tab)
    2. Normalizes whitespace (multiple spaces to single)
    3. Truncates extremely long lines (may indicate binary data)
    4. Limits total text length to prevent memory issues
    5. Removes potential prompt injection sequences

    Note on truncation (Golden Rule #14):
        This function intentionally truncates text exceeding max_length.
        This is acceptable because:
        - LLM context windows have finite limits
        - Metadata (DOI, PMID, title, authors) is typically in the first pages
        - Full document text is preserved in the database; only LLM input is limited
        - Truncation is logged for transparency

    Args:
        text: Raw text extracted from PDF
        max_length: Maximum total character count (default: 100K)
        max_line_length: Maximum length per line (default: 10K)

    Returns:
        Sanitized text safe for LLM processing

    Example:
        >>> raw_text = pdf_extractor.extract_text()
        >>> clean_text = sanitize_llm_input(raw_text)
        >>> metadata = llm.extract_metadata(clean_text)
    """
    if not text:
        return ""

    # Step 1: Remove control characters (keep newline, tab, carriage return)
    # This removes NUL bytes, bell, backspace, etc.
    allowed_controls = {'\n', '\t', '\r'}
    sanitized = ''.join(
        char if (char.isprintable() or char in allowed_controls) else ' '
        for char in text
    )

    # Step 2: Normalize whitespace
    # Replace multiple spaces with single space
    import re
    sanitized = re.sub(r' {2,}', ' ', sanitized)
    # Normalize line endings
    sanitized = sanitized.replace('\r\n', '\n').replace('\r', '\n')
    # Remove excessive blank lines (more than 2 consecutive)
    sanitized = re.sub(r'\n{3,}', '\n\n', sanitized)

    # Step 3: Truncate extremely long lines
    # Very long lines without breaks often indicate encoded/binary data
    lines = sanitized.split('\n')
    processed_lines = []
    for line in lines:
        if len(line) > max_line_length:
            # Truncate and mark
            line = line[:max_line_length] + "..."
        processed_lines.append(line)
    sanitized = '\n'.join(processed_lines)

    # Step 4: Limit total length
    original_length = len(sanitized)
    if original_length > max_length:
        # Log truncation for transparency (Golden Rule #8, #14)
        logger.info(
            f"Truncating LLM input from {original_length} to ~{max_length} characters. "
            "Full text preserved in database; only LLM input is limited."
        )

        # Find a good break point (end of sentence or paragraph)
        truncate_at = max_length - len(LLM_TRUNCATION_SUFFIX)

        # Try to find a paragraph break
        last_para = sanitized.rfind('\n\n', 0, truncate_at)
        if last_para > truncate_at * 0.8:  # Only use if reasonably close
            truncate_at = last_para
        else:
            # Try to find end of sentence
            for end_char in ['. ', '.\n', '? ', '!\n']:
                last_sentence = sanitized.rfind(end_char, 0, truncate_at)
                if last_sentence > truncate_at * 0.9:
                    truncate_at = last_sentence + len(end_char)
                    break

        sanitized = sanitized[:truncate_at].rstrip() + LLM_TRUNCATION_SUFFIX

    # Step 5: Basic protection against common prompt injection patterns
    # Note: This is not foolproof but adds a layer of protection
    injection_patterns = [
        r'\bignore\s+(all\s+)?(previous|above|prior)\s+instructions?\b',
        r'\bsystem\s*:\s*',
        r'\b(human|user|assistant)\s*:\s*',
        r'<\|im_start\|>',
        r'<\|im_end\|>',
        r'<<\s*SYS\s*>>',
        r'\[\s*INST\s*\]',
    ]

    for pattern in injection_patterns:
        sanitized = re.sub(pattern, '[FILTERED]', sanitized, flags=re.IGNORECASE)

    return sanitized.strip()


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
    'WORKER_FORCE_TERMINATE_TIMEOUT_MS',
    'LLM_MAX_TEXT_LENGTH',
    'LLM_MAX_LINE_LENGTH',
    'VALIDATION_DEBOUNCE_MS',
    # Status codes
    'ValidationStatus',
    # Classes
    'DebouncedValidator',
    # Validators
    'validate_pmid',
    'validate_doi',
    'validate_year',
    'validate_title',
    'validate_pdf_file',
    'classify_extraction_error',
    # Sanitization
    'sanitize_llm_input',
]
