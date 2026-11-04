"""audit_cursor rolls the shared audit connection back when a tracker call fails (#341)."""

from unittest.mock import MagicMock

import psycopg
import pytest

from bmlibrarian.audit import CitationTracker
from bmlibrarian.audit.connection import audit_cursor


def test_failed_block_rolls_back_and_reraises() -> None:
    """The error reaches the caller and the connection leaves its aborted transaction."""
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value.execute.side_effect = psycopg.Error("fk")

    with pytest.raises(psycopg.Error):
        CitationTracker(conn).get_citations_for_document(1, 2)

    conn.rollback.assert_called_once()


def test_successful_block_does_not_roll_back() -> None:
    """A working block leaves the transaction to the tracker's own commit."""
    conn = MagicMock()

    with audit_cursor(conn, row_factory="rf") as cur:
        assert cur is conn.cursor.return_value.__enter__.return_value

    conn.cursor.assert_called_once_with(row_factory="rf")
    conn.rollback.assert_not_called()


def test_failed_rollback_keeps_the_original_error() -> None:
    """A broken connection whose rollback also fails still reports the first error."""
    conn = MagicMock()
    conn.rollback.side_effect = psycopg.OperationalError("connection lost")

    with pytest.raises(ValueError, match="original"):
        with audit_cursor(conn):
            raise ValueError("original")
