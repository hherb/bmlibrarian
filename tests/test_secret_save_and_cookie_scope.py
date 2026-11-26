"""Secret-save failures reach the user; browser cookies keep a domain (#472).

Before: a failed OpenAthens session save, CLI session-token save or setup
wizard API-key save was only logged, and the browser fallback injected
cookies without a domain (Selenium then set them on whatever host the PDF
URL named).
"""

import asyncio
import os
import stat
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bmlibrarian.utils.browser_downloader import BrowserDownloader
from bmlibrarian.utils.openathens_auth import (
    OpenAthensAuth,
    OpenAthensConfig,
    scoped_browser_cookies,
)

GOOD = {"name": "ok", "value": "1", "domain": ".publisher.com", "path": "/"}
UNSCOPED = [{"name": "nodomain", "value": "x"}, {"name": "e", "value": "x", "domain": ""}, "junk"]
SESSION_DATA = {"created_at": datetime.now(), "cookies": [GOOD],
                "institution_url": "https://example.openathens.net/login", "user_agent": "UA"}


def make_auth(tmp_path: Path) -> OpenAthensAuth:
    """An OpenAthensAuth whose session file lives in ``tmp_path``."""
    config = OpenAthensConfig(institution_url="https://example.openathens.net/login")
    return OpenAthensAuth(config=config, session_file=tmp_path / "s" / "session.json")


class TestOpenAthensSessionSave:
    """A failed save is reported through the return value and ``session_saved``."""

    def test_save_failure_returns_false(self, tmp_path: Path) -> None:
        auth = make_auth(tmp_path)
        auth.session_data = SESSION_DATA.copy()
        with patch("bmlibrarian.utils.openathens_auth.write_private_text",
                   side_effect=OSError("chmod refused")):
            assert auth._save_session() is False
        assert auth._save_session() is True

    def test_loaded_session_counts_as_saved_and_clear_resets(self, tmp_path: Path) -> None:
        auth = make_auth(tmp_path)
        auth.session_data = SESSION_DATA.copy()
        assert auth._save_session()
        reloaded = make_auth(tmp_path)
        assert reloaded.session_saved is True
        reloaded.clear_session()
        assert reloaded.session_saved is False


class TestScopedBrowserCookies:
    """Only cookies naming their own domain reach a browser."""

    def test_drops_cookies_without_domain(self) -> None:
        assert scoped_browser_cookies([GOOD, *UNSCOPED]) == [GOOD]

    def test_playwright_path_injects_only_scoped_cookies(self, tmp_path: Path) -> None:
        context = MagicMock()
        context.add_cookies = AsyncMock()
        context.add_init_script = AsyncMock(side_effect=RuntimeError("stop here"))
        context.close = AsyncMock()
        downloader = BrowserDownloader()
        downloader.browser = MagicMock()
        downloader.browser.new_context = AsyncMock(return_value=context)

        asyncio.run(downloader.download_pdf("https://x.example/a.pdf", tmp_path / "a.pdf",
                                            cookies=[GOOD, *UNSCOPED]))
        injected = [c for call in context.add_cookies.await_args_list for c in call.args[0]]
        assert injected == [GOOD]


class TestCliSessionTokenSave:
    """--save-session that fails prints a warning instead of a debug log."""

    def test_failed_token_save_is_printed(self, capsys: pytest.CaptureFixture[str]) -> None:
        from bmlibrarian.cli import auth_helper

        args = SimpleNamespace(user="alice", password="pw", session_token=None, save_session=True)
        result = SimpleNamespace(success=True, user_id=1, username="alice", session_token="tok")
        config = MagicMock()
        config.settings_load_failed.return_value = False
        with patch.object(auth_helper, "authenticate_cli", return_value=result), \
             patch("bmlibrarian.config.get_config", return_value=config), \
             patch("bmlibrarian.database.get_db_manager"), \
             patch("atexit.register"), \
             patch.object(auth_helper, "save_session_token", return_value=False):
            ok, error = auth_helper.setup_config_with_auth(args)
        assert (ok, error) == (True, None)
        assert "session could not be saved" in capsys.readouterr().err


try:
    from PySide6.QtWidgets import QApplication

    from bmlibrarian.gui.qt.setup_wizard.api_keys import APIKeysPage
    HAS_QT = True
except ImportError:  # pragma: no cover - Qt missing
    HAS_QT = False


@pytest.mark.skipif(not HAS_QT, reason="Qt not available")
class TestWizardApiKeysSave:
    """The API-keys page saves to a missing .env and stops on a failed save."""

    @pytest.fixture
    def page(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> "APIKeysPage":
        """An API-keys page writing to ``tmp_path/conf/.env``."""
        QApplication.instance() or QApplication([])
        monkeypatch.setenv("BMLIBRARIAN_ENV_FILE", str(tmp_path / "conf" / ".env"))
        # setenv first so teardown restores the original (the page sets os.environ itself)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "unset")
        monkeypatch.delenv("ANTHROPIC_API_KEY")
        page = APIKeysPage(None)
        page._wizard = MagicMock()
        page.anthropic_key_edit.setText("sk-ant-test")
        return page

    def test_missing_env_file_is_created_private(self, page: "APIKeysPage", tmp_path: Path) -> None:
        assert page.validatePage() is True
        env = tmp_path / "conf" / ".env"
        assert "ANTHROPIC_API_KEY=sk-ant-test" in env.read_text()
        if os.name == "posix":
            assert stat.S_IMODE(env.stat().st_mode) == 0o600

    def test_failed_save_blocks_the_page_and_says_why(self, page: "APIKeysPage") -> None:
        with patch("bmlibrarian.gui.qt.setup_wizard.api_keys.write_private_text",
                   side_effect=OSError("disk full")):
            assert page.validatePage() is False
        assert not page.error_frame.isHidden()
        assert "disk full" in page.error_label.text()
        assert "ANTHROPIC_API_KEY" not in os.environ
