"""
Plugin registration for the Audit Validation GUI.

Registers the audit validation tab with the Qt plugin system.
"""

import logging
from typing import Optional

from PySide6.QtWidgets import QWidget, QTabWidget, QVBoxLayout, QMessageBox

import psycopg

from bmlibrarian.database import DatabaseManager
from bmlibrarian.config import BMLibrarianConfig

from .data_manager import AuditValidationDataManager
from .validation_tab import ValidationTabWidget
from .statistics_widget import StatisticsWidget

logger = logging.getLogger(__name__)


class AuditValidationPlugin:
    """
    Plugin for the Audit Trail Validation GUI.

    Provides a tabbed interface for human reviewers to validate
    automated evaluations in the audit trail.
    """

    PLUGIN_NAME = "Audit Validation"
    PLUGIN_DESCRIPTION = "Validate audit trail items for benchmarking and fine-tuning"

    def __init__(self):
        """Initialize the plugin."""
        self.db_manager: Optional[DatabaseManager] = None
        self.conn: Optional[psycopg.Connection] = None
        self.data_manager: Optional[AuditValidationDataManager] = None
        self.main_widget: Optional[QWidget] = None
        self.reviewer_id: Optional[int] = None
        self.reviewer_name: str = "Anonymous"

    def set_reviewer(self, reviewer_id: Optional[int], reviewer_name: str) -> None:
        """
        Set the current reviewer information.

        Args:
            reviewer_id: ID of the reviewer (optional)
            reviewer_name: Name of the reviewer
        """
        self.reviewer_id = reviewer_id
        self.reviewer_name = reviewer_name

    def initialize(self, conn: Optional[psycopg.Connection] = None) -> bool:
        """
        Initialize the plugin with database connection.

        Args:
            conn: Optional existing database connection

        Returns:
            True if initialization successful, False otherwise
        """
        try:
            if conn:
                self.conn = conn
            else:
                # Use DatabaseManager for connection (golden rule #5)
                self.db_manager = DatabaseManager()
                self.conn = self.db_manager.conn

            self.data_manager = AuditValidationDataManager(self.conn)
            logger.info("Audit Validation plugin initialized successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize Audit Validation plugin: {e}")
            return False

    def create_widget(self, parent: Optional[QWidget] = None) -> QWidget:
        """
        Create the main plugin widget.

        Args:
            parent: Parent widget

        Returns:
            The main plugin widget
        """
        if self.data_manager is None:
            error_widget = QWidget(parent)
            layout = QVBoxLayout(error_widget)
            layout.addWidget(QMessageBox.critical(
                error_widget, "Error",
                "Plugin not initialized. Please check database connection."
            ))
            return error_widget

        self.main_widget = QWidget(parent)
        layout = QVBoxLayout(self.main_widget)
        layout.setContentsMargins(0, 0, 0, 0)

        # Create tab widget with validation and statistics tabs
        tabs = QTabWidget()

        # Validation tab
        validation_tab = ValidationTabWidget(
            data_manager=self.data_manager,
            reviewer_id=self.reviewer_id,
            reviewer_name=self.reviewer_name,
            parent=self.main_widget
        )
        tabs.addTab(validation_tab, "Review Items")

        # Statistics tab
        statistics_tab = StatisticsWidget(
            data_manager=self.data_manager,
            parent=self.main_widget
        )
        tabs.addTab(statistics_tab, "Statistics")

        # Connect signals
        validation_tab.validation_saved.connect(
            lambda *args: statistics_tab.refresh()
        )

        layout.addWidget(tabs)

        return self.main_widget

    def cleanup(self) -> None:
        """Clean up plugin resources."""
        if self.db_manager:
            try:
                self.db_manager.close()
                logger.info("Audit Validation plugin connection closed")
            except Exception as e:
                logger.error(f"Error closing connection: {e}")
        elif self.conn and not self.conn.closed:
            try:
                self.conn.close()
                logger.info("Audit Validation plugin connection closed")
            except Exception as e:
                logger.error(f"Error closing connection: {e}")

    @classmethod
    def get_plugin_info(cls) -> dict:
        """Get plugin information for registration."""
        return {
            'name': cls.PLUGIN_NAME,
            'description': cls.PLUGIN_DESCRIPTION,
            'version': '1.0.0',
            'author': 'BMLibrarian'
        }
