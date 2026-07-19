"""Regression tests for silent PDF-corpus corruption bugs.

These tests are hermetic (no real network access): the HTTP/FTP layers
are replaced with mocks that simulate two classes of failure:

1. A remote server returns HTTP 200 with an HTML paywall/login page
   instead of a PDF (Bugs A and C). Previously this body was written to
   disk as a ``.pdf`` file and reported as a successful download.
2. A download raises an exception mid-stream (Timeout, ConnectionError,
   or a generic exception) after some bytes have already been written to
   the output file (Bug B). Previously the partially-written file was
   left on disk, causing later code to believe the PDF already existed
   and skip re-downloading it.

Covered call sites:
- ``bmlibrarian.utils.pdf_manager.PDFManager.download_pdf`` (Bug A)
- ``bmlibrarian.discovery.full_text_finder.FullTextFinder._download_from_source``
  and ``._download_via_ftp`` (Bug B)
- ``bmlibrarian.importers.medrxiv_importer.MedRxivImporter.download_pdf`` (Bug C)
"""

import ftplib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

from bmlibrarian.utils.pdf_validation import is_pdf_content, is_pdf_file
from bmlibrarian.utils.pdf_manager import PDFManager
from bmlibrarian.discovery.data_types import PDFSource, SourceType, AccessType
from bmlibrarian.discovery.full_text_finder import FullTextFinder


# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------

# A minimal but syntactically-valid PDF body: just needs to satisfy the
# %PDF- magic-byte check used throughout this module.
VALID_PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<< >>\nendobj\n%%EOF"

HTML_PAYWALL_BODY = (
    b"<!DOCTYPE html><html><head><title>Please sign in</title></head>"
    b"<body><h1>Access denied - institutional login required</h1></body></html>"
)


def _chunks(data: bytes, size: int = 8192):
    """Split bytes into a list of chunks, mimicking requests.iter_content()."""
    return [data[i:i + size] for i in range(0, len(data), size)] or [b""]


class RaisingIterator:
    """Iterator that yields some real data, then raises mid-stream.

    Used to simulate a dropped connection / read timeout partway through
    a download, after bytes have already been written to the output file.
    """

    def __init__(self, good_chunks, exception):
        self._chunks = list(good_chunks)
        self._exception = exception
        self._index = 0

    def __iter__(self):
        return self

    def __next__(self):
        if self._index < len(self._chunks):
            chunk = self._chunks[self._index]
            self._index += 1
            return chunk
        raise self._exception


def make_mock_response(body: bytes, content_type: str, raising_exception=None) -> MagicMock:
    """Build a MagicMock standing in for a `requests.Response`.

    Args:
        body: Bytes to (successfully) stream back, if raising_exception is None.
        content_type: Value for the Content-Type response header.
        raising_exception: If given, iter_content() yields no data and
            immediately raises this exception (mid-stream failure).

    Returns:
        MagicMock configured to behave like a streaming `requests` response.
    """
    response = MagicMock()
    response.status_code = 200
    response.headers = {"content-type": content_type}
    response.raise_for_status.return_value = None

    if raising_exception is not None:
        response.iter_content.return_value = RaisingIterator([b"partial-bytes-not-a-full-pdf"], raising_exception)
    else:
        response.iter_content.return_value = _chunks(body)

    return response


# ---------------------------------------------------------------------------
# Pure function: is_pdf_content / is_pdf_file
# ---------------------------------------------------------------------------

class TestIsPdfContent:
    """Unit tests for the shared magic-byte validation helper."""

    def test_valid_pdf_header_is_accepted(self):
        assert is_pdf_content(VALID_PDF_BYTES) is True

    def test_html_body_is_rejected(self):
        assert is_pdf_content(HTML_PAYWALL_BODY) is False

    def test_empty_bytes_rejected(self):
        assert is_pdf_content(b"") is False

    def test_non_bytes_input_rejected(self):
        assert is_pdf_content(None) is False  # type: ignore[arg-type]
        assert is_pdf_content("not-bytes-a-str") is False  # type: ignore[arg-type]

    def test_is_pdf_file_valid(self, tmp_path):
        pdf_file = tmp_path / "real.pdf"
        pdf_file.write_bytes(VALID_PDF_BYTES)
        assert is_pdf_file(pdf_file) is True

    def test_is_pdf_file_html_body(self, tmp_path):
        fake_file = tmp_path / "fake.pdf"
        fake_file.write_bytes(HTML_PAYWALL_BODY)
        assert is_pdf_file(fake_file) is False

    def test_is_pdf_file_missing_file(self, tmp_path):
        assert is_pdf_file(tmp_path / "does_not_exist.pdf") is False


# ---------------------------------------------------------------------------
# Bug A: PDFManager.download_pdf()
# ---------------------------------------------------------------------------

class TestPDFManagerDownloadIntegrity:
    """Regression tests for PDFManager.download_pdf() (Bug A)."""

    def _make_manager_and_document(self, tmp_path):
        manager = PDFManager(base_dir=str(tmp_path))
        document = {
            "id": 1,
            "doi": "10.1234/example.paper",
            "pdf_url": "https://example.com/paper.pdf",
        }
        return manager, document

    def test_html_paywall_page_not_persisted_and_signals_failure(self, tmp_path):
        """An HTML 200 response must not be saved as a .pdf or reported as success."""
        manager, document = self._make_manager_and_document(tmp_path)
        response = make_mock_response(HTML_PAYWALL_BODY, content_type="text/html; charset=utf-8")

        with patch("bmlibrarian.utils.pdf_manager.requests.get", return_value=response):
            result = manager.download_pdf(
                document, max_retries=1, use_browser_fallback=False
            )

        assert result is None, "download_pdf() must not report success for HTML content"

        pdf_path = manager.get_pdf_path(document)
        assert pdf_path is not None
        assert not pdf_path.exists(), "HTML paywall page must not be left on disk as a .pdf"

    def test_html_paywall_falls_back_to_browser_download(self, tmp_path):
        """When the HTTP body fails the PDF magic-byte check, the browser
        fallback path must actually run (previously it was unreachable
        because the mismatched content was reported as a success)."""
        manager, document = self._make_manager_and_document(tmp_path)
        response = make_mock_response(HTML_PAYWALL_BODY, content_type="text/html; charset=utf-8")

        def fake_browser_download(**kwargs):
            save_path = Path(kwargs["save_path"])
            save_path.parent.mkdir(parents=True, exist_ok=True)
            save_path.write_bytes(VALID_PDF_BYTES)
            return {"status": "success", "path": str(save_path), "size": len(VALID_PDF_BYTES)}

        with patch("bmlibrarian.utils.pdf_manager.requests.get", return_value=response), \
             patch(
                 "bmlibrarian.utils.browser_downloader.download_pdf_with_browser",
                 side_effect=fake_browser_download,
             ) as mock_browser:
            result = manager.download_pdf(
                document, max_retries=1, use_browser_fallback=True
            )

        assert mock_browser.called, "Browser fallback must be attempted after magic-byte failure"
        pdf_path = manager.get_pdf_path(document)
        assert result == pdf_path
        assert pdf_path.exists()
        assert pdf_path.read_bytes() == VALID_PDF_BYTES

    def test_valid_pdf_still_downloads_successfully(self, tmp_path):
        """Regression guard: legitimate PDF downloads must be unaffected."""
        manager, document = self._make_manager_and_document(tmp_path)
        response = make_mock_response(VALID_PDF_BYTES, content_type="application/pdf")

        with patch("bmlibrarian.utils.pdf_manager.requests.get", return_value=response):
            result = manager.download_pdf(
                document, max_retries=1, use_browser_fallback=False
            )

        pdf_path = manager.get_pdf_path(document)
        assert result == pdf_path
        assert pdf_path.exists()
        assert pdf_path.read_bytes() == VALID_PDF_BYTES


# ---------------------------------------------------------------------------
# Bug B: FullTextFinder._download_from_source() (HTTP)
# ---------------------------------------------------------------------------

class TestFullTextFinderHttpMidStreamCleanup:
    """Regression tests for FullTextFinder._download_from_source() (Bug B)."""

    def _make_finder(self):
        return FullTextFinder(unpaywall_email="test@example.com")

    def _make_source(self):
        return PDFSource(
            url="https://example.com/paper.pdf",
            source_type=SourceType.DIRECT_URL,
            access_type=AccessType.OPEN,
        )

    @pytest.mark.parametrize(
        "exception",
        [
            requests.exceptions.Timeout("read timed out"),
            requests.exceptions.ConnectionError("connection reset by peer"),
            RuntimeError("unexpected mid-stream failure"),
        ],
        ids=["timeout", "connection_error", "generic_exception"],
    )
    def test_partial_file_removed_on_mid_stream_exception(self, tmp_path, exception):
        finder = self._make_finder()
        output_path = tmp_path / "2024" / "paper.pdf"
        response = make_mock_response(b"", content_type="application/pdf", raising_exception=exception)

        with patch.object(finder.session, "get", return_value=response):
            result = finder._download_from_source(
                source=self._make_source(),
                output_path=output_path,
                max_attempts=1,
            )

        assert result.success is False
        assert not output_path.exists(), (
            "Partially-written file must be removed after a mid-stream download failure"
        )

    def test_valid_pdf_still_downloads_successfully(self, tmp_path):
        """Regression guard: legitimate downloads must be unaffected."""
        finder = self._make_finder()
        output_path = tmp_path / "2024" / "paper.pdf"
        response = make_mock_response(VALID_PDF_BYTES, content_type="application/pdf")

        with patch.object(finder.session, "get", return_value=response):
            result = finder._download_from_source(
                source=self._make_source(),
                output_path=output_path,
                max_attempts=1,
            )

        assert result.success is True
        assert output_path.exists()
        assert output_path.read_bytes() == VALID_PDF_BYTES


# ---------------------------------------------------------------------------
# Bug B: FullTextFinder._download_via_ftp()
# ---------------------------------------------------------------------------

class TestFullTextFinderFtpMidStreamCleanup:
    """Regression tests for FullTextFinder._download_via_ftp() (Bug B)."""

    FTP_URL = "ftp://ftp.example.com/pub/pmc/oa_pdf/sample.pdf"

    def _make_finder(self):
        return FullTextFinder(unpaywall_email="test@example.com")

    def _patch_ftp(self, exception):
        """Build a mocked ftplib.FTP class whose retrbinary() writes a
        partial chunk via the callback, then raises `exception`."""
        mock_ftp_instance = MagicMock()

        def retrbinary_side_effect(cmd, callback):
            callback(b"partial-ftp-bytes-not-a-full-pdf")
            raise exception

        mock_ftp_instance.retrbinary.side_effect = retrbinary_side_effect
        mock_ftp_class = MagicMock(return_value=mock_ftp_instance)
        return mock_ftp_class

    @pytest.mark.parametrize(
        "exception",
        [
            ftplib.error_temp("450 Requested file action not taken"),
            TimeoutError("FTP operation timed out"),
            RuntimeError("unexpected mid-stream FTP failure"),
        ],
        ids=["ftp_error_temp", "timeout_error", "generic_exception"],
    )
    def test_partial_file_removed_on_mid_stream_exception(self, tmp_path, exception):
        finder = self._make_finder()
        output_path = tmp_path / "2024" / "paper.pdf"
        mock_ftp_class = self._patch_ftp(exception)

        with patch("bmlibrarian.discovery.full_text_finder.ftplib.FTP", mock_ftp_class):
            result = finder._download_via_ftp(
                url=self.FTP_URL,
                output_path=output_path,
                max_attempts=1,
            )

        assert result.success is False
        assert not output_path.exists(), (
            "Partially-written FTP file must be removed after a mid-stream failure"
        )

    def test_valid_pdf_still_downloads_successfully_via_ftp(self, tmp_path):
        """Regression guard: legitimate FTP downloads must be unaffected."""
        finder = self._make_finder()
        output_path = tmp_path / "2024" / "paper.pdf"

        mock_ftp_instance = MagicMock()

        def retrbinary_side_effect(cmd, callback):
            callback(VALID_PDF_BYTES)

        mock_ftp_instance.retrbinary.side_effect = retrbinary_side_effect
        mock_ftp_class = MagicMock(return_value=mock_ftp_instance)

        with patch("bmlibrarian.discovery.full_text_finder.ftplib.FTP", mock_ftp_class):
            result = finder._download_via_ftp(
                url=self.FTP_URL,
                output_path=output_path,
                max_attempts=1,
            )

        assert result.success is True
        assert output_path.exists()
        assert output_path.read_bytes() == VALID_PDF_BYTES


# ---------------------------------------------------------------------------
# Bug C: MedRxivImporter.download_pdf()
# ---------------------------------------------------------------------------

class TestMedRxivImporterDownloadIntegrity:
    """Regression tests for MedRxivImporter.download_pdf() (Bug C)."""

    @pytest.fixture
    def importer(self, tmp_path):
        from bmlibrarian.importers.medrxiv_importer import MedRxivImporter

        mock_db_manager = MagicMock()
        mock_db_manager.get_cached_source_ids.return_value = {"medrxiv": 42}

        with patch(
            "bmlibrarian.importers.medrxiv_importer.get_db_manager",
            return_value=mock_db_manager,
        ):
            yield MedRxivImporter(pdf_base_dir=str(tmp_path))

    def test_html_paywall_page_not_persisted_and_signals_failure(self, importer, tmp_path):
        paper = {"doi": "10.1101/2024.01.01.24300000", "version": "1"}
        response = make_mock_response(HTML_PAYWALL_BODY, content_type="text/html; charset=utf-8")

        with patch("bmlibrarian.importers.medrxiv_importer.requests.get", return_value=response):
            filename, was_downloaded = importer.download_pdf(paper)

        assert filename is None
        assert was_downloaded is False

        expected_path = tmp_path / (paper["doi"].replace("/", "_") + ".pdf")
        assert not expected_path.exists(), "HTML paywall page must not be left on disk as a .pdf"

    def test_valid_pdf_still_downloads_successfully(self, importer, tmp_path):
        paper = {"doi": "10.1101/2024.01.01.24300001", "version": "1"}
        response = make_mock_response(VALID_PDF_BYTES, content_type="application/pdf")

        with patch("bmlibrarian.importers.medrxiv_importer.requests.get", return_value=response):
            filename, was_downloaded = importer.download_pdf(paper)

        expected_filename = paper["doi"].replace("/", "_") + ".pdf"
        assert filename == expected_filename
        assert was_downloaded is True

        expected_path = tmp_path / expected_filename
        assert expected_path.exists()
        assert expected_path.read_bytes() == VALID_PDF_BYTES


# ---------------------------------------------------------------------------
# Pre-existing files must survive failed download attempts
#
# The mid-stream cleanup handlers must never delete a good PDF that already
# existed at the output path before the attempt: when the failure occurs
# BEFORE any bytes are written (e.g. a connect timeout), the file on disk is
# a previous successful download, not this attempt's partial output.
# ---------------------------------------------------------------------------

class TestPreExistingFileSurvivesFailedAttempt:
    """A failed download attempt must not delete a pre-existing good PDF."""

    def test_full_text_finder_http_connect_failure_preserves_existing_pdf(self, tmp_path):
        """session.get() raising before any write must leave the old file intact."""
        finder = FullTextFinder(unpaywall_email="test@example.com")
        output_path = tmp_path / "2024" / "paper.pdf"
        output_path.parent.mkdir(parents=True)
        output_path.write_bytes(VALID_PDF_BYTES)

        with patch.object(
            finder.session, "get",
            side_effect=requests.exceptions.Timeout("connect timed out"),
        ):
            result = finder._download_from_source(
                source=PDFSource(
                    url="https://example.com/paper.pdf",
                    source_type=SourceType.DIRECT_URL,
                    access_type=AccessType.OPEN,
                ),
                output_path=output_path,
                max_attempts=1,
            )

        assert result.success is False
        assert output_path.exists(), (
            "A connect failure before any bytes were written must not delete "
            "the pre-existing PDF at the output path"
        )
        assert output_path.read_bytes() == VALID_PDF_BYTES

    def test_full_text_finder_ftp_connect_failure_preserves_existing_pdf(self, tmp_path):
        """An FTP connect failure before any write must leave the old file intact."""
        finder = FullTextFinder(unpaywall_email="test@example.com")
        output_path = tmp_path / "2024" / "paper.pdf"
        output_path.parent.mkdir(parents=True)
        output_path.write_bytes(VALID_PDF_BYTES)

        mock_ftp_instance = MagicMock()
        mock_ftp_instance.connect.side_effect = TimeoutError("FTP connect timed out")
        mock_ftp_class = MagicMock(return_value=mock_ftp_instance)

        with patch("bmlibrarian.discovery.full_text_finder.ftplib.FTP", mock_ftp_class):
            result = finder._download_via_ftp(
                url="ftp://ftp.example.com/pub/pmc/oa_pdf/sample.pdf",
                output_path=output_path,
                max_attempts=1,
            )

        assert result.success is False
        assert output_path.exists(), (
            "An FTP connect failure before any bytes were written must not "
            "delete the pre-existing PDF at the output path"
        )
        assert output_path.read_bytes() == VALID_PDF_BYTES

    def test_pdf_manager_connect_failure_preserves_existing_pdf(self, tmp_path):
        """requests.get() raising before any write must leave the old file intact."""
        manager = PDFManager(base_dir=str(tmp_path))
        document = {
            "id": 1,
            "doi": "10.1234/example.paper",
            "pdf_url": "https://example.com/paper.pdf",
            "pdf_filename": "2024/paper.pdf",
        }
        pdf_path = manager.get_pdf_path(document, create_dirs=True)
        pdf_path.write_bytes(VALID_PDF_BYTES)

        with patch(
            "bmlibrarian.utils.pdf_manager.requests.get",
            side_effect=requests.exceptions.ConnectionError("connection refused"),
        ):
            result = manager.download_pdf(
                document, max_retries=1, use_browser_fallback=False
            )

        assert result is None
        assert pdf_path.exists(), (
            "A connect failure before any bytes were written must not delete "
            "the pre-existing PDF at the output path"
        )
        assert pdf_path.read_bytes() == VALID_PDF_BYTES

    def test_full_text_finder_mid_stream_failure_still_removes_partial_output(self, tmp_path):
        """Temp-file downloads must not leak .part files after a mid-stream failure."""
        finder = FullTextFinder(unpaywall_email="test@example.com")
        output_path = tmp_path / "2024" / "paper.pdf"
        response = make_mock_response(
            b"", content_type="application/pdf",
            raising_exception=requests.exceptions.ConnectionError("reset"),
        )

        with patch.object(finder.session, "get", return_value=response):
            result = finder._download_from_source(
                source=PDFSource(
                    url="https://example.com/paper.pdf",
                    source_type=SourceType.DIRECT_URL,
                    access_type=AccessType.OPEN,
                ),
                output_path=output_path,
                max_attempts=1,
            )

        assert result.success is False
        assert not output_path.exists()
        leftovers = list(output_path.parent.glob("*")) if output_path.parent.exists() else []
        assert leftovers == [], f"Partial download artifacts left behind: {leftovers}"


# ---------------------------------------------------------------------------
# PDFManager browser fallback: reachable on exhausted retries, and validated
# ---------------------------------------------------------------------------

class TestPDFManagerBrowserFallbackConsistency:
    """The browser fallback must be reachable for exhausted-retry network
    failures and anti-bot HTTP rejections, and its output must pass the same
    magic-byte validation as direct HTTP downloads."""

    def _make_manager_and_document(self, tmp_path):
        manager = PDFManager(base_dir=str(tmp_path))
        document = {
            "id": 1,
            "doi": "10.1234/example.paper",
            "pdf_url": "https://example.com/paper.pdf",
        }
        return manager, document

    def _fake_browser_success(self, body: bytes):
        def fake_browser_download(**kwargs):
            save_path = Path(kwargs["save_path"])
            save_path.parent.mkdir(parents=True, exist_ok=True)
            save_path.write_bytes(body)
            return {"status": "success", "path": str(save_path), "size": len(body)}
        return fake_browser_download

    def test_exhausted_timeouts_fall_back_to_browser(self, tmp_path):
        """A timeout on every retry must reach the browser fallback, not give up."""
        manager, document = self._make_manager_and_document(tmp_path)

        with patch(
            "bmlibrarian.utils.pdf_manager.requests.get",
            side_effect=requests.exceptions.Timeout("read timed out"),
        ), patch(
            "bmlibrarian.utils.browser_downloader.download_pdf_with_browser",
            side_effect=self._fake_browser_success(VALID_PDF_BYTES),
        ) as mock_browser:
            result = manager.download_pdf(
                document, max_retries=2, use_browser_fallback=True
            )

        assert mock_browser.called, (
            "Browser fallback must be attempted after retries are exhausted"
        )
        pdf_path = manager.get_pdf_path(document)
        assert result == pdf_path
        assert pdf_path.read_bytes() == VALID_PDF_BYTES

    def test_http_403_falls_back_to_browser(self, tmp_path):
        """An anti-bot 403 is exactly what the browser fallback exists for."""
        manager, document = self._make_manager_and_document(tmp_path)

        response = MagicMock()
        response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            response=MagicMock(status_code=403)
        )

        with patch(
            "bmlibrarian.utils.pdf_manager.requests.get", return_value=response
        ), patch(
            "bmlibrarian.utils.browser_downloader.download_pdf_with_browser",
            side_effect=self._fake_browser_success(VALID_PDF_BYTES),
        ) as mock_browser:
            result = manager.download_pdf(
                document, max_retries=1, use_browser_fallback=True
            )

        assert mock_browser.called, "Browser fallback must be attempted on HTTP 403"
        pdf_path = manager.get_pdf_path(document)
        assert result == pdf_path
        assert pdf_path.read_bytes() == VALID_PDF_BYTES

    def test_http_404_does_not_launch_browser(self, tmp_path):
        """A definitive 404 must not waste a browser launch."""
        manager, document = self._make_manager_and_document(tmp_path)

        response = MagicMock()
        response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            response=MagicMock(status_code=404)
        )

        with patch(
            "bmlibrarian.utils.pdf_manager.requests.get", return_value=response
        ), patch(
            "bmlibrarian.utils.browser_downloader.download_pdf_with_browser"
        ) as mock_browser:
            result = manager.download_pdf(
                document, max_retries=1, use_browser_fallback=True
            )

        assert result is None
        assert not mock_browser.called, "404 is definitive - no browser fallback"

    def test_browser_fallback_output_is_magic_byte_validated(self, tmp_path):
        """A browser 'success' that produced HTML must be rejected, not persisted."""
        manager, document = self._make_manager_and_document(tmp_path)
        response = make_mock_response(
            HTML_PAYWALL_BODY, content_type="text/html; charset=utf-8"
        )

        with patch(
            "bmlibrarian.utils.pdf_manager.requests.get", return_value=response
        ), patch(
            "bmlibrarian.utils.browser_downloader.download_pdf_with_browser",
            side_effect=self._fake_browser_success(HTML_PAYWALL_BODY),
        ) as mock_browser:
            result = manager.download_pdf(
                document, max_retries=1, use_browser_fallback=True
            )

        assert mock_browser.called
        assert result is None, (
            "A non-PDF browser download must not be reported as success"
        )
        pdf_path = manager.get_pdf_path(document)
        assert not pdf_path.exists(), (
            "A non-PDF browser download must not be left on disk as a .pdf"
        )
        leftovers = list(pdf_path.parent.glob("*")) if pdf_path.parent.exists() else []
        assert leftovers == [], f"Partial download artifacts left behind: {leftovers}"
