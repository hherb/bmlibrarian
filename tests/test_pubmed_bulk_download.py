"""
Tests for PubMedBulkImporter's download paths (HTTPS, MD5-verified).

The downloader is replaced by a fake that "downloads" by writing bytes, so the
importer's listing, skipping, tracking and failure handling are tested without
a network or database.
"""

from pathlib import Path
from typing import Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

from src.bmlibrarian.importers.pubmed_bulk_importer import PubMedBulkImporter


class FakeDownloader:
    """Lists fixed files; download succeeds unless the name is in ``fail``."""

    def __init__(self, files: List[str], fail: Optional[set] = None) -> None:
        self.files = files
        self.fail = fail or set()
        self.listed: List[str] = []
        self.downloads: List[str] = []

    def list_files(self, directory_url: str) -> List[str]:
        self.listed.append(directory_url)
        return list(self.files)

    def fetch_md5(self, file_url: str) -> str:
        return "0" * 32

    def download(self, url: str, dest: Path, expected_md5: str, progress_callback=None) -> bool:
        name = url.rsplit("/", 1)[-1]
        self.downloads.append(url)
        if name in self.fail:
            return False
        dest.write_bytes(b"data")
        return True


class FakeTracker:
    """In-memory DownloadTracker."""

    def __init__(self, downloaded: Optional[set] = None) -> None:
        self.downloaded: Dict[str, tuple] = {n: ("baseline", 4, "x") for n in (downloaded or set())}

    def is_file_downloaded(self, filename: str) -> bool:
        return filename in self.downloaded

    def mark_downloaded(self, filename: str, file_type: str, file_size: int, checksum: str) -> None:
        self.downloaded[filename] = (file_type, file_size, checksum)


def make_importer(tmp_path: Path, downloader: FakeDownloader,
                  tracker: Optional[FakeTracker] = None) -> PubMedBulkImporter:
    """Importer with the database mocked out and the fakes injected."""
    with patch("src.bmlibrarian.importers.pubmed_bulk_importer.get_db_manager") as mock_db:
        mock_db.return_value = MagicMock()
        cursor = mock_db.return_value.get_connection.return_value.__enter__.return_value.cursor
        cursor.return_value.__enter__.return_value.fetchone.return_value = [1]
        importer = PubMedBulkImporter(data_dir=str(tmp_path), use_tracking=False, downloader=downloader)
    importer.tracker = tracker
    return importer


class TestDownloadBaseline:
    """Baseline downloads use the HTTPS listing and record verified files."""

    def test_downloads_listed_files_over_https(self, tmp_path: Path) -> None:
        dl = FakeDownloader(["pubmed26n0001.xml.gz", "pubmed26n0002.xml.gz"])
        tracker = FakeTracker()
        importer = make_importer(tmp_path, dl, tracker)
        assert importer.download_baseline() == 2
        assert dl.listed == ["https://ftp.ncbi.nlm.nih.gov/pubmed/baseline/"]
        assert dl.downloads[0] == "https://ftp.ncbi.nlm.nih.gov/pubmed/baseline/pubmed26n0001.xml.gz"
        assert (tmp_path / "baseline" / "pubmed26n0002.xml.gz").exists()
        assert tracker.downloaded["pubmed26n0001.xml.gz"][0] == "baseline"

    def test_skips_tracked_files_that_exist(self, tmp_path: Path) -> None:
        dl = FakeDownloader(["pubmed26n0001.xml.gz", "pubmed26n0002.xml.gz"])
        importer = make_importer(tmp_path, dl, FakeTracker({"pubmed26n0001.xml.gz"}))
        (tmp_path / "baseline" / "pubmed26n0001.xml.gz").write_bytes(b"data")
        assert importer.download_baseline() == 1
        assert [u.rsplit("/", 1)[-1] for u in dl.downloads] == ["pubmed26n0002.xml.gz"]

    def test_tracked_but_missing_file_is_downloaded_again(self, tmp_path: Path) -> None:
        dl = FakeDownloader(["pubmed26n0001.xml.gz"])
        importer = make_importer(tmp_path, dl, FakeTracker({"pubmed26n0001.xml.gz"}))
        assert importer.download_baseline() == 1

    def test_failed_file_is_not_tracked_and_others_continue(self, tmp_path: Path) -> None:
        dl = FakeDownloader(["pubmed26n0001.xml.gz", "pubmed26n0002.xml.gz"], fail={"pubmed26n0001.xml.gz"})
        tracker = FakeTracker()
        importer = make_importer(tmp_path, dl, tracker)
        assert importer.download_baseline() == 1
        assert "pubmed26n0001.xml.gz" not in tracker.downloaded
        assert not (tmp_path / "baseline" / "pubmed26n0001.xml.gz").exists()


class TestDownloadUpdates:
    """Update files come from the updatefiles directory."""

    def test_downloads_update_files(self, tmp_path: Path) -> None:
        dl = FakeDownloader(["pubmed26n1335.xml.gz"])
        tracker = FakeTracker()
        importer = make_importer(tmp_path, dl, tracker)
        assert importer.download_updates() == 1
        assert dl.listed == ["https://ftp.ncbi.nlm.nih.gov/pubmed/updatefiles/"]
        assert (tmp_path / "updatefiles" / "pubmed26n1335.xml.gz").exists()
        assert tracker.downloaded["pubmed26n1335.xml.gz"][0] == "update"
