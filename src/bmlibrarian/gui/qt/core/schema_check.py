"""Refuse to run a Qt window on a database whose migrations failed.

Shared by the main app (``BMLibrarianApplication``) and every standalone
window that uses PostgreSQL (labs, review GUIs), so they show the same
"Database Migration Failed" dialog instead of a generic per-widget error
(#342, #378). It runs once at startup and also registers a handler, so a
migration that first fails later (e.g. the server was down at startup and
a worker thread creates the manager) shows the same dialog and quits the
app (#381).
"""

import logging

from PySide6.QtCore import QObject, Qt, QTimer, Signal, Slot
from PySide6.QtWidgets import QApplication, QMessageBox

logger = logging.getLogger(__name__)

MIGRATION_FAILED_TITLE = "Database Migration Failed"
MIGRATION_FAILED_HINT = (
    "The database schema is out of date, so BMLibrarian cannot run. Fix "
    "the cause (often missing table ownership for the database user) and "
    "restart."
)
# Event-loop exit code when a migration fails after startup
MIGRATION_FAILED_EXIT_CODE = 1


class _MigrationFailureNotifier(QObject):
    """Carries a migration failure from any thread to the GUI thread."""

    failed = Signal(str)

    def __init__(self) -> None:
        """Create in the GUI thread, so the queued slot runs there."""
        super().__init__()
        self.failed.connect(self._show_and_quit, Qt.ConnectionType.QueuedConnection)

    @Slot(str)
    def _show_and_quit(self, message: str) -> None:
        """Show the fatal migration dialog, close the windows, end the event loop.

        Args:
            message: The migration error's text.
        """
        QMessageBox.critical(
            QApplication.activeWindow(),
            MIGRATION_FAILED_TITLE,
            f"{message}\n\n{MIGRATION_FAILED_HINT}",
        )
        # exit() skips closeEvent, where the main window stops plugin workers
        QApplication.closeAllWindows()
        QApplication.exit(MIGRATION_FAILED_EXIT_CODE)
        # exit() only ends loops already running: if this ran in a modal's loop
        # before app.exec(), the re-posted exit ends app.exec() too
        QTimer.singleShot(0, _exit_migration_failed)


def _exit_migration_failed() -> None:
    """End the running event loop with ``MIGRATION_FAILED_EXIT_CODE``."""
    QApplication.exit(MIGRATION_FAILED_EXIT_CODE)


# Kept alive for the process; created by the first check_schema_current()
# that lets the window start
_notifier: _MigrationFailureNotifier | None = None


def _report_late_migration_failure(error: Exception) -> None:
    """Migration failure handler: hand the error to the GUI thread.

    Args:
        error: The ``MigrationError`` raised by ``get_db_manager()``.
    """
    logger.error(f"Database migration failed after startup: {error}")
    if _notifier is not None:
        _notifier.failed.emit(str(error))


def _install_late_failure_handler() -> None:
    """Register the handler that makes a later migration failure fatal too."""
    global _notifier
    from ....database import set_migration_failure_handler

    if _notifier is None:
        _notifier = _MigrationFailureNotifier()
    set_migration_failure_handler(_report_late_migration_failure)


def check_schema_current() -> bool:
    """Create the shared DatabaseManager (applying pending migrations) and install the late-failure handler.

    A migration that fails while being applied leaves the schema outdated,
    so every later write to the affected tables would fail: show the error
    and tell the caller not to start. Any other failure to create the
    manager (no credentials, server down) is left to the widgets, which
    report it when they use the database; if the migration then fails on
    that later attempt, the same dialog is shown, the windows are closed and
    the event loop exits with ``MIGRATION_FAILED_EXIT_CODE``.

    Needs a QApplication (it may show a dialog) and must run in the GUI
    thread. Call it before building the tool's window.

    Returns:
        False if a migration failed (the window must not start), else True.
    """
    from ....database import get_db_manager
    from ....migrations import MigrationError

    try:
        get_db_manager()
    except MigrationError as e:
        logger.error(f"Database migration failed: {e}")
        # Called before any window is built, so there is nowhere to show a toast.
        QMessageBox.critical(None, MIGRATION_FAILED_TITLE, f"{e}\n\n{MIGRATION_FAILED_HINT}")
        return False
    except Exception as e:
        logger.warning(f"Database manager not available at startup: {e}")
    _install_late_failure_handler()
    return True
