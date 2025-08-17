"""Pytest configuration and fixtures for bmlibrarian tests."""

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def clean_environment():
    """Fixture to clean environment variables before and after tests."""
    # Store original environment
    original_env = {}
    env_vars = ['POSTGRES_HOST', 'POSTGRES_PORT', 'POSTGRES_USER', 
               'POSTGRES_PASSWORD', 'POSTGRES_DB']
    
    for var in env_vars:
        original_env[var] = os.environ.get(var)
        # Clear the variable
        os.environ.pop(var, None)
    
    yield
    
    # Restore original environment
    for var, value in original_env.items():
        if value is None:
            os.environ.pop(var, None)
        else:
            os.environ[var] = value


@pytest.fixture
def test_env():
    """Fixture providing test database environment variables."""
    return {
        'POSTGRES_HOST': 'localhost',
        'POSTGRES_PORT': '5432',
        'POSTGRES_USER': 'testuser',
        'POSTGRES_PASSWORD': 'testpass',
        'POSTGRES_DB': 'testdb'
    }


@pytest.fixture
def migration_manager_params():
    """Fixture providing standard MigrationManager parameters."""
    return {
        'host': 'localhost',
        'port': '5432',
        'user': 'testuser',
        'password': 'testpass',
        'database': 'testdb'
    }


@pytest.fixture
def mock_psycopg_connection():
    """Fixture providing a mock psycopg connection."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_conn.__enter__.return_value = mock_conn
    return mock_conn, mock_cursor


@pytest.fixture
def temporary_sql_file():
    """Fixture providing a temporary SQL file."""
    content = "CREATE TABLE test_table (id SERIAL PRIMARY KEY, name VARCHAR(100));"
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.sql', delete=False) as f:
        f.write(content)
        temp_path = Path(f.name)
    
    yield temp_path, content
    
    # Cleanup
    temp_path.unlink()


@pytest.fixture
def temporary_migrations_dir():
    """Fixture providing a temporary migrations directory with test files."""
    with tempfile.TemporaryDirectory() as temp_dir:
        migrations_dir = Path(temp_dir)
        
        # Create test migration files
        migrations = [
            ("001_initial.sql", "CREATE TABLE users (id SERIAL PRIMARY KEY);"),
            ("002_add_posts.sql", "CREATE TABLE posts (id SERIAL PRIMARY KEY, user_id INT);"),
            ("003_add_comments.sql", "CREATE TABLE comments (id SERIAL PRIMARY KEY, post_id INT);")
        ]
        
        migration_files = []
        for filename, content in migrations:
            migration_file = migrations_dir / filename
            migration_file.write_text(content)
            migration_files.append((migration_file, content))
        
        yield migrations_dir, migration_files


@pytest.fixture
def baseline_schema_file():
    """Fixture providing a baseline schema file."""
    content = """
-- Baseline schema for bmlibrarian
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE authors (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE papers (
    id SERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    abstract TEXT,
    author_id INT REFERENCES authors(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.sql', delete=False) as f:
        f.write(content)
        temp_path = Path(f.name)
    
    yield temp_path, content
    
    # Cleanup
    temp_path.unlink()


@pytest.fixture
def mock_applied_migrations():
    """Fixture providing mock applied migrations data."""
    return [
        ("001_initial.sql", "abc123def456"),
        ("002_add_posts.sql", "def456ghi789")
    ]


@pytest.fixture
def cli_args_init():
    """Fixture providing CLI args for init command."""
    args = MagicMock()
    args.command = "migrate"
    args.migrate_action = "init"
    args.host = "localhost"
    args.port = "5432"
    args.user = "testuser"
    args.password = "testpass"
    args.database = "testdb"
    args.baseline_schema = None
    return args


@pytest.fixture
def cli_args_apply():
    """Fixture providing CLI args for apply command."""
    args = MagicMock()
    args.command = "migrate"
    args.migrate_action = "apply"
    args.host = "localhost"
    args.port = "5432"
    args.user = "testuser"
    args.password = "testpass"
    args.database = "testdb"
    args.migrations_dir = None
    return args


@pytest.fixture(autouse=True)
def isolate_tests():
    """Automatically isolate tests by cleaning up any state."""
    yield
    # Any cleanup code can go here if needed