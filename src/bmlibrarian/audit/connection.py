"""
Cursor helper shared by the audit trackers.

All trackers share one non-autocommit connection (``agents/lifecycle.py``).
A failed statement leaves that connection in an aborted transaction, after
which every later audit write fails with ``InFailedSqlTransaction``, so a
tracker must roll back before re-raising.
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
    failed operation. The original exception is re-raised.

    Args:
        conn: The tracker's database connection.
        **cursor_kwargs: Passed to ``conn.cursor()`` (e.g. ``row_factory``).

    Yields:
        The open cursor.
    """
    try:
        with conn.cursor(**cursor_kwargs) as cur:
            yield cur
    except Exception:
        try:
            conn.rollback()
        except psycopg.Error:
            logger.exception("Rollback of the audit connection failed")
        raise
