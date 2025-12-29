"""Unit tests for Europe PMC PDF downloader security fixes.

Tests cover:
- Path traversal attack prevention
- PMCID validation and bounds checking
- Range overlap validation
- HTTP session cleanup
- ReDoS protection in regex patterns
"""

import io
import tarfile
import tempfile
from pathlib import Path
from typing import Tuple
from unittest.mock import MagicMock, patch

import pytest

from src.bmlibrarian.importers.europe_pmc_pdf_downloader import (
    EuropePMCPDFDownloader,
    PDFPackageInfo,
    MIN_PMCID,
    MAX_PMCID,
    MAX_REGEX_MATCHES,
)


class TestPathTraversalPrevention:
    """Tests for path traversal vulnerability fixes."""

    def test_safe_path_allowed(self, tmp_path: Path) -> None:
        """Normal paths should be allowed."""
        downloader = EuropePMCPDFDownloader(output_dir=tmp_path)
        member = MagicMock()
        member.name = "PMC123456.pdf"

        assert downloader._is_safe_tar_member(member) is True
        downloader.close()

    def test_nested_safe_path_allowed(self, tmp_path: Path) -> None:
        """Nested paths without traversal should be allowed."""
        downloader = EuropePMCPDFDownloader(output_dir=tmp_path)
        member = MagicMock()
        member.name = "data/papers/PMC123456.pdf"

        assert downloader._is_safe_tar_member(member) is True
        downloader.close()

    def test_absolute_path_blocked(self, tmp_path: Path) -> None:
        """Absolute paths should be blocked."""
        downloader = EuropePMCPDFDownloader(output_dir=tmp_path)
        member = MagicMock()
        member.name = "/etc/passwd"

        assert downloader._is_safe_tar_member(member) is False
        downloader.close()

    def test_path_traversal_blocked(self, tmp_path: Path) -> None:
        """Path traversal attempts should be blocked."""
        downloader = EuropePMCPDFDownloader(output_dir=tmp_path)

        # Test various traversal patterns
        traversal_paths = [
            "../../../etc/passwd",
            "data/../../../etc/passwd",
            "..\\..\\..\\windows\\system32",
            "foo/../../bar/../../etc/passwd",
            "./../secret",
        ]

        for path in traversal_paths:
            member = MagicMock()
            member.name = path
            assert downloader._is_safe_tar_member(member) is False, f"Should block: {path}"

        downloader.close()

    def test_dotdot_in_filename_blocked(self, tmp_path: Path) -> None:
        """Filenames containing .. should be blocked."""
        downloader = EuropePMCPDFDownloader(output_dir=tmp_path)
        member = MagicMock()
        member.name = "PMC..123456.pdf"

        # This is actually safe, but our paranoid check blocks it
        # The important thing is we don't allow actual traversal
        result = downloader._is_safe_tar_member(member)
        # Our check blocks anything with '..' in the path
        assert result is False
        downloader.close()


class TestPMCIDValidation:
    """Tests for PMCID validation and bounds checking."""

    def test_valid_pmcid_range(self, tmp_path: Path) -> None:
        """Valid PMCID ranges should be accepted."""
        downloader = EuropePMCPDFDownloader(
            output_dir=tmp_path,
            pmcid_ranges=[(1, 1000), (5000, 10000)]
        )
        assert downloader.pmcid_ranges == [(1, 1000), (5000, 10000)]
        downloader.close()

    def test_pmcid_range_bounds_validation(self, tmp_path: Path) -> None:
        """PMCID ranges outside valid bounds should be rejected."""
        # Test below minimum
        with pytest.raises(ValueError, match="must be >="):
            EuropePMCPDFDownloader(
                output_dir=tmp_path,
                pmcid_ranges=[(0, 1000)]
            )

        # Test above maximum
        with pytest.raises(ValueError, match="exceeds maximum"):
            EuropePMCPDFDownloader(
                output_dir=tmp_path,
                pmcid_ranges=[(1, MAX_PMCID + 1)]
            )

    def test_pmcid_range_swap(self, tmp_path: Path) -> None:
        """Reversed PMCID ranges should be automatically swapped."""
        downloader = EuropePMCPDFDownloader(
            output_dir=tmp_path,
            pmcid_ranges=[(1000, 100)]  # Reversed
        )
        # Should be swapped to (100, 1000)
        assert downloader.pmcid_ranges == [(100, 1000)]
        downloader.close()

    def test_get_pmcid_subdir_valid(self, tmp_path: Path) -> None:
        """Valid PMCIDs should return correct subdirectory."""
        downloader = EuropePMCPDFDownloader(output_dir=tmp_path)

        assert downloader._get_pmcid_subdir(1) == "0/0-99"
        assert downloader._get_pmcid_subdir(100) == "0/100-199"
        assert downloader._get_pmcid_subdir(1000) == "1000/1000-1099"
        assert downloader._get_pmcid_subdir(12345) == "12000/12300-12399"

        downloader.close()

    def test_get_pmcid_subdir_bounds_check(self, tmp_path: Path) -> None:
        """PMCIDs outside valid range should raise ValueError."""
        downloader = EuropePMCPDFDownloader(output_dir=tmp_path)

        with pytest.raises(ValueError, match="out of valid range"):
            downloader._get_pmcid_subdir(0)

        with pytest.raises(ValueError, match="out of valid range"):
            downloader._get_pmcid_subdir(MAX_PMCID + 1)

        downloader.close()

    def test_get_pdf_path_validation(self, tmp_path: Path) -> None:
        """Invalid PMCIDs should raise ValueError in get_pdf_path."""
        downloader = EuropePMCPDFDownloader(output_dir=tmp_path)

        with pytest.raises(ValueError, match="Invalid PMCID"):
            downloader.get_pdf_path("")

        with pytest.raises(ValueError, match="Invalid PMCID"):
            downloader.get_pdf_path("notanumber")

        with pytest.raises(ValueError, match="Invalid PMCID"):
            downloader.get_pdf_path("PMCabc")

        downloader.close()


class TestRangeOverlapValidation:
    """Tests for PMCID range overlap checking."""

    def test_in_pmcid_range_no_filter(self, tmp_path: Path) -> None:
        """Without filter, all ranges should be accepted."""
        downloader = EuropePMCPDFDownloader(output_dir=tmp_path)
        assert downloader._in_pmcid_range(1, 1000000) is True
        downloader.close()

    def test_in_pmcid_range_exact_match(self, tmp_path: Path) -> None:
        """Exact range match should return True."""
        downloader = EuropePMCPDFDownloader(
            output_dir=tmp_path,
            pmcid_ranges=[(1000, 2000)]
        )
        assert downloader._in_pmcid_range(1000, 2000) is True
        downloader.close()

    def test_in_pmcid_range_subset(self, tmp_path: Path) -> None:
        """Subset of range should return True."""
        downloader = EuropePMCPDFDownloader(
            output_dir=tmp_path,
            pmcid_ranges=[(1000, 5000)]
        )
        assert downloader._in_pmcid_range(2000, 3000) is True
        downloader.close()

    def test_in_pmcid_range_overlap(self, tmp_path: Path) -> None:
        """Overlapping range should return True."""
        downloader = EuropePMCPDFDownloader(
            output_dir=tmp_path,
            pmcid_ranges=[(1000, 2000)]
        )
        # Package starts before, ends within
        assert downloader._in_pmcid_range(500, 1500) is True
        # Package starts within, ends after
        assert downloader._in_pmcid_range(1500, 2500) is True
        downloader.close()

    def test_in_pmcid_range_no_overlap(self, tmp_path: Path) -> None:
        """Non-overlapping range should return False."""
        downloader = EuropePMCPDFDownloader(
            output_dir=tmp_path,
            pmcid_ranges=[(1000, 2000)]
        )
        assert downloader._in_pmcid_range(3000, 4000) is False
        assert downloader._in_pmcid_range(100, 500) is False
        downloader.close()


class TestHTTPSessionCleanup:
    """Tests for HTTP session cleanup."""

    def test_context_manager_cleanup(self, tmp_path: Path) -> None:
        """Context manager should properly close session."""
        with EuropePMCPDFDownloader(output_dir=tmp_path) as downloader:
            # Force session creation
            session = downloader._get_session()
            assert session is not None

        # After exiting context, session should be None
        assert downloader._session is None

    def test_explicit_close(self, tmp_path: Path) -> None:
        """Explicit close() should clean up resources."""
        downloader = EuropePMCPDFDownloader(output_dir=tmp_path)
        session = downloader._get_session()
        assert session is not None

        downloader.close()
        assert downloader._session is None

    def test_lazy_session_creation(self, tmp_path: Path) -> None:
        """Session should not be created until needed."""
        downloader = EuropePMCPDFDownloader(output_dir=tmp_path)
        assert downloader._session is None

        # First call creates session
        session1 = downloader._get_session()
        assert session1 is not None

        # Second call returns same session
        session2 = downloader._get_session()
        assert session1 is session2

        downloader.close()


class TestUserAgentConfiguration:
    """Tests for User-Agent configuration."""

    def test_default_user_agent(self, tmp_path: Path) -> None:
        """Default User-Agent should not contain contact email."""
        downloader = EuropePMCPDFDownloader(output_dir=tmp_path)
        assert "mailto:" not in downloader._user_agent
        assert "example.com" not in downloader._user_agent
        assert "BMLibrarian" in downloader._user_agent
        downloader.close()

    def test_custom_contact_email(self, tmp_path: Path) -> None:
        """Custom contact email should be included in User-Agent."""
        downloader = EuropePMCPDFDownloader(
            output_dir=tmp_path,
            contact_email="test@example.org"
        )
        assert "mailto:test@example.org" in downloader._user_agent
        downloader.close()


class TestCLIRangeParsing:
    """Tests for CLI range parsing."""

    def test_valid_range_parsing(self) -> None:
        """Valid range strings should be parsed correctly."""
        from europe_pmc_pdf_cli import parse_range

        assert parse_range("1-1000") == (1, 1000)
        assert parse_range("1000-2000") == (1000, 2000)

    def test_invalid_range_format(self) -> None:
        """Invalid range format should raise ValueError."""
        from europe_pmc_pdf_cli import parse_range

        with pytest.raises(ValueError, match="Invalid range format"):
            parse_range("1000")

        with pytest.raises(ValueError, match="Invalid range format"):
            parse_range("1000-2000-3000")

    def test_non_numeric_range(self) -> None:
        """Non-numeric range values should raise ValueError."""
        from europe_pmc_pdf_cli import parse_range

        with pytest.raises(ValueError, match="Invalid PMCID values"):
            parse_range("abc-def")

    def test_range_bounds_validation(self) -> None:
        """Range values outside bounds should raise ValueError."""
        from europe_pmc_pdf_cli import parse_range

        with pytest.raises(ValueError, match="must be >="):
            parse_range("0-1000")

        with pytest.raises(ValueError, match="must be <="):
            parse_range(f"1-{MAX_PMCID + 1}")


class TestTarExtractionSecurity:
    """Integration tests for secure tar extraction."""

    def _create_tar_with_member(
        self,
        member_name: str,
        content: bytes = b'%PDF-test'
    ) -> io.BytesIO:
        """Create an in-memory tar.gz with a single file."""
        tar_buffer = io.BytesIO()
        with tarfile.open(fileobj=tar_buffer, mode='w:gz') as tar:
            info = tarfile.TarInfo(name=member_name)
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))
        tar_buffer.seek(0)
        return tar_buffer

    def test_extract_safe_pdf(self, tmp_path: Path) -> None:
        """Safe PDF paths should be extracted successfully."""
        # Create a tar with a safe path
        tar_buffer = self._create_tar_with_member("PMC123456.pdf")

        # Write to packages directory
        packages_dir = tmp_path / 'packages'
        packages_dir.mkdir()
        tar_path = packages_dir / "test.tar.gz"
        tar_path.write_bytes(tar_buffer.getvalue())

        downloader = EuropePMCPDFDownloader(output_dir=tmp_path)
        pkg = PDFPackageInfo(
            filename="test.tar.gz",
            pmcid_start=123456,
            pmcid_end=123456
        )

        count = downloader._extract_pdfs_from_package(pkg)
        assert count == 1

        # Verify PDF was extracted to correct location
        pdf_path = tmp_path / 'pdf' / '123000' / '123400-123499' / 'PMC123456.pdf'
        assert pdf_path.exists()

        downloader.close()

    def test_extract_blocks_traversal(self, tmp_path: Path) -> None:
        """Path traversal attempts should be blocked."""
        # Create a tar with a malicious path
        tar_buffer = self._create_tar_with_member("../../../etc/PMC999999.pdf")

        # Write to packages directory
        packages_dir = tmp_path / 'packages'
        packages_dir.mkdir()
        tar_path = packages_dir / "malicious.tar.gz"
        tar_path.write_bytes(tar_buffer.getvalue())

        downloader = EuropePMCPDFDownloader(output_dir=tmp_path)
        pkg = PDFPackageInfo(
            filename="malicious.tar.gz",
            pmcid_start=999999,
            pmcid_end=999999
        )

        count = downloader._extract_pdfs_from_package(pkg)
        assert count == 0  # Nothing should be extracted

        # Verify no files were created outside output dir
        assert not (tmp_path.parent / 'etc').exists()

        downloader.close()


class TestConstants:
    """Tests for configuration constants."""

    def test_pmcid_bounds(self) -> None:
        """PMCID bounds should be reasonable values."""
        assert MIN_PMCID == 1
        assert MAX_PMCID > 0
        assert MAX_PMCID < 10**10  # Reasonable upper bound

    def test_regex_match_limit(self) -> None:
        """Regex match limit should be a reasonable value."""
        assert MAX_REGEX_MATCHES > 0
        assert MAX_REGEX_MATCHES <= 100000
