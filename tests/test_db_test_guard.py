"""
Tests for bmlibrarian.db_test_guard: the test suite must never change production.

In October 2026 a full test run applied migrations 031 and 032 to the
production database: tests call get_db_manager(), which reads the default
~/.bmlibrarian/.env (production) and auto-migrates. The guard makes that
impossible: under pytest, a protected database is never migrated and its
connections are read-only.
"""

from unittest.mock import MagicMock, patch

import pytest

from bmlibrarian import db_test_guard as guard

UNDER_PYTEST = {"pytest": object()}
NOT_UNDER_PYTEST: dict = {}


class TestPureHelpers:
    """Detection of pytest and of protected databases."""

    def test_running_under_pytest(self) -> None:
        assert guard.running_under_pytest(UNDER_PYTEST) is True
        assert guard.running_under_pytest(NOT_UNDER_PYTEST) is False

    def test_production_is_protected_dev_is_not(self) -> None:
        assert guard.is_protected_database("knowledgebase") is True
        assert guard.is_protected_database("bmlibrarian_dev") is False
        assert guard.is_protected_database(None) is False

    def test_database_name_from_conninfo(self) -> None:
        assert guard.database_name("host=localhost port=5432 dbname=knowledgebase user=u") == "knowledgebase"
        assert guard.database_name("host=localhost user=u") is None

    def test_guard_applies_only_to_protected_database_under_pytest(self) -> None:
        assert guard.guard_applies("knowledgebase", UNDER_PYTEST) is True
        assert guard.guard_applies("knowledgebase", NOT_UNDER_PYTEST) is False
        assert guard.guard_applies("bmlibrarian_dev", UNDER_PYTEST) is False

    def test_pool_kwargs_make_protected_connections_read_only(self) -> None:
        kwargs = guard.pool_connection_kwargs("dbname=knowledgebase user=u", UNDER_PYTEST)
        assert kwargs == {"options": "-c default_transaction_read_only=on"}
        assert guard.pool_connection_kwargs("dbname=bmlibrarian_dev user=u", UNDER_PYTEST) == {}
        assert guard.pool_connection_kwargs("dbname=knowledgebase user=u", NOT_UNDER_PYTEST) == {}


class TestMigrationManagerGuard:
    """Migrations are refused for a protected database while pytest is loaded."""

    def test_apply_pending_refuses_production(self, tmp_path) -> None:
        from bmlibrarian.migrations import MigrationManager
        manager = MigrationManager("localhost", "5432", "u", "p", "knowledgebase")
        manager.get_connection = MagicMock(side_effect=AssertionError("must not connect"))
        with pytest.raises(guard.ProtectedDatabaseError):
            manager.apply_pending_migrations(tmp_path)

    def test_initialize_refuses_production(self, tmp_path) -> None:
        from bmlibrarian.migrations import MigrationManager
        manager = MigrationManager("localhost", "5432", "u", "p", "knowledgebase")
        manager.get_connection = MagicMock(side_effect=AssertionError("must not connect"))
        with pytest.raises(guard.ProtectedDatabaseError):
            manager.initialize_database(tmp_path / "baseline_schema.sql")


class TestDatabaseManagerGuard:
    """DatabaseManager skips auto-migration on a protected database under pytest."""

    def test_auto_migrate_is_skipped_for_production(self) -> None:
        from bmlibrarian import database

        def fake_init(self, conninfo=None):
            self._conninfo = "host=localhost dbname=knowledgebase user=u"

        with patch.object(database.DatabaseManager, "_init_pool", fake_init), \
             patch.object(database.DatabaseManager, "_apply_pending_migrations") as migrate, \
             patch.object(database.DatabaseManager, "_cache_source_ids"):
            database.DatabaseManager(auto_migrate=True)
        migrate.assert_not_called()

    def test_auto_migrate_runs_for_dev_database(self) -> None:
        from bmlibrarian import database

        def fake_init(self, conninfo=None):
            self._conninfo = "host=localhost dbname=bmlibrarian_dev user=u"

        with patch.object(database.DatabaseManager, "_init_pool", fake_init), \
             patch.object(database.DatabaseManager, "_apply_pending_migrations") as migrate, \
             patch.object(database.DatabaseManager, "_cache_source_ids"):
            database.DatabaseManager(auto_migrate=True)
        migrate.assert_called_once()
