# One-click installer (Rust + Tauri) with a private PostgreSQL

**Date:** 2026-11-07
**Status:** Draft (design), awaiting approval
**Scope:**
- the first Rust code of the BMLibrarian port: Cargo workspace, CI, a
  private-PostgreSQL manager, setup logic, and a Tauri app shell whose first
  screen is the installer/first-run setup
- packaging as a macOS `.dmg`, a Windows `.exe` and a Linux bootstrap script

**Related:** `doc/planning/rust/implementation_plan.md` (the Rust plan; this
work pulls part of Phase B step 1 and the start of Phase F forward).

## Intent

A less tech-savvy user (clinician, researcher) should download one file,
double-click it, and end up with everything BMLibrarian needs, preconfigured.
They should never have to learn that PostgreSQL, pgvector, pg_search, Ollama or
model files exist.

Today that is impossible. The only setup path is the Python `setup_wizard.py`,
run from a source checkout via `uv`. It assumes PostgreSQL is already installed
and running, and that the user knows its superuser credentials. If any
extension is missing it stops with "please install them before proceeding."

The owner decided that this installer is the **first piece of the Rust
implementation**, and that it targets the **Rust-plan database layout
throughout**:
- `halfvec(256)` vectors, embedded in-process with llama.cpp
- `pg_search` BM25 lexical search
- PostgreSQL 18

That makes the current Python app's heavy dependencies (torch, `llama-cpp-python`,
Playwright, …) and its `plpython3u` requirement irrelevant to the installer.
The owner also decided to bring in **Tauri now**: the installer is the first
screen of the Tauri desktop app that the Rust plan's Phase F grows into.

Primary platforms are **macOS and Windows**; Linux is supported with a lighter
touch, because Linux users are generally more tech-savvy.

## Goals

1. **One thing to double-click:**
   - macOS: a `.dmg`, signed with the owner's Developer ID and notarised
   - Windows: an `.exe`, signed with the owner's code-signing certificate
   - Linux: a small download-and-run bootstrap script

   Distribution is direct download, **not** through the Mac App Store or the
   Microsoft Store. Store sandboxing forbids installing PostgreSQL, registering
   background services or installing Ollama.

2. **Check first, install only what's missing.** Setup inspects each
   requirement, keeps what is already present *and usable*, and installs the
   rest:

   | Requirement | Usable when | Otherwise |
   |---|---|---|
   | PostgreSQL 18 with pgvector (≥ 0.8.1, for `halfvec`) and, on macOS/Linux, `pg_search` available **and** in `shared_preload_libraries` | running, and the user can supply superuser credentials | install the **private PostgreSQL** (below) |
   | Ollama | responding at the configured host | install Ollama |
   | Generation models `gpt-oss:20b`, `medgemma4B_it_q8:latest` | pulled in Ollama | pull them |
   | Embedding model: arctic-embed-l-v2.0, F16 GGUF, pinned by sha256 (Rust plan, `bml-index`) | file present with the right checksum | download and verify it |
   | BMLibrarian app | installed and current | install / update |

   No Python and no `uv` are needed.

3. **Private PostgreSQL** for everyone whose existing server is absent or
   unusable. For the target user that is almost everyone, and it is the safe
   default. It must:
   - run as the user, with **no admin rights** needed
   - listen on a **non-standard port**, so a PostgreSQL the user (or another
     program) installs later on 5432 never collides with it
   - bind to `127.0.0.1` only, with `scram-sha-256` authentication
   - ship pgvector everywhere, and `pg_search` on macOS and Linux, preloaded
   - keep its data in a folder **the user picks**, defaulting under
     `~/.bmlibrarian/`, because a full PubMed mirror may only fit on an
     external disk
   - start at user login without admin rights: a per-user LaunchAgent on
     macOS, a per-user logon Scheduled Task on Windows (or the per-user
     `HKCU\…\Run` key if the task needs admin on some configurations), and a
     `systemd --user` unit on Linux. It serves the app, the `bml` CLI and
     long-running imports, not only while the GUI is open.
   - work with the import profile, which borrows RAM during bulk imports and
     restarts the server via `pg_ctl` with the data directory. It needs to
     know the private server's bin and data directories.

4. **Windows lexical-search fallback.** `pg_search` does not run on Windows:
   ParadeDB inherits pgrx's lack of Windows support and ships no Windows
   binaries. On Windows the lexical index uses PostgreSQL's built-in text
   search (tsvector + GIN), behind the same `bml-search` interface. Everything
   else is identical across platforms.

5. **No limits on corpus size.** Users may mirror only medRxiv, all of PubMed,
   or PubMed from a given year onwards. Setup neither restricts nor presizes
   for any choice, beyond asking where the data lives.

6. **Models:** always install the approved models. When RAM or free disk is
   below what they need, show a plain-language warning and continue. **Never
   substitute different models.**

7. **Headless setup.** The same setup logic runs without the GUI
   (`bml setup …`), so the Linux bootstrap script and developers can use it.
   The GUI is a front end to that logic, not a second implementation.

## Non-goals

- Restricting or recommending a corpus size.
- Docker, a VM or WSL2 for the database.
- Managing, upgrading or reconfiguring a PostgreSQL the user already had. We
  use it as-is or ignore it.
- Auto-selecting smaller models for weak hardware.
- App-store distribution of any kind.
- Supporting the current Python app's database layout on a fresh install.
- Native Linux packages (`.deb`/`.rpm`). The bootstrap script is enough.
- The rest of the Tauri GUI (search, review, …). This work only starts the
  app shell.

## Anti-goals: failure even if it "works"

- **Touching a pre-existing PostgreSQL** in any way, including its data
  directory, config, port, preload libraries or service registration.
- **Changing the Python app's `~/.bmlibrarian/.env` or `config.json` at
  all.** Existing users, including the developer's own machine
  (`knowledgebase` on 5432, `bmlibrarian_dev` on :5532), must keep their
  configuration.
- Requiring admin/root rights on the default path. The Linux Ollama install
  is the one stated exception (below).
- A step that silently fails and leaves a half-working install. Every failure
  is reported in plain language with what to do next. Re-running setup
  resumes or repairs.
- Exposing the private PostgreSQL to the network.
- Deleting the user's database folder without an explicit confirmation, ever.

## Constraints

- **PostgreSQL 18** is the minimum (Rust plan, decided 2026-10-13).
- **Rust workspace at `rust/` in this repository** (Rust plan, decided
  2026-10-13), so that migrations, the Python app and the Rust code change
  together. It does not exist yet; this work creates it. Use bmlib Rust
  (`../bmlib/rust`) for shared functionality, and contribute generic pieces
  back.
- **The Python app's configuration (`~/.bmlibrarian/.env`, read by
  `src/bmlibrarian/env_loader.py`) is left untouched.** The Python and Rust
  stacks need databases with different layouts, so the Rust stack has its own
  files (see Decisions). It follows the same rules: an explicitly named
  missing file is an error, never a silent fallback. Every credentials file is
  owner-only (600, or the Windows ACL equivalent).
- **Schema comes from migrations, not from setup.** Setup creates the server,
  roles, the database and the extensions. The schema is applied by the Rust
  migrations runner (`bml-db`).
- **Fresh installs start a new migration history with no `plpython3u`**
  (owner, 2026-11-07). This replaces the Rust plan's "`bml-db` reads
  `migrations/`" for fresh installs.
  - The Rust-layout history lives in its own folder, `rust/migrations/`, and
    starts from a new baseline.
  - The Python history (`baseline_schema.sql` + `migrations/`) is not used on
    fresh installs and is left unchanged for existing databases.
  - Rust-layout migrations detect whether `pg_search` is available
    (`pg_available_extensions`) and create the tsvector fallback otherwise.
  - Migrations stay idempotent (golden rule 15) and contain no tracking code
    (rule 16).
- Every downloaded artefact (PostgreSQL, extensions, Ollama installer, GGUF)
  is pinned by version **and** checksum, and verified before use.
- **Licensing:** PostgreSQL and pgvector are under the PostgreSQL licence.
  `pg_search` is AGPL-3.0: the owner accepts offering its source, so releases
  include or link the exact source. bmlib is already AGPL-3.0-or-later.
- **macOS notarisation** requires every bundled executable and dylib
  (PostgreSQL binaries and extensions included) to be signed with the
  hardened runtime.

## Decisions

### Made by the owner

- The target user is non-technical; macOS and Windows first, Linux too.
- `.dmg` on macOS, `.exe` on Windows, a bootstrap script on Linux.
- Check what's installed; install only what's missing or unusable.
- Private PostgreSQL on a non-standard port.
- No restriction on corpus size.
- Always install the approved models; warn when the hardware is
  insufficient.
- The installer is written in Rust, as the first piece of the Rust port.
- Rust-plan database layout throughout.
- On Windows, fall back to built-in text search instead of `pg_search`.
- Tauri is brought in now.
- Offering `pg_search` source is fine.
- Signing: the owner has a macOS Developer ID certificate and a Windows
  code-signing certificate. **Signing happens on the owner's machine, not in
  CI.**
  - CI builds and tests unsigned artefacts.
  - A local release script then signs every bundled executable and dylib
    (macOS: hardened runtime, plus the entitlements PostgreSQL needs to load
    extension dylibs), notarises and staples the `.dmg`, and signs the `.exe`.
  - It publishes the signed artefacts and checksums to GitHub Releases.
  - No signing keys or Apple credentials are stored in GitHub.
- Fresh installs start a new migration history with no `plpython3u`.
- The owner understands that target users have nothing to *use* until the
  app gains search (Rust Phase C) and its GUI. The installer is built now.
  When it ships to non-technical users is a later decision.

### Made by Claude (open to correction)

- **Where this work ends:** a fresh install has the private server running and
  autostarting, plus an empty database with its roles and extensions
  (`vector`, plus `pg_search` or nothing extra on Windows). It also has
  Ollama, the models and the GGUF in place, and `bml server status`
  reports healthy. The `bml-db` migrations runner and the Rust-layout baseline
  in `rust/migrations/` come with Phase B.

- **Crates** (added to the Rust plan's workspace table):
  - `bml-pgserver`: obtains, initialises, configures, starts/stops and
    registers the private server; chooses the port. It is kept separate from
    `bml-db`, which is the client-side pool and migrations runner.
  - `bml-setup`: requirement checks and install steps as idempotent,
    resumable steps that emit progress events. It is UI-free.
  - `bml-app`: the Tauri app; its first-run screen drives `bml-setup`.
  - `bml-cli` gains `bml setup …` and `bml server status|start|stop`.

  Pure functions (port choice, config file generation, hardware checks,
  requirement verdicts) carry the logic, so most of it is unit-testable
  without a server.
- **Port:** a fixed default outside common PostgreSQL ports. Avoid 5432–5439,
  5532 (the developer's PG 18), 6432 and 6543 (pgbouncer), and the OS
  ephemeral range (≥ 49152). If the default is taken, use the next free port
  upward. The chosen port is written to `~/.bmlibrarian/bml.env`.
- **Rust stack configuration, separate from Python's:**
  - `~/.bmlibrarian/bml.env` holds the app role's connection
    (`POSTGRES_HOST/PORT/DB/USER/PASSWORD`). `BML_ENV_FILE` selects another
    file.
  - `~/.bmlibrarian/bml-admin.env` holds the superuser credentials, used only
    for migrations, `CREATE EXTENSION` and the import profile. Both files are
    owner-only.
  - The OS keychain is not used: it has no headless path on Linux.
  - This follows the Rust plan's §8 split between an unprivileged app role
    and an admin connection.
  - Python's `~/.bmlibrarian/.env` is never read or written by setup, so
    existing Python users (including the owner's `knowledgebase` /
    `bmlibrarian_dev`) are unaffected by construction.
- **Credentials:** setup generates the PostgreSQL superuser and app-user
  passwords. The user never sees or types them.
- **"Usable" existing PostgreSQL:** version 18, pgvector ≥ 0.8.1 available,
  `pg_search` available and preloaded (macOS/Linux), and superuser
  credentials supplied by the user. Anything less means the private server is
  installed alongside it, and the existing one is ignored. We never edit an
  existing server's `shared_preload_libraries`.
- **Using an existing usable server:** setup creates a *new* dedicated
  database and roles. It refuses names that already exist rather than reusing
  them, and it never opens, alters or reads any other database there.
  Creating new objects is the only change made to an existing server.
- **Server supervision:** the login autostart entry runs
  `bml server start` once. It does not keep the server alive (no `KeepAlive`
  or restart-on-exit), so `bml-pgserver` is the only thing that ever stops or
  restarts the server, and an import-profile restart never fights a
  supervisor. The private server's bin and data directories are recorded in a
  `bml-pgserver` state file under `~/.bmlibrarian/`.
- **Import profile:** nothing imports into the private server before the Rust
  importer (Phase B). Fresh installs don't support the Python layout, so the
  Python `db_import_profile.py` is not changed. The Rust profile
  (`bml db profile`, Phase B) restarts the server through `bml-pgserver`, and
  sizes `shared_buffers`/`max_wal_size` from the machine's RAM instead of the
  hard-coded 32 GB. This work provides the restart and RAM-detection
  primitives.
- **Linux:** for now, `bml setup` and the CLI only, without the Tauri GUI,
  matching the lighter Linux touch. The binaries target a glibc baseline old
  enough for current Ubuntu LTS / Debian stable, on x86_64 and arm64.
- **Updates and bundled binary versions:** binaries are installed side by side
  in versioned directories from day one. For now, an update that would change
  the PostgreSQL major version or the `pg_search` version under an existing
  data directory leaves that server on its current binaries and says so. A
  resumable upgrade step (`pg_upgrade`, `ALTER EXTENSION … UPDATE` + reindex)
  is a later piece of work.
- **Embedding model:** bmlib Rust already pins the GGUF (repo, revision,
  sha256 in `embed/model.rs`) and has a verified download. Setup calls it.
- **Ollama:** use Ollama's official installers.
  - Windows: the installer is per-user.
  - macOS: install `Ollama.app` into `~/Applications` and skip its
    admin-only CLI link. The app talks to Ollama over HTTP.
  - Linux: the official `install.sh` (sudo) is acceptable for Linux users;
    the bootstrap script says so before running it.
- **Releases and updates:** releases are published as GitHub Releases. Running
  a newer installer updates an existing install, using Tauri's updater once
  the app exists. Migrations are applied by the app/CLI at start, not by the
  installer.
- **Linux bootstrap script:** downloads the signed/checksummed Linux release
  from GitHub Releases into a per-user folder, then runs `bml setup`
  headless.
- **Rust plan document:** update `doc/planning/rust/implementation_plan.md`
  to record this work (the new crates, Tauri pulled forward, the Windows
  fallback), so the plan stays the single source of truth.

## Pieces of work, in order

1. **Workspace and CI.** Create the `rust/` Cargo workspace, with fmt, clippy
   and tests on macOS arm64 and x86_64, Windows x64, and Linux x86_64 and
   arm64. This is the Rust plan's Phase B step 1, pulled forward.
2. **`bml-pgserver`.** Portable PG 18 binaries with pgvector, plus `pg_search`
   on macOS/Linux, built or obtained per platform, pinned and checksummed. It
   handles:
   - `initdb` into the chosen folder
   - `postgresql.conf`: port, `listen_addresses`, `shared_preload_libraries`
   - `pg_hba.conf`
   - roles, database and extensions
   - per-user autostart
   - start/stop/status
   - writing `~/.bmlibrarian/bml.env` and `bml-admin.env`
   - restart and RAM-detection primitives for the later Rust import profile
3. **`bml-setup` plus `bml setup` CLI.** Requirement checks, Ollama install,
   model pulls, GGUF download and verification, hardware warnings, resumable
   steps.
4. **`bml-app` (Tauri) first-run screen.** The plain-language setup flow:
   - choose where the data lives
   - see progress
   - read warnings
   - finish, or retry a failed step
5. **Packaging.** CI builds unsigned artefacts. The owner's local release
   script produces the signed and notarised `.dmg` and the signed `.exe`. Also
   in this step: the Linux bootstrap script, and GitHub Releases with
   checksums and the AGPL source offer.
6. **Windows lexical fallback.** Done in the Rust-layout migrations and
   `bml-search` when those are written (Phases B/C). This design only fixes
   the requirement.

## Left to the builder

- Where portable PG 18 / pgvector / `pg_search` binaries come from: existing
  portable distributions, or built in CI. They must be pinned, checksummed
  and signable.
- The Tauri front-end stack. Keep it lean, follow the project's styling and
  DPI-scaling intent, and use toasts rather than modal dialogs (owner
  preference).
- The installer framework on Windows (e.g. Tauri's NSIS bundler) and `.dmg`
  layout details.
- The Windows signing tool for the owner's hardware-held key: `signtool` on a
  Windows machine, or `jsign`/`osslsigncode` from the Mac.
- Exact hardware thresholds for the model warnings.
- The exact default port within the constraints above.
- Uninstall behaviour, within the anti-goal above.
- Documentation: a user guide in `doc/users/` and developer docs in
  `doc/developers/`, per project rules.
