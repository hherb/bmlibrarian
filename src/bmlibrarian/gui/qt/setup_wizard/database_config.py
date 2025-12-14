"""
Database configuration page for the Setup Wizard.

Contains the page for entering PostgreSQL credentials.
"""

import logging
from typing import Optional, TYPE_CHECKING

from PySide6.QtWidgets import (
    QWizardPage,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QGroupBox,
    QPushButton,
    QMessageBox,
)
from PySide6.QtGui import QIntValidator

from ..resources.styles.dpi_scale import get_font_scale
from .utils import DEFAULT_DATABASE_NAME, DEFAULT_APP_USER
from .constants import (
    DEFAULT_POSTGRES_HOST,
    DEFAULT_POSTGRES_PORT,
    DB_CONNECTION_TIMEOUT_SECONDS,
    REQUIRED_EXTENSIONS,
    COLOR_ERROR,
    COLOR_WARNING,
    COLOR_SUCCESS,
)

if TYPE_CHECKING:
    from .wizard import SetupWizard

logger = logging.getLogger(__name__)


class DatabaseConfigPage(QWizardPage):
    """
    Page for entering PostgreSQL superuser credentials and bmlibrarian user password.

    Simplified setup flow:
    - User provides superuser credentials to connect to PostgreSQL
    - User chooses a password for the bmlibrarian application user
    - The wizard will create the database, extensions, and user automatically
    """

    def __init__(self, parent: Optional["SetupWizard"] = None):
        """Initialize database configuration page."""
        super().__init__(parent)
        self._wizard = parent
        self._connection_tested = False
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the configuration page UI."""
        scale = get_font_scale()

        self.setTitle("Database Credentials")
        self.setSubTitle(
            "Enter PostgreSQL superuser credentials and choose a password for BMLibrarian."
        )

        layout = QVBoxLayout(self)
        layout.setSpacing(scale["spacing_large"])

        # Superuser connection settings group
        superuser_group = QGroupBox("PostgreSQL Superuser Connection")
        superuser_layout = QVBoxLayout(superuser_group)
        superuser_layout.setSpacing(scale["spacing_medium"])

        # Host
        host_layout = QHBoxLayout()
        host_label = QLabel("Host:")
        host_label.setMinimumWidth(scale["control_width_small"])
        self.host_edit = QLineEdit(DEFAULT_POSTGRES_HOST)
        self.host_edit.setPlaceholderText(DEFAULT_POSTGRES_HOST)
        host_layout.addWidget(host_label)
        host_layout.addWidget(self.host_edit)
        superuser_layout.addLayout(host_layout)

        # Port (with integer validation)
        port_layout = QHBoxLayout()
        port_label = QLabel("Port:")
        port_label.setMinimumWidth(scale["control_width_small"])
        self.port_edit = QLineEdit(DEFAULT_POSTGRES_PORT)
        self.port_edit.setPlaceholderText(DEFAULT_POSTGRES_PORT)
        self.port_edit.setValidator(QIntValidator(1, 65535))  # Valid port range
        port_layout.addWidget(port_label)
        port_layout.addWidget(self.port_edit)
        superuser_layout.addLayout(port_layout)

        # Superuser username
        superuser_user_layout = QHBoxLayout()
        superuser_user_label = QLabel("Superuser:")
        superuser_user_label.setMinimumWidth(scale["control_width_small"])
        self.superuser_edit = QLineEdit()
        self.superuser_edit.setPlaceholderText("postgres")
        superuser_user_layout.addWidget(superuser_user_label)
        superuser_user_layout.addWidget(self.superuser_edit)
        superuser_layout.addLayout(superuser_user_layout)

        # Superuser password
        superuser_pass_layout = QHBoxLayout()
        superuser_pass_label = QLabel("Password:")
        superuser_pass_label.setMinimumWidth(scale["control_width_small"])
        self.superuser_pass_edit = QLineEdit()
        self.superuser_pass_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.superuser_pass_edit.setPlaceholderText("superuser password")
        superuser_pass_layout.addWidget(superuser_pass_label)
        superuser_pass_layout.addWidget(self.superuser_pass_edit)
        superuser_layout.addLayout(superuser_pass_layout)

        layout.addWidget(superuser_group)

        # Test connection button and status
        test_layout = QHBoxLayout()
        self.test_btn = QPushButton("Test Connection")
        self.test_btn.clicked.connect(self._test_connection)
        test_layout.addWidget(self.test_btn)
        test_layout.addStretch()
        layout.addLayout(test_layout)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        # BMLibrarian user password group
        app_user_group = QGroupBox("BMLibrarian Application User")
        app_user_layout = QVBoxLayout(app_user_group)
        app_user_layout.setSpacing(scale["spacing_medium"])

        app_user_info = QLabel(
            f"A dedicated '{DEFAULT_APP_USER}' user will be created for the application.\n"
            "Choose a secure password for this user:"
        )
        app_user_info.setWordWrap(True)
        app_user_layout.addWidget(app_user_info)

        # App user password
        app_pass_layout = QHBoxLayout()
        app_pass_label = QLabel("Password:")
        app_pass_label.setMinimumWidth(scale["control_width_small"])
        self.app_pass_edit = QLineEdit()
        self.app_pass_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.app_pass_edit.setPlaceholderText("bmlibrarian user password")
        app_pass_layout.addWidget(app_pass_label)
        app_pass_layout.addWidget(self.app_pass_edit)
        app_user_layout.addLayout(app_pass_layout)

        # Confirm password
        confirm_pass_layout = QHBoxLayout()
        confirm_pass_label = QLabel("Confirm:")
        confirm_pass_label.setMinimumWidth(scale["control_width_small"])
        self.confirm_pass_edit = QLineEdit()
        self.confirm_pass_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.confirm_pass_edit.setPlaceholderText("confirm password")
        confirm_pass_layout.addWidget(confirm_pass_label)
        confirm_pass_layout.addWidget(self.confirm_pass_edit)
        app_user_layout.addLayout(confirm_pass_layout)

        layout.addWidget(app_user_group)

        layout.addStretch()

        # Register fields for wizard
        self.registerField("postgres_host", self.host_edit)
        self.registerField("postgres_port", self.port_edit)
        self.registerField("superuser_name", self.superuser_edit)
        self.registerField("superuser_password", self.superuser_pass_edit)
        self.registerField("app_user_password", self.app_pass_edit)

        # Connect text changes to trigger isComplete() re-evaluation
        self.host_edit.textChanged.connect(lambda _: self.completeChanged.emit())
        self.port_edit.textChanged.connect(lambda _: self.completeChanged.emit())
        self.superuser_edit.textChanged.connect(lambda _: self._on_credentials_changed())
        self.superuser_pass_edit.textChanged.connect(lambda _: self._on_credentials_changed())
        self.app_pass_edit.textChanged.connect(lambda _: self.completeChanged.emit())
        self.confirm_pass_edit.textChanged.connect(lambda _: self.completeChanged.emit())

    def _on_credentials_changed(self) -> None:
        """Handle changes to superuser credentials."""
        # Reset connection test status when credentials change
        self._connection_tested = False
        self.status_label.setText("")
        self.completeChanged.emit()

    def _test_connection(self) -> None:
        """Test the superuser connection to PostgreSQL."""
        host = self.host_edit.text().strip()
        port = self.port_edit.text().strip()
        superuser = self.superuser_edit.text().strip()
        superuser_pass = self.superuser_pass_edit.text()

        if not all([host, port, superuser, superuser_pass]):
            self.status_label.setText(
                f'<span style="color: {COLOR_ERROR};">Please fill in all superuser fields.</span>'
            )
            return

        self.status_label.setText("Testing connection...")
        self._connection_tested = False

        try:
            import psycopg

            # NOTE: Direct psycopg usage is necessary here during bootstrapping
            # before DatabaseManager is available. This is an exception to Golden
            # Rule #5 because we need to validate superuser credentials BEFORE
            # the database is set up.
            #
            # Connect to 'postgres' database (always exists) to test superuser access
            conn_params = {
                'host': host,
                'port': int(port),
                'dbname': 'postgres',  # Default database that always exists
                'user': superuser,
                'password': superuser_pass,
                'connect_timeout': DB_CONNECTION_TIMEOUT_SECONDS,
            }

            with psycopg.connect(**conn_params) as conn:
                with conn.cursor() as cur:
                    # Check if user has superuser privileges
                    cur.execute("SELECT usesuper FROM pg_user WHERE usename = current_user")
                    result = cur.fetchone()
                    is_superuser = result[0] if result else False

                    # Check for required extensions availability
                    cur.execute("""
                        SELECT name FROM pg_available_extensions
                        WHERE name IN ('vector', 'plpython3u', 'pg_trgm')
                    """)
                    available_exts = [row[0] for row in cur.fetchall()]

            missing_exts = [ext for ext in REQUIRED_EXTENSIONS if ext not in available_exts]

            if not is_superuser:
                self.status_label.setText(
                    f'<span style="color: {COLOR_WARNING};">Connection successful, but user '
                    f"'{superuser}' is not a superuser. Superuser privileges are required "
                    f"to create extensions.</span>"
                )
            elif missing_exts:
                self.status_label.setText(
                    f'<span style="color: {COLOR_WARNING};">Connection successful, but these '
                    f'extensions are not available: {", ".join(missing_exts)}. '
                    f"Please install them before proceeding.</span>"
                )
            else:
                self._connection_tested = True
                self.status_label.setText(
                    f'<span style="color: {COLOR_SUCCESS};">Connection successful! '
                    f"Superuser access verified, all required extensions available.</span>"
                )
                self.completeChanged.emit()

        except Exception as e:
            logger.error(f"Superuser connection test failed: {e}")
            self.status_label.setText(
                f'<span style="color: {COLOR_ERROR};">Connection failed: {str(e)}</span>'
            )

    def isComplete(self) -> bool:
        """
        Check if all required fields are filled and connection tested.

        Returns:
            bool: True if all requirements are met
        """
        # Check all fields are filled
        fields_filled = all([
            self.host_edit.text().strip(),
            self.port_edit.text().strip(),
            self.superuser_edit.text().strip(),
            self.superuser_pass_edit.text(),
            self.app_pass_edit.text(),
            self.confirm_pass_edit.text(),
        ])

        # Check passwords match
        passwords_match = self.app_pass_edit.text() == self.confirm_pass_edit.text()

        # Check connection was tested successfully
        return fields_filled and passwords_match and self._connection_tested

    def validatePage(self) -> bool:
        """Validate the page before proceeding."""
        # Verify passwords match
        if self.app_pass_edit.text() != self.confirm_pass_edit.text():
            QMessageBox.warning(
                self,
                "Password Mismatch",
                "The BMLibrarian user passwords do not match. Please try again.",
            )
            return False

        # Store values in wizard config
        if self._wizard:
            self._wizard.set_config_value("postgres_host", self.host_edit.text().strip())
            self._wizard.set_config_value("postgres_port", self.port_edit.text().strip())
            self._wizard.set_config_value("superuser_name", self.superuser_edit.text().strip())
            self._wizard.set_config_value("superuser_password", self.superuser_pass_edit.text())
            self._wizard.set_config_value("postgres_db", DEFAULT_DATABASE_NAME)
            self._wizard.set_config_value("postgres_user", DEFAULT_APP_USER)
            self._wizard.set_config_value("postgres_password", self.app_pass_edit.text())

        return True
