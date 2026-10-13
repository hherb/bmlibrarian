"""Import-time PostgreSQL server settings, applied for a bulk import and restored after.

Bulk imports want large shared buffers and a large WAL allowance (otherwise the
server checkpoints every few seconds: ~6 per minute measured during COPY
merges). Day to day that RAM is needed for model inference, so the import
profile is *borrowed*: applied with ``ALTER SYSTEM`` before an import (restarting
the server only when a restart-only setting such as ``shared_buffers`` changes)
and restored exactly afterwards.

Crash safety: the values that ``ALTER SYSTEM`` held before are written to a state
file **before** anything is changed. While that file exists the profile counts
as active, so ``apply`` is a no-op (a resumed import keeps the profile) and
``restore`` puts the saved values back and removes the file. A killed import
leaves the server in the import profile until ``restore`` runs.

These settings are server-wide: every database on that server is affected, and
a restart drops all of its connections. ``apply`` therefore refuses while other
client sessions are connected, unless forced. A superuser connection is needed.
"""

import json
import re
import shlex
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Dict, Iterator, List, Mapping, Optional, Sequence, Tuple

import psycopg

ALLOWED_SETTINGS = frozenset({"shared_buffers", "max_wal_size", "min_wal_size"})
VALUE_PATTERN = re.compile(r"[0-9]+(kB|MB|GB|TB)?")
DEFAULT_IMPORT_PROFILE: Dict[str, str] = {
    "shared_buffers": "32GB",   # restart-only; the one setting that costs RAM
    "max_wal_size": "64GB",     # disk, not RAM: no checkpoint storm during merges
    "min_wal_size": "4GB",
}
STATE_DIR = Path.home() / ".bmlibrarian"
STATE_FILE_TEMPLATE = "pg_import_profile_{port}.json"
AUTO_CONF_NAME = "postgresql.auto.conf"
POSTMASTER_OPTS_NAME = "postmaster.opts"
PG_CTL_NAME = "pg_ctl"
SERVER_LOG_NAME = "postgresql.log"   # Postgres.app's server log in the data directory
RESTART_TIMEOUT_S = 300
RECONNECT_ATTEMPTS = 60
RECONNECT_DELAY_S = 1.0

ALREADY_ACTIVE = "import profile already active"
APPLIED = "import profile applied"
RESTORED = "day-to-day profile restored"
NOTHING_TO_RESTORE = "nothing to restore (no state file)"

Session = Tuple[str, str, int]   # (database, application_name, pid)


class ImportProfileError(RuntimeError):
    """The import profile cannot be applied or restored safely."""


def validate_setting(name: str, value: Optional[str]) -> None:
    """Allow only managed setting names and plain size values.

    ALTER SYSTEM cannot take bind parameters, so these are inlined into SQL; the
    state file is a file on disk and is not trusted either.

    Raises:
        ValueError: If the name is not managed or the value is not a plain size.
    """
    if name not in ALLOWED_SETTINGS:
        raise ValueError(f"setting {name!r} is not managed by the import profile")
    if value is not None and not VALUE_PATTERN.fullmatch(value):
        raise ValueError(f"refusing value {value!r} for {name}")


def parse_auto_conf(text: str) -> Dict[str, str]:
    """Settings currently in ``postgresql.auto.conf`` (what ALTER SYSTEM manages)."""
    values: Dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip().strip("'")
    return values


def restore_plan(profile: Mapping[str, str], auto_conf: Mapping[str, str]) -> Dict[str, Optional[str]]:
    """What to restore for each profile setting: the previous ALTER SYSTEM value, or None (= RESET)."""
    return {name: auto_conf.get(name) for name in profile}


def bindir_from_postmaster_opts(text: str) -> Path:
    """Directory of the server binary, from ``postmaster.opts``.

    The first token is the ``postgres`` binary; Postgres.app writes it unquoted
    even when the path contains spaces, so it is matched up to ``/postgres``.

    Raises:
        ValueError: If no server binary path can be found.
    """
    text = text.strip()
    quoted = re.match(r'^"([^"]+)"', text)
    if quoted:
        return Path(quoted.group(1)).parent
    unquoted = re.match(r"^(.*?/postgres)(?:\s|$)", text)
    if unquoted:
        return Path(unquoted.group(1)).parent
    raise ValueError(f"cannot find the server binary in {POSTMASTER_OPTS_NAME}: {text[:80]!r}")


def server_start_options(text: str) -> List[str]:
    """Server options recorded in ``postmaster.opts``, without the binary and ``-D <dir>``.

    ``pg_ctl restart`` replays these through a shell, which expands literal
    ``$system`` / ``$libdir`` in Postgres.app's ``extension_control_path`` and
    ``dynamic_library_path`` to empty strings -- the restarted server then cannot
    find its own libraries. The options are therefore read here and passed back
    shell-quoted (see :func:`shell_quoted_options`).
    """
    tokens = re.findall(r'"((?:[^"\\]|\\.)*)"', text)
    if text.strip().startswith('"'):
        tokens = tokens[1:]   # quoted binary path
    options: List[str] = []
    skip_next = False
    for token in tokens:
        if skip_next:
            skip_next = False
            continue
        if token == "-D":
            skip_next = True
            continue
        options.append(token)
    return options


def shell_quoted_options(options: Sequence[str]) -> str:
    """Join options for ``pg_ctl -o`` so the shell passes every character literally."""
    return " ".join(shlex.quote(option) for option in options)


def check_no_other_sessions(sessions: Sequence[Session], force: bool) -> None:
    """Refuse to restart the server while other clients are connected (unless forced).

    Raises:
        ImportProfileError: If other sessions exist and ``force`` is False.
    """
    if sessions and not force:
        listed = ", ".join(f"{db}/{app or '?'} (pid {pid})" for db, app, pid in sessions[:10])
        raise ImportProfileError(
            f"{len(sessions)} other client session(s) would be dropped by the restart: {listed}. "
            "Close them or use force.")


def default_state_file(port: str) -> Path:
    """Per-server state file: ``~/.bmlibrarian/pg_import_profile_<port>.json``."""
    return STATE_DIR / STATE_FILE_TEMPLATE.format(port=port)


class ImportProfile:
    """Apply and restore the import profile on one server.

    The server interactions are injected callables so the flow can be tested
    without a server; use :meth:`for_server` for the real thing.
    """

    def __init__(
        self,
        state_file: Path,
        data_dir: Path,
        execute: Callable[[str], None],
        pending_restart: Callable[[], bool],
        restart: Callable[[], None],
        other_sessions: Callable[[], List[Session]],
        is_superuser: Callable[[], bool],
    ) -> None:
        """Create a profile controller (see :meth:`for_server`)."""
        self.state_file = Path(state_file)
        self.data_dir = Path(data_dir)
        self.execute = execute
        self.pending_restart = pending_restart
        self.restart = restart
        self.other_sessions = other_sessions
        self.is_superuser = is_superuser

    @property
    def is_active(self) -> bool:
        """Whether the import profile is applied (state file present)."""
        return self.state_file.exists()

    def _alter(self, values: Mapping[str, Optional[str]]) -> None:
        """ALTER SYSTEM SET/RESET each value, then reload, then restart if needed."""
        for name, value in values.items():
            validate_setting(name, value)
        for name, value in values.items():
            if value is None:
                self.execute(f"ALTER SYSTEM RESET {name}")
            else:
                self.execute(f"ALTER SYSTEM SET {name} = '{value}'")
        self.execute("SELECT pg_reload_conf()")
        if self.pending_restart():
            self.restart()

    def apply(self, profile: Optional[Mapping[str, str]] = None, force: bool = False) -> str:
        """Apply the import profile (no-op while the state file exists).

        Raises:
            ImportProfileError: Without superuser rights, or while other sessions
                are connected (unless ``force``).
        """
        if self.is_active:
            return ALREADY_ACTIVE
        profile = dict(profile or DEFAULT_IMPORT_PROFILE)
        for name, value in profile.items():
            validate_setting(name, value)
        if not self.is_superuser():
            raise ImportProfileError("the import profile needs a superuser connection (ALTER SYSTEM)")
        check_no_other_sessions(self.other_sessions(), force)
        auto_conf = parse_auto_conf((self.data_dir / AUTO_CONF_NAME).read_text(encoding="utf-8"))
        state = {"data_directory": str(self.data_dir), "applied_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                 "profile": profile, "restore": restore_plan(profile, auto_conf)}
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")
        self._alter(profile)
        return APPLIED

    def restore(self) -> str:
        """Restore the day-to-day profile recorded in the state file."""
        if not self.is_active:
            return NOTHING_TO_RESTORE
        state = json.loads(self.state_file.read_text(encoding="utf-8"))
        self._alter(state["restore"])
        self.state_file.unlink()
        return RESTORED

    @classmethod
    def for_server(cls, conninfo: str, state_file: Optional[Path] = None) -> "ImportProfile":
        """A controller for the server behind ``conninfo`` (must be local to this machine)."""
        with psycopg.connect(conninfo) as conn:
            data_dir = Path(conn.execute("SHOW data_directory").fetchone()[0])
            port = conn.execute("SHOW port").fetchone()[0]
        bindir = bindir_from_postmaster_opts((data_dir / POSTMASTER_OPTS_NAME).read_text(encoding="utf-8"))

        def execute(sql: str) -> None:
            with psycopg.connect(conninfo, autocommit=True) as conn:
                conn.execute(sql)

        def pending_restart() -> bool:
            with psycopg.connect(conninfo) as conn:
                return bool(conn.execute("SELECT bool_or(pending_restart) FROM pg_settings WHERE name = ANY(%s)",
                                         (list(ALLOWED_SETTINGS),)).fetchone()[0])

        def restart() -> None:
            # Not `pg_ctl restart`: it replays postmaster.opts through a shell that
            # expands Postgres.app's literal $system/$libdir. Read the options first,
            # stop, then start with every option shell-quoted.
            options = server_start_options((data_dir / POSTMASTER_OPTS_NAME).read_text(encoding="utf-8"))
            pg_ctl = str(bindir / PG_CTL_NAME)
            subprocess.run([pg_ctl, "stop", "-D", str(data_dir), "-m", "fast", "-w",
                            "-t", str(RESTART_TIMEOUT_S)], check=True, stdout=subprocess.DEVNULL)
            subprocess.run([pg_ctl, "start", "-D", str(data_dir), "-l", str(data_dir / SERVER_LOG_NAME),
                            "-w", "-t", str(RESTART_TIMEOUT_S), "-o", shell_quoted_options(options)],
                           check=True, stdout=subprocess.DEVNULL)
            for _ in range(RECONNECT_ATTEMPTS):
                try:
                    with psycopg.connect(conninfo) as conn:
                        conn.execute("SELECT 1")
                    return
                except psycopg.OperationalError:
                    time.sleep(RECONNECT_DELAY_S)
            raise ImportProfileError("the server did not come back after the restart")

        def other_sessions() -> List[Session]:
            with psycopg.connect(conninfo) as conn:
                return [tuple(r) for r in conn.execute(
                    "SELECT datname, application_name, pid FROM pg_stat_activity "
                    "WHERE backend_type = 'client backend' AND pid <> pg_backend_pid()").fetchall()]

        def is_superuser() -> bool:
            with psycopg.connect(conninfo) as conn:
                return bool(conn.execute("SELECT rolsuper FROM pg_roles WHERE rolname = current_user").fetchone()[0])

        return cls(state_file or default_state_file(port), data_dir, execute, pending_restart, restart,
                   other_sessions, is_superuser)


@contextmanager
def import_profile(conninfo: str, profile: Optional[Mapping[str, str]] = None,
                   force: bool = False) -> Iterator[ImportProfile]:
    """Apply the import profile for the duration of the block and restore it after.

    Open connection pools *inside* the block and close them before it ends: the
    restart on apply/restore breaks existing connections. A SIGKILL leaves the
    state file, so the next (resumed) import keeps the profile and restores it.
    """
    controller = ImportProfile.for_server(conninfo)
    controller.apply(profile, force=force)
    try:
        yield controller
    finally:
        controller.restore()
