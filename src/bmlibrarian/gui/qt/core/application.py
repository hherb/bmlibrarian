"""Application wrapper for BMLibrarian Qt GUI.

This module provides the BMLibrarianApplication class which wraps QApplication
and provides application-wide services and initialization.
"""

import sys
import logging
from pathlib import Path
from typing import Optional, List

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from .main_window import BMLibrarianMainWindow
from .config_manager import GUIConfigManager


class BMLibrarianApplication:
    """Application wrapper for BMLibrarian Qt GUI.

    This class:
    - Initializes QApplication
    - Sets up logging
    - Loads application stylesheet
    - Creates and shows main window
    - Handles application lifecycle

    Example:
        app = BMLibrarianApplication(sys.argv)
        sys.exit(app.run())
    """

    def __init__(self, argv: Optional[List[str]] = None):
        """Initialize the application.

        Args:
            argv: Command line arguments (defaults to sys.argv)
        """
        if argv is None:
            argv = sys.argv

        # Initialize logging
        self._setup_logging()

        self.logger = logging.getLogger("bmlibrarian.gui.qt.Application")
        self.logger.info("Initializing BMLibrarian Qt Application...")

        # Create QApplication
        self.qapp = QApplication(argv)
        self.qapp.setApplicationName("BMLibrarian")
        self.qapp.setOrganizationName("BMLibrarian")
        self.qapp.setApplicationVersion("0.1.0")

        # Set application-wide font
        self._setup_font()

        # Load configuration
        self.config_manager = GUIConfigManager()

        # Load theme/stylesheet
        self._load_theme()

        # Create main window
        self.main_window: Optional[BMLibrarianMainWindow] = None

        self.logger.info("Application initialized")

    def _setup_logging(self):
        """Setup logging configuration."""
        # Configure root logger
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(sys.stdout),
                logging.FileHandler(
                    Path.home() / ".bmlibrarian" / "gui_qt.log"
                )
            ]
        )

        # Set library loggers to appropriate levels
        logging.getLogger("bmlibrarian.gui.qt").setLevel(logging.DEBUG)
        logging.getLogger("PySide6").setLevel(logging.WARNING)
        logging.getLogger("httpx").setLevel(logging.WARNING)  # Suppress httpx INFO logs

    def _setup_font(self):
        """Setup application-wide font."""
        # Use system default font with reasonable size
        font = QFont()
        font.setPointSize(10)
        self.qapp.setFont(font)

    def _load_theme(self):
        """Load and apply theme stylesheet."""
        theme = self.config_manager.get_theme()

        if theme == "dark":
            stylesheet_path = self._get_resource_path("styles/dark.qss")
        else:
            stylesheet_path = self._get_resource_path("styles/default.qss")

        if stylesheet_path and stylesheet_path.exists():
            try:
                with open(stylesheet_path, 'r') as f:
                    stylesheet = f.read()
                self.qapp.setStyleSheet(stylesheet)
                self.logger.info(f"Loaded theme: {theme}")
            except Exception as e:
                self.logger.warning(f"Failed to load theme '{theme}': {e}")
        else:
            self.logger.debug(f"Theme file not found: {stylesheet_path}")

    def _get_resource_path(self, resource: str) -> Optional[Path]:
        """Get path to a resource file.

        Args:
            resource: Relative path to resource (e.g., "styles/dark.qss")

        Returns:
            Optional[Path]: Full path to resource or None if not found
        """
        # Resource directory is relative to this file
        resource_dir = Path(__file__).parent.parent / "resources"
        resource_path = resource_dir / resource

        if resource_path.exists():
            return resource_path

        return None

    def run(self) -> int:
        """Run the application.

        Returns:
            int: Exit code (0 for success)
        """
        try:
            # Create and show main window
            self.main_window = BMLibrarianMainWindow()
            self.main_window.show()

            self.logger.info("Application running")

            # Run event loop
            return self.qapp.exec()

        except Exception as e:
            self.logger.error(f"Application error: {e}", exc_info=True)
            return 1
        finally:
            self.logger.info("Application shutdown")


def main(argv: Optional[List[str]] = None) -> int:
    """Main entry point for the application.

    Args:
        argv: Command line arguments

    Returns:
        int: Exit code
    """
    app = BMLibrarianApplication(argv)
    return app.run()


if __name__ == "__main__":
    sys.exit(main())
