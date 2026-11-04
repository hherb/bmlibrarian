"""audit_cursor rolls the shared audit connection back when a tracker call fails (#341)."""

import re
from pathlib import Path
from unittest.mock import MagicMock

import psycopg
import pytest

from bmlibrarian.audit import CitationTracker
from bmlibrarian.audit.connection import audit_cursor

SRC = Path(__file__).parent.parent / "src" / "bmlibrarian"
# Everything that runs queries on an audit connection; connection.py is the helper itself
AUDIT_CONNECTION_USERS = [
    *(p for p in (SRC / "audit").glob("*.py") if p.name != "connection.py"),
    SRC / "gui" / "qt" / "plugins" / "audit_validation" / "data_manager.py",
]
BARE_CURSOR = re.compile(r"\bconn\.cursor\(")


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


def test_interrupt_rolls_back_too() -> None:
    """Ctrl-C between statements must not leave half a write for the next commit."""
    conn = MagicMock()

    with pytest.raises(KeyboardInterrupt):
        with audit_cursor(conn):
            raise KeyboardInterrupt

    conn.rollback.assert_called_once()


@pytest.mark.parametrize("path", AUDIT_CONNECTION_USERS, ids=lambda p: p.name)
def test_no_bare_cursor_on_an_audit_connection(path: Path) -> None:
    """Every query on an audit connection goes through audit_cursor."""
    assert not BARE_CURSOR.search(path.read_text()), f"{path.name} opens conn.cursor() directly"
