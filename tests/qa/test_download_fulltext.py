"""Tests for ``_download_fulltext_if_needed`` in document Q&A (#323).

The download must end in stored full text and a linked PDF, reuse a linked
PDF instead of downloading again, and never keep an unverified download.
"""

from pathlib import Path
from typing import Any, List, Optional, Tuple
from unittest.mock import MagicMock, patch

import pytest

from bmlibrarian.discovery import DownloadResult
from bmlibrarian.qa import document_qa

DOWNLOAD_TARGET = "bmlibrarian.discovery.download_pdf_for_document"
CONVERTER_TARGET = "bmlibrarian.importers.pdf_converter.get_converter"


def _db(row: Optional[Tuple[Any, ...]]) -> Tuple[MagicMock, List[Tuple[str, Any]]]:
    """A db_manager whose SELECT returns ``row``; records every execute."""
    executed: List[Tuple[str, Any]] = []
    cur = MagicMock()
    cur.execute.side_effect = lambda sql, params: executed.append((sql, params))
    cur.fetchone.return_value = row
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur
    db = MagicMock()
    db.get_connection.return_value.__enter__.return_value = conn
    return db, executed


def _converter(text: str) -> MagicMock:
    """A get_converter replacement whose convert() returns ``text``."""
    converter = MagicMock()
    converter.convert.return_value = MagicMock(success=True, text=text, error_message=None)
    return MagicMock(return_value=converter)


def _updates(executed: List[Tuple[str, Any]]) -> List[Any]:
    """Parameters of the UPDATE statements that ran."""
    return [params for sql, params in executed if "UPDATE" in sql]


@pytest.fixture(autouse=True)
def _config():
    """No OpenAthens or unpaywall settings."""
    with patch("bmlibrarian.config.get_config", return_value={}):
        yield


def test_verified_download_is_linked_with_its_text(tmp_path: Path) -> None:
    """A verified download stores full text and its relative pdf_filename."""
    pdf = tmp_path / "2024" / "x.pdf"
    pdf.parent.mkdir()
    pdf.write_bytes(b"%PDF-1.4")
    db, executed = _db(("10.1/x", "123", "T", None, None))
    result = DownloadResult(success=True, file_path=str(pdf), verified=True)
    with patch(DOWNLOAD_TARGET, return_value=result), \
         patch(CONVERTER_TARGET, _converter("Full text.")):
        assert document_qa._download_fulltext_if_needed(7, db, output_dir=tmp_path)
    assert _updates(executed) == [("Full text.", "2024/x.pdf", 7)]


def test_linked_pdf_is_reused_without_downloading(tmp_path: Path) -> None:
    """A PDF already linked and on disk is read, not downloaded again."""
    pdf = tmp_path / "2024" / "x.pdf"
    pdf.parent.mkdir()
    pdf.write_bytes(b"%PDF-1.4")
    db, executed = _db(("10.1/x", "123", "T", None, "2024/x.pdf"))
    with patch(DOWNLOAD_TARGET) as download, \
         patch(CONVERTER_TARGET, _converter("Full text.")):
        assert document_qa._download_fulltext_if_needed(7, db, output_dir=tmp_path)
    download.assert_not_called()
    assert _updates(executed) == [("Full text.", None, 7)]


def test_unverified_download_is_discarded(tmp_path: Path) -> None:
    """A PDF that could not be checked is deleted and nothing is stored."""
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    db, executed = _db(("10.1/x", "123", "T", None, None))
    result = DownloadResult(success=True, file_path=str(pdf), verification_error="bad xref")
    with patch(DOWNLOAD_TARGET, return_value=result):
        assert not document_qa._download_fulltext_if_needed(7, db, output_dir=tmp_path)
    assert not pdf.exists()
    assert _updates(executed) == []


def test_pdf_without_text_is_still_linked(tmp_path: Path) -> None:
    """An image-only PDF is linked (no re-download) but reports no full text."""
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    db, executed = _db(("10.1/x", "123", "T", None, None))
    result = DownloadResult(success=True, file_path=str(pdf), verified=True)
    with patch(DOWNLOAD_TARGET, return_value=result), \
         patch(CONVERTER_TARGET, _converter("  ")):
        assert not document_qa._download_fulltext_if_needed(7, db, output_dir=tmp_path)
    assert _updates(executed) == [(None, "x.pdf", 7)]
