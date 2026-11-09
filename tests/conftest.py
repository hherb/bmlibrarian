"""Pytest configuration and fixtures for bmlibrarian tests."""

import os
import socket
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterator, List
from unittest.mock import MagicMock
from urllib.parse import urlsplit

import psycopg
import psycopg_pool
import pytest

# Live tests (#334): a plain ``pytest tests/`` must not read whatever database
# the default .env points at (on a dev machine, production) or need Ollama.
RUN_LIVE_OPTION = "--run-live"
TEST_DB_ENV_VARIABLE = "BMLIBRARIAN_TEST_DB_ENV"
LIVE_MARKERS = ("requires_database", "requires_ollama")
ENV_FILE_VARIABLE = "BMLIBRARIAN_ENV_FILE"  # bmlibrarian.env_loader, not imported here


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add ``--run-live`` (run tests that need a live database or Ollama)."""
    parser.addoption(
        RUN_LIVE_OPTION, action="store_true", default=False,
        help="run tests marked requires_database/requires_ollama against the configured "
             f"database and Ollama (also enabled when {TEST_DB_ENV_VARIABLE} is set, which "
             f"then also selects that env file for the whole run)")


def live_tests_enabled(config: pytest.Config) -> bool:
    """Whether live tests run: ``--run-live`` or ``BMLIBRARIAN_TEST_DB_ENV`` set."""
    return bool(config.getoption(RUN_LIVE_OPTION) or os.environ.get(TEST_DB_ENV_VARIABLE))


def pytest_configure(config: pytest.Config) -> None:
    """Point every live test at the dev database named by ``BMLIBRARIAN_TEST_DB_ENV``.

    Setting the variable turns all live tests on, so without this the tests that
    do not read it themselves would use the default env file (production).
    An explicit ``BMLIBRARIAN_ENV_FILE`` is left alone.
    """
    test_db_env = os.environ.get(TEST_DB_ENV_VARIABLE, "").strip()
    if test_db_env:
        os.environ.setdefault(ENV_FILE_VARIABLE, test_db_env)


def pytest_collection_modifyitems(config: pytest.Config, items: List[pytest.Item]) -> None:
    """Skip tests carrying a live marker unless live tests are enabled."""
    if live_tests_enabled(config):
        return
    skip = pytest.mark.skip(reason=f"needs a live service; run with {RUN_LIVE_OPTION} "
                                   f"or set {TEST_DB_ENV_VARIABLE}")
    for item in items:
        if any(item.get_closest_marker(name) for name in LIVE_MARKERS):
            item.add_marker(skip)


# Guard trips of the running test, kept so that one swallowed on the way (a Qt
# slot or timer callback, a background thread) still fails the test.
_GUARD_TRIPS: List[str] = []


def _live_access_failure(service: str, marker: str) -> None:
    """Fail the current test for reaching a live service without its marker."""
    message = (f"test reached a live {service} without @pytest.mark.{marker}; mock it, "
               f"or mark the test and run it with {RUN_LIVE_OPTION}")
    _GUARD_TRIPS.append(message)
    pytest.fail(message, pytrace=False)


@pytest.hookimpl(wrapper=True)
def pytest_runtest_call(item: pytest.Item) -> Any:
    """Fail a test whose guard trip was swallowed instead of reaching pytest."""
    _GUARD_TRIPS.clear()
    result = yield  # a trip that propagated is already this test's failure
    if _GUARD_TRIPS:
        pytest.fail(f"swallowed by the code under test: {_GUARD_TRIPS[0]}", pytrace=False)
    return result


@pytest.fixture
def live_guard_trips() -> List[str]:
    """The guard trips of the running test; a test that trips on purpose clears it."""
    return _GUARD_TRIPS


@pytest.fixture(scope="session", autouse=True)
def _block_live_services(request: pytest.FixtureRequest) -> Iterator[None]:
    """Make an unmarked test that opens a PostgreSQL connection or reaches Ollama fail.

    Without live tests enabled, connecting through psycopg/psycopg_pool or to the
    local Ollama port fails the test with a message naming the marker it needs
    (``pytest.fail`` raises a ``BaseException``, so ``except Exception`` in the
    code under test does not hide it; see ``pytest_runtest_call`` for one caught
    elsewhere). Session scope applies it before any module or class fixture.
    Tests that mock these themselves are unaffected: their patches go on top.
    """
    if live_tests_enabled(request.config):
        yield
        return

    def blocked_db(*_args: Any, **_kwargs: Any) -> None:
        """Stand-in for psycopg connection entry points."""
        _live_access_failure("PostgreSQL database", "requires_database")

    # Imported here so that loading conftest does not import bmlibrarian.
    from bmlibrarian.llm.constants import DEFAULT_OLLAMA_HOST

    # shortcut: only Ollama on the default port is blocked; a test reaching a
    # remote or non-default OLLAMA_HOST still gets through. Upgrade if such a test turns up.
    ollama_port = urlsplit(DEFAULT_OLLAMA_HOST).port
    assert ollama_port is not None, f"DEFAULT_OLLAMA_HOST {DEFAULT_OLLAMA_HOST!r} names no port"
    real_connect = socket.socket.connect

    def guarded_connect(sock: socket.socket, address: Any) -> None:
        """``socket.connect`` that refuses the local Ollama port."""
        if isinstance(address, tuple) and len(address) >= 2 and address[1] == ollama_port:
            _live_access_failure("Ollama server", "requires_ollama")
        real_connect(sock, address)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(psycopg, "connect", blocked_db)
        patch.setattr(psycopg.Connection, "connect", blocked_db)
        patch.setattr(psycopg_pool.ConnectionPool, "__init__", blocked_db)
        patch.setattr(socket.socket, "connect", guarded_connect)
        yield


# Modules that bind list_ollama_models at import; the others look it up in
# bmlibrarian.llm when called.
MODEL_LIST_IMPORTERS = (
    "bmlibrarian.llm",
    "bmlibrarian.gui.qt.plugins.configuration.config_tab",
    "bmlibrarian.gui.qt.plugins.settings.plugin",
)
OFFLINE_MODELS = ["gpt-oss:20b", "medgemma4B_it_q8:latest"]


@pytest.fixture
def offline_model_list(monkeypatch: pytest.MonkeyPatch) -> List[str]:
    """Make GUI model pickers list ``OFFLINE_MODELS`` instead of asking Ollama."""
    for module in MODEL_LIST_IMPORTERS:
        monkeypatch.setattr(f"{module}.list_ollama_models", lambda *_a, **_k: list(OFFLINE_MODELS))
    return OFFLINE_MODELS


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
    # A remembered migration failure (#379) must not leak into later tests
    database = sys.modules.get("bmlibrarian.database")
    if database is not None:
        database._db_manager_error = None
        # A Qt fatal-dialog handler (#381) must not fire in later tests
        database._migration_failure_handler = None

@pytest.fixture(autouse=True)
def _no_backoff_waits(monkeypatch: pytest.MonkeyPatch) -> list:
    """Make retries with exponential backoff return at once.

    ``call_with_backoff`` waits through ``transient_retry._sleep``; tests that
    exercise a recoverable failure would otherwise sleep for seconds. The
    requested delays are recorded and returned for tests that check them.
    """
    from bmlibrarian.utils import transient_retry

    delays: list = []
    monkeypatch.setattr(transient_retry, "_sleep", delays.append)
    return delays
