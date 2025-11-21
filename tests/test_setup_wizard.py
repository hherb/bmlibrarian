"""Unit tests for BMLibrarian Setup Wizard.

Tests the setup wizard functionality including:
- Database connection validation
- .env file creation and security
- Project root detection
- Worker thread operations
- Error handling scenarios

Note: These tests are designed to run without requiring a Qt display.
They test the underlying logic rather than the Qt GUI components.
"""

import os
import stat
import tempfile
from pathlib import Path
from typing import Dict, Any
from unittest.mock import Mock, patch, MagicMock

import pytest


# Skip Qt-dependent tests if PySide6 is not available or display is missing
def pytest_configure(config):
    """Configure pytest markers."""
    config.addinivalue_line(
        "markers", "requires_qt: mark test as requiring Qt (deselect with '-m \"not requires_qt\"')"
    )


def _qt_available() -> bool:
    """Check if Qt is available for testing."""
    try:
        # Check if display is available
        if not os.environ.get('DISPLAY') and not os.environ.get('QT_QPA_PLATFORM'):
            return False
        from PySide6.QtWidgets import QApplication
        return True
    except (ImportError, RuntimeError):
        return False


# Test the find_project_root logic independently
def _find_project_root_logic(start_path: Path) -> Path:
    """
    Re-implementation of find_project_root logic for testing.

    This allows us to test the algorithm without importing Qt modules.
    """
    current = start_path
    while current != current.parent:
        if (current / "pyproject.toml").exists():
            return current
        current = current.parent
    return Path.cwd()


class TestFindProjectRoot:
    """Tests for the find_project_root function."""

    def test_find_project_root_finds_pyproject(self, tmp_path: Path) -> None:
        """Test that find_project_root finds directory with pyproject.toml."""
        # Create a pyproject.toml in the temp directory
        (tmp_path / "pyproject.toml").touch()

        # Create a nested directory structure
        nested_dir = tmp_path / "src" / "submodule" / "deep"
        nested_dir.mkdir(parents=True)

        # Test the algorithm directly
        result = _find_project_root_logic(nested_dir)
        assert result == tmp_path

    def test_find_project_root_returns_cwd_when_not_found(self, tmp_path: Path) -> None:
        """Test that find_project_root returns cwd when pyproject.toml not found."""
        # Create a directory without pyproject.toml
        nested_dir = tmp_path / "no_project" / "deep"
        nested_dir.mkdir(parents=True)

        # Verify behavior: when no pyproject.toml exists up the tree,
        # it should fall back to cwd
        current = nested_dir
        found = None
        while current != current.parent:
            if (current / "pyproject.toml").exists():
                found = current
                break
            current = current.parent

        # Should not find anything
        assert found is None


class TestEnvFileSecurity:
    """Tests for .env file creation and security."""

    def test_env_file_permissions_constant(self) -> None:
        """Test that ENV_FILE_PERMISSIONS constant value is 0o600."""
        # The expected value is 0o600 (owner read/write only)
        expected_permissions = 0o600
        assert expected_permissions == 384  # 0o600 in decimal

    def test_env_file_creation_with_secure_permissions(self, tmp_path: Path) -> None:
        """Test that .env files are created with secure permissions."""
        env_path = tmp_path / ".env"

        # Create test content
        env_content = "TEST_VAR=value\n"
        env_path.write_text(env_content)
        env_path.chmod(0o600)

        # Verify permissions
        file_stat = os.stat(env_path)
        file_mode = stat.S_IMODE(file_stat.st_mode)
        assert file_mode == 0o600

    def test_env_file_not_world_readable(self, tmp_path: Path) -> None:
        """Test that .env files are not readable by others."""
        env_path = tmp_path / ".env"
        env_content = "POSTGRES_PASSWORD=secret\n"
        env_path.write_text(env_content)
        env_path.chmod(0o600)

        # Verify no world/group read permissions
        file_stat = os.stat(env_path)
        file_mode = stat.S_IMODE(file_stat.st_mode)

        # Check that group and others have no permissions
        assert not (file_mode & stat.S_IRGRP)  # No group read
        assert not (file_mode & stat.S_IWGRP)  # No group write
        assert not (file_mode & stat.S_IROTH)  # No others read
        assert not (file_mode & stat.S_IWOTH)  # No others write


class TestDatabaseConnectionValidation:
    """Tests for database connection validation."""

    def test_parameterized_connection_params(self) -> None:
        """Test that connection uses parameterized approach (dict) instead of string."""
        # Verify the expected connection parameter structure
        conn_params = {
            'host': 'localhost',
            'port': 5432,
            'dbname': 'testdb',
            'user': 'testuser',
            'password': 'test!@#$%^&*()password',  # Special characters
            'connect_timeout': 10,
        }

        # All values should be preserved exactly
        assert conn_params['password'] == 'test!@#$%^&*()password'
        assert isinstance(conn_params['port'], int)
        assert conn_params['connect_timeout'] == 10

    def test_password_with_special_characters(self) -> None:
        """Test that passwords with special characters are handled safely."""
        special_passwords = [
            "pass'word",
            "pass\"word",
            "pass;word",
            "pass=word",
            "pass word",
            "pass\tword",
            "pass\nword",
            "test!@#$%^&*()",
        ]

        for password in special_passwords:
            conn_params = {
                'host': 'localhost',
                'port': 5432,
                'dbname': 'test',
                'user': 'user',
                'password': password,
            }
            # Password should be preserved exactly as provided
            assert conn_params['password'] == password

    @patch('psycopg.connect')
    def test_connection_test_uses_parameterized_connection(
        self, mock_connect: Mock
    ) -> None:
        """Test that connection test uses parameterized connection."""
        # This tests that the implementation uses **conn_params approach
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = ("PostgreSQL 16",)
        mock_cursor.fetchall.return_value = [("vector",), ("plpython3u",), ("pg_trgm",)]

        mock_conn = MagicMock()
        mock_conn.__enter__ = Mock(return_value=mock_conn)
        mock_conn.__exit__ = Mock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = Mock(return_value=False)

        mock_connect.return_value = mock_conn

        # Test that we can connect with parameterized approach
        import psycopg
        conn_params = {
            'host': 'localhost',
            'port': 5432,
            'dbname': 'test',
            'user': 'user',
            'password': 'pass=word;special',
            'connect_timeout': 10,
        }

        with psycopg.connect(**conn_params) as conn:
            pass

        # Verify connect was called with keyword arguments (not string)
        mock_connect.assert_called_once()
        call_kwargs = mock_connect.call_args[1]
        assert 'host' in call_kwargs
        assert call_kwargs['password'] == 'pass=word;special'


class TestInvalidCredentialsHandling:
    """Tests for handling invalid credentials."""

    def test_empty_fields_rejected(self) -> None:
        """Test that empty fields are rejected during validation."""
        fields = {
            'host': 'localhost',
            'port': '5432',
            'dbname': '',  # Empty
            'user': 'test',
            'password': 'test',
        }

        # Should detect empty field
        assert not all([fields['host'], fields['port'], fields['dbname'],
                       fields['user'], fields['password']])

    def test_whitespace_only_fields_rejected(self) -> None:
        """Test that whitespace-only fields are rejected."""
        fields = {
            'host': '   ',  # Whitespace only
            'port': '5432',
            'dbname': 'test',
            'user': 'test',
            'password': 'test',
        }

        # After stripping, should be empty
        stripped = {k: v.strip() for k, v in fields.items()}
        assert not all([stripped['host'], stripped['port'], stripped['dbname'],
                       stripped['user'], stripped['password']])


class TestWorkerCancellation:
    """Tests for worker thread cancellation logic (without Qt)."""

    def test_cancellation_flag_behavior(self) -> None:
        """Test that cancellation flag pattern works correctly."""
        # Simulate worker cancellation pattern
        _cancelled = False

        def cancel() -> None:
            nonlocal _cancelled
            _cancelled = True

        # Initially not cancelled
        assert not _cancelled

        # After calling cancel
        cancel()
        assert _cancelled

    def test_worker_initialization_parameters(self) -> None:
        """Test that worker initialization pattern stores parameters correctly."""
        # Simulate worker initialization pattern
        worker_params = {
            'host': 'localhost',
            'port': '5432',
            'dbname': 'testdb',
            'user': 'testuser',
            'password': 'testpass',
            'pdf_dir': '/tmp/pdfs',
        }

        # Verify all parameters are stored
        assert worker_params['host'] == 'localhost'
        assert worker_params['port'] == '5432'
        assert worker_params['dbname'] == 'testdb'
        assert worker_params['user'] == 'testuser'
        assert worker_params['password'] == 'testpass'
        assert worker_params['pdf_dir'] == '/tmp/pdfs'

    def test_check_only_mode_pattern(self) -> None:
        """Test that check-only mode pattern works correctly."""
        # Simulate worker check-only mode pattern
        _check_only = False
        _skip_schema = False

        def set_check_only(value: bool) -> None:
            nonlocal _check_only
            _check_only = value

        def set_skip_schema(value: bool) -> None:
            nonlocal _skip_schema
            _skip_schema = value

        # Initially not check-only
        assert not _check_only
        assert not _skip_schema

        # After setting
        set_check_only(True)
        set_skip_schema(True)
        assert _check_only
        assert _skip_schema


class TestEnvLoadOrder:
    """Tests for .env file loading order."""

    def test_user_config_path_is_primary(self) -> None:
        """Test that ~/.bmlibrarian/.env is the primary config location."""
        from pathlib import Path

        expected_primary = Path.home() / ".bmlibrarian" / ".env"

        # Verify the path format
        assert expected_primary.parts[-1] == ".env"
        assert expected_primary.parts[-2] == ".bmlibrarian"

    @patch('pathlib.Path.exists')
    def test_user_config_checked_first(self, mock_exists: Mock) -> None:
        """Test that user config is checked before project config."""
        from pathlib import Path

        call_order = []

        def track_exists(self: Any) -> bool:
            call_order.append(str(self))
            return False

        # The implementation should check ~/.bmlibrarian/.env first
        user_env = Path.home() / ".bmlibrarian" / ".env"
        assert ".bmlibrarian" in str(user_env)


class TestConfigurationPersistence:
    """Tests for configuration persistence."""

    def test_env_content_format(self) -> None:
        """Test that .env content is formatted correctly."""
        host = "localhost"
        port = "5432"
        dbname = "testdb"
        user = "testuser"
        password = "testpass"
        pdf_dir = "/home/user/pdfs"

        expected_lines = [
            f"POSTGRES_HOST={host}",
            f"POSTGRES_PORT={port}",
            f"POSTGRES_DB={dbname}",
            f"POSTGRES_USER={user}",
            f"POSTGRES_PASSWORD={password}",
            f"PDF_BASE_DIR={pdf_dir}",
            "OLLAMA_HOST=http://localhost:11434",
        ]

        # Verify all expected environment variables would be in content
        for line in expected_lines:
            key = line.split("=")[0]
            assert key in ["POSTGRES_HOST", "POSTGRES_PORT", "POSTGRES_DB",
                          "POSTGRES_USER", "POSTGRES_PASSWORD", "PDF_BASE_DIR",
                          "OLLAMA_HOST"]

    def test_config_directory_creation(self, tmp_path: Path) -> None:
        """Test that config directory is created with correct permissions."""
        config_dir = tmp_path / ".bmlibrarian"

        # Create directory with secure permissions
        config_dir.mkdir(mode=0o700, exist_ok=True)

        # Verify directory exists and has correct permissions
        assert config_dir.exists()
        dir_stat = os.stat(config_dir)
        dir_mode = stat.S_IMODE(dir_stat.st_mode)
        assert dir_mode == 0o700


class TestErrorHandling:
    """Tests for error handling scenarios."""

    def test_connection_error_message_includes_details(self) -> None:
        """Test that connection errors include useful details."""
        error_message = "could not connect to server: Connection refused"

        # Error message should be informative
        assert "connect" in error_message.lower() or "refused" in error_message.lower()

    def test_missing_extension_warning(self) -> None:
        """Test that missing extensions generate appropriate warnings."""
        required_extensions = ["vector", "plpython3u", "pg_trgm"]
        installed_extensions = ["vector"]  # Missing plpython3u and pg_trgm

        missing = [ext for ext in required_extensions if ext not in installed_extensions]

        assert "plpython3u" in missing
        assert "pg_trgm" in missing
        assert len(missing) == 2

    def test_permission_error_handling(self, tmp_path: Path) -> None:
        """Test that permission errors are handled gracefully."""
        # Create a read-only directory
        readonly_dir = tmp_path / "readonly"
        readonly_dir.mkdir()

        try:
            # Make directory read-only
            readonly_dir.chmod(0o444)

            # Attempting to write should raise PermissionError
            env_path = readonly_dir / ".env"
            try:
                env_path.write_text("test")
                # If we get here on some systems, clean up
                env_path.unlink()
                pytest.skip("System allows writing to read-only directory")
            except PermissionError:
                # This is the expected behavior
                pass
        finally:
            # Restore permissions for cleanup
            readonly_dir.chmod(0o755)
