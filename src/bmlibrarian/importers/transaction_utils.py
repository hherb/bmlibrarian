"""
Transaction utilities shared by BMLibrarian bulk importers.

Bulk importers (medRxiv, PubMed, Europe PMC, ClinicalTrials.gov, Retraction
Watch, ...) typically process many records inside a single database
transaction for performance. Without per-record isolation, a single
malformed or unexpectedly-failing record can "poison" the whole
transaction:

- If the per-record error handler calls ``conn.rollback()``, every record
  written earlier in that same transaction (already counted as a success)
  is discarded.
- If the per-record error handler does nothing, PostgreSQL leaves the
  connection in an aborted-transaction state ("current transaction is
  aborted, commands ignored until end of transaction block"), so every
  subsequent record fails too, and the final ``conn.commit()`` silently
  discards the entire transaction (PostgreSQL treats COMMIT of an aborted
  transaction as a ROLLBACK).

:func:`record_savepoint` wraps a single record's writes in a SQL
SAVEPOINT. On success the savepoint is released. On failure, the
transaction is rolled back only to the savepoint -- discarding just that
record's writes while leaving every previously-written record in the
transaction intact and the connection in a healthy, non-aborted state so
processing can continue with the next record.

This relies only on standard SQL SAVEPOINT / RELEASE SAVEPOINT / ROLLBACK
TO SAVEPOINT statements, which are supported identically by psycopg3
(PostgreSQL, used in production) and Python's built-in ``sqlite3`` module
(used for hermetic unit testing).
"""

import re
from contextlib import contextmanager
from typing import Any, Iterator, Protocol


class _SavepointCursor(Protocol):
    """Minimal cursor protocol required by :func:`record_savepoint`.

    Both psycopg3 cursors and Python's built-in ``sqlite3`` cursors satisfy
    this protocol, which is what makes it possible to unit test importer
    logic against an in-memory SQLite database.
    """

    def execute(self, query: str, params: Any = None) -> Any:
        """Execute a single SQL statement."""
        ...


# Savepoint identifiers must be simple, hardcoded SQL identifiers. They are
# interpolated directly into `SAVEPOINT <name>` / `ROLLBACK TO SAVEPOINT
# <name>` statements because neither PostgreSQL nor SQLite support binding
# savepoint names as query parameters. Per the "never trust external input"
# rule, callers must NEVER derive a savepoint name from user, file, network,
# or database content -- only from a fixed string literal in the calling code.
_VALID_SAVEPOINT_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

#: Maximum length for a savepoint identifier. PostgreSQL identifiers are
#: truncated at 63 bytes; this keeps names well within that limit.
MAX_SAVEPOINT_NAME_LENGTH = 63

#: Default savepoint name used when a caller does not need a custom one.
DEFAULT_SAVEPOINT_NAME = "record_import"


def _validate_savepoint_name(name: str) -> None:
    """Validate that ``name`` is safe to interpolate into a SAVEPOINT statement.

    Args:
        name: Proposed savepoint identifier.

    Raises:
        ValueError: If ``name`` is not a simple alphanumeric/underscore
            identifier starting with a letter or underscore, or exceeds
            ``MAX_SAVEPOINT_NAME_LENGTH`` characters.
    """
    if not isinstance(name, str) or not _VALID_SAVEPOINT_NAME_PATTERN.match(name):
        raise ValueError(
            f"Invalid savepoint name {name!r}: must match "
            f"{_VALID_SAVEPOINT_NAME_PATTERN.pattern!r}. Savepoint names must "
            "be hardcoded identifiers in calling code, never derived from "
            "external, user, or database data."
        )
    if len(name) > MAX_SAVEPOINT_NAME_LENGTH:
        raise ValueError(
            f"Invalid savepoint name {name!r}: exceeds "
            f"{MAX_SAVEPOINT_NAME_LENGTH} characters."
        )


@contextmanager
def record_savepoint(
    cur: _SavepointCursor, name: str = DEFAULT_SAVEPOINT_NAME
) -> Iterator[None]:
    """Wrap one record's database writes in a SQL SAVEPOINT.

    On success, the savepoint is released and the surrounding transaction
    keeps whatever was written. On any exception raised inside the ``with``
    block, the transaction is rolled back to the savepoint -- undoing only
    this record's writes -- and the exception is re-raised so the caller
    can log it and update failure counters while continuing to the next
    record with a healthy (non-aborted) transaction.

    Args:
        cur: An open DB-API cursor (psycopg3 or ``sqlite3``) belonging to a
            connection that is inside an active transaction.
        name: Savepoint identifier. Must be a simple, hardcoded identifier
            (validated by :func:`_validate_savepoint_name`); never derive
            this from external, user, or database data.

    Yields:
        None. The caller performs the record's writes inside the block.

    Raises:
        ValueError: If ``name`` is not a valid savepoint identifier.
        Exception: Re-raises whatever exception was raised inside the
            ``with`` block, after rolling back to the savepoint.
    """
    _validate_savepoint_name(name)
    cur.execute(f"SAVEPOINT {name}")
    try:
        yield
    except Exception:
        cur.execute(f"ROLLBACK TO SAVEPOINT {name}")
        raise
    else:
        cur.execute(f"RELEASE SAVEPOINT {name}")
