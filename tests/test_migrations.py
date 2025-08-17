"""Unit tests for the migrations module."""

import hashlib
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, call, mock_open, patch

import pytest

from bmlibrarian.migrations import MigrationManager


class TestMigrationManager:
    """Test cases for MigrationManager class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.manager = MigrationManager(
            host="localhost",
            port="5432",
            user="testuser",
            password="testpass",
            database="testdb"
        )

    def test_init(self):
        """Test MigrationManager initialization."""
        assert self.manager.host == "localhost"
        assert self.manager.port == "5432"
        assert self.manager.user == "testuser"
        assert self.manager.password == "testpass"
        assert self.manager.database == "testdb"
        
        expected_params = {
            "host": "localhost",
            "port": "5432",
            "user": "testuser",
            "password": "testpass"
        }
        assert self.manager._conn_params == expected_params

    @patch('bmlibrarian.migrations.psycopg.connect')
    def test_get_connection_default(self, mock_connect):
        """Test getting database connection without specifying database."""
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        
        result = self.manager._get_connection()
        
        mock_connect.assert_called_once_with(
            host="localhost",
            port="5432",
            user="testuser",
            password="testpass"
        )
        assert result == mock_conn

    @patch('bmlibrarian.migrations.psycopg.connect')
    def test_get_connection_with_database(self, mock_connect):
        """Test getting database connection with specific database."""
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        
        result = self.manager._get_connection("specific_db")
        
        mock_connect.assert_called_once_with(
            host="localhost",
            port="5432",
            user="testuser",
            password="testpass",
            dbname="specific_db"
        )
        assert result == mock_conn

    @patch.object(MigrationManager, '_get_connection')
    def test_database_exists_true(self, mock_get_connection):
        """Test database_exists when database exists."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (1,)
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_get_connection.return_value.__enter__.return_value = mock_conn
        
        result = self.manager._database_exists("test_db")
        
        assert result is True
        mock_get_connection.assert_called_once_with("postgres")
        mock_cursor.execute.assert_called_once_with(
            "SELECT 1 FROM pg_database WHERE datname = %s",
            ("test_db",)
        )

    @patch.object(MigrationManager, '_get_connection')
    def test_database_exists_false(self, mock_get_connection):
        """Test database_exists when database doesn't exist."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_get_connection.return_value.__enter__.return_value = mock_conn
        
        result = self.manager._database_exists("test_db")
        
        assert result is False

    @patch('bmlibrarian.migrations.psycopg.sql.SQL')
    @patch('bmlibrarian.migrations.psycopg.sql.Identifier')
    @patch.object(MigrationManager, '_get_connection')
    def test_create_database(self, mock_get_connection, mock_identifier, mock_sql):
        """Test database creation."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_get_connection.return_value.__enter__.return_value = mock_conn
        
        mock_identifier.return_value = "quoted_db_name"
        mock_sql_instance = MagicMock()
        mock_sql.return_value.format.return_value = mock_sql_instance
        
        self.manager._create_database("test_db")
        
        mock_get_connection.assert_called_once_with("postgres")
        assert mock_conn.autocommit is True
        mock_identifier.assert_called_once_with("test_db")
        mock_cursor.execute.assert_called_once_with(mock_sql_instance)

    @patch.object(MigrationManager, '_get_connection')
    def test_create_migrations_table(self, mock_get_connection):
        """Test creation of migrations tracking table."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_get_connection.return_value.__enter__.return_value = mock_conn
        
        self.manager._create_migrations_table()
        
        mock_get_connection.assert_called_once_with("testdb")
        expected_sql = """
                    CREATE TABLE IF NOT EXISTS bmlibrarian_migrations (
                        id SERIAL PRIMARY KEY,
                        filename VARCHAR(255) NOT NULL UNIQUE,
                        checksum VARCHAR(64) NOT NULL,
                        applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """
        mock_cursor.execute.assert_called_once_with(expected_sql)
        mock_conn.commit.assert_called_once()

    @patch.object(MigrationManager, '_get_connection')
    def test_get_applied_migrations(self, mock_get_connection):
        """Test getting list of applied migrations."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            ("001_initial.sql", "abc123"),
            ("002_add_table.sql", "def456")
        ]
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_get_connection.return_value.__enter__.return_value = mock_conn
        
        result = self.manager._get_applied_migrations()
        
        assert result == [("001_initial.sql", "abc123"), ("002_add_table.sql", "def456")]
        mock_cursor.execute.assert_called_once_with(
            "SELECT filename, checksum FROM bmlibrarian_migrations ORDER BY filename"
        )

    def test_calculate_checksum(self):
        """Test checksum calculation."""
        content = "CREATE TABLE test (id INT);"
        expected = hashlib.sha256(content.encode('utf-8')).hexdigest()
        
        result = self.manager._calculate_checksum(content)
        
        assert result == expected

    @patch.object(MigrationManager, '_get_connection')
    def test_apply_sql_file(self, mock_get_connection):
        """Test applying SQL file to database."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_get_connection.return_value.__enter__.return_value = mock_conn
        
        sql_content = "CREATE TABLE test (id INT);"
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.sql', delete=False) as f:
            f.write(sql_content)
            temp_path = Path(f.name)
        
        try:
            self.manager._apply_sql_file(temp_path)
            
            mock_get_connection.assert_called_once_with("testdb")
            mock_cursor.execute.assert_called_once_with(sql_content)
            mock_conn.commit.assert_called_once()
        finally:
            temp_path.unlink()

    @patch.object(MigrationManager, '_get_connection')
    def test_record_migration(self, mock_get_connection):
        """Test recording migration as applied."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_get_connection.return_value.__enter__.return_value = mock_conn
        
        self.manager._record_migration("test.sql", "abc123")
        
        mock_get_connection.assert_called_once_with("testdb")
        mock_cursor.execute.assert_called_once_with(
            "INSERT INTO bmlibrarian_migrations (filename, checksum) VALUES (%s, %s)",
            ("test.sql", "abc123")
        )
        mock_conn.commit.assert_called_once()

    @patch.object(MigrationManager, '_record_migration')
    @patch.object(MigrationManager, '_apply_sql_file')
    @patch.object(MigrationManager, '_create_migrations_table')
    @patch.object(MigrationManager, '_get_applied_migrations')
    @patch.object(MigrationManager, '_create_database')
    @patch.object(MigrationManager, '_database_exists')
    def test_initialize_database_new_db(self, mock_db_exists, mock_create_db, 
                                       mock_get_applied, mock_create_table,
                                       mock_apply_sql, mock_record):
        """Test initializing database when database doesn't exist."""
        mock_db_exists.return_value = False
        mock_get_applied.return_value = []
        
        baseline_content = "CREATE TABLE baseline (id INT);"
        with tempfile.NamedTemporaryFile(mode='w', suffix='.sql', delete=False) as f:
            f.write(baseline_content)
            baseline_path = Path(f.name)
        
        try:
            with patch('builtins.print') as mock_print:
                self.manager.initialize_database(baseline_path)
            
            mock_db_exists.assert_called_once_with("testdb")
            mock_create_db.assert_called_once_with("testdb")
            mock_create_table.assert_called_once()
            mock_get_applied.assert_called_once()
            mock_apply_sql.assert_called_once_with(baseline_path)
            
            expected_checksum = hashlib.sha256(baseline_content.encode('utf-8')).hexdigest()
            mock_record.assert_called_once_with(baseline_path.name, expected_checksum)
            
            # Check print calls
            mock_print.assert_any_call("Checking if database 'testdb' exists...")
            mock_print.assert_any_call("Creating database 'testdb'...")
            mock_print.assert_any_call("Baseline schema applied successfully!")
        finally:
            baseline_path.unlink()

    @patch.object(MigrationManager, '_get_applied_migrations')
    @patch.object(MigrationManager, '_create_migrations_table')
    @patch.object(MigrationManager, '_database_exists')
    def test_initialize_database_already_applied(self, mock_db_exists, mock_create_table, mock_get_applied):
        """Test initializing database when baseline already applied."""
        mock_db_exists.return_value = True
        mock_get_applied.return_value = [("baseline_schema.sql", "abc123")]
        
        baseline_path = Path("baseline_schema.sql")
        
        with patch('builtins.print') as mock_print:
            self.manager.initialize_database(baseline_path)
        
        mock_print.assert_any_call("Baseline schema has already been applied.")

    def test_initialize_database_file_not_found(self):
        """Test initializing database with non-existent baseline file."""
        non_existent_path = Path("/non/existent/file.sql")
        
        with pytest.raises(FileNotFoundError):
            self.manager.initialize_database(non_existent_path)

    @patch.object(MigrationManager, '_record_migration')
    @patch.object(MigrationManager, '_apply_sql_file')
    @patch.object(MigrationManager, '_get_applied_migrations')
    @patch.object(MigrationManager, '_create_migrations_table')
    def test_apply_pending_migrations_success(self, mock_create_table, mock_get_applied,
                                            mock_apply_sql, mock_record):
        """Test applying pending migrations successfully."""
        mock_get_applied.return_value = [("001_initial.sql", "abc123")]
        
        with tempfile.TemporaryDirectory() as temp_dir:
            migrations_dir = Path(temp_dir)
            
            # Create test migration files
            migration1 = migrations_dir / "001_initial.sql"
            migration2 = migrations_dir / "002_new.sql"
            migration3 = migrations_dir / "003_another.sql"
            
            migration1.write_text("-- Migration 1")
            migration2.write_text("-- Migration 2")
            migration3.write_text("-- Migration 3")
            
            with patch('builtins.print') as mock_print:
                result = self.manager.apply_pending_migrations(migrations_dir)
            
            assert result == 2  # Should apply 2 new migrations
            mock_create_table.assert_called_once()
            mock_get_applied.assert_called_once()
            
            # Should apply migration2 and migration3 (migration1 already applied)
            expected_calls = [call(migration2), call(migration3)]
            mock_apply_sql.assert_has_calls(expected_calls)
            
            # Should record both new migrations
            assert mock_record.call_count == 2

    @patch.object(MigrationManager, '_create_migrations_table')
    def test_apply_pending_migrations_no_directory(self, mock_create_table):
        """Test applying migrations when directory doesn't exist."""
        with tempfile.TemporaryDirectory() as temp_dir:
            non_existent_dir = Path(temp_dir) / "non_existent"
            
            with patch('builtins.print') as mock_print:
                result = self.manager.apply_pending_migrations(non_existent_dir)
            
            assert result == 0
            mock_print.assert_any_call(f"Migrations directory does not exist: {non_existent_dir}")
            mock_print.assert_any_call("Creating migrations directory...")

    @patch('sys.exit')
    @patch.object(MigrationManager, '_apply_sql_file')
    @patch.object(MigrationManager, '_get_applied_migrations')
    @patch.object(MigrationManager, '_create_migrations_table')
    def test_apply_pending_migrations_failure(self, mock_create_table, mock_get_applied,
                                            mock_apply_sql, mock_exit):
        """Test handling migration application failure."""
        mock_get_applied.return_value = []
        mock_apply_sql.side_effect = Exception("SQL error")
        
        with tempfile.TemporaryDirectory() as temp_dir:
            migrations_dir = Path(temp_dir)
            migration = migrations_dir / "001_test.sql"
            migration.write_text("-- Test migration")
            
            with patch('builtins.print') as mock_print:
                self.manager.apply_pending_migrations(migrations_dir)
            
            mock_exit.assert_called_once_with(1)
            mock_print.assert_any_call("✗ Failed to apply 001_test.sql: SQL error")


