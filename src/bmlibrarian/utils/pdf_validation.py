"""PDF content validation utilities.

Provides small, reusable pure functions for verifying that downloaded
bytes actually contain a PDF document, rather than an HTML paywall/login
page (or other unexpected content) that a remote server returned with a
misleading HTTP 200 status and/or "application/pdf" filename.

Per the PDF specification, a conforming PDF file must begin with the
literal ASCII header ``%PDF-`` followed by the version number. Servers
that redirect to login/paywall pages typically return an HTML document
instead, which does NOT start with this header. Checking for the magic
bytes is a cheap, reliable way to catch this class of silent corruption
before a bad file is persisted to the PDF corpus or recorded as a
successful download.

This module intentionally has no dependency on ``requests`` or any other
network library so that the validation logic can be reused (and unit
tested) independently of how the bytes were obtained.
"""

import logging
from pathlib import Path
from typing import Union

logger = logging.getLogger(__name__)

# PDF files are required to start with this literal byte sequence.
PDF_MAGIC_BYTES = b"%PDF-"

# Number of leading bytes read from disk when validating a file on disk.
# The magic bytes appear within the first few bytes of a conforming PDF;
# reading a small header is sufficient and avoids loading large files.
PDF_HEADER_READ_SIZE = 1024


def is_pdf_content(first_bytes: bytes) -> bool:
    """Check whether the given leading bytes indicate genuine PDF content.

    Args:
        first_bytes: The first bytes read from the downloaded/streamed
            content. Passing the first ``PDF_HEADER_READ_SIZE`` bytes (or
            more) is sufficient; passing fewer bytes than the magic
            sequence will simply fail the check.

    Returns:
        True if the bytes contain the ``%PDF-`` magic header, False
        otherwise (including when ``first_bytes`` is empty or not a
        bytes-like object).
    """
    if not isinstance(first_bytes, (bytes, bytearray)):
        logger.warning(
            "is_pdf_content() received non-bytes input of type %s; treating as invalid",
            type(first_bytes).__name__,
        )
        return False

    if not first_bytes:
        return False

    # Some servers/proxies prepend a small amount of whitespace or a BOM
    # before the actual PDF header, so search within a bounded prefix
    # rather than requiring an exact startswith() match.
    return PDF_MAGIC_BYTES in bytes(first_bytes[:PDF_HEADER_READ_SIZE])


def is_pdf_file(file_path: Union[str, Path]) -> bool:
    """Check whether a file on disk contains valid PDF content.

    Reads only the first ``PDF_HEADER_READ_SIZE`` bytes of the file, so
    this is safe to call on large files.

    Args:
        file_path: Path to the file to validate.

    Returns:
        True if the file exists and its content starts with the PDF
        magic bytes, False otherwise (including on any I/O error, which
        is logged and treated as "not a valid PDF" rather than raised).
    """
    try:
        with open(file_path, "rb") as f:
            header = f.read(PDF_HEADER_READ_SIZE)
        return is_pdf_content(header)
    except OSError as e:
        logger.warning("Failed to read file for PDF validation (%s): %s", file_path, e)
        return False
