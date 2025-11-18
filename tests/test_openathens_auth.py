"""Unit tests for OpenAthens authentication module."""

import json
import pytest
import stat
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock, MagicMock

from bmlibrarian.utils.openathens_auth import (
    OpenAthensConfig,
    OpenAthensAuth,
    login_interactive_sync
)


class TestOpenAthensConfig:
    """Test OpenAthensConfig class."""

    def test_init_with_valid_https_url(self):
        """Test initialization with valid HTTPS URL."""
        config = OpenAthensConfig(
            institution_url='https://example.openathens.net/login'
        )
        assert config.institution_url == 'https://example.openathens.net/login'
        assert config.session_max_age_hours == 24
        assert config.auth_check_interval == 1.0

    def test_init_with_custom_parameters(self):
        """Test initialization with custom parameters."""
        config = OpenAthensConfig(
            institution_url='https://custom.example.edu/auth',
            session_max_age_hours=12,
            auth_check_interval=0.5,
            cloudflare_wait=60,
            headless=False,
            session_cache_ttl=120
        )
        assert config.session_max_age_hours == 12
        assert config.auth_check_interval == 0.5
        assert config.cloudflare_wait == 60
        assert config.headless is False
        assert config.session_cache_ttl == 120

    def test_url_validation_removes_trailing_slash(self):
        """Test that trailing slashes are removed from URLs."""
        config = OpenAthensConfig(
            institution_url='https://example.edu/auth/'
        )
        assert config.institution_url == 'https://example.edu/auth'

    def test_url_validation_requires_https(self):
        """Test that HTTP URLs are rejected."""
        with pytest.raises(ValueError, match="must use HTTPS"):
            OpenAthensConfig(institution_url='http://example.edu/auth')

    def test_url_validation_requires_valid_url(self):
        """Test that invalid URLs are rejected."""
        with pytest.raises(ValueError, match="Invalid URL format"):
            OpenAthensConfig(institution_url='not-a-url')

    def test_url_validation_requires_non_empty(self):
        """Test that empty URLs are rejected."""
        with pytest.raises(ValueError, match="cannot be empty"):
            OpenAthensConfig(institution_url='')

    def test_cookie_patterns_included(self):
        """Test that authentication cookie patterns are configured."""
        config = OpenAthensConfig(
            institution_url='https://example.edu/auth'
        )
        assert len(config.auth_cookie_patterns) > 0
        assert r'openathens.*session' in config.auth_cookie_patterns
        assert r'_saml_.*' in config.auth_cookie_patterns
        assert r'shib.*session' in config.auth_cookie_patterns


class TestOpenAthensAuth:
    """Test OpenAthensAuth class."""

    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return OpenAthensConfig(
            institution_url='https://test.example.edu/openathens',
            session_max_age_hours=24,
            auth_check_interval=0.1,
            session_cache_ttl=5
        )

    @pytest.fixture
    def temp_session_file(self, tmp_path):
        """Create temporary session file path."""
        return tmp_path / 'test_session.json'

    @pytest.fixture
    def auth(self, config, temp_session_file):
        """Create OpenAthensAuth instance."""
        return OpenAthensAuth(config, session_file=temp_session_file)

    def test_init_creates_session_directory(self, config, tmp_path):
        """Test that initialization creates session directory."""
        session_file = tmp_path / 'sessions' / 'test.json'
        auth = OpenAthensAuth(config, session_file=session_file)

        assert session_file.parent.exists()
        assert auth.session_file == session_file

    def test_serialize_deserialize_session_data(self, auth):
        """Test session data serialization/deserialization."""
        original_data = {
            'created_at': datetime.now(),
            'cookies': [
                {'name': 'session_id', 'value': 'abc123'},
                {'name': 'token', 'value': 'xyz789'}
            ],
            'institution_url': 'https://example.edu/auth',
            'user_agent': 'Mozilla/5.0'
        }

        # Serialize
        serialized = auth._serialize_session_data(original_data)

        # Check JSON-serializable
        json_str = json.dumps(serialized)
        assert isinstance(json_str, str)

        # Deserialize
        deserialized = auth._deserialize_session_data(serialized)

        # Verify data integrity
        assert deserialized['created_at'] == original_data['created_at']
        assert deserialized['cookies'] == original_data['cookies']
        assert deserialized['institution_url'] == original_data['institution_url']
        assert deserialized['user_agent'] == original_data['user_agent']

    def test_save_and_load_session(self, auth, temp_session_file):
        """Test saving and loading session data."""
        # Create session data
        auth.session_data = {
            'created_at': datetime.now(),
            'cookies': [{'name': 'test', 'value': 'value'}],
            'institution_url': 'https://test.edu',
            'user_agent': 'TestAgent'
        }

        # Save session
        auth._save_session()

        # Verify file exists
        assert temp_session_file.exists()

        # Verify file permissions (600)
        file_mode = temp_session_file.stat().st_mode
        assert file_mode & stat.S_IRUSR  # Owner read
        assert file_mode & stat.S_IWUSR  # Owner write
        assert not (file_mode & stat.S_IRGRP)  # No group read
        assert not (file_mode & stat.S_IROTH)  # No others read

        # Create new instance and load
        new_auth = OpenAthensAuth(auth.config, session_file=temp_session_file)

        # Verify loaded data
        assert new_auth.session_data is not None
        assert new_auth.session_data['institution_url'] == 'https://test.edu'
        assert len(new_auth.session_data['cookies']) == 1

    def test_load_session_handles_missing_file(self, auth):
        """Test that loading missing session file doesn't crash."""
        # Should not raise exception
        auth._load_session()
        assert auth.session_data is None

    def test_load_session_handles_corrupted_file(self, temp_session_file):
        """Test that corrupted session file is handled gracefully."""
        # Write corrupted JSON
        temp_session_file.write_text('{"invalid json')

        config = OpenAthensConfig(institution_url='https://test.edu')
        auth = OpenAthensAuth(config, session_file=temp_session_file)

        # Should handle error gracefully
        assert auth.session_data is None

    def test_detect_auth_success_with_openathens_cookie(self, auth):
        """Test authentication detection with OpenAthens cookie."""
        cookies = [
            {'name': 'openathens_session_id', 'value': 'abc123'},
            {'name': 'other_cookie', 'value': 'xyz'}
        ]

        assert auth._detect_auth_success(cookies) is True

    def test_detect_auth_success_with_saml_cookie(self, auth):
        """Test authentication detection with SAML cookie."""
        cookies = [
            {'name': '_saml_idp', 'value': 'abc123'}
        ]

        assert auth._detect_auth_success(cookies) is True

    def test_detect_auth_success_with_shibboleth_cookie(self, auth):
        """Test authentication detection with Shibboleth cookie."""
        cookies = [
            {'name': 'shibsession_12345', 'value': 'abc123'}
        ]

        assert auth._detect_auth_success(cookies) is True

    def test_detect_auth_success_no_auth_cookies(self, auth):
        """Test authentication detection with no auth cookies."""
        cookies = [
            {'name': 'regular_cookie', 'value': 'abc'},
            {'name': 'tracking_id', 'value': '123'}
        ]

        assert auth._detect_auth_success(cookies) is False

    def test_is_session_valid_returns_false_when_no_session(self, auth):
        """Test session validation returns False when no session exists."""
        assert auth.is_session_valid() is False

    def test_is_session_valid_returns_true_for_fresh_session(self, auth):
        """Test session validation returns True for fresh session."""
        auth.session_data = {
            'created_at': datetime.now(),
            'cookies': [],
            'institution_url': 'https://test.edu',
            'user_agent': 'Test'
        }

        assert auth.is_session_valid() is True

    def test_is_session_valid_returns_false_for_expired_session(self, auth):
        """Test session validation returns False for expired session."""
        # Create session that's 25 hours old (exceeds 24 hour max)
        auth.session_data = {
            'created_at': datetime.now() - timedelta(hours=25),
            'cookies': [],
            'institution_url': 'https://test.edu',
            'user_agent': 'Test'
        }

        assert auth.is_session_valid() is False

    def test_is_authenticated_uses_cache(self, auth):
        """Test that is_authenticated uses cached results."""
        # Create valid session
        auth.session_data = {
            'created_at': datetime.now(),
            'cookies': [],
            'institution_url': 'https://test.edu',
            'user_agent': 'Test'
        }

        # First call - should cache result
        result1 = auth.is_authenticated()
        assert result1 is True
        assert auth._last_validation_time is not None

        # Invalidate session but shouldn't affect cached result
        auth.session_data['created_at'] = datetime.now() - timedelta(hours=25)

        # Second call within TTL - should use cache
        result2 = auth.is_authenticated()
        assert result2 is True  # Still True from cache

    def test_is_authenticated_cache_expires(self, auth):
        """Test that authentication cache expires after TTL."""
        # Use very short TTL for testing
        auth.config.session_cache_ttl = 0.1  # 100ms

        # Create valid session
        auth.session_data = {
            'created_at': datetime.now(),
            'cookies': [],
            'institution_url': 'https://test.edu',
            'user_agent': 'Test'
        }

        # First call
        result1 = auth.is_authenticated()
        assert result1 is True

        # Wait for cache to expire
        import time
        time.sleep(0.2)

        # Invalidate session
        auth.session_data['created_at'] = datetime.now() - timedelta(hours=25)

        # Should re-validate and return False
        result2 = auth.is_authenticated()
        assert result2 is False

    def test_get_cookies_returns_empty_for_invalid_session(self, auth):
        """Test get_cookies returns empty list for invalid session."""
        assert auth.get_cookies() == []

    def test_get_cookies_returns_cookies_for_valid_session(self, auth):
        """Test get_cookies returns cookies for valid session."""
        cookies = [
            {'name': 'session', 'value': 'abc'},
            {'name': 'token', 'value': '123'}
        ]

        auth.session_data = {
            'created_at': datetime.now(),
            'cookies': cookies,
            'institution_url': 'https://test.edu',
            'user_agent': 'Test'
        }

        assert auth.get_cookies() == cookies

    def test_get_user_agent_returns_none_for_invalid_session(self, auth):
        """Test get_user_agent returns None for invalid session."""
        assert auth.get_user_agent() is None

    def test_get_user_agent_returns_agent_for_valid_session(self, auth):
        """Test get_user_agent returns user agent for valid session."""
        auth.session_data = {
            'created_at': datetime.now(),
            'cookies': [],
            'institution_url': 'https://test.edu',
            'user_agent': 'Mozilla/5.0'
        }

        assert auth.get_user_agent() == 'Mozilla/5.0'

    @patch('bmlibrarian.utils.openathens_auth.requests.head')
    def test_check_network_connectivity_success(self, mock_head, auth):
        """Test network connectivity check with successful connection."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_head.return_value = mock_response

        assert auth._check_network_connectivity() is True
        mock_head.assert_called_once()

    @patch('bmlibrarian.utils.openathens_auth.requests.head')
    def test_check_network_connectivity_failure(self, mock_head, auth):
        """Test network connectivity check with failed connection."""
        mock_head.side_effect = Exception("Network error")

        assert auth._check_network_connectivity() is False

    @patch('bmlibrarian.utils.openathens_auth.requests.head')
    def test_check_network_connectivity_http_error(self, mock_head, auth):
        """Test network connectivity check with HTTP error."""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_head.return_value = mock_response

        assert auth._check_network_connectivity() is False

    def test_clear_session_removes_data(self, auth, temp_session_file):
        """Test clear_session removes session data and file."""
        # Create session
        auth.session_data = {
            'created_at': datetime.now(),
            'cookies': [],
            'institution_url': 'https://test.edu',
            'user_agent': 'Test'
        }
        auth._save_session()

        # Clear session
        auth.clear_session()

        # Verify cleared
        assert auth.session_data is None
        assert auth._last_validation_time is None
        assert not temp_session_file.exists()

    @pytest.mark.asyncio
    async def test_login_interactive_checks_network_first(self, auth):
        """Test that login checks network connectivity first."""
        with patch.object(auth, '_check_network_connectivity', return_value=False):
            result = await auth.login_interactive()
            assert result is False

    @pytest.mark.asyncio
    async def test_cleanup_browser_handles_exceptions(self, auth):
        """Test that browser cleanup handles exceptions gracefully."""
        # Create mock browser that raises exception on close
        auth.browser = AsyncMock()
        auth.browser.close.side_effect = Exception("Close error")
        auth.playwright = AsyncMock()

        # Should not raise exception
        await auth._cleanup_browser()

        # Should still attempt to close
        auth.browser.close.assert_called_once()


class TestLoginInteractiveSync:
    """Test synchronous login wrapper."""

    @patch('bmlibrarian.utils.openathens_auth.asyncio.run')
    def test_login_interactive_sync_success(self, mock_run):
        """Test successful synchronous login."""
        config = OpenAthensConfig(institution_url='https://test.edu')

        # Mock successful login
        mock_run.return_value = True

        auth = login_interactive_sync(config)

        assert auth is not None
        assert isinstance(auth, OpenAthensAuth)

    @patch('bmlibrarian.utils.openathens_auth.asyncio.run')
    def test_login_interactive_sync_failure(self, mock_run):
        """Test failed synchronous login raises exception."""
        config = OpenAthensConfig(institution_url='https://test.edu')

        # Mock failed login
        mock_run.return_value = False

        with pytest.raises(RuntimeError, match="login failed"):
            login_interactive_sync(config)


class TestIntegration:
    """Integration tests for OpenAthens authentication."""

    @pytest.fixture
    def temp_dir(self, tmp_path):
        """Create temporary directory for integration tests."""
        return tmp_path

    def test_full_session_lifecycle(self, temp_dir):
        """Test complete session creation, save, load, and clear lifecycle."""
        session_file = temp_dir / 'integration_test.json'

        # Create configuration
        config = OpenAthensConfig(
            institution_url='https://integration.test.edu/auth',
            session_max_age_hours=1
        )

        # Create auth instance
        auth1 = OpenAthensAuth(config, session_file=session_file)

        # Manually create session (simulating successful login)
        auth1.session_data = {
            'created_at': datetime.now(),
            'cookies': [
                {'name': 'openathens_session', 'value': 'test123'},
                {'name': '_saml_sp', 'value': 'sp456'}
            ],
            'institution_url': config.institution_url,
            'user_agent': 'Mozilla/5.0 (Test Browser)'
        }

        # Save session
        auth1._save_session()

        # Verify authentication
        assert auth1.is_authenticated() is True
        assert len(auth1.get_cookies()) == 2
        assert auth1.get_user_agent() == 'Mozilla/5.0 (Test Browser)'

        # Create new instance and load session
        auth2 = OpenAthensAuth(config, session_file=session_file)

        # Verify session loaded correctly
        assert auth2.is_authenticated() is True
        assert len(auth2.get_cookies()) == 2
        assert auth2.get_user_agent() == 'Mozilla/5.0 (Test Browser)'

        # Clear session
        auth2.clear_session()

        # Verify cleared
        assert auth2.is_authenticated() is False
        assert not session_file.exists()
