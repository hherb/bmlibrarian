"""Database migration system for bmlibrarian."""

import hashlib
import logging
import os
import re
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator, List, Tuple, Optional

import psycopg

from bmlibrarian.db_test_guard import guarded_connect_kwargs, refuse_if_guarded

logger = logging.getLogger(__name__)

# Session advisory lock key held while migrating (any constant unique to this
# purpose; the Rust bml-db library uses its own database).
MIGRATION_LOCK_KEY = 0x626D6C5F6D696772  # "bml_migr"
MIGRATION_LOCK_POLL_SECONDS = 1.0
# How long to wait for another process's migrations (a CONCURRENTLY index on a
# large table can take a while) before giving up with a MigrationError.
MIGRATION_LOCK_TIMEOUT_SECONDS = 3600.0

# A whole line that is just BEGIN; or COMMIT; (a file managing its own transaction).
OWN_TRANSACTION_LINE = re.compile(r"^[ \t]*(BEGIN|COMMIT)[ \t]*;[ \t]*$", re.IGNORECASE | re.MULTILINE)
# The index and table names of a CREATE INDEX CONCURRENTLY statement.
CONCURRENT_INDEX_NAME = re.compile(
    r'CREATE\s+(?:UNIQUE\s+)?INDEX\s+CONCURRENTLY\s+(?:IF\s+NOT\s+EXISTS\s+)?'
    r'(?P<name>"[^"]+"|[\w$]+)\s+ON\s+(?:ONLY\s+)?(?P<table>(?:"[^"]+"|[\w$]+)(?:\.(?:"[^"]+"|[\w$]+))?)',
    re.IGNORECASE,
)


def concurrent_index_target(statement: str) -> Tuple[str, str]:
    """The index and table a ``CREATE INDEX CONCURRENTLY`` statement names.

    Returns:
        (the index name as stored: unquoted names folded to lower case, quoted
        ones verbatim; the table as written, for ``to_regclass``).

    Raises:
        MigrationError: The statement names no index, so it can't be checked.
    """
    match = CONCURRENT_INDEX_NAME.match(statement.strip())
    if match is None:
        raise MigrationError(
            f"CREATE INDEX CONCURRENTLY needs an index name to be checked: {statement[:80]}"
        )
    name, table = match.group("name", "table")
    # shortcut: a "" escape inside a quoted name is not undone; no migration uses one.
    name = name[1:-1] if name.startswith('"') else name.lower()
    return name, table


class MigrationError(RuntimeError):
    """A pending migration could not be read, applied or recorded.

    The schema is outdated, or (for a file with ``CREATE INDEX CONCURRENTLY``)
    its committed SQL will run again on a retry; either way the app must not
    start as if it were current.
    """


class MigrationManager:
    """Manages database migrations for bmlibrarian."""

    def __init__(self, host: str, port: str, user: str, password: str, database: str):
        """Initialize the migration manager with database connection parameters."""
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.database = database
        self._conn_params = {
            "host": host,
            "port": port,
            "user": user,
            "password": password
        }

    @classmethod
    def from_env(cls) -> Optional['MigrationManager']:
        """Create MigrationManager from environment variables.

        Returns:
            MigrationManager instance or None if credentials missing
        """
        try:
            from bmlibrarian.env_loader import load_bmlibrarian_env
            # Same file selection as bmlibrarian.database (BMLIBRARIAN_ENV_FILE,
            # else ~/.bmlibrarian/.env, else ./.env); existing values are kept.
            load_bmlibrarian_env(override=False)

            user = os.getenv("POSTGRES_USER")
            password = os.getenv("POSTGRES_PASSWORD")

            if not user or not password:
                logger.warning("Missing POSTGRES_USER or POSTGRES_PASSWORD in environment")
                return None

            return cls(
                host=os.getenv("POSTGRES_HOST", "localhost"),
                port=os.getenv("POSTGRES_PORT", "5432"),
                user=user,
                password=password,
                database=os.getenv("POSTGRES_DB", "knowledgebase")
            )
        except Exception as e:
            logger.warning(f"Could not create MigrationManager from environment: {e}")
            return None

    def _get_connection(self, database: Optional[str] = None,
                        guard_as: Optional[str] = None) -> psycopg.Connection:
        """Get a database connection (read-only for a protected database under pytest).

        Args:
            database: Database to connect to.
            guard_as: Database the test guard judges instead of ``database``; for
                maintenance connections to ``postgres`` made on behalf of another
                database.
        """
        params = self._conn_params.copy()
        if database:
            params["dbname"] = database
        params.update(guarded_connect_kwargs(guard_as or database))
        return psycopg.connect(**params)
    
    def _database_exists(self, database_name: str) -> bool:
        """Check if a database exists."""
        with self._get_connection("postgres", guard_as=database_name) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM pg_database WHERE datname = %s",
                    (database_name,)
                )
                return cur.fetchone() is not None
    
    def _create_database(self, database_name: str):
        """Create a new database."""
        with self._get_connection("postgres", guard_as=database_name) as conn:
            conn.autocommit = True
            with conn.cursor() as cur:
                # Use identifier to safely quote the database name
                cur.execute(psycopg.sql.SQL("CREATE DATABASE {}").format(
                    psycopg.sql.Identifier(database_name)
                ))
    
    def _create_migrations_table(self):
        """Create the migrations tracking table."""
        with self._get_connection(self.database) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS bmlibrarian_migrations (
                        id SERIAL PRIMARY KEY,
                        filename VARCHAR(255) NOT NULL UNIQUE,
                        checksum VARCHAR(64) NOT NULL,
                        applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                conn.commit()
    
    def _get_applied_migrations(self) -> List[Tuple[str, str]]:
        """Get list of applied migrations (filename, checksum)."""
        with self._get_connection(self.database) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT filename, checksum FROM bmlibrarian_migrations ORDER BY filename"
                )
                return cur.fetchall()
    
    def _calculate_checksum(self, content: str) -> str:
        """Calculate SHA-256 checksum of migration content."""
        return hashlib.sha256(content.encode('utf-8')).hexdigest()
    
    def _extract_concurrent_indexes(self, sql_content: str) -> Tuple[str, List[str]]:
        """Extract CREATE INDEX CONCURRENTLY statements from SQL content.

        These statements cannot run inside a transaction block, so they must
        be executed separately with autocommit enabled.

        Args:
            sql_content: The full SQL content of the migration file

        Returns:
            Tuple of (modified_sql_without_concurrent_indexes, list_of_concurrent_index_statements)
        """
        # Pattern to match CREATE INDEX CONCURRENTLY statements
        # Handles multi-line statements ending with semicolon
        pattern = re.compile(
            r'CREATE\s+(?:UNIQUE\s+)?INDEX\s+CONCURRENTLY\s+.*?;',
            re.IGNORECASE | re.DOTALL
        )

        concurrent_statements = pattern.findall(sql_content)
        modified_sql = pattern.sub('-- [CONCURRENT INDEX MOVED TO POST-TRANSACTION EXECUTION]', sql_content)

        return modified_sql, concurrent_statements

    @contextmanager
    def _migration_lock(
        self, report: Callable[[str], None] = logger.warning
    ) -> Iterator[psycopg.Connection]:
        """Hold the migration lock for this database; yield its connection.

        One process applies migrations at a time. The lock is a session
        advisory lock on an autocommit connection, released when it closes.
        It is polled with ``pg_try_advisory_lock`` rather than waited for:
        a waiter blocked inside a statement keeps a snapshot, which
        ``CREATE INDEX CONCURRENTLY`` in the holder would wait on in turn.

        Args:
            report: Told once if the lock is held elsewhere and this waits.

        Raises:
            MigrationError: The lock could not be taken (connection failed,
                or another process held it for ``MIGRATION_LOCK_TIMEOUT_SECONDS``),
                so pending migrations stay unapplied.
        """
        conn: Optional[psycopg.Connection] = None
        try:
            try:
                conn = self._get_connection(self.database)
                conn.autocommit = True
                deadline = time.monotonic() + MIGRATION_LOCK_TIMEOUT_SECONDS
                announced = False
                while conn.execute(
                    "SELECT pg_try_advisory_lock(%s)", (MIGRATION_LOCK_KEY,)
                ).fetchone() != (True,):
                    if time.monotonic() >= deadline:
                        raise MigrationError(
                            "Another process held the migration lock for over "
                            f"{MIGRATION_LOCK_TIMEOUT_SECONDS:.0f} s; pending migrations were not applied"
                        )
                    if not announced:
                        report(
                            "Waiting for another process to finish applying migrations "
                            f"(giving up after {MIGRATION_LOCK_TIMEOUT_SECONDS:.0f} s)"
                        )
                        announced = True
                    time.sleep(MIGRATION_LOCK_POLL_SECONDS)
            except psycopg.Error as e:
                raise MigrationError(f"Could not take the migration lock: {e}") from e
            yield conn
        finally:
            if conn is not None:
                conn.close()

    @staticmethod
    def _is_recorded(conn: psycopg.Connection, filename: str) -> bool:
        """Whether ``filename`` is recorded as applied, read on ``conn``."""
        return conn.execute(
            "SELECT 1 FROM bmlibrarian_migrations WHERE filename = %s", (filename,)
        ).fetchone() is not None

    @staticmethod
    def _record_migration(conn: psycopg.Connection, filename: str, checksum: str) -> None:
        """Record a migration as applied, on ``conn`` (in its transaction, if any)."""
        conn.execute(
            "INSERT INTO bmlibrarian_migrations (filename, checksum) VALUES (%s, %s)",
            (filename, checksum),
        )

    @staticmethod
    def _index_state(conn: psycopg.Connection, name: str, table: str) -> Tuple[psycopg.sql.Identifier, Optional[bool]]:
        """Find index ``name`` on ``table`` (as from ``concurrent_index_target``).

        Returns:
            (the index, schema-qualified when it exists; ``True``/``False`` for
            valid/invalid, ``None`` if it does not exist on that table).
        """
        row = conn.execute(
            "SELECT n.nspname, c.relname, i.indisvalid FROM pg_index i"
            " JOIN pg_class c ON c.oid = i.indexrelid"
            " JOIN pg_namespace n ON n.oid = c.relnamespace"
            " WHERE c.relname = %s AND i.indrelid = to_regclass(%s)",
            (name, table),
        ).fetchone()
        if row is None:
            return psycopg.sql.Identifier(name), None
        return psycopg.sql.Identifier(row[0], row[1]), row[2]

    def _apply_migration(self, conn: psycopg.Connection, filename: str, content: str) -> bool:
        """Apply one migration and record it, holding the migration lock on ``conn``.

        The SQL and its record commit together, so a failure leaves neither.
        ``CREATE INDEX CONCURRENTLY`` can't run in a transaction: such
        statements run afterwards (an INVALID index left by an earlier failed
        build is dropped first, as ``IF NOT EXISTS`` would skip it), and the
        migration is recorded only once every one of its indexes is valid (its
        other SQL is then committed already and runs again on a retry, so it
        must be idempotent, as every migration should be).

        Args:
            conn: The autocommit connection from ``_migration_lock``.
            filename: The migration's file name, as recorded.
            content: The migration's SQL.

        Returns:
            False if another process had already applied it, else True.
        """
        checksum = self._calculate_checksum(content)
        main_sql, concurrent_indexes = self._extract_concurrent_indexes(content)
        # The runner owns the transaction; a file's own BEGIN/COMMIT would end it early.
        main_sql = OWN_TRANSACTION_LINE.sub("", main_sql)
        # Before anything runs: an index we can't name can't be checked afterwards.
        targets = [(stmt, *concurrent_index_target(stmt)) for stmt in concurrent_indexes]

        with conn.transaction():
            if self._is_recorded(conn, filename):
                return False
            if main_sql.strip():
                conn.execute(main_sql)
                # One connection serves the whole run: a file's SET/set_config (the
                # baseline empties search_path) must not reach the record or the next file.
                conn.execute("RESET ALL")
            if not concurrent_indexes:
                self._record_migration(conn, filename, checksum)
                return True

        logger.info(f"Executing {len(concurrent_indexes)} CONCURRENT index statement(s) outside transaction")
        for idx_stmt, name, table in targets:
            index, valid = self._index_state(conn, name, table)
            if valid is False:
                logger.info(f"Dropping invalid index {name} left by an earlier failed build")
                conn.execute(psycopg.sql.SQL("DROP INDEX CONCURRENTLY IF EXISTS {}").format(index))
            logger.info(f"Creating concurrent index: {idx_stmt[:80]}...")
            conn.execute(idx_stmt)
            _, valid = self._index_state(conn, name, table)
            if valid is None:
                raise MigrationError(
                    f"Index {name} does not exist on {table} after CREATE INDEX CONCURRENTLY"
                    " (IF NOT EXISTS skipped it for a same-named index elsewhere?)"
                )
            if not valid:
                raise MigrationError(f"Index {name} is not valid after CREATE INDEX CONCURRENTLY")

        with conn.transaction():
            self._record_migration(conn, filename, checksum)
        return True

    def mark_migration_applied(self, migration_file: Path) -> bool:
        """Mark a migration as applied without executing it.

        This is a recovery mechanism for when a migration was applied manually
        or the schema already exists from other means.

        Args:
            migration_file: Path to the migration file to mark as applied

        Returns:
            True if successfully marked, False if already applied

        Raises:
            ProtectedDatabaseError: Under pytest, for a protected (production) database.
        """
        refuse_if_guarded(self.database, "mark a migration as applied")
        migration_file = Path(migration_file)
        if not migration_file.exists():
            raise FileNotFoundError(f"Migration file not found: {migration_file}")

        # Ensure migrations table exists
        self._create_migrations_table()

        with open(migration_file, 'r', encoding='utf-8') as f:
            content = f.read()
        checksum = self._calculate_checksum(content)

        with self._migration_lock() as conn, conn.transaction():
            if self._is_recorded(conn, migration_file.name):
                logger.info(f"Migration {migration_file.name} is already marked as applied")
                return False
            self._record_migration(conn, migration_file.name, checksum)
        logger.info(f"Marked migration as applied: {migration_file.name}")
        return True

    def get_migration_status(self, migrations_dir: Path) -> dict:
        """Get status of all migrations.

        Args:
            migrations_dir: Path to migrations directory

        Returns:
            Dictionary with 'applied', 'pending', and 'total' counts plus lists
        """
        migrations_dir = Path(migrations_dir)
        result = {
            'applied': [],
            'pending': [],
            'total': 0
        }

        if not migrations_dir.exists():
            return result

        # Ensure migrations table exists
        try:
            self._create_migrations_table()
            applied_migrations = {filename for filename, _ in self._get_applied_migrations()}
        except Exception as e:
            logger.warning(f"Could not get applied migrations: {e}")
            applied_migrations = set()

        # Find all migration files
        for file_path in sorted(migrations_dir.glob("*.sql"), key=lambda x: x.name):
            if re.match(r'^\d+_.*\.sql$', file_path.name):
                result['total'] += 1
                if file_path.name in applied_migrations:
                    result['applied'].append(file_path.name)
                else:
                    result['pending'].append(file_path.name)

        return result
    
    def initialize_database(self, baseline_schema_path: Path):
        """Initialize database with baseline schema."""
        refuse_if_guarded(self.database, "initialize the schema")
        baseline_schema_path = Path(baseline_schema_path)
        
        if not baseline_schema_path.exists():
            raise FileNotFoundError(f"Baseline schema file not found: {baseline_schema_path}")
        
        print(f"Checking if database '{self.database}' exists...")
        
        # Create database if it doesn't exist
        if not self._database_exists(self.database):
            print(f"Creating database '{self.database}'...")
            self._create_database(self.database)
        else:
            print(f"Database '{self.database}' already exists.")
        
        # Create migrations table
        print("Creating migrations tracking table...")
        self._create_migrations_table()
        
        # Check if baseline has already been applied
        applied_migrations = self._get_applied_migrations()
        baseline_filename = baseline_schema_path.name
        
        for filename, _ in applied_migrations:
            if filename == baseline_filename:
                print("Baseline schema has already been applied.")
                return
        
        # Apply and record the baseline schema
        print("Applying baseline schema...")
        with open(baseline_schema_path, 'r', encoding='utf-8') as f:
            content = f.read()
        with self._migration_lock(print) as conn:
            if not self._apply_migration(conn, baseline_filename, content):
                print("Baseline schema was applied by another process meanwhile.")
                return

        print("Baseline schema applied successfully!")
    
    def apply_pending_migrations(
        self,
        migrations_dir: Path,
        silent: bool = False,
        dry_run: bool = False
    ) -> int:
        """Apply all pending migrations from the migrations directory.

        Args:
            migrations_dir: Path to migrations directory
            silent: If True, use logging instead of print statements
            dry_run: If True, only show what would be applied without making changes

        Returns:
            Number of migrations applied (or would be applied in dry_run mode)

        Raises:
            ProtectedDatabaseError: Under pytest, for a protected (production) database.
            MigrationError: A pending migration could not be read, applied or
                recorded.
        """
        refuse_if_guarded(self.database, "apply migrations")
        migrations_dir = Path(migrations_dir)

        if not migrations_dir.exists():
            msg = f"Migrations directory does not exist: {migrations_dir}"
            if silent:
                logger.debug(msg)
            else:
                print(msg)
            return 0

        # Ensure migrations table exists. A role without CREATE on the schema
        # can fail here even when the table exists, so fall through and read it.
        create_error: Optional[Exception] = None
        try:
            self._create_migrations_table()
        except Exception as e:
            create_error = e
            logger.debug(f"Could not create migrations table (reading it instead): {e}")

        # Get applied migrations
        try:
            applied_migrations = {filename for filename, _ in self._get_applied_migrations()}
        except Exception as e:
            msg = f"Could not get applied migrations: {e}"
            if create_error is not None:
                msg += f" (creating the migrations table also failed: {create_error})"
            if silent:
                logger.warning(msg)
            else:
                print(f"Warning: {msg}")
            return 0

        # Find migration files (should be .sql files with numeric prefix)
        migration_files = []
        for file_path in migrations_dir.glob("*.sql"):
            if re.match(r'^\d+_.*\.sql$', file_path.name):
                migration_files.append(file_path)

        # Sort by filename (which should start with numbers for ordering)
        migration_files.sort(key=lambda x: x.name)

        # Dry run mode - just show what would be applied
        if dry_run:
            pending_count = 0
            for migration_file in migration_files:
                if migration_file.name not in applied_migrations:
                    pending_count += 1
                    msg = f"[DRY RUN] Would apply: {migration_file.name}"
                    if silent:
                        logger.info(msg)
                    else:
                        print(msg)

            if pending_count == 0:
                msg = f"[DRY RUN] Database is up to date. {len(applied_migrations)} migrations already applied, no pending migrations."
                if silent:
                    logger.info(msg)
                else:
                    print(msg)
            else:
                msg = f"[DRY RUN] Total: {pending_count} migration(s) would be applied ({len(applied_migrations)} already applied)"
                if silent:
                    logger.info(msg)
                else:
                    print(msg)

            return pending_count

        # Apply pending migrations. The set read above is re-checked per file
        # under the lock, since another process may have applied some meanwhile.
        pending = [f for f in migration_files if f.name not in applied_migrations]
        if not pending:
            return 0
        applied_count = 0
        with self._migration_lock(logger.warning if silent else print) as conn:
            for migration_file in pending:
                msg = f"Applying migration: {migration_file.name}"
                if silent:
                    logger.info(msg)
                else:
                    print(msg)

                try:
                    # Inside the try: an unreadable pending file is a failed apply too.
                    with open(migration_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                    applied = self._apply_migration(conn, migration_file.name, content)
                except Exception as e:
                    msg = f"✗ Failed to apply {migration_file.name}: {e}"
                    if silent:
                        logger.error(msg)
                    else:
                        print(msg)
                    raise MigrationError(msg) from e

                if applied:
                    applied_count += 1
                    msg = f"✓ Applied: {migration_file.name}"
                else:
                    msg = f"Already applied by another process: {migration_file.name}"
                if silent:
                    logger.info(msg)
                else:
                    print(msg)

        return applied_count
