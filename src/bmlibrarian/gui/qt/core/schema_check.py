"""Refuse to start a Qt window on a database whose migrations failed.

Shared by the main app (``BMLibrarianApplication``) and every standalone
window that uses PostgreSQL (labs, review GUIs), so they show the same
"Database Migration Failed" dialog instead of a generic per-widget error
(#342, #378). It runs once at startup; a migration that first fails later
(e.g. the server was down at startup) is reported by the widget that hit it.
"""

import logging

from PySide6.QtWidgets import QMessageBox

logger = logging.getLogger(__name__)

MIGRATION_FAILED_TITLE = "Database Migration Failed"
MIGRATION_FAILED_HINT = (
    "The database schema is out of date, so BMLibrarian cannot start. Fix "
    "the cause (often missing table ownership for the database user) and "
    "restart."
)


def check_schema_current() -> bool:
    """Create the shared DatabaseManager, which applies pending migrations.

    A migration that fails while being applied leaves the schema outdated,
    so every later write to the affected tables would fail: show the error
    and tell the caller not to start. Any other failure to create the
    manager (no credentials, server down) is left to the widgets, which
    report it when they use the database.

    Needs a QApplication (it may show a dialog). Call it before building the
    tool's window.

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
    return True
