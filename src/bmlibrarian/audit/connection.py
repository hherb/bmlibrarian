"""
Cursor helper shared by the audit trackers.

Each caller hands one long-lived, non-autocommit connection to several
trackers (``agents/lifecycle.py`` for the Qt app, ``cli/workflow_agents.py``
for the CLI, the audit-validation plugin's persistent connection for
``ValidationTracker`` and its data manager). A failed statement leaves that
connection in an aborted transaction, after which every later audit call
(read or write) fails with ``InFailedSqlTransaction``, so every query on it
must roll back before re-raising. Code sharing the connection must not leave
uncommitted writes on it, as the rollback would discard them too.
"""

import logging
from contextlib import contextmanager
from typing import Any, Iterator

import psycopg

logger = logging.getLogger(__name__)


@contextmanager
def audit_cursor(conn: psycopg.Connection, **cursor_kwargs: Any) -> Iterator[psycopg.Cursor]:
    """
    Yield a cursor on ``conn``, rolling ``conn`` back if the block raises.

    Trackers commit after each write, so the rollback only discards the
    failed operation. It also runs on ``KeyboardInterrupt``/``SystemExit``,
    so a half-done multi-statement write is never committed by the next
    tracker call. The original exception is re-raised.

    Args:
        conn: The tracker's database connection.
        **cursor_kwargs: Passed to ``conn.cursor()`` (e.g. ``row_factory``).

    Yields:
        The open cursor.
    """
    try:
        with conn.cursor(**cursor_kwargs) as cur:
            yield cur
    except BaseException:
        try:
            conn.rollback()
        except psycopg.Error:
            logger.exception(
                "Rollback of the audit connection failed; the connection is likely "
                "lost and audit tracking stays unavailable until the application restarts"
            )
        raise
