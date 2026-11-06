# `bml-pgserver`: the private PostgreSQL manager

The first crate of the Rust port (`rust/`), written for the one-click installer
(spec: `docs/superpowers/specs/2026-11-07-one-click-installer-design.md`; plan:
`docs/superpowers/plans/2026-11-07-rust-pgserver.md`). It is synchronous, with
no async runtime. The logic lives in pure functions, and a thin I/O layer runs
`initdb`/`pg_ctl` through `std::process::Command` (never a shell) and talks SQL
through the `postgres` crate.

## Modules

| Module | Responsibility |
|---|---|
| `port` | `DEFAULT_PORT` (5418), `is_avoided` (5432–5439, 5532, 6432, 6543, ≥ 49152), `choose_port(start, is_free)`, `port_is_free` (binds `127.0.0.1:port`) |
| `conf` | `render_bml_conf`, `render_pg_hba`, `ensure_include`, `quote_conf_value`, `provides_pg_search` |
| `envfile` | `ConnInfo`; `render_env` / `parse_env` / `read_conn_info`; `generate_password` (64 hex characters); `write_private_file` (atomic; mode 600 / `icacls`) |
| `state` | `ServerState` ↔ `bml-pgserver.json`; `resolve_config_dir(flag, env, home)` |
| `control` | `pg_major_version` (≥ 18), `status` / `start` / `stop` / `restart` (all idempotent), `total_memory_bytes` |
| `init` | `init(&InitRequest, config_dir)`, the resumable setup; `connect(&ConnInfo)` |
| `autostart` | LaunchAgent / `systemd --user` / HKCU `Run` renderers, `enable` / `disable` |
| `error` | `PgServerError` |

`bml-cli` (the `bml` binary) maps `bml server …` onto these functions.

## The config file contract

`initdb`'s `postgresql.conf` is kept as written, plus one line:
`include 'bml.conf'`. Everything we set lives in `bml.conf`:

- `port`
- `listen_addresses = '127.0.0.1'`
- `unix_socket_directories = ''` (TCP only, on every platform)
- `password_encryption = 'scram-sha-256'`
- `dynamic_library_path = '$libdir:<ext>/lib/postgresql:…'`
- `extension_control_path = '$system:<ext>/share/postgresql:…'`
- `shared_preload_libraries = 'pg_search'`, when an extension folder provides
  it

Path lists use `;` on Windows. `pg_hba.conf` is replaced with two loopback
`host … scram-sha-256` lines; there are no `local` or `trust` lines.
`postgresql.auto.conf` is left to `ALTER SYSTEM`, which the import profile
uses.

**Extension folders** use the layout Postgres.app uses for its own extensions
(`~/Library/Application Support/Postgres/Extensions/18/<name>/{lib,share}/postgresql`).
PostgreSQL 18's `extension_control_path` and `dynamic_library_path` then load
them without touching the PostgreSQL installation, so extensions can be
installed side by side, one folder per version. This was verified against
Postgres.app 18.1 with `pg_search`.

`pg_search` is created only when an extension folder provides it, because it
must be preloaded. A `pg_search` installed system-wide but not preloaded is
ignored. On Windows there is none, and the lexical-search fallback is a
migration concern (Phase B/C).

## `init` steps

Each step checks before it acts, so `init` can be repeated, and it resumes
after a kill at any point:

1. **Version check.** `postgres --version` must report ≥ 18.
2. **Port.** Take it from the state file. If there is no state file, use
   `choose_port`. A state file naming a different data or bin folder is
   `StateMismatch`.
3. **Data folder.**
   - `PG_VERSION` present: it's ours, continue.
   - Missing or empty: free to initialise.
   - Anything else: `DataDirNotEmpty`, and nothing is touched.
4. **Admin credentials.**
   - `bml-admin.env` is reused when it exists.
   - If it is missing and the data folder is initialised: `AdminCredentialsLost`,
     with no re-initialisation.
   - Otherwise a password is generated and written **before** `initdb`.
5. **`initdb`.** `-U bml_admin --pwfile=<private tmp> --auth=scram-sha-256
   --encoding=UTF8 --locale-provider=builtin --builtin-locale=C.UTF-8`. The
   pwfile is removed even if `initdb` fails. The builtin C.UTF-8 locale
   behaves the same on every OS.
6. **Server config.** Write `bml.conf`, `pg_hba.conf` and the include line,
   each only if its content differs.
7. **State.** Save the state file.
8. **Start.** Start the server, or restart it if it was running and step 6
   changed something.
9. **Role and database.**
   - Create the `bml_app` role if it is missing.
   - If the role exists but `bml.env` is gone, give it a new password with
     `ALTER ROLE`.
   - Create the `bmlibrarian` database, owned by `bml_app`, if it is missing.
10. **Extensions.** `CREATE EXTENSION IF NOT EXISTS vector`, failing with
    `ExtensionUnavailable` if it isn't available, plus `pg_search` when
    preloaded.
11. **App credentials.** Write `bml.env`.

Passwords are generated hex, so they are interpolated into `CREATE/ALTER ROLE`
safely. Role and database names are constants.

## Server control and autostart

- `restart` is stop + start, not `pg_ctl restart`. The latter replays
  `postmaster.opts` through a shell (the same reason as
  `db_import_profile.py`).
- Autostart runs `bml --config-dir <dir> server start` once, with no
  `KeepAlive`/`Restart=`. That way `bml-pgserver` is the only thing that stops
  or restarts the server, and import-profile restarts never fight a
  supervisor.
- The server outlives the launchd job because `pg_ctl` puts the postmaster in
  its own session. This was verified on macOS: the job exits 0 and the server
  stays up.
- Windows uses the HKCU `Run` key, because `schtasks /SC ONLOGON` needs admin
  rights.

## Tests

```bash
cd rust
cargo test                                   # unit + CLI tests, no server needed
BML_TEST_PG_BINDIR="/Applications/Postgres 2.app/Contents/Versions/18/bin" \
BML_TEST_PG_EXTENSION_DIRS="$HOME/Library/Application Support/Postgres/Extensions/18/pg_search" \
  cargo test -- --include-ignored            # also against a real PG 18
```

The integration tests (`#[ignore]`) use temporary folders only, never
`~/.bmlibrarian`:
- They hold a global lock, so two never race for a port.
- They stop their server on drop.
- Their data folder is named `data dir ü'q`, to cover awkward paths.

`BML_TEST_PG_EXTENSION_DIRS` is an OS path list.

CI (`.github/workflows/rust.yml`):
- runs fmt, clippy and tests on macOS arm64 and Intel, Windows, and Linux
  x86_64 and arm64
- runs the integration tests on Linux against PGDG PostgreSQL 18 + pgvector,
  without `pg_search`
