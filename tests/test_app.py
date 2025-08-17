"""Unit tests for the app module."""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from bmlibrarian.app import get_database_connection, initialize_app


class TestInitializeApp:
    """Test cases for initialize_app function."""

    def setup_method(self):
        """Set up test environment."""
        # Store original environment variables
        self.original_env = {}
        env_vars = ['POSTGRES_HOST', 'POSTGRES_PORT', 'POSTGRES_USER', 
                   'POSTGRES_PASSWORD', 'POSTGRES_DB']
        for var in env_vars:
            self.original_env[var] = os.environ.get(var)

    def teardown_method(self):
        """Clean up test environment."""
        # Restore original environment variables
        for var, value in self.original_env.items():
            if value is None:
                os.environ.pop(var, None)
            else:
                os.environ[var] = value

    @patch.dict(os.environ, {
        'POSTGRES_HOST': 'testhost',
        'POSTGRES_PORT': '5433',
        'POSTGRES_USER': 'testuser',
        'POSTGRES_PASSWORD': 'testpass',
        'POSTGRES_DB': 'testdb'
    })
    @patch('bmlibrarian.app.MigrationManager')
    def test_initialize_app_success(self, mock_migration_manager):
        """Test successful app initialization."""
        mock_manager_instance = MagicMock()
        mock_manager_instance.apply_pending_migrations.return_value = 2
        mock_migration_manager.return_value = mock_manager_instance
        
        with patch('builtins.print') as mock_print:
            initialize_app()
        
        # Verify MigrationManager was created with correct config
        mock_migration_manager.assert_called_once_with(
            host='testhost',
            port='5433',
            user='testuser',
            password='testpass',
            database='testdb'
        )
        
        # Verify migrations were applied
        expected_path = Path.home() / ".bmlibrarian" / "migrations"
        mock_manager_instance.apply_pending_migrations.assert_called_once_with(expected_path)
        
        # Verify success message
        mock_print.assert_called_once_with("Applied 2 pending migration(s).")

    @patch.dict(os.environ, {
        'POSTGRES_USER': 'testuser',
        'POSTGRES_PASSWORD': 'testpass'
    }, clear=True)
    @patch('bmlibrarian.app.MigrationManager')
    def test_initialize_app_default_values(self, mock_migration_manager):
        """Test app initialization with default values."""
        mock_manager_instance = MagicMock()
        mock_manager_instance.apply_pending_migrations.return_value = 0
        mock_migration_manager.return_value = mock_manager_instance
        
        initialize_app()
        
        # Verify default values were used
        mock_migration_manager.assert_called_once_with(
            host='localhost',  # default
            port='5432',       # default
            user='testuser',
            password='testpass',
            database='bmlibrarian_dev'  # default
        )

    @patch.dict(os.environ, {
        'POSTGRES_PASSWORD': 'testpass'
    }, clear=True)
    def test_initialize_app_missing_user(self):
        """Test app initialization with missing user."""
        with pytest.raises(ValueError) as exc_info:
            initialize_app()
        
        assert "Database credentials not configured" in str(exc_info.value)
        assert "POSTGRES_USER and POSTGRES_PASSWORD" in str(exc_info.value)

    @patch.dict(os.environ, {
        'POSTGRES_USER': 'testuser'
    }, clear=True)
    def test_initialize_app_missing_password(self):
        """Test app initialization with missing password."""
        with pytest.raises(ValueError) as exc_info:
            initialize_app()
        
        assert "Database credentials not configured" in str(exc_info.value)

    @patch.dict(os.environ, {}, clear=True)
    def test_initialize_app_missing_both_credentials(self):
        """Test app initialization with missing user and password."""
        with pytest.raises(ValueError) as exc_info:
            initialize_app()
        
        assert "Database credentials not configured" in str(exc_info.value)

    @patch.dict(os.environ, {
        'POSTGRES_USER': 'testuser',
        'POSTGRES_PASSWORD': 'testpass'
    })
    @patch('bmlibrarian.app.MigrationManager')
    def test_initialize_app_no_migrations_applied(self, mock_migration_manager):
        """Test app initialization when no migrations are applied."""
        mock_manager_instance = MagicMock()
        mock_manager_instance.apply_pending_migrations.return_value = 0
        mock_migration_manager.return_value = mock_manager_instance
        
        with patch('builtins.print') as mock_print:
            initialize_app()
        
        # Should not print anything when no migrations applied
        mock_print.assert_not_called()

    @patch.dict(os.environ, {
        'POSTGRES_USER': 'testuser',
        'POSTGRES_PASSWORD': 'testpass'
    })
    @patch('bmlibrarian.app.MigrationManager')
    def test_initialize_app_migration_failure(self, mock_migration_manager):
        """Test app initialization when migration fails."""
        mock_manager_instance = MagicMock()
        mock_manager_instance.apply_pending_migrations.side_effect = Exception("Migration failed")
        mock_migration_manager.return_value = mock_manager_instance
        
        with patch('builtins.print') as mock_print:
            initialize_app()
        
        # Should print warning messages
        mock_print.assert_any_call("Warning: Failed to apply migrations: Migration failed")
        mock_print.assert_any_call("The application may not function correctly.")


class TestGetDatabaseConnection:
    """Test cases for get_database_connection function."""

    def setup_method(self):
        """Set up test environment."""
        # Store original environment variables
        self.original_env = {}
        env_vars = ['POSTGRES_HOST', 'POSTGRES_PORT', 'POSTGRES_USER', 
                   'POSTGRES_PASSWORD', 'POSTGRES_DB']
        for var in env_vars:
            self.original_env[var] = os.environ.get(var)

    def teardown_method(self):
        """Clean up test environment."""
        # Restore original environment variables
        for var, value in self.original_env.items():
            if value is None:
                os.environ.pop(var, None)
            else:
                os.environ[var] = value

    @patch.dict(os.environ, {
        'POSTGRES_HOST': 'testhost',
        'POSTGRES_PORT': '5433',
        'POSTGRES_USER': 'testuser',
        'POSTGRES_PASSWORD': 'testpass',
        'POSTGRES_DB': 'testdb'
    })
    @patch('psycopg.connect')
    def test_get_database_connection_success(self, mock_connect):
        """Test successful database connection."""
        mock_connection = MagicMock()
        mock_connect.return_value = mock_connection
        
        result = get_database_connection()
        
        mock_connect.assert_called_once_with(
            host='testhost',
            port='5433',
            user='testuser',
            password='testpass',
            dbname='testdb'
        )
        assert result == mock_connection

    @patch.dict(os.environ, {
        'POSTGRES_USER': 'testuser',
        'POSTGRES_PASSWORD': 'testpass'
    }, clear=True)
    @patch('psycopg.connect')
    def test_get_database_connection_default_values(self, mock_connect):
        """Test database connection with default values."""
        mock_connection = MagicMock()
        mock_connect.return_value = mock_connection
        
        result = get_database_connection()
        
        mock_connect.assert_called_once_with(
            host='localhost',
            port='5432',
            user='testuser',
            password='testpass',
            dbname='bmlibrarian_dev'
        )
        assert result == mock_connection

    @patch.dict(os.environ, {
        'POSTGRES_PASSWORD': 'testpass'
    }, clear=True)
    def test_get_database_connection_missing_user(self):
        """Test database connection with missing user."""
        with pytest.raises(ValueError) as exc_info:
            get_database_connection()
        
        assert "Database credentials not configured" in str(exc_info.value)
        assert "POSTGRES_USER and POSTGRES_PASSWORD" in str(exc_info.value)

    @patch.dict(os.environ, {
        'POSTGRES_USER': 'testuser'
    }, clear=True)
    def test_get_database_connection_missing_password(self):
        """Test database connection with missing password."""
        with pytest.raises(ValueError) as exc_info:
            get_database_connection()
        
        assert "Database credentials not configured" in str(exc_info.value)

    @patch.dict(os.environ, {}, clear=True)
    def test_get_database_connection_missing_both_credentials(self):
        """Test database connection with missing user and password."""
        with pytest.raises(ValueError) as exc_info:
            get_database_connection()
        
        assert "Database credentials not configured" in str(exc_info.value)

    @patch.dict(os.environ, {
        'POSTGRES_USER': 'testuser',
        'POSTGRES_PASSWORD': 'testpass'
    })
    @patch('psycopg.connect')
    def test_get_database_connection_psycopg_error(self, mock_connect):
        """Test database connection when psycopg raises an error."""
        mock_connect.side_effect = Exception("Connection failed")
        
        with pytest.raises(Exception) as exc_info:
            get_database_connection()
        
        assert "Connection failed" in str(exc_info.value)

    @patch.dict(os.environ, {
        'POSTGRES_HOST': '192.168.1.100',
        'POSTGRES_PORT': '5434',
        'POSTGRES_USER': 'admin',
        'POSTGRES_PASSWORD': 'secret123',
        'POSTGRES_DB': 'production_db'
    })
    @patch('psycopg.connect')
    def test_get_database_connection_custom_config(self, mock_connect):
        """Test database connection with custom configuration."""
        mock_connection = MagicMock()
        mock_connect.return_value = mock_connection
        
        result = get_database_connection()
        
        mock_connect.assert_called_once_with(
            host='192.168.1.100',
            port='5434',
            user='admin',
            password='secret123',
            dbname='production_db'
        )
        assert result == mock_connection