"""Database migration system for bmlibrarian."""

import hashlib
import logging
import os
import re
import sys
from pathlib import Path
from typing import List, Tuple, Optional

import psycopg

logger = logging.getLogger(__name__)


class MigrationManager:
    """Manages database migrations for bmlibrarian."""

    def __init__(self, host: str, port: str, user: str, password: str, database: str):
        """Initialize the migration manager with database connection parameters."""
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.database = database
        self._conn_params = {
            "host": host,
            "port": port,
            "user": user,
            "password": password
        }

    @classmethod
    def from_env(cls) -> Optional['MigrationManager']:
        """Create MigrationManager from environment variables.

        Returns:
            MigrationManager instance or None if credentials missing
        """
        try:
            from dotenv import load_dotenv
            # Check ~/.bmlibrarian/.env first (primary user configuration location),
            # then fall back to .env in current directory (for development convenience)
            user_env_path = Path.home() / ".bmlibrarian" / ".env"
            if user_env_path.exists():
                load_dotenv(user_env_path)
            else:
                load_dotenv()

            user = os.getenv("POSTGRES_USER")
            password = os.getenv("POSTGRES_PASSWORD")

            if not user or not password:
                logger.warning("Missing POSTGRES_USER or POSTGRES_PASSWORD in environment")
                return None

            return cls(
                host=os.getenv("POSTGRES_HOST", "localhost"),
                port=os.getenv("POSTGRES_PORT", "5432"),
                user=user,
                password=password,
                database=os.getenv("POSTGRES_DB", "knowledgebase")
            )
        except Exception as e:
            logger.warning(f"Could not create MigrationManager from environment: {e}")
            return None

    def _get_connection(self, database: str = None) -> psycopg.Connection:
        """Get a database connection."""
        params = self._conn_params.copy()
        if database:
            params["dbname"] = database
        return psycopg.connect(**params)
    
    def _database_exists(self, database_name: str) -> bool:
        """Check if a database exists."""
        with self._get_connection("postgres") as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM pg_database WHERE datname = %s",
                    (database_name,)
                )
                return cur.fetchone() is not None
    
    def _create_database(self, database_name: str):
        """Create a new database."""
        with self._get_connection("postgres") as conn:
            conn.autocommit = True
            with conn.cursor() as cur:
                # Use identifier to safely quote the database name
                cur.execute(psycopg.sql.SQL("CREATE DATABASE {}").format(
                    psycopg.sql.Identifier(database_name)
                ))
    
    def _create_migrations_table(self):
        """Create the migrations tracking table."""
        with self._get_connection(self.database) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS bmlibrarian_migrations (
                        id SERIAL PRIMARY KEY,
                        filename VARCHAR(255) NOT NULL UNIQUE,
                        checksum VARCHAR(64) NOT NULL,
                        applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                conn.commit()
    
    def _get_applied_migrations(self) -> List[Tuple[str, str]]:
        """Get list of applied migrations (filename, checksum)."""
        with self._get_connection(self.database) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT filename, checksum FROM bmlibrarian_migrations ORDER BY filename"
                )
                return cur.fetchall()
    
    def _calculate_checksum(self, content: str) -> str:
        """Calculate SHA-256 checksum of migration content."""
        return hashlib.sha256(content.encode('utf-8')).hexdigest()
    
    def _apply_sql_file(self, sql_file_path: Path):
        """Apply a SQL file to the database."""
        with open(sql_file_path, 'r', encoding='utf-8') as f:
            sql_content = f.read()
        
        with self._get_connection(self.database) as conn:
            with conn.cursor() as cur:
                # Execute the SQL content
                cur.execute(sql_content)
                conn.commit()
    
    def _record_migration(self, filename: str, checksum: str):
        """Record a migration as applied."""
        with self._get_connection(self.database) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO bmlibrarian_migrations (filename, checksum) VALUES (%s, %s)",
                    (filename, checksum)
                )
                conn.commit()
    
    def initialize_database(self, baseline_schema_path: Path):
        """Initialize database with baseline schema."""
        baseline_schema_path = Path(baseline_schema_path)
        
        if not baseline_schema_path.exists():
            raise FileNotFoundError(f"Baseline schema file not found: {baseline_schema_path}")
        
        print(f"Checking if database '{self.database}' exists...")
        
        # Create database if it doesn't exist
        if not self._database_exists(self.database):
            print(f"Creating database '{self.database}'...")
            self._create_database(self.database)
        else:
            print(f"Database '{self.database}' already exists.")
        
        # Create migrations table
        print("Creating migrations tracking table...")
        self._create_migrations_table()
        
        # Check if baseline has already been applied
        applied_migrations = self._get_applied_migrations()
        baseline_filename = baseline_schema_path.name
        
        for filename, _ in applied_migrations:
            if filename == baseline_filename:
                print("Baseline schema has already been applied.")
                return
        
        # Apply baseline schema
        print("Applying baseline schema...")
        self._apply_sql_file(baseline_schema_path)
        
        # Record baseline as applied
        with open(baseline_schema_path, 'r', encoding='utf-8') as f:
            content = f.read()
        checksum = self._calculate_checksum(content)
        self._record_migration(baseline_filename, checksum)
        
        print("Baseline schema applied successfully!")
    
    def apply_pending_migrations(self, migrations_dir: Path, silent: bool = False) -> int:
        """Apply all pending migrations from the migrations directory.

        Args:
            migrations_dir: Path to migrations directory
            silent: If True, use logging instead of print statements

        Returns:
            Number of migrations applied
        """
        migrations_dir = Path(migrations_dir)

        if not migrations_dir.exists():
            msg = f"Migrations directory does not exist: {migrations_dir}"
            if silent:
                logger.debug(msg)
            else:
                print(msg)
            return 0

        # Ensure migrations table exists
        try:
            self._create_migrations_table()
        except Exception as e:
            msg = f"Could not create migrations table: {e}"
            if silent:
                logger.warning(msg)
            else:
                print(f"Warning: {msg}")
            return 0

        # Get applied migrations
        try:
            applied_migrations = {filename for filename, _ in self._get_applied_migrations()}
        except Exception as e:
            msg = f"Could not get applied migrations: {e}"
            if silent:
                logger.warning(msg)
            else:
                print(f"Warning: {msg}")
            return 0

        # Find migration files (should be .sql files with numeric prefix)
        migration_files = []
        for file_path in migrations_dir.glob("*.sql"):
            if re.match(r'^\d+_.*\.sql$', file_path.name):
                migration_files.append(file_path)

        # Sort by filename (which should start with numbers for ordering)
        migration_files.sort(key=lambda x: x.name)

        # Apply pending migrations
        applied_count = 0
        for migration_file in migration_files:
            if migration_file.name not in applied_migrations:
                msg = f"Applying migration: {migration_file.name}"
                if silent:
                    logger.info(msg)
                else:
                    print(msg)

                # Read and validate migration
                with open(migration_file, 'r', encoding='utf-8') as f:
                    content = f.read()

                checksum = self._calculate_checksum(content)

                try:
                    # Apply migration
                    self._apply_sql_file(migration_file)

                    # Record as applied
                    self._record_migration(migration_file.name, checksum)

                    applied_count += 1
                    msg = f"✓ Applied: {migration_file.name}"
                    if silent:
                        logger.info(msg)
                    else:
                        print(msg)

                except Exception as e:
                    msg = f"✗ Failed to apply {migration_file.name}: {e}"
                    if silent:
                        logger.error(msg)
                    else:
                        print(msg)
                    # Don't exit in silent mode, just log error
                    if not silent:
                        sys.exit(1)

        return applied_count