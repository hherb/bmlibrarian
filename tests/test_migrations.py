"""Unit tests for the migrations module."""

import hashlib
import re
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Iterator, List, Optional, Tuple, Union
from unittest.mock import MagicMock, call, patch

import psycopg
import pytest

from bmlibrarian.db_test_guard import READ_ONLY_OPTIONS
from bmlibrarian.migrations import (
    CONCURRENT_INDEX_NAME,
    MIGRATION_LOCK_KEY,
    MIGRATION_LOCK_TIMEOUT_SECONDS,
    OWN_TRANSACTION_LINE,
    MigrationError,
    MigrationManager,
    concurrent_index_target,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
# What still ends the runner's transaction once a file's bare BEGIN;/COMMIT; lines are dropped.
TRANSACTION_CONTROL = re.compile(
    r"^\s*(COMMIT|ROLLBACK|END\s*;|START\s+TRANSACTION|BEGIN\s+(WORK|TRANSACTION)|BEGIN\s*;)",
    re.IGNORECASE | re.MULTILINE,
)


class FakeConn:
    """A plain stand-in connection that logs each statement with its transaction depth."""

    def __init__(self, recorded: bool = False, fail_on: str = "",
                 index_states: Iterable[Optional[Tuple[str, str, bool]]] = ()) -> None:
        """Answer the "is it recorded?" check with ``recorded``; raise on SQL containing ``fail_on``.

        ``index_states`` answers successive pg_index lookups: a (schema, name, valid) row or None.
        """
        self.recorded = recorded
        self.fail_on = fail_on
        self.index_states = list(index_states)
        self.depth = 0
        self.commits = 0
        self.rollbacks = 0
        self.log: List[Tuple[str, Any, int]] = []

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Count a commit, or a rollback when the block raises."""
        self.depth += 1
        try:
            yield
        except BaseException:
            self.rollbacks += 1
            raise
        else:
            self.commits += 1
        finally:
            self.depth -= 1

    def execute(self, sql: Union[str, psycopg.sql.Composable], params: Any = None) -> MagicMock:
        """Log ``sql`` and return a cursor-like object for its answer."""
        sql = sql if isinstance(sql, str) else sql.as_string(None)
        self.log.append((sql, params, self.depth))
        if self.fail_on and self.fail_on in sql:
            raise RuntimeError("record failed")
        row = None
        if "pg_index" in sql:
            row = self.index_states.pop(0)
        elif "FROM bmlibrarian_migrations" in sql:
            row = (1,) if self.recorded else None
        return MagicMock(fetchone=MagicMock(return_value=row))


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

    def test_apply_migration_runs_sql_and_record_in_one_transaction(self):
        """SQL and record run inside one transaction; the file's own BEGIN/COMMIT are dropped."""
        conn = FakeConn()
        content = "BEGIN;\nCREATE TABLE t (id INT);\nCOMMIT;\n"

        assert self.manager._apply_migration(conn, "001_t.sql", content) is True

        assert conn.commits == 1
        assert [sql.strip() for sql, _, depth in conn.log if depth == 1] == [
            "SELECT 1 FROM bmlibrarian_migrations WHERE filename = %s",
            "CREATE TABLE t (id INT);",
            "RESET ALL",
            "INSERT INTO bmlibrarian_migrations (filename, checksum) VALUES (%s, %s)",
        ]
        assert conn.log[-1][1] == ("001_t.sql", hashlib.sha256(content.encode("utf-8")).hexdigest())
        assert all(depth == 1 for _, _, depth in conn.log)

    def test_failed_record_rolls_back_the_migration_sql(self):
        """A record that fails takes the migration's SQL down with it (#439)."""
        conn = FakeConn(fail_on="INSERT INTO bmlibrarian_migrations")

        with pytest.raises(RuntimeError, match="record failed"):
            self.manager._apply_migration(conn, "001_t.sql", "CREATE TABLE t (id INT);")

        assert (conn.commits, conn.rollbacks) == (0, 1)
        assert any("CREATE TABLE" in sql and depth == 1 for sql, _, depth in conn.log)

    def test_apply_migration_skips_one_already_recorded(self):
        """Another process applied it while this one waited for the lock."""
        conn = FakeConn(recorded=True)

        assert self.manager._apply_migration(conn, "001_t.sql", "CREATE TABLE t (id INT);") is False

        assert [sql for sql, _, _ in conn.log] == ["SELECT 1 FROM bmlibrarian_migrations WHERE filename = %s"]

    def test_concurrent_index_is_built_outside_and_recorded_last(self):
        """Main SQL commits, the index builds outside a transaction, then the record commits."""
        conn = FakeConn(index_states=[None, ("public", "idx_t", True)])
        content = "CREATE TABLE t (x INT);\nCREATE INDEX CONCURRENTLY idx_t ON t (x);\n"

        assert self.manager._apply_migration(conn, "001_t.sql", content) is True

        steps = [(sql.strip().split()[0], depth) for sql, _, depth in conn.log if "pg_index" not in sql]
        assert steps == [("SELECT", 1), ("CREATE", 1), ("RESET", 1), ("CREATE", 0), ("INSERT", 1)]
        assert conn.commits == 2

    def test_invalid_index_after_build_leaves_no_record(self):
        """A build that leaves an INVALID index fails the migration, unrecorded."""
        conn = FakeConn(index_states=[None, ("public", "idx_t", False)])

        with pytest.raises(MigrationError, match="idx_t is not valid"):
            self.manager._apply_migration(conn, "001_t.sql", "CREATE INDEX CONCURRENTLY idx_t ON t (x);")

        assert not any("INSERT" in sql for sql, _, _ in conn.log)

    def test_missing_index_after_build_is_reported_as_missing(self):
        """IF NOT EXISTS skipping the build is not reported as an invalid index."""
        conn = FakeConn(index_states=[None, None])

        with pytest.raises(MigrationError, match="does not exist on t"):
            self.manager._apply_migration(
                conn, "001_t.sql", "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_t ON t (x);"
            )

    def test_invalid_index_from_earlier_build_is_dropped_first(self):
        """IF NOT EXISTS would skip an INVALID leftover, so it is dropped before the build."""
        conn = FakeConn(index_states=[("public", "idx_t", False), ("public", "idx_t", True)])

        self.manager._apply_migration(
            conn, "001_t.sql", "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_t ON t (x);"
        )

        executed = [sql for sql, _, _ in conn.log if "pg_index" not in sql]
        drop = next(i for i, sql in enumerate(executed) if sql.startswith("DROP INDEX CONCURRENTLY"))
        build = next(i for i, sql in enumerate(executed) if sql.startswith("CREATE INDEX"))
        assert drop < build

    def test_unnamed_concurrent_index_is_refused_before_any_sql(self):
        """An index we can't name can't be checked, and nothing of the file runs."""
        conn = FakeConn()

        with pytest.raises(MigrationError, match="needs an index name"):
            self.manager._apply_migration(
                conn, "001_t.sql", "CREATE TABLE t (x INT);\nCREATE INDEX CONCURRENTLY ON t (x);\n"
            )

        assert conn.log == []

    @pytest.mark.parametrize("statement, expected", [
        ("CREATE INDEX CONCURRENTLY Idx_T ON s.t (x);", ("idx_t", "s.t")),
        ('CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS "Idx T" ON ONLY "S"."T" (x);', ("Idx T", '"S"."T"')),
    ])
    def test_concurrent_index_target_folds_like_postgres(self, statement: str, expected: Tuple[str, str]) -> None:
        """Unquoted names fold to lower case; quoted ones and the table text are kept."""
        assert concurrent_index_target(statement) == expected

    def test_migration_lock_polls_then_releases_on_error(self):
        """The lock is polled until free, its wait announced once, and released on any exit."""
        conn = MagicMock()
        conn.execute.return_value.fetchone.side_effect = [(False,), (False,), (True,)]
        report = MagicMock()

        with patch.object(self.manager, "_get_connection", return_value=conn), \
                patch("bmlibrarian.migrations.time.sleep") as sleep:
            with pytest.raises(RuntimeError, match="boom"):
                with self.manager._migration_lock(report) as got:
                    assert got is conn
                    raise RuntimeError("boom")

        assert conn.autocommit is True
        assert sleep.call_count == 2
        report.assert_called_once()
        conn.execute.assert_called_with("SELECT pg_try_advisory_lock(%s)", (MIGRATION_LOCK_KEY,))
        conn.close.assert_called_once()

    def test_migration_lock_gives_up_after_timeout(self):
        """A lock held elsewhere for too long is a MigrationError, not a hang."""
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = (False,)
        clock = iter([0.0, 0.0, MIGRATION_LOCK_TIMEOUT_SECONDS + 1])

        with patch.object(self.manager, "_get_connection", return_value=conn), \
                patch("bmlibrarian.migrations.time.sleep"), \
                patch("bmlibrarian.migrations.time.monotonic", side_effect=lambda: next(clock)):
            with pytest.raises(MigrationError, match="held the migration lock"):
                with self.manager._migration_lock(MagicMock()):
                    pass

        conn.close.assert_called_once()

    def test_migration_lock_connection_failure_is_a_migration_error(self):
        """A connection lost while waiting must stop startup, not be swallowed as a warning."""
        conn = MagicMock()
        conn.execute.side_effect = psycopg.OperationalError("server closed the connection")

        with patch.object(self.manager, "_get_connection", return_value=conn):
            with pytest.raises(MigrationError, match="Could not take the migration lock"):
                with self.manager._migration_lock(MagicMock()):
                    pass

        conn.close.assert_called_once()

    @patch.object(MigrationManager, '_migration_lock')
    @patch.object(MigrationManager, '_apply_migration', side_effect=[True, Exception("boom")])
    @patch.object(MigrationManager, '_get_applied_migrations', return_value=[])
    @patch.object(MigrationManager, '_create_migrations_table')
    def test_failure_mid_sequence_stops_the_run(self, mock_create_table, mock_get_applied,
                                                mock_apply, mock_lock, tmp_path):
        """After 002 fails, 003 is not attempted."""
        for name in ("001_a.sql", "002_b.sql", "003_c.sql"):
            (tmp_path / name).write_text(f"-- {name}")

        with pytest.raises(MigrationError, match="002_b.sql"):
            self.manager.apply_pending_migrations(tmp_path, silent=True)

        assert [c.args[1] for c in mock_apply.call_args_list] == ["001_a.sql", "002_b.sql"]

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




@pytest.mark.parametrize(
    "path",
    sorted((REPO_ROOT / "migrations").glob("*.sql")) + [REPO_ROOT / "baseline_schema.sql"],
    ids=lambda p: p.name,
)
def test_shipped_migrations_fit_the_runner(path: Path) -> None:
    """Every shipped file's CONCURRENTLY indexes are nameable, and none ends the transaction early."""
    main_sql, concurrent = MigrationManager("h", "1", "u", "p", "d")._extract_concurrent_indexes(
        path.read_text(encoding="utf-8")
    )
    for statement in concurrent:
        assert CONCURRENT_INDEX_NAME.match(statement.strip()), statement[:80]
    stripped = OWN_TRANSACTION_LINE.sub("", main_sql)
    # Ignore function bodies: their BEGIN ... END; is PL/pgSQL, not transaction control.
    outside_bodies = re.sub(r"\$(\w*)\$.*?\$\1\$", "", stripped, flags=re.DOTALL)
    assert TRANSACTION_CONTROL.search(outside_bodies) is None
