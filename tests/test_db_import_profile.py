"""
Tests for bmlibrarian.db_import_profile (import-time PostgreSQL server settings).

Pure helpers are tested directly; the apply/restore flow runs against a fake
server connection and a fake restart function, so no real server is touched
(a real restart would drop every connection on that server).
"""

import json
from pathlib import Path
from typing import Dict, List, Optional

import pytest

from bmlibrarian import db_import_profile as dip


class TestValidation:
    """ALTER SYSTEM cannot take bind parameters: only allow-listed names and plain sizes pass."""

    def test_allowed_setting_and_size_pass(self) -> None:
        dip.validate_setting("shared_buffers", "32GB")
        dip.validate_setting("max_wal_size", None)

    def test_unknown_setting_is_rejected(self) -> None:
        with pytest.raises(ValueError):
            dip.validate_setting("listen_addresses", "*")

    def test_injection_value_is_rejected(self) -> None:
        with pytest.raises(ValueError):
            dip.validate_setting("shared_buffers", "1GB'; DROP TABLE x; --")


class TestPureHelpers:
    """Parsing and planning without a server."""

    def test_parse_auto_conf(self) -> None:
        text = "# Do not edit\nmaintenance_work_mem = '8GB'\nshared_buffers='1GB'\n"
        assert dip.parse_auto_conf(text) == {"maintenance_work_mem": "8GB", "shared_buffers": "1GB"}

    def test_restore_plan_resets_new_and_restores_previous(self) -> None:
        plan = dip.restore_plan({"shared_buffers": "32GB", "max_wal_size": "64GB"}, {"max_wal_size": "4GB"})
        assert plan == {"shared_buffers": None, "max_wal_size": "4GB"}

    def test_bindir_from_postmaster_opts(self) -> None:
        opts = ('/Applications/Postgres 2.app/Contents/Versions/18/bin/postgres "-D" "/data" "-p" "5532"')
        assert dip.bindir_from_postmaster_opts(opts) == Path("/Applications/Postgres 2.app/Contents/Versions/18/bin")

    def test_bindir_from_quoted_postmaster_opts(self) -> None:
        opts = '"/usr/lib/postgresql/18/bin/postgres" "-D" "/var/lib/pg"'
        assert dip.bindir_from_postmaster_opts(opts) == Path("/usr/lib/postgresql/18/bin")

    def test_other_sessions_block_unless_forced(self) -> None:
        sessions = [("drugref", "psql", 123)]
        with pytest.raises(dip.ImportProfileError):
            dip.check_no_other_sessions(sessions, force=False)
        dip.check_no_other_sessions(sessions, force=True)
        dip.check_no_other_sessions([], force=False)


class FakeServer:
    """Records ALTER SYSTEM statements and simulates settings and restarts."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.statements: List[str] = []
        self.restarts = 0
        self.pending_restart = False

    def run(self, sql: str) -> None:
        self.statements.append(sql)
        if "shared_buffers" in sql:
            self.pending_restart = True

    def restart(self) -> None:
        self.restarts += 1
        self.pending_restart = False


def make_profile(tmp_path: Path, server: FakeServer, auto_conf: str = "") -> dip.ImportProfile:
    (server.data_dir / "postgresql.auto.conf").write_text(auto_conf, encoding="utf-8")
    return dip.ImportProfile(
        state_file=tmp_path / "state.json",
        data_dir=server.data_dir,
        execute=server.run,
        pending_restart=lambda: server.pending_restart,
        restart=server.restart,
        other_sessions=lambda: [],
        is_superuser=lambda: True,
    )


class TestApplyRestore:
    """The flow: state first, ALTER SYSTEM, restart only when needed, exact restore."""

    def test_apply_writes_state_then_alters_and_restarts(self, tmp_path: Path) -> None:
        server = FakeServer(tmp_path)
        profile = make_profile(tmp_path, server)
        profile.apply({"shared_buffers": "32GB", "max_wal_size": "64GB"})
        state = json.loads((tmp_path / "state.json").read_text())
        assert state["restore"] == {"shared_buffers": None, "max_wal_size": None}
        assert "ALTER SYSTEM SET shared_buffers = '32GB'" in server.statements
        assert server.restarts == 1

    def test_apply_is_noop_while_state_exists(self, tmp_path: Path) -> None:
        server = FakeServer(tmp_path)
        profile = make_profile(tmp_path, server)
        profile.apply({"max_wal_size": "64GB"})
        n = len(server.statements)
        assert profile.apply({"max_wal_size": "64GB"}) == dip.ALREADY_ACTIVE
        assert len(server.statements) == n

    def test_restore_returns_previous_values_and_removes_state(self, tmp_path: Path) -> None:
        server = FakeServer(tmp_path)
        profile = make_profile(tmp_path, server, auto_conf="max_wal_size = '4GB'\n")
        profile.apply({"shared_buffers": "32GB", "max_wal_size": "64GB"})
        server.statements.clear()
        profile.restore()
        assert "ALTER SYSTEM RESET shared_buffers" in server.statements
        assert "ALTER SYSTEM SET max_wal_size = '4GB'" in server.statements
        assert not (tmp_path / "state.json").exists()
        assert server.restarts == 2

    def test_apply_refuses_without_superuser(self, tmp_path: Path) -> None:
        server = FakeServer(tmp_path)
        profile = make_profile(tmp_path, server)
        profile.is_superuser = lambda: False
        with pytest.raises(dip.ImportProfileError):
            profile.apply({"max_wal_size": "64GB"})
        assert not (tmp_path / "state.json").exists()
