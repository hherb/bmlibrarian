"""
Tests for bmlibrarian.db_test_guard: the test suite must never change production.

In October 2026 a full test run applied migrations 031 and 032 to the
production database: tests call get_db_manager(), which reads the default
~/.bmlibrarian/.env (production) and auto-migrates. The guard makes that
impossible: under pytest, every database not recognisably a dev/test database
is protected, is never migrated, and gets read-only connections.
"""

from pathlib import Path
from typing import Optional, Tuple
from unittest.mock import MagicMock, patch

import pytest
from psycopg.conninfo import conninfo_to_dict

from bmlibrarian import db_test_guard as guard
from bmlibrarian.migrations import MigrationManager

UNDER_PYTEST = {"pytest": object()}
NOT_UNDER_PYTEST: dict = {}
NO_ENV: dict = {}


class TestPureHelpers:
    """Detection of pytest and of protected databases."""

    def test_running_under_pytest(self) -> None:
        """pytest is detected from the module table."""
        assert guard.running_under_pytest(UNDER_PYTEST) is True
        assert guard.running_under_pytest(NOT_UNDER_PYTEST) is False

    @pytest.mark.parametrize("name", ["bmlibrarian_dev", "dev_db", "dev", "test_db", "testdb",
                                      "bmlibrarian-test", "kb_development", "BMLIBRARIAN_DEV"])
    def test_dev_and_test_databases_are_not_protected(self, name: str) -> None:
        """Names with a dev/test token may be changed by tests."""
        assert guard.is_protected_database(name, NO_ENV) is False

    @pytest.mark.parametrize("name", ["knowledgebase", "bmlibrarian", "mydb", "latest_kb", "devices",
                                      "postgres", None, ""])
    def test_everything_else_is_protected(self, name: Optional[str]) -> None:
        """Allow-list: production (old and PG18), unknown names and a missing name are protected."""
        assert guard.is_protected_database(name, NO_ENV) is True

    def test_explicit_allow_list(self) -> None:
        """BMLIBRARIAN_TEST_ALLOWED_DATABASES unprotects exactly the names it lists."""
        env = {guard.ALLOWED_DATABASES_ENV: " scratch , other "}
        assert guard.is_protected_database("scratch", env) is False
        assert guard.is_protected_database("other", env) is False
        assert guard.is_protected_database("knowledgebase", env) is True

    def test_database_name_from_conninfo(self) -> None:
        """dbname is read from the conninfo, None if absent."""
        assert guard.database_name("host=localhost port=5432 dbname=knowledgebase user=u") == "knowledgebase"
        assert guard.database_name("host=localhost user=u") is None

    def test_guard_applies_only_to_protected_database_under_pytest(self) -> None:
        """Both conditions are required: under pytest and a protected database."""
        assert guard.guard_applies("knowledgebase", UNDER_PYTEST, NO_ENV) is True
        assert guard.guard_applies("bmlibrarian", UNDER_PYTEST, NO_ENV) is True
        assert guard.guard_applies(None, UNDER_PYTEST, NO_ENV) is True
        assert guard.guard_applies("knowledgebase", NOT_UNDER_PYTEST, NO_ENV) is False
        assert guard.guard_applies("bmlibrarian_dev", UNDER_PYTEST, NO_ENV) is False


class TestReadOnlyConninfo:
    """The read-only option is written into the connection string itself."""

    def test_protected_conninfo_gets_read_only_option(self) -> None:
        """The option is added and the other parameters are kept."""
        conninfo = guard.guarded_conninfo("dbname=knowledgebase user=u", UNDER_PYTEST, NO_ENV)
        params = conninfo_to_dict(conninfo)
        assert params["options"] == guard.READ_ONLY_OPTIONS
        assert params["dbname"] == "knowledgebase" and params["user"] == "u"

    def test_conninfo_without_dbname_is_read_only(self) -> None:
        """A conninfo naming no database fails closed."""
        conninfo = guard.guarded_conninfo("host=localhost user=u", UNDER_PYTEST, NO_ENV)
        assert conninfo_to_dict(conninfo)["options"] == guard.READ_ONLY_OPTIONS

    def test_existing_options_are_kept_and_option_added_once(self) -> None:
        """Existing -c settings survive, and guarding twice adds nothing."""
        conninfo = guard.guarded_conninfo("dbname=knowledgebase options='-c work_mem=64MB'", UNDER_PYTEST, NO_ENV)
        assert conninfo_to_dict(conninfo)["options"] == f"-c work_mem=64MB {guard.READ_ONLY_OPTIONS}"
        again = guard.guarded_conninfo(conninfo, UNDER_PYTEST, NO_ENV)
        assert conninfo_to_dict(again)["options"] == conninfo_to_dict(conninfo)["options"]

    def test_dev_database_and_no_pytest_are_unchanged(self) -> None:
        """Unguarded conninfos are returned verbatim."""
        assert guard.guarded_conninfo("dbname=bmlibrarian_dev user=u", UNDER_PYTEST, NO_ENV) == \
            "dbname=bmlibrarian_dev user=u"
        assert guard.guarded_conninfo("dbname=knowledgebase user=u", NOT_UNDER_PYTEST, NO_ENV) == \
            "dbname=knowledgebase user=u"

    def test_connect_kwargs(self) -> None:
        """psycopg.connect() kwargs carry the option only for a guarded database."""
        assert guard.guarded_connect_kwargs("knowledgebase", None, UNDER_PYTEST, NO_ENV) == \
            {"options": guard.READ_ONLY_OPTIONS}
        assert guard.guarded_connect_kwargs("bmlibrarian_dev", None, UNDER_PYTEST, NO_ENV) == {}


class TestMigrationManagerGuard:
    """Migrations are refused for a protected database while pytest is loaded."""

    @staticmethod
    def manager(database: str) -> MigrationManager:
        """A MigrationManager whose connections must never be opened."""
        manager = MigrationManager("localhost", "5432", "u", "p", database)
        manager._get_connection = MagicMock(side_effect=AssertionError("must not connect"))
        return manager

    @pytest.mark.parametrize("database", ["knowledgebase", "bmlibrarian"])
    def test_apply_pending_refuses_production(self, tmp_path: Path, database: str) -> None:
        """Both production databases (old and PG18) refuse migrations."""
        with pytest.raises(guard.ProtectedDatabaseError):
            self.manager(database).apply_pending_migrations(tmp_path)

    def test_initialize_refuses_production(self, tmp_path: Path) -> None:
        """Schema initialisation is refused."""
        with pytest.raises(guard.ProtectedDatabaseError):
            self.manager("knowledgebase").initialize_database(tmp_path / "baseline_schema.sql")

    def test_mark_applied_refuses_production(self, tmp_path: Path) -> None:
        """Recording a migration as applied is refused."""
        migration = tmp_path / "999_x.sql"
        migration.write_text("SELECT 1;")
        with pytest.raises(guard.ProtectedDatabaseError):
            self.manager("knowledgebase").mark_migration_applied(migration)

    def test_connections_to_protected_database_are_read_only(self) -> None:
        """Direct and maintenance connections are judged by the database they act for."""
        from bmlibrarian import migrations
        manager = migrations.MigrationManager("localhost", "5432", "u", "p", "knowledgebase")
        with patch.object(migrations.psycopg, "connect") as connect:
            manager._get_connection("knowledgebase")
            manager._get_connection("postgres", guard_as="bmlibrarian_dev")
        assert connect.call_args_list[0].kwargs["options"] == guard.READ_ONLY_OPTIONS
        assert "options" not in connect.call_args_list[1].kwargs


class TestDatabaseManagerGuard:
    """DatabaseManager skips auto-migration and opens read-only pools for protected databases."""

    @staticmethod
    def build(conninfo: str) -> Tuple[object, MagicMock, MagicMock]:
        """A DatabaseManager on ``conninfo`` with the pool and migrations mocked."""
        from bmlibrarian import database
        with patch.object(database, "ConnectionPool") as pool_cls, \
             patch.object(database.DatabaseManager, "_warmup_pool"), \
             patch.object(database.DatabaseManager, "_apply_pending_migrations") as migrate, \
             patch.object(database.DatabaseManager, "_cache_source_ids"):
            manager = database.DatabaseManager(auto_migrate=True, conninfo=conninfo)
        return manager, pool_cls, migrate

    def test_production_pool_is_read_only_and_not_migrated(self) -> None:
        """Wiring check: the pool really receives the read-only conninfo."""
        manager, pool_cls, migrate = self.build("host=localhost dbname=knowledgebase user=u")
        migrate.assert_not_called()
        pool_conninfo = pool_cls.call_args.kwargs["conninfo"]
        assert conninfo_to_dict(pool_conninfo)["options"] == guard.READ_ONLY_OPTIONS
        # Worker processes get manager.conninfo: it must carry the option too.
        assert manager.conninfo == pool_conninfo

    def test_dev_pool_is_writable_and_migrated(self) -> None:
        """A dev database is migrated and writable as before."""
        manager, pool_cls, migrate = self.build("host=localhost dbname=bmlibrarian_dev user=u")
        migrate.assert_called_once()
        assert "options" not in conninfo_to_dict(pool_cls.call_args.kwargs["conninfo"])
