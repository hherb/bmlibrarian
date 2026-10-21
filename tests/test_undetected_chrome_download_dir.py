"""Tests that the undetected-Chrome fallback only takes its own downloads (#325).

Chrome used to download into the shared ``<year>/`` folder, and the newest
``*.pdf`` there was moved onto the target path, which could be another
document's PDF. It now downloads into a fresh per-call directory.
"""

import os
import sys
import types
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from bmlibrarian.utils import browser_downloader
from bmlibrarian.utils.browser_downloader import (
    CHROME_DOWNLOAD_DIR_PREFIX,
    download_pdf_with_undetected_chrome,
    promote_downloaded_pdf,
)

PDF_BYTES = b"%PDF-1.4\n% test\n"
OTHER_PDF_BYTES = b"%PDF-1.4\n% another document\n"


class TestPromoteDownloadedPdf:
    """promote_downloaded_pdf moves only a valid PDF from the download dir."""

    def test_moves_pdf_onto_save_path(self, tmp_path: Path) -> None:
        """A valid PDF replaces the (empty) reserved placeholder."""
        download_dir = tmp_path / "dl"
        download_dir.mkdir()
        (download_dir / "article.pdf").write_bytes(PDF_BYTES)
        save_path = tmp_path / "10.1000_x.pdf"
        save_path.touch()

        size = promote_downloaded_pdf(download_dir, save_path)

        assert size == len(PDF_BYTES)
        assert save_path.read_bytes() == PDF_BYTES
        assert not (download_dir / "article.pdf").exists()

    def test_no_download_returns_none(self, tmp_path: Path) -> None:
        """An empty download dir leaves save_path untouched."""
        download_dir = tmp_path / "dl"
        download_dir.mkdir()
        save_path = tmp_path / "target.pdf"
        save_path.touch()

        assert promote_downloaded_pdf(download_dir, save_path) is None
        assert save_path.read_bytes() == b""

    def test_non_pdf_is_not_promoted(self, tmp_path: Path) -> None:
        """An HTML page saved as .pdf never lands on save_path."""
        download_dir = tmp_path / "dl"
        download_dir.mkdir()
        (download_dir / "article.pdf").write_bytes(b"<html>login</html>")
        save_path = tmp_path / "target.pdf"
        save_path.touch()

        assert promote_downloaded_pdf(download_dir, save_path) is None
        assert save_path.read_bytes() == b""

    def test_partial_download_is_ignored(self, tmp_path: Path) -> None:
        """Chrome's in-progress .crdownload files are not taken."""
        download_dir = tmp_path / "dl"
        download_dir.mkdir()
        (download_dir / "article.pdf.crdownload").write_bytes(PDF_BYTES)
        save_path = tmp_path / "target.pdf"

        assert promote_downloaded_pdf(download_dir, save_path) is None
        assert not save_path.exists()


class _FakeOptions:
    """Stands in for uc.ChromeOptions and records the prefs."""

    def __init__(self) -> None:
        """Start with no prefs."""
        self.prefs: Dict[str, Any] = {}

    def add_argument(self, arg: str) -> None:
        """Ignore command-line arguments."""

    def add_experimental_option(self, name: str, value: Dict[str, Any]) -> None:
        """Record the prefs dict."""
        if name == "prefs":
            self.prefs = value


class _FakeIframe:
    """An iframe element whose src points at a PDF."""

    def __init__(self, src: str) -> None:
        """Store the src attribute."""
        self._src = src

    def get_attribute(self, name: str) -> Optional[str]:
        """Return the src attribute."""
        return self._src if name == "src" else None


class _FakeDriver:
    """A Chrome driver showing an article page with a PDF iframe."""

    def __init__(self, options: _FakeOptions, download_bytes: Optional[bytes]) -> None:
        """Keep the download dir from the prefs and what a PDF fetch saves."""
        self.download_dir = Path(options.prefs["download.default_directory"])
        self.download_bytes = download_bytes
        self.title = "Article"
        self.page_source = "<html>article</html>"
        self.current_url = "https://publisher.example/article"

    def set_page_load_timeout(self, timeout: int) -> None:
        """Ignore the timeout."""

    def get(self, url: str) -> None:
        """Navigating to a PDF downloads it, if this driver has bytes to save."""
        if url.endswith(".pdf") and self.download_bytes is not None:
            (self.download_dir / "download.pdf").write_bytes(self.download_bytes)

    def find_elements(self, by: str, value: str) -> List[_FakeIframe]:
        """No links; one PDF iframe."""
        if value == "iframe":
            return [_FakeIframe("https://publisher.example/viewer/article.pdf")]
        return []

    def find_element(self, by: str, value: str) -> None:
        """No meta tags."""
        raise LookupError(value)

    def quit(self) -> None:
        """Nothing to close."""


def _install_fake_chrome(
    monkeypatch: pytest.MonkeyPatch, download_bytes: Optional[bytes]
) -> List[_FakeDriver]:
    """Replace undetected_chromedriver and selenium with fakes.

    Returns:
        A list that receives each driver created.
    """
    drivers: List[_FakeDriver] = []

    def make_chrome(options: _FakeOptions, version_main: Optional[int] = None) -> _FakeDriver:
        driver = _FakeDriver(options, download_bytes)
        drivers.append(driver)
        return driver

    uc = types.ModuleType("undetected_chromedriver")
    uc.ChromeOptions = _FakeOptions  # type: ignore[attr-defined]
    uc.Chrome = make_chrome  # type: ignore[attr-defined]
    by_mod = types.ModuleType("selenium.webdriver.common.by")
    by_mod.By = types.SimpleNamespace(  # type: ignore[attr-defined]
        TAG_NAME="tag name", CSS_SELECTOR="css selector"
    )
    modules = {
        "undetected_chromedriver": uc,
        "selenium": types.ModuleType("selenium"),
        "selenium.webdriver": types.ModuleType("selenium.webdriver"),
        "selenium.webdriver.common": types.ModuleType("selenium.webdriver.common"),
        "selenium.webdriver.common.by": by_mod,
        "selenium.webdriver.support": types.ModuleType("selenium.webdriver.support"),
        "selenium.webdriver.support.ui": types.SimpleNamespace(WebDriverWait=object),
        "selenium.webdriver.support.expected_conditions": types.ModuleType("ec"),
    }
    modules["selenium.webdriver.support"].expected_conditions = modules[  # type: ignore[attr-defined]
        "selenium.webdriver.support.expected_conditions"
    ]
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.setattr(browser_downloader.time, "sleep", lambda seconds: None)
    return drivers


class TestUndetectedChromeDownloadDir:
    """The fallback downloads into its own directory and removes it."""

    def test_other_documents_pdf_is_never_moved(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """With nothing downloaded, a sibling PDF stays where it is."""
        _install_fake_chrome(monkeypatch, download_bytes=None)
        year_dir = tmp_path / "2024"
        year_dir.mkdir()
        save_path = year_dir / "10.1000_target.pdf"
        save_path.touch()
        other = year_dir / "10.1000_other.pdf"
        other.write_bytes(OTHER_PDF_BYTES)
        # The sibling is the newest PDF in the year folder
        old_mtime = other.stat().st_mtime - 60
        os.utime(save_path, (old_mtime, old_mtime))

        result = download_pdf_with_undetected_chrome(
            "https://publisher.example/article", save_path
        )

        assert result["status"] == "failed"
        assert other.read_bytes() == OTHER_PDF_BYTES
        assert save_path.read_bytes() == b""

    def test_own_download_is_promoted_and_temp_dir_removed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The downloaded PDF reaches save_path; the per-call dir is gone."""
        drivers = _install_fake_chrome(monkeypatch, download_bytes=PDF_BYTES)
        year_dir = tmp_path / "2024"
        year_dir.mkdir()
        other = year_dir / "10.1000_other.pdf"
        other.write_bytes(OTHER_PDF_BYTES)
        save_path = year_dir / "10.1000_target.pdf"
        save_path.touch()

        result = download_pdf_with_undetected_chrome(
            "https://publisher.example/article", save_path
        )

        assert result["status"] == "success"
        assert save_path.read_bytes() == PDF_BYTES
        assert other.read_bytes() == OTHER_PDF_BYTES
        download_dir = drivers[0].download_dir
        assert download_dir.parent == year_dir.absolute()
        assert download_dir.name.startswith(CHROME_DOWNLOAD_DIR_PREFIX)
        assert not download_dir.exists()
