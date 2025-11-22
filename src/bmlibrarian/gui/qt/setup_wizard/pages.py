"""
Wizard pages for BMLibrarian Setup Wizard.

Contains all QWizardPage implementations for the setup process.
"""

import logging
import os
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from PySide6.QtWidgets import (
    QWizardPage,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QTextEdit,
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
    return gen.custom(f"""
        QFrame#{object_name} {{
            background-color: {bg_color};
            border: 1px solid {border_color};
            border-radius: {{radius_small}}px;
            padding: {{padding_medium}}px;
        }}
    """)


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
    Page displaying PostgreSQL setup instructions.

    Shows commands for creating database with required extensions.
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
            "Please ensure your PostgreSQL database is configured with the required extensions."
        )

        layout = QVBoxLayout(self)
        layout.setSpacing(scale["spacing_large"])

        # Instructions
        instructions = QLabel(
            "BMLibrarian requires PostgreSQL with the following extensions:\n\n"
            "  - pgvector: For semantic similarity search\n"
            "  - plpython3u: For embedding generation within the database\n"
            "  - pg_trgm: For trigram-based text search\n\n"
            "If you haven't already, create a new database with these extensions:"
        )
        instructions.setWordWrap(True)
        layout.addWidget(instructions)

        # SQL Commands box
        sql_group = QGroupBox("SQL Commands")
        sql_layout = QVBoxLayout(sql_group)

        sql_commands = """-- Connect to PostgreSQL as superuser (e.g., postgres)
-- Then run these commands:

-- Create the database
CREATE DATABASE bmlibrarian;

-- Connect to the new database
\\c bmlibrarian

-- Install required extensions
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS plpython3u;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Grant privileges to your user (replace 'your_user')
GRANT ALL PRIVILEGES ON DATABASE bmlibrarian TO your_user;"""

        sql_text = QTextEdit()
        sql_text.setPlainText(sql_commands)
        sql_text.setReadOnly(True)
        sql_text.setFont(QFont("Monospace", scale["font_small"]))
        sql_text.setMinimumHeight(scale["control_height_xlarge"] * SQL_TEXT_HEIGHT_MULTIPLIER)
        sql_layout.addWidget(sql_text)

        # Copy button
        copy_btn = QPushButton("Copy to Clipboard")
        copy_btn.clicked.connect(lambda: self._copy_to_clipboard(sql_commands))
        sql_layout.addWidget(copy_btn)

        layout.addWidget(sql_group)

        # Additional notes
        notes = QLabel(
            "Important Notes:\n\n"
            "  - You need superuser privileges to create the plpython3u extension\n"
            "  - pgvector may require separate installation depending on your OS\n"
            "  - On Ubuntu/Debian: sudo apt install postgresql-16-pgvector\n"
            "  - On macOS with Homebrew: brew install pgvector"
        )
        notes.setWordWrap(True)
        layout.addWidget(notes)

        layout.addStretch()

    def _copy_to_clipboard(self, text: str) -> None:
        """Copy text to clipboard."""
        from PySide6.QtWidgets import QApplication

        clipboard = QApplication.clipboard()
        clipboard.setText(text)

        # Show brief notification
        QMessageBox.information(
            self,
            "Copied",
            "SQL commands copied to clipboard.",
            QMessageBox.StandardButton.Ok,
        )


# =============================================================================
# Database Configuration Page
# =============================================================================


class DatabaseConfigPage(QWizardPage):
    """
    Page for entering PostgreSQL connection details.

    Collects database credentials and validates connection.
    """

    def __init__(self, parent: Optional["SetupWizard"] = None):
        """Initialize database configuration page."""
        super().__init__(parent)
        self._wizard = parent
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the configuration page UI."""
        scale = get_font_scale()

        self.setTitle("Database Configuration")
        self.setSubTitle("Enter your PostgreSQL connection details.")

        layout = QVBoxLayout(self)
        layout.setSpacing(scale["spacing_large"])

        # Connection settings group
        conn_group = QGroupBox("Connection Settings")
        conn_layout = QVBoxLayout(conn_group)
        conn_layout.setSpacing(scale["spacing_medium"])

        # Host
        host_layout = QHBoxLayout()
        host_label = QLabel("Host:")
        host_label.setMinimumWidth(scale["control_width_small"])
        self.host_edit = QLineEdit(DEFAULT_POSTGRES_HOST)
        self.host_edit.setPlaceholderText(DEFAULT_POSTGRES_HOST)
        host_layout.addWidget(host_label)
        host_layout.addWidget(self.host_edit)
        conn_layout.addLayout(host_layout)

        # Port (with integer validation)
        port_layout = QHBoxLayout()
        port_label = QLabel("Port:")
        port_label.setMinimumWidth(scale["control_width_small"])
        self.port_edit = QLineEdit(DEFAULT_POSTGRES_PORT)
        self.port_edit.setPlaceholderText(DEFAULT_POSTGRES_PORT)
        self.port_edit.setValidator(QIntValidator(1, 65535))  # Valid port range
        port_layout.addWidget(port_label)
        port_layout.addWidget(self.port_edit)
        conn_layout.addLayout(port_layout)

        # Database name
        db_layout = QHBoxLayout()
        db_label = QLabel("Database:")
        db_label.setMinimumWidth(scale["control_width_small"])
        self.db_edit = QLineEdit()
        self.db_edit.setPlaceholderText("bmlibrarian")
        db_layout.addWidget(db_label)
        db_layout.addWidget(self.db_edit)
        conn_layout.addLayout(db_layout)

        # Username
        user_layout = QHBoxLayout()
        user_label = QLabel("Username:")
        user_label.setMinimumWidth(scale["control_width_small"])
        self.user_edit = QLineEdit()
        self.user_edit.setPlaceholderText("your_username")
        user_layout.addWidget(user_label)
        user_layout.addWidget(self.user_edit)
        conn_layout.addLayout(user_layout)

        # Password
        pass_layout = QHBoxLayout()
        pass_label = QLabel("Password:")
        pass_label.setMinimumWidth(scale["control_width_small"])
        self.pass_edit = QLineEdit()
        self.pass_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.pass_edit.setPlaceholderText("your_password")
        pass_layout.addWidget(pass_label)
        pass_layout.addWidget(self.pass_edit)
        conn_layout.addLayout(pass_layout)

        layout.addWidget(conn_group)

        # Test connection button
        test_btn = QPushButton("Test Connection")
        test_btn.clicked.connect(self._test_connection)
        layout.addWidget(test_btn)

        # Status label
        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        layout.addStretch()

        # Register fields for wizard
        self.registerField("postgres_host*", self.host_edit)
        self.registerField("postgres_port*", self.port_edit)
        self.registerField("postgres_db*", self.db_edit)
        self.registerField("postgres_user*", self.user_edit)
        self.registerField("postgres_password*", self.pass_edit)

    def _test_connection(self) -> None:
        """Test the database connection."""
        host = self.host_edit.text().strip()
        port = self.port_edit.text().strip()
        dbname = self.db_edit.text().strip()
        user = self.user_edit.text().strip()
        password = self.pass_edit.text()

        if not all([host, port, dbname, user, password]):
            self.status_label.setText(
                f'<span style="color: {COLOR_ERROR};">Please fill in all fields.</span>'
            )
            return

        self.status_label.setText("Testing connection...")

        try:
            import psycopg

            # NOTE: Direct psycopg usage is necessary here during bootstrapping
            # before DatabaseManager is available. This is an exception to Golden
            # Rule #5 ("All postgres database communication happens through the
            # database manager") because we need to validate credentials and check
            # for required extensions BEFORE the database is set up.
            #
            # Using parameterized connection (dict approach) to safely handle
            # passwords with special characters and prevent injection.
            conn_params = {
                'host': host,
                'port': int(port),
                'dbname': dbname,
                'user': user,
                'password': password,
                'connect_timeout': DB_CONNECTION_TIMEOUT_SECONDS,
            }

            with psycopg.connect(**conn_params) as conn:
                with conn.cursor() as cur:
                    # Test basic connectivity
                    cur.execute("SELECT version()")
                    version = cur.fetchone()[0]

                    # Check for required extensions
                    ext_placeholders = ", ".join([f"'{ext}'" for ext in REQUIRED_EXTENSIONS])
                    cur.execute(
                        f"SELECT extname FROM pg_extension WHERE extname IN ({ext_placeholders})"
                    )
                    extensions = [row[0] for row in cur.fetchall()]

            missing = [ext for ext in REQUIRED_EXTENSIONS if ext not in extensions]

            if missing:
                self.status_label.setText(
                    f'<span style="color: {COLOR_WARNING};">Connection successful, but missing extensions: '
                    f'{", ".join(missing)}</span>'
                )
            else:
                self.status_label.setText(
                    f'<span style="color: {COLOR_SUCCESS};">Connection successful! '
                    f"All required extensions present.</span>"
                )

        except Exception as e:
            logger.error(f"Database connection test failed: {e}")
            self.status_label.setText(
                f'<span style="color: {COLOR_ERROR};">Connection failed: {str(e)}</span>'
            )

    def validatePage(self) -> bool:
        """Validate the page before proceeding."""
        # Store values in wizard config
        if self._wizard:
            self._wizard.set_config_value("postgres_host", self.host_edit.text().strip())
            self._wizard.set_config_value("postgres_port", self.port_edit.text().strip())
            self._wizard.set_config_value("postgres_db", self.db_edit.text().strip())
            self._wizard.set_config_value("postgres_user", self.user_edit.text().strip())
            self._wizard.set_config_value("postgres_password", self.pass_edit.text())

        return True


# =============================================================================
# Database Setup Page
# =============================================================================


class DatabaseSetupWorker(QThread):
    """
    Worker thread for database setup operations.

    Performs:
    1. Check if database has existing tables
    2. Create .env file
    3. Apply database schema
    """

    progress = Signal(str)  # Progress message
    finished = Signal(bool, str)  # Success, message
    table_check = Signal(bool, list)  # Has tables, table list

    def __init__(
        self,
        host: str,
        port: str,
        dbname: str,
        user: str,
        password: str,
        pdf_dir: str,
        parent: Optional[object] = None,
    ):
        """Initialize the worker."""
        super().__init__(parent)
        self.host = host
        self.port = port
        self.dbname = dbname
        self.user = user
        self.password = password
        self.pdf_dir = pdf_dir
        self._check_only = False
        self._skip_schema = False

    def set_check_only(self, check_only: bool) -> None:
        """Set whether to only check for tables."""
        self._check_only = check_only

    def set_skip_schema(self, skip: bool) -> None:
        """Set whether to skip schema setup."""
        self._skip_schema = skip

    def run(self) -> None:
        """Execute database setup."""
        try:
            import psycopg

            # NOTE: Direct psycopg usage is necessary here during bootstrapping
            # before DatabaseManager is available. This is an exception to Golden
            # Rule #5 ("All postgres database communication happens through the
            # database manager") because we need to check for existing tables
            # BEFORE the database schema is applied.
            #
            # Using parameterized connection (dict approach) to safely handle
            # passwords with special characters and prevent injection.
            conn_params = {
                'host': self.host,
                'port': int(self.port),
                'dbname': self.dbname,
                'user': self.user,
                'password': self.password,
                'connect_timeout': DB_CONNECTION_TIMEOUT_SECONDS,
            }

            self.progress.emit("Connecting to database...")

            with psycopg.connect(**conn_params) as conn:
                with conn.cursor() as cur:
                    # Check for existing tables
                    self.progress.emit("Checking for existing tables...")
                    cur.execute(
                        """
                        SELECT table_name FROM information_schema.tables
                        WHERE table_schema = 'public'
                        AND table_type = 'BASE TABLE'
                    """
                    )
                    tables = [row[0] for row in cur.fetchall()]

                    self.table_check.emit(len(tables) > 0, tables)

                    if self._check_only:
                        self.finished.emit(True, "Table check complete")
                        return

                    if tables:
                        self.finished.emit(
                            False,
                            f"Database already contains {len(tables)} tables. "
                            "Please use an empty database.",
                        )
                        return

            if self._skip_schema:
                self.finished.emit(True, "Setup complete (schema skipped)")
                return

            # Create .env file
            self.progress.emit("Creating .env file...")
            self._create_env_file()

            # Apply schema
            self.progress.emit("Applying database schema...")
            self._apply_schema()

            self.finished.emit(True, "Database setup completed successfully!")

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

# PostgreSQL Connection
POSTGRES_HOST={self.host}
POSTGRES_PORT={self.port}
POSTGRES_DB={self.dbname}
POSTGRES_USER={self.user}
POSTGRES_PASSWORD={self.password}

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
        os.environ["POSTGRES_USER"] = self.user
        os.environ["POSTGRES_PASSWORD"] = self.password
        os.environ["PDF_BASE_DIR"] = self.pdf_dir

    def _apply_schema(self) -> None:
        """Apply the database schema."""
        from bmlibrarian.migrations import MigrationManager

        manager = MigrationManager(
            host=self.host,
            port=self.port,
            user=self.user,
            password=self.password,
            database=self.dbname,
        )

        # Get paths using robust project root detection
        project_root = find_project_root()
        baseline_path = project_root / "baseline_schema.sql"
        migrations_dir = project_root / "migrations"

        if baseline_path.exists():
            self.progress.emit("Initializing baseline schema...")
            manager.initialize_database(baseline_path)

        if migrations_dir.exists():
            self.progress.emit("Applying migrations...")
            manager.apply_pending_migrations(migrations_dir, silent=True)


class DatabaseSetupPage(QWizardPage):
    """
    Page for database schema setup.

    Checks for existing tables and applies schema if database is empty.
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

        self.setTitle("Database Schema Setup")
        self.setSubTitle("Setting up the database schema...")

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
            dbname = self._wizard.get_config_value("postgres_db", "")
            user = self._wizard.get_config_value("postgres_user", "")
            password = self._wizard.get_config_value("postgres_password", "")
            pdf_dir = self._wizard.get_config_value(
                "pdf_base_dir", str(Path.home() / "knowledgebase" / "pdf")
            )

            # Start worker
            self._worker = DatabaseSetupWorker(
                host, port, dbname, user, password, pdf_dir, self
            )
            self._worker.progress.connect(self._on_progress)
            self._worker.finished.connect(self._on_finished)
            self._worker.table_check.connect(self._on_table_check)
            self._worker.start()

    def _on_progress(self, message: str) -> None:
        """Handle progress updates."""
        self.status_label.setText(message)

    def _on_table_check(self, has_tables: bool, tables: list) -> None:
        """Handle table check result."""
        self._has_tables = has_tables

        if has_tables:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(100)

            self.warning_frame.setVisible(True)
            displayed_tables = tables[:TABLE_DISPLAY_LIMIT]
            self.warning_label.setText(
                f"The database already contains {len(tables)} table(s):\n\n"
                f"{', '.join(displayed_tables)}"
                f"{'...' if len(tables) > TABLE_DISPLAY_LIMIT else ''}\n\n"
                "Please go back and specify a different (empty) database name, "
                "or drop the existing tables before proceeding."
            )
            self.status_label.setText("Database is not empty")

    def _on_finished(self, success: bool, message: str) -> None:
        """Handle setup completion."""
        self._setup_complete = success

        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100 if success else 0)

        if success and not self._has_tables:
            self.success_frame.setVisible(True)
            self.success_label.setText(message)
            self.status_label.setText("Setup complete!")
        elif not success and not self._has_tables:
            self.warning_frame.setVisible(True)
            self.warning_label.setText(message)
            self.status_label.setText("Setup failed")

        self.completeChanged.emit()

    def isComplete(self) -> bool:
        """Check if page is complete."""
        return self._setup_complete and not self._has_tables

    def validatePage(self) -> bool:
        """Validate the page."""
        if self._has_tables:
            QMessageBox.warning(
                self,
                "Database Not Empty",
                "The database contains existing tables.\n\n"
                "Please go back and specify a different database name.",
            )
            return False

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
            self.progress.emit("Downloading PubMed baseline files...")
            importer.download_baseline()

            if self._cancelled:
                return

            # Import baseline
            self.progress.emit("Importing PubMed baseline files...")
            pubmed_stats = importer.import_files(file_type="baseline")
            stats["pubmed"] = pubmed_stats
        except Exception as e:
            logger.error(f"PubMed full import failed: {e}", exc_info=True)
            stats["pubmed_error"] = str(e)

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
