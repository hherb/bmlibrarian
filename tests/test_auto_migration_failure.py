"""A migration that fails while being applied stops startup (#342).

Before, ``DatabaseManager`` logged "Auto-migration check failed" as a warning
and carried on, so the app ran against an outdated schema and writes to the
affected tables failed later at runtime.
"""

import logging
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from bmlibrarian import database
from bmlibrarian.migrations import MigrationError, MigrationManager

# A dev name, so db_test_guard lets auto-migration run (against mocks only).
DEV_CONNINFO = "host=localhost dbname=bmlibrarian_dev user=u"


def build_manager(apply_side_effect: Any) -> tuple[Any, MagicMock]:
    """Construct a DatabaseManager whose migration run fails with ``apply_side_effect``.

    Returns:
        (the manager, or the exception it raised; the mocked pool class).
    """
    migration_manager = MagicMock()
    migration_manager.apply_pending_migrations.side_effect = apply_side_effect
    with patch.object(database, "ConnectionPool") as pool_cls, \
         patch.object(database.DatabaseManager, "_warmup_pool"), \
         patch.object(database.DatabaseManager, "_cache_source_ids"), \
         patch.object(MigrationManager, "from_env", return_value=migration_manager):
        try:
            result: Any = database.DatabaseManager(auto_migrate=True, conninfo=DEV_CONNINFO)
        except Exception as e:  # returned so each test can assert on it
            result = e
    return result, pool_cls


class TestDatabaseManagerMigrationFailure:
    """DatabaseManager raises on a failed migration, warns on a failed check."""

    def test_failed_migration_raises_and_closes_pool(self) -> None:
        """A failed migration propagates and the opened pool is not leaked."""
        result, pool_cls = build_manager(MigrationError("✗ Failed to apply 035_x.sql: denied"))
        assert isinstance(result, MigrationError)
        assert "035_x.sql" in str(result)
        pool_cls.return_value.close.assert_called_once()

    def test_other_errors_only_warn(self, caplog: pytest.LogCaptureFixture) -> None:
        """Not being able to check migrations is still only a warning."""
        with caplog.at_level(logging.WARNING, logger="bmlibrarian.database"):
            result, pool_cls = build_manager(OSError("no access"))
        assert isinstance(result, database.DatabaseManager)
        assert "Auto-migration check failed" in caplog.text
        pool_cls.return_value.close.assert_not_called()

    def test_migration_manager_raises_migration_error(self, tmp_path: Any) -> None:
        """MigrationManager signals a failed apply as MigrationError (a RuntimeError)."""
        (tmp_path / "001_test.sql").write_text("-- test")
        manager = MigrationManager("localhost", "5432", "u", "p", "bmlibrarian_dev")
        with patch.object(MigrationManager, "_create_migrations_table"), \
             patch.object(MigrationManager, "_get_applied_migrations", return_value=[]), \
             patch.object(MigrationManager, "_apply_sql_file", side_effect=Exception("SQL error")), \
             patch.object(MigrationManager, "_record_migration") as record, \
             patch("builtins.print"):
            with pytest.raises(MigrationError, match="001_test.sql: SQL error"):
                manager.apply_pending_migrations(tmp_path)
        record.assert_not_called()
        assert issubclass(MigrationError, RuntimeError)


class TestQtStartupSchemaCheck:
    """The Qt app refuses to start when a migration failed."""

    @staticmethod
    def check(side_effect: Any) -> tuple[bool, MagicMock]:
        """Run ``_check_schema_current`` with ``get_db_manager`` failing as given."""
        from PySide6.QtWidgets import QMessageBox

        from bmlibrarian.gui.qt.core.application import BMLibrarianApplication

        fake_app = SimpleNamespace(logger=logging.getLogger("test"))
        with patch.object(database, "get_db_manager", side_effect=side_effect), \
             patch.object(QMessageBox, "critical") as critical:
            ok = BMLibrarianApplication._check_schema_current(fake_app)  # type: ignore[arg-type]
        return ok, critical

    def test_migration_error_shows_error_and_stops(self) -> None:
        """A failed migration is shown to the user and blocks startup."""
        ok, critical = self.check(MigrationError("✗ Failed to apply 035_x.sql: denied"))
        assert ok is False
        critical.assert_called_once()
        assert "035_x.sql" in critical.call_args.args[2]

    def test_other_db_errors_do_not_block_startup(self) -> None:
        """Other manager failures are left to the tabs, as before."""
        ok, critical = self.check(ValueError("Database credentials not configured"))
        assert ok is True
        critical.assert_not_called()
