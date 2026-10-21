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
        from bmlibrarian.gui.document_card_factory_base import PDFButtonState
        from bmlibrarian.gui.qt.qt_document_card_factory import (
            FindPdfOutcome, FindPdfStatus
        )

        pdf_path = tmp_path / "found.pdf"
        pdf_path.write_bytes(b"%PDF-1.4")
        release = threading.Event()

        def blocking_discovery(card_data, progress_cb):
            release.wait(EVENT_PUMP_TIMEOUT_S)
            return 'RESULT'

        factory, find_button, primary, card = _make_find_pdf_widgets(tmp_path)
        outcome = FindPdfOutcome(FindPdfStatus.ATTACHED, "PDF found", pdf_path)

        try:
            with patch.object(factory, 'discover_and_download', side_effect=blocking_discovery), \
                 patch.object(factory, 'finalize_discovery_result', return_value=outcome), \
                 patch.object(factory, '_update_pdf_filename_in_database',
                              return_value=True) as update_db:
                factory._handle_find_pdf_click(find_button, primary, card)

                # Returned while discovery is still blocked on the worker
                assert not release.is_set()
                assert not find_button.isEnabled()
                assert len(factory._find_pdf_sessions) == 1

                release.set()
                assert _pump_until(lambda: not factory._find_pdf_sessions)
        finally:
            # Never leave a blocked worker behind for later tests
            release.set()
            factory.shutdown()

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

    @staticmethod
    def _make_tab(tmp_path):
        """A search tab (no UI) using a card factory that writes to tmp_path."""
        from bmlibrarian.gui.qt.qt_document_card_factory import QtDocumentCardFactory
        from bmlibrarian.lab.paper_weight_lab.tabs.search_tab import SearchTab

        with patch.object(SearchTab, '_setup_ui'):
            tab = SearchTab()
        tab._card_factory = QtDocumentCardFactory(base_pdf_dir=tmp_path)
        return tab

    def test_find_full_text_does_not_block(self, app, tmp_path):
        """Discovery runs on a worker; a verified PDF is attached and ingested."""
        import threading

        pdf_path = tmp_path / "paper.pdf"
        pdf_path.write_bytes(b"%PDF-1.4")
        release = threading.Event()
        result = _download_result(success=True, file_path=str(pdf_path), verified=True)

        def blocking_discovery(card_data, progress_cb):
            progress_cb('pmc', 'resolving')
            release.wait(EVENT_PUMP_TIMEOUT_S)
            return result

        tab = self._make_tab(tmp_path)
        factory = tab._card_factory
        downloaded = []
        tab.full_text_downloaded.connect(lambda doc_id, path: downloaded.append((doc_id, path)))
        doc = {'id': 7, 'title': 'T', 'doi': '10.1/x', 'year': 2020}

        with patch.object(factory, 'discover_and_download', side_effect=blocking_discovery), \
             patch.object(factory, '_update_pdf_filename_in_database',
                          return_value=True) as update_pdf, \
             patch.object(tab, '_update_tree_item_status'):
            tab._find_full_text_online(doc)
            assert not release.is_set()  # returned while discovery still running
            assert len(tab._discovery_sessions) == 1

            release.set()
            assert _pump_until(lambda: not tab._discovery_sessions)

        update_pdf.assert_called_once()
        assert downloaded == [(7, pdf_path)]
        assert doc['has_pdf'] is True

    def _apply(self, tmp_path, result, decision=None, save_path=None,
               reassign_doc_id=None, full_text_saved=True, finalize_error=None):
        """Run ``_on_full_text_result`` with DB writes and the prompt patched."""
        from contextlib import nullcontext
        from types import SimpleNamespace
        from bmlibrarian.gui.document_card_factory_base import DocumentCardData

        tab = self._make_tab(tmp_path)
        factory = tab._card_factory
        doc = {'id': 7, 'title': 'A paper'}
        card = DocumentCardData(doc_id=7, title='A paper')
        dialog = MagicMock()
        downloaded, selected = [], []
        tab.full_text_downloaded.connect(lambda *a: downloaded.append(a))
        tab.document_selected.connect(selected.append)
        prompt = MagicMock(return_value=(decision, save_path, reassign_doc_id))
        module = 'bmlibrarian.lab.paper_weight_lab.tabs.search_tab'
        with patch('bmlibrarian.discovery.verification_prompt.prompt_gui_verification', prompt), \
             patch('bmlibrarian.discovery.verification_prompt.find_alternative_document',
                   return_value=None), \
             patch.object(factory, '_update_pdf_filename_in_database',
                          return_value=True) as update_pdf, \
             patch.object(factory, '_update_doi_in_database', return_value=True) as update_doi, \
             patch.object(factory, '_update_full_text_in_database',
                          return_value=full_text_saved) as update_full_text, \
             (patch.object(factory, 'finalize_discovery_result', side_effect=finalize_error)
              if finalize_error else nullcontext()), \
             patch.object(tab, '_update_tree_item_status'), \
             patch(f'{module}.is_widget_valid', return_value=True), \
             patch(f'{module}.QTimer'), \
             patch(f'{module}.QMessageBox') as message_box:
            tab._on_full_text_result(doc, card, dialog, result)
        return SimpleNamespace(
            doc=doc, dialog=dialog, downloaded=downloaded, selected=selected,
            prompt=prompt, update_pdf=update_pdf, update_doi=update_doi,
            update_full_text=update_full_text, message_box=message_box,
        )

    def test_verified_pdf_saves_discovered_doi(self, app, tmp_path):
        """The CrossRef DOI is saved only after the PDF passed verification (#312)."""
        from unittest.mock import ANY
        pdf = tmp_path / "ok.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        result = _download_result(success=True, file_path=str(pdf), verified=True,
                                  discovered_doi='10.1/found')
        r = self._apply(tmp_path, result)
        r.prompt.assert_not_called()
        r.update_pdf.assert_called_once_with(7, pdf, ANY)
        r.update_doi.assert_called_once_with(7, '10.1/found')
        assert r.downloaded == [(7, pdf)]
        assert r.selected == []
        assert r.doc['has_pdf'] is True
        assert 'has_full_text' not in r.doc

    def test_mismatched_pdf_is_prompted_and_rejected(self, app, tmp_path):
        """A PDF that failed verification is not attached unless accepted (#312)."""
        from bmlibrarian.discovery.verification_prompt import VerificationDecision
        pdf = tmp_path / "wrong.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        result = _download_result(success=True, file_path=str(pdf), verified=False,
                                  discovered_doi='10.1/wrong')
        r = self._apply(tmp_path, result, VerificationDecision.REJECT)
        r.prompt.assert_called_once()
        r.update_pdf.assert_not_called()
        r.update_doi.assert_not_called()
        assert not pdf.exists()
        assert r.downloaded == []
        assert r.selected == [7]  # proceeds with the abstract
        assert 'has_pdf' not in r.doc
        r.dialog.set_failure.assert_called_once()

    @pytest.mark.parametrize("decision_name, reassign_to", [
        ("REASSIGN", 99), ("SAVE_AS", None), ("RETRY", None),
    ])
    def test_user_choices_give_this_document_nothing(
        self, app, tmp_path, decision_name, reassign_to
    ):
        """Reassign, save-a-copy and retry attach nothing to this document."""
        from bmlibrarian.discovery.verification_prompt import VerificationDecision
        pdf = tmp_path / "other.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        result = _download_result(success=True, file_path=str(pdf), verified=False,
                                  full_text="Other paper text")
        r = self._apply(
            tmp_path, result, VerificationDecision[decision_name],
            save_path=tmp_path / "copy.pdf", reassign_doc_id=reassign_to,
        )
        assert r.downloaded == []
        assert r.selected == [7]
        assert 'has_pdf' not in r.doc and 'has_full_text' not in r.doc
        assert all(c.args[0] != 7 for c in r.update_pdf.call_args_list)
        assert all(c.args[0] != 7 for c in r.update_full_text.call_args_list)
        if reassign_to:
            assert r.update_pdf.call_args.args[0] == reassign_to
        # RETRY's message must not point at a card's Find button
        assert "click Find" not in r.dialog.set_failure.call_args.args[0]

    def test_nothing_found_continues_with_abstract(self, app, tmp_path):
        """A failed discovery selects the document for an abstract-only assessment."""
        result = _download_result(success=False, error_message="No PDF sources found")
        r = self._apply(tmp_path, result)
        assert r.downloaded == []
        assert r.selected == [7]
        r.message_box.warning.assert_called_once()

    def test_finalize_error_continues_with_abstract(self, app, tmp_path):
        """An exception while applying the result is reported, not raised."""
        pdf = tmp_path / "x.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        result = _download_result(success=True, file_path=str(pdf), verified=True)
        r = self._apply(tmp_path, result, finalize_error=RuntimeError("boom"))
        assert r.downloaded == []
        assert r.selected == [7]
        assert "boom" in r.dialog.set_failure.call_args.args[0]

    def test_stored_pmc_full_text_marks_document(self, app, tmp_path):
        """PMC full text that was saved marks the document as having full text."""
        pdf = tmp_path / "pmc.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        result = _download_result(success=True, file_path=str(pdf), verified=True,
                                  full_text="Body text")
        r = self._apply(tmp_path, result)
        r.update_full_text.assert_called_once_with(7, "Body text")
        assert r.doc['has_full_text'] is True

    def test_unsaved_full_text_is_not_claimed(self, app, tmp_path):
        """A failed full-text write is reported and not shown as full text."""
        pdf = tmp_path / "pmc.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        result = _download_result(success=True, file_path=str(pdf), verified=True,
                                  full_text="Body text")
        r = self._apply(tmp_path, result, full_text_saved=False)
        assert 'has_full_text' not in r.doc
        assert r.doc['has_pdf'] is True
        assert "full text could not be saved" in r.dialog.set_success.call_args.args[1]

    def test_manual_upload_ignores_mismatched_full_text(self, app, tmp_path):
        """A manual upload is stored under the factory's PDF directory, and the
        rejected download's full text is not claimed for this document."""
        from bmlibrarian.discovery.verification_prompt import VerificationDecision
        pdf = tmp_path / "wrong.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        upload_dir = tmp_path / "elsewhere"
        upload_dir.mkdir()
        uploaded = upload_dir / "mine.pdf"
        uploaded.write_bytes(b"%PDF-1.4 mine")
        result = _download_result(success=True, file_path=str(pdf), verified=False,
                                  full_text="Wrong paper text")
        r = self._apply(tmp_path, result, VerificationDecision.MANUAL_UPLOAD,
                        save_path=uploaded)
        assert len(r.downloaded) == 1
        stored = r.downloaded[0][1]
        assert stored.is_relative_to(tmp_path) and stored.read_bytes() == b"%PDF-1.4 mine"
        r.update_full_text.assert_not_called()
        assert 'has_full_text' not in r.doc

    def test_unverified_pdf_says_so(self, app, tmp_path):
        """A PDF whose content could not be checked is attached and marked."""
        pdf = tmp_path / "unchecked.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        result = _download_result(success=True, file_path=str(pdf), verified=None)
        r = self._apply(tmp_path, result)
        assert "content not verified" in r.dialog.set_success.call_args.args[1]
        assert r.downloaded == [(7, pdf)]

    def test_closing_dialog_cancels_search(self, app, tmp_path):
        """Closing the progress dialog drops the late result (no prompt, no
        DB writes) and continues with the abstract straight away."""
        import threading
        from bmlibrarian.gui.qt.qt_document_card_factory import PDFDiscoveryProgressDialog

        pdf = tmp_path / "late.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        release = threading.Event()
        result = _download_result(success=True, file_path=str(pdf), verified=False)

        def blocking_discovery(card_data, progress_cb):
            """Block until released, simulating slow discovery."""
            release.wait(EVENT_PUMP_TIMEOUT_S)
            return result

        tab = self._make_tab(tmp_path)
        factory = tab._card_factory
        downloaded, selected = [], []
        tab.full_text_downloaded.connect(lambda *a: downloaded.append(a))
        tab.document_selected.connect(selected.append)
        try:
            with patch.object(factory, 'discover_and_download', side_effect=blocking_discovery), \
                 patch.object(factory, 'finalize_discovery_result') as finalize:
                tab._find_full_text_online({'id': 7, 'title': 'T'})
                tab.findChild(PDFDiscoveryProgressDialog).reject()
                assert selected == [7]

                release.set()
                assert _pump_until(lambda: not tab._discovery_sessions)
                finalize.assert_not_called()
        finally:
            release.set()
            tab._terminate_workers()
        assert downloaded == []
        assert selected == [7]


@pytest.mark.skipif(not HAS_QT, reason="Qt not available")
class TestPaperWeightLabCardFactory:
    """The search tab builds its card factory from the configured PDF directory."""

    @pytest.fixture
    def app(self):
        """Create Qt application for tests."""
        return QApplication.instance() or QApplication([])

    @staticmethod
    def _tab():
        """A search tab without UI or factory."""
        from bmlibrarian.lab.paper_weight_lab.tabs.search_tab import SearchTab
        with patch.object(SearchTab, '_setup_ui'):
            return SearchTab()

    def test_uses_configured_pdf_dir(self, app, tmp_path):
        """``pdf.base_dir`` from config is where the factory stores PDFs."""
        tab = self._tab()
        with patch('bmlibrarian.config.get_config',
                   return_value={'pdf': {'base_dir': str(tmp_path)}}):
            factory = tab._get_card_factory()
        assert factory.base_pdf_dir == tmp_path
        assert tab._get_card_factory() is factory

    def test_bad_config_is_reported(self, app):
        """A non-path ``pdf.base_dir`` is reported and the abstract is used."""
        tab = self._tab()
        selected = []
        tab.document_selected.connect(selected.append)
        module = 'bmlibrarian.lab.paper_weight_lab.tabs.search_tab'
        with patch('bmlibrarian.config.get_config',
                   return_value={'pdf': {'base_dir': None}}), \
             patch(f'{module}.QMessageBox') as message_box:
            tab._find_full_text_online({'id': 7, 'title': 'T'})
        message_box.warning.assert_called_once()
        assert "PDF directory" in message_box.warning.call_args.args[2]
        assert selected == [7]
        assert not tab._discovery_sessions


def _make_find_pdf_widgets(tmp_path):
    """Create a factory, Find button, primary PDF button and card data."""
    from PySide6.QtWidgets import QPushButton
    from bmlibrarian.gui.document_card_factory_base import (
        DocumentCardData, PDFButtonConfig, PDFButtonState
    )
    from bmlibrarian.gui.qt.qt_document_card_factory import (
        PDFButtonWidget, QtDocumentCardFactory
    )

    factory = QtDocumentCardFactory(base_pdf_dir=tmp_path)
    find_button = QPushButton("Find PDF")
    primary = PDFButtonWidget(PDFButtonConfig(state=PDFButtonState.UPLOAD))
    card = DocumentCardData(doc_id=42, title="A paper", doi="10.1/x", year=2021)
    return factory, find_button, primary, card


def _download_result(**overrides):
    """Build a stand-in for discovery's DownloadResult."""
    from types import SimpleNamespace

    fields = dict(
        success=False, file_path=None, verified=None, verification_warnings=[],
        source=None, full_text=None, error_message=None,
    )
    fields.update(overrides)
    return SimpleNamespace(**fields)


class TestFindPDFOutcomes:
    """The Find PDF result handler reports what actually happened."""

    @pytest.fixture
    def app(self):
        """Create QApplication for tests."""
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
        yield app

    def _run(self, app, tmp_path, outcome=None, finalize_error=None, db_ok=True):
        """Run a click whose discovery returns immediately; return widgets."""
        factory, find_button, primary, card = _make_find_pdf_widgets(tmp_path)
        finalize = (
            {'side_effect': finalize_error} if finalize_error
            else {'return_value': outcome}
        )
        with patch.object(factory, 'discover_and_download', return_value='RESULT'), \
             patch.object(factory, 'finalize_discovery_result', **finalize), \
             patch.object(factory, '_update_pdf_filename_in_database',
                          return_value=db_ok) as update_db, \
             patch('bmlibrarian.gui.qt.qt_document_card_factory.QTimer.singleShot'):
            factory._handle_find_pdf_click(find_button, primary, card)
            assert _pump_until(lambda: not factory._find_pdf_sessions)
        return factory, find_button, primary, update_db

    def test_not_found_writes_nothing(self, app, tmp_path):
        """No PDF: no DB write, no cache entry, the reason in the tooltip."""
        from bmlibrarian.gui.qt.qt_document_card_factory import (
            FindPdfOutcome, FindPdfStatus
        )
        outcome = FindPdfOutcome(FindPdfStatus.NOT_FOUND, "Playwright is not installed")
        factory, find_button, _, update_db = self._run(app, tmp_path, outcome)

        update_db.assert_not_called()
        assert 42 not in factory._pdf_path_cache
        assert find_button.text() == "✗ Not Found"
        assert "Playwright" in find_button.toolTip()

    def test_reassigned_is_not_reported_as_not_found(self, app, tmp_path):
        """A PDF reassigned to another document gets its own state."""
        from bmlibrarian.gui.qt.qt_document_card_factory import (
            FindPdfOutcome, FindPdfStatus
        )
        outcome = FindPdfOutcome(FindPdfStatus.REASSIGNED, "PDF attached to document 7")
        factory, find_button, _, update_db = self._run(app, tmp_path, outcome)

        update_db.assert_not_called()
        assert find_button.text() == "↪ Reassigned"
        assert 42 not in factory._pdf_path_cache

    def test_failed_database_write_is_reported(self, app, tmp_path):
        """The PDF is viewable, but the user is told the link was not saved."""
        from bmlibrarian.gui.document_card_factory_base import PDFButtonState
        from bmlibrarian.gui.qt.qt_document_card_factory import (
            FindPdfOutcome, FindPdfStatus
        )
        pdf_path = tmp_path / "found.pdf"
        pdf_path.write_bytes(b"%PDF-1.4")
        outcome = FindPdfOutcome(FindPdfStatus.ATTACHED, "PDF found", pdf_path)
        factory, find_button, primary, update_db = self._run(
            app, tmp_path, outcome, db_ok=False
        )

        update_db.assert_called_once()
        assert find_button.text() == "⚠ Not Saved"
        assert "database" in find_button.toolTip()
        assert primary.config.state == PDFButtonState.VIEW

    def test_finalize_exception_goes_to_error_path(self, app, tmp_path):
        """An exception while finalizing shows an error, never hangs."""
        factory, find_button, primary, update_db = self._run(
            app, tmp_path, finalize_error=RuntimeError("dialog crashed")
        )
        errors = []
        primary.error_occurred.connect(errors.append)

        update_db.assert_not_called()
        assert find_button.text() == "✗ Error"
        assert "dialog crashed" in find_button.toolTip()
        # No duplicate modal via the PDF button's error signal
        assert errors == []


class TestFinalizeDiscoveryResult:
    """``finalize_discovery_result`` maps each verification decision."""

    @pytest.fixture
    def app(self):
        """Create QApplication for tests."""
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
        yield app

    def _finalize(self, tmp_path, result, decision=None, save_path=None, reassign_id=None):
        """Run finalize with the verification prompt patched to ``decision``."""
        factory, _, _, card = _make_find_pdf_widgets(tmp_path)
        prompt = MagicMock(return_value=(decision, save_path, reassign_id))
        with patch('bmlibrarian.discovery.verification_prompt.prompt_gui_verification', prompt), \
             patch('bmlibrarian.discovery.verification_prompt.find_alternative_document',
                   return_value=None), \
             patch.object(factory, '_update_pdf_filename_in_database',
                          return_value=True) as update_pdf, \
             patch.object(factory, '_update_full_text_in_database',
                          return_value=True) as update_text:
            outcome = factory.finalize_discovery_result(card, result)
        return outcome, prompt, update_pdf, update_text

    def test_success_with_full_text(self, app, tmp_path):
        """A verified download is ATTACHED and its full text stored."""
        from bmlibrarian.gui.qt.qt_document_card_factory import FindPdfStatus
        pdf = tmp_path / "ok.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        outcome, prompt, update_pdf, update_text = self._finalize(
            tmp_path, _download_result(success=True, file_path=str(pdf), full_text="body")
        )
        assert outcome.status == FindPdfStatus.ATTACHED
        assert outcome.pdf_path == pdf
        prompt.assert_not_called()
        update_text.assert_called_once_with(42, "body")
        # The caller records pdf_filename for ATTACHED
        update_pdf.assert_not_called()

    @pytest.mark.parametrize("verified, message", [
        (True, "PDF found"),
        (None, "PDF found (content not verified)"),
    ])
    def test_unverified_success_says_so(self, app, tmp_path, verified, message):
        """A PDF that was never checked is not reported as plainly found."""
        pdf = tmp_path / "ok.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        outcome, *_ = self._finalize(
            tmp_path, _download_result(success=True, file_path=str(pdf), verified=verified)
        )
        assert outcome.message == message

    def test_success_but_file_missing(self, app, tmp_path):
        """Reported success with no file on disk is NOT_FOUND."""
        from bmlibrarian.gui.qt.qt_document_card_factory import FindPdfStatus
        outcome, *_ = self._finalize(
            tmp_path, _download_result(success=True, file_path=str(tmp_path / "gone.pdf"))
        )
        assert outcome.status == FindPdfStatus.NOT_FOUND
        assert "missing" in outcome.message

    def test_download_error_message_reaches_user(self, app, tmp_path):
        """The download's own error text is kept, not replaced."""
        from bmlibrarian.gui.qt.qt_document_card_factory import FindPdfStatus
        outcome, *_ = self._finalize(
            tmp_path,
            _download_result(error_message="Browser downloader not available "
                                           "(playwright not installed)")
        )
        assert outcome.status == FindPdfStatus.NOT_FOUND
        assert "playwright" in outcome.message

    def test_verification_failed_without_file(self, app, tmp_path):
        """A failed verification with no file never prompts."""
        from bmlibrarian.gui.qt.qt_document_card_factory import FindPdfStatus
        outcome, prompt, *_ = self._finalize(tmp_path, _download_result(verified=False))
        assert outcome.status == FindPdfStatus.NOT_FOUND
        prompt.assert_not_called()

    def test_reassign_updates_the_other_document_only(self, app, tmp_path):
        """REASSIGN writes the PDF (and full text) to the chosen document."""
        from bmlibrarian.discovery.verification_prompt import VerificationDecision
        from bmlibrarian.gui.qt.qt_document_card_factory import FindPdfStatus
        pdf = tmp_path / "2021" / "wrong.pdf"
        pdf.parent.mkdir()
        pdf.write_bytes(b"%PDF-1.4")
        outcome, _, update_pdf, update_text = self._finalize(
            tmp_path,
            _download_result(verified=False, file_path=str(pdf), full_text="body"),
            decision=VerificationDecision.REASSIGN, reassign_id=7,
        )
        assert outcome.status == FindPdfStatus.REASSIGNED
        assert outcome.pdf_path is None
        assert update_pdf.call_args[0][0] == 7
        update_text.assert_called_once_with(7, "body")

    @pytest.mark.parametrize("decision_name,status_name", [
        ("REJECT", "DECLINED"),
        ("RETRY", "DECLINED"),
        ("SAVE_AS", "SAVED_COPY"),
    ])
    def test_discarding_decisions_delete_the_temp_file(
        self, app, tmp_path, decision_name, status_name
    ):
        """REJECT, RETRY and SAVE_AS remove the downloaded file."""
        from bmlibrarian.discovery.verification_prompt import VerificationDecision
        from bmlibrarian.gui.qt.qt_document_card_factory import FindPdfStatus
        pdf = tmp_path / "wrong.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        outcome, _, update_pdf, _ = self._finalize(
            tmp_path, _download_result(verified=False, file_path=str(pdf)),
            decision=VerificationDecision[decision_name],
            save_path=tmp_path / "copy.pdf",
        )
        assert outcome.status == FindPdfStatus[status_name]
        assert not pdf.exists()
        update_pdf.assert_not_called()

    @pytest.mark.parametrize("verification", [
        {"verified": False},
        {"verified": None, "verification_error": "boom"},  # unchecked (#317)
    ])
    @pytest.mark.parametrize("decision_name, remembered", [
        ("REJECT", True), ("RETRY", True), ("ACCEPT", False),
    ])
    def test_rejected_source_is_remembered(
        self, app, tmp_path, decision_name, remembered, verification
    ):
        """REJECT and RETRY make the next search skip the PDF's source (#315)."""
        from types import SimpleNamespace
        from bmlibrarian.discovery.verification_prompt import VerificationDecision
        pdf = tmp_path / "wrong.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        factory, _, _, card = _make_find_pdf_widgets(tmp_path)
        prompt = MagicMock(return_value=(VerificationDecision[decision_name], None, None))
        result = _download_result(
            file_path=str(pdf), success=True,
            source=SimpleNamespace(url="https://bad.example/a.pdf"), **verification,
        )
        with patch('bmlibrarian.discovery.verification_prompt.prompt_gui_verification', prompt), \
             patch('bmlibrarian.discovery.verification_prompt.find_alternative_document',
                   return_value=None), \
             patch.object(factory, '_update_full_text_in_database', return_value=True):
            factory.finalize_discovery_result(card, result)
        expected = {"https://bad.example/a.pdf"} if remembered else set()
        assert factory._rejected_source_urls.get(42, set()) == expected

    def test_unchecked_pdf_is_prompted(self, app, tmp_path):
        """A PDF whose re-check crashed goes to the prompt marked "unchecked";
        accepting it attaches it as not verified (#317)."""
        from bmlibrarian.discovery.verification_prompt import VerificationDecision
        from bmlibrarian.gui.qt.qt_document_card_factory import FindPdfStatus
        pdf = tmp_path / "x.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        outcome, prompt, *_ = self._finalize(
            tmp_path,
            _download_result(success=True, file_path=str(pdf), verified=None,
                             verification_error="boom", discovered_doi="10.9/found"),
            decision=VerificationDecision.ACCEPT,
        )
        assert prompt.call_args[0][0].unchecked is True
        assert outcome.status == FindPdfStatus.ATTACHED
        assert outcome.message == "PDF found (content not verified)"

    def test_manual_upload_copies_into_year_directory(self, app, tmp_path):
        """MANUAL_UPLOAD copies the chosen file under YYYY/ and attaches it."""
        from bmlibrarian.discovery.verification_prompt import VerificationDecision
        from bmlibrarian.gui.qt.qt_document_card_factory import FindPdfStatus
        wrong = tmp_path / "wrong.pdf"
        wrong.write_bytes(b"%PDF-1.4")
        chosen = tmp_path / "chosen.pdf"
        chosen.write_bytes(b"%PDF-1.4 chosen")
        with patch('bmlibrarian.utils.pdf_manager.PDFManager.get_pdf_path',
                   return_value=tmp_path / "2021" / "chosen.pdf") as get_path:
            (tmp_path / "2021").mkdir()
            outcome, _, update_pdf, _ = self._finalize(
                tmp_path, _download_result(verified=False, file_path=str(wrong)),
                decision=VerificationDecision.MANUAL_UPLOAD, save_path=chosen,
            )
        assert get_path.call_args[0][0]['publication_date'] == "2021"
        assert outcome.status == FindPdfStatus.ATTACHED
        assert outcome.pdf_path == tmp_path / "2021" / "chosen.pdf"
        assert outcome.pdf_path.read_bytes() == b"%PDF-1.4 chosen"
        assert not wrong.exists()
        # Recorded once, by the caller
        update_pdf.assert_not_called()

    def test_manual_upload_never_overwrites_another_pdf(self, app, tmp_path):
        """A taken YYYY/<picked name> (maybe another document's PDF) is left
        alone; the upload goes to the next free name (#319)."""
        from bmlibrarian.discovery.verification_prompt import VerificationDecision
        wrong = tmp_path / "wrong.pdf"
        wrong.write_bytes(b"%PDF-1.4")
        chosen = tmp_path / "main.pdf"
        chosen.write_bytes(b"%PDF-1.4 chosen")
        taken = tmp_path / "2021" / "main.pdf"
        taken.parent.mkdir()
        taken.write_bytes(b"%PDF-1.4 other document")
        with patch('bmlibrarian.utils.pdf_manager.PDFManager.get_pdf_path',
                   return_value=taken):
            outcome, *_ = self._finalize(
                tmp_path, _download_result(verified=False, file_path=str(wrong)),
                decision=VerificationDecision.MANUAL_UPLOAD, save_path=chosen,
            )
        assert outcome.pdf_path == tmp_path / "2021" / "main_1.pdf"
        assert outcome.pdf_path.read_bytes() == b"%PDF-1.4 chosen"
        assert taken.read_bytes() == b"%PDF-1.4 other document"


class TestFindPDFSessionRobustness:
    """Sessions always end the UI's searching state, and stop on shutdown."""

    @pytest.fixture
    def app(self):
        """Create QApplication for tests."""
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
        yield app

    def test_handler_exception_reported_via_failed(self, app):
        """An exception in on_discovered is reported through on_failed."""
        from bmlibrarian.gui.qt.qt_document_card_factory import (
            FindPDFSession, PDFDiscoveryWorker
        )
        failures = []

        def on_discovered(result):
            """Fail like a handler whose widget was deleted."""
            raise RuntimeError("widget gone")

        session = FindPDFSession(
            PDFDiscoveryWorker(lambda cb: None),
            on_progress=lambda *a: None,
            on_discovered=on_discovered,
            on_failed=failures.append,
            on_done=lambda s: None,
        )
        session._handle_discovered('RESULT')
        assert failures == ["widget gone"]

    def test_thread_stopping_silently_is_a_failure(self, app):
        """``finished`` without ``discovered``/``failed`` reports a failure."""
        from bmlibrarian.gui.qt.qt_document_card_factory import (
            FindPDFSession, PDFDiscoveryWorker
        )
        events = []
        session = FindPDFSession(
            PDFDiscoveryWorker(lambda cb: None),
            on_progress=lambda *a: None,
            on_discovered=lambda r: events.append('discovered'),
            on_failed=lambda msg: events.append(('failed', msg)),
            on_done=lambda s: events.append('done'),
        )
        session._handle_thread_finished()
        assert events == [('failed', FindPDFSession.UNEXPECTED_STOP_MESSAGE), 'done']

    def test_shutdown_stops_running_discovery(self, app, tmp_path):
        """shutdown() waits for the worker and drops its late result."""
        import threading

        release = threading.Event()

        def blocking_discovery(card_data, progress_cb):
            """Block until released, simulating slow discovery."""
            release.wait(EVENT_PUMP_TIMEOUT_S)
            return 'RESULT'

        factory, find_button, primary, card = _make_find_pdf_widgets(tmp_path)
        with patch.object(factory, 'discover_and_download', side_effect=blocking_discovery), \
             patch.object(factory, 'finalize_discovery_result') as finalize:
            factory._handle_find_pdf_click(find_button, primary, card)
            session = next(iter(factory._find_pdf_sessions))
            worker = session.worker
            timer = threading.Timer(0.2, release.set)
            timer.start()
            try:
                factory.shutdown()
            finally:
                release.set()
                timer.join()

            assert not worker.isRunning()
            assert not factory._find_pdf_sessions
            _pump_until(lambda: False, timeout_s=0.3)
            finalize.assert_not_called()

    def test_widgets_deleted_mid_discovery(self, app, tmp_path, monkeypatch):
        """Closing the card while discovery runs must not raise; the PDF is
        still recorded for the document."""
        import sys
        import threading
        import shiboken6
        from bmlibrarian.gui.qt.qt_document_card_factory import (
            FindPdfOutcome, FindPdfStatus
        )

        slot_errors = []
        monkeypatch.setattr(sys, 'excepthook', lambda *exc: slot_errors.append(exc))
        pdf_path = tmp_path / "found.pdf"
        pdf_path.write_bytes(b"%PDF-1.4")
        release = threading.Event()

        def blocking_discovery(card_data, progress_cb):
            """Block until released, simulating slow discovery."""
            release.wait(EVENT_PUMP_TIMEOUT_S)
            return 'RESULT'

        factory, find_button, primary, card = _make_find_pdf_widgets(tmp_path)
        outcome = FindPdfOutcome(FindPdfStatus.ATTACHED, "PDF found", pdf_path)
        try:
            with patch.object(factory, 'discover_and_download', side_effect=blocking_discovery), \
                 patch.object(factory, 'finalize_discovery_result', return_value=outcome), \
                 patch.object(factory, '_update_pdf_filename_in_database',
                              return_value=True) as update_db:
                factory._handle_find_pdf_click(find_button, primary, card)
                shiboken6.delete(find_button)
                shiboken6.delete(primary)
                release.set()
                assert _pump_until(lambda: not factory._find_pdf_sessions)
        finally:
            release.set()
            factory.shutdown()

        assert slot_errors == []
        update_db.assert_called_once()
        assert factory._pdf_path_cache[42] == pdf_path


@pytest.mark.skipif(not HAS_QT, reason="Qt not available")
class TestFetchAndDiscoveredDoi:
    """FETCH clicks use the Find PDF flow (#278); a CrossRef DOI is saved only
    after a verified download (#279); closing the dialog cancels."""

    @pytest.fixture
    def app(self):
        """Create QApplication for tests."""
        app = QApplication.instance() or QApplication([])
        yield app

    def test_fetch_click_runs_find_flow_and_becomes_view(self, app, tmp_path):
        """A FETCH click starts no PDFFetchWorker and ends as an enabled View button."""
        from bmlibrarian.gui.document_card_factory_base import (
            DocumentCardData, PDFButtonConfig, PDFButtonState
        )
        from bmlibrarian.gui.qt.qt_document_card_factory import (
            FindPdfOutcome, FindPdfStatus, PDFButtonWidget, QtDocumentCardFactory
        )

        pdf_path = tmp_path / "found.pdf"
        pdf_path.write_bytes(b"%PDF-1.4")
        factory = QtDocumentCardFactory(base_pdf_dir=tmp_path)
        card = DocumentCardData(doc_id=42, title="A paper", pdf_url="https://x/p.pdf")
        button = PDFButtonWidget(PDFButtonConfig(state=PDFButtonState.FETCH, doc_id=42))
        _container = factory._create_button_container(button, card)  # owns button
        outcome = FindPdfOutcome(FindPdfStatus.ATTACHED, "PDF found", pdf_path)

        with patch.object(factory, 'discover_and_download',
                          return_value=_download_result(verified=True)), \
             patch.object(factory, 'finalize_discovery_result', return_value=outcome), \
             patch.object(factory, '_update_pdf_filename_in_database', return_value=True), \
             patch('bmlibrarian.gui.qt.qt_document_card_factory.QTimer.singleShot'):
            button.click()
            assert button._fetch_worker is None
            assert _pump_until(lambda: not factory._find_pdf_sessions)

        assert button.config.state == PDFButtonState.VIEW
        assert button.isEnabled()
        assert "View" in button.text()

    def _fetch_click(self, tmp_path, outcome):
        """Click a FETCH button whose discovery ends in ``outcome``.

        Returns (button, progress dialog, the QTimer.singleShot mock).
        """
        from bmlibrarian.gui.document_card_factory_base import (
            DocumentCardData, PDFButtonConfig, PDFButtonState
        )
        from bmlibrarian.gui.qt.qt_document_card_factory import (
            PDFButtonWidget, PDFDiscoveryProgressDialog, QtDocumentCardFactory
        )

        factory = QtDocumentCardFactory(base_pdf_dir=tmp_path)
        card = DocumentCardData(doc_id=42, title="A paper", pdf_url="https://x/p.pdf")
        button = PDFButtonWidget(PDFButtonConfig(state=PDFButtonState.FETCH, doc_id=42))
        self._container = factory._create_button_container(button, card)  # owns button
        with patch.object(factory, 'discover_and_download',
                          return_value=_download_result()), \
             patch.object(factory, 'finalize_discovery_result', return_value=outcome), \
             patch.object(factory, '_update_pdf_filename_in_database', return_value=True), \
             patch('bmlibrarian.gui.qt.qt_document_card_factory.QTimer.singleShot') as timer:
            original_text = button.text()
            button.click()
            assert _pump_until(lambda: not factory._find_pdf_sessions)
        dialog = button.window().findChild(PDFDiscoveryProgressDialog)
        return button, original_text, dialog, timer

    def test_fetch_click_not_found_resets_to_fetch(self, app, tmp_path):
        """A FETCH click that finds nothing returns to an enabled Fetch button."""
        from bmlibrarian.gui.document_card_factory_base import PDFButtonState
        from bmlibrarian.gui.qt.qt_document_card_factory import (
            FindPdfOutcome, FindPdfStatus
        )

        button, original_text, _, timer = self._fetch_click(
            tmp_path, FindPdfOutcome(FindPdfStatus.NOT_FOUND, "No PDF sources found")
        )
        assert not button.isEnabled()
        for call in timer.call_args_list:  # run the delayed dialog close + button reset
            call.args[1]()

        assert button.config.state == PDFButtonState.FETCH
        assert button.isEnabled()
        assert button.text() == original_text

    def test_closing_dialog_after_success_keeps_view(self, app, tmp_path):
        """Closing the success dialog is not a cancel and keeps the View button."""
        from bmlibrarian.gui.qt.qt_document_card_factory import (
            FindPdfOutcome, FindPdfStatus
        )

        pdf_path = tmp_path / "found.pdf"
        pdf_path.write_bytes(b"%PDF-1.4")
        button, _, dialog, _ = self._fetch_click(
            tmp_path, FindPdfOutcome(FindPdfStatus.ATTACHED, "PDF found", pdf_path)
        )
        dialog.reject()
        assert "View" in button.text()
        assert button.isEnabled()

    def _run_attached(self, tmp_path, result, pdf_saved=True, doi_saved=True):
        """Run a Find PDF click ending ATTACHED; return (DOI-update mock, Find button)."""
        from bmlibrarian.gui.qt.qt_document_card_factory import (
            FindPdfOutcome, FindPdfStatus
        )
        pdf_path = tmp_path / "found.pdf"
        pdf_path.write_bytes(b"%PDF-1.4")
        factory, find_button, primary, card = _make_find_pdf_widgets(tmp_path)
        outcome = FindPdfOutcome(FindPdfStatus.ATTACHED, "PDF found", pdf_path)
        with patch.object(factory, 'discover_and_download', return_value=result), \
             patch.object(factory, 'finalize_discovery_result', return_value=outcome), \
             patch.object(factory, '_update_pdf_filename_in_database',
                          return_value=pdf_saved), \
             patch.object(factory, '_update_doi_in_database',
                          return_value=doi_saved) as update_doi, \
             patch('bmlibrarian.gui.qt.qt_document_card_factory.QTimer.singleShot'):
            factory._handle_find_pdf_click(find_button, primary, card)
            assert _pump_until(lambda: not factory._find_pdf_sessions)
        return update_doi, find_button

    def test_discovered_doi_saved_after_verified_download(self, app, tmp_path):
        """A verified PDF confirms the CrossRef DOI, which is then saved."""
        update_doi, _ = self._run_attached(
            tmp_path, _download_result(verified=True, discovered_doi="10.9/found")
        )
        update_doi.assert_called_once_with(42, "10.9/found")

    @pytest.mark.parametrize("verified", [False, None])
    def test_discovered_doi_not_saved_unless_verified(self, app, tmp_path, verified):
        """A mismatch (accepted by the user) or an unchecked PDF does not
        confirm the CrossRef DOI."""
        update_doi, _ = self._run_attached(
            tmp_path, _download_result(verified=verified, discovered_doi="10.9/found")
        )
        update_doi.assert_not_called()

    def test_discovered_doi_saved_when_pdf_link_unsaved(self, app, tmp_path):
        """The verified PDF confirms the DOI even if its link could not be saved."""
        update_doi, _ = self._run_attached(
            tmp_path, _download_result(verified=True, discovered_doi="10.9/found"),
            pdf_saved=False,
        )
        update_doi.assert_called_once_with(42, "10.9/found")

    def test_failed_doi_save_is_reported(self, app, tmp_path):
        """A DOI that could not be written is named in the button tooltip."""
        _, find_button = self._run_attached(
            tmp_path, _download_result(verified=True, discovered_doi="10.9/found"),
            doi_saved=False,
        )
        assert "10.9/found could not be saved" in find_button.toolTip()

    def _discover(self, tmp_path, download_result, verify=None):
        """Run ``discover_and_download`` with CrossRef finding 10.9/found.

        Returns (result, finder mock, PDFVerifier.verify_pdf mock).
        """
        from types import SimpleNamespace

        factory, _, _, card = _make_find_pdf_widgets(tmp_path)
        card.doi = None
        card.pmid = "123"
        title_result = SimpleNamespace(
            status=SimpleNamespace(value='success'),
            metadata={'discovered_doi': '10.9/found', 'similarity': 0.95},
            error_message=None,
        )
        finder = MagicMock()
        finder.download_for_document.return_value = download_result
        verify = verify or MagicMock()
        with patch('bmlibrarian.config.get_config', return_value={}), \
             patch('bmlibrarian.config.get_openathens_config', return_value={}), \
             patch('bmlibrarian.discovery.resolvers.CrossRefTitleResolver.resolve',
                   return_value=title_result), \
             patch('bmlibrarian.discovery.FullTextFinder', return_value=finder), \
             patch('bmlibrarian.discovery.pdf_verifier.PDFVerifier.verify_pdf', verify), \
             patch.object(factory, '_update_doi_in_database') as update_doi:
            result = factory.discover_and_download(card)
        update_doi.assert_not_called()
        return result, finder, verify

    def test_doi_match_on_discovered_doi_is_rechecked_by_title(self, app, tmp_path):
        """A PDF "verified" only by the CrossRef DOI it was fetched with is
        re-checked against the card's PMID/title; a wrong paper is a mismatch."""
        from types import SimpleNamespace
        from bmlibrarian.discovery import DownloadResult

        downloaded = DownloadResult(
            success=True, file_path=str(tmp_path / "x.pdf"),
            verified=True, verification_match_type='doi',
        )
        verify = MagicMock(return_value=SimpleNamespace(
            verified=False, confidence=0.3, match_type=None,
            warnings=["Could not verify PDF"], title_similarity=0.2,
        ))
        result, _, verify = self._discover(tmp_path, downloaded, verify)

        assert result.verified is False
        assert result.verification_warnings == ["Could not verify PDF"]
        kwargs = verify.call_args.kwargs
        assert 'expected_doi' not in kwargs
        assert kwargs['expected_pmid'] == "123"
        assert kwargs['expected_title'] == "A paper"

    def test_recheck_crash_leaves_pdf_unverified(self, app, tmp_path):
        """If the re-check itself fails, the PDF is unverified, not verified."""
        from bmlibrarian.discovery import DownloadResult

        downloaded = DownloadResult(
            success=True, file_path=str(tmp_path / "x.pdf"),
            verified=True, verification_match_type='doi',
        )
        result, _, _ = self._discover(
            tmp_path, downloaded, MagicMock(side_effect=RuntimeError("boom"))
        )
        assert result.verified is None
        assert result.verification_error == "boom"
        assert any("boom" in w for w in result.verification_warnings)

    def test_rejected_sources_are_excluded_from_next_search(self, app, tmp_path):
        """Sources the user rejected for this document reach the finder as
        ``excluded_urls``; other documents are unaffected (#315)."""
        from bmlibrarian.discovery import DownloadResult

        factory, _, _, card = _make_find_pdf_widgets(tmp_path)
        factory._remember_rejected_source(card.doc_id, "https://bad.example/a.pdf")
        factory._remember_rejected_source(7, "https://other.example/c.pdf")
        finder = MagicMock()
        finder.download_for_document.return_value = DownloadResult(success=False)
        with patch('bmlibrarian.config.get_config', return_value={}), \
             patch('bmlibrarian.config.get_openathens_config', return_value={}), \
             patch('bmlibrarian.discovery.FullTextFinder', return_value=finder):
            factory.discover_and_download(card)
        excluded = finder.download_for_document.call_args.kwargs['excluded_urls']
        assert excluded == {"https://bad.example/a.pdf"}

    def test_reject_then_search_again_skips_source(self, app, tmp_path):
        """Round trip: REJECT in the prompt, then the next Find for the same
        document passes the rejected URL to the finder (#315)."""
        from types import SimpleNamespace
        from bmlibrarian.discovery import DownloadResult
        from bmlibrarian.discovery.verification_prompt import VerificationDecision

        pdf = tmp_path / "wrong.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        factory, _, _, card = _make_find_pdf_widgets(tmp_path)
        prompt = MagicMock(return_value=(VerificationDecision.REJECT, None, None))
        rejected = _download_result(
            verified=False, file_path=str(pdf), success=True,
            source=SimpleNamespace(url="ftp://ftp.ncbi.nlm.nih.gov/pub/pmc/x.pdf"),
        )
        with patch('bmlibrarian.discovery.verification_prompt.prompt_gui_verification', prompt), \
             patch('bmlibrarian.discovery.verification_prompt.find_alternative_document',
                   return_value=None):
            factory.finalize_discovery_result(card, rejected)

        finder = MagicMock()
        finder.download_for_document.return_value = DownloadResult(success=False)
        with patch('bmlibrarian.config.get_config', return_value={}), \
             patch('bmlibrarian.config.get_openathens_config', return_value={}), \
             patch('bmlibrarian.discovery.FullTextFinder', return_value=finder):
            factory.discover_and_download(card)
        excluded = finder.download_for_document.call_args.kwargs['excluded_urls']
        assert excluded == {"ftp://ftp.ncbi.nlm.nih.gov/pub/pmc/x.pdf"}

    def test_title_verified_pdf_is_not_rechecked(self, app, tmp_path):
        """A PDF verified by the card's title needs no second check."""
        from bmlibrarian.discovery import DownloadResult

        downloaded = DownloadResult(
            success=True, file_path=str(tmp_path / "x.pdf"),
            verified=True, verification_match_type='title_exact',
        )
        result, _, verify = self._discover(tmp_path, downloaded)
        assert result.verified is True
        verify.assert_not_called()

    def test_discover_and_download_writes_no_doi(self, app, tmp_path):
        """The worker half carries the discovered DOI instead of writing it."""
        from types import SimpleNamespace
        from bmlibrarian.discovery import DownloadResult

        factory, _, _, card = _make_find_pdf_widgets(tmp_path)
        card.doi = None
        title_result = SimpleNamespace(
            status=SimpleNamespace(value='success'),
            metadata={'discovered_doi': '10.9/found', 'similarity': 0.95},
            error_message=None,
        )
        finder = MagicMock()
        finder.download_for_document.return_value = DownloadResult(success=False)
        with patch('bmlibrarian.config.get_config', return_value={}), \
             patch('bmlibrarian.config.get_openathens_config', return_value={}), \
             patch('bmlibrarian.discovery.resolvers.CrossRefTitleResolver.resolve',
                   return_value=title_result), \
             patch('bmlibrarian.discovery.FullTextFinder', return_value=finder), \
             patch.object(factory, '_update_doi_in_database') as update_doi:
            result = factory.discover_and_download(card)

        update_doi.assert_not_called()
        assert result.discovered_doi == '10.9/found'
        document = finder.download_for_document.call_args.kwargs['document']
        assert document['doi'] == '10.9/found'

    def test_closing_dialog_cancels_search(self, app, tmp_path):
        """Closing the progress dialog drops the late result and re-enables
        the button once the worker has stopped."""
        import threading
        from bmlibrarian.gui.qt.qt_document_card_factory import PDFDiscoveryProgressDialog

        release = threading.Event()

        downloaded = tmp_path / "late.pdf"

        def blocking_discovery(card_data, progress_cb):
            """Block until released, simulating slow discovery."""
            release.wait(EVENT_PUMP_TIMEOUT_S)
            downloaded.write_bytes(b"%PDF-1.4")
            return _download_result(
                success=True, file_path=str(downloaded),
                file_mtime_ns=downloaded.stat().st_mtime_ns,
            )

        factory, find_button, primary, card = _make_find_pdf_widgets(tmp_path)
        try:
            with patch.object(factory, 'discover_and_download', side_effect=blocking_discovery), \
                 patch.object(factory, 'finalize_discovery_result') as finalize:
                factory._handle_find_pdf_click(find_button, primary, card)
                assert not find_button.isEnabled()

                find_button.findChild(PDFDiscoveryProgressDialog).reject()
                # Disabled until the worker stops, so a retry cannot race it
                assert not find_button.isEnabled()

                release.set()
                assert _pump_until(lambda: not factory._find_pdf_sessions)
                finalize.assert_not_called()
                assert find_button.isEnabled()
                assert find_button.text() == "Find PDF"
                # Nothing links the abandoned download, so it is deleted (#314)
                assert not downloaded.exists()
        finally:
            release.set()
            factory.shutdown()


class TestDiscardAbandonedDownload:
    """``discard_abandoned_download`` only deletes files the search created."""

    def test_new_file_is_deleted(self, tmp_path):
        """A PDF the cancelled search created is removed."""
        from bmlibrarian.gui.qt.qt_document_card_factory import discard_abandoned_download
        pdf = tmp_path / "new.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        discard_abandoned_download(_download_result(
            file_path=str(pdf), file_mtime_ns=pdf.stat().st_mtime_ns,
        ))
        assert not pdf.exists()

    @pytest.mark.parametrize("result_fields", [
        {},  # mtime not recorded: origin unknown
        {"file_mtime_ns": "STALE"},  # rewritten since
    ])
    def test_file_not_known_to_be_ours_is_kept(self, tmp_path, result_fields):
        """A file written again after the search (e.g. a second search
        attached it), or of unknown origin, stays."""
        from bmlibrarian.gui.qt.qt_document_card_factory import discard_abandoned_download
        pdf = tmp_path / "old.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        mtime = pdf.stat().st_mtime_ns
        fields = dict(result_fields)
        if "file_mtime_ns" in fields:
            fields["file_mtime_ns"] = mtime if fields["file_mtime_ns"] == "CURRENT" else mtime - 1
        discard_abandoned_download(_download_result(file_path=str(pdf), **fields))
        assert pdf.exists()

    def test_real_result_from_elsewhere_is_kept(self, tmp_path):
        """A real DownloadResult not built by ``download_for_document`` has
        no recorded mtime, so its file is not deleted."""
        from bmlibrarian.discovery import DownloadResult
        from bmlibrarian.gui.qt.qt_document_card_factory import discard_abandoned_download
        pdf = tmp_path / "other.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        discard_abandoned_download(DownloadResult(success=True, file_path=str(pdf)))
        assert pdf.exists()

    def test_no_file_is_fine(self):
        """A result without a file (nothing found) is ignored."""
        from bmlibrarian.gui.qt.qt_document_card_factory import discard_abandoned_download
        discard_abandoned_download(_download_result())
        discard_abandoned_download("RESULT")


class TestDescribeDiscoveryError:
    """User-facing discovery error text."""

    def test_known_error_uses_friendly_wording(self):
        """HTTP 403 gets the standard access-restricted message."""
        from bmlibrarian.gui.qt.qt_document_card_factory import describe_discovery_error
        assert "Access restricted" in describe_discovery_error("HTTP 403 Forbidden")

    def test_unknown_error_keeps_the_reason(self):
        """An unrecognised error keeps its raw text."""
        from bmlibrarian.gui.qt.qt_document_card_factory import describe_discovery_error
        message = describe_discovery_error("playwright not installed")
        assert "playwright not installed" in message


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


class TestUncheckedVerificationDialog:
    """The real verification dialog renders the "could not be checked" case."""

    @pytest.fixture
    def app(self):
        """Create Qt application for tests."""
        return QApplication.instance() or QApplication([])

    def _prompt_data(self, tmp_path, unchecked):
        """Prompt data for a PDF with no extracted identifiers."""
        from bmlibrarian.discovery.verification_prompt import VerificationPromptData
        pdf = tmp_path / "x.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        return VerificationPromptData(
            pdf_path=pdf, expected_doi=None, extracted_doi=None,
            expected_title="Expected", extracted_title=None, unchecked=unchecked,
        )

    @pytest.mark.parametrize("unchecked, heading", [
        (True, "PDF Could Not Be Checked"),
        (False, "PDF Verification Failed"),
    ])
    def test_dialog_heading(self, app, tmp_path, unchecked, heading):
        """The dialog builds and its heading says which case it is."""
        from PySide6.QtWidgets import QLabel
        from bmlibrarian.discovery.verification_dialog import PDFVerificationDialog
        # The real viewer shows a modal for the fake PDF; use the fallback label
        with patch('bmlibrarian.gui.qt.widgets.pdf_viewer.PDFViewerWidget',
                   side_effect=RuntimeError("no viewer in tests")):
            dialog = PDFVerificationDialog(self._prompt_data(tmp_path, unchecked))
        try:
            texts = [label.text() for label in dialog.findChildren(QLabel)]
            assert any(heading in t for t in texts)
        finally:
            dialog.deleteLater()

    @pytest.mark.parametrize("unchecked, summary", [
        (True, "The PDF could not be checked"),
        (False, "Unknown mismatch"),
    ])
    def test_summary_without_details(self, tmp_path, unchecked, summary):
        """With nothing extracted the summary names the case."""
        assert self._prompt_data(tmp_path, unchecked).get_mismatch_summary() == summary
