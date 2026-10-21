"""Tests that the undetected-Chrome fallback only takes its own downloads (#325).

Chrome downloads into a per-call directory; a sibling PDF in the year folder
must never be moved onto the target path, and the directory is removed on
every exit path.
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
    wait_for_chrome_download,
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

    def test_older_valid_pdf_wins_over_newer_junk(self, tmp_path: Path) -> None:
        """A newer non-PDF does not hide an older valid PDF."""
        download_dir = tmp_path / "dl"
        download_dir.mkdir()
        valid = download_dir / "article.pdf"
        valid.write_bytes(PDF_BYTES)
        old_mtime = valid.stat().st_mtime - 60
        os.utime(valid, (old_mtime, old_mtime))
        (download_dir / "login.pdf").write_bytes(b"<html>login</html>")
        save_path = tmp_path / "target.pdf"
        save_path.touch()

        assert promote_downloaded_pdf(download_dir, save_path) == len(PDF_BYTES)
        assert save_path.read_bytes() == PDF_BYTES

    def test_partial_download_is_ignored(self, tmp_path: Path) -> None:
        """Chrome's in-progress .crdownload files are not taken."""
        download_dir = tmp_path / "dl"
        download_dir.mkdir()
        (download_dir / "article.pdf.crdownload").write_bytes(PDF_BYTES)
        save_path = tmp_path / "target.pdf"

        assert promote_downloaded_pdf(download_dir, save_path) is None
        assert not save_path.exists()


class TestWaitForChromeDownload:
    """wait_for_chrome_download waits for a started download, not a fixed time."""

    def test_waits_until_partial_download_finishes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A download slower than the start window is still waited for (#327)."""
        partial = tmp_path / "article.pdf.crdownload"
        partial.write_bytes(b"%PDF")
        sleeps: List[float] = []

        def fake_sleep(seconds: float) -> None:
            """Chrome finishes the download after 20 polls (10 s)."""
            sleeps.append(seconds)
            if len(sleeps) == 20:
                partial.rename(tmp_path / "article.pdf")

        monkeypatch.setattr(browser_downloader.time, "sleep", fake_sleep)

        assert wait_for_chrome_download(tmp_path, finish_timeout=60) is True
        assert len(sleeps) == 20

    def test_unfinished_download_times_out(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A download still in progress at the finish timeout returns False."""
        (tmp_path / "article.pdf.crdownload").write_bytes(b"%PDF")
        sleeps: List[float] = []
        monkeypatch.setattr(browser_downloader.time, "sleep", sleeps.append)

        assert wait_for_chrome_download(
            tmp_path, finish_timeout=3, poll_interval=1
        ) is False
        assert sum(sleeps) == 3

    def test_no_download_gives_up_after_start_window(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Nothing downloaded: stop after start_timeout, not finish_timeout."""
        sleeps: List[float] = []
        monkeypatch.setattr(browser_downloader.time, "sleep", sleeps.append)

        assert wait_for_chrome_download(
            tmp_path, finish_timeout=60, start_timeout=2, poll_interval=1
        ) is True
        assert sum(sleeps) == 2

    def test_earlier_files_are_ignored(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A rejected earlier download does not end the wait for a new one."""
        old = tmp_path / "login.pdf"
        old.write_bytes(b"<html>login</html>")
        sleeps: List[float] = []
        monkeypatch.setattr(browser_downloader.time, "sleep", sleeps.append)

        assert wait_for_chrome_download(
            tmp_path, finish_timeout=60, already_there=frozenset({old}),
            start_timeout=2, poll_interval=1,
        ) is True
        assert sum(sleeps) == 2


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


class _FakeMeta:
    """A ``<meta name="citation_pdf_url">`` element."""

    def __init__(self, content: str) -> None:
        """Store the content attribute."""
        self._content = content

    def get_attribute(self, name: str) -> Optional[str]:
        """Return the content attribute."""
        return self._content if name == "content" else None


class _FakeIframe:
    """An iframe element whose src points at a PDF."""

    def __init__(self, src: str) -> None:
        """Store the src attribute."""
        self._src = src

    def get_attribute(self, name: str) -> Optional[str]:
        """Return the src attribute."""
        return self._src if name == "src" else None


class _FakeDriver:
    """A Chrome driver showing an article page with a PDF iframe or meta link."""

    def __init__(
        self,
        options: _FakeOptions,
        download_bytes: Optional[bytes],
        meta_pdf_url: Optional[str],
        never_finishes: bool = False,
    ) -> None:
        """Keep the download dir from the prefs and what a PDF fetch saves.

        With ``meta_pdf_url`` the page has a citation_pdf_url meta tag and no
        iframe; otherwise it has a PDF iframe and no meta tag. With
        ``never_finishes`` a PDF fetch only leaves a ``.crdownload`` file.
        """
        self.download_dir = Path(options.prefs["download.default_directory"])
        self.download_bytes = download_bytes
        self.meta_pdf_url = meta_pdf_url
        self.never_finishes = never_finishes
        self.title = "Article"
        self.page_source = "<html>article</html>"
        self.current_url = "https://publisher.example/article"

    def set_page_load_timeout(self, timeout: int) -> None:
        """Ignore the timeout."""

    def get(self, url: str) -> None:
        """Navigating to a PDF downloads it, if this driver has bytes to save."""
        if url.endswith(".pdf") and self.never_finishes:
            (self.download_dir / "download.pdf.crdownload").write_bytes(b"%PDF")
        elif url.endswith(".pdf") and self.download_bytes is not None:
            (self.download_dir / "download.pdf").write_bytes(self.download_bytes)

    def find_elements(self, by: str, value: str) -> List[_FakeIframe]:
        """No links; one PDF iframe unless the page has a meta PDF link."""
        if value == "iframe" and self.meta_pdf_url is None:
            return [_FakeIframe("https://publisher.example/viewer/article.pdf")]
        return []

    def find_element(self, by: str, value: str) -> _FakeMeta:
        """Only the citation_pdf_url meta tag, if this page has one."""
        if self.meta_pdf_url is not None and "citation_pdf_url" in value:
            return _FakeMeta(self.meta_pdf_url)
        raise LookupError(value)

    def execute_script(self, script: str) -> Dict[str, Any]:
        """The in-page fetch fails, so the download path is used."""
        return {"error": "fetch blocked"}

    def quit(self) -> None:
        """Nothing to close."""


def _install_fake_chrome(
    monkeypatch: pytest.MonkeyPatch,
    download_bytes: Optional[bytes],
    meta_pdf_url: Optional[str] = None,
    fail_on_start: bool = False,
    never_finishes: bool = False,
) -> List[_FakeDriver]:
    """Replace undetected_chromedriver and selenium with fakes, and no-op time.sleep.

    Args:
        monkeypatch: pytest monkeypatch fixture.
        download_bytes: What navigating to a PDF URL saves, or None for nothing.
        meta_pdf_url: Give the page a citation_pdf_url meta tag with this URL.
        fail_on_start: Make launching Chrome raise (e.g. a driver mismatch).
        never_finishes: A PDF fetch leaves only an unfinished download.

    Returns:
        A list that receives each driver created.
    """
    drivers: List[_FakeDriver] = []

    def make_chrome(options: _FakeOptions, version_main: Optional[int] = None) -> _FakeDriver:
        """Create a fake driver, or fail like a Chrome/driver version mismatch."""
        if fail_on_start:
            raise RuntimeError("session not created: Chrome version mismatch")
        driver = _FakeDriver(options, download_bytes, meta_pdf_url, never_finishes)
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
        assert not list(year_dir.glob(CHROME_DOWNLOAD_DIR_PREFIX + "*"))

    def test_meta_link_download_never_takes_sibling(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The direct-navigation branch also ignores the year folder."""
        _install_fake_chrome(
            monkeypatch, download_bytes=None,
            meta_pdf_url="https://publisher.example/article.pdf",
        )
        year_dir = tmp_path / "2024"
        year_dir.mkdir()
        save_path = year_dir / "10.1000_target.pdf"
        save_path.touch()
        other = year_dir / "10.1000_other.pdf"
        other.write_bytes(OTHER_PDF_BYTES)
        old_mtime = other.stat().st_mtime - 60
        os.utime(save_path, (old_mtime, old_mtime))

        result = download_pdf_with_undetected_chrome(
            "https://publisher.example/article", save_path
        )

        assert result["status"] == "failed"
        assert other.read_bytes() == OTHER_PDF_BYTES
        assert save_path.read_bytes() == b""

    def test_meta_link_download_is_promoted(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A PDF downloaded by direct navigation reaches save_path."""
        _install_fake_chrome(
            monkeypatch, download_bytes=PDF_BYTES,
            meta_pdf_url="https://publisher.example/article.pdf",
        )
        year_dir = tmp_path / "2024"
        year_dir.mkdir()
        save_path = year_dir / "10.1000_target.pdf"
        save_path.touch()

        result = download_pdf_with_undetected_chrome(
            "https://publisher.example/article", save_path
        )

        assert result["status"] == "success"
        assert save_path.read_bytes() == PDF_BYTES
        assert not list(year_dir.glob(CHROME_DOWNLOAD_DIR_PREFIX + "*"))

    def test_non_pdf_download_is_reported(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A login page saved as .pdf fails with a specific error."""
        _install_fake_chrome(monkeypatch, download_bytes=b"<html>login</html>")
        year_dir = tmp_path / "2024"
        year_dir.mkdir()
        save_path = year_dir / "10.1000_target.pdf"
        save_path.touch()

        result = download_pdf_with_undetected_chrome(
            "https://publisher.example/article", save_path
        )

        assert result["status"] == "failed"
        assert "not a valid PDF" in result["error"]
        assert save_path.read_bytes() == b""
        assert not list(year_dir.glob(CHROME_DOWNLOAD_DIR_PREFIX + "*"))

    def test_chrome_launch_failure_removes_temp_dir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A crash after the dir is created still cleans it up."""
        _install_fake_chrome(monkeypatch, download_bytes=None, fail_on_start=True)
        year_dir = tmp_path / "2024"
        year_dir.mkdir()
        save_path = year_dir / "10.1000_target.pdf"
        save_path.touch()

        result = download_pdf_with_undetected_chrome(
            "https://publisher.example/article", save_path
        )

        assert result["status"] == "failed"
        assert "version mismatch" in result["error"]
        assert save_path.read_bytes() == b""
        assert not list(year_dir.glob(CHROME_DOWNLOAD_DIR_PREFIX + "*"))

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

    def test_unfinished_download_is_reported(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A download that never finishes fails with its own error (#327)."""
        _install_fake_chrome(monkeypatch, download_bytes=None, never_finishes=True)
        year_dir = tmp_path / "2024"
        year_dir.mkdir()
        save_path = year_dir / "10.1000_target.pdf"
        save_path.touch()

        result = download_pdf_with_undetected_chrome(
            "https://publisher.example/article", save_path, timeout=2
        )

        assert result["status"] == "failed"
        assert "did not finish within 2 s" in result["error"]
        assert save_path.read_bytes() == b""
        assert not list(year_dir.glob(CHROME_DOWNLOAD_DIR_PREFIX + "*"))
