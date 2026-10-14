# Test Database Guard

Code: `src/bmlibrarian/db_test_guard.py`. Wired into
`src/bmlibrarian/database.py` (`DatabaseManager`) and
`src/bmlibrarian/migrations.py` (`MigrationManager`). Tests:
`tests/test_db_test_guard.py`.

## Why

Many tests call `get_db_manager()`. That reads the default env file
(`~/.bmlibrarian/.env`), which on a developer machine usually names the
production database, and `DatabaseManager` applies pending migrations on
connect. On 2026-10-13/14 a full test run applied migrations 031 and 032 to
production this way. They were additive and were kept, but the suite must
never be able to do this.

## What it does

The guard is active only while `pytest` is in `sys.modules`, and only for
**protected databases** (`PROTECTED_DATABASES = {"knowledgebase"}`):

| Where | Behaviour under pytest on a protected database |
|---|---|
| `MigrationManager.apply_pending_migrations()` / `initialize_database()` | raise `ProtectedDatabaseError` before connecting |
| `DatabaseManager(auto_migrate=True)` | skips auto-migration, logs a warning |
| `DatabaseManager` connection pool | every connection opens with `-c default_transaction_read_only=on`; any write fails with `ReadOnlySqlTransaction` |

Live read-only tests against production keep working; writes and schema
changes cannot happen. Outside pytest nothing changes.

## Not covered

Code that calls `psycopg.connect()` directly instead of going through
`DatabaseManager` bypasses the guard. That already violates golden rule 5, and
those modules should move to the database manager.

## Writing tests that need a writable database

Use a development database:

- the opt-in pattern of `tests/test_pubmed_bulk_importer_copy.py`: set
  `BMLIBRARIAN_TEST_DB_ENV=~/.bmlibrarian/.env_pg18_dev`. Such tests skip when
  it is unset and refuse `knowledgebase`;
- or select the env file for the whole run with `BMLIBRARIAN_ENV_FILE`.
