"""
Tests for PDFIngestor.ingest_pdf's handling of failed and empty conversions.

The database and filesystem are mocked: the ingestor is built with
``object.__new__`` so its constructor never touches the database manager.
"""

from pathlib import Path
from typing import Any, Dict, Optional
from unittest.mock import MagicMock

import pytest

from bmlibrarian.importers.pdf_converter import ConversionResult
from bmlibrarian.importers.pdf_ingestor import PDFIngestor

DOCUMENT_ID = 42
EXISTING_DOCUMENT: Dict[str, Any] = {"id": DOCUMENT_ID, "pdf_filename": "2020/old.pdf"}


def _conversion(
    success: bool, text: str = "", error_message: Optional[str] = None
) -> ConversionResult:
    """Build a ConversionResult for a 3-page PDF."""
    return ConversionResult(
        success=success,
        text=text,
        format="plaintext",
        page_count=3,
        converted_pages=3 if text else 0,
        char_count=len(text),
        error_message=error_message,
    )


def _ingestor(conversion: ConversionResult) -> PDFIngestor:
    """Return a PDFIngestor whose converter, DB and storage are mocks."""
    ingestor = object.__new__(PDFIngestor)
    ingestor.pdf_base_dir = Path("/nonexistent")
    ingestor._converter = MagicMock()
    ingestor._converter.convert.return_value = conversion
    ingestor.get_document = MagicMock(return_value=dict(EXISTING_DOCUMENT))
    ingestor._store_pdf = MagicMock(return_value=None)
    ingestor._update_document_full_text = MagicMock(return_value=True)
    return ingestor


@pytest.fixture
def pdf_path(tmp_path: Path) -> Path:
    """A file that exists (contents are irrelevant: the converter is mocked)."""
    path = tmp_path / "paper.pdf"
    path.write_bytes(b"%PDF-1.4")
    return path


def test_password_protected_pdf_fails_without_touching_full_text(pdf_path: Path) -> None:
    """bmlib reports a password-protected PDF as a failed conversion."""
    ingestor = _ingestor(_conversion(False, error_message="PDF is password-protected"))

    result = ingestor.ingest_pdf(DOCUMENT_ID, pdf_path, store_pdf=False)

    assert result.success is False
    assert result.error_message == "PDF is password-protected"
    assert result.full_text_stored is False
    ingestor._update_document_full_text.assert_not_called()


@pytest.mark.parametrize("text", ["", "  \n\n  "])
def test_successful_conversion_without_text_keeps_existing_full_text(
    pdf_path: Path, text: str
) -> None:
    """An image-only PDF must not overwrite full_text with an empty string."""
    ingestor = _ingestor(_conversion(True, text=text))

    result = ingestor.ingest_pdf(DOCUMENT_ID, pdf_path, store_pdf=False)

    assert result.full_text_stored is False
    assert any("No extractable text" in w for w in result.warnings)
    ingestor._update_document_full_text.assert_not_called()


def test_successful_conversion_with_text_is_stored(pdf_path: Path) -> None:
    """The normal path still writes the text with the existing pdf_filename."""
    ingestor = _ingestor(_conversion(True, text="Full text of the paper."))

    result = ingestor.ingest_pdf(DOCUMENT_ID, pdf_path, store_pdf=False)

    assert result.success is True
    assert result.full_text_stored is True
    ingestor._update_document_full_text.assert_called_once_with(
        DOCUMENT_ID, "Full text of the paper.", "2020/old.pdf"
    )
