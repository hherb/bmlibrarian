"""Tests for CLI authentication helper module.

Tests argument parsing, session management, and config integration.
"""

import argparse
import json
import tempfile
import pytest
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch

from bmlibrarian.cli.auth_helper import (
    CLIAuthResult,
    add_auth_arguments,
    add_config_sync_arguments,
    load_saved_session_token,
    save_session_token,
    clear_saved_session_token,
    authenticate_cli,
    setup_config_with_auth,
    SESSION_TOKEN_FILE,
)


class TestCLIAuthResult:
    """Tests for CLIAuthResult dataclass."""

    def test_successful_result(self) -> None:
        """Test creating a successful auth result."""
        result = CLIAuthResult(
            success=True,
            user_id=1,
            username="testuser",
            session_token="token123"
        )

        assert result.success is True
        assert result.user_id == 1
        assert result.username == "testuser"
        assert result.session_token == "token123"
        assert result.error_message is None

    def test_failed_result(self) -> None:
        """Test creating a failed auth result."""
        result = CLIAuthResult(
            success=False,
            error_message="Invalid credentials"
        )

        assert result.success is False
        assert result.user_id is None
        assert result.username is None
        assert result.session_token is None
        assert result.error_message == "Invalid credentials"


class TestAddAuthArguments:
    """Tests for add_auth_arguments function."""

    def test_adds_user_argument(self) -> None:
        """Test that --user argument is added."""
        parser = argparse.ArgumentParser()
        add_auth_arguments(parser)

        args = parser.parse_args(['--user', 'testuser'])
        assert args.user == 'testuser'

    def test_adds_password_argument(self) -> None:
        """Test that --password argument is added."""
        parser = argparse.ArgumentParser()
        add_auth_arguments(parser)

        args = parser.parse_args(['--password', 'secret'])
        assert args.password == 'secret'

    def test_adds_session_token_argument(self) -> None:
        """Test that --session-token argument is added."""
        parser = argparse.ArgumentParser()
        add_auth_arguments(parser)

        args = parser.parse_args(['--session-token', 'token123'])
        assert args.session_token == 'token123'

    def test_adds_save_session_argument(self) -> None:
        """Test that --save-session argument is added."""
        parser = argparse.ArgumentParser()
        add_auth_arguments(parser)

        args = parser.parse_args(['--save-session'])
        assert args.save_session is True

    def test_adds_logout_argument(self) -> None:
        """Test that --logout argument is added."""
        parser = argparse.ArgumentParser()
        add_auth_arguments(parser)

        args = parser.parse_args(['--logout'])
        assert args.logout is True

    def test_short_form_arguments(self) -> None:
        """Test short form arguments (-u, -p)."""
        parser = argparse.ArgumentParser()
        add_auth_arguments(parser)

        args = parser.parse_args(['-u', 'user', '-p', 'pass'])
        assert args.user == 'user'
        assert args.password == 'pass'

    def test_default_values(self) -> None:
        """Test default argument values."""
        parser = argparse.ArgumentParser()
        add_auth_arguments(parser)

        args = parser.parse_args([])
        assert args.user is None
        assert args.password is None
        assert args.session_token is None
        assert args.save_session is False
        assert args.logout is False


class TestAddConfigSyncArguments:
    """Tests for add_config_sync_arguments function."""

    def test_adds_sync_to_db_argument(self) -> None:
        """Test that --sync-to-db argument is added."""
        parser = argparse.ArgumentParser()
        add_config_sync_arguments(parser)

        args = parser.parse_args(['--sync-to-db'])
        assert args.sync_to_db is True

    def test_adds_sync_from_db_argument(self) -> None:
        """Test that --sync-from-db argument is added."""
        parser = argparse.ArgumentParser()
        add_config_sync_arguments(parser)

        args = parser.parse_args(['--sync-from-db'])
        assert args.sync_from_db is True

    def test_adds_export_config_argument(self) -> None:
        """Test that --export-config argument is added."""
        parser = argparse.ArgumentParser()
        add_config_sync_arguments(parser)

        args = parser.parse_args(['--export-config', 'config.json'])
        assert args.export_config == 'config.json'

    def test_adds_import_config_argument(self) -> None:
        """Test that --import-config argument is added."""
        parser = argparse.ArgumentParser()
        add_config_sync_arguments(parser)

        args = parser.parse_args(['--import-config', 'config.json'])
        assert args.import_config == 'config.json'


class TestSessionTokenPersistence:
    """Tests for session token save/load/clear functions."""

    @pytest.fixture
    def temp_session_file(self, tmp_path: Path, monkeypatch):
        """Create a temporary session token file path."""
        temp_file = tmp_path / ".session_token"
        monkeypatch.setattr(
            'bmlibrarian.cli.auth_helper.SESSION_TOKEN_FILE',
            temp_file
        )
        return temp_file

    def test_save_and_load_session_token(
        self,
        temp_session_file: Path
    ) -> None:
        """Test saving and loading session token."""
        token = "test-token-12345"

        # Save token
        result = save_session_token(token)
        assert result is True
        assert temp_session_file.exists()

        # Load token
        loaded = load_saved_session_token()
        assert loaded == token

    def test_load_nonexistent_token(self, temp_session_file: Path) -> None:
        """Test loading when no token file exists."""
        # Ensure file doesn't exist
        if temp_session_file.exists():
            temp_session_file.unlink()

        loaded = load_saved_session_token()
        assert loaded is None

    def test_clear_session_token(self, temp_session_file: Path) -> None:
        """Test clearing session token."""
        # First save a token
        save_session_token("token-to-clear")
        assert temp_session_file.exists()

        # Clear it
        result = clear_saved_session_token()
        assert result is True
        assert not temp_session_file.exists()

    def test_clear_nonexistent_token(self, temp_session_file: Path) -> None:
        """Test clearing when no token exists."""
        # Ensure file doesn't exist
        if temp_session_file.exists():
            temp_session_file.unlink()

        result = clear_saved_session_token()
        assert result is True  # Should succeed even if file doesn't exist

    def test_saved_token_has_restricted_permissions(
        self,
        temp_session_file: Path
    ) -> None:
        """Test that saved token file has restricted permissions."""
        save_session_token("secure-token")

        # Check permissions (owner read/write only = 0o600)
        mode = temp_session_file.stat().st_mode & 0o777
        assert mode == 0o600


class TestAuthenticateCLI:
    """Tests for authenticate_cli function."""

    @pytest.mark.skip(reason="Requires database connection - integration test")
    def test_authenticate_with_valid_session_token(self) -> None:
        """Test authentication with valid session token."""
        # This test requires database connection - skipped for unit tests
        pass

    @pytest.mark.skip(reason="Requires database connection - integration test")
    def test_authenticate_with_username_password(self) -> None:
        """Test authentication with username and password."""
        # This test requires database connection - skipped for unit tests
        pass

    def test_authenticate_without_credentials(self) -> None:
        """Test authentication with no credentials provided."""
        result = authenticate_cli(prompt_for_password=False)

        assert result.success is False
        assert result.error_message == "No credentials provided"

    def test_authenticate_with_username_but_no_password(self) -> None:
        """Test authentication with username but no password (no prompt)."""
        result = authenticate_cli(
            username="alice",
            prompt_for_password=False
        )

        assert result.success is False
        assert "Password required" in result.error_message


class TestSetupConfigWithAuth:
    """Tests for setup_config_with_auth function."""

    @pytest.fixture
    def mock_args(self) -> argparse.Namespace:
        """Create mock arguments with all auth-related attributes."""
        args = argparse.Namespace()
        args.user = None
        args.password = None
        args.session_token = None
        args.save_session = False
        args.logout = False
        args.sync_to_db = False
        args.sync_from_db = False
        args.export_config = None
        args.import_config = None
        return args

    def test_setup_without_auth(self, mock_args: argparse.Namespace) -> None:
        """Test setup without any authentication."""
        success, error = setup_config_with_auth(mock_args)

        # Should succeed - anonymous usage is fine
        assert success is True
        assert error is None

    def test_logout_clears_session(
        self,
        mock_args: argparse.Namespace,
        tmp_path: Path,
        monkeypatch
    ) -> None:
        """Test that logout clears saved session."""
        # Setup temp session file
        temp_file = tmp_path / ".session_token"
        monkeypatch.setattr(
            'bmlibrarian.cli.auth_helper.SESSION_TOKEN_FILE',
            temp_file
        )

        # Save a session first
        save_session_token("token-to-clear")
        assert temp_file.exists()

        # Trigger logout
        mock_args.logout = True
        success, error = setup_config_with_auth(mock_args)

        assert success is True
        assert not temp_file.exists()

    @pytest.mark.skip(reason="Requires config module integration - integration test")
    def test_export_config(
        self,
        mock_args: argparse.Namespace,
        tmp_path: Path
    ) -> None:
        """Test exporting configuration to JSON."""
        # This test requires config module integration - skipped for unit tests
        pass

    @pytest.mark.skip(reason="Requires config module integration - integration test")
    def test_import_config(
        self,
        mock_args: argparse.Namespace,
        tmp_path: Path
    ) -> None:
        """Test importing configuration from JSON."""
        # This test requires config module integration - skipped for unit tests
        pass

    @pytest.mark.skip(reason="Requires config module integration - integration test")
    def test_sync_to_db_requires_auth(
        self,
        mock_args: argparse.Namespace
    ) -> None:
        """Test that sync-to-db requires authentication."""
        # This test requires config module integration - skipped for unit tests
        pass
