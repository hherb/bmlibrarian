"""
Plugin registration for the Audit Validation GUI.

Registers the audit validation tab with the Qt plugin system.
"""

import logging
from typing import Optional

from PySide6.QtWidgets import QWidget, QTabWidget, QVBoxLayout, QLabel

import psycopg

from bmlibrarian.database import DatabaseManager, PersistentConnection

from ...plugins.base_tab import BaseTabPlugin, TabPluginMetadata
from .data_manager import AuditValidationDataManager
from .validation_tab import ValidationTabWidget
from .statistics_widget import StatisticsWidget

logger = logging.getLogger(__name__)


class AuditValidationPlugin(BaseTabPlugin):
    """
    Plugin for the Audit Trail Validation GUI.

    Provides a tabbed interface for human reviewers to validate
    automated evaluations in the audit trail.
    """

    def __init__(self):
        """Initialize the plugin."""
        super().__init__()
        self.db_manager: Optional[DatabaseManager] = None
        self._persistent_conn: Optional[PersistentConnection] = None
        self.conn: Optional[psycopg.Connection] = None
        self.data_manager: Optional[AuditValidationDataManager] = None
        self.main_widget: Optional[QWidget] = None
        self.validation_tab: Optional[ValidationTabWidget] = None
        self.statistics_tab: Optional[StatisticsWidget] = None
        self.reviewer_id: Optional[int] = None
        self.reviewer_name: str = "Anonymous"

    def get_metadata(self) -> TabPluginMetadata:
        """
        Return plugin metadata.

        Returns:
            TabPluginMetadata describing this plugin
        """
        return TabPluginMetadata(
            plugin_id="audit_validation",
            display_name="Audit Validation",
            description="Validate audit trail items for benchmarking and fine-tuning",
            version="1.0.0",
            icon=None,
            requires=[]
        )

    def set_reviewer(self, reviewer_id: Optional[int], reviewer_name: str) -> None:
        """
        Set the current reviewer information.

        Args:
            reviewer_id: ID of the reviewer (optional)
            reviewer_name: Name of the reviewer
        """
        self.reviewer_id = reviewer_id
        self.reviewer_name = reviewer_name

    def _initialize_database(self) -> bool:
        """
        Initialize the database connection.

        Returns:
            True if initialization successful, False otherwise
        """
        try:
            # Use DatabaseManager for connection (golden rule #5)
            # For GUI plugins that need long-lived connections, we acquire
            # a persistent connection from the pool
            self.db_manager = DatabaseManager()
            self._persistent_conn = self.db_manager.acquire_persistent_connection()
            self.conn = self._persistent_conn.connection

            self.data_manager = AuditValidationDataManager(self.conn)
            logger.info("Audit Validation plugin database initialized successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize Audit Validation plugin database: {e}")
            return False

    def create_widget(self, parent: Optional[QWidget] = None) -> QWidget:
        """
        Create the main plugin widget.

        Args:
            parent: Parent widget

        Returns:
            The main plugin widget
        """
        # Initialize database if not already done
        if self.data_manager is None:
            if not self._initialize_database():
                # Return error widget if database initialization fails
                error_widget = QWidget(parent)
                layout = QVBoxLayout(error_widget)
                error_label = QLabel(
                    "Failed to initialize Audit Validation plugin.\n"
                    "Please check database connection."
                )
                layout.addWidget(error_label)
                return error_widget

        self.main_widget = QWidget(parent)
        layout = QVBoxLayout(self.main_widget)
        layout.setContentsMargins(0, 0, 0, 0)

        # Create tab widget with validation and statistics tabs
        tabs = QTabWidget()

        # Validation tab
        self.validation_tab = ValidationTabWidget(
            data_manager=self.data_manager,
            reviewer_id=self.reviewer_id,
            reviewer_name=self.reviewer_name,
            parent=self.main_widget
        )
        tabs.addTab(self.validation_tab, "Review Items")

        # Statistics tab
        self.statistics_tab = StatisticsWidget(
            data_manager=self.data_manager,
            parent=self.main_widget
        )
        tabs.addTab(self.statistics_tab, "Statistics")

        # Connect signals
        self.validation_tab.validation_saved.connect(
            lambda *args: self.statistics_tab.refresh()
        )

        layout.addWidget(tabs)

        self._widget = self.main_widget
        return self.main_widget

    def on_tab_activated(self):
        """Called when this tab becomes active."""
        self._is_active = True
        self.status_changed.emit("Audit Validation tab activated")

        # Refresh statistics when tab is activated
        if self.statistics_tab:
            self.statistics_tab.refresh()

    def on_tab_deactivated(self):
        """Called when this tab is deactivated."""
        self._is_active = False

    def cleanup(self) -> None:
        """Clean up plugin resources."""
        # Disconnect validation tab signal if connected
        if self.validation_tab:
            try:
                self.validation_tab.validation_saved.disconnect()
            except RuntimeError:
                pass  # Already disconnected

        # First, release the persistent connection back to the pool
        if self._persistent_conn:
            try:
                self._persistent_conn.release()
                self._persistent_conn = None
                self.conn = None
                logger.info("Audit Validation plugin persistent connection released")
            except Exception as e:
                logger.error(f"Error releasing persistent connection: {e}")

        # Then close the database manager (which closes the pool)
        if self.db_manager:
            try:
                self.db_manager.close()
                self.db_manager = None
                logger.info("Audit Validation plugin database manager closed")
            except Exception as e:
                logger.error(f"Error closing database manager: {e}")

        # Call parent cleanup to handle base plugin signals
        super().cleanup()


def create_plugin() -> BaseTabPlugin:
    """
    Plugin factory function.

    Returns:
        AuditValidationPlugin instance
    """
    return AuditValidationPlugin()
