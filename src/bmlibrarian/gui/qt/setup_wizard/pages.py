"""
Wizard pages for BMLibrarian Setup Wizard.

Contains all QWizardPage implementations for the setup process.
"""

import logging
import os
from pathlib import Path
from typing import Optional, List, Dict, Any, TYPE_CHECKING

from PySide6.QtWidgets import (
    QWizardPage,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QTextEdit,
    QTextBrowser,
    QGroupBox,
    QCheckBox,
    QRadioButton,
    QButtonGroup,
    QProgressBar,
    QPushButton,
    QFileDialog,
    QSpinBox,
    QMessageBox,
    QFrame,
    QScrollArea,
    QWidget,
    QSplitter,
    QListWidget,
    QListWidgetItem,
)
from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtGui import QFont, QIntValidator

from ..resources.styles.dpi_scale import get_font_scale
from ..resources.styles.stylesheet_generator import StylesheetGenerator
from .constants import (
    DEFAULT_POSTGRES_HOST,
    DEFAULT_POSTGRES_PORT,
    DB_CONNECTION_TIMEOUT_SECONDS,
    MEDRXIV_DEFAULT_DAYS,
    MEDRXIV_MIN_DAYS,
    MEDRXIV_MAX_DAYS,
    MEDRXIV_FULL_IMPORT_DAYS,
    PUBMED_DEFAULT_MAX_RESULTS,
    PUBMED_MIN_RESULTS,
    PUBMED_MAX_RESULTS,
    PUBMED_TEST_QUERY,
    TABLE_DISPLAY_LIMIT,
    SQL_TEXT_HEIGHT_MULTIPLIER,
    LOG_TEXT_HEIGHT_MULTIPLIER,
    PROGRESS_MEDRXIV_START,
    PROGRESS_PUBMED_START,
    PROGRESS_COMPLETE,
    REQUIRED_EXTENSIONS,
    COLOR_ERROR,
    COLOR_WARNING,
    COLOR_SUCCESS,
    COLOR_MUTED,
    FRAME_NOTE_BG,
    FRAME_NOTE_BORDER,
    FRAME_WARNING_BG,
    FRAME_WARNING_BORDER,
    FRAME_SUCCESS_BG,
    FRAME_SUCCESS_BORDER,
)

if TYPE_CHECKING:
    from .wizard import SetupWizard


logger = logging.getLogger(__name__)

# File permission constant for secure .env files (owner read/write only)
ENV_FILE_PERMISSIONS = 0o600


def find_project_root() -> Path:
    """
    Find the project root directory by looking for pyproject.toml.

    Searches from the current file's location upward through parent directories
    until it finds a directory containing pyproject.toml or reaches the
    filesystem root.

    Returns:
        Path: The project root directory, or current working directory if not found.
    """
    current = Path(__file__).parent
    while current != current.parent:
        if (current / "pyproject.toml").exists():
            return current
        current = current.parent
    # Fallback to current working directory
    return Path.cwd()


def _create_frame_stylesheet(
    scale: dict, bg_color: str, border_color: str, object_name: str
) -> str:
    """
    Create a stylesheet for a colored frame using StylesheetGenerator.

    Args:
        scale: Font scale dictionary
        bg_color: Background color hex code
        border_color: Border color hex code
        object_name: QFrame object name for CSS selector

    Returns:
        str: Generated stylesheet string
    """
    gen = StylesheetGenerator(scale)
    # Use double braces for CSS syntax, single braces for format placeholders
    # Note: f-string is NOT used here to avoid conflicts with .format()
    template = """
        QFrame#OBJECT_NAME {{
            background-color: BG_COLOR;
            border: 1px solid BORDER_COLOR;
            border-radius: {radius_small}px;
            padding: {padding_medium}px;
        }}
    """
    # First substitute scale values, then replace our placeholders
    styled = gen.custom(template)
    return styled.replace("OBJECT_NAME", object_name).replace("BG_COLOR", bg_color).replace("BORDER_COLOR", border_color)


# =============================================================================
# Welcome Page
# =============================================================================


class WelcomePage(QWizardPage):
    """
    Welcome page introducing the setup wizard.

    Displays overview of what the wizard will configure.
    """

    def __init__(self, parent: Optional["SetupWizard"] = None):
        """Initialize welcome page."""
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the welcome page UI."""
        scale = get_font_scale()

        self.setTitle("Welcome to BMLibrarian Setup")
        self.setSubTitle(
            "This wizard will help you configure BMLibrarian for first use."
        )

        layout = QVBoxLayout(self)
        layout.setSpacing(scale["spacing_large"])

        # Welcome message
        welcome_text = QLabel(
            "BMLibrarian is a comprehensive Python library for AI-powered "
            "access to biomedical literature databases.\n\n"
            "This setup wizard will guide you through:\n\n"
            "  1. PostgreSQL database configuration\n"
            "  2. Database schema initialization\n"
            "  3. Optional data import from PubMed and medRxiv\n\n"
            "Before proceeding, please ensure you have:\n\n"
            "  - PostgreSQL server installed and running\n"
            "  - pgvector extension available\n"
            "  - plpython3u extension available\n"
            "  - Database administrator credentials"
        )
        welcome_text.setWordWrap(True)
        layout.addWidget(welcome_text)

        # Requirements note
        note_frame = QFrame()
        note_frame.setObjectName("noteFrame")
        note_frame.setStyleSheet(
            _create_frame_stylesheet(scale, FRAME_NOTE_BG, FRAME_NOTE_BORDER, "noteFrame")
        )

        note_layout = QVBoxLayout(note_frame)
        note_label = QLabel(
            "Note: The wizard will check if the database already contains "
            "tables. If it does, you will need to specify a different "
            "(empty) database name to avoid data loss."
        )
        note_label.setWordWrap(True)
        note_layout.addWidget(note_label)

        layout.addWidget(note_frame)
        layout.addStretch()


# =============================================================================
# Database Instructions Page
# =============================================================================


class DatabaseInstructionsPage(QWizardPage):
    """
    Page explaining the automated database setup process.

    Informs the user what will be created automatically.
    """

    def __init__(self, parent: Optional["SetupWizard"] = None):
        """Initialize database instructions page."""
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the instructions page UI."""
        scale = get_font_scale()

        self.setTitle("PostgreSQL Database Setup")
        self.setSubTitle(
            "The wizard will automatically set up your database."
        )

        layout = QVBoxLayout(self)
        layout.setSpacing(scale["spacing_large"])

        # What will be created
        overview = QLabel(
            "BMLibrarian requires PostgreSQL with specific extensions for "
            "semantic search and text processing.\n\n"
            "On the next page, you'll provide PostgreSQL superuser credentials, "
            "and the wizard will automatically:"
        )
        overview.setWordWrap(True)
        layout.addWidget(overview)

        # Steps that will be performed
        steps_frame = QFrame()
        steps_frame.setObjectName("stepsFrame")
        steps_frame.setStyleSheet(
            _create_frame_stylesheet(scale, FRAME_NOTE_BG, FRAME_NOTE_BORDER, "stepsFrame")
        )
        steps_layout = QVBoxLayout(steps_frame)

        steps = [
            "1. Create the 'bmlibrarian' database",
            "2. Install required extensions:",
            "      • pgvector (semantic similarity search)",
            "      • plpython3u (embedding generation)",
            "      • pg_trgm (trigram text search)",
            "3. Create a 'bmlibrarian' database user",
            "4. Grant appropriate permissions",
            "5. Apply the database schema",
        ]
        for step in steps:
            step_label = QLabel(step)
            steps_layout.addWidget(step_label)

        layout.addWidget(steps_frame)

        # Prerequisites note
        prereq_label = QLabel(
            "\nPrerequisites:\n\n"
            "  • PostgreSQL must be installed and running\n"
            "  • You need superuser credentials (e.g., 'postgres' user)\n"
            "  • pgvector extension must be available on your system:\n"
            "      - macOS (Homebrew): brew install pgvector\n"
            "      - Ubuntu/Debian: sudo apt install postgresql-16-pgvector\n"
            "      - Or compile from source: github.com/pgvector/pgvector"
        )
        prereq_label.setWordWrap(True)
        layout.addWidget(prereq_label)

        layout.addStretch()


# =============================================================================
# Database Configuration Page
# =============================================================================

# Default database name and application user
DEFAULT_DATABASE_NAME = "bmlibrarian"
DEFAULT_APP_USER = "bmlibrarian"


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
        app_user_group = QGroupBox(f"BMLibrarian Application User")
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


# =============================================================================
# Database Setup Page
# =============================================================================


class DatabaseSetupWorker(QThread):
    """
    Worker thread for complete database setup operations.

    Performs (using superuser credentials):
    1. Create the bmlibrarian database (if not exists)
    2. Create required extensions (vector, plpython3u, pg_trgm)
    3. Create the bmlibrarian application user
    4. Grant appropriate permissions
    5. Create .env file
    6. Apply database schema (using app user)
    """

    progress = Signal(str)  # Progress message
    finished = Signal(bool, str)  # Success, message
    table_check = Signal(bool, list)  # Has tables, table list (for compatibility)

    def __init__(
        self,
        host: str,
        port: str,
        superuser: str,
        superuser_password: str,
        app_user: str,
        app_password: str,
        dbname: str,
        pdf_dir: str,
        parent: Optional[object] = None,
    ):
        """Initialize the worker."""
        super().__init__(parent)
        self.host = host
        self.port = port
        self.superuser = superuser
        self.superuser_password = superuser_password
        self.app_user = app_user
        self.app_password = app_password
        self.dbname = dbname
        self.pdf_dir = pdf_dir

    def run(self) -> None:
        """Execute complete database setup."""
        try:
            import psycopg

            # NOTE: Direct psycopg usage is necessary here during bootstrapping
            # before DatabaseManager is available. This is an exception to Golden
            # Rule #5 ("All postgres database communication happens through the
            # database manager") because we need to create the database itself.

            # Step 1: Connect to postgres database as superuser
            self.progress.emit("Connecting as superuser...")
            postgres_conn_params = {
                'host': self.host,
                'port': int(self.port),
                'dbname': 'postgres',
                'user': self.superuser,
                'password': self.superuser_password,
                'connect_timeout': DB_CONNECTION_TIMEOUT_SECONDS,
                'autocommit': True,  # Required for CREATE DATABASE
            }

            with psycopg.connect(**postgres_conn_params) as conn:
                with conn.cursor() as cur:
                    # Step 2: Check if database exists
                    self.progress.emit(f"Checking if database '{self.dbname}' exists...")
                    cur.execute(
                        "SELECT 1 FROM pg_database WHERE datname = %s",
                        (self.dbname,)
                    )
                    db_exists = cur.fetchone() is not None

                    if not db_exists:
                        # Create the database
                        self.progress.emit(f"Creating database '{self.dbname}'...")
                        # Use SQL identifier quoting for safety
                        cur.execute(
                            psycopg.sql.SQL("CREATE DATABASE {}").format(
                                psycopg.sql.Identifier(self.dbname)
                            )
                        )
                        logger.info(f"Created database '{self.dbname}'")
                    else:
                        self.progress.emit(f"Database '{self.dbname}' already exists")

                    # Step 3: Check if user exists
                    self.progress.emit(f"Checking if user '{self.app_user}' exists...")
                    cur.execute(
                        "SELECT 1 FROM pg_roles WHERE rolname = %s",
                        (self.app_user,)
                    )
                    user_exists = cur.fetchone() is not None

                    if not user_exists:
                        # Create the application user
                        # Using sql.Literal for password to safely escape it
                        self.progress.emit(f"Creating user '{self.app_user}'...")
                        cur.execute(
                            psycopg.sql.SQL("CREATE USER {} WITH PASSWORD {}").format(
                                psycopg.sql.Identifier(self.app_user),
                                psycopg.sql.Literal(self.app_password)
                            )
                        )
                        logger.info(f"Created user '{self.app_user}'")
                    else:
                        # Update password for existing user
                        # Using sql.Literal for password to safely escape it
                        self.progress.emit(f"Updating password for user '{self.app_user}'...")
                        cur.execute(
                            psycopg.sql.SQL("ALTER USER {} WITH PASSWORD {}").format(
                                psycopg.sql.Identifier(self.app_user),
                                psycopg.sql.Literal(self.app_password)
                            )
                        )
                        logger.info(f"Updated password for existing user '{self.app_user}'")

            # Step 4: Connect to the new database to create extensions and grant permissions
            self.progress.emit(f"Connecting to '{self.dbname}' database...")
            db_conn_params = {
                'host': self.host,
                'port': int(self.port),
                'dbname': self.dbname,
                'user': self.superuser,
                'password': self.superuser_password,
                'connect_timeout': DB_CONNECTION_TIMEOUT_SECONDS,
            }

            with psycopg.connect(**db_conn_params) as conn:
                with conn.cursor() as cur:
                    # Create extensions
                    for ext in REQUIRED_EXTENSIONS:
                        self.progress.emit(f"Creating extension '{ext}'...")
                        cur.execute(
                            psycopg.sql.SQL("CREATE EXTENSION IF NOT EXISTS {}").format(
                                psycopg.sql.Identifier(ext)
                            )
                        )
                        logger.info(f"Created extension '{ext}'")

                    # Grant privileges on database
                    self.progress.emit(f"Granting database privileges to '{self.app_user}'...")
                    cur.execute(
                        psycopg.sql.SQL("GRANT ALL PRIVILEGES ON DATABASE {} TO {}").format(
                            psycopg.sql.Identifier(self.dbname),
                            psycopg.sql.Identifier(self.app_user)
                        )
                    )

                    # Grant privileges on public schema (required for PostgreSQL 15+)
                    self.progress.emit(f"Granting schema privileges to '{self.app_user}'...")
                    cur.execute(
                        psycopg.sql.SQL("GRANT USAGE, CREATE ON SCHEMA public TO {}").format(
                            psycopg.sql.Identifier(self.app_user)
                        )
                    )

                    # Set default privileges for future tables
                    cur.execute(
                        psycopg.sql.SQL(
                            "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
                            "GRANT ALL ON TABLES TO {}"
                        ).format(psycopg.sql.Identifier(self.app_user))
                    )
                    cur.execute(
                        psycopg.sql.SQL(
                            "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
                            "GRANT ALL ON SEQUENCES TO {}"
                        ).format(psycopg.sql.Identifier(self.app_user))
                    )

                    # Check for existing tables (for table_check signal compatibility)
                    cur.execute("""
                        SELECT table_name FROM information_schema.tables
                        WHERE table_schema = 'public'
                        AND table_type = 'BASE TABLE'
                    """)
                    tables = [row[0] for row in cur.fetchall()]
                    self.table_check.emit(len(tables) > 0, tables)

                conn.commit()

            # Step 5: Create .env file
            self.progress.emit("Creating configuration files...")
            self._create_env_file()

            # Step 6: Apply schema using app user credentials
            self.progress.emit("Applying database schema...")
            self._apply_schema()

            # Step 7: Seed required data (sources table)
            self.progress.emit("Seeding required data...")
            self._seed_required_data()

            self.finished.emit(
                True,
                f"Database setup completed successfully!\n\n"
                f"• Database: {self.dbname}\n"
                f"• User: {self.app_user}\n"
                f"• Extensions: {', '.join(REQUIRED_EXTENSIONS)}"
            )

        except Exception as e:
            logger.error(f"Database setup failed: {e}", exc_info=True)
            self.finished.emit(False, f"Setup failed: {str(e)}")

    def _create_env_file(self) -> None:
        """
        Create the .env file with configuration.

        Creates .env files in two locations:
        1. ~/.bmlibrarian/.env (PRIMARY - user configuration directory)
        2. <project_root>/.env (for development convenience)

        Both files are created with restrictive permissions (0o600) to protect
        sensitive credentials from unauthorized access.
        """
        env_content = f"""# BMLibrarian Configuration
# Generated by Setup Wizard

# PostgreSQL Connection (application user)
POSTGRES_HOST={self.host}
POSTGRES_PORT={self.port}
POSTGRES_DB={self.dbname}
POSTGRES_USER={self.app_user}
POSTGRES_PASSWORD={self.app_password}

# File System
PDF_BASE_DIR={self.pdf_dir}

# Ollama (default)
OLLAMA_HOST=http://localhost:11434
"""

        # PRIMARY: Create in ~/.bmlibrarian (checked first when loading config)
        config_dir = Path.home() / ".bmlibrarian"
        config_dir.mkdir(mode=0o700, exist_ok=True)  # Secure directory permissions
        user_env_path = config_dir / ".env"
        user_env_path.write_text(env_content)
        user_env_path.chmod(ENV_FILE_PERMISSIONS)  # Owner read/write only
        logger.info(f"Created primary .env file at {user_env_path} (mode 0o600)")

        # SECONDARY: Write to project root for development convenience
        project_root = find_project_root()
        project_env_path = project_root / ".env"
        try:
            project_env_path.write_text(env_content)
            project_env_path.chmod(ENV_FILE_PERMISSIONS)  # Owner read/write only
            logger.info(f"Created project .env file at {project_env_path} (mode 0o600)")
        except PermissionError as e:
            # Project directory may not be writable in some deployments
            logger.warning(f"Could not create project .env file: {e}")

        # Set environment variables for current session
        os.environ["POSTGRES_HOST"] = self.host
        os.environ["POSTGRES_PORT"] = self.port
        os.environ["POSTGRES_DB"] = self.dbname
        os.environ["POSTGRES_USER"] = self.app_user
        os.environ["POSTGRES_PASSWORD"] = self.app_password
        os.environ["PDF_BASE_DIR"] = self.pdf_dir

    def _apply_schema(self) -> None:
        """
        Apply the database schema.

        Uses superuser credentials for baseline schema (may contain extension
        commands requiring superuser), then grants ownership to app user.
        """
        from bmlibrarian.migrations import MigrationManager

        # Get paths using robust project root detection
        project_root = find_project_root()
        baseline_path = project_root / "baseline_schema.sql"
        migrations_dir = project_root / "migrations"

        # Apply baseline schema as superuser (may contain extension commands)
        if baseline_path.exists():
            self.progress.emit("Initializing baseline schema (as superuser)...")
            superuser_manager = MigrationManager(
                host=self.host,
                port=self.port,
                user=self.superuser,
                password=self.superuser_password,
                database=self.dbname,
            )
            superuser_manager.initialize_database(baseline_path)

            # Grant ownership of all tables/sequences to app user
            self.progress.emit("Transferring table ownership to app user...")
            self._transfer_ownership()

        # Apply migrations as app user (should not need superuser)
        if migrations_dir.exists():
            self.progress.emit("Applying migrations...")
            app_manager = MigrationManager(
                host=self.host,
                port=self.port,
                user=self.app_user,
                password=self.app_password,
                database=self.dbname,
            )
            app_manager.apply_pending_migrations(migrations_dir, silent=True)

    def _transfer_ownership(self) -> None:
        """Transfer ownership of all tables, sequences, and functions to app user."""
        import psycopg

        conn_params = {
            'host': self.host,
            'port': int(self.port),
            'dbname': self.dbname,
            'user': self.superuser,
            'password': self.superuser_password,
            'connect_timeout': DB_CONNECTION_TIMEOUT_SECONDS,
        }

        with psycopg.connect(**conn_params) as conn:
            with conn.cursor() as cur:
                # Transfer ownership of all tables in public schema
                cur.execute("""
                    SELECT tablename FROM pg_tables WHERE schemaname = 'public'
                """)
                tables = [row[0] for row in cur.fetchall()]
                for table in tables:
                    cur.execute(
                        psycopg.sql.SQL("ALTER TABLE {} OWNER TO {}").format(
                            psycopg.sql.Identifier(table),
                            psycopg.sql.Identifier(self.app_user)
                        )
                    )

                # Transfer ownership of all sequences
                cur.execute("""
                    SELECT sequencename FROM pg_sequences WHERE schemaname = 'public'
                """)
                sequences = [row[0] for row in cur.fetchall()]
                for seq in sequences:
                    cur.execute(
                        psycopg.sql.SQL("ALTER SEQUENCE {} OWNER TO {}").format(
                            psycopg.sql.Identifier(seq),
                            psycopg.sql.Identifier(self.app_user)
                        )
                    )

                # Grant usage on all schemas that may have been created
                cur.execute("""
                    SELECT nspname FROM pg_namespace
                    WHERE nspname NOT LIKE 'pg_%' AND nspname != 'information_schema'
                """)
                schemas = [row[0] for row in cur.fetchall()]
                for schema in schemas:
                    cur.execute(
                        psycopg.sql.SQL("GRANT ALL ON SCHEMA {} TO {}").format(
                            psycopg.sql.Identifier(schema),
                            psycopg.sql.Identifier(self.app_user)
                        )
                    )

            conn.commit()
        logger.info(f"Transferred ownership of {len(tables)} tables and {len(sequences)} sequences to '{self.app_user}'")

    def _seed_required_data(self) -> None:
        """
        Seed required data into the database.

        Inserts essential records that importers and other components depend on,
        such as source entries for PubMed and medRxiv.
        """
        import psycopg

        conn_params = {
            'host': self.host,
            'port': int(self.port),
            'dbname': self.dbname,
            'user': self.app_user,
            'password': self.app_password,
            'connect_timeout': DB_CONNECTION_TIMEOUT_SECONDS,
        }

        # Required sources for importers
        sources = [
            {
                'name': 'pubmed',
                'url': 'https://pubmed.ncbi.nlm.nih.gov/',
                'is_reputable': True,
                'is_free': True,
            },
            {
                'name': 'medrxiv',
                'url': 'https://www.medrxiv.org/',
                'is_reputable': True,
                'is_free': True,
            },
            {
                'name': 'biorxiv',
                'url': 'https://www.biorxiv.org/',
                'is_reputable': True,
                'is_free': True,
            },
        ]

        with psycopg.connect(**conn_params) as conn:
            with conn.cursor() as cur:
                for source in sources:
                    # Use INSERT ... ON CONFLICT to be idempotent
                    cur.execute("""
                        INSERT INTO public.sources (name, url, is_reputable, is_free)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (name) DO NOTHING
                    """, (source['name'], source['url'], source['is_reputable'], source['is_free']))

            conn.commit()

        logger.info(f"Seeded {len(sources)} source entries")


class DatabaseSetupPage(QWizardPage):
    """
    Page for complete database setup.

    Creates the database, user, extensions, and applies schema.
    """

    def __init__(self, parent: Optional["SetupWizard"] = None):
        """Initialize database setup page."""
        super().__init__(parent)
        self._wizard = parent
        self._worker: Optional[DatabaseSetupWorker] = None
        self._setup_complete = False
        self._has_tables = False
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the setup page UI."""
        scale = get_font_scale()

        self.setTitle("Creating Database")
        self.setSubTitle("Setting up the database, user, and schema...")

        layout = QVBoxLayout(self)
        layout.setSpacing(scale["spacing_large"])

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # Indeterminate
        layout.addWidget(self.progress_bar)

        # Status label
        self.status_label = QLabel("Checking database...")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        # Warning frame (hidden by default)
        self.warning_frame = QFrame()
        self.warning_frame.setObjectName("warningFrame")
        self.warning_frame.setStyleSheet(
            _create_frame_stylesheet(scale, FRAME_WARNING_BG, FRAME_WARNING_BORDER, "warningFrame")
        )
        self.warning_frame.setVisible(False)

        warning_layout = QVBoxLayout(self.warning_frame)
        self.warning_label = QLabel()
        self.warning_label.setWordWrap(True)
        warning_layout.addWidget(self.warning_label)

        layout.addWidget(self.warning_frame)

        # Success frame (hidden by default)
        self.success_frame = QFrame()
        self.success_frame.setObjectName("successFrame")
        self.success_frame.setStyleSheet(
            _create_frame_stylesheet(scale, FRAME_SUCCESS_BG, FRAME_SUCCESS_BORDER, "successFrame")
        )
        self.success_frame.setVisible(False)

        success_layout = QVBoxLayout(self.success_frame)
        self.success_label = QLabel()
        self.success_label.setWordWrap(True)
        success_layout.addWidget(self.success_label)

        layout.addWidget(self.success_frame)

        layout.addStretch()

    def initializePage(self) -> None:
        """Initialize the page when it becomes visible."""
        # Reset state
        self._setup_complete = False
        self._has_tables = False
        self.warning_frame.setVisible(False)
        self.success_frame.setVisible(False)
        self.progress_bar.setRange(0, 0)

        # Get config from wizard
        if self._wizard:
            host = self._wizard.get_config_value("postgres_host", "localhost")
            port = self._wizard.get_config_value("postgres_port", "5432")
            superuser = self._wizard.get_config_value("superuser_name", "")
            superuser_password = self._wizard.get_config_value("superuser_password", "")
            dbname = self._wizard.get_config_value("postgres_db", DEFAULT_DATABASE_NAME)
            app_user = self._wizard.get_config_value("postgres_user", DEFAULT_APP_USER)
            app_password = self._wizard.get_config_value("postgres_password", "")
            pdf_dir = self._wizard.get_config_value(
                "pdf_base_dir", str(Path.home() / "knowledgebase" / "pdf")
            )

            # Start worker with new parameters
            self._worker = DatabaseSetupWorker(
                host=host,
                port=port,
                superuser=superuser,
                superuser_password=superuser_password,
                app_user=app_user,
                app_password=app_password,
                dbname=dbname,
                pdf_dir=pdf_dir,
                parent=self,
            )
            self._worker.progress.connect(self._on_progress)
            self._worker.finished.connect(self._on_finished)
            self._worker.table_check.connect(self._on_table_check)
            self._worker.start()

    def _on_progress(self, message: str) -> None:
        """Handle progress updates."""
        self.status_label.setText(message)

    def _on_table_check(self, has_tables: bool, tables: list) -> None:
        """
        Handle table check result.

        In the new simplified setup flow, existing tables are informational only.
        The setup will proceed regardless (schema migrations handle existing tables).
        """
        self._has_tables = has_tables
        if has_tables:
            logger.info(f"Database has {len(tables)} existing tables")

    def _on_finished(self, success: bool, message: str) -> None:
        """Handle setup completion."""
        self._setup_complete = success

        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100 if success else 0)

        if success:
            self.success_frame.setVisible(True)
            self.success_label.setText(message)
            self.status_label.setText("Setup complete!")
        else:
            self.warning_frame.setVisible(True)
            self.warning_label.setText(message)
            self.status_label.setText("Setup failed")

        self.completeChanged.emit()

    def isComplete(self) -> bool:
        """Check if page is complete."""
        return self._setup_complete

    def validatePage(self) -> bool:
        """Validate the page."""
        return self._setup_complete


# =============================================================================
# Import Options Page
# =============================================================================


class ImportOptionsPage(QWizardPage):
    """
    Page for selecting data import options.

    Allows user to choose between:
    - Full PubMed mirror
    - Full medRxiv mirror
    - Quick test import (latest updates only)
    - Skip import
    """

    def __init__(self, parent: Optional["SetupWizard"] = None):
        """Initialize import options page."""
        super().__init__(parent)
        self._wizard = parent
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the import options page UI."""
        scale = get_font_scale()

        self.setTitle("Data Import Options")
        self.setSubTitle("Choose which data sources to import into your database.")

        layout = QVBoxLayout(self)
        layout.setSpacing(scale["spacing_large"])

        # Import mode selection
        mode_group = QGroupBox("Import Mode")
        mode_layout = QVBoxLayout(mode_group)

        self.mode_button_group = QButtonGroup(self)

        # Skip import option
        self.skip_radio = QRadioButton("Skip Import (configure manually later)")
        self.skip_radio.setChecked(True)
        self.mode_button_group.addButton(self.skip_radio, 0)
        mode_layout.addWidget(self.skip_radio)

        # Quick test option
        self.quick_radio = QRadioButton(
            "Quick Test Import (latest updates from both sources)"
        )
        self.mode_button_group.addButton(self.quick_radio, 1)
        mode_layout.addWidget(self.quick_radio)

        quick_note = QLabel(
            f"    Downloads ~{MEDRXIV_DEFAULT_DAYS} days of medRxiv preprints and "
            f"~{PUBMED_DEFAULT_MAX_RESULTS} PubMed articles"
        )
        quick_note.setStyleSheet(f"color: {COLOR_MUTED}; font-style: italic;")
        mode_layout.addWidget(quick_note)

        # Full medRxiv option
        self.medrxiv_radio = QRadioButton("Full medRxiv Mirror")
        self.mode_button_group.addButton(self.medrxiv_radio, 2)
        mode_layout.addWidget(self.medrxiv_radio)

        medrxiv_note = QLabel("    Downloads all available medRxiv preprints (~500K+)")
        medrxiv_note.setStyleSheet(f"color: {COLOR_MUTED}; font-style: italic;")
        mode_layout.addWidget(medrxiv_note)

        # Full PubMed option
        self.pubmed_radio = QRadioButton("Full PubMed Baseline Mirror")
        self.mode_button_group.addButton(self.pubmed_radio, 3)
        mode_layout.addWidget(self.pubmed_radio)

        pubmed_note = QLabel(
            "    Downloads complete PubMed baseline (~38M articles, ~400GB)"
        )
        pubmed_note.setStyleSheet(f"color: {COLOR_MUTED}; font-style: italic;")
        mode_layout.addWidget(pubmed_note)

        layout.addWidget(mode_group)

        # Optional settings group
        settings_group = QGroupBox("Import Settings")
        settings_layout = QVBoxLayout(settings_group)

        # MedRxiv days
        medrxiv_days_layout = QHBoxLayout()
        medrxiv_days_label = QLabel("medRxiv days to fetch (for quick test):")
        self.medrxiv_days_spin = QSpinBox()
        self.medrxiv_days_spin.setRange(MEDRXIV_MIN_DAYS, MEDRXIV_MAX_DAYS)
        self.medrxiv_days_spin.setValue(MEDRXIV_DEFAULT_DAYS)
        medrxiv_days_layout.addWidget(medrxiv_days_label)
        medrxiv_days_layout.addWidget(self.medrxiv_days_spin)
        medrxiv_days_layout.addStretch()
        settings_layout.addLayout(medrxiv_days_layout)

        # PubMed max results
        pubmed_max_layout = QHBoxLayout()
        pubmed_max_label = QLabel("PubMed max results (for quick test):")
        self.pubmed_max_spin = QSpinBox()
        self.pubmed_max_spin.setRange(PUBMED_MIN_RESULTS, PUBMED_MAX_RESULTS)
        self.pubmed_max_spin.setValue(PUBMED_DEFAULT_MAX_RESULTS)
        pubmed_max_layout.addWidget(pubmed_max_label)
        pubmed_max_layout.addWidget(self.pubmed_max_spin)
        pubmed_max_layout.addStretch()
        settings_layout.addLayout(pubmed_max_layout)

        # Download PDFs checkbox
        self.download_pdfs_check = QCheckBox("Download PDFs (medRxiv only)")
        self.download_pdfs_check.setChecked(False)
        settings_layout.addWidget(self.download_pdfs_check)

        layout.addWidget(settings_group)

        # Warning for large imports
        warning_frame = QFrame()
        warning_frame.setObjectName("importWarningFrame")
        warning_frame.setStyleSheet(
            _create_frame_stylesheet(scale, FRAME_NOTE_BG, FRAME_NOTE_BORDER, "importWarningFrame")
        )

        warning_layout = QVBoxLayout(warning_frame)
        warning_label = QLabel(
            "Warning: Full mirror imports can take many hours to complete "
            "and require significant disk space. For testing purposes, "
            "the 'Quick Test Import' option is recommended."
        )
        warning_label.setWordWrap(True)
        warning_layout.addWidget(warning_label)

        layout.addWidget(warning_frame)

        layout.addStretch()

    def get_import_mode(self) -> int:
        """Get the selected import mode."""
        return self.mode_button_group.checkedId()

    def get_import_settings(self) -> dict:
        """Get the import settings."""
        return {
            "mode": self.get_import_mode(),
            "medrxiv_days": self.medrxiv_days_spin.value(),
            "pubmed_max_results": self.pubmed_max_spin.value(),
            "download_pdfs": self.download_pdfs_check.isChecked(),
        }

    def nextId(self) -> int:
        """Determine next page based on import selection."""
        from .wizard import SetupWizard

        mode = self.get_import_mode()
        if mode == 0:  # Skip import
            return SetupWizard.PAGE_COMPLETE
        return SetupWizard.PAGE_IMPORT_PROGRESS


# =============================================================================
# Import Progress Page
# =============================================================================


class ImportWorker(QThread):
    """Worker thread for data import operations."""

    progress = Signal(str)  # Progress message
    progress_percent = Signal(int)  # Progress percentage
    finished = Signal(bool, str, dict)  # Success, message, stats

    def __init__(
        self,
        import_mode: int,
        settings: dict,
        parent: Optional[object] = None,
    ):
        """Initialize the import worker."""
        super().__init__(parent)
        self.import_mode = import_mode
        self.settings = settings
        self._cancelled = False

    def cancel(self) -> None:
        """Cancel the import operation."""
        self._cancelled = True
        logger.info("Import cancellation requested")

    def is_cancelled(self) -> bool:
        """Check if import has been cancelled."""
        return self._cancelled

    def _progress_callback(self, message: str) -> None:
        """Callback for importer progress messages. Emits signal to GUI."""
        self.progress.emit(message)

    def run(self) -> None:
        """Execute the import operation."""
        try:
            stats = {}

            if self.import_mode == 1:  # Quick test
                self._run_quick_test(stats)
            elif self.import_mode == 2:  # Full medRxiv
                self._run_medrxiv_full(stats)
            elif self.import_mode == 3:  # Full PubMed
                self._run_pubmed_full(stats)

            if self._cancelled:
                self.finished.emit(False, "Import cancelled", stats)
            else:
                self.finished.emit(True, "Import completed successfully!", stats)

        except Exception as e:
            logger.error(f"Import failed: {e}", exc_info=True)
            self.finished.emit(False, f"Import failed: {str(e)}", {})

    def _run_quick_test(self, stats: dict) -> None:
        """Run quick test import."""
        # MedRxiv
        self.progress.emit("Importing medRxiv preprints...")
        self.progress_percent.emit(PROGRESS_MEDRXIV_START)

        try:
            from bmlibrarian.importers import MedRxivImporter

            importer = MedRxivImporter()
            medrxiv_stats = importer.update_database(
                download_pdfs=self.settings.get("download_pdfs", False),
                days_to_fetch=self.settings.get("medrxiv_days", MEDRXIV_DEFAULT_DAYS),
                progress_callback=self._progress_callback,
                cancel_check=self.is_cancelled,
            )
            stats["medrxiv"] = medrxiv_stats
            self.progress.emit(
                f"medRxiv: {medrxiv_stats.get('total_processed', 0)} papers imported"
            )
        except Exception as e:
            logger.error(f"medRxiv import failed: {e}", exc_info=True)
            stats["medrxiv_error"] = str(e)

        if self._cancelled:
            return

        # PubMed
        self.progress.emit("Importing PubMed articles...")
        self.progress_percent.emit(PROGRESS_PUBMED_START)

        try:
            from bmlibrarian.importers import PubMedImporter

            importer = PubMedImporter()
            pubmed_stats = importer.import_by_search(
                query=PUBMED_TEST_QUERY,
                max_results=self.settings.get("pubmed_max_results", PUBMED_DEFAULT_MAX_RESULTS),
                progress_callback=self._progress_callback,
                cancel_check=self.is_cancelled,
            )
            stats["pubmed"] = pubmed_stats
            self.progress.emit(
                f"PubMed: {pubmed_stats.get('imported', 0)} articles imported"
            )
        except Exception as e:
            logger.error(f"PubMed import failed: {e}", exc_info=True)
            stats["pubmed_error"] = str(e)

        self.progress_percent.emit(PROGRESS_COMPLETE)

    def _run_medrxiv_full(self, stats: dict) -> None:
        """Run full medRxiv import."""
        self.progress.emit("Starting full medRxiv import (this may take hours)...")
        self.progress_percent.emit(0)

        try:
            from bmlibrarian.importers import MedRxivImporter

            importer = MedRxivImporter()
            # Use a large days_to_fetch for full historical import
            medrxiv_stats = importer.update_database(
                download_pdfs=self.settings.get("download_pdfs", False),
                days_to_fetch=MEDRXIV_FULL_IMPORT_DAYS,
                progress_callback=self._progress_callback,
                cancel_check=self.is_cancelled,
            )
            stats["medrxiv"] = medrxiv_stats
        except Exception as e:
            logger.error(f"medRxiv full import failed: {e}", exc_info=True)
            stats["medrxiv_error"] = str(e)

        self.progress_percent.emit(PROGRESS_COMPLETE)

    def _run_pubmed_full(self, stats: dict) -> None:
        """Run full PubMed baseline import."""
        self.progress.emit("Starting full PubMed baseline import (this will take many hours)...")
        self.progress_percent.emit(0)

        try:
            from bmlibrarian.importers import PubMedBulkImporter

            importer = PubMedBulkImporter()

            # Download baseline
            self._progress_callback("Downloading PubMed baseline files...")
            importer.download_baseline()

            if self._cancelled:
                self._progress_callback("Import cancelled by user")
                return

            # Import baseline
            self._progress_callback("Importing PubMed baseline files...")
            pubmed_stats = importer.import_files(file_type="baseline")
            stats["pubmed"] = pubmed_stats
            self._progress_callback(f"PubMed baseline import complete: {pubmed_stats}")
        except Exception as e:
            logger.error(f"PubMed full import failed: {e}", exc_info=True)
            stats["pubmed_error"] = str(e)
            self._progress_callback(f"PubMed full import failed: {e}")

        self.progress_percent.emit(PROGRESS_COMPLETE)


class ImportProgressPage(QWizardPage):
    """
    Page showing import progress.

    Displays real-time progress of data import operations.
    """

    def __init__(self, parent: Optional["SetupWizard"] = None):
        """Initialize import progress page."""
        super().__init__(parent)
        self._wizard = parent
        self._worker: Optional[ImportWorker] = None
        self._import_complete = False
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the progress page UI."""
        scale = get_font_scale()

        self.setTitle("Importing Data")
        self.setSubTitle("Please wait while data is being imported...")

        layout = QVBoxLayout(self)
        layout.setSpacing(scale["spacing_large"])

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        # Status label
        self.status_label = QLabel("Preparing import...")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        # Log area
        log_group = QGroupBox("Import Log")
        log_layout = QVBoxLayout(log_group)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMinimumHeight(scale["control_height_xlarge"] * LOG_TEXT_HEIGHT_MULTIPLIER)
        log_layout.addWidget(self.log_text)

        layout.addWidget(log_group)

        # Cancel button
        self.cancel_btn = QPushButton("Cancel Import")
        self.cancel_btn.clicked.connect(self._cancel_import)
        layout.addWidget(self.cancel_btn)

        layout.addStretch()

    def initializePage(self) -> None:
        """Initialize the page when it becomes visible."""
        self._import_complete = False
        self.progress_bar.setValue(0)
        self.log_text.clear()
        self.cancel_btn.setEnabled(True)

        # Get import settings from previous page
        options_page = self.wizard().page(self.wizard().PAGE_IMPORT_OPTIONS)
        if isinstance(options_page, ImportOptionsPage):
            settings = options_page.get_import_settings()
            import_mode = settings["mode"]

            # Start import worker
            self._worker = ImportWorker(import_mode, settings, self)
            self._worker.progress.connect(self._on_progress)
            self._worker.progress_percent.connect(self._on_progress_percent)
            self._worker.finished.connect(self._on_finished)
            self._worker.start()

    def _on_progress(self, message: str) -> None:
        """Handle progress updates."""
        self.status_label.setText(message)
        self.log_text.append(message)

    def _on_progress_percent(self, percent: int) -> None:
        """Handle progress percentage updates."""
        self.progress_bar.setValue(percent)

    def _on_finished(self, success: bool, message: str, stats: dict) -> None:
        """Handle import completion."""
        self._import_complete = True
        self.cancel_btn.setEnabled(False)

        self.status_label.setText(message)
        self.log_text.append(f"\n{message}")

        # Log stats
        if stats:
            self.log_text.append("\n--- Import Statistics ---")
            for key, value in stats.items():
                self.log_text.append(f"{key}: {value}")

        # Store results in wizard
        if self._wizard:
            self._wizard.set_import_result(
                "medrxiv",
                "medrxiv" in stats and "medrxiv_error" not in stats,
                stats.get("medrxiv", {}),
            )
            self._wizard.set_import_result(
                "pubmed",
                "pubmed" in stats and "pubmed_error" not in stats,
                stats.get("pubmed", {}),
            )

        self.completeChanged.emit()

    def _cancel_import(self) -> None:
        """Cancel the import operation."""
        if self._worker and self._worker.isRunning():
            reply = QMessageBox.question(
                self,
                "Cancel Import",
                "Are you sure you want to cancel the import?\n\n"
                "Data imported so far will be kept.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )

            if reply == QMessageBox.StandardButton.Yes:
                self._worker.cancel()
                self.status_label.setText("Cancelling import...")

    def isComplete(self) -> bool:
        """Check if page is complete."""
        return self._import_complete

    def cleanup(self) -> None:
        """
        Clean up resources when wizard is closed.

        Cancels any running import and waits for the thread to finish.
        """
        if self._worker and self._worker.isRunning():
            logger.info("Cleaning up import worker...")
            self._worker.cancel()
            # Wait for thread to finish with a timeout
            if not self._worker.wait(5000):  # 5 second timeout
                logger.warning("Import worker did not finish in time, terminating...")
                self._worker.terminate()
                self._worker.wait()
            logger.info("Import worker cleaned up")


# =============================================================================
# Document Browser Page
# =============================================================================


class DocumentBrowserPage(QWizardPage):
    """
    Page for browsing imported documents to verify import success.

    Displays a list of recently imported documents with title, authors,
    date, and journal. Selecting a document shows its abstract in a
    Markdown-rendered preview panel.
    """

    # Number of documents to display
    DOCUMENTS_PER_PAGE = 20

    def __init__(self, parent: Optional["SetupWizard"] = None):
        """Initialize document browser page."""
        super().__init__(parent)
        self._wizard = parent
        self._documents: List[Dict[str, Any]] = []
        self._current_page = 0
        self._total_documents = 0
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the document browser UI."""
        scale = get_font_scale()

        self.setTitle("Verify Imported Documents")
        self.setSubTitle("Browse recently imported documents to verify the import was successful.")

        layout = QVBoxLayout(self)
        layout.setSpacing(scale["spacing_medium"])

        # Create splitter for list and preview
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left panel: Document list
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)

        # Document count label
        self.count_label = QLabel("Loading documents...")
        left_layout.addWidget(self.count_label)

        # Document list
        self.doc_list = QListWidget()
        self.doc_list.setAlternatingRowColors(True)
        self.doc_list.currentItemChanged.connect(self._on_document_selected)
        left_layout.addWidget(self.doc_list)

        # Pagination controls
        pagination_layout = QHBoxLayout()
        self.prev_btn = QPushButton("← Previous")
        self.prev_btn.clicked.connect(self._prev_page)
        self.prev_btn.setEnabled(False)
        pagination_layout.addWidget(self.prev_btn)

        self.page_label = QLabel("Page 1")
        self.page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pagination_layout.addWidget(self.page_label)

        self.next_btn = QPushButton("Next →")
        self.next_btn.clicked.connect(self._next_page)
        pagination_layout.addWidget(self.next_btn)

        left_layout.addLayout(pagination_layout)

        splitter.addWidget(left_panel)

        # Right panel: Abstract preview
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)

        # Document metadata
        self.metadata_label = QLabel("Select a document to view details")
        self.metadata_label.setWordWrap(True)
        self.metadata_label.setStyleSheet(f"""
            QLabel {{
                background-color: #f5f5f5;
                padding: {scale["padding_medium"]}px;
                border-radius: {scale["radius_small"]}px;
            }}
        """)
        right_layout.addWidget(self.metadata_label)

        # Abstract preview (using QTextBrowser for Markdown rendering)
        abstract_label = QLabel("Abstract:")
        right_layout.addWidget(abstract_label)

        self.abstract_browser = QTextBrowser()
        self.abstract_browser.setOpenExternalLinks(True)
        self.abstract_browser.setPlaceholderText("Select a document to view its abstract")
        right_layout.addWidget(self.abstract_browser)

        splitter.addWidget(right_panel)

        # Set initial splitter sizes (40% list, 60% preview)
        splitter.setSizes([400, 600])

        layout.addWidget(splitter)

    def initializePage(self) -> None:
        """Initialize the page when it becomes visible."""
        self._current_page = 0
        self._load_documents()

    def _load_documents(self) -> None:
        """Load documents from the database."""
        try:
            from bmlibrarian.database import get_db_manager

            db_manager = get_db_manager()
            offset = self._current_page * self.DOCUMENTS_PER_PAGE

            with db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    # Get total count
                    cur.execute("SELECT COUNT(*) FROM document")
                    self._total_documents = cur.fetchone()[0]

                    # Get documents for current page
                    cur.execute("""
                        SELECT id, title, authors, publication_date, publication, abstract
                        FROM document
                        ORDER BY id DESC
                        LIMIT %s OFFSET %s
                    """, (self.DOCUMENTS_PER_PAGE, offset))

                    self._documents = []
                    for row in cur.fetchall():
                        self._documents.append({
                            'id': row[0],
                            'title': row[1] or 'Untitled',
                            'authors': row[2] or [],
                            'date': row[3],
                            'journal': row[4] or 'Unknown',
                            'abstract': row[5] or 'No abstract available',
                        })

            self._update_document_list()
            self._update_pagination()

        except Exception as e:
            logger.error(f"Error loading documents: {e}")
            self.count_label.setText(f"Error loading documents: {e}")
            self._documents = []

    def _update_document_list(self) -> None:
        """Update the document list widget."""
        self.doc_list.clear()

        if not self._documents:
            self.count_label.setText("No documents found")
            return

        start = self._current_page * self.DOCUMENTS_PER_PAGE + 1
        end = min(start + len(self._documents) - 1, self._total_documents)
        self.count_label.setText(f"Showing {start}-{end} of {self._total_documents} documents")

        for doc in self._documents:
            # Format authors (first 3, then "et al.")
            authors = doc['authors']
            if isinstance(authors, list):
                if len(authors) > 3:
                    author_str = ', '.join(authors[:3]) + ' et al.'
                else:
                    author_str = ', '.join(authors) if authors else 'Unknown'
            else:
                author_str = str(authors) if authors else 'Unknown'

            # Format date
            date_str = str(doc['date'])[:10] if doc['date'] else 'No date'

            # Create list item text
            title = doc['title'][:80] + '...' if len(doc['title']) > 80 else doc['title']
            item_text = f"{title}\n{author_str} • {date_str} • {doc['journal']}"

            item = QListWidgetItem(item_text)
            item.setData(Qt.ItemDataRole.UserRole, doc)
            self.doc_list.addItem(item)

    def _update_pagination(self) -> None:
        """Update pagination controls."""
        total_pages = max(1, (self._total_documents + self.DOCUMENTS_PER_PAGE - 1) // self.DOCUMENTS_PER_PAGE)
        self.page_label.setText(f"Page {self._current_page + 1} of {total_pages}")
        self.prev_btn.setEnabled(self._current_page > 0)
        self.next_btn.setEnabled((self._current_page + 1) * self.DOCUMENTS_PER_PAGE < self._total_documents)

    def _prev_page(self) -> None:
        """Go to previous page."""
        if self._current_page > 0:
            self._current_page -= 1
            self._load_documents()

    def _next_page(self) -> None:
        """Go to next page."""
        if (self._current_page + 1) * self.DOCUMENTS_PER_PAGE < self._total_documents:
            self._current_page += 1
            self._load_documents()

    def _on_document_selected(self, current: QListWidgetItem, previous: QListWidgetItem) -> None:
        """Handle document selection."""
        if current is None:
            return

        doc = current.data(Qt.ItemDataRole.UserRole)
        if not doc:
            return

        # Update metadata display
        authors = doc['authors']
        if isinstance(authors, list):
            author_str = ', '.join(authors) if authors else 'Unknown'
        else:
            author_str = str(authors) if authors else 'Unknown'

        date_str = str(doc['date'])[:10] if doc['date'] else 'No date'

        metadata_html = f"""
        <h3>{doc['title']}</h3>
        <p><b>Authors:</b> {author_str}</p>
        <p><b>Journal:</b> {doc['journal']}</p>
        <p><b>Date:</b> {date_str}</p>
        <p><b>ID:</b> {doc['id']}</p>
        """
        self.metadata_label.setText(metadata_html)

        # Update abstract display with Markdown rendering
        abstract = doc['abstract']

        # Convert Markdown-style formatting to HTML
        # Bold: **text** -> <b>text</b>
        import re
        abstract_html = re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', abstract)
        # Italic: *text* -> <i>text</i>
        abstract_html = re.sub(r'\*([^*]+)\*', r'<i>\1</i>', abstract_html)
        # Superscript: ^text^ -> <sup>text</sup>
        abstract_html = re.sub(r'\^([^^]+)\^', r'<sup>\1</sup>', abstract_html)
        # Subscript: ~text~ -> <sub>text</sub>
        abstract_html = re.sub(r'~([^~]+)~', r'<sub>\1</sub>', abstract_html)
        # Paragraph breaks
        abstract_html = abstract_html.replace('\n\n', '</p><p>')
        abstract_html = f"<p>{abstract_html}</p>"

        self.abstract_browser.setHtml(abstract_html)


# =============================================================================
# Complete Page
# =============================================================================


class CompletePage(QWizardPage):
    """
    Final page showing setup completion summary.

    Displays summary of what was configured and next steps.
    """

    def __init__(self, parent: Optional["SetupWizard"] = None):
        """Initialize complete page."""
        super().__init__(parent)
        self._wizard = parent
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the complete page UI."""
        scale = get_font_scale()

        self.setTitle("Setup Complete!")
        self.setSubTitle("BMLibrarian has been configured successfully.")

        layout = QVBoxLayout(self)
        layout.setSpacing(scale["spacing_large"])

        # Summary
        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

        # Next steps
        next_steps_group = QGroupBox("Next Steps")
        next_steps_layout = QVBoxLayout(next_steps_group)

        next_steps_text = QLabel(
            "You can now:\n\n"
            "  1. Run the BMLibrarian CLI:\n"
            "     uv run python bmlibrarian_cli.py\n\n"
            "  2. Run the Research GUI:\n"
            "     uv run python bmlibrarian_research_gui.py\n\n"
            "  3. Configure additional settings:\n"
            "     uv run python bmlibrarian_config_gui.py\n\n"
            "  4. Import more data:\n"
            "     uv run python medrxiv_import_cli.py update\n"
            "     uv run python pubmed_import_cli.py search \"your query\""
        )
        next_steps_text.setWordWrap(True)
        next_steps_layout.addWidget(next_steps_text)

        layout.addWidget(next_steps_group)

        layout.addStretch()

    def initializePage(self) -> None:
        """Initialize the page when it becomes visible."""
        if self._wizard:
            config = self._wizard.get_config()
            import_results = self._wizard.get_import_results()

            summary = (
                f"Configuration Summary:\n\n"
                f"  Database: {config.get('postgres_db', 'N/A')}@"
                f"{config.get('postgres_host', 'localhost')}:"
                f"{config.get('postgres_port', '5432')}\n"
                f"  User: {config.get('postgres_user', 'N/A')}\n"
                f"  PDF Directory: {config.get('pdf_base_dir', 'N/A')}\n\n"
            )

            # Add import results
            if import_results.get("medrxiv_success"):
                stats = import_results.get("medrxiv_stats", {})
                summary += f"  medRxiv: {stats.get('total_processed', 0)} papers imported\n"
            elif import_results.get("medrxiv_stats"):
                summary += "  medRxiv: Import skipped or failed\n"

            if import_results.get("pubmed_success"):
                stats = import_results.get("pubmed_stats", {})
                summary += f"  PubMed: {stats.get('imported', 0)} articles imported\n"
            elif import_results.get("pubmed_stats"):
                summary += "  PubMed: Import skipped or failed\n"

            self.summary_label.setText(summary)
