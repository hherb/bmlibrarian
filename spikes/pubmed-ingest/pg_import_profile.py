#!/usr/bin/env python3
"""
Switch the local PostgreSQL server between an *import* profile and the
day-to-day profile, and back.

Bulk imports want large shared buffers and a large WAL allowance (no checkpoint
every few seconds). Day to day, the RAM is needed for model inference. This
tool applies the import profile with ``ALTER SYSTEM`` (restarting the server
only when a restart-only setting changes), and restores exactly what was there
before.

Crash safety: the original values are written to a state file **before**
anything is changed. While the state file exists the import profile counts as
active: ``apply`` is then a no-op, so a resumed import keeps the profile, and
``restore`` puts the saved values back and deletes the file. A killed import
leaves the server in the import profile until ``restore`` runs.

The settings are server-wide: they affect every database on this server,
``knowledgebase`` included. A restart drops all open connections.

Usage:
    uv run python spikes/pubmed-ingest/pg_import_profile.py status
    uv run python spikes/pubmed-ingest/pg_import_profile.py apply [--shared-buffers 32GB]
    uv run python spikes/pubmed-ingest/pg_import_profile.py restore
"""

import argparse
import contextlib
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, Iterator, Optional, Sequence

SPIKE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SPIKE_DIR))
import bench_python as b  # noqa: E402

STATE_FILE = Path.home() / ".bmlibrarian" / "pg_import_profile_state.json"
PG_CTL = Path("/Applications/Postgres.app/Contents/Versions/16/bin/pg_ctl")
RESTART_TIMEOUT_S = 300
RECONNECT_ATTEMPTS = 60
RECONNECT_DELAY_S = 1.0

ALLOWED_SETTINGS = frozenset({"shared_buffers", "max_wal_size", "min_wal_size"})
VALUE_PATTERN = re.compile(r"[0-9]+(kB|MB|GB|TB)?")

# The import profile. Only shared_buffers costs RAM; the WAL settings cost disk.
DEFAULT_IMPORT_PROFILE: Dict[str, str] = {
    "shared_buffers": "32GB",   # postmaster: needs a restart
    "max_wal_size": "64GB",     # sighup: no checkpoint storm during COPY merges
    "min_wal_size": "4GB",      # sighup
}


def current_settings(names: Sequence[str]) -> Dict[str, dict]:
    """Current value, unit, context and source of each setting."""
    with b.connect() as conn:
        rows = conn.execute("SELECT name, setting, unit, context, source, pending_restart "
                            "FROM pg_settings WHERE name = ANY(%s)", (list(names),)).fetchall()
        data_dir = conn.execute("SHOW data_directory").fetchone()[0]
    out = {r[0]: {"setting": r[1], "unit": r[2], "context": r[3], "source": r[4],
                  "pending_restart": r[5]} for r in rows}
    out["_data_directory"] = {"setting": data_dir}
    return out


def auto_conf_values(data_dir: str) -> Dict[str, str]:
    """Entries currently in postgresql.auto.conf (what ALTER SYSTEM manages)."""
    path = Path(data_dir) / "postgresql.auto.conf"
    values: Dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip().strip("'")
    return values


def restart_server(data_dir: str) -> None:
    """Fast restart with the server's own recorded options (postmaster.opts)."""
    subprocess.run([str(PG_CTL), "restart", "-D", data_dir, "-m", "fast", "-w",
                    "-t", str(RESTART_TIMEOUT_S)], check=True, stdout=subprocess.DEVNULL)
    for _ in range(RECONNECT_ATTEMPTS):
        try:
            with b.connect() as conn:
                conn.execute("SELECT 1")
            return
        except Exception:  # server still starting
            time.sleep(RECONNECT_DELAY_S)
    raise RuntimeError("server did not come back after restart")


def validated(name: str, value: Optional[str]) -> None:
    """ALTER SYSTEM cannot take bind parameters, so only allow-listed names and
    plain size/number values ever reach the SQL text (the state file is a file
    on disk and is not trusted either)."""
    if name not in ALLOWED_SETTINGS:
        raise ValueError(f"setting {name!r} is not managed by this tool")
    if value is not None and not VALUE_PATTERN.fullmatch(value):
        raise ValueError(f"refusing value {value!r} for {name}")


def alter_system(values: Dict[str, Optional[str]]) -> None:
    """ALTER SYSTEM SET (or RESET for None), then reload."""
    for name, value in values.items():
        validated(name, value)
    with b.connect() as conn:
        conn.autocommit = True
        for name, value in values.items():
            if value is None:
                conn.execute(f"ALTER SYSTEM RESET {name}")
            else:
                conn.execute(f"ALTER SYSTEM SET {name} = '{value}'")
        conn.execute("SELECT pg_reload_conf()")


def needs_restart(names: Sequence[str]) -> bool:
    """True if any of the settings is restart-only and now pending."""
    settings = current_settings(names)
    return any(settings[n]["context"] == "postmaster" and settings[n]["pending_restart"] for n in names)


def apply(profile: Dict[str, str]) -> str:
    """Apply the import profile; idempotent while the state file exists."""
    if STATE_FILE.exists():
        return f"import profile already active (state file {STATE_FILE})"
    settings = current_settings(list(profile))
    data_dir = settings["_data_directory"]["setting"]
    auto = auto_conf_values(data_dir)
    state = {"data_directory": data_dir, "applied_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
             "profile": profile,
             # What ALTER SYSTEM held before: a value to restore, or None = RESET.
             "restore": {name: auto.get(name) for name in profile},
             "before": {name: settings[name] for name in profile}}
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    alter_system(dict(profile))
    if needs_restart(list(profile)):
        restart_server(data_dir)
    return "import profile applied"


def restore() -> str:
    """Restore the day-to-day profile from the state file."""
    if not STATE_FILE.exists():
        return "nothing to restore (no state file)"
    state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    alter_system(state["restore"])
    if needs_restart(list(state["profile"])):
        restart_server(state["data_directory"])
    STATE_FILE.unlink()
    return "day-to-day profile restored"


@contextlib.contextmanager
def import_profile(profile: Optional[Dict[str, str]] = None) -> Iterator[None]:
    """Apply the import profile for the duration of a (successful) import.

    On a normal exit or an exception the day-to-day profile is restored. A
    SIGKILL leaves the state file, so the next resumed import keeps the profile
    and its own exit restores it.
    """
    print(apply(profile or DEFAULT_IMPORT_PROFILE), file=sys.stderr)
    try:
        yield
    finally:
        print(restore(), file=sys.stderr)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Entry point."""
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("command", choices=("status", "apply", "restore"))
    p.add_argument("--shared-buffers", default=DEFAULT_IMPORT_PROFILE["shared_buffers"])
    p.add_argument("--max-wal-size", default=DEFAULT_IMPORT_PROFILE["max_wal_size"])
    args = p.parse_args(argv)
    if args.command == "status":
        names = list(DEFAULT_IMPORT_PROFILE)
        print(json.dumps({"state_file": str(STATE_FILE) if STATE_FILE.exists() else None,
                          "settings": current_settings(names)}, indent=2))
    elif args.command == "apply":
        print(apply({**DEFAULT_IMPORT_PROFILE, "shared_buffers": args.shared_buffers,
                     "max_wal_size": args.max_wal_size}))
    else:
        print(restore())
    return 0


if __name__ == "__main__":
    sys.exit(main())
