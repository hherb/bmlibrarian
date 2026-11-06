# Private PostgreSQL manager (`bml-pgserver`) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create the `rust/` Cargo workspace and CI, and a `bml-pgserver`
library plus `bml server …` CLI. Together they turn a set of PostgreSQL 18
binaries (and optional extension folders) into a private, per-user server that
is initialised, configured, running, optionally autostarted, and holding an
empty `bmlibrarian` database with its extensions.

**Architecture:** `bml-pgserver` is a synchronous library.
- The logic lives in pure functions, unit-tested without a server: port
  choice, config text, env-file text, version parsing, autostart files.
- A thin I/O layer runs `initdb`/`pg_ctl` via `std::process` and talks SQL
  through the `postgres` crate.
- `bml-cli` builds the `bml` binary with clap and calls into the library.
- Integration tests run against a real PG 18 when `BML_TEST_PG_BINDIR` is
  set, and are skipped otherwise.

**Tech Stack:** Rust 1.98 (edition 2021, `rust-version = "1.85"` like bmlib),
with these crates:
- `postgres` 0.19 (NoTls)
- `clap` 4.5 (derive)
- `serde` 1 + `serde_json` 1
- `thiserror` 2
- `getrandom` 0.3
- `sysinfo` 0.35 (`default-features = false, features = ["system"]`)
- dev: `tempfile` 3

Use these major/minor lines. Don't take any crate release newer than two
weeks.

**Spec:** `docs/superpowers/specs/2026-11-07-one-click-installer-design.md`
(pieces of work 1 and 2). **This is plan 1 of 4.** Later plans:
- 2: obtaining the pinned binaries, plus `bml-setup` / `bml setup`
- 3: the Tauri first-run screen
- 4: packaging, signing and releases

## Global Constraints

- PostgreSQL major version ≥ **18**. Refuse anything older with a clear error.
- The server listens on `127.0.0.1` only, with `scram-sha-256` auth and no
  Unix sockets (`unix_socket_directories = ''`).
- Ports to avoid: **5432–5439, 5532, 6432, 6543**, and anything **≥ 49152**.
  The default port is **5418**. When it is taken, scan upward to the next free
  port that is not avoided.
- Config dir: `~/.bmlibrarian/` by default. The CLI's `--config-dir` flag
  overrides it, and so does the `BML_CONFIG_DIR` env var. Files:
  - `bml.env`: the app role
  - `bml-admin.env`: the superuser
  - `bml-pgserver.json`: the state file

  All three are owner-only: mode 600 on Unix, `icacls` on Windows.
- **Never read or write the Python app's `~/.bmlibrarian/.env` or
  `config.json`.**
- Fixed names:
  - superuser role `bml_admin`
  - app role `bml_app`
  - database `bmlibrarian`
  - autostart label `org.bmlibrarian.pgserver`, systemd unit
    `bml-pgserver.service`, Windows Run-key value `BMLibrarianPgServer`
- Autostart runs `bml --config-dir <dir> server start` **once** at login, with
  no KeepAlive or restart-on-exit.
- Never delete or overwrite a data folder that we did not initialise.
- Every public item has a doc comment (`missing_docs = "warn"`, as in bmlib).
  Numbers and names are named constants (project golden rule 2), and every
  function is fully typed.
- Required extension: `vector` (pgvector ≥ 0.8.1). `pg_search` is optional:
  when an extension folder provides it, it is preloaded and created; when none
  does (Windows), it is skipped silently.

## Review Focus

1. **Paths with spaces, quotes or non-ASCII characters**, for the bindir
   (e.g. `/Applications/Postgres 2.app/…`) and the data folder. They must
   survive config quoting and process arguments. Tested in Tasks 3 and 7.
2. **Default port already taken**, whether by another PostgreSQL or by
   anything else. Init picks the next free, non-avoided port, and re-runs keep
   it. Tested in Tasks 2 and 7.
3. **Init interrupted part-way and run again.** It resumes with the same
   credentials. If the admin credentials file is gone but the data folder is
   initialised, it fails with an explicit error and never re-initialises.
   Tested in Task 7.
4. **A non-empty data folder we didn't create.** Init refuses, and no file in
   it is touched. Tested in Task 7.
5. **A corrupt or unreadable state file.** That is an error naming the file,
   never read as "not set up", which would invite a re-init. Tested in
   Task 5.

---

### Task 1: Workspace, crates and CI

**Files:**
- Create: `rust/Cargo.toml`
- Create: `rust/bml-pgserver/Cargo.toml`, `rust/bml-pgserver/src/lib.rs`
- Create: `rust/bml-cli/Cargo.toml`, `rust/bml-cli/src/main.rs`
- Create: `.github/workflows/rust.yml`
- Modify: `.gitignore` (append `rust/target/`)

**Interfaces:**
- Produces:
  - workspace members `bml-pgserver` (lib) and `bml-cli` (bin named `bml`)
  - shared `[workspace.package]` and `[workspace.lints]`
  - `publish = false` on both crates

- [ ] **Step 1: Write the workspace.** `rust/Cargo.toml`:
  - `resolver = "2"`
  - members `["bml-pgserver", "bml-cli"]`
  - `[workspace.package]` with `version = "0.1.0"`, `edition = "2021"`,
    `rust-version = "1.85"`
  - `[workspace.lints.rust] missing_docs = "warn"` and
    `[workspace.lints.clippy] all = "warn"`, copied from
    `../bmlib/rust/Cargo.toml`
  - `[workspace.dependencies]` for the crates in the Tech Stack

  Each crate has `[lints] workspace = true`.
- [ ] **Step 2: Write the crate skeletons.**
  - `lib.rs`: a crate doc comment only.
  - `main.rs`: a clap `Cli` with a global `--config-dir <PATH>` option and an
    empty `server` subcommand group, so that `bml --help` lists `server`.
- [ ] **Step 3: Verify.** Run `cd rust && cargo build && cargo clippy
  --all-targets -- -D warnings && cargo run -q -p bml-cli -- --help`.
  Expected: builds clean, and the help output contains `server`.
- [ ] **Step 4: Write CI.** `.github/workflows/rust.yml`, triggered on push
  and PR for paths `rust/**` and the workflow file itself.
  - Job `check`, with matrix `macos-14` (arm64), the current Intel macOS
    runner label (`macos-15-intel`, or whichever Intel label GitHub offers
    now), `windows-latest`, `ubuntu-latest` and `ubuntu-24.04-arm`. In `rust/` it runs
    `cargo fmt --check`, `cargo clippy --all-targets -- -D warnings` and
    `cargo test`.
  - Job `integration-linux`, on `ubuntu-latest`:
    - install PG 18 + pgvector from PGDG (`sudo apt-get install -y
      postgresql-common && sudo
      /usr/share/postgresql-common/pgdg/apt.postgresql.org.sh -y && sudo
      apt-get install -y postgresql-18 postgresql-18-pgvector`)
    - then run `cargo test -- --include-ignored` with
      `BML_TEST_PG_BINDIR=/usr/lib/postgresql/18/bin`
- [ ] **Step 5: Commit.** `git add rust .github .gitignore && git commit -m
  "feat(rust): workspace with bml-pgserver and bml-cli crates, CI"`

### Task 2: Port choice

**Files:**
- Create: `rust/bml-pgserver/src/port.rs` (`pub mod port` in `lib.rs`)

**Interfaces:**
- Produces:
  - `pub const DEFAULT_PORT: u16 = 5418;`
  - `pub fn is_avoided(port: u16) -> bool`
  - `pub fn choose_port(start: u16, is_free: impl Fn(u16) -> bool) -> Result<u16, PortError>`
  - `pub fn port_is_free(port: u16) -> bool`, which binds a `TcpListener` to
    `127.0.0.1:port` and drops it
  - `PortError::NoFreePort { start: u16 }`. The scan stops at the first port
    ≥ 49152; there is no other cap.

- [ ] **Step 1: Write failing tests** (in `port.rs` `#[cfg(test)]`):
  - `avoided_ports`: `is_avoided(p)` is true for 5432, 5435, 5439, 5532,
    6432, 6543, 49152 and 60000, and false for 5418, 5431, 5440 and 5531.
  - `default_when_free`: `choose_port(DEFAULT_PORT, |_| true) == Ok(5418)`.
  - `skips_taken`: with `is_free = |p| p != 5418 && p != 5419`, the result is
    `Ok(5420)`.
  - `skips_avoided_while_scanning`: `choose_port(5430, |_| true) == Ok(5430)`,
    and `choose_port(5431, |p| p != 5431) == Ok(5440)`.
  - `exhausted`: `choose_port(49150, |_| false)` gives
    `Err(PortError::NoFreePort { start: 49150 })`.
  - `real_bind`: bind a `TcpListener` on `127.0.0.1:0`, read its port, and
    assert `!port_is_free(that_port)`.
- [ ] **Step 2: Run** `cargo test -p bml-pgserver port`. Expected: FAIL
  (does not compile).
- [ ] **Step 3: Implement** the four items above.
- [ ] **Step 4: Run** `cargo test -p bml-pgserver port`. Expected: PASS.
- [ ] **Step 5: Commit.** `feat(pgserver): port choice avoiding common
  PostgreSQL ports`

### Task 3: Server config text

**Files:**
- Create: `rust/bml-pgserver/src/conf.rs`

**Interfaces:**
- Produces:
  - `pub struct ServerConfig { pub port: u16, pub extension_dirs: Vec<PathBuf>, pub preload_pg_search: bool }`
  - `pub const BML_CONF_NAME: &str = "bml.conf";`
  - `pub const INCLUDE_LINE: &str = "include 'bml.conf'";`
  - `pub fn quote_conf_value(value: &str) -> String`: wraps the value in
    single quotes and doubles any embedded `'`.
  - `pub fn render_bml_conf(cfg: &ServerConfig) -> String`
  - `pub fn render_pg_hba() -> String`
  - `pub fn ensure_include(postgresql_conf: &str) -> Option<String>`: returns
    the new text with `INCLUDE_LINE` appended on its own line, or `None` if a
    line already equals it after trimming.
  - `pub fn provides_pg_search(extension_dir: &Path) -> bool`: true when
    `<dir>/share/postgresql/extension/pg_search.control` exists.

  `render_bml_conf` emits exactly these settings, one per line, with
  path-valued settings built from `extension_dirs` in order:
  - `port = <port>`
  - `listen_addresses = '127.0.0.1'`
  - `unix_socket_directories = ''`
  - `password_encryption = 'scram-sha-256'`
  - `dynamic_library_path = '$libdir:<dir>/lib/postgresql:…'`
  - `extension_control_path = '$system:<dir>/share/postgresql:…'`
  - `shared_preload_libraries = 'pg_search'`, only if `preload_pg_search`

  The path lists are joined with `:` on Unix and `;` on Windows (the
  separator is a constant chosen by `cfg!(windows)`). On Windows, path
  separators inside values are written as `/`.

  `render_pg_hba` emits exactly:
  - `host all all 127.0.0.1/32 scram-sha-256`
  - `host all all ::1/128 scram-sha-256`

  It emits no `local` lines.

- [ ] **Step 1: Write failing tests:**
  - `quotes_single_quote`: `quote_conf_value("a'b c")` gives `"'a''b c'"`.
  - `conf_with_spaced_ext_dir`: `extension_dirs =
    ["/Users/x/Ext 18/pg_search"]` with `preload_pg_search = true`. The output
    contains `"extension_control_path = '$system:/Users/x/Ext
    18/pg_search/share/postgresql'"` and `"shared_preload_libraries =
    'pg_search'"`.
  - `conf_without_ext_dirs`: with no dirs and no preload, the output contains
    `"dynamic_library_path = '$libdir'"` and does not contain
    `shared_preload_libraries`.
  - `hba_has_no_local_or_trust`: the output contains neither `local` nor
    `trust`.
  - `include_added_once`: `ensure_include("a = 1\n")` is `Some` and ends with
    `"include 'bml.conf'\n"`, and calling `ensure_include` on that result
    gives `None`.
  - `detects_pg_search`: a tempdir with the control file returns true; an
    empty tempdir returns false.
- [ ] **Step 2: Run** `cargo test -p bml-pgserver conf`. Expected: FAIL.
- [ ] **Step 3: Implement** the items above.
- [ ] **Step 4: Run** `cargo test -p bml-pgserver conf`. Expected: PASS.
- [ ] **Step 5: Commit.** `feat(pgserver): render bml.conf and pg_hba.conf`

### Task 4: Credentials and env files

**Files:**
- Create: `rust/bml-pgserver/src/envfile.rs`

**Interfaces:**
- Produces:
  - `pub struct ConnInfo { pub host: String, pub port: u16, pub dbname: String, pub user: String, pub password: String }`
  - `pub const APP_ENV_FILE_NAME: &str = "bml.env";`
  - `pub const ADMIN_ENV_FILE_NAME: &str = "bml-admin.env";`
  - `pub const PASSWORD_BYTES: usize = 32;`
  - `pub fn generate_password() -> String`: lowercase hex of `PASSWORD_BYTES`
    bytes from `getrandom`, so 64 characters. Hex only, so it is safe inside
    SQL string literals and env files.
  - `pub fn render_env(info: &ConnInfo) -> String`
  - `pub fn parse_env(text: &str) -> Result<ConnInfo, EnvFileError>`
  - `pub fn write_private_file(path: &Path, contents: &str) -> io::Result<()>`
  - `pub fn read_conn_info(path: &Path) -> Result<Option<ConnInfo>, EnvFileError>`:
    `Ok(None)` only when the file does not exist.

  `render_env` writes exactly five lines, in this order: `POSTGRES_HOST=…`,
  `POSTGRES_PORT=…`, `POSTGRES_DB=…`, `POSTGRES_USER=…`,
  `POSTGRES_PASSWORD=…`, each ending in `\n`.

  `parse_env` ignores blank lines and lines starting with `#`, and errors on a
  missing key.

  `write_private_file` writes to `<path>.tmp` and renames it over `path`. The
  `.tmp` file is created with mode `0o600` on Unix (`OpenOptionsExt::mode`).
  On Windows, after the rename it runs `icacls <path> /inheritance:r
  /grant:r <USERNAME>:F`, and a non-zero exit is an `io::Error`.

- [ ] **Step 1: Write failing tests:**
  - `password_is_64_hex`: the length is 64, every character is in `0-9a-f`,
    and two calls differ.
  - `env_roundtrip`: `parse_env(&render_env(&info)) == Ok(info)` for a sample
    `ConnInfo { host: "127.0.0.1", port: 5418, dbname: "bmlibrarian", user:
    "bml_app", password: generate_password() }`. Derive `PartialEq, Debug,
    Clone`.
  - `env_missing_key_errors`: parsing text with no `POSTGRES_PASSWORD` gives
    `Err`.
  - `read_missing_is_none` and `read_garbage_is_err`.
  - `#[cfg(unix)] private_file_mode`: after writing, the mode `& 0o777` is
    `0o600`. Also after overwriting a file that was first created with mode
    `0o644`.
- [ ] **Step 2: Run** `cargo test -p bml-pgserver envfile`. Expected: FAIL.
- [ ] **Step 3: Implement** the items above.
- [ ] **Step 4: Run** `cargo test -p bml-pgserver envfile`. Expected: PASS.
- [ ] **Step 5: Commit.** `feat(pgserver): owner-only env files with
  generated credentials`

### Task 5: State file and config-dir resolution

**Files:**
- Create: `rust/bml-pgserver/src/state.rs`

**Interfaces:**
- Consumes: `envfile::write_private_file` (Task 4)
- Produces:
  - `#[derive(Serialize, Deserialize, Debug, Clone, PartialEq)] pub struct ServerState { pub pg_major: u32, pub bindir: PathBuf, pub data_dir: PathBuf, pub port: u16, pub extension_dirs: Vec<PathBuf> }`
  - `pub const STATE_FILE_NAME: &str = "bml-pgserver.json";`
  - `pub fn load_state(config_dir: &Path) -> Result<Option<ServerState>, StateError>`:
    `Ok(None)` only when the file is absent.
    `StateError::Corrupt { path: PathBuf, source: serde_json::Error }`, whose
    `Display` includes the path.
  - `pub fn save_state(config_dir: &Path, state: &ServerState) -> Result<(), StateError>`:
    pretty JSON, written through `write_private_file`, creating `config_dir`
    if needed.
  - `pub const CONFIG_DIR_ENV: &str = "BML_CONFIG_DIR";`
  - `pub const CONFIG_DIR_NAME: &str = ".bmlibrarian";`
  - `pub fn resolve_config_dir(flag: Option<PathBuf>, env: Option<OsString>, home: Option<PathBuf>) -> Result<PathBuf, StateError>`:
    tries the flag, then the env var, then `home/.bmlibrarian`, and returns
    `StateError::NoHome` when all three are missing. The CLI passes
    `std::env::var_os(CONFIG_DIR_ENV)` and `std::env::home_dir()`.

- [ ] **Step 1: Write failing tests:**
  - `roundtrip`, `missing_is_none`.
  - `corrupt_is_error_with_path`: writing `{not json` gives
    `Err(StateError::Corrupt{..})`, and `err.to_string()` contains
    `bml-pgserver.json`.
  - `resolve_precedence`: the flag beats the env var, which beats home; all
    three `None` gives `Err(NoHome)`.
- [ ] **Step 2: Run** `cargo test -p bml-pgserver state`. Expected: FAIL.
- [ ] **Step 3: Implement** the items above.
- [ ] **Step 4: Run** `cargo test -p bml-pgserver state`. Expected: PASS.
- [ ] **Step 5: Commit.** `feat(pgserver): state file and config-dir
  resolution`

### Task 6: Process control, version check, restart and RAM primitives

**Files:**
- Create: `rust/bml-pgserver/src/control.rs`
- Create: `rust/bml-pgserver/src/error.rs` (`PgServerError`, using
  `thiserror`, wrapping the module errors plus `Io`, `Postgres`,
  `Command { program: String, status: Option<i32>, stderr: String }`,
  `UnsupportedVersion { found: u32 }`)
- Create: `rust/bml-pgserver/tests/common/mod.rs` (integration helpers)
- Test: `rust/bml-pgserver/tests/control.rs`

**Interfaces:**
- Consumes: `ServerState` (Task 5)
- Produces:
  - `pub const MIN_PG_MAJOR: u32 = 18;`
  - `pub const SERVER_LOG_NAME: &str = "bml-server.log";`, the log file in the
    data dir
  - `pub fn tool(bindir: &Path, name: &str) -> PathBuf`: joins
    `name + std::env::consts::EXE_SUFFIX`
  - `pub fn parse_postgres_version(output: &str) -> Option<u32>`
  - `pub fn pg_major_version(bindir: &Path) -> Result<u32, PgServerError>`:
    runs `postgres --version` and rejects anything below `MIN_PG_MAJOR` with
    `UnsupportedVersion`
  - `pub enum ServerStatus { Running, Stopped, NotInitialised }`
  - `pub fn status(state: &ServerState) -> Result<ServerStatus, PgServerError>`:
    from the `pg_ctl status -D <data>` exit code (0 → Running, 3 → Stopped,
    4 → NotInitialised, anything else → `Command` error)
  - `pub fn start(state: &ServerState) -> Result<(), PgServerError>`:
    `Ok` without action if already Running, otherwise `pg_ctl start -D <data>
    -l <data>/bml-server.log -w -t 60` (the timeout seconds are a const)
  - `pub fn stop(state: &ServerState) -> Result<(), PgServerError>`: `Ok` if
    Stopped, otherwise `pg_ctl stop -D <data> -m fast -w`
  - `pub fn restart(state: &ServerState) -> Result<(), PgServerError>`: stop,
    then start. It does not use `pg_ctl restart`, because that replays
    `postmaster.opts` through a shell (see `db_import_profile.py:253`).
  - `pub fn total_memory_bytes() -> u64`, via `sysinfo`
  - Test helpers in `tests/common/mod.rs`:
    - `pub fn test_bindir() -> Option<PathBuf>`, from `BML_TEST_PG_BINDIR`
    - `pub fn test_extension_dirs() -> Vec<PathBuf>`, from
      `BML_TEST_PG_EXTENSION_DIRS`, split with `std::env::split_paths`
    - `pub fn serial() -> MutexGuard<'static, ()>`, a global lock so
      integration tests never race for ports

  All arguments go through `Command::arg` (never through a shell), so paths
  with spaces need no quoting.

- [ ] **Step 1: Write failing unit tests:**
  - `parses_postgres_app`:
    `parse_postgres_version("postgres (PostgreSQL) 18.1 (Postgres.app)") ==
    Some(18)`
  - `parses_debian`: `"postgres (PostgreSQL) 18.0 (Debian 18.0-1.pgdg24.04+1)"`
    gives `Some(18)`
  - `parses_beta`: `"postgres (PostgreSQL) 19beta1"` gives `Some(19)`
  - `rejects_garbage`: `"hello"` gives `None`
  - `memory_positive`: `total_memory_bytes() > 0`
  - `#[cfg(windows)] tool_has_exe`
- [ ] **Step 2: Write the failing integration test** `start_stop_idempotent`,
  marked `#[ignore]` and returning early when `test_bindir()` is `None`:
  - run `initdb -D <tmp>/data -U bml_admin --auth=trust` directly (test-only
    setup)
  - build a `ServerState` on a port from `choose_port(DEFAULT_PORT,
    port_is_free)` and write `bml.conf` with `listen_addresses` and the port
  - assert `status == Stopped`
  - call `start` twice, then assert `Running`
  - call `stop` twice, then assert `Stopped`
  - call `restart` from Stopped, assert `Running`, then `stop`
- [ ] **Step 3: Run** `cargo test -p bml-pgserver`. Expected: the unit tests
  FAIL.
- [ ] **Step 4: Implement** the items above.
- [ ] **Step 5: Run** `cargo test -p bml-pgserver` (expected PASS), then
  `BML_TEST_PG_BINDIR="/Applications/Postgres 2.app/Contents/Versions/18/bin"
  cargo test -p bml-pgserver -- --include-ignored` (expected PASS). This is
  the owner's local PG 18.1; the space in the path is deliberate.
- [ ] **Step 6: Commit.** `feat(pgserver): pg_ctl control, version check,
  restart and RAM detection`

### Task 7: `init`: the resumable setup of the private server

**Files:**
- Create: `rust/bml-pgserver/src/init.rs`
- Test: `rust/bml-pgserver/tests/init.rs`

**Interfaces:**
- Consumes: everything from Tasks 2–6
- Produces:
  - `pub struct InitRequest { pub bindir: PathBuf, pub data_dir: PathBuf, pub extension_dirs: Vec<PathBuf> }`
  - `pub struct InitOutcome { pub state: ServerState, pub pg_search: bool, pub created: bool }`.
    `created` is false when everything already existed.
  - `pub fn init(req: &InitRequest, config_dir: &Path) -> Result<InitOutcome, PgServerError>`
  - New `PgServerError` variants:
    - `DataDirNotEmpty { path }`
    - `AdminCredentialsLost { data_dir, admin_env }`
    - `ExtensionUnavailable { name }`
    - `StateMismatch { field: &'static str }`, raised when the state file
      names a different data dir or bindir than the request
  - Constants: `ADMIN_ROLE = "bml_admin"`, `APP_ROLE = "bml_app"`,
    `DATABASE = "bmlibrarian"`, `HOST = "127.0.0.1"`,
    `REQUIRED_EXTENSIONS = ["vector"]`, `OPTIONAL_EXTENSIONS =
    ["pg_search"]`
  - `pub fn connect(info: &ConnInfo) -> Result<postgres::Client, PgServerError>`
    (NoTls)

- [ ] **Step 1: Write the failing integration tests.** All are `#[ignore]`,
  take `serial()`, skip without `test_bindir()`, and use a tempdir named
  `"data dir ü'q"`:
  - `fresh_init`:
    - `init` returns `created == true`
    - `status == Running`
    - connecting with `bml.env` as `bml_app` to `bmlibrarian`,
      `SELECT extname FROM pg_extension` includes `vector`, plus `pg_search`
      when `test_extension_dirs()` provides it
    - `bml-admin.env` and `bml.env` exist; on Unix both have mode 600
    - `state.port` is not avoided
  - `rerun_is_noop`: a second `init` with the same request returns
    `created == false`, the same port, and byte-identical env files.
  - `resumes_after_kill`: run `init`, `stop`, delete `bml.env` and drop the
    `bml_app` role through an admin connection, then `init` again. The role
    and file are recreated, and `bml_app` can log in.
  - `admin_lost_refuses`: run `init`, `stop`, delete `bml-admin.env`. The
    next `init` gives `Err(AdminCredentialsLost{..})`, and `PG_VERSION` is
    still in the data dir.
  - `foreign_dir_refused`: put a data dir containing `keep.txt` in place. The
    result is `Err(DataDirNotEmpty{..})`, and `keep.txt` is unchanged.
  - `port_taken_moves_on`: hold a `TcpListener` on
    `choose_port(DEFAULT_PORT, port_is_free)`, run `init`, and check
    `state.port` is a different, non-avoided port.

  Every test calls `stop` in a drop guard so no server outlives it.
- [ ] **Step 2: Run** with `--include-ignored` and the local bindir.
  Expected: FAIL.
- [ ] **Step 3: Implement `init`.** Each step checks before acting, so the
  whole call is idempotent. In order:
  1. `pg_major_version(bindir)`.
  2. Load the state. If there is one, its `data_dir`/`bindir` must equal the
     request's (otherwise `StateMismatch`), and its port is reused.
     Otherwise, choose a port.
  3. Inspect the data dir:
     - `PG_VERSION` present means it is initialised
     - missing or empty means it is free
     - anything else is `DataDirNotEmpty`
  4. Admin credentials:
     - if `bml-admin.env` exists, reuse it
     - else if the data dir is initialised, `AdminCredentialsLost`
     - else generate a password and write `bml-admin.env` **before** `initdb`,
       so the password can never be lost
  5. If not initialised, run `initdb -D <data> -U bml_admin
     --pwfile=<config_dir>/.pwfile.tmp --auth=scram-sha-256 --encoding=UTF8
     --locale-provider=builtin --builtin-locale=C.UTF-8`. The pwfile is
     written through `write_private_file` and removed afterwards, even when
     `initdb` fails.
  6. Write `bml.conf` (preload `pg_search` if any extension dir
     `provides_pg_search`) and `pg_hba.conf`, and `ensure_include` on
     `postgresql.conf`. Write each file only if its content differs.
  7. `save_state`.
  8. `start`.
  9. As admin, connected to the `postgres` database:
     - create `bml_app` with `LOGIN PASSWORD '<hex>'` if it is absent from
       `pg_roles`
     - otherwise, when `bml.env` is missing, generate a new password and
       `ALTER ROLE … PASSWORD`
     - create the database `bmlibrarian` `OWNER bml_app` if it is absent
       from `pg_database`
  10. As admin, connected to `bmlibrarian`, for each required extension:
      if it is not in `pg_available_extensions`, `ExtensionUnavailable`;
      otherwise `CREATE EXTENSION IF NOT EXISTS`. Do the same for optional
      extensions, but only when they are available.
  11. Write `bml.env` if it is missing.

  `created` is true if any of steps 5, 9 or 11 did something.
- [ ] **Step 4: Run** `cargo test -p bml-pgserver` and the ignored suite with
  `BML_TEST_PG_BINDIR="/Applications/Postgres 2.app/Contents/Versions/18/bin"
  BML_TEST_PG_EXTENSION_DIRS="$HOME/Library/Application
  Support/Postgres/Extensions/18/pg_search"`. Expected: all PASS, with
  `pg_search` present in `fresh_init`. If `pg_search` doesn't load through
  `extension_control_path`/`dynamic_library_path`, fix `render_bml_conf` (and
  its Task 3 test) so it does. The PG 18 docs on those two settings are the
  reference.
- [ ] **Step 5: Commit.** `feat(pgserver): resumable init of the private
  server, roles, database and extensions`

### Task 8: Autostart at login

**Files:**
- Create: `rust/bml-pgserver/src/autostart.rs`

**Interfaces:**
- Produces:
  - `pub const LAUNCH_AGENT_LABEL: &str = "org.bmlibrarian.pgserver";`
  - `pub const SYSTEMD_UNIT_NAME: &str = "bml-pgserver.service";`
  - `pub const WINDOWS_RUN_VALUE: &str = "BMLibrarianPgServer";`
  - `pub fn start_args(exe: &Path, config_dir: &Path) -> Vec<OsString>`:
    `[exe, "--config-dir", config_dir, "server", "start"]`
  - `pub fn render_launch_agent(exe: &Path, config_dir: &Path) -> String`:
    a plist with `Label`, `ProgramArguments` (one `<string>` per arg,
    XML-escaped), `RunAtLoad` true, and **no** `KeepAlive`
  - `pub fn render_systemd_unit(exe: &Path, config_dir: &Path) -> String`:
    `Type=oneshot`, `RemainAfterExit=yes`, `ExecStart=` (the start args,
    each double-quoted) and `ExecStop=` (the same with `stop`),
    `WantedBy=default.target`, with no `Restart=`
  - `pub fn windows_run_command(exe: &Path, config_dir: &Path) -> String`:
    every argument double-quoted
  - `pub fn enable(exe: &Path, config_dir: &Path) -> Result<(), PgServerError>`
  - `pub fn disable() -> Result<(), PgServerError>`

  Per platform:
  - **macOS:** write `~/Library/LaunchAgents/<label>.plist`, then `launchctl
    bootstrap gui/<uid> <plist>`, treating "already loaded" as success.
    `disable` runs `launchctl bootout gui/<uid>/<label>` and removes the file.
  - **Linux:** write `~/.config/systemd/user/<unit>`, then `systemctl --user
    daemon-reload && systemctl --user enable <unit>`.
  - **Windows:** `reg add HKCU\Software\Microsoft\Windows\CurrentVersion\Run
    /v <value> /t REG_SZ /d <cmd> /f`. Use the Run key, not a Scheduled
    Task, because `schtasks /SC ONLOGON` needs admin rights.

  Get the uid via `id -u`; don't add a `libc` dependency.

- [ ] **Step 1: Write failing tests** for the pure renderers, using
  `exe = "/Applications/BML App/bml"` and `config_dir = "/Users/a b/.bmlibrarian"`:
  - `plist_runs_once`: contains `<key>RunAtLoad</key>` followed by `<true/>`,
    contains `<string>/Users/a b/.bmlibrarian</string>`, and does not contain
    `KeepAlive`.
  - `plist_escapes_xml`: a config dir containing `&` renders as `&amp;`.
  - `unit_oneshot_no_restart`: contains `Type=oneshot` and
    `RemainAfterExit=yes`; does not contain `Restart=`; contains `"server"
    "start"`.
  - `windows_cmd_quotes`: `windows_run_command(r"C:\Program Files\BML\bml.exe",
    r"C:\Users\a b\.bmlibrarian")` gives `"\"C:\\Program Files\\BML\\bml.exe\"
    \"--config-dir\" \"C:\\Users\\a b\\.bmlibrarian\" \"server\" \"start\""`.
- [ ] **Step 2: Run** `cargo test -p bml-pgserver autostart`. Expected: FAIL.
- [ ] **Step 3: Implement** the items above.
- [ ] **Step 4: Run** `cargo test -p bml-pgserver autostart`. Expected:
  PASS. `enable`/`disable` are verified manually in Task 9, Step 4.
- [ ] **Step 5: Commit.** `feat(pgserver): per-user autostart at login
  without keep-alive`

### Task 9: `bml server` CLI

**Files:**
- Modify: `rust/bml-cli/src/main.rs`
- Create: `rust/bml-cli/src/server.rs`
- Test: `rust/bml-cli/tests/server_cli.rs`

**Interfaces:**
- Consumes:
  - `resolve_config_dir`, `load_state` (Task 5)
  - `status`/`start`/`stop`/`restart` (Task 6)
  - `init`, `InitRequest`, `connect` (Task 7)
  - `read_conn_info`, `APP_ENV_FILE_NAME` (Task 4)
  - `enable`/`disable` (Task 8)
- Produces these commands:
  - `bml [--config-dir DIR] server init --bindir DIR --data-dir DIR
    [--extension-dir DIR]...`
  - `bml [--config-dir DIR] server start|stop|restart|status`
  - `bml [--config-dir DIR] server autostart enable|disable`

  `status` exit codes are consts:
  - `0`: running and healthy
  - `1`: stopped or unhealthy
  - `2`: not set up, meaning no state file

  `status` prints these plain lines:
  - `Server: running on 127.0.0.1:<port>` / `stopped` / `not set up (run "bml
    server init")`
  - `Data: <data_dir>`
  - `Extensions: vector, pg_search`, from a `bml_app` connection to
    `bmlibrarian`. When that connection fails it prints `Health: cannot
    connect: <error>` and exits 1.

  Any other error prints `error: <message>` to stderr and exits 1, with no
  panics.

- [ ] **Step 1: Write failing tests.** Use
  `std::process::Command::new(env!("CARGO_BIN_EXE_bml"))` and a tempdir
  config dir:
  - `status_not_set_up`: exit code 2, and stdout contains `not set up`.
  - `corrupt_state_errors`: with `bml-pgserver.json` set to `{x`, the exit
    code is 1 and stderr contains `bml-pgserver.json`.
  - `#[ignore]` `init_status_stop` (skips without `BML_TEST_PG_BINDIR`):
    - `server init` → 0
    - `server status` → 0, and stdout contains `Extensions: vector`
    - `server stop` → 0
    - `server status` → 1
- [ ] **Step 2: Run** `cargo test -p bml-cli`. Expected: FAIL.
- [ ] **Step 3: Implement** `server.rs` with the subcommands. `autostart
  enable` passes `std::env::current_exe()`.
- [ ] **Step 4: Run** the tests (expected PASS). Then on the Mac, verify
  manually:
  1. `bml --config-dir /tmp/bmlcfg server init --bindir "/Applications/Postgres
     2.app/Contents/Versions/18/bin" --data-dir /tmp/bmldata` →
     `server autostart enable`
  2. `launchctl print gui/$(id -u)/org.bmlibrarian.pgserver` shows the job
  3. `server stop`, then `launchctl kickstart gui/$(id -u)/org.bmlibrarian.pgserver`
     → `server status` exit 0
  4. `server autostart disable` → `server stop` → remove both `/tmp`
     folders

  This uses `/tmp` paths, never `~/.bmlibrarian`.
- [ ] **Step 5: Commit.** `feat(cli): bml server
  init/start/stop/restart/status/autostart`

### Task 10: Documentation and plan updates

**Files:**
- Create: `doc/users/private_postgres_server.md`: what the private server is;
  the `bml server …` commands; where files live; how to stop autostart; and
  that it never touches another PostgreSQL or the Python `.env`
- Create: `doc/developers/rust_pgserver.md`:
  - module map
  - init steps and their idempotency
  - the config file contract (the `bml.conf` include, extension path
    settings)
  - how to run the integration tests (`BML_TEST_PG_BINDIR`,
    `BML_TEST_PG_EXTENSION_DIRS`)
- Modify: `doc/planning/rust/implementation_plan.md`:
  - add `bml-pgserver`, `bml-setup` and `bml-app` to the workspace table
  - note Tauri pulled forward
  - note the Windows tsvector fallback
  - note the fresh-install migration history in `rust/migrations/`
  - link the spec
- Modify: `CLAUDE.md`, the Development Commands list: `cd rust && cargo
  test`, `cargo test -- --include-ignored` with `BML_TEST_PG_BINDIR`, and the
  `bml server …` commands

- [ ] **Step 1: Write the docs and edits above.**
- [ ] **Step 2: Verify.** `cd rust && cargo fmt --check && cargo clippy
  --all-targets -- -D warnings && cargo test` passes, and `cargo doc
  --no-deps` produces no `missing_docs` warnings.
- [ ] **Step 3: Commit.** `docs: private PostgreSQL server user and developer
  guides; Rust plan updated`
