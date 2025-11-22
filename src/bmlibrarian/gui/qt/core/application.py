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
from ..dialogs import LoginDialog, LoginResult


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

        # Create main window (will be created after login)
        self.main_window: Optional[BMLibrarianMainWindow] = None

        # Login state
        self._login_result: Optional[LoginResult] = None
        self._db_connection = None

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
        """Load and apply DPI-aware theme stylesheet."""
        from ..resources.styles import generate_default_theme, generate_dark_theme

        theme = self.config_manager.get_theme()

        try:
            if theme == "dark":
                stylesheet = generate_dark_theme()
            else:
                stylesheet = generate_default_theme()

            self.qapp.setStyleSheet(stylesheet)
            self.logger.info(f"Loaded DPI-aware theme: {theme}")
        except Exception as e:
            self.logger.warning(f"Failed to generate theme '{theme}': {e}")

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
            # Show login dialog first
            if not self._show_login_dialog():
                self.logger.info("Login cancelled, exiting")
                return 0

            # Set user context on the global config for database-backed settings
            self._setup_user_context()

            # Check for existing JSON config and offer migration
            self._check_config_migration()

            # Create and show main window
            self.main_window = BMLibrarianMainWindow(
                user_id=self._login_result.user_id if self._login_result else None,
                username=self._login_result.username if self._login_result else None,
            )
            self.main_window.show()

            self.logger.info("Application running")

            # Run event loop
            return self.qapp.exec()

        except Exception as e:
            self.logger.error(f"Application error: {e}", exc_info=True)
            return 1
        finally:
            self._cleanup()
            self.logger.info("Application shutdown")

    def _show_login_dialog(self) -> bool:
        """Show the login dialog and authenticate the user.

        Returns:
            True if login was successful, False if cancelled.
        """
        dialog = LoginDialog()
        result = dialog.exec()

        if result == LoginDialog.DialogCode.Accepted:
            self._login_result = dialog.get_login_result()
            self._db_connection = dialog.get_connection()

            if self._login_result:
                self.logger.info(
                    f"User logged in: {self._login_result.username} "
                    f"(id={self._login_result.user_id})"
                )
                return True

        return False

    def _setup_user_context(self) -> None:
        """Set up user context on the global config for database-backed settings.

        This connects the authenticated user session to the config system,
        enabling database-backed settings storage and retrieval.
        """
        if not self._login_result or not self._db_connection:
            self.logger.warning("Cannot setup user context: no login result or connection")
            return

        try:
            from ....config import get_config

            config = get_config()
            config.set_user_context(
                user_id=self._login_result.user_id,
                connection=self._db_connection,
                session_token=self._login_result.session_token
            )
            self.logger.info(
                f"User context set for user_id={self._login_result.user_id}, "
                "database-backed settings enabled"
            )
        except Exception as e:
            self.logger.error(f"Failed to set user context: {e}")
            # Continue without database-backed settings - fall back to JSON/defaults

    def _check_config_migration(self) -> None:
        """Check for existing JSON config and offer to migrate to database.

        This is called after login to help users migrate their local
        JSON configuration to database-backed settings.
        """
        from PySide6.QtWidgets import QMessageBox

        # Check if user has database settings already
        try:
            from ....config import get_config
            from ....auth import UserSettingsManager

            config = get_config()
            if not config.has_user_context():
                return

            # Check if user already has any settings in database
            settings_manager = UserSettingsManager(
                self._db_connection,
                self._login_result.user_id
            )

            # Check a common category to see if user has settings
            existing_settings = settings_manager.get('agents')
            if existing_settings:
                # User already has database settings, no migration needed
                self.logger.debug("User already has database settings")
                return

        except Exception as e:
            self.logger.debug(f"Could not check existing settings: {e}")
            return

        # Check for local JSON config file
        json_config_path = Path.home() / ".bmlibrarian" / "config.json"
        if not json_config_path.exists():
            self.logger.debug("No local JSON config found")
            return

        # Offer to migrate
        reply = QMessageBox.question(
            None,
            "Import Settings",
            "A local configuration file was found.\n\n"
            f"Path: {json_config_path}\n\n"
            "Would you like to import these settings to your user profile?\n\n"
            "This will sync your local settings to the database so they're "
            "available across devices.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )

        if reply == QMessageBox.StandardButton.Yes:
            self._perform_config_migration(json_config_path)

    def _perform_config_migration(self, json_path: Path) -> None:
        """Perform the actual config migration from JSON to database.

        Args:
            json_path: Path to JSON configuration file.
        """
        from PySide6.QtWidgets import QMessageBox
        import json

        try:
            # Load JSON config
            with open(json_path, 'r') as f:
                json_config = json.load(f)

            # Import valid categories from centralized config
            from ....config import VALID_SETTINGS_CATEGORIES

            # Get config and sync
            from ....config import get_config
            config = get_config()

            # Update config with JSON values
            migrated_count = 0
            for category, settings in json_config.items():
                if category in VALID_SETTINGS_CATEGORIES and isinstance(settings, dict):
                    for key, value in settings.items():
                        config.set(f"{category}.{key}", value)
                    migrated_count += 1

            # Sync to database
            config.sync_to_database()

            self.logger.info(f"Migrated {migrated_count} categories from JSON to database")

            QMessageBox.information(
                None,
                "Migration Complete",
                f"Successfully imported {migrated_count} setting categories "
                f"to your user profile.\n\n"
                f"Your local config file has been preserved at:\n{json_path}"
            )

        except Exception as e:
            self.logger.error(f"Config migration failed: {e}")
            QMessageBox.warning(
                None,
                "Migration Failed",
                f"Failed to import settings:\n\n{str(e)}\n\n"
                "You can try again later from the Configuration tab."
            )

    def _cleanup(self) -> None:
        """Cleanup resources on shutdown."""
        # Clear user context from config
        try:
            from ....config import get_config
            config = get_config()
            if config.has_user_context():
                config.clear_user_context()
                self.logger.debug("User context cleared")
        except Exception as e:
            self.logger.warning(f"Error clearing user context: {e}")

        # Close database connection if open
        if self._db_connection:
            try:
                self._db_connection.close()
                self.logger.debug("Database connection closed")
            except Exception as e:
                self.logger.warning(f"Error closing database connection: {e}")

    @property
    def current_user_id(self) -> Optional[int]:
        """Get the current logged-in user's ID."""
        return self._login_result.user_id if self._login_result else None

    @property
    def current_username(self) -> Optional[str]:
        """Get the current logged-in user's username."""
        return self._login_result.username if self._login_result else None

    @property
    def login_result(self) -> Optional[LoginResult]:
        """Get the full login result."""
        return self._login_result


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
