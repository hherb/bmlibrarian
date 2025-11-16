"""
Application wrapper for BMLibrarian Qt GUI.

Provides QApplication wrapper and main entry point.
"""

import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from .main_window import BMLibrarianMainWindow


class BMLibrarianApplication:
    """Wrapper for Qt application lifecycle."""

    def __init__(self, argv: list[str] | None = None):
        """
        Initialize the application.

        Args:
            argv: Optional command line arguments (defaults to sys.argv)
        """
        if argv is None:
            argv = sys.argv

        # Create QApplication instance
        self.app = QApplication(argv)
        self.app.setApplicationName("BMLibrarian")
        self.app.setOrganizationName("BMLibrarian")
        self.app.setOrganizationDomain("bmlibrarian.org")

        # Set application-wide properties
        self.app.setAttribute(Qt.AA_UseHighDpiPixmaps)

        # Create main window
        self.main_window = None

    def run(self) -> int:
        """
        Run the application.

        Returns:
            Application exit code
        """
        # Create and show main window
        self.main_window = BMLibrarianMainWindow()
        self.main_window.show()

        # Enter event loop
        return self.app.exec()


def main(argv: list[str] | None = None) -> int:
    """
    Main entry point for the BMLibrarian Qt GUI.

    Args:
        argv: Optional command line arguments

    Returns:
        Application exit code
    """
    app = BMLibrarianApplication(argv)
    return app.run()


if __name__ == "__main__":
    sys.exit(main())
