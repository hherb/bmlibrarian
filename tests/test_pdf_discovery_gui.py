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

        # Valid HTTPS URL
        config = {
            "openathens": {
                "enabled": True,
                "institution_url": "https://myinst.openathens.net"
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
        assert "Fetch" in button.text()

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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
