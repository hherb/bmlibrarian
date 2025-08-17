"""Application startup utilities for bmlibrarian."""

import os
from pathlib import Path

from .migrations import MigrationManager


def initialize_app():
    """Initialize the bmlibrarian application and apply any pending migrations."""
    # Get database configuration from environment variables
    db_config = {
        "host": os.getenv("POSTGRES_HOST", "localhost"),
        "port": os.getenv("POSTGRES_PORT", "5432"),
        "user": os.getenv("POSTGRES_USER"),
        "password": os.getenv("POSTGRES_PASSWORD"),
        "database": os.getenv("POSTGRES_DB", "bmlibrarian_dev")
    }
    
    # Check if required environment variables are set
    if not db_config["user"] or not db_config["password"]:
        raise ValueError(
            "Database credentials not configured. Please set POSTGRES_USER and POSTGRES_PASSWORD environment variables."
        )
    
    # Create migration manager
    migration_manager = MigrationManager(**db_config)
    
    # Apply pending migrations
    migrations_dir = Path.home() / ".bmlibrarian" / "migrations"
    try:
        applied_count = migration_manager.apply_pending_migrations(migrations_dir)
        if applied_count > 0:
            print(f"Applied {applied_count} pending migration(s).")
    except Exception as e:
        print(f"Warning: Failed to apply migrations: {e}")
        print("The application may not function correctly.")


def get_database_connection():
    """Get a database connection using environment configuration."""
    db_config = {
        "host": os.getenv("POSTGRES_HOST", "localhost"),
        "port": os.getenv("POSTGRES_PORT", "5432"),
        "user": os.getenv("POSTGRES_USER"),
        "password": os.getenv("POSTGRES_PASSWORD"),
        "database": os.getenv("POSTGRES_DB", "bmlibrarian_dev")
    }
    
    if not db_config["user"] or not db_config["password"]:
        raise ValueError(
            "Database credentials not configured. Please set POSTGRES_USER and POSTGRES_PASSWORD environment variables."
        )
    
    import psycopg
    return psycopg.connect(**{k: v for k, v in db_config.items() if k != "database"}, dbname=db_config["database"])