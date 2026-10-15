"""Tests for PDF discovery GUI components and workflows.

Tests the GUI integration of PDF discovery functionality:
- PDF button creation with discoverable identifiers
- Button state transitions
- OpenAthens configuration validation
- Error handling through UI stack
- Thread-safe state management
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock
from typing import Optional


# Test URL validation utilities
class TestOpenAthensUrlValidation:
    """Test OpenAthens URL validation for security."""

    def test_valid_https_url(self):
        """Test that valid HTTPS URLs pass validation."""
        from bmlibrarian.utils.url_validation import validate_openathens_url

        is_valid, normalized, error = validate_openathens_url(
            "https://institution.openathens.net/login"
        )

        assert is_valid is True
        assert normalized == "https://institution.openathens.net/login"
        assert error is None

    def test_rejects_http_url(self):
        """Test that HTTP URLs are rejected for security."""
        from bmlibrarian.utils.url_validation import validate_openathens_url

        is_valid, normalized, error = validate_openathens_url(
            "http://institution.openathens.net/login"
        )

        assert is_valid is False
        assert normalized is None
        assert "HTTPS" in error

    def test_rejects_empty_url(self):
        """Test that empty URLs are rejected."""
        from bmlibrarian.utils.url_validation import validate_openathens_url

        is_valid, normalized, error = validate_openathens_url("")
        assert is_valid is False
        assert "empty" in error.lower()

        is_valid, normalized, error = validate_openathens_url(None)
        assert is_valid is False

    def test_rejects_localhost(self):
        """Test that localhost URLs are rejected (SSRF prevention)."""
        from bmlibrarian.utils.url_validation import validate_openathens_url

        is_valid, normalized, error = validate_openathens_url(
            "https://localhost/login"
        )

        assert is_valid is False
        assert "localhost" in error.lower()

    def test_rejects_private_networks(self):
        """Test that private network IPs are rejected (SSRF prevention)."""
        from bmlibrarian.utils.url_validation import validate_openathens_url

        # 192.168.x.x
        is_valid, _, error = validate_openathens_url("https://192.168.1.1/login")
        assert is_valid is False
        assert "private" in error.lower()

        # 10.x.x.x
        is_valid, _, error = validate_openathens_url("https://10.0.0.1/login")
        assert is_valid is False

        # 172.16-31.x.x
        is_valid, _, error = validate_openathens_url("https://172.16.0.1/login")
        assert is_valid is False

    def test_normalizes_trailing_slash(self):
        """Test that trailing slashes are removed."""
        from bmlibrarian.utils.url_validation import validate_openathens_url

        is_valid, normalized, _ = validate_openathens_url(
            "https://institution.openathens.net/login/"
        )

        assert is_valid is True
        assert normalized == "https://institution.openathens.net/login"

    def test_get_validated_url_from_config(self):
        """Test getting validated URL from config dictionary."""
        from bmlibrarian.utils.url_validation import get_validated_openathens_url

        # Enabled with valid URL
        config = {
            "openathens": {
                "enabled": True,
                "institution_url": "https://myinst.openathens.net"
            }
        }
        url = get_validated_openathens_url(config)
        assert url == "https://myinst.openathens.net"

        # Disabled
        config = {
            "openathens": {
                "enabled": False,
                "institution_url": "https://myinst.openathens.net"
            }
        }
        url = get_validated_openathens_url(config)
        assert url is None

        # Invalid URL
        config = {
            "openathens": {
                "enabled": True,
                "institution_url": "http://insecure.com"
            }
        }
        url = get_validated_openathens_url(config)
        assert url is None


class TestDiscoveryConfigValidation:
    """Test discovery configuration validation."""

    def test_valid_config(self):
        """Test that valid discovery config passes validation."""
        from bmlibrarian.utils.validation import validate_discovery_config

        config = {
            "timeout": 30,
            "browser_timeout": 60000,
            "prefer_open_access": True,
            "use_browser_fallback": True,
            "browser_headless": True
        }

        assert validate_discovery_config(config) is True

    def test_timeout_range_validation(self):
        """Test that timeout must be within valid range (5-120)."""
        from bmlibrarian.utils.validation import validate_discovery_config

        # Too low
        config = {"timeout": 2}
        assert validate_discovery_config(config) is False

        # Too high
        config = {"timeout": 300}
        assert validate_discovery_config(config) is False

        # Valid
        config = {"timeout": 60}
        assert validate_discovery_config(config) is True

    def test_browser_timeout_range_validation(self):
        """Test that browser_timeout must be within valid range (5000-300000)."""
        from bmlibrarian.utils.validation import validate_discovery_config

        # Too low
        config = {"browser_timeout": 1000}
        assert validate_discovery_config(config) is False

        # Too high
        config = {"browser_timeout": 500000}
        assert validate_discovery_config(config) is False

        # Valid
        config = {"browser_timeout": 120000}
        assert validate_discovery_config(config) is True

    def test_boolean_field_validation(self):
        """Test that boolean fields must be actual booleans."""
        from bmlibrarian.utils.validation import validate_discovery_config

        # String instead of bool
        config = {"prefer_open_access": "yes"}
        assert validate_discovery_config(config) is False

        # Integer instead of bool
        config = {"use_browser_fallback": 1}
        assert validate_discovery_config(config) is False


class TestOpenAthensConfigValidation:
    """Test OpenAthens configuration validation."""

    def test_valid_config(self):
        """Test that valid OpenAthens config passes validation."""
        from bmlibrarian.utils.validation import validate_openathens_config

        config = {
            "enabled": True,
            "institution_url": "https://myinst.openathens.net",
            "session_timeout_hours": 24,
            "login_timeout": 300,
            "headless": False
        }

        assert validate_openathens_config(config) is True

    def test_session_timeout_validation(self):
        """Test that session_timeout_hours must be within range (1-168)."""
        from bmlibrarian.utils.validation import validate_openathens_config

        # Too low
        config = {"session_timeout_hours": 0}
        assert validate_openathens_config(config) is False

        # Too high (> 1 week)
        config = {"session_timeout_hours": 200}
        assert validate_openathens_config(config) is False

        # Valid
        config = {"session_timeout_hours": 48}
        assert validate_openathens_config(config) is True

    def test_login_timeout_validation(self):
        """Test that login_timeout must be within range (30-600)."""
        from bmlibrarian.utils.validation import validate_openathens_config

        # Too low
        config = {"login_timeout": 10}
        assert validate_openathens_config(config) is False

        # Too high
        config = {"login_timeout": 1000}
        assert validate_openathens_config(config) is False

        # Valid
        config = {"login_timeout": 180}
        assert validate_openathens_config(config) is True

    def test_url_validation_when_enabled(self):
        """Test that institution_url is validated when OpenAthens is enabled."""
        from bmlibrarian.utils.validation import validate_openathens_config

        # Invalid URL when enabled
        config = {
            "enabled": True,
            "institution_url": "http://insecure.com"
        }
        assert validate_openathens_config(config) is False

        # Invalid URL is OK when disabled
        config = {
            "enabled": False,
            "institution_url": "http://insecure.com"
        }
        assert validate_openathens_config(config) is True


class TestUserFriendlyErrorMessages:
    """Test standardized user-friendly error messages."""

    def test_403_access_restricted(self):
        """Test that HTTP 403 errors produce user-friendly message."""
        from bmlibrarian.utils.error_messages import format_pdf_download_error

        error = Exception("HTTP 403: Forbidden")
        friendly = format_pdf_download_error(error, doc_id=123)

        assert "institutional subscription" in friendly.user_message.lower()
        assert friendly.category.value == "permission"

    def test_404_not_found(self):
        """Test that HTTP 404 errors produce user-friendly message."""
        from bmlibrarian.utils.error_messages import format_pdf_download_error

        error = Exception("HTTP 404: Not Found")
        friendly = format_pdf_download_error(error, doc_id=123)

        assert "not found" in friendly.user_message.lower()
        assert friendly.category.value == "file"

    def test_timeout_error(self):
        """Test that timeout errors produce user-friendly message."""
        from bmlibrarian.utils.error_messages import format_pdf_download_error

        error = Exception("Connection timed out")
        friendly = format_pdf_download_error(error)

        assert "timed out" in friendly.user_message.lower() or "timeout" in friendly.user_message.lower()
        assert friendly.category.value == "timeout"

    def test_network_error(self):
        """Test that network errors produce user-friendly message."""
        from bmlibrarian.utils.error_messages import format_pdf_download_error

        error = Exception("Connection refused")
        friendly = format_pdf_download_error(error)

        assert "network" in friendly.user_message.lower() or "connection" in friendly.user_message.lower()

    def test_ssl_error(self):
        """Test that SSL errors produce user-friendly message."""
        from bmlibrarian.utils.error_messages import format_pdf_download_error

        error = Exception("SSL certificate verification failed")
        friendly = format_pdf_download_error(error)

        assert "certificate" in friendly.user_message.lower() or "secure" in friendly.user_message.lower()

    def test_technical_details_logged(self):
        """Test that technical details are available for logging."""
        from bmlibrarian.utils.error_messages import format_pdf_download_error

        error = Exception("Detailed technical error: connection reset by peer")
        friendly = format_pdf_download_error(error, doc_id=456)

        # Technical message should have more detail than user message
        assert len(friendly.technical_message) >= len(friendly.user_message)
        assert friendly.original_exception is error


class TestFullTextFinderSecureConfig:
    """Test FullTextFinder uses secure configuration."""

    def test_from_config_validates_openathens_url(self):
        """Test that from_config validates OpenAthens URLs."""
        from bmlibrarian.discovery import FullTextFinder

        # Valid HTTPS redirector URL (a bare portal host is deliberately not
        # treated as a proxy by FullTextFinder)
        config = {
            "openathens": {
                "enabled": True,
                "institution_url": "https://go.openathens.net/redirector/myinst.edu"
            }
        }
        finder = FullTextFinder.from_config(config)
        # Check that OpenAthens resolver was created
        assert any('openathens' in str(r).lower() for r in finder.resolvers)

        # Invalid HTTP URL should be rejected
        config = {
            "openathens": {
                "enabled": True,
                "institution_url": "http://insecure.com"  # HTTP not HTTPS
            }
        }
        finder = FullTextFinder.from_config(config)
        # OpenAthens resolver should NOT be created due to validation failure
        assert not any('openathens' in str(r).lower() for r in finder.resolvers)

    def test_from_config_uses_default_timeout(self):
        """Test that from_config uses defaults when not specified."""
        from bmlibrarian.discovery import FullTextFinder

        config = {}  # Empty config
        finder = FullTextFinder.from_config(config)

        # Should use default timeout (30 seconds)
        assert finder.timeout == 30


# Tests that require Qt - skip if not available
try:
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QThread
    HAS_QT = True
except ImportError:
    HAS_QT = False


@pytest.mark.skipif(not HAS_QT, reason="Qt not available")
class TestPDFFetchWorkerThreadSafety:
    """Test PDFFetchWorker thread safety and state management."""

    @pytest.fixture
    def app(self):
        """Create Qt application for tests."""
        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        return app

    def test_worker_runs_in_separate_thread(self, app):
        """Test that PDFFetchWorker runs in background thread."""
        from bmlibrarian.gui.qt.qt_document_card_factory import PDFFetchWorker

        main_thread = QThread.currentThread()
        worker_thread = None

        def handler():
            nonlocal worker_thread
            worker_thread = QThread.currentThread()
            return Path("/tmp/test.pdf")

        worker = PDFFetchWorker(handler)
        worker.start()
        worker.wait(1000)

        assert worker_thread is not None
        assert worker_thread != main_thread

    def test_worker_emits_error_on_failure(self, app):
        """Test that worker emits error signal on failure."""
        from bmlibrarian.gui.qt.qt_document_card_factory import PDFFetchWorker

        error_received = []

        def handler():
            raise RuntimeError("Test error")

        worker = PDFFetchWorker(handler)
        worker.error.connect(lambda msg: error_received.append(msg))
        worker.start()
        worker.wait(1000)
        # Cross-thread signals are queued to the GUI thread: deliver them
        _pump_until(lambda: bool(error_received))

        assert len(error_received) == 1
        # Should be user-friendly message
        assert "download" in error_received[0].lower() or "error" in error_received[0].lower()

    def test_worker_abort_is_thread_safe(self, app):
        """Test that abort operation is thread-safe."""
        from bmlibrarian.gui.qt.qt_document_card_factory import PDFFetchWorker
        import time

        handler_started = []
        handler_completed = []

        def slow_handler():
            handler_started.append(True)
            time.sleep(2)  # Slow operation
            handler_completed.append(True)
            return Path("/tmp/test.pdf")

        worker = PDFFetchWorker(slow_handler)
        worker.start()

        # Wait for handler to start
        time.sleep(0.1)
        if handler_started:
            worker.abort()

        worker.wait(3000)

        # Handler should have started but abort was called
        assert worker._abort is True


@pytest.mark.skipif(not HAS_QT, reason="Qt not available")
class TestPDFButtonStateTransitions:
    """Test PDF button state transitions."""

    @pytest.fixture
    def app(self):
        """Create Qt application for tests."""
        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        return app

    def test_button_creation_with_local_pdf(self, app):
        """Test PDF button shows VIEW when local PDF exists."""
        from bmlibrarian.gui.document_card_factory_base import (
            PDFButtonConfig, PDFButtonState
        )
        from bmlibrarian.gui.qt.qt_document_card_factory import PDFButtonWidget

        pdf_path = Path("/tmp/exists.pdf")
        pdf_path.touch()

        try:
            config = PDFButtonConfig(
                state=PDFButtonState.VIEW,
                pdf_path=pdf_path
            )
            button = PDFButtonWidget(config)

            assert button.config.state == PDFButtonState.VIEW
            assert "View" in button.text()
        finally:
            pdf_path.unlink()

    def test_button_creation_without_pdf(self, app):
        """Test PDF button shows FETCH when URL available but no local PDF."""
        from bmlibrarian.gui.document_card_factory_base import (
            PDFButtonConfig, PDFButtonState
        )
        from bmlibrarian.gui.qt.qt_document_card_factory import PDFButtonWidget

        config = PDFButtonConfig(
            state=PDFButtonState.FETCH,
            pdf_url="https://example.com/paper.pdf"
        )
        button = PDFButtonWidget(config)

        assert button.config.state == PDFButtonState.FETCH
        # FETCH state is labelled "Find" since it runs the discovery workflow
        assert "Find" in button.text()

    def test_button_creation_upload_only(self, app):
        """Test PDF button shows UPLOAD when no PDF and no URL."""
        from bmlibrarian.gui.document_card_factory_base import (
            PDFButtonConfig, PDFButtonState
        )
        from bmlibrarian.gui.qt.qt_document_card_factory import PDFButtonWidget

        config = PDFButtonConfig(
            state=PDFButtonState.UPLOAD
        )
        button = PDFButtonWidget(config)

        assert button.config.state == PDFButtonState.UPLOAD
        assert "Upload" in button.text()


# Generous upper bound for worker threads in tests; they finish in milliseconds.
EVENT_PUMP_TIMEOUT_S = 5.0
EVENT_PUMP_INTERVAL_S = 0.01


def _pump_until(predicate, timeout_s: float = EVENT_PUMP_TIMEOUT_S) -> bool:
    """Process Qt events until predicate() is true or the timeout expires."""
    import time

    deadline = time.monotonic() + timeout_s
    while not predicate() and time.monotonic() < deadline:
        QApplication.processEvents()
        time.sleep(EVENT_PUMP_INTERVAL_S)
    QApplication.processEvents()
    return predicate()


@pytest.mark.skipif(not HAS_QT, reason="Qt not available")
class TestFindPDFRunsOffGuiThread:
    """"Find PDF" discovery must run on a worker thread, outcome on the GUI thread."""

    @pytest.fixture
    def app(self):
        """Create Qt application for tests."""
        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        return app

    def _make_session(self, discovery_fn, calls):
        """Build a FindPDFSession recording which thread each callback ran on."""
        from bmlibrarian.gui.qt.qt_document_card_factory import (
            FindPDFSession, PDFDiscoveryWorker
        )

        def record(kind):
            def callback(*args):
                calls.append((kind, args, QThread.currentThread()))
            return callback

        worker = PDFDiscoveryWorker(discovery_fn)
        return FindPDFSession(
            worker,
            on_progress=record('progress'),
            on_discovered=record('discovered'),
            on_failed=record('failed'),
            on_done=record('done'),
        )

    def test_discovery_runs_on_worker_and_callbacks_on_gui_thread(self, app):
        """Discovery runs off the GUI thread; every callback runs on it."""
        gui_thread = QThread.currentThread()
        discovery_threads = []
        calls = []

        def discovery_fn(progress_cb):
            discovery_threads.append(QThread.currentThread())
            progress_cb('pmc', 'resolving')
            return 'RESULT'

        session = self._make_session(discovery_fn, calls)
        session.start()

        assert _pump_until(lambda: any(c[0] == 'done' for c in calls))
        assert discovery_threads and discovery_threads[0] != gui_thread
        assert [c[0] for c in calls] == ['progress', 'discovered', 'done']
        assert calls[0][1] == ('pmc', 'resolving')
        assert calls[1][1] == ('RESULT',)
        assert all(c[2] == gui_thread for c in calls)

    def test_discovery_exception_reported_via_failed(self, app):
        """An exception in discovery reaches on_failed, not on_discovered."""
        calls = []

        def discovery_fn(progress_cb):
            raise RuntimeError("resolver exploded")

        session = self._make_session(discovery_fn, calls)
        session.start()

        assert _pump_until(lambda: any(c[0] == 'done' for c in calls))
        kinds = [c[0] for c in calls]
        assert kinds == ['failed', 'done']
        assert calls[0][1] == ('resolver exploded',)

    def test_release_deferred_while_result_is_handled(self, app):
        """A thread-finished signal during result handling (e.g. from a modal
        dialog's nested event loop) must not release the session early."""
        from bmlibrarian.gui.qt.qt_document_card_factory import (
            FindPDFSession, PDFDiscoveryWorker
        )

        events = []
        session_ref = []

        def on_discovered(result):
            # Simulate the worker's finished signal arriving mid-handling
            session_ref[0]._handle_thread_finished()
            events.append('handled')

        worker = PDFDiscoveryWorker(lambda cb: None)
        session = FindPDFSession(
            worker,
            on_progress=lambda *a: None,
            on_discovered=on_discovered,
            on_failed=lambda *a: None,
            on_done=lambda s: events.append('done'),
        )
        session_ref.append(session)

        session._handle_discovered('RESULT')

        assert events == ['handled', 'done']

    def test_click_handler_returns_before_discovery_finishes(self, app, tmp_path):
        """The click slot must not block on network discovery."""
        import threading
        from PySide6.QtWidgets import QPushButton
        from bmlibrarian.gui.document_card_factory_base import (
            DocumentCardData, PDFButtonConfig, PDFButtonState
        )
        from bmlibrarian.gui.qt.qt_document_card_factory import (
            PDFButtonWidget, QtDocumentCardFactory
        )

        pdf_path = tmp_path / "found.pdf"
        pdf_path.write_bytes(b"%PDF-1.4")
        release = threading.Event()

        def blocking_discovery(card_data, progress_cb):
            release.wait(EVENT_PUMP_TIMEOUT_S)
            return 'RESULT'

        factory = QtDocumentCardFactory(base_pdf_dir=tmp_path)
        find_button = QPushButton("Find PDF")
        primary = PDFButtonWidget(PDFButtonConfig(state=PDFButtonState.UPLOAD))
        card = DocumentCardData(doc_id=42, title="A paper", doi="10.1/x")

        with patch.object(factory, '_discover_and_download', side_effect=blocking_discovery), \
             patch.object(factory, '_finalize_discovery_result', return_value=pdf_path), \
             patch.object(factory, '_update_pdf_filename_in_database') as update_db:
            factory._handle_find_pdf_click(find_button, primary, card)

            # Returned while discovery is still blocked on the worker
            assert not release.is_set()
            assert not find_button.isEnabled()
            assert len(factory._find_pdf_sessions) == 1

            release.set()
            assert _pump_until(lambda: not factory._find_pdf_sessions)

        assert find_button.text() == "✓ Found"
        assert primary.config.state == PDFButtonState.VIEW
        assert primary.config.pdf_path == pdf_path
        assert factory._pdf_path_cache[42] == pdf_path
        update_db.assert_called_once()


@pytest.mark.skipif(not HAS_QT, reason="Qt not available")
class TestPaperWeightLabFindFullText:
    """paper_weight_lab's "find full text" also runs discovery off the GUI thread."""

    @pytest.fixture
    def app(self):
        """Create Qt application for tests."""
        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        return app

    def test_find_full_text_does_not_block(self, app, tmp_path):
        import threading
        from types import SimpleNamespace
        from bmlibrarian.lab.paper_weight_lab.tabs.search_tab import SearchTab

        pdf_path = tmp_path / "paper.pdf"
        pdf_path.write_bytes(b"%PDF-1.4")
        release = threading.Event()
        result = SimpleNamespace(full_text=None, file_path=str(pdf_path), error_message=None)

        def blocking_discovery(doc_data, progress_cb):
            progress_cb('pmc', 'resolving')
            release.wait(EVENT_PUMP_TIMEOUT_S)
            return result

        with patch.object(SearchTab, '_setup_ui'):
            tab = SearchTab()
        downloaded = []
        tab.full_text_downloaded.connect(lambda doc_id, path: downloaded.append((doc_id, path)))
        doc = {'id': 7, 'title': 'T', 'doi': '10.1/x', 'year': 2020}

        with patch.object(tab, '_discover_full_text', side_effect=blocking_discovery), \
             patch.object(tab, '_update_pdf_in_database') as update_pdf, \
             patch.object(tab, '_update_tree_item_status'):
            tab._find_full_text_online(doc)
            assert not release.is_set()  # returned while discovery still running
            assert len(tab._discovery_sessions) == 1

            release.set()
            assert _pump_until(lambda: not tab._discovery_sessions)

        update_pdf.assert_called_once()
        assert downloaded == [(7, pdf_path)]
        assert doc['has_pdf'] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
