"""Unit tests for the migrations module."""

import hashlib
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from bmlibrarian.db_test_guard import READ_ONLY_OPTIONS
from bmlibrarian.migrations import MigrationError, MigrationManager


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
        """Without a database name the test guard cannot vouch for it: read-only under pytest."""
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        
        result = self.manager._get_connection()
        
        mock_connect.assert_called_once_with(
            host="localhost",
            port="5432",
            user="testuser",
            password="testpass",
            options=READ_ONLY_OPTIONS,
        )
        assert result == mock_conn

    @patch('bmlibrarian.migrations.psycopg.connect')
    def test_get_connection_with_database(self, mock_connect):
        """Test getting database connection with specific database."""
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        
        result = self.manager._get_connection("specific_test_db")
        
        mock_connect.assert_called_once_with(
            host="localhost",
            port="5432",
            user="testuser",
            password="testpass",
            dbname="specific_test_db"
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
        mock_get_connection.assert_called_once_with("postgres", guard_as="test_db")
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
        
        mock_get_connection.assert_called_once_with("postgres", guard_as="test_db")
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

    @staticmethod
    def fake_conn(recorded: bool) -> MagicMock:
        """A connection whose "is it recorded?" query answers ``recorded``."""
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = (1,) if recorded else None
        return conn

    def test_apply_migration_runs_sql_and_record_in_one_transaction(self):
        """SQL and record go through one connection; the file's own BEGIN/COMMIT are dropped."""
        conn = self.fake_conn(recorded=False)
        content = "BEGIN;\nCREATE TABLE t (id INT);\nCOMMIT;\n"

        assert self.manager._apply_migration(conn, "001_t.sql", content) is True

        conn.transaction.assert_called_once()
        executed = [c.args for c in conn.execute.call_args_list]
        assert executed[1][0].strip() == "CREATE TABLE t (id INT);"
        assert executed[2] == ("RESET ALL",)
        assert executed[3] == (
            "INSERT INTO bmlibrarian_migrations (filename, checksum) VALUES (%s, %s)",
            ("001_t.sql", hashlib.sha256(content.encode("utf-8")).hexdigest()),
        )

    def test_apply_migration_skips_one_already_recorded(self):
        """Another process applied it while this one waited for the lock."""
        conn = self.fake_conn(recorded=True)

        assert self.manager._apply_migration(conn, "001_t.sql", "CREATE TABLE t (id INT);") is False

        assert conn.execute.call_count == 1  # only the check

    def test_unnamed_concurrent_index_is_refused(self):
        """An index we can't name can't be checked for validity."""
        with pytest.raises(MigrationError, match="needs an index name"):
            self.manager._index_state(MagicMock(), "CREATE INDEX CONCURRENTLY ON t (x);")

    @patch.object(MigrationManager, '_migration_lock')
    @patch.object(MigrationManager, '_apply_migration', return_value=True)
    @patch.object(MigrationManager, '_create_migrations_table')
    @patch.object(MigrationManager, '_get_applied_migrations')
    @patch.object(MigrationManager, '_create_database')
    @patch.object(MigrationManager, '_database_exists')
    def test_initialize_database_new_db(self, mock_db_exists, mock_create_db,
                                       mock_get_applied, mock_create_table,
                                       mock_apply, mock_lock):
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
            lock_conn = mock_lock.return_value.__enter__.return_value
            mock_apply.assert_called_once_with(lock_conn, baseline_path.name, baseline_content)
            
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

    @patch.object(MigrationManager, '_migration_lock')
    @patch.object(MigrationManager, '_apply_migration', return_value=True)
    @patch.object(MigrationManager, '_get_applied_migrations')
    @patch.object(MigrationManager, '_create_migrations_table')
    def test_apply_pending_migrations_success(self, mock_create_table, mock_get_applied,
                                            mock_apply, mock_lock):
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
            lock_conn = mock_lock.return_value.__enter__.return_value
            mock_apply.assert_has_calls([
                call(lock_conn, "002_new.sql", "-- Migration 2"),
                call(lock_conn, "003_another.sql", "-- Migration 3"),
            ])
            assert mock_apply.call_count == 2

    @patch.object(MigrationManager, '_migration_lock')
    @patch.object(MigrationManager, '_apply_migration', side_effect=[False, True])
    @patch.object(MigrationManager, '_get_applied_migrations', return_value=[])
    @patch.object(MigrationManager, '_create_migrations_table')
    def test_apply_pending_counts_only_own_applies(self, mock_create_table, mock_get_applied,
                                                   mock_apply, mock_lock, tmp_path):
        """A migration another process applied meanwhile is not counted."""
        (tmp_path / "001_a.sql").write_text("-- a")
        (tmp_path / "002_b.sql").write_text("-- b")

        with patch('builtins.print') as mock_print:
            assert self.manager.apply_pending_migrations(tmp_path) == 1

        mock_print.assert_any_call("Already applied by another process: 001_a.sql")

    @patch.object(MigrationManager, '_migration_lock')
    @patch.object(MigrationManager, '_get_applied_migrations', return_value=[("001_a.sql", "x")])
    @patch.object(MigrationManager, '_create_migrations_table')
    def test_nothing_pending_takes_no_lock(self, mock_create_table, mock_get_applied,
                                           mock_lock, tmp_path):
        """The usual startup with an up-to-date schema never waits on the lock."""
        (tmp_path / "001_a.sql").write_text("-- a")

        assert self.manager.apply_pending_migrations(tmp_path, silent=True) == 0

        mock_lock.assert_not_called()

    @patch.object(MigrationManager, '_create_migrations_table')
    def test_apply_pending_migrations_no_directory(self, mock_create_table):
        """Test applying migrations when directory doesn't exist."""
        with tempfile.TemporaryDirectory() as temp_dir:
            non_existent_dir = Path(temp_dir) / "non_existent"
            
            with patch('builtins.print') as mock_print:
                result = self.manager.apply_pending_migrations(non_existent_dir)
            
            assert result == 0
            mock_print.assert_any_call(f"Migrations directory does not exist: {non_existent_dir}")
            assert not non_existent_dir.exists()  # missing directory is reported, not created

    @patch.object(MigrationManager, '_migration_lock')
    @patch.object(MigrationManager, '_apply_migration')
    @patch.object(MigrationManager, '_get_applied_migrations')
    @patch.object(MigrationManager, '_create_migrations_table')
    def test_apply_pending_migrations_failure(self, mock_create_table, mock_get_applied,
                                            mock_apply, mock_lock):
        """Test handling migration application failure."""
        mock_get_applied.return_value = []
        mock_apply.side_effect = Exception("SQL error")
        
        with tempfile.TemporaryDirectory() as temp_dir:
            migrations_dir = Path(temp_dir)
            migration = migrations_dir / "001_test.sql"
            migration.write_text("-- Test migration")
            
            with patch('builtins.print') as mock_print:
                with pytest.raises(MigrationError, match="Failed to apply 001_test.sql: SQL error"):
                    self.manager.apply_pending_migrations(migrations_dir)
            
            mock_print.assert_any_call("✗ Failed to apply 001_test.sql: SQL error")


