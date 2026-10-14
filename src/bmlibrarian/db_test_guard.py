"""
Guard that keeps the test suite away from production databases.

Tests call ``get_db_manager()``, which reads the default env file
(``~/.bmlibrarian/.env``, usually production) and applies pending migrations on
connect. In October 2026 a full test run applied migrations 031 and 032 to the
production database that way. While pytest is loaded, this guard therefore:

- refuses to migrate a protected database (``MigrationManager``), and
  ``DatabaseManager`` skips its auto-migration there;
- opens ``DatabaseManager`` connections to a protected database read-only
  (``default_transaction_read_only=on``), so live read tests keep working but
  cannot write.

Outside pytest nothing changes.
"""

import logging
import sys
from typing import Dict, Mapping, Optional

from psycopg.conninfo import conninfo_to_dict

logger = logging.getLogger(__name__)

# Databases the test suite must never change.
PROTECTED_DATABASES = frozenset({"knowledgebase"})
READ_ONLY_OPTIONS = "-c default_transaction_read_only=on"


class ProtectedDatabaseError(RuntimeError):
    """A write or migration to a protected database was attempted under pytest."""


def running_under_pytest(modules: Optional[Mapping[str, object]] = None) -> bool:
    """Whether pytest is loaded in this process.

    Args:
        modules: Module table to inspect (default: ``sys.modules``).
    """
    return "pytest" in (sys.modules if modules is None else modules)


def is_protected_database(dbname: Optional[str]) -> bool:
    """Whether ``dbname`` is a database the test suite must not change."""
    return dbname in PROTECTED_DATABASES


def database_name(conninfo: str) -> Optional[str]:
    """The ``dbname`` of a libpq connection string, if it names one."""
    return conninfo_to_dict(conninfo).get("dbname")


def guard_applies(dbname: Optional[str], modules: Optional[Mapping[str, object]] = None) -> bool:
    """Whether the guard is active for ``dbname`` (protected and under pytest)."""
    return is_protected_database(dbname) and running_under_pytest(modules)


def pool_connection_kwargs(conninfo: str, modules: Optional[Mapping[str, object]] = None) -> Dict[str, str]:
    """Extra connection arguments for a pool: read-only for a guarded database.

    Args:
        conninfo: The pool's libpq connection string.
        modules: Module table to inspect (default: ``sys.modules``).

    Returns:
        ``{"options": READ_ONLY_OPTIONS}`` if the guard applies, else ``{}``.
    """
    if guard_applies(database_name(conninfo), modules):
        logger.warning("Running under pytest: connections to %s are read-only", database_name(conninfo))
        return {"options": READ_ONLY_OPTIONS}
    return {}


def refuse_if_guarded(dbname: Optional[str], action: str) -> None:
    """Raise if ``action`` would change a protected database under pytest.

    Raises:
        ProtectedDatabaseError: If the guard applies to ``dbname``.
    """
    if guard_applies(dbname):
        raise ProtectedDatabaseError(
            f"refusing to {action} on protected database {dbname!r} while running under pytest; "
            "point the tests at a development database (BMLIBRARIAN_ENV_FILE)")
