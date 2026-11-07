# `bml-pgserver`: the private PostgreSQL manager

The first crate of the Rust port (`rust/`), written for the one-click installer
(spec: `docs/superpowers/specs/2026-11-07-one-click-installer-design.md`; plan:
`docs/superpowers/plans/2026-11-07-rust-pgserver.md`). Its API is synchronous: it
uses the `postgres` crate's blocking client (which runs tokio internally) and
has no async code of its own. The logic lives in pure functions, and a thin I/O layer runs
`initdb`/`pg_ctl` through `std::process::Command` (never a shell) and talks SQL
through the `postgres` crate.

## Modules

| Module | Responsibility |
|---|---|
| `port` | `DEFAULT_PORT` (5418), `is_avoided` (5432–5439, 5532, 6432, 6543, ≥ 49152), `choose_port(start, is_free)`, `port_is_free` (binds `127.0.0.1:port` **and** a loopback connect must be refused: on macOS a loopback bind succeeds while another process listens on `0.0.0.0`). Only "address in use" (and, on Windows, an excluded port range's access-denied) counts as taken; any other bind error stops the scan with `PortError::Probe`, naming the port, instead of ending in "no free port" |
| `conf` | `render_bml_conf`, `render_pg_hba`, `ensure_include`, `quote_conf_value`, `extension_control_dir`, `provides_pg_search` |
| `envfile` | `ConnInfo`; `render_env` / `parse_env` (`EnvParseError`) / `read_conn_info` (`EnvFileError`: unreadable, or `Invalid` with the path and the parse error); `generate_password` (64 hex characters; `parse_env` accepts only hex passwords); `write_private_file` (atomic; mode 600, or `icacls` on the temp file before the rename); `Debug` hides the password |
| `state` | `ServerState` ↔ `bml-pgserver.json` (state files with the retired `pg_major` field still load); `resolve_config_dir(flag, env, home)` (made absolute) |
| `control` | `pg_major_version` (≥ 18), `status` / `start` / `stop` (idempotent) / `restart`, `total_memory_bytes` (an error rather than 0 when the system does not report it). `start` and `stop` refuse a missing or unreadable data folder (`DataDirUnavailable`); a failed start quotes the end of `bml-server.log` (`StartFailed`) |
| `init` | `init(&InitRequest, config_dir)`, the resumable setup; `connect(&ConnInfo)` (errors are `Connect`, naming role, database and address) |
| `autostart` | LaunchAgent / `systemd --user` / HKCU `Run` renderers, `enable` / `disable` |
| `error` | `PgServerError`; database errors show the server's message, detail, `SQLSTATE` and hint |

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
after an interruption between steps. A kill during `initdb` itself can leave a
half-written data folder, which is refused (`IncompleteDataDir`) rather than
resumed.

0. **Path check**, before anything is created:
   - Every path is made absolute (`std::path::absolute`), because it is saved
     and used later from other working directories (and from autostart).
   - Paths must be valid Unicode (`NonUnicodePath`): they are written into
     `bml.conf` and the JSON state file.
   - Unix: the bin folder and data folder may not contain `"`, `$`, a backtick
     or `\`. `pg_ctl` starts the server through `/bin/sh -c "…"`, so a folder
     with them could be initialised but never started (`UnsafePath`).
   - Each extension folder must have `share/postgresql/extension` and must not
     contain the path-list separator (`:`, or `;` on Windows):
     `BadExtensionDir`.
1. **Version check.** `postgres --version` must report ≥ 18.
2. **Port.** Take it from the state file. If there is no state file, use
   `choose_port`. A state file naming a different data or bin folder is
   `StateMismatch`, which shows both paths.
3. **Data folder.** "Finished" below means `bml.env` exists: it is written
   last, so a setup once completed.
   - `PG_VERSION` present: it's ours if it holds our `bml.conf`, or if our
     state file names it and setup finished. Named by our state file but with
     neither, our first run was killed during or right after `initdb`:
     `IncompleteDataDir`. Any other PostgreSQL data folder is
     `ForeignDataDir`, and nothing in it is touched, even if a leftover
     `bml-admin.env` exists.
   - Missing or empty, named by our state file, setup finished:
     `DataDirMissing`. This is almost always an unmounted disk, so `init`
     never creates a new, empty server there. To start over on purpose,
     delete `bml-pgserver.json`.
   - Missing or empty otherwise: free to initialise.
   - Anything else: `IncompleteDataDir` if our state file names it and setup
     never finished, else `DataDirNotEmpty`. Nothing is touched.
4. **Admin credentials.**
   - `bml-admin.env` is reused when it exists.
   - If it is missing and the data folder is initialised: `AdminCredentialsLost`,
     with no re-initialisation.
   - Otherwise a password is generated and written **before** `initdb`.
   The state file is saved here, **before** `initdb`. It is what lets a
   repeated run recognise an initialised folder as ours.
5. **`initdb`.** `-U bml_admin --pwfile=<private tmp> --auth=scram-sha-256
   --encoding=UTF8 --locale-provider=builtin --builtin-locale=C.UTF-8`. The
   pwfile is removed even if `initdb` fails (initdb's own error is reported
   first). The builtin C.UTF-8 locale behaves the same on every OS.
6. **Server config.** Write `bml.conf`, `pg_hba.conf` and the include line,
   each only if its content differs.
7. **Start.** Start the server, or restart it if it was running and step 6
   changed something.
8. **Role and database.** Create the `bml_app` role (with `bml.env`'s
   password, or a new one if `bml.env` is missing) and the `bmlibrarian`
   database, owned by `bml_app`, if they are missing.
9. **Extensions.** `CREATE EXTENSION IF NOT EXISTS vector`, failing with
   `ExtensionUnavailable` if it isn't available, plus `pg_search` when
   preloaded.
10. **App login check.** Connect as `bml_app`. If the password is refused
    (`SQLSTATE 28P01`: `bml.env` was lost, or the data folder came from
    another machine), set it with `ALTER ROLE` and connect again. A refused
    attempt leaves one "password authentication failed" line in the server
    log.
11. **App credentials.** Write `bml.env`.

`CREATE/ALTER ROLE` is sent a SCRAM-SHA-256 verifier
(`postgres_protocol::password::scram_sha_256`), never the password, so the
password cannot reach the server log. The verifier is base64 plus `$` and
`:`, so it is safe inside the SQL literal. Role and database names are
constants.

## Server control and autostart

- `restart` is stop + start, not `pg_ctl restart`, so a restart uses the
  same `pg_ctl start` arguments (log file, wait timeout) as `start` rather
  than whatever `postmaster.opts` recorded.
- Autostart runs `bml --config-dir <dir> server start` once, with no
  `KeepAlive`/`Restart=`, so nothing restarts the server and import-profile
  restarts never fight a supervisor. Per platform:
  - macOS: `enable` also starts the server at once (`RunAtLoad`). Output goes
    to `bml-autostart.log` in the config folder. `launchctl bootout` (before
    `bootstrap`, and in `disable`) may only fail with "not loaded" (exit 3 or
    113) or "unloading" (36); anything else is an error. `bootout` returns
    before the job is unloaded, so `bootstrap` is retried for up to 2 s while
    it fails with `5: Input/output error`.
  - Linux: the unit's `ExecStop` stops the server when the user's systemd
    manager stops at logout. Output goes to the journal. Arguments are quoted
    with `%` → `%%` and `$` → `$$`.
  - Windows: output is lost (issue #397). Trailing backslashes in
    arguments are doubled before the closing quote.
- There is one autostart entry per user; enabling for another config folder
  replaces it. The entry records `current_exe()`, so enable it from an
  installed `bml`, not a `cargo run` build in `target/debug`.
- `bml server autostart enable` refuses (exit 2) when nothing is set up.
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
`~/.bmlibrarian`. On CI (`CI` set) they fail rather than skip when
`BML_TEST_PG_BINDIR` is missing. The `bml-pgserver/tests/init.rs` tests also:
- hold a per-binary lock, so two never race for a port;
- stop their server on drop, before the temp folder is deleted;
- use a data folder named `data dir ü'q`, to cover awkward paths.

`tests/control.rs` and the CLI's `init_status_stop` stop their server on drop
too.

`bml-pgserver/tests/refusals.rs` (Unix, no server needed, runs in plain
`cargo test`) uses a fake bin folder whose `postgres` prints a version and
whose `initdb` fails. It covers `UnsupportedVersion`, `ForeignDataDir`,
`StateMismatch`, `AdminCredentialsLost`, `IncompleteDataDir`, and the removal
of `.pwfile.tmp` after a failed `initdb`. It is a single test on purpose:
writing a script while another test thread forks can make Linux refuse to run
it ("text file busy").

On macOS, a unit test runs `plutil -lint` on the rendered LaunchAgent.

`BML_TEST_PG_EXTENSION_DIRS` is an OS path list.

CI (`.github/workflows/rust.yml`):
- runs fmt, clippy (`-D warnings`) and tests on macOS arm64 (`macos-15`) and
  Intel, Windows, and Linux x86_64 and arm64
- runs the integration tests on Linux against PGDG PostgreSQL 18 + pgvector,
  and on macOS (`macos-15`) against Homebrew `postgresql@18` + `pgvector`;
  neither has `pg_search`, so its preload is only tested locally
