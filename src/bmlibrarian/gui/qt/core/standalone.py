"""Run a single Qt widget or tab plugin in its own window.

Used by the standalone launchers that open one BMLibrarian tool without the
full tabbed application: ``fact_checker_review_gui.py`` and
``scripts/{query,pico,prisma2020,study_assessment}_lab.py``. The window uses
the same DPI-aware theme as the main app, shows the tool's status messages in
a status bar, and runs its ``cleanup()`` on quit (stopping worker threads, as
the main window does on close).
"""

import logging
import sys
from typing import TYPE_CHECKING, Callable, List, Optional

from PySide6.QtCore import SignalInstance
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox, QWidget

from .config_manager import GUIConfigManager

if TYPE_CHECKING:
    from ..plugins.base_tab import BaseTabPlugin

logger = logging.getLogger(__name__)

# Fraction of the available screen width and height a standalone window
# initially covers
STANDALONE_WINDOW_SCREEN_FRACTION = 0.8
# Process exit code when the tool could not be created
STARTUP_FAILURE_EXIT_CODE = 1


def build_theme_stylesheet(theme: str) -> str:
    """Generate the application stylesheet for a theme name.

    Args:
        theme: "dark" for the dark theme; anything else selects the default

    Returns:
        The generated Qt stylesheet
    """
    from ..resources.styles import generate_dark_theme, generate_default_theme

    return generate_dark_theme() if theme == "dark" else generate_default_theme()


def _apply_theme(qapp: QApplication) -> None:
    """Apply the user's configured GUI theme, falling back to Qt defaults."""
    try:
        theme = GUIConfigManager().get_theme()
        qapp.setStyleSheet(build_theme_stylesheet(theme))
    except Exception as e:
        logger.warning(f"Failed to apply GUI theme, using Qt defaults: {e}", exc_info=True)


def _ensure_application(argv: Optional[List[str]]) -> QApplication:
    """Return the QApplication, creating it (and basic logging) if needed."""
    # No-op when the launcher already configured logging
    logging.basicConfig(level=logging.INFO)
    existing = QApplication.instance()
    if isinstance(existing, QApplication):
        return existing
    return QApplication(argv if argv is not None else sys.argv)


def _report_startup_failure(title: str, error: Exception) -> int:
    """Log and show a tool that failed to start; return the exit code.

    The error is shown in a dialog as well as logged, because a launcher
    started without a terminal would otherwise just never open a window.
    """
    logger.exception(f"Failed to start {title}")
    print(f"Error: failed to start {title}: {error}", file=sys.stderr)
    QMessageBox.critical(None, title, f"Failed to start:\n\n{error}")
    return STARTUP_FAILURE_EXIT_CODE


def _show_window(
    qapp: QApplication,
    widget: QWidget,
    title: str,
    status_signal: Optional[SignalInstance],
) -> QMainWindow:
    """Put ``widget`` in a sized main window with a status bar and show it."""
    window = QMainWindow()
    window.setWindowTitle(title)
    window.setCentralWidget(widget)
    if status_signal is not None:
        status_signal.connect(window.statusBar().showMessage)

    screen = qapp.primaryScreen()
    if screen is not None:
        available = screen.availableGeometry()
        window.resize(
            int(available.width() * STANDALONE_WINDOW_SCREEN_FRACTION),
            int(available.height() * STANDALONE_WINDOW_SCREEN_FRACTION),
        )
    window.show()
    return window


def run_widget_standalone(
    widget_factory: Callable[[], QWidget],
    title: str,
    argv: Optional[List[str]] = None,
) -> int:
    """Show a widget as the central widget of its own main window.

    If the widget has a ``status_changed`` signal its messages go to the
    window's status bar, and if it has a ``cleanup()`` method it runs when
    the application quits.

    Args:
        widget_factory: Creates the widget; called after the QApplication exists
        title: Window title
        argv: Arguments for QApplication (defaults to ``sys.argv``)

    Returns:
        The Qt event loop's exit code, or STARTUP_FAILURE_EXIT_CODE if the
        widget could not be created
    """
    qapp = _ensure_application(argv)
    _apply_theme(qapp)

    try:
        widget = widget_factory()
    except Exception as e:
        return _report_startup_failure(title, e)

    cleanup = getattr(widget, "cleanup", None)
    if callable(cleanup):
        qapp.aboutToQuit.connect(cleanup)
    window = _show_window(qapp, widget, title, getattr(widget, "status_changed", None))
    exit_code = qapp.exec()
    del window
    return exit_code


def run_plugin_standalone(
    create_plugin: Callable[[], "BaseTabPlugin"],
    argv: Optional[List[str]] = None,
) -> int:
    """Run one tab plugin (``plugins/<name>/plugin.py:create_plugin``) standalone.

    Mirrors the main window's plugin lifecycle: ``status_changed`` goes to the
    status bar, ``on_tab_activated()`` runs once the window is shown and
    ``cleanup()`` runs on quit (stopping the plugin's worker threads).

    Args:
        create_plugin: The plugin module's ``create_plugin`` factory
        argv: Arguments for QApplication (defaults to ``sys.argv``)

    Returns:
        The Qt event loop's exit code, or STARTUP_FAILURE_EXIT_CODE if the
        plugin could not be created
    """
    # QApplication must exist before the plugin builds any widget
    qapp = _ensure_application(argv)
    _apply_theme(qapp)

    try:
        plugin = create_plugin()
        title = f"BMLibrarian - {plugin.get_metadata().display_name}"
        widget = plugin.create_widget(None)
    except Exception as e:
        return _report_startup_failure("BMLibrarian tool", e)

    qapp.aboutToQuit.connect(plugin.cleanup)
    window = _show_window(qapp, widget, title, plugin.status_changed)
    plugin.on_tab_activated()
    exit_code = qapp.exec()
    del window
    return exit_code
