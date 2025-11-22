"""User profile widget for BMLibrarian Qt GUI.

Displays current user information and provides access to
database-backed settings management.
"""

import logging
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QGroupBox, QFormLayout, QMessageBox
)
from PySide6.QtCore import Qt, Signal

from ..resources.styles import get_font_scale
from ..resources.styles.stylesheet_generator import StylesheetGenerator
from ....config import get_config


logger = logging.getLogger(__name__)


class UserProfileWidget(QWidget):
    """Widget displaying user profile and settings sync status.

    This widget shows:
    - Current user's name and ID (if authenticated)
    - Settings storage mode (database or local JSON)
    - Quick sync buttons for authenticated users

    Signals:
        logout_requested: Emitted when user clicks logout button.
        settings_sync_requested: Emitted when user requests a settings sync.
    """

    logout_requested = Signal()
    settings_sync_requested = Signal(str)  # 'to_db' or 'from_db'

    def __init__(
        self,
        user_id: Optional[int] = None,
        username: Optional[str] = None,
        parent: Optional[QWidget] = None
    ):
        """Initialize the user profile widget.

        Args:
            user_id: Current user's ID (None if not authenticated).
            username: Current user's username.
            parent: Optional parent widget.
        """
        super().__init__(parent)

        self._user_id = user_id
        self._username = username

        self.scale = get_font_scale()
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Setup the user interface."""
        s = self.scale

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            s['padding_small'], s['padding_small'],
            s['padding_small'], s['padding_small']
        )
        layout.setSpacing(s['spacing_small'])

        # User info section
        self._create_user_info_section(layout)

        # Settings status section
        self._create_settings_status_section(layout)

        layout.addStretch()

    def _create_user_info_section(self, parent_layout: QVBoxLayout) -> None:
        """Create the user information section.

        Args:
            parent_layout: Parent layout to add section to.
        """
        s = self.scale

        user_group = QGroupBox("User Profile")
        user_layout = QFormLayout(user_group)
        user_layout.setSpacing(s['spacing_small'])

        gen = StylesheetGenerator(s)
        if self._user_id:
            # Authenticated user
            username_label = QLabel(self._username or "Unknown")
            username_label.setStyleSheet(gen.label_stylesheet(bold=True))
            user_layout.addRow("Username:", username_label)

            user_id_label = QLabel(str(self._user_id))
            user_layout.addRow("User ID:", user_id_label)

            status_label = QLabel("Authenticated")
            status_label.setStyleSheet(gen.label_stylesheet(color="#27ae60"))  # Green
            user_layout.addRow("Status:", status_label)
        else:
            # Anonymous user
            anon_label = QLabel("Not logged in")
            anon_label.setStyleSheet(gen.label_stylesheet(color="#7f8c8d"))  # Gray
            user_layout.addRow("Username:", anon_label)

            status_label = QLabel("Anonymous")
            status_label.setStyleSheet(gen.label_stylesheet(color="#f39c12"))  # Orange
            user_layout.addRow("Status:", status_label)

        parent_layout.addWidget(user_group)

    def _create_settings_status_section(self, parent_layout: QVBoxLayout) -> None:
        """Create the settings storage status section.

        Args:
            parent_layout: Parent layout to add section to.
        """
        s = self.scale
        bmlib_config = get_config()
        gen = StylesheetGenerator(s)

        settings_group = QGroupBox("Settings Storage")
        settings_layout = QVBoxLayout(settings_group)
        settings_layout.setSpacing(s['spacing_small'])

        # Status indicator
        status_layout = QHBoxLayout()
        if bmlib_config.has_user_context():
            storage_text = "Database-backed settings"
            storage_color = "#27ae60"  # Green
        else:
            storage_text = "Local JSON file settings"
            storage_color = "#f39c12"  # Orange

        status_label = QLabel(f"{storage_text}")
        status_label.setStyleSheet(gen.label_stylesheet(color=storage_color, bold=True))
        status_layout.addWidget(status_label)
        status_layout.addStretch()

        settings_layout.addLayout(status_layout)

        # Sync buttons (only for authenticated users)
        if bmlib_config.has_user_context():
            button_layout = QHBoxLayout()

            sync_to_btn = QPushButton("Save to Database")
            sync_to_btn.setToolTip("Save current settings to the database")
            sync_to_btn.clicked.connect(lambda: self._on_sync_requested('to_db'))
            button_layout.addWidget(sync_to_btn)

            sync_from_btn = QPushButton("Load from Database")
            sync_from_btn.setToolTip("Load settings from the database")
            sync_from_btn.clicked.connect(lambda: self._on_sync_requested('from_db'))
            button_layout.addWidget(sync_from_btn)

            settings_layout.addLayout(button_layout)

            # Info text
            info_label = QLabel(
                "Your settings are automatically synced when you save in the "
                "Configuration tab."
            )
            info_label.setWordWrap(True)
            info_label.setStyleSheet(gen.label_stylesheet(
                color="#7f8c8d", font_size_key='font_small'
            ))
            settings_layout.addWidget(info_label)
        else:
            # Info for anonymous users
            info_label = QLabel(
                "Log in with a user account to enable database-backed settings "
                "that sync across devices."
            )
            info_label.setWordWrap(True)
            info_label.setStyleSheet(gen.label_stylesheet(
                color="#7f8c8d", font_size_key='font_small'
            ))
            settings_layout.addWidget(info_label)

        parent_layout.addWidget(settings_group)

    def _on_sync_requested(self, direction: str) -> None:
        """Handle sync button click.

        Args:
            direction: Either 'to_db' or 'from_db'.
        """
        self.settings_sync_requested.emit(direction)

        try:
            bmlib_config = get_config()

            if direction == 'to_db':
                bmlib_config.sync_to_database()
                QMessageBox.information(
                    self,
                    "Success",
                    "Settings have been saved to the database."
                )
                logger.info("Settings synced to database from profile widget")
            else:
                bmlib_config._sync_from_database()
                QMessageBox.information(
                    self,
                    "Success",
                    "Settings have been loaded from the database."
                )
                logger.info("Settings synced from database via profile widget")
        except Exception as e:
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to sync settings: {str(e)}"
            )
            logger.error(f"Failed to sync settings: {e}")

    @property
    def user_id(self) -> Optional[int]:
        """Get the current user ID."""
        return self._user_id

    @property
    def username(self) -> Optional[str]:
        """Get the current username."""
        return self._username

    @property
    def is_authenticated(self) -> bool:
        """Check if a user is authenticated."""
        return self._user_id is not None
