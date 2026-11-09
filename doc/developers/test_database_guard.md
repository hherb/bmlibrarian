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

## Which databases are protected

The guard is active only while `pytest` is in `sys.modules`. It uses an
**allow-list**: every database is protected unless it is recognisably a
test/development database, so a new production database (for example a
future PG18 `bmlibrarian` on port 5532) is protected without anyone having to
list it.

A database is *not* protected if:

- a token of its name, split on `_` or `-`, is `dev`, `devel` or
  `development`, or starts with `test` (`bmlibrarian_dev`, `dev_db`,
  `test_db`, `testdb`, `kb-test`); or
- it is listed in `BMLIBRARIAN_TEST_ALLOWED_DATABASES` (comma-separated).

A connection string that names no database is protected: libpq would use
`PGDATABASE` or the user name, which the guard cannot vouch for.

## What it does

| Where | Behaviour under pytest on a protected database |
|---|---|
| `MigrationManager.apply_pending_migrations()` / `initialize_database()` / `mark_migration_applied()` | raise `ProtectedDatabaseError` before connecting |
| `MigrationManager._get_connection()` | opens with `-c default_transaction_read_only=on` (maintenance connections to `postgres` are judged by the database they act for, `guard_as`) |
| `DatabaseManager(auto_migrate=True)` | skips auto-migration, logs a warning |
| `DatabaseManager` connection pool | the read-only option is written into the conninfo itself (`guarded_conninfo()`); writes fail with `ReadOnlySqlTransaction` unless a transaction explicitly runs `SET TRANSACTION READ WRITE` |

Because the option is part of `DatabaseManager.conninfo`, worker processes
handed that string (the PubMed bulk importer's `spawn` workers, which do not
load pytest) stay read-only too.

Live read-only tests against production keep working; writes and schema
changes cannot happen through these paths. Outside pytest nothing changes.

## Not covered

Code that calls `psycopg.connect()` directly instead of going through
`DatabaseManager` bypasses the guard (for example `db_import_profile.py`,
`app.py`, `fulltext_discovery_cli.py`, `paperchecker/database.py`, the Qt
login in `gui/qt/core/application.py`). That already violates golden rule 5;
those modules should move to the database manager (ROADMAP §2).

## Writing tests that need a writable database

Use a development database:

- the opt-in pattern of `tests/test_pubmed_bulk_importer_copy.py` and the
  031/032–033 migration tests: they read `BMLIBRARIAN_TEST_DB_ENV`
  (e.g. `~/.bmlibrarian/.env_pg18_dev`), skip when it is unset and refuse any
  database `is_protected_database()` protects;
- or select the env file for the whole run with `BMLIBRARIAN_ENV_FILE`
  pointing at a dev database.

## Live tests are opt-in (#334)

A plain `pytest tests/` is hermetic: it reads no database and needs no
Ollama. `tests/conftest.py`:

- skips tests marked `requires_database` or `requires_ollama` unless live
  tests are enabled with `--run-live` or by setting `BMLIBRARIAN_TEST_DB_ENV`;
- fails any other test that opens a PostgreSQL connection
  (`psycopg.connect`, `psycopg.Connection.connect`, a `psycopg_pool`
  pool) or connects to the local Ollama port, with a message naming the
  marker it needs (`_block_live_services`). Mock the service, or mark the test.

With `--run-live` the tests use whatever the env file names, so production is
read (read-only, see above); prefer `BMLIBRARIAN_ENV_FILE` plus
`BMLIBRARIAN_TEST_DB_ENV` pointing at a dev database. Not caught: a remote
`OLLAMA_HOST`, and connections opened in a background thread (the failure is
raised there, not in the test).
