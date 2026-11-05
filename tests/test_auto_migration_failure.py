"""A migration that fails while being applied stops startup (#342).

Before, ``DatabaseManager`` logged "Auto-migration check failed" as a warning
and carried on, so the app ran against an outdated schema and writes to the
affected tables failed later at runtime.
"""

import logging
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, call, patch

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


class TestGetDbManagerRemembersFailure:
    """``get_db_manager()`` re-raises a failed migration without re-running it (#379)."""

    @pytest.fixture(autouse=True)
    def fresh_globals(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Run each test with no global manager and no stored error."""
        monkeypatch.setattr(database, "_db_manager", None)
        monkeypatch.setattr(database, "_db_manager_error", None)

    def test_failure_is_remembered_until_close_database(self) -> None:
        """Later calls raise the same error; ``close_database()`` allows a retry."""
        error = MigrationError("✗ Failed to apply 035_x.sql: denied")
        with patch.object(database, "DatabaseManager", side_effect=error) as cls:
            for _ in range(3):
                with pytest.raises(MigrationError, match="035_x.sql"):
                    database.get_db_manager()
            assert cls.call_count == 1
            database.close_database()
            with pytest.raises(MigrationError):
                database.get_db_manager()
            assert cls.call_count == 2

    def test_other_errors_are_not_remembered(self) -> None:
        """Only a failed migration sticks; e.g. missing credentials are retried."""
        with patch.object(database, "DatabaseManager", side_effect=ValueError("no creds")) as cls:
            for _ in range(2):
                with pytest.raises(ValueError):
                    database.get_db_manager()
        assert cls.call_count == 2
        assert database._db_manager_error is None

    def test_concurrent_callers_create_one_manager(self) -> None:
        """Threads racing on first use migrate once and share one outcome."""
        import threading
        import time

        manager = MagicMock()

        def slow_create() -> MagicMock:
            """Stand in for a DatabaseManager whose migrations take a while."""
            time.sleep(0.05)
            return manager

        with patch.object(database, "DatabaseManager", side_effect=slow_create) as cls:
            results: list = []
            threads = [
                threading.Thread(target=lambda: results.append(database.get_db_manager()))
                for _ in range(4)
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
        assert cls.call_count == 1
        assert results == [manager] * 4

    def test_handler_told_once_about_a_failure(self) -> None:
        """The failure handler hears about the first failure only (#381)."""
        error = MigrationError("✗ Failed to apply 035_x.sql: denied")
        handler = MagicMock()
        database.set_migration_failure_handler(handler)
        with patch.object(database, "DatabaseManager", side_effect=error):
            for _ in range(3):
                with pytest.raises(MigrationError):
                    database.get_db_manager()
        handler.assert_called_once_with(error)

    def test_failing_handler_still_raises_migration_error(self) -> None:
        """A broken handler can't hide the migration failure from the caller."""
        database.set_migration_failure_handler(MagicMock(side_effect=RuntimeError("boom")))
        error = MigrationError("✗ Failed to apply 035_x.sql: denied")
        with patch.object(database, "DatabaseManager", side_effect=error), \
             pytest.raises(MigrationError, match="035_x.sql"):
            database.get_db_manager()

    def test_handler_not_told_about_other_errors(self) -> None:
        """No credentials / server down is not a migration failure."""
        handler = MagicMock()
        database.set_migration_failure_handler(handler)
        with patch.object(database, "DatabaseManager", side_effect=ValueError("no creds")), \
             pytest.raises(ValueError):
            database.get_db_manager()
        handler.assert_not_called()

    def test_handler_calling_get_db_manager_does_not_deadlock(self) -> None:
        """The handler runs outside the (non-reentrant) lock."""
        import threading

        seen: list = []

        def handler(error: Exception) -> None:
            """Ask for the manager again, as a careless handler might."""
            try:
                database.get_db_manager()
            except MigrationError as again:
                seen.append(again)

        database.set_migration_failure_handler(handler)
        error = MigrationError("✗ Failed to apply 035_x.sql: denied")

        def first_call() -> None:
            """The call that runs the failing migration."""
            with pytest.raises(MigrationError):
                database.get_db_manager()

        with patch.object(database, "DatabaseManager", side_effect=error):
            thread = threading.Thread(target=first_call, daemon=True)
            thread.start()
            thread.join(timeout=5)
        assert not thread.is_alive()
        assert seen == [error]


class TestLateMigrationFailureIsFatal:
    """A migration first failing after startup shows the fatal dialog (#381)."""

    @pytest.fixture(autouse=True)
    def fresh_globals(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """No global manager, no stored error, a QApplication to deliver signals."""
        from PySide6.QtWidgets import QApplication

        from bmlibrarian.gui.qt.core import schema_check

        monkeypatch.setattr(database, "_db_manager", None)
        monkeypatch.setattr(database, "_db_manager_error", None)
        # A fresh notifier, so nothing queued here outlives the test
        monkeypatch.setattr(schema_check, "_notifier", None)
        self.qapp = QApplication.instance() or QApplication([])

    def test_worker_thread_failure_reaches_gui_thread_and_quits(self) -> None:
        """Startup could not connect; a worker's later migration failure is fatal."""
        import threading
        import time

        from bmlibrarian.gui.qt.core import schema_check

        with patch.object(database, "get_db_manager", side_effect=ValueError("server down")):
            assert schema_check.check_schema_current() is True

        shown_in: list = []
        worker_errors: list = []

        def worker() -> None:
            """Stand in for a widget's QThread creating the manager."""
            try:
                database.get_db_manager()
            except MigrationError as e:
                worker_errors.append(e)

        error = MigrationError("✗ Failed to apply 035_x.sql: denied")
        fake_qapp = MagicMock()
        with patch.object(database, "DatabaseManager", side_effect=error), \
             patch.object(schema_check, "QApplication", fake_qapp), \
             patch.object(schema_check.QMessageBox, "critical",
                          side_effect=lambda *a: shown_in.append(threading.current_thread())) as critical:
            thread = threading.Thread(target=worker)
            thread.start()
            thread.join()
            assert critical.call_count == 0  # queued, not shown on the worker
            deadline = time.monotonic() + 5
            # The immediate exit, then the re-posted one
            while fake_qapp.exit.call_count < 2 and time.monotonic() < deadline:
                self.qapp.processEvents()
        assert worker_errors == [error]
        assert shown_in == [threading.main_thread()]
        assert critical.call_args.args[1] == schema_check.MIGRATION_FAILED_TITLE
        assert "035_x.sql" in critical.call_args.args[2]
        fake_qapp.closeAllWindows.assert_called_once_with()
        assert fake_qapp.exit.call_args_list == [call(schema_check.MIGRATION_FAILED_EXIT_CODE)] * 2

    def test_exit_survives_a_modal_loop_before_app_exec(self) -> None:
        """A failure handled in a nested loop before exec() still ends exec() with 1."""
        from PySide6.QtCore import QEventLoop, QTimer

        from bmlibrarian.gui.qt.core import schema_check

        notifier = schema_check._MigrationFailureNotifier()
        with patch.object(schema_check.QMessageBox, "critical"), \
             patch.object(schema_check.QApplication, "closeAllWindows"):
            notifier.failed.emit("✗ Failed to apply 035_x.sql: denied")
            modal = QEventLoop()  # stands in for a QMessageBox opened before exec()
            QTimer.singleShot(0, modal.quit)
            modal.exec()
            # Without the re-posted exit this loop would run until the fallback
            QTimer.singleShot(5000, lambda: self.qapp.exit(0))
            assert self.qapp.exec() == schema_check.MIGRATION_FAILED_EXIT_CODE

    def test_startup_migration_failure_installs_no_handler(self) -> None:
        """The startup dialog already covers it; the window never starts."""
        from bmlibrarian.gui.qt.core import schema_check

        error = MigrationError("✗ Failed to apply 035_x.sql: denied")
        with patch.object(database, "get_db_manager", side_effect=error), \
             patch.object(schema_check.QMessageBox, "critical"):
            assert schema_check.check_schema_current() is False
        assert database._migration_failure_handler is None


class TestDirectCallersUseSharedManager:
    """Former ``DatabaseManager()`` callers reuse the shared manager (#381)."""

    def test_audit_plugin_cleanup_keeps_shared_pool_open(self) -> None:
        """The plugin releases its connection but doesn't close the app's pool."""
        from bmlibrarian.gui.qt.plugins.audit_validation import plugin as plugin_mod

        manager = MagicMock()
        with patch.object(plugin_mod, "get_db_manager", return_value=manager), \
             patch.object(plugin_mod, "AuditValidationDataManager"):
            plugin = plugin_mod.AuditValidationPlugin()
            assert plugin._initialize_database() is True
            plugin.cleanup()
        manager.acquire_persistent_connection.return_value.release.assert_called_once()
        manager.close.assert_not_called()

    def test_audit_gui_reviewer_lookup_uses_shared_manager(self) -> None:
        """The reviewer lookup neither builds nor closes its own manager."""
        import importlib.util

        root = Path(__file__).resolve().parent.parent
        spec = importlib.util.spec_from_file_location("gui_audit_validation", root / "audit_validation_gui.py")
        assert spec is not None and spec.loader is not None
        gui = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gui)

        manager = MagicMock()
        cursor = manager.get_connection.return_value.__enter__.return_value.cursor.return_value
        cursor.__enter__.return_value.fetchone.return_value = {"id": 7}
        window = SimpleNamespace(reviewer_name="alice", reviewer_id=None)
        with patch.object(gui, "get_db_manager", return_value=manager):
            gui.AuditValidationMainWindow._lookup_reviewer(window)
        assert window.reviewer_id == 7
        manager.close.assert_not_called()

        # Building the window uses only methods the plugin has (no initialize())
        window.setCentralWidget = MagicMock()
        window._lookup_reviewer = MagicMock()
        with patch.object(gui, "AuditValidationPlugin", autospec=True) as plugin_cls:
            gui.AuditValidationMainWindow._initialize_plugin(window)
        window.setCentralWidget.assert_called_once_with(
            plugin_cls.return_value.create_widget.return_value
        )


def _exit_code(entry: Any) -> Any:
    """Run a launcher entry point; return its exit code (returned or via sys.exit)."""
    try:
        return entry()
    except SystemExit as exit_info:
        return exit_info.code


class TestStandaloneWindowsCheckSchema:
    """Standalone windows run the startup migration check too (#378)."""

    @staticmethod
    def _launcher_patches(standalone: Any, schema_ok: bool) -> tuple[MagicMock, list]:
        """Patches that keep ``run_*_standalone`` from showing anything."""
        qapp = MagicMock()
        qapp.exec.return_value = 0
        return qapp, [
            patch.object(standalone, "_ensure_application", return_value=qapp),
            patch.object(standalone, "_apply_theme"),
            patch.object(standalone, "_show_window"),
            patch.object(standalone, "check_schema_current", return_value=schema_ok),
        ]

    def test_plugin_not_created_when_migration_failed(self) -> None:
        """A failed check exits before the plugin factory runs."""
        from contextlib import ExitStack

        from bmlibrarian.gui.qt.core import standalone

        create_plugin = MagicMock()
        qapp, patches = self._launcher_patches(standalone, schema_ok=False)
        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            code = standalone.run_plugin_standalone(create_plugin)
        assert code == standalone.STARTUP_FAILURE_EXIT_CODE
        create_plugin.assert_not_called()
        qapp.exec.assert_not_called()

    @pytest.mark.parametrize("check_schema, checks", [(True, 1), (False, 0)])
    def test_widget_check_can_be_skipped(self, check_schema: bool, checks: int) -> None:
        """``check_schema=False`` (SQLite review packages) skips the check."""
        from contextlib import ExitStack

        from bmlibrarian.gui.qt.core import standalone

        _, patches = self._launcher_patches(standalone, schema_ok=True)
        with ExitStack() as stack:
            mocks = [stack.enter_context(p) for p in patches]
            assert standalone.run_widget_standalone(MagicMock, "T", check_schema=check_schema) == 0
        assert mocks[3].call_count == checks

    def test_widget_not_created_when_migration_failed(self) -> None:
        """A failed check exits before the widget factory runs."""
        from contextlib import ExitStack

        from bmlibrarian.gui.qt.core import standalone

        widget_factory = MagicMock()
        qapp, patches = self._launcher_patches(standalone, schema_ok=False)
        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            code = standalone.run_widget_standalone(widget_factory, "T")
        assert code == standalone.STARTUP_FAILURE_EXIT_CODE
        widget_factory.assert_not_called()
        qapp.exec.assert_not_called()

    @pytest.mark.parametrize("module, window, entry", [
        ("bmlibrarian.lab.transparency_lab", "TransparencyLabWindow", "main"),
        ("bmlibrarian.lab.paper_checker_lab.main_window", "PaperCheckerLab", "main"),
        ("bmlibrarian.lab.paper_reviewer_lab.main_window", "PaperReviewerLab", "main"),
        ("bmlibrarian.lab.paper_weight_lab.main_window", "PaperWeightLab", "main"),
        ("bmlibrarian.lab.pubmed_search_lab", "PubMedSearchLabWindow",
         "run_pubmed_search_lab"),
    ])
    def test_lab_main_stops_before_window(self, module: str, window: str, entry: str) -> None:
        """Each lab entry point exits 1 without building its window."""
        import importlib

        from bmlibrarian.gui.qt.core import schema_check
        from bmlibrarian.gui.qt.resources.styles import theme_generator

        lab = importlib.import_module(module)
        # The theme needs a real QApplication (the PubMed lab builds it first)
        with patch.object(lab, "QApplication"), \
             patch.object(theme_generator, "generate_default_theme", return_value=""), \
             patch.object(lab, window) as window_cls, \
             patch.object(schema_check, "check_schema_current", return_value=False):
            assert _exit_code(getattr(lab, entry)) == 1
        window_cls.assert_not_called()

    def test_pubmed_lab_returns_event_loop_exit_code(self) -> None:
        """A late migration failure's exit code 1 reaches the caller (#381)."""
        from bmlibrarian.gui.qt.core import schema_check
        from bmlibrarian.gui.qt.resources.styles import theme_generator
        from bmlibrarian.lab import pubmed_search_lab as lab

        with patch.object(lab, "QApplication") as qapp_cls, \
             patch.object(theme_generator, "generate_default_theme", return_value=""), \
             patch.object(lab, "PubMedSearchLabWindow"), \
             patch.object(schema_check, "check_schema_current", return_value=True):
            qapp_cls.instance.return_value.exec.return_value = 1
            assert lab.run_pubmed_search_lab() == 1

    @pytest.mark.parametrize("script, window, argv", [
        ("systematic_review_gui.py", "SystematicReviewMainWindow", ["--review-dir"]),
        ("audit_validation_gui.py", "AuditValidationMainWindow", ["--user", "alice"]),
        ("scripts/pdf_verification_gui.py", "PDFVerificationGUI", []),
        ("scripts/pdflab.py", "PDFConversionLabWindow", []),
    ])
    def test_gui_main_stops_before_window(
        self, tmp_path: Path, script: str, window: str, argv: list[str]
    ) -> None:
        """The script-level standalone GUIs exit 1 without a window."""
        import importlib.util

        from bmlibrarian.gui.qt.core import schema_check

        if argv == ["--review-dir"]:
            argv = argv + [str(tmp_path)]
        root = Path(__file__).resolve().parent.parent
        spec = importlib.util.spec_from_file_location(f"gui_{Path(script).stem}", root / script)
        assert spec is not None and spec.loader is not None
        gui = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gui)
        with patch.object(gui, "QApplication"), \
             patch.object(gui, window) as window_cls, \
             patch.object(gui.sys, "argv", [script, *argv]), \
             patch.object(schema_check, "check_schema_current", return_value=False):
            assert _exit_code(gui.main) == 1
        window_cls.assert_not_called()
