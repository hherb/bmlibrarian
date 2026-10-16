"""Tests for PMCPackageDownloader's single-level retry loop.

Before 2026-10-16 the per-package loop wrapped _download_ftp(), which had its
own retry loop, so one package could hit NCBI up to 9 times.
"""

import ftplib
from pathlib import Path
from typing import List
from unittest.mock import MagicMock, patch

import pytest

from bmlibrarian.discovery.data_types import AccessType, PDFSource, SourceType
from bmlibrarian.discovery.pmc_package_downloader import (
    ExtractedPackage,
    PackageFetchError,
    PMCPackageDownloader,
    is_corruption_error,
)
from bmlibrarian.utils.rate_limit import HostRateLimiter

PACKAGE_URL = "ftp://ftp.ncbi.nlm.nih.gov/pub/pmc/oa_package/00/00/PMC1.tar.gz"


@pytest.fixture(autouse=True)
def no_sleep():
    """Skip real backoff sleeps."""
    with patch("bmlibrarian.discovery.pmc_package_downloader.time.sleep"):
        yield


def make_downloader(max_retries: int = 3) -> PMCPackageDownloader:
    """Downloader with a non-pacing limiter."""
    limiter = HostRateLimiter(default_interval=0.0, host_intervals={})
    return PMCPackageDownloader(timeout=1, max_retries=max_retries, rate_limiter=limiter)


def make_source() -> PDFSource:
    """PMC package source."""
    return PDFSource(
        url=PACKAGE_URL,
        source_type=SourceType.PMC_PACKAGE,
        access_type=AccessType.OPEN,
        priority=1,
        metadata={"pmcid": "PMC1"},
    )


def run(downloader: PMCPackageDownloader, tmp_path: Path):
    """Call download_and_extract into tmp_path."""
    return downloader.download_and_extract(
        source=make_source(),
        pdf_output_dir=tmp_path / "pdf",
        fulltext_output_dir=tmp_path / "fulltext",
        base_filename="PMC1",
    )


class TestDownloadFtpSingleShot:
    """_download_ftp() makes exactly one attempt and classifies failures."""

    def test_permission_error_not_retryable(self) -> None:
        """550-style errors are permanent."""
        downloader = make_downloader()
        with patch("ftplib.FTP") as ftp_cls:
            ftp_cls.return_value.retrbinary.side_effect = ftplib.error_perm("550 no such file")
            with pytest.raises(PackageFetchError) as exc:
                downloader._download_ftp(PACKAGE_URL)
        assert exc.value.retryable is False
        assert ftp_cls.return_value.connect.call_count == 1

    def test_timeout_retryable_and_single_attempt(self) -> None:
        """A timeout is transient but still only one connection is made."""
        downloader = make_downloader()
        with patch("ftplib.FTP") as ftp_cls:
            ftp_cls.return_value.connect.side_effect = TimeoutError("timed out")
            with pytest.raises(PackageFetchError) as exc:
                downloader._download_ftp(PACKAGE_URL)
        assert exc.value.retryable is True
        assert ftp_cls.return_value.connect.call_count == 1

    def test_invalid_url(self) -> None:
        """A URL without host/path is rejected without connecting."""
        downloader = make_downloader()
        with patch("ftplib.FTP") as ftp_cls:
            with pytest.raises(PackageFetchError) as exc:
                downloader._download_ftp("ftp://")
        assert exc.value.retryable is False
        ftp_cls.assert_not_called()

    def test_success_returns_bytes(self) -> None:
        """Data written by retrbinary is returned."""
        downloader = make_downloader()
        with patch("ftplib.FTP") as ftp_cls:
            ftp_cls.return_value.retrbinary.side_effect = lambda cmd, cb: cb(b"data")
            assert downloader._download_ftp(PACKAGE_URL) == b"data"


class TestDownloadAndExtractRetries:
    """download_and_extract() owns the only retry loop."""

    def test_transient_failures_bounded_by_max_retries(self, tmp_path: Path) -> None:
        """Every attempt failing transiently means max_retries fetches, not max_retries**2."""
        downloader = make_downloader(max_retries=3)
        calls: List[str] = []

        def fail(url: str) -> bytes:
            calls.append(url)
            raise PackageFetchError("FTP connection error: reset", retryable=True)

        with patch.object(downloader, "_download_ftp", side_effect=fail):
            result = run(downloader, tmp_path)

        assert len(calls) == 3
        assert result.success is False
        assert result.attempts == 3
        assert "after 3 attempts" in result.error_message

    def test_permanent_failure_stops_immediately(self, tmp_path: Path) -> None:
        """A non-retryable fetch error is not retried."""
        downloader = make_downloader(max_retries=3)
        with patch.object(downloader, "_download_ftp",
                          side_effect=PackageFetchError("FTP permission error: 550", False)) as fetch:
            result = run(downloader, tmp_path)
        assert fetch.call_count == 1
        assert result.success is False
        assert "550" in result.error_message

    def test_corrupt_download_is_refetched(self, tmp_path: Path) -> None:
        """A gzip/corruption extraction error triggers a fresh download."""
        downloader = make_downloader(max_retries=3)
        pdf = tmp_path / "pdf" / "PMC1.pdf"
        pdf.parent.mkdir(parents=True)
        pdf.write_bytes(b"%PDF-1.4")
        extractions = [
            ExtractedPackage(error_message="Invalid gzip data", package_contents=[]),
            ExtractedPackage(pdf_path=pdf, pdf_size=8, package_contents=["PMC1.pdf"]),
        ]
        with patch.object(downloader, "_download_ftp", return_value=b"x") as fetch, \
                patch.object(downloader, "_extract_package", side_effect=extractions):
            result = run(downloader, tmp_path)
        assert fetch.call_count == 2
        assert result.success is True
        assert result.attempts == 2

    def test_non_corruption_extraction_error_not_retried(self, tmp_path: Path) -> None:
        """An unusable package isn't downloaded again."""
        downloader = make_downloader(max_retries=3)
        extracted = ExtractedPackage(error_message="No PDF member in archive", package_contents=[])
        with patch.object(downloader, "_download_ftp", return_value=b"x") as fetch, \
                patch.object(downloader, "_extract_package", return_value=extracted):
            result = run(downloader, tmp_path)
        assert fetch.call_count == 1
        assert result.success is False
        assert result.error_message.startswith("PMC package extraction failed")

    def test_each_attempt_is_paced(self, tmp_path: Path) -> None:
        """Every FTP connection goes through the rate limiter."""
        limiter = MagicMock(spec=HostRateLimiter)
        downloader = PMCPackageDownloader(timeout=1, max_retries=2, rate_limiter=limiter)
        with patch("ftplib.FTP") as ftp_cls:
            ftp_cls.return_value.connect.side_effect = OSError("refused")
            run(downloader, tmp_path)
        assert limiter.acquire.call_count == 2


@pytest.mark.parametrize("message,expected", [
    ("Invalid tar file", True),
    ("Corrupt archive", True),
    ("Not a gzipped file", True),
    ("No PDF member in archive", False),
])
def test_is_corruption_error(message: str, expected: bool) -> None:
    """Corruption markers are matched case-insensitively."""
    assert is_corruption_error(message) is expected
