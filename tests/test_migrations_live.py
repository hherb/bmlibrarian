"""MigrationManager against a real PostgreSQL (#439).

Each test makes its own scratch database (the role needs CREATEDB) and drops
it afterwards. Run with ``BMLIBRARIAN_TEST_DB_ENV=<dev env file>``.
"""

import threading
import uuid
from pathlib import Path
from typing import Iterator, List, Tuple

import psycopg
import pytest

from bmlibrarian.migrations import MIGRATION_LOCK_KEY, MigrationError, MigrationManager

pytestmark = pytest.mark.requires_database

# Not idempotent: applying it twice fails with "already exists".
CREATE_TABLE = "BEGIN;\nCREATE TABLE race_t (x INT);\nINSERT INTO race_t VALUES (1), (1);\nCOMMIT;\n"
UNIQUE_INDEX = "CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS race_t_x ON race_t (x);\n"
THREADS = 4


@pytest.fixture
def scratch_manager() -> Iterator[MigrationManager]:
    """A MigrationManager for a fresh scratch database, dropped afterwards."""
    base = MigrationManager.from_env()
    if base is None:
        pytest.skip("no database credentials configured")
    name = f"bmlibrarian_test_mig_{uuid.uuid4().hex[:8]}"
    manager = MigrationManager(base.host, base.port, base.user, base.password, name)
    manager._create_database(name)
    try:
        manager._create_migrations_table()
        yield manager
    finally:
        with manager._get_connection("postgres", guard_as=name) as conn:
            conn.autocommit = True
            conn.execute(psycopg.sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                psycopg.sql.Identifier(name)))


def recorded(manager: MigrationManager) -> List[str]:
    """The migration file names recorded as applied."""
    return [name for name, _ in manager._get_applied_migrations()]


def test_concurrent_runs_apply_each_migration_once(scratch_manager: MigrationManager,
                                                   tmp_path: Path) -> None:
    """Runners that all saw both files pending: one applies them, the others skip them."""
    (tmp_path / "001_table.sql").write_text(CREATE_TABLE.replace("(1), (1)", "(1), (2)"))
    (tmp_path / "002_index.sql").write_text(UNIQUE_INDEX)
    counts: List[int] = []
    errors: List[BaseException] = []
    # Every runner has read the applied set (nothing yet) before the lock is let go.
    read_pending = threading.Barrier(THREADS + 1)

    def run() -> None:
        """Apply the directory with a manager of its own (its own connections)."""
        own = MigrationManager(scratch_manager.host, scratch_manager.port, scratch_manager.user,
                               scratch_manager.password, scratch_manager.database)
        read = own._get_applied_migrations

        def read_then_wait() -> List[Tuple[str, str]]:
            """Read the applied set, then wait until every runner has."""
            applied = read()
            read_pending.wait()
            return applied

        own._get_applied_migrations = read_then_wait  # type: ignore[method-assign]
        try:
            counts.append(own.apply_pending_migrations(tmp_path, silent=True))
        except BaseException as e:  # collected so the main thread can assert
            errors.append(e)

    threads = [threading.Thread(target=run) for _ in range(THREADS)]
    with scratch_manager._get_connection(scratch_manager.database) as holder:
        holder.autocommit = True
        holder.execute("SELECT pg_advisory_lock(%s)", (MIGRATION_LOCK_KEY,))
        for t in threads:
            t.start()
        read_pending.wait()
    # The holder's connection is closed: the lock is free and the runners contend for it.
    for t in threads:
        t.join()

    assert errors == []
    assert sorted(counts) == [0] * (THREADS - 1) + [2]
    assert recorded(scratch_manager) == ["001_table.sql", "002_index.sql"]


def test_failed_record_rolls_back_the_migration(scratch_manager: MigrationManager,
                                                tmp_path: Path) -> None:
    """If recording fails, the migration's SQL is rolled back with it (#439)."""
    # The file records itself, so the runner's own record hits the UNIQUE filename.
    (tmp_path / "001_atomic.sql").write_text(
        "CREATE TABLE atomic_t (x INT);\n"
        "INSERT INTO bmlibrarian_migrations (filename, checksum) VALUES ('001_atomic.sql', 'x');\n")

    with pytest.raises(MigrationError, match="001_atomic.sql"):
        scratch_manager.apply_pending_migrations(tmp_path, silent=True)

    assert recorded(scratch_manager) == []
    with scratch_manager._get_connection(scratch_manager.database) as conn:
        assert conn.execute("SELECT to_regclass('atomic_t')").fetchone() == (None,)


def test_invalid_concurrent_index_is_rebuilt_before_recording(scratch_manager: MigrationManager,
                                                              tmp_path: Path) -> None:
    """A failed CONCURRENTLY build is not recorded, and the retry drops its INVALID index."""
    (tmp_path / "001_table.sql").write_text(CREATE_TABLE)
    (tmp_path / "002_index.sql").write_text(UNIQUE_INDEX)

    with pytest.raises(MigrationError, match="002_index.sql"):
        scratch_manager.apply_pending_migrations(tmp_path, silent=True)
    assert recorded(scratch_manager) == ["001_table.sql"]

    with scratch_manager._get_connection(scratch_manager.database) as conn:
        conn.execute("DELETE FROM race_t WHERE ctid <> (SELECT min(ctid) FROM race_t)")
        conn.commit()

    assert scratch_manager.apply_pending_migrations(tmp_path, silent=True) == 1
    assert recorded(scratch_manager) == ["001_table.sql", "002_index.sql"]
    with scratch_manager._get_connection(scratch_manager.database) as conn:
        valid = conn.execute(
            "SELECT indisvalid FROM pg_index WHERE indexrelid = 'race_t_x'::regclass"
        ).fetchone()
    assert valid == (True,)


def test_session_settings_do_not_leak_into_the_next_file(scratch_manager: MigrationManager,
                                                         tmp_path: Path) -> None:
    """A file that empties search_path (as the pg_dump baseline does) can't break the next."""
    (tmp_path / "001_dump.sql").write_text(
        "SELECT pg_catalog.set_config('search_path', '', false);\nCREATE TABLE public.leak_a (x INT);\n")
    (tmp_path / "002_plain.sql").write_text("CREATE TABLE leak_b (x INT);\n")

    assert scratch_manager.apply_pending_migrations(tmp_path, silent=True) == 2
    assert recorded(scratch_manager) == ["001_dump.sql", "002_plain.sql"]
