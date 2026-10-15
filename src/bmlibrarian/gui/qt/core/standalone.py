"""Run a single Qt widget or tab plugin in its own window.

Used by the standalone launchers (``fact_checker_review_gui.py``,
``scripts/*_lab.py``) that open one BMLibrarian tool without the full tabbed
application. The window uses the same DPI-aware theme as the main app.
"""

import logging
import sys
from typing import TYPE_CHECKING, Callable, List, Optional

from PySide6.QtWidgets import QApplication, QMainWindow, QWidget

from .config_manager import GUIConfigManager

if TYPE_CHECKING:
    from ..plugins.base_tab import BaseTabPlugin

logger = logging.getLogger(__name__)

# Fraction of the available screen area a standalone window initially covers
STANDALONE_WINDOW_SCREEN_FRACTION = 0.8


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
        logger.warning(f"Failed to apply GUI theme, using Qt defaults: {e}")


def run_widget_standalone(
    widget_factory: Callable[[], QWidget],
    title: str,
    argv: Optional[List[str]] = None,
) -> int:
    """Show a widget as the central widget of its own main window.

    Args:
        widget_factory: Creates the widget; called after the QApplication exists
        title: Window title
        argv: Arguments for QApplication (defaults to ``sys.argv``)

    Returns:
        The Qt event loop's exit code
    """
    qapp = QApplication.instance() or QApplication(argv if argv is not None else sys.argv)
    _apply_theme(qapp)

    window = QMainWindow()
    window.setWindowTitle(title)
    window.setCentralWidget(widget_factory())

    screen = qapp.primaryScreen()
    if screen is not None:
        available = screen.availableGeometry()
        window.resize(
            int(available.width() * STANDALONE_WINDOW_SCREEN_FRACTION),
            int(available.height() * STANDALONE_WINDOW_SCREEN_FRACTION),
        )
    window.show()
    return qapp.exec()


def run_plugin_standalone(
    create_plugin: Callable[[], "BaseTabPlugin"],
    argv: Optional[List[str]] = None,
) -> int:
    """Run one tab plugin (``plugins/<name>/plugin.py:create_plugin``) standalone.

    Args:
        create_plugin: The plugin module's ``create_plugin`` factory
        argv: Arguments for QApplication (defaults to ``sys.argv``)

    Returns:
        The Qt event loop's exit code
    """
    # QApplication must exist before the plugin builds any widget
    QApplication.instance() or QApplication(argv if argv is not None else sys.argv)
    plugin = create_plugin()
    title = f"BMLibrarian - {plugin.get_metadata().display_name}"
    return run_widget_standalone(lambda: plugin.create_widget(None), title, argv)
