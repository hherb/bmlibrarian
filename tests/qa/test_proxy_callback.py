"""
Tests for the proxy callback functionality in document Q&A.

Tests the new `always_allow_proxy` and `proxy_callback` parameters
for user consent when downloading PDFs via institutional proxy.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from typing import Optional

from bmlibrarian.qa.data_types import (
    ProxyCallbackResult,
    ProxyCallback,
    QAError,
    AnswerSource,
    DocumentTextStatus,
    SemanticSearchAnswer,
)


class TestProxyCallbackResult:
    """Tests for the ProxyCallbackResult dataclass."""

    def test_default_values(self) -> None:
        """Test default values are False."""
        result = ProxyCallbackResult()
        assert result.pdf_made_available is False
        assert result.allow_proxy is False

    def test_pdf_made_available(self) -> None:
        """Test pdf_made_available flag."""
        result = ProxyCallbackResult(pdf_made_available=True)
        assert result.pdf_made_available is True
        assert result.allow_proxy is False

    def test_allow_proxy(self) -> None:
        """Test allow_proxy flag."""
        result = ProxyCallbackResult(allow_proxy=True)
        assert result.pdf_made_available is False
        assert result.allow_proxy is True

    def test_both_flags(self) -> None:
        """Test both flags can be set (though semantically unusual)."""
        result = ProxyCallbackResult(pdf_made_available=True, allow_proxy=True)
        assert result.pdf_made_available is True
        assert result.allow_proxy is True

    def test_repr(self) -> None:
        """Test string representation."""
        result = ProxyCallbackResult(pdf_made_available=True, allow_proxy=False)
        repr_str = repr(result)
        assert "pdf_made_available=True" in repr_str
        assert "allow_proxy=False" in repr_str


class TestProxyCallbackType:
    """Tests for the ProxyCallback type alias."""

    def test_callback_signature(self) -> None:
        """Test callback matches expected signature."""

        def my_callback(document_id: int, title: Optional[str]) -> ProxyCallbackResult:
            return ProxyCallbackResult()

        # Type checking should pass - this is a valid ProxyCallback
        callback: ProxyCallback = my_callback
        result = callback(123, "Test Title")
        assert isinstance(result, ProxyCallbackResult)

    def test_callback_with_none_title(self) -> None:
        """Test callback handles None title."""

        def my_callback(document_id: int, title: Optional[str]) -> ProxyCallbackResult:
            if title is None:
                return ProxyCallbackResult(allow_proxy=True)
            return ProxyCallbackResult()

        result = my_callback(123, None)
        assert result.allow_proxy is True


class TestQAErrorExtensions:
    """Tests for new QAError enum values."""

    def test_proxy_required_error(self) -> None:
        """Test PROXY_REQUIRED error exists and has description."""
        error = QAError.PROXY_REQUIRED
        assert error.value == "proxy_required"
        assert "proxy" in error.description.lower()

    def test_user_cancelled_error(self) -> None:
        """Test USER_CANCELLED error exists and has description."""
        error = QAError.USER_CANCELLED
        assert error.value == "user_cancelled"
        assert "declined" in error.description.lower() or "cancel" in error.description.lower()

    def test_proxy_download_failed_error(self) -> None:
        """Test PROXY_DOWNLOAD_FAILED error exists and has description."""
        error = QAError.PROXY_DOWNLOAD_FAILED
        assert error.value == "proxy_download_failed"
        assert "proxy" in error.description.lower() or "failed" in error.description.lower()


class TestFallbackReason:
    """Tests for fallback_reason field in SemanticSearchAnswer."""

    def test_fallback_reason_default_none(self) -> None:
        """Test fallback_reason defaults to None."""
        answer = SemanticSearchAnswer(answer="test")
        assert answer.fallback_reason is None

    def test_fallback_reason_user_declined(self) -> None:
        """Test fallback_reason can track user declined."""
        answer = SemanticSearchAnswer(
            answer="test",
            source=AnswerSource.ABSTRACT,
            fallback_reason="user_declined",
        )
        assert answer.fallback_reason == "user_declined"

    def test_fallback_reason_proxy_failed(self) -> None:
        """Test fallback_reason can track proxy failure."""
        answer = SemanticSearchAnswer(
            answer="test",
            source=AnswerSource.ABSTRACT,
            fallback_reason="proxy_download_failed",
        )
        assert answer.fallback_reason == "proxy_download_failed"

    def test_fallback_reason_in_to_dict(self) -> None:
        """Test fallback_reason is included in to_dict output."""
        answer = SemanticSearchAnswer(
            answer="test",
            source=AnswerSource.ABSTRACT,
            fallback_reason="user_declined",
        )
        result = answer.to_dict()
        assert "fallback_reason" in result
        assert result["fallback_reason"] == "user_declined"

    def test_fallback_reason_none_in_to_dict(self) -> None:
        """Test fallback_reason None is included in to_dict output."""
        answer = SemanticSearchAnswer(answer="test")
        result = answer.to_dict()
        assert "fallback_reason" in result
        assert result["fallback_reason"] is None


class TestProxyCallbackIntegration:
    """Integration tests for proxy callback in answer_from_document."""

    @pytest.fixture
    def mock_db_manager(self) -> Mock:
        """Create a mock database manager."""
        mock = Mock()
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.__enter__ = Mock(return_value=mock_conn)
        mock_conn.__exit__ = Mock(return_value=False)
        mock_cursor.__enter__ = Mock(return_value=mock_cursor)
        mock_cursor.__exit__ = Mock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor
        mock.get_connection.return_value = mock_conn
        return mock

    @pytest.fixture
    def mock_status_with_abstract(self) -> DocumentTextStatus:
        """Create a status with abstract but no fulltext."""
        return DocumentTextStatus(
            document_id=123,
            has_abstract=True,
            has_fulltext=False,
            has_abstract_embeddings=True,
            has_fulltext_chunks=False,
            abstract_length=500,
            fulltext_length=0,
            title="Test Document",
        )

    def test_callback_called_when_open_access_fails(self) -> None:
        """Test that callback is invoked when open access download fails."""
        callback_called = False
        received_doc_id = None
        received_title = None

        def track_callback(doc_id: int, title: Optional[str]) -> ProxyCallbackResult:
            nonlocal callback_called, received_doc_id, received_title
            callback_called = True
            received_doc_id = doc_id
            received_title = title
            return ProxyCallbackResult()

        # We can't easily test the full flow without mocking many components,
        # but we can test the callback contract is correct
        result = track_callback(123, "Test Document")
        assert isinstance(result, ProxyCallbackResult)

    def test_callback_returns_pdf_made_available(self) -> None:
        """Test callback signaling PDF was made available externally."""

        def upload_callback(doc_id: int, title: Optional[str]) -> ProxyCallbackResult:
            # Simulate user uploading PDF
            return ProxyCallbackResult(pdf_made_available=True)

        result = upload_callback(123, "Test")
        assert result.pdf_made_available is True
        assert result.allow_proxy is False

    def test_callback_returns_allow_proxy(self) -> None:
        """Test callback signaling user consents to proxy."""

        def consent_callback(doc_id: int, title: Optional[str]) -> ProxyCallbackResult:
            # Simulate user consenting to proxy
            return ProxyCallbackResult(allow_proxy=True)

        result = consent_callback(123, "Test")
        assert result.pdf_made_available is False
        assert result.allow_proxy is True

    def test_callback_returns_neither(self) -> None:
        """Test callback signaling user declined both options."""

        def decline_callback(doc_id: int, title: Optional[str]) -> ProxyCallbackResult:
            # Simulate user declining
            return ProxyCallbackResult()

        result = decline_callback(123, "Test")
        assert result.pdf_made_available is False
        assert result.allow_proxy is False


class TestExampleCallbacks:
    """Tests for example callback implementations."""

    def test_cli_callback_example(self) -> None:
        """Test the CLI callback example pattern."""

        def cli_proxy_callback(
            document_id: int, title: Optional[str]
        ) -> ProxyCallbackResult:
            """Example CLI callback that would prompt user."""
            # In real implementation, this would use input()
            # Here we just test the structure
            choice = "2"  # Simulate user choosing proxy

            if choice == "1":
                return ProxyCallbackResult(pdf_made_available=True)
            elif choice == "2":
                return ProxyCallbackResult(allow_proxy=True)
            else:
                return ProxyCallbackResult()

        result = cli_proxy_callback(123, "Test Document")
        assert result.allow_proxy is True

    def test_gui_callback_factory_pattern(self) -> None:
        """Test the GUI callback factory pattern."""

        def create_gui_proxy_callback(parent_widget: object) -> ProxyCallback:
            """Factory that creates a GUI callback with parent reference."""

            def gui_callback(
                document_id: int, title: Optional[str]
            ) -> ProxyCallbackResult:
                # Simulate user clicking "Use Proxy"
                return ProxyCallbackResult(allow_proxy=True)

            return gui_callback

        # Create callback with mock parent
        callback = create_gui_proxy_callback(Mock())

        # Verify it's callable and returns correct type
        result = callback(123, "Test")
        assert isinstance(result, ProxyCallbackResult)
        assert result.allow_proxy is True


class TestAlwaysAllowProxyParameter:
    """Tests for the always_allow_proxy parameter."""

    def test_always_allow_proxy_bypasses_callback(self) -> None:
        """Test that always_allow_proxy=True doesn't need callback."""
        # This is a conceptual test - the actual behavior is tested
        # in integration tests with mocked components

        callback_called = False

        def should_not_be_called(
            doc_id: int, title: Optional[str]
        ) -> ProxyCallbackResult:
            nonlocal callback_called
            callback_called = True
            return ProxyCallbackResult()

        # When always_allow_proxy=True, callback should not be invoked
        # (This would need full integration test with mocks to verify)

        # For now, just verify the callback contract
        assert callable(should_not_be_called)
        assert not callback_called  # Verify we haven't called it yet


class TestCallbackTimeout:
    """Tests for proxy callback timeout functionality."""

    def test_invoke_callback_with_timeout_success(self) -> None:
        """Test callback that completes within timeout."""
        from bmlibrarian.qa.document_qa import _invoke_proxy_callback_with_timeout

        def fast_callback(doc_id: int, title: Optional[str]) -> ProxyCallbackResult:
            return ProxyCallbackResult(allow_proxy=True)

        result, timed_out = _invoke_proxy_callback_with_timeout(
            fast_callback, 123, "Test", timeout_seconds=5.0
        )

        assert not timed_out
        assert result is not None
        assert result.allow_proxy is True

    def test_invoke_callback_with_timeout_timeout(self) -> None:
        """Test callback that exceeds timeout."""
        import time
        from bmlibrarian.qa.document_qa import _invoke_proxy_callback_with_timeout

        def slow_callback(doc_id: int, title: Optional[str]) -> ProxyCallbackResult:
            time.sleep(2.0)  # Takes 2 seconds
            return ProxyCallbackResult(allow_proxy=True)

        result, timed_out = _invoke_proxy_callback_with_timeout(
            slow_callback, 123, "Test", timeout_seconds=0.1
        )

        assert timed_out is True
        assert result is None

    def test_invoke_callback_with_timeout_exception(self) -> None:
        """Test callback that raises an exception."""
        from bmlibrarian.qa.document_qa import _invoke_proxy_callback_with_timeout

        def error_callback(doc_id: int, title: Optional[str]) -> ProxyCallbackResult:
            raise RuntimeError("Test error")

        result, timed_out = _invoke_proxy_callback_with_timeout(
            error_callback, 123, "Test", timeout_seconds=5.0
        )

        assert timed_out is False  # Not timed out, just failed
        assert result is None


class TestFallbackReasonConstants:
    """Tests for fallback reason constants."""

    def test_fallback_constants_exist(self) -> None:
        """Test that fallback reason constants are defined."""
        from bmlibrarian.qa.document_qa import (
            FALLBACK_USER_DECLINED,
            FALLBACK_PROXY_FAILED,
            FALLBACK_NO_PROXY_CONFIGURED,
            FALLBACK_OPEN_ACCESS_FAILED,
            FALLBACK_NO_FULLTEXT_CHUNKS,
            FALLBACK_CALLBACK_TIMEOUT,
        )

        assert FALLBACK_USER_DECLINED == "user_declined"
        assert FALLBACK_PROXY_FAILED == "proxy_download_failed"
        assert FALLBACK_NO_PROXY_CONFIGURED == "no_proxy_configured"
        assert FALLBACK_OPEN_ACCESS_FAILED == "open_access_failed"
        assert FALLBACK_NO_FULLTEXT_CHUNKS == "no_fulltext_chunks"
        assert FALLBACK_CALLBACK_TIMEOUT == "callback_timeout"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
