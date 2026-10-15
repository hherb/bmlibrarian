"""
Guard that keeps the test suite away from production databases.

Tests call ``get_db_manager()``, which reads the default env file
(``~/.bmlibrarian/.env``, usually production) and applies pending migrations on
connect. In October 2026 a full test run applied migrations 031 and 032 to the
production database that way. While pytest is loaded, every database that is
not recognisably a test database is protected (an allow-list, so a new
production database such as the PG18 ``bmlibrarian`` is protected without
anyone remembering to list it). For a protected database the guard:

- refuses to migrate it (``MigrationManager``), and ``DatabaseManager`` skips
  its auto-migration there;
- opens ``DatabaseManager`` and ``MigrationManager`` connections read-only
  (``default_transaction_read_only=on``), so live read tests keep working but
  cannot write. The option is written into the connection string itself, so
  worker processes handed that string stay read-only even though pytest is not
  loaded in them.

A connection string that names no database is protected too: libpq would fall
back to ``PGDATABASE`` or the user name, which the guard cannot vouch for.

Outside pytest nothing changes.
"""

import logging
import os
import re
import sys
from typing import Dict, Mapping, Optional

from psycopg.conninfo import conninfo_to_dict, make_conninfo

logger = logging.getLogger(__name__)

# Comma-separated extra database names the test suite may change.
ALLOWED_DATABASES_ENV = "BMLIBRARIAN_TEST_ALLOWED_DATABASES"
# A database is a test database if a name token (split on _ or -) is one of
# these or starts with "test": bmlibrarian_dev, dev_db, test_db, testdb.
DEV_NAME_TOKENS = frozenset({"dev", "devel", "development"})
TEST_NAME_PREFIX = "test"
NAME_TOKEN_SEPARATOR = re.compile(r"[_\-]")
READ_ONLY_OPTIONS = "-c default_transaction_read_only=on"


class ProtectedDatabaseError(RuntimeError):
    """A write or migration to a protected database was attempted under pytest."""


def running_under_pytest(modules: Optional[Mapping[str, object]] = None) -> bool:
    """Whether pytest is loaded in this process.

    Args:
        modules: Module table to inspect (default: ``sys.modules``).
    """
    return "pytest" in (sys.modules if modules is None else modules)


def allowed_databases(environ: Optional[Mapping[str, str]] = None) -> frozenset:
    """Database names explicitly allowed via ``BMLIBRARIAN_TEST_ALLOWED_DATABASES``.

    Args:
        environ: Environment to read (default: ``os.environ``).
    """
    raw = (os.environ if environ is None else environ).get(ALLOWED_DATABASES_ENV, "")
    return frozenset(name.strip() for name in raw.split(",") if name.strip())


def is_test_database(dbname: Optional[str], environ: Optional[Mapping[str, str]] = None) -> bool:
    """Whether ``dbname`` is recognisably a test/development database.

    Args:
        dbname: Database name (None if the connection string names none).
        environ: Environment for the explicit allow-list (default: ``os.environ``).
    """
    if not dbname:
        return False
    if dbname in allowed_databases(environ):
        return True
    tokens = NAME_TOKEN_SEPARATOR.split(dbname.lower())
    return any(t in DEV_NAME_TOKENS or t.startswith(TEST_NAME_PREFIX) for t in tokens)


def is_protected_database(dbname: Optional[str], environ: Optional[Mapping[str, str]] = None) -> bool:
    """Whether ``dbname`` is a database the test suite must not change (anything not a test DB)."""
    return not is_test_database(dbname, environ)


def database_name(conninfo: str) -> Optional[str]:
    """The ``dbname`` of a libpq connection string, if it names one."""
    dbname = conninfo_to_dict(conninfo).get("dbname")
    return str(dbname) if dbname is not None else None


def guard_applies(dbname: Optional[str], modules: Optional[Mapping[str, object]] = None,
                  environ: Optional[Mapping[str, str]] = None) -> bool:
    """Whether the guard is active for ``dbname`` (protected and under pytest).

    Args:
        dbname: Database name (None if the connection string names none).
        modules: Module table to inspect (default: ``sys.modules``).
        environ: Environment for the explicit allow-list (default: ``os.environ``).
    """
    return running_under_pytest(modules) and is_protected_database(dbname, environ)


def with_read_only_option(options: Optional[str]) -> str:
    """``options`` (libpq ``-c`` settings) with read-only transactions added once."""
    if not options:
        return READ_ONLY_OPTIONS
    if READ_ONLY_OPTIONS in options:
        return options
    return f"{options} {READ_ONLY_OPTIONS}"


def guarded_conninfo(conninfo: str, modules: Optional[Mapping[str, object]] = None,
                     environ: Optional[Mapping[str, str]] = None) -> str:
    """The connection string to use: read-only for a guarded database, else unchanged.

    Args:
        conninfo: The libpq connection string.
        modules: Module table to inspect (default: ``sys.modules``).
        environ: Environment for the explicit allow-list (default: ``os.environ``).

    Returns:
        ``conninfo`` with ``default_transaction_read_only=on`` in its options if
        the guard applies, else ``conninfo`` itself.
    """
    dbname = database_name(conninfo)
    if not guard_applies(dbname, modules, environ):
        return conninfo
    logger.warning("Running under pytest: connections to protected database %r are read-only", dbname)
    existing = conninfo_to_dict(conninfo).get("options")
    options = with_read_only_option(str(existing) if existing is not None else None)
    return make_conninfo(conninfo, options=options)


def guarded_connect_kwargs(dbname: Optional[str], options: Optional[str] = None,
                           modules: Optional[Mapping[str, object]] = None,
                           environ: Optional[Mapping[str, str]] = None) -> Dict[str, str]:
    """Extra ``psycopg.connect()`` keyword arguments: read-only options for a guarded database.

    Args:
        dbname: Database the connection will open.
        options: Options the caller already passes, if any.
        modules: Module table to inspect (default: ``sys.modules``).
        environ: Environment for the explicit allow-list (default: ``os.environ``).

    Returns:
        ``{"options": ...}`` if the guard applies, else ``{}``.
    """
    if guard_applies(dbname, modules, environ):
        return {"options": with_read_only_option(options)}
    return {}


def refuse_if_guarded(dbname: Optional[str], action: str) -> None:
    """Raise if ``action`` would change a protected database under pytest.

    Raises:
        ProtectedDatabaseError: If the guard applies to ``dbname``.
    """
    if guard_applies(dbname):
        raise ProtectedDatabaseError(
            f"refusing to {action} on protected database {dbname!r} while running under pytest; "
            f"point the tests at a development database (BMLIBRARIAN_ENV_FILE) whose name contains "
            f"'dev' or 'test', or list it in {ALLOWED_DATABASES_ENV}")
