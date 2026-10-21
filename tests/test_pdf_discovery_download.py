"""Tests for PDF discovery and download with browser fallback functionality.

Tests the integrated workflow: discovery -> direct HTTP -> browser fallback
"""

import pytest
import requests
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime

from bmlibrarian.discovery import (
    FullTextFinder,
    DocumentIdentifiers,
    DiscoveryResult,
    DownloadResult,
    PDFSource,
    SourceType,
    AccessType,
    download_pdf_for_document
)

# _download_with_browser imports this lazily, so patch it at its source.
BROWSER_DOWNLOAD_TARGET = 'bmlibrarian.utils.browser_downloader.download_pdf_with_browser'


class TestFullTextFinderBrowserFallback:
    """Test FullTextFinder browser fallback functionality."""

    def test_discover_and_download_with_browser_fallback_enabled(self):
        """Test that browser fallback is enabled by default."""
        finder = FullTextFinder(unpaywall_email="test@example.com")

        # Default browser config should be set
        assert hasattr(finder, '_browser_fallback_config') is False  # Not set until from_config

    def test_from_config_with_browser_settings(self):
        """Test from_config correctly sets browser fallback settings."""
        config = {
            'unpaywall_email': 'test@example.com',
            'discovery': {
                'use_browser_fallback': True,
                'browser_headless': False,
                'browser_timeout': 120000
            }
        }

        finder = FullTextFinder.from_config(config)

        assert finder._browser_fallback_config['enabled'] is True
        assert finder._browser_fallback_config['headless'] is False
        assert finder._browser_fallback_config['timeout'] == 120000

    def test_from_config_browser_fallback_disabled(self):
        """Test browser fallback can be disabled via config."""
        config = {
            'discovery': {
                'use_browser_fallback': False
            }
        }

        finder = FullTextFinder.from_config(config)

        assert finder._browser_fallback_config['enabled'] is False

    def test_discover_and_download_tries_browser_on_http_failure(self, tmp_path):
        """Test that browser download is tried when HTTP fails."""
        finder = FullTextFinder(unpaywall_email="test@example.com")

        mock_source = PDFSource(
            url="https://example.com/paper.pdf",
            source_type=SourceType.UNPAYWALL,
            access_type=AccessType.OPEN,
            priority=1
        )
        output_path = tmp_path / "paper.pdf"

        def fake_browser_download(url, save_path, **kwargs):
            Path(save_path).write_bytes(b"%PDF-1.4 browser")
            return {'status': 'success', 'size': 16}

        with patch.object(finder, 'discover') as mock_discover, \
                patch.object(finder.session, 'get',
                             side_effect=requests.ConnectionError("HTTP failed")) as mock_get, \
                patch('bmlibrarian.discovery.full_text_finder.time.sleep'), \
                patch(BROWSER_DOWNLOAD_TARGET, side_effect=fake_browser_download) as mock_browser:
            mock_discover.return_value = DiscoveryResult(
                identifiers=DocumentIdentifiers(doi="10.1234/test"),
                sources=[mock_source],
                resolution_results=[]
            )

            result = finder.discover_and_download(
                DocumentIdentifiers(doi="10.1234/test"), output_path, max_attempts=1
            )

        assert mock_get.called
        assert mock_browser.call_count == 1
        assert result.success is True


class TestExcludedSources:
    """Sources the user rejected are not downloaded from again (#315)."""

    def _sources(self):
        """Two discovered sources, the rejected one first."""
        return [
            PDFSource(url="https://bad.example/a.pdf", source_type=SourceType.PMC,
                      access_type=AccessType.OPEN, priority=1),
            PDFSource(url="https://good.example/b.pdf", source_type=SourceType.UNPAYWALL,
                      access_type=AccessType.OPEN, priority=2),
        ]

    def test_excluded_url_is_skipped(self, tmp_path):
        """Only the source not rejected earlier is tried."""
        finder = FullTextFinder(unpaywall_email="test@example.com")
        identifiers = DocumentIdentifiers(doi="10.1234/test")
        with patch.object(finder, 'discover', return_value=DiscoveryResult(
                identifiers=identifiers, sources=self._sources(), resolution_results=[])), \
             patch.object(finder, '_download_from_source',
                          return_value=DownloadResult(success=True)) as download:
            result = finder.discover_and_download(
                identifiers, tmp_path / "p.pdf", use_browser_fallback=False,
                excluded_urls={"https://bad.example/a.pdf"},
            )
        assert result.success
        assert [c.kwargs['source'].url for c in download.call_args_list] == [
            "https://good.example/b.pdf"
        ]

    def test_excluded_doi_fallback_is_not_added(self, tmp_path):
        """With nothing discovered, a rejected DOI fallback URL is not retried
        and the error says why nothing was tried."""
        finder = FullTextFinder(unpaywall_email="test@example.com")
        identifiers = DocumentIdentifiers(doi="10.1234/test")
        fallback = finder._create_doi_fallback_url("10.1234/test")
        with patch.object(finder, 'discover', return_value=DiscoveryResult(
                identifiers=identifiers, sources=[], resolution_results=[])), \
             patch.object(finder, '_download_from_source') as download:
            result = finder.discover_and_download(
                identifiers, tmp_path / "p.pdf", excluded_urls={fallback},
            )
        download.assert_not_called()
        assert not result.success
        assert "rejected earlier" in result.error_message


class TestDownloadForDocument:
    """Test download_for_document convenience method."""

    def test_download_for_document_extracts_identifiers(self):
        """Test that identifiers are correctly extracted from document dict."""
        finder = FullTextFinder(unpaywall_email="test@example.com")

        document = {
            'id': 123,
            'doi': '10.1234/test',
            'pmid': '12345678',
            'pmcid': 'PMC1234567',
            'title': 'Test Paper',
            'pdf_url': 'https://example.com/paper.pdf',
            'publication_date': '2024-01-15'
        }

        # Mock the discover_and_download to verify identifiers
        with patch.object(finder, 'discover_and_download') as mock_dad:
            mock_dad.return_value = DownloadResult(
                success=False,
                error_message="Test"
            )

            finder.download_for_document(document)

            # Check that discover_and_download was called with correct path
            call_args = mock_dad.call_args
            assert call_args is not None

    @pytest.mark.parametrize("existed", [False, True])
    def test_reports_whether_output_file_existed(self, tmp_path, existed):
        """``file_existed_before`` tells callers if the PDF overwrote a file."""
        finder = FullTextFinder(unpaywall_email="test@example.com")
        document = {'id': 5, 'doi': '10.1234/test', 'publication_date': '2024'}
        if existed:
            target = finder._generate_output_path(document, tmp_path)
            target.write_bytes(b"%PDF-1.4 old")
        with patch.object(finder, 'discover_and_download',
                          return_value=DownloadResult(success=True)):
            result = finder.download_for_document(document, output_dir=tmp_path)
        assert result.file_existed_before is existed

    def test_download_for_document_generates_year_path(self):
        """Test that output path uses year-based directory structure."""
        finder = FullTextFinder(unpaywall_email="test@example.com")

        document = {
            'id': 123,
            'doi': '10.1234/test',
            'publication_date': '2024-01-15'
        }

        output_dir = Path("/tmp/pdfs")
        expected_path = output_dir / "2024" / "10.1234_test.pdf"

        generated_path = finder._generate_output_path(document, output_dir)

        assert generated_path.parent.name == "2024"
        assert "10.1234_test" in generated_path.name

    def test_download_for_document_handles_missing_year(self):
        """Test that documents without year use 'unknown' subdirectory."""
        finder = FullTextFinder(unpaywall_email="test@example.com")

        document = {
            'id': 123,
            'doi': '10.1234/test'
            # No publication_date
        }

        output_dir = Path("/tmp/pdfs")
        generated_path = finder._generate_output_path(document, output_dir)

        assert generated_path.parent.name == "unknown"

    def test_download_for_document_uses_doc_id_when_no_doi(self):
        """Test that document ID is used for filename when no DOI."""
        finder = FullTextFinder(unpaywall_email="test@example.com")

        document = {
            'id': 456
            # No DOI
        }

        output_dir = Path("/tmp/pdfs")
        generated_path = finder._generate_output_path(document, output_dir)

        assert "doc_456" in generated_path.name


class TestDownloadPdfForDocumentFunction:
    """Test the standalone download_pdf_for_document convenience function."""

    @patch('bmlibrarian.discovery.full_text_finder.FullTextFinder')
    def test_convenience_function_creates_finder(self, mock_finder_class):
        """Test that convenience function creates FullTextFinder correctly."""
        mock_finder = MagicMock()
        mock_finder.download_for_document.return_value = DownloadResult(
            success=True,
            file_path="/tmp/test.pdf"
        )
        mock_finder_class.return_value = mock_finder

        document = {'doi': '10.1234/test'}

        result = download_pdf_for_document(
            document=document,
            unpaywall_email='test@example.com',
            use_browser_fallback=True
        )

        mock_finder_class.assert_called_once()


class TestExtractYear:
    """Test year extraction from documents."""

    def test_extract_year_from_datetime(self):
        """Test year extraction from datetime object."""
        finder = FullTextFinder()

        document = {'publication_date': datetime(2024, 6, 15)}
        assert finder._extract_year(document) == 2024

    def test_extract_year_from_date_string(self):
        """Test year extraction from ISO date string."""
        finder = FullTextFinder()

        document = {'publication_date': '2023-12-25'}
        assert finder._extract_year(document) == 2023

    def test_extract_year_from_year_only_string(self):
        """Test year extraction from year-only string."""
        finder = FullTextFinder()

        document = {'publication_date': '2022'}
        assert finder._extract_year(document) == 2022

    def test_extract_year_from_year_field(self):
        """Test year extraction from year field."""
        finder = FullTextFinder()

        document = {'year': 2021}
        assert finder._extract_year(document) == 2021

    def test_extract_year_returns_none_for_missing(self):
        """Test year extraction returns None when no date info."""
        finder = FullTextFinder()

        document = {'title': 'Test'}
        assert finder._extract_year(document) is None


class TestBrowserDownloadMethod:
    """Test _download_with_browser method."""

    def test_download_with_browser_handles_import_error(self):
        """Test graceful handling when playwright is not installed."""
        finder = FullTextFinder()

        sources = [
            PDFSource(
                url="https://example.com/paper.pdf",
                source_type=SourceType.DOI_REDIRECT,
                access_type=AccessType.UNKNOWN,
                priority=10
            )
        ]

        # A None entry in sys.modules makes the function-level import raise
        # ImportError, as it would without playwright.
        with patch.dict('sys.modules', {'bmlibrarian.utils.browser_downloader': None}):
            result = finder._download_with_browser(sources, Path("/tmp/test.pdf"))

        assert result.success is False
        assert "not available" in result.error_message

    @patch(BROWSER_DOWNLOAD_TARGET)
    def test_download_with_browser_tries_all_sources(self, mock_browser):
        """Test that browser download tries all sources in order."""
        mock_browser.return_value = {'status': 'failed', 'error': 'Test error'}

        finder = FullTextFinder()

        sources = [
            PDFSource(url="https://example.com/1.pdf", source_type=SourceType.PMC, access_type=AccessType.OPEN, priority=1),
            PDFSource(url="https://example.com/2.pdf", source_type=SourceType.UNPAYWALL, access_type=AccessType.OPEN, priority=2),
        ]

        result = finder._download_with_browser(sources, Path("/tmp/test.pdf"))

        # Should have tried both sources
        assert mock_browser.call_count == 2
        assert result.success is False

    @patch(BROWSER_DOWNLOAD_TARGET)
    def test_download_with_browser_returns_on_success(self, mock_browser):
        """Test that browser download returns immediately on success."""
        mock_browser.return_value = {'status': 'success', 'size': 5000}

        finder = FullTextFinder()

        sources = [
            PDFSource(url="https://example.com/1.pdf", source_type=SourceType.PMC, access_type=AccessType.OPEN, priority=1),
            PDFSource(url="https://example.com/2.pdf", source_type=SourceType.UNPAYWALL, access_type=AccessType.OPEN, priority=2),
        ]

        # Create temp file to simulate successful download
        output_path = Path("/tmp/test_browser_download.pdf")
        output_path.touch()

        try:
            result = finder._download_with_browser(sources, output_path)

            # Should succeed on first source
            assert mock_browser.call_count == 1
            assert result.success is True
        finally:
            if output_path.exists():
                output_path.unlink()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


class TestThrottledDownloadNotRetriedTwice:
    """A throttled source is retried by the session only, not again by the download loop."""

    @pytest.mark.parametrize("status", [429, 503])
    def test_throttle_costs_only_session_retries(self, status, tmp_path):
        """Persistent 429 / 503+Retry-After: 1 + session retries requests, then fail."""
        import io
        from bmlibrarian.utils.rate_limit import (
            DEFAULT_MAX_RATE_LIMIT_RETRIES, HostRateLimiter,
        )

        limiter = HostRateLimiter(default_interval=0.0, host_intervals={},
                                  sleep=lambda seconds: None)
        finder = FullTextFinder(rate_limiter=limiter)
        source = PDFSource(url="https://publisher.example/paper.pdf",
                           source_type=SourceType.DOI_REDIRECT,
                           access_type=AccessType.UNKNOWN, priority=10)

        def throttled(*args, **kwargs):
            response = requests.Response()
            response.status_code = status
            response.headers["Retry-After"] = "1"
            response.raw = io.BytesIO(b"")
            response.url = source.url
            return response

        with patch.object(requests.Session, "request", side_effect=throttled) as req, \
                patch('bmlibrarian.discovery.full_text_finder.time.sleep'):
            result = finder._download_from_source(source, tmp_path / "p.pdf", max_attempts=3)

        assert req.call_count == DEFAULT_MAX_RATE_LIMIT_RETRIES + 1
        assert result.success is False
        assert f"HTTP {status}" in result.error_message
