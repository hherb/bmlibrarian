"""A migration that fails while being applied stops startup (#342).

Before, ``DatabaseManager`` logged "Auto-migration check failed" as a warning
and carried on, so the app ran against an outdated schema and writes to the
affected tables failed later at runtime.
"""

import logging
from pathlib import Path
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


def run_apply(
    migrations_dir: Path,
    create_side_effect: Any = None,
    applied_side_effect: Any = None,
) -> tuple[Any, MagicMock]:
    """Run ``apply_pending_migrations`` with the database calls mocked.

    Returns:
        (the applied count, or the exception raised; the mocked ``_apply_sql_file``).
    """
    manager = MigrationManager("localhost", "5432", "u", "p", "bmlibrarian_dev")
    with patch.object(MigrationManager, "_create_migrations_table", side_effect=create_side_effect), \
         patch.object(MigrationManager, "_get_applied_migrations",
                      side_effect=applied_side_effect, return_value=[]), \
         patch.object(MigrationManager, "_apply_sql_file") as apply_sql, \
         patch.object(MigrationManager, "_record_migration"), \
         patch("builtins.print"):
        try:
            result: Any = manager.apply_pending_migrations(migrations_dir)
        except Exception as e:  # returned so each test can assert on it
            result = e
    return result, apply_sql


class TestMigrationManagerFailureModes:
    """Only "could not check" returns 0; a pending file that can't be applied raises."""

    def test_unreadable_migration_file_raises(self, tmp_path: Path) -> None:
        """A pending file that is not UTF-8 is a failed apply, not a failed check."""
        (tmp_path / "001_bad.sql").write_bytes(b"-- caf\xe9\n")
        result, apply_sql = run_apply(tmp_path)
        assert isinstance(result, MigrationError)
        assert "001_bad.sql" in str(result)
        apply_sql.assert_not_called()

    def test_table_create_failure_still_applies_pending(self, tmp_path: Path) -> None:
        """No CREATE on the schema, but the table is readable: pending files still run."""
        (tmp_path / "001_x.sql").write_text("-- x")
        result, apply_sql = run_apply(tmp_path, create_side_effect=Exception("permission denied for schema public"))
        assert result == 1
        apply_sql.assert_called_once()

    def test_table_create_and_read_failure_returns_zero(self, tmp_path: Path) -> None:
        """Neither creating nor reading the tracking table works: state unknown, not fatal."""
        (tmp_path / "001_x.sql").write_text("-- x")
        result, apply_sql = run_apply(
            tmp_path,
            create_side_effect=Exception("permission denied for schema public"),
            applied_side_effect=Exception("relation does not exist"),
        )
        assert result == 0
        apply_sql.assert_not_called()


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

    @pytest.mark.parametrize("schema_ok, expected_windows", [(False, 0), (True, 1)])
    def test_run_stops_before_main_window(self, schema_ok: bool, expected_windows: int) -> None:
        """``run()`` returns 1 without a main window when the schema check fails."""
        from bmlibrarian.gui.qt.core import application as app_mod

        fake_app = MagicMock()
        fake_app._args.user = "u"
        fake_app._auto_login.return_value = True
        fake_app._check_schema_current.return_value = schema_ok
        fake_app.qapp.exec.return_value = 0
        with patch.object(app_mod, "BMLibrarianMainWindow") as main_window:
            code = app_mod.BMLibrarianApplication.run(fake_app)
        assert code == (0 if schema_ok else 1)
        assert main_window.call_count == expected_windows
        assert fake_app._setup_user_context.call_count == expected_windows
        fake_app._cleanup.assert_called_once()


class TestCliStopsOnMigrationError:
    """``bmlibrarian_cli.py`` agent setup stops on a failed migration (#342)."""

    def test_setup_agents_fails_with_migration_message(self) -> None:
        """The MigrationError is not swallowed as "audit tracking unavailable"."""
        from bmlibrarian.cli.workflow_agents import WorkflowAgentManager

        ui = MagicMock()
        manager = WorkflowAgentManager(config=MagicMock(), ui=ui, query_processor=MagicMock())
        error = MigrationError("✗ Failed to apply 035_x.sql: denied")
        with patch.object(database, "get_db_manager", side_effect=error), \
             patch("bmlibrarian.cli.workflow_agents.AgentFactory") as factory:
            assert manager.setup_agents() is False
        factory.create_all_agents.assert_not_called()
        assert "035_x.sql" in ui.show_error_message.call_args.args[0]
