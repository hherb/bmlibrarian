"""Login dialog for BMLibrarian Qt GUI.

This module provides a login/registration dialog with database connection
configuration support.
"""

import os
import socket
import logging
from pathlib import Path
from typing import Optional, Tuple
from dataclasses import dataclass

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
    QLabel, QLineEdit, QPushButton, QFormLayout, QMessageBox,
    QGroupBox, QSpinBox, QCheckBox, QFrame
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont

from ..resources.styles.dpi_scale import get_scale_value


# ============================================================================
# Data Classes
# ============================================================================


@dataclass
class DatabaseConfig:
    """Database connection configuration."""
    host: str = "localhost"
    port: int = 5432
    database: str = "knowledgebase"
    user: str = ""
    password: str = ""

    def to_env_dict(self) -> dict:
        """Convert to environment variable dictionary."""
        return {
            "POSTGRES_HOST": self.host,
            "POSTGRES_PORT": str(self.port),
            "POSTGRES_DB": self.database,
            "POSTGRES_USER": self.user,
            "POSTGRES_PASSWORD": self.password,
        }


@dataclass
class LoginResult:
    """Result of a successful login."""
    user_id: int
    username: str
    email: str
    session_token: Optional[str] = None
    db_config: Optional[DatabaseConfig] = None


# ============================================================================
# Login Dialog
# ============================================================================


class LoginDialog(QDialog):
    """Login dialog with tabbed interface for authentication and DB configuration.

    This dialog provides:
    - Tab 1: Login/Registration form
    - Tab 2: PostgreSQL connection parameters

    Signals:
        login_successful: Emitted when user successfully logs in or registers.
            Carries the user_id of the authenticated user.
    """

    login_successful = Signal(int)  # Emits user_id

    # Constants for field width based on character count
    FIELD_WIDTH_CHARS = 35
    BUTTON_MIN_WIDTH_CHARS = 12

    def __init__(self, parent: Optional[QWidget] = None):
        """Initialize the login dialog.

        Args:
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._logger = logging.getLogger("bmlibrarian.gui.qt.LoginDialog")

        # Result data
        self._login_result: Optional[LoginResult] = None
        self._connection = None

        # Setup UI
        self._setup_ui()
        self._load_saved_db_config()

    def _setup_ui(self) -> None:
        """Setup the dialog UI."""
        self.setWindowTitle("BMLibrarian - Login")
        self.setModal(True)

        # Get DPI-aware dimensions
        scale = get_scale_value
        char_width = scale('char_width', 8)
        padding = scale('padding_medium', 10)
        spacing = scale('spacing_medium', 8)

        # Calculate field width based on characters
        field_width = max(300, char_width * self.FIELD_WIDTH_CHARS)
        button_min_width = max(100, char_width * self.BUTTON_MIN_WIDTH_CHARS)

        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(spacing)
        main_layout.setContentsMargins(padding, padding, padding, padding)

        # Title
        title_label = QLabel("BMLibrarian")
        title_font = QFont()
        title_font.setPointSize(scale('font_xlarge', 16))
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(title_label)

        subtitle_label = QLabel("Biomedical Literature Research Platform")
        subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(subtitle_label)

        # Add separator
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        main_layout.addWidget(separator)

        # Tab widget
        self.tab_widget = QTabWidget()
        main_layout.addWidget(self.tab_widget)

        # Create tabs
        self._create_login_tab(field_width)
        self._create_db_config_tab(field_width)

        # Set minimum size based on content
        self.setMinimumWidth(field_width + padding * 4)

    def _create_login_tab(self, field_width: int) -> None:
        """Create the login/registration tab.

        Args:
            field_width: Width for input fields.
        """
        tab = QWidget()
        layout = QVBoxLayout(tab)

        scale = get_scale_value
        spacing = scale('spacing_medium', 8)
        padding = scale('padding_medium', 10)

        layout.setSpacing(spacing)
        layout.setContentsMargins(padding, padding, padding, padding)

        # Login group
        login_group = QGroupBox("Login")
        login_layout = QFormLayout()
        login_layout.setSpacing(spacing)

        self.login_username = QLineEdit()
        self.login_username.setPlaceholderText("Enter your username")
        self.login_username.setMinimumWidth(field_width)
        login_layout.addRow("Username:", self.login_username)

        self.login_password = QLineEdit()
        self.login_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.login_password.setPlaceholderText("Enter your password")
        self.login_password.setMinimumWidth(field_width)
        login_layout.addRow("Password:", self.login_password)

        login_group.setLayout(login_layout)
        layout.addWidget(login_group)

        # Login button
        self.login_button = QPushButton("Login")
        self.login_button.clicked.connect(self._on_login)
        self.login_password.returnPressed.connect(self._on_login)
        layout.addWidget(self.login_button)

        # Separator
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(separator)

        # Registration group
        reg_group = QGroupBox("New User Registration")
        reg_layout = QFormLayout()
        reg_layout.setSpacing(spacing)

        self.reg_username = QLineEdit()
        self.reg_username.setPlaceholderText("Choose a username")
        self.reg_username.setMinimumWidth(field_width)
        reg_layout.addRow("Username:", self.reg_username)

        self.reg_email = QLineEdit()
        self.reg_email.setPlaceholderText("your.email@example.com")
        self.reg_email.setMinimumWidth(field_width)
        reg_layout.addRow("Email:", self.reg_email)

        self.reg_password = QLineEdit()
        self.reg_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.reg_password.setPlaceholderText("Choose a password (min 4 chars)")
        self.reg_password.setMinimumWidth(field_width)
        reg_layout.addRow("Password:", self.reg_password)

        self.reg_password_confirm = QLineEdit()
        self.reg_password_confirm.setEchoMode(QLineEdit.EchoMode.Password)
        self.reg_password_confirm.setPlaceholderText("Confirm your password")
        self.reg_password_confirm.setMinimumWidth(field_width)
        reg_layout.addRow("Confirm:", self.reg_password_confirm)

        reg_group.setLayout(reg_layout)
        layout.addWidget(reg_group)

        # Register button
        self.register_button = QPushButton("Register")
        self.register_button.clicked.connect(self._on_register)
        layout.addWidget(self.register_button)

        layout.addStretch()
        self.tab_widget.addTab(tab, "Login / Register")

    def _create_db_config_tab(self, field_width: int) -> None:
        """Create the database configuration tab.

        Args:
            field_width: Width for input fields.
        """
        tab = QWidget()
        layout = QVBoxLayout(tab)

        scale = get_scale_value
        spacing = scale('spacing_medium', 8)
        padding = scale('padding_medium', 10)

        layout.setSpacing(spacing)
        layout.setContentsMargins(padding, padding, padding, padding)

        # Info label
        info_label = QLabel(
            "Configure the PostgreSQL database connection.\n"
            "These settings are required to connect to the BMLibrarian database."
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        # Connection group
        conn_group = QGroupBox("PostgreSQL Connection")
        conn_layout = QFormLayout()
        conn_layout.setSpacing(spacing)

        self.db_host = QLineEdit()
        self.db_host.setPlaceholderText("localhost")
        self.db_host.setText("localhost")
        self.db_host.setMinimumWidth(field_width)
        conn_layout.addRow("Host:", self.db_host)

        self.db_port = QSpinBox()
        self.db_port.setRange(1, 65535)
        self.db_port.setValue(5432)
        self.db_port.setMinimumWidth(field_width)
        conn_layout.addRow("Port:", self.db_port)

        self.db_name = QLineEdit()
        self.db_name.setPlaceholderText("knowledgebase")
        self.db_name.setText("knowledgebase")
        self.db_name.setMinimumWidth(field_width)
        conn_layout.addRow("Database:", self.db_name)

        self.db_user = QLineEdit()
        self.db_user.setPlaceholderText("Database username")
        self.db_user.setMinimumWidth(field_width)
        conn_layout.addRow("Username:", self.db_user)

        self.db_password = QLineEdit()
        self.db_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.db_password.setPlaceholderText("Database password")
        self.db_password.setMinimumWidth(field_width)
        conn_layout.addRow("Password:", self.db_password)

        conn_group.setLayout(conn_layout)
        layout.addWidget(conn_group)

        # Save checkbox
        self.save_db_config = QCheckBox("Save connection settings")
        self.save_db_config.setChecked(True)
        layout.addWidget(self.save_db_config)

        # Buttons
        button_layout = QHBoxLayout()

        self.test_conn_button = QPushButton("Test Connection")
        self.test_conn_button.clicked.connect(self._on_test_connection)
        button_layout.addWidget(self.test_conn_button)

        self.save_conn_button = QPushButton("Save Settings")
        self.save_conn_button.clicked.connect(self._on_save_db_config)
        button_layout.addWidget(self.save_conn_button)

        layout.addLayout(button_layout)

        # Status label
        self.db_status_label = QLabel("")
        self.db_status_label.setWordWrap(True)
        layout.addWidget(self.db_status_label)

        layout.addStretch()
        self.tab_widget.addTab(tab, "Database Connection")

    def _load_saved_db_config(self) -> None:
        """Load saved database configuration from environment or .env file."""
        # Try environment variables first
        self.db_host.setText(os.environ.get("POSTGRES_HOST", "localhost"))
        self.db_port.setValue(int(os.environ.get("POSTGRES_PORT", "5432")))
        self.db_name.setText(os.environ.get("POSTGRES_DB", "knowledgebase"))
        self.db_user.setText(os.environ.get("POSTGRES_USER", ""))
        self.db_password.setText(os.environ.get("POSTGRES_PASSWORD", ""))

        # Try to load from .env file if env vars are not set
        if not self.db_user.text():
            self._load_from_env_file()

    def _load_from_env_file(self) -> None:
        """Load database config from .env file."""
        env_paths = [
            Path.home() / ".bmlibrarian" / ".env",
            Path.cwd() / ".env",
        ]

        for env_path in env_paths:
            if env_path.exists():
                try:
                    self._parse_env_file(env_path)
                    self._logger.info(f"Loaded database config from {env_path}")
                    break
                except Exception as e:
                    self._logger.warning(f"Failed to parse {env_path}: {e}")

    def _parse_env_file(self, path: Path) -> None:
        """Parse a .env file and update UI fields.

        Args:
            path: Path to the .env file.
        """
        with open(path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")

                    if key == "POSTGRES_HOST" and value:
                        self.db_host.setText(value)
                    elif key == "POSTGRES_PORT" and value:
                        try:
                            self.db_port.setValue(int(value))
                        except ValueError:
                            pass
                    elif key == "POSTGRES_DB" and value:
                        self.db_name.setText(value)
                    elif key == "POSTGRES_USER" and value:
                        self.db_user.setText(value)
                    elif key == "POSTGRES_PASSWORD" and value:
                        self.db_password.setText(value)

    def _get_db_config(self) -> DatabaseConfig:
        """Get the current database configuration from UI fields.

        Returns:
            DatabaseConfig object with current settings.
        """
        return DatabaseConfig(
            host=self.db_host.text().strip() or "localhost",
            port=self.db_port.value(),
            database=self.db_name.text().strip() or "knowledgebase",
            user=self.db_user.text().strip(),
            password=self.db_password.text(),
        )

    def _on_test_connection(self) -> None:
        """Test the database connection."""
        db_config = self._get_db_config()

        if not db_config.user:
            QMessageBox.warning(
                self,
                "Missing Information",
                "Please enter a database username."
            )
            return

        self.db_status_label.setText("Testing connection...")
        self.db_status_label.repaint()

        try:
            import psycopg

            conn_string = (
                f"host={db_config.host} "
                f"port={db_config.port} "
                f"dbname={db_config.database} "
                f"user={db_config.user} "
                f"password={db_config.password}"
            )

            with psycopg.connect(conn_string, connect_timeout=10) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT version()")
                    version = cur.fetchone()[0]

                    # Check if required tables exist
                    cur.execute(
                        "SELECT EXISTS(SELECT 1 FROM information_schema.tables "
                        "WHERE table_schema = 'public' AND table_name = 'users')"
                    )
                    users_exists = cur.fetchone()[0]

                    cur.execute(
                        "SELECT EXISTS(SELECT 1 FROM information_schema.schemata "
                        "WHERE schema_name = 'bmlsettings')"
                    )
                    settings_exists = cur.fetchone()[0]

            status_parts = [f"Connected successfully!\n{version[:50]}..."]
            if users_exists:
                status_parts.append("Users table: OK")
            else:
                status_parts.append("Users table: NOT FOUND")
            if settings_exists:
                status_parts.append("Settings schema: OK")
            else:
                status_parts.append("Settings schema: NOT FOUND (run migrations)")

            self.db_status_label.setText("\n".join(status_parts))
            self._logger.info("Database connection test successful")

        except Exception as e:
            error_msg = f"Connection failed: {e}"
            self.db_status_label.setText(error_msg)
            self._logger.error(f"Database connection test failed: {e}")

    def _on_save_db_config(self) -> None:
        """Save the database configuration to .env file."""
        db_config = self._get_db_config()

        if not db_config.user:
            QMessageBox.warning(
                self,
                "Missing Information",
                "Please enter a database username."
            )
            return

        # Create .bmlibrarian directory if needed
        config_dir = Path.home() / ".bmlibrarian"
        config_dir.mkdir(parents=True, exist_ok=True)

        env_path = config_dir / ".env"

        try:
            # Read existing content (if any) to preserve other settings
            existing_lines = []
            if env_path.exists():
                with open(env_path, 'r') as f:
                    for line in f:
                        stripped = line.strip()
                        if stripped and not stripped.startswith('#'):
                            key = stripped.split('=', 1)[0].strip()
                            if key not in db_config.to_env_dict():
                                existing_lines.append(line.rstrip())

            # Write new config
            with open(env_path, 'w') as f:
                f.write("# BMLibrarian Database Configuration\n")
                f.write("# Auto-generated by BMLibrarian GUI\n\n")

                for key, value in db_config.to_env_dict().items():
                    f.write(f"{key}={value}\n")

                if existing_lines:
                    f.write("\n# Other settings\n")
                    for line in existing_lines:
                        f.write(f"{line}\n")

            # Also set environment variables for current session
            for key, value in db_config.to_env_dict().items():
                os.environ[key] = value

            self.db_status_label.setText(f"Configuration saved to:\n{env_path}")
            self._logger.info(f"Saved database config to {env_path}")

            QMessageBox.information(
                self,
                "Settings Saved",
                f"Database settings saved to:\n{env_path}"
            )

        except Exception as e:
            error_msg = f"Failed to save settings: {e}"
            self.db_status_label.setText(error_msg)
            self._logger.error(f"Failed to save database config: {e}")
            QMessageBox.critical(self, "Error", error_msg)

    def _get_db_connection(self):
        """Get a database connection using current settings.

        Returns:
            A psycopg connection object.

        Raises:
            Exception: If connection fails.
        """
        import psycopg

        db_config = self._get_db_config()

        # Set environment variables for the DatabaseManager
        for key, value in db_config.to_env_dict().items():
            os.environ[key] = value

        conn_string = (
            f"host={db_config.host} "
            f"port={db_config.port} "
            f"dbname={db_config.database} "
            f"user={db_config.user} "
            f"password={db_config.password}"
        )

        return psycopg.connect(conn_string, connect_timeout=10)

    def _on_login(self) -> None:
        """Handle login button click."""
        username = self.login_username.text().strip()
        password = self.login_password.text()

        if not username:
            QMessageBox.warning(self, "Missing Information", "Please enter your username.")
            self.login_username.setFocus()
            return

        if not password:
            QMessageBox.warning(self, "Missing Information", "Please enter your password.")
            self.login_password.setFocus()
            return

        # Validate database config
        db_config = self._get_db_config()
        if not db_config.user:
            QMessageBox.warning(
                self,
                "Database Not Configured",
                "Please configure the database connection in the 'Database Connection' tab first."
            )
            self.tab_widget.setCurrentIndex(1)
            return

        try:
            # Get database connection
            conn = self._get_db_connection()

            # Import here to avoid circular imports
            from ....auth import UserService

            user_service = UserService(conn)
            user, session_token = user_service.authenticate(
                username=username,
                password=password,
                client_type="qt_gui",
                hostname=socket.gethostname(),
                create_session=True
            )

            self._login_result = LoginResult(
                user_id=user.id,
                username=user.username,
                email=user.email,
                session_token=session_token,
                db_config=db_config
            )

            self._connection = conn
            self._logger.info(f"User logged in: {username}")

            # Save DB config if checkbox is checked
            if self.save_db_config.isChecked():
                self._on_save_db_config()

            self.login_successful.emit(user.id)
            self.accept()

        except Exception as e:
            error_str = str(e)
            if "not found" in error_str.lower():
                QMessageBox.warning(
                    self,
                    "Login Failed",
                    f"User '{username}' not found. Please check your username or register a new account."
                )
            elif "invalid password" in error_str.lower():
                QMessageBox.warning(
                    self,
                    "Login Failed",
                    "Invalid password. Please try again."
                )
            elif "connection" in error_str.lower():
                QMessageBox.critical(
                    self,
                    "Connection Error",
                    f"Failed to connect to database:\n{e}\n\n"
                    "Please check your database settings in the 'Database Connection' tab."
                )
                self.tab_widget.setCurrentIndex(1)
            else:
                QMessageBox.critical(
                    self,
                    "Login Error",
                    f"An error occurred during login:\n{e}"
                )
            self._logger.error(f"Login failed for {username}: {e}")

    def _on_register(self) -> None:
        """Handle register button click."""
        username = self.reg_username.text().strip()
        email = self.reg_email.text().strip()
        password = self.reg_password.text()
        password_confirm = self.reg_password_confirm.text()

        # Validate inputs
        if not username:
            QMessageBox.warning(self, "Missing Information", "Please enter a username.")
            self.reg_username.setFocus()
            return

        if not email:
            QMessageBox.warning(self, "Missing Information", "Please enter an email address.")
            self.reg_email.setFocus()
            return

        if '@' not in email or '.' not in email:
            QMessageBox.warning(self, "Invalid Email", "Please enter a valid email address.")
            self.reg_email.setFocus()
            return

        if not password:
            QMessageBox.warning(self, "Missing Information", "Please enter a password.")
            self.reg_password.setFocus()
            return

        if len(password) < 4:
            QMessageBox.warning(
                self,
                "Password Too Short",
                "Password must be at least 4 characters long."
            )
            self.reg_password.setFocus()
            return

        if password != password_confirm:
            QMessageBox.warning(self, "Password Mismatch", "Passwords do not match.")
            self.reg_password_confirm.setFocus()
            return

        # Validate database config
        db_config = self._get_db_config()
        if not db_config.user:
            QMessageBox.warning(
                self,
                "Database Not Configured",
                "Please configure the database connection in the 'Database Connection' tab first."
            )
            self.tab_widget.setCurrentIndex(1)
            return

        try:
            # Get database connection
            conn = self._get_db_connection()

            # Import here to avoid circular imports
            from ....auth import UserService

            user_service = UserService(conn)
            user = user_service.register(
                username=username,
                email=email,
                password=password
            )

            # Auto-login after registration
            _, session_token = user_service.authenticate(
                username=username,
                password=password,
                client_type="qt_gui",
                hostname=socket.gethostname(),
                create_session=True
            )

            self._login_result = LoginResult(
                user_id=user.id,
                username=user.username,
                email=user.email,
                session_token=session_token,
                db_config=db_config
            )

            self._connection = conn
            self._logger.info(f"User registered and logged in: {username}")

            # Save DB config if checkbox is checked
            if self.save_db_config.isChecked():
                self._on_save_db_config()

            QMessageBox.information(
                self,
                "Registration Successful",
                f"Welcome, {username}! Your account has been created."
            )

            self.login_successful.emit(user.id)
            self.accept()

        except Exception as e:
            error_str = str(e)
            if "username" in error_str.lower() and "exists" in error_str.lower():
                QMessageBox.warning(
                    self,
                    "Registration Failed",
                    f"Username '{username}' is already taken. Please choose a different username."
                )
                self.reg_username.setFocus()
            elif "email" in error_str.lower() and "exists" in error_str.lower():
                QMessageBox.warning(
                    self,
                    "Registration Failed",
                    f"Email '{email}' is already registered. Please use a different email or login."
                )
                self.reg_email.setFocus()
            elif "connection" in error_str.lower():
                QMessageBox.critical(
                    self,
                    "Connection Error",
                    f"Failed to connect to database:\n{e}\n\n"
                    "Please check your database settings in the 'Database Connection' tab."
                )
                self.tab_widget.setCurrentIndex(1)
            else:
                QMessageBox.critical(
                    self,
                    "Registration Error",
                    f"An error occurred during registration:\n{e}"
                )
            self._logger.error(f"Registration failed for {username}: {e}")

    def get_login_result(self) -> Optional[LoginResult]:
        """Get the login result after successful authentication.

        Returns:
            LoginResult object if login was successful, None otherwise.
        """
        return self._login_result

    def get_connection(self):
        """Get the database connection established during login.

        Returns:
            The psycopg connection object, or None if not connected.
        """
        return self._connection
