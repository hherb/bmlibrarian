"""Path-traversal (zip/tar slip) regression tests for bulk importers.

These tests build malicious archives on disk and drive the real extraction
methods, asserting that traversal members are rejected and never written
outside the intended extraction directory. They are hermetic: importers are
constructed against a ``tmp_path`` and no network, S3, or database access
occurs.
"""

import tarfile
import zipfile
from pathlib import Path

from bmlibrarian.importers.pmc_bulk_importer import (
    LicenseType,
    PackageFormat,
    PackageInfo,
    PMCBulkImporter,
)
from bmlibrarian.importers.medrxiv_meca_importer import (
    MECAPackageInfo,
    MedRxivMECAImporter,
)


def _write_targz(archive_path: Path, members: dict[str, bytes]) -> None:
    """Create a tar.gz archive containing the given {name: content} members."""
    import io

    with tarfile.open(archive_path, "w:gz") as tar:
        for name, content in members.items():
            info = tarfile.TarInfo(name=name)
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))


def _write_zip(archive_path: Path, members: dict[str, bytes]) -> None:
    """Create a zip archive containing the given {name: content} members."""
    with zipfile.ZipFile(archive_path, "w") as zf:
        for name, content in members.items():
            zf.writestr(name, content)


class TestPMCBulkTarExtractionSecurity:
    """PMCBulkImporter._extract_package must reject tar-slip members."""

    @staticmethod
    def _make_pkg(filename: str) -> PackageInfo:
        return PackageInfo(
            filename=filename,
            license_type=LicenseType.COMMERCIAL,
            format=PackageFormat.XML,
            pmcid_range="PMC001xxxxxx",
            is_baseline=True,
            date="2026-01-01",
        )

    def test_safe_members_extracted(self, tmp_path: Path) -> None:
        """A safe .nxml member is extracted and counted."""
        importer = PMCBulkImporter(output_dir=tmp_path)
        pkg = self._make_pkg("safe.tar.gz")
        _write_targz(
            importer.packages_dir / pkg.filename,
            {"PMC123/PMC123.nxml": b"<article/>"},
        )

        count = importer._extract_package(pkg)

        assert count == 1
        extracted = importer.extracted_dir / "safe" / "PMC123" / "PMC123.nxml"
        assert extracted.exists()

    def test_traversal_member_blocked(self, tmp_path: Path) -> None:
        """A '..' member is skipped and never written outside extract dir."""
        importer = PMCBulkImporter(output_dir=tmp_path)
        pkg = self._make_pkg("evil.tar.gz")
        _write_targz(
            importer.packages_dir / pkg.filename,
            {
                "../../../evil.nxml": b"<article/>",
                "PMC999/PMC999.nxml": b"<article/>",
            },
        )

        count = importer._extract_package(pkg)

        # Only the safe member counts.
        assert count == 1
        # The traversal payload must not escape the output tree.
        assert not (tmp_path.parent / "evil.nxml").exists()
        assert not (tmp_path / "evil.nxml").exists()

    def test_absolute_member_blocked(self, tmp_path: Path) -> None:
        """An absolute-path member is rejected."""
        importer = PMCBulkImporter(output_dir=tmp_path)
        pkg = self._make_pkg("abs.tar.gz")
        _write_targz(
            importer.packages_dir / pkg.filename,
            {"/tmp/evil.nxml": b"<article/>"},
        )

        count = importer._extract_package(pkg)
        assert count == 0


class TestMECAZipExtractionSecurity:
    """MedRxivMECAImporter.extract_package must reject zip-slip members."""

    def test_traversal_member_blocked(self, tmp_path: Path) -> None:
        """A '..' zip member is skipped; safe members still extract."""
        importer = MedRxivMECAImporter(output_dir=tmp_path)
        archive_path = tmp_path / "evil.meca"
        _write_zip(
            archive_path,
            {
                "../../../evil.txt": b"payload",
                "content/article.xml": b"<article/>",
            },
        )
        package = MECAPackageInfo(
            key="s3/evil.meca",
            filename="evil.meca",
            local_path=str(archive_path),
        )

        importer.extract_package(package)

        extract_dir = tmp_path / "extracted" / "evil"
        # Safe member was extracted...
        assert (extract_dir / "content" / "article.xml").exists()
        # ...but the traversal payload never escaped the extract dir.
        assert not (tmp_path.parent / "evil.txt").exists()
        assert not (tmp_path / "evil.txt").exists()

    def test_absolute_member_blocked(self, tmp_path: Path) -> None:
        """An absolute-path zip member is rejected."""
        importer = MedRxivMECAImporter(output_dir=tmp_path)
        archive_path = tmp_path / "abs.meca"
        _write_zip(
            archive_path,
            {
                "/tmp/evil.txt": b"payload",
                "content/article.xml": b"<article/>",
            },
        )
        package = MECAPackageInfo(
            key="s3/abs.meca",
            filename="abs.meca",
            local_path=str(archive_path),
        )

        importer.extract_package(package)

        extract_dir = tmp_path / "extracted" / "abs"
        # Safe member extracted; the absolute-path member was skipped, so its
        # sanitized landing spot inside the extract dir must not exist either.
        assert (extract_dir / "content" / "article.xml").exists()
        assert not (extract_dir / "tmp" / "evil.txt").exists()
