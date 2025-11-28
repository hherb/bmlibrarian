#!/usr/bin/env python
"""
Audit Trail Validation GUI - Human Review Interface for Systematic Review Auditing.

This application provides a graphical interface for human reviewers to validate
or reject automated evaluations in the audit trail. The purpose is to:

1. Enable human reviewers to evaluate correctness of automated decisions
2. Log human disagreement with automated decisions for benchmarking
3. Provide data for fine-tuning the system

Usage:
    uv run python audit_validation_gui.py
    uv run python audit_validation_gui.py --user alice
    uv run python audit_validation_gui.py --user alice --incremental
"""

import argparse
import logging
import sys
from typing import Optional

from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox, QInputDialog
from PySide6.QtCore import Qt

import psycopg
from psycopg.rows import dict_row

from bmlibrarian.config import BMLibrarianConfig
from bmlibrarian.gui.qt.plugins.audit_validation.plugin import AuditValidationPlugin

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class AuditValidationMainWindow(QMainWindow):
    """Main window for the Audit Validation GUI."""

    def __init__(
        self,
        reviewer_name: Optional[str] = None,
        incremental: bool = False
    ):
        """
        Initialize the main window.

        Args:
            reviewer_name: Name of the reviewer (prompts if not provided)
            incremental: Whether to show only unvalidated items
        """
        super().__init__()
        self.reviewer_name = reviewer_name
        self.reviewer_id: Optional[int] = None
        self.incremental = incremental
        self.plugin: Optional[AuditValidationPlugin] = None

        self._setup_window()
        self._initialize_plugin()

    def _setup_window(self) -> None:
        """Set up the main window properties."""
        self.setWindowTitle("Audit Trail Validation - BMLibrarian")
        self.setMinimumSize(1200, 800)

        # Center on screen
        screen = QApplication.primaryScreen().geometry()
        self.setGeometry(
            (screen.width() - 1200) // 2,
            (screen.height() - 800) // 2,
            1200,
            800
        )

    def _initialize_plugin(self) -> None:
        """Initialize the audit validation plugin."""
        # Get reviewer name if not provided
        if not self.reviewer_name:
            self.reviewer_name, ok = QInputDialog.getText(
                self,
                "Reviewer Name",
                "Enter your name for tracking validations:",
                text="Anonymous"
            )
            if not ok:
                self.reviewer_name = "Anonymous"

        # Try to get reviewer ID from database
        self._lookup_reviewer()

        # Initialize plugin
        self.plugin = AuditValidationPlugin()
        self.plugin.set_reviewer(self.reviewer_id, self.reviewer_name)

        if not self.plugin.initialize():
            QMessageBox.critical(
                self,
                "Initialization Error",
                "Failed to initialize the audit validation plugin.\n"
                "Please check your database connection settings."
            )
            return

        # Create and set the main widget
        main_widget = self.plugin.create_widget(self)
        self.setCentralWidget(main_widget)

        logger.info(f"Audit Validation GUI initialized for reviewer: {self.reviewer_name}")

    def _lookup_reviewer(self) -> None:
        """Look up or create reviewer in the database."""
        try:
            config = BMLibrarianConfig()
            db_config = config.get_database_config()

            with psycopg.connect(
                host=db_config.get('host', 'localhost'),
                port=db_config.get('port', 5432),
                dbname=db_config.get('database', 'knowledgebase'),
                user=db_config.get('user', ''),
                password=db_config.get('password', '')
            ) as conn:
                with conn.cursor(row_factory=dict_row) as cur:
                    # Try to find existing user
                    cur.execute(
                        "SELECT id FROM public.users WHERE username = %s",
                        (self.reviewer_name,)
                    )
                    row = cur.fetchone()
                    if row:
                        self.reviewer_id = row['id']
                        logger.info(f"Found reviewer ID: {self.reviewer_id}")
                    else:
                        logger.info(f"Reviewer '{self.reviewer_name}' not found in users table")

        except Exception as e:
            logger.warning(f"Could not look up reviewer: {e}")

    def closeEvent(self, event) -> None:
        """Handle window close event."""
        if self.plugin:
            self.plugin.cleanup()
        event.accept()


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Audit Trail Validation GUI - Human Review Interface",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                         Launch with reviewer name prompt
  %(prog)s --user alice            Launch with specified reviewer name
  %(prog)s --user alice --incremental  Show only unvalidated items
  %(prog)s --debug                 Enable debug logging
        """
    )

    parser.add_argument(
        '--user', '-u',
        dest='reviewer_name',
        help='Reviewer name for tracking validations'
    )

    parser.add_argument(
        '--incremental', '-i',
        action='store_true',
        help='Show only unvalidated items (incremental mode)'
    )

    parser.add_argument(
        '--debug', '-d',
        action='store_true',
        help='Enable debug logging'
    )

    return parser.parse_args()


def main() -> int:
    """Main entry point."""
    args = parse_arguments()

    # Configure logging level
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logging.getLogger('bmlibrarian').setLevel(logging.DEBUG)

    # Create Qt application
    app = QApplication(sys.argv)
    app.setApplicationName("BMLibrarian Audit Validation")
    app.setOrganizationName("BMLibrarian")

    # Create and show main window
    window = AuditValidationMainWindow(
        reviewer_name=args.reviewer_name,
        incremental=args.incremental
    )
    window.show()

    # Run event loop
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
