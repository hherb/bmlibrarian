"""Regression tests for CLI authentication connection handling.

Guards against the bug where ``setup_config_with_auth`` called
``DatabaseManager.get_connection()`` (a ``@contextmanager``) without
entering it, passing a ``_GeneratorContextManager`` object instead of a
psycopg connection into ``config.set_user_context``. Every ``--user``
login then failed ("Failed to setup user context"), and database-backed
settings were unreachable from the CLI.

Also guards against the three-way settings-category whitelist drift that
made ``sync_to_database()`` partially fail on every call.

Hermetic: no PostgreSQL or Ollama required.
"""

from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any, Iterator, List

import pytest

import bmlibrarian.cli.auth_helper as auth_helper_module
from bmlibrarian.cli.auth_helper import setup_config_with_auth


class _FakeConnection:
    """Minimal stand-in for a psycopg Connection."""

    def cursor(self, *args: Any, **kwargs: Any) -> None:  # pragma: no cover
        raise NotImplementedError("not needed for this test")


class _FakePersistentConnection:
    """Mimics database.PersistentConnection (.connection / .release())."""

    def __init__(self) -> None:
        self.connection = _FakeConnection()
        self.released = False

    def release(self) -> None:
        self.released = True


class _FakeDBManager:
    """Mimics DatabaseManager's connection API shapes."""

    def __init__(self) -> None:
        self.persistent = _FakePersistentConnection()

    @contextmanager
    def get_connection(self) -> Iterator[_FakeConnection]:
        # Real get_connection is a @contextmanager returning a pool conn;
        # calling it without `with` yields a _GeneratorContextManager.
        yield _FakeConnection()

    def acquire_persistent_connection(self) -> _FakePersistentConnection:
        return self.persistent


class _FakeConfig:
    """Records what setup_config_with_auth passes to set_user_context."""

    def __init__(self) -> None:
        self.received_connections: List[Any] = []

    def set_user_context(self, user_id: int, connection: Any,
                         session_token: Any = None) -> None:
        self.received_connections.append(connection)

    def has_user_context(self) -> bool:
        return bool(self.received_connections)


def test_login_passes_usable_connection_to_set_user_context(monkeypatch) -> None:
    """The object handed to set_user_context must be a usable connection."""
    fake_config = _FakeConfig()
    fake_db = _FakeDBManager()

    import bmlibrarian.config as config_module
    import bmlibrarian.database as database_module

    monkeypatch.setattr(config_module, "get_config", lambda: fake_config)
    monkeypatch.setattr(database_module, "get_db_manager", lambda: fake_db)
    monkeypatch.setattr(
        auth_helper_module,
        "authenticate_cli",
        lambda **kwargs: SimpleNamespace(
            success=True, user_id=1, username="alice",
            session_token="tok", error_message=None,
        ),
    )

    args = SimpleNamespace(
        user="alice", password="secret", session_token=None,
        save_session=False, logout=False,
        sync_to_db=False, sync_from_db=False,
        export_config=None, import_config=None,
    )

    success, error = setup_config_with_auth(args)

    assert success, f"login failed: {error}"
    assert len(fake_config.received_connections) == 1
    conn = fake_config.received_connections[0]
    assert hasattr(conn, "cursor"), (
        f"set_user_context received {type(conn).__name__!r} instead of a "
        "usable connection - get_connection() context manager was never entered"
    )


def test_settings_manager_rolls_back_on_error() -> None:
    """A failed statement must roll the shared connection back, not wedge it.

    Without the rollback, one error leaves a long-lived connection in
    PostgreSQL's aborted-transaction state and every later settings
    operation fails until the process restarts.
    """
    from unittest.mock import MagicMock

    from bmlibrarian.auth.user_settings import UserSettingsManager

    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value.execute.side_effect = (
        RuntimeError("duplicate key")
    )

    manager = UserSettingsManager(conn, user_id=1)

    with pytest.raises(RuntimeError, match="duplicate key"):
        manager.set("models", {"query_agent": "gpt-oss:20b"})

    conn.rollback.assert_called_once()


def test_settings_category_whitelists_are_in_sync() -> None:
    """config and auth must agree on valid settings categories.

    Drift here means sync_to_database() silently fails for the categories
    only one side knows about.
    """
    from bmlibrarian.auth.user_settings import VALID_CATEGORIES
    from bmlibrarian.config import VALID_SETTINGS_CATEGORIES

    assert set(VALID_CATEGORIES) == set(VALID_SETTINGS_CATEGORIES), (
        "settings-category whitelists have drifted: "
        f"config-only={set(VALID_SETTINGS_CATEGORIES) - set(VALID_CATEGORIES)}, "
        f"auth-only={set(VALID_CATEGORIES) - set(VALID_SETTINGS_CATEGORIES)}"
    )
