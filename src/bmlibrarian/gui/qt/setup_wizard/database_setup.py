"""
Database setup page and worker for the Setup Wizard.

Contains the worker thread and page for creating the database,
extensions, and applying the schema.
"""

import logging
import os
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from PySide6.QtWidgets import (
    QWizardPage,
    QVBoxLayout,
    QLabel,
    QProgressBar,
    QFrame,
)
from PySide6.QtCore import Signal, QThread

from ..resources.styles.dpi_scale import get_font_scale
from .utils import (
    find_project_root,
    create_frame_stylesheet,
    ENV_FILE_PERMISSIONS,
    DEFAULT_DATABASE_NAME,
    DEFAULT_APP_USER,
)
from .constants import (
    DB_CONNECTION_TIMEOUT_SECONDS,
    REQUIRED_EXTENSIONS,
    FRAME_WARNING_BG,
    FRAME_WARNING_BORDER,
    FRAME_SUCCESS_BG,
    FRAME_SUCCESS_BORDER,
)

if TYPE_CHECKING:
    from .wizard import SetupWizard

logger = logging.getLogger(__name__)


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
                        self.progress.emit(f"Creating user '{self.app_user}'...")
                        cur.execute(
                            psycopg.sql.SQL("CREATE USER {} WITH PASSWORD {}").format(
                                psycopg.sql.Identifier(self.app_user),
                                psycopg.sql.Literal(self.app_password)
                            )
                        )
                        logger.info(f"Created user '{self.app_user}'")
                    else:
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

        If BMLIBRARIAN_ENV_FILE is set (via --env argument), writes ONLY to that
        file and skips the default locations. This allows running the installer
        against a custom environment without affecting the default configuration.

        Otherwise, creates .env files in two locations:
        1. ~/.bmlibrarian/.env (PRIMARY - user configuration directory)
        2. <project_root>/.env (for development convenience)

        All files are created with restrictive permissions (0o600) to protect
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

        # Check if a custom env file was specified via --env argument
        custom_env_file = os.environ.get('BMLIBRARIAN_ENV_FILE')
        if custom_env_file:
            # Write ONLY to the custom env file, skip default locations
            custom_env_path = Path(custom_env_file)
            custom_env_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            custom_env_path.write_text(env_content)
            custom_env_path.chmod(ENV_FILE_PERMISSIONS)
            logger.info(
                f"Created custom .env file at {custom_env_path} (mode 0o600) - "
                "skipping default locations"
            )
        else:
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
                logger.info(
                    f"Created project .env file at {project_env_path} (mode 0o600)"
                )
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
        logger.info(
            f"Transferred ownership of {len(tables)} tables and "
            f"{len(sequences)} sequences to '{self.app_user}'"
        )

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
            {
                'name': 'other',
                'url': None,
                'is_reputable': False,
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
            create_frame_stylesheet(scale, FRAME_WARNING_BG, FRAME_WARNING_BORDER, "warningFrame")
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
            create_frame_stylesheet(scale, FRAME_SUCCESS_BG, FRAME_SUCCESS_BORDER, "successFrame")
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
