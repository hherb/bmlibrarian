"""
Tests for bmlibrarian.env_loader: which .env file configures the database.

``BMLIBRARIAN_ENV_FILE`` selects an explicit env file (e.g. the PostgreSQL 18
configuration) instead of ``~/.bmlibrarian/.env``. A missing explicit file must
fail loudly: silently falling back to the default file would point the caller
at whatever database that file names (today: the production knowledgebase).
"""

import os
from pathlib import Path

import pytest

from bmlibrarian import env_loader


def write_env(path: Path, port: str) -> Path:
    """Write a minimal env file and return its path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"POSTGRES_PORT={port}\nPOSTGRES_DB=db_{port}\n", encoding="utf-8")
    return path


class TestResolveEnvFile:
    """Pure resolution of the env file to load."""

    def test_explicit_variable_selects_that_file(self, tmp_path: Path) -> None:
        explicit = write_env(tmp_path / "pg18.env", "5532")
        write_env(tmp_path / "home" / ".bmlibrarian" / ".env", "5432")
        resolved = env_loader.resolve_env_file({env_loader.ENV_FILE_VARIABLE: str(explicit)}, tmp_path / "home")
        assert resolved == explicit

    def test_missing_explicit_file_raises_instead_of_falling_back(self, tmp_path: Path) -> None:
        write_env(tmp_path / "home" / ".bmlibrarian" / ".env", "5432")
        with pytest.raises(FileNotFoundError):
            env_loader.resolve_env_file({env_loader.ENV_FILE_VARIABLE: str(tmp_path / "nope.env")},
                                        tmp_path / "home")

    def test_default_user_env_when_no_variable(self, tmp_path: Path) -> None:
        default = write_env(tmp_path / "home" / ".bmlibrarian" / ".env", "5432")
        assert env_loader.resolve_env_file({}, tmp_path / "home") == default

    def test_none_when_no_variable_and_no_user_env(self, tmp_path: Path) -> None:
        assert env_loader.resolve_env_file({}, tmp_path / "home") is None


class TestLoadEnv:
    """Loading applies the resolved file over the existing environment."""

    def test_explicit_file_overrides_existing_values(self, tmp_path: Path, monkeypatch) -> None:
        explicit = write_env(tmp_path / "pg18.env", "5532")
        monkeypatch.setenv(env_loader.ENV_FILE_VARIABLE, str(explicit))
        monkeypatch.setenv("POSTGRES_PORT", "5432")
        monkeypatch.setenv("POSTGRES_DB", "knowledgebase")
        loaded = env_loader.load_bmlibrarian_env(home=tmp_path / "home")
        assert loaded == explicit
        assert os.environ["POSTGRES_PORT"] == "5532"
        assert os.environ["POSTGRES_DB"] == "db_5532"


class TestDatabaseModuleHonoursSelection:
    """Importing bmlibrarian.database loads the selected file, not ~/.bmlibrarian/.env."""

    def test_database_import_uses_explicit_env_file(self, tmp_path: Path) -> None:
        import subprocess
        import sys

        home = tmp_path / "home"
        write_env(home / ".bmlibrarian" / ".env", "5432")
        explicit = write_env(tmp_path / "pg18.env", "5532")
        env = {k: v for k, v in os.environ.items() if not k.startswith("POSTGRES_")}
        env.update({"HOME": str(home), env_loader.ENV_FILE_VARIABLE: str(explicit)})
        out = subprocess.run(
            [sys.executable, "-c", "import os, bmlibrarian.database; print(os.environ['POSTGRES_PORT'])"],
            env=env, capture_output=True, text=True, check=True)
        assert out.stdout.strip() == "5532"


class TestDatabaseManagerExplicitConninfo:
    """An explicit conninfo wins over the environment (used by worker processes)."""

    def test_explicit_conninfo_is_used_and_env_ignored(self, monkeypatch) -> None:
        from unittest.mock import patch

        from bmlibrarian import database

        monkeypatch.setenv("POSTGRES_DB", "knowledgebase")
        monkeypatch.setenv("POSTGRES_USER", "someone")
        monkeypatch.setenv("POSTGRES_PASSWORD", "secret")
        with patch.object(database, "ConnectionPool") as pool:
            manager = database.DatabaseManager(auto_migrate=False, conninfo="host=localhost port=5532 dbname=dev_db")
        assert pool.call_args.kwargs["conninfo"] == "host=localhost port=5532 dbname=dev_db"
        assert manager.conninfo == "host=localhost port=5532 dbname=dev_db"
