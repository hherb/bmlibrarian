# `bml-setup` and `bml setup`

Guided first-run setup, "Rust installer piece 3". Plan:
`docs/superpowers/plans/2026-11-07-bml-setup.md`; design:
`docs/superpowers/specs/2026-11-07-one-click-installer-design.md`. User
guide: `doc/users/bml_setup_guide.md`.

## Layout

`rust/bml-setup` (UI-free library; piece 4's Tauri screen reuses it):

| File | Role |
|---|---|
| `lib.rs` | `StepId`, `StepEvent`, `StepOutcome`, `SetupError` |
| `runner.rs` | `SetupPlan`, `DatabasePlan`, `run_setup`, `run_step`, `should_run`, `depends_on` |
| `pgdist.rs` | the bundled PostgreSQL: pinned release, host target, atomic install (`ensure_pgdist`, `install_from_archive`) |
| `steps.rs` | One function per step; each checks first, acts only when needed |
| `hardware.rs` | Pure RAM/disk verdicts (`MIN_RAM_BYTES`, model sizes) |
| `models.rs` | Approved-model plan: `gpt-oss:20b`; `medgemma1.5:4b-it-q8_0` pulled then `/api/copy` to `medgemma4B_it_q8:latest` |
| `ollama.rs` | Host parsing (`parse_ollama_host`), HTTP client over bmlib `HttpClient`, pull-stream parser |
| `ollama_install.rs` | Pinned, checksum-verified Ollama installers per platform |

`rust/bml-cli/src/setup.rs` is the thin front end (clap, reporter, summary).

## Steps, events, dependencies

Order: Hardware, Database, Autostart, Ollama, Models, EmbeddingModel.
`run_setup` carries on past failures; a step is skipped when it is in
`SetupPlan::skip` or when a dependency failed or was skipped
(Autostart needs Database; Models needs Ollama). Steps report through a
`FnMut(StepEvent)` callback (`Started`, `Progress`, `Notice`, `Warning`, and
`Finished`, which `run_setup` sends for every step, skipped ones included;
`run_step` sends no `Finished`) and end in a `StepOutcome` (`AlreadyPresent`,
`Installed`, `Started`, `Warnings(texts)`, `Skipped`, `Failed(message)`).
Hardware only warns and ends in `Warnings` (the same texts as its `Warning`
events, so the summary repeats them) or `AlreadyPresent`; it fails only when
the system does not report its memory. A disk it cannot find in the mount list
(or a relative path) gets an "unknown free space" warning. The Ollama models
disk is checked only for a loopback `OLLAMA_HOST`; the folder is
`OLLAMA_MODELS` (an empty value counts as unset), else on Linux
`/usr/share/ollama/.ollama/models` (the `install.sh` service user) when
`/usr/share/ollama` exists or `~/.ollama/models` does not, else
`~/.ollama/models`. The Models step tries every approved model and fails with
all their errors joined. The Database step with
no plan resumes from saved state, and reports when nothing is saved; it warns
when `pg_search` is missing or the app password had to be reset, and then
ends in `Warnings` with those texts (`report_warnings`, shared by Hardware,
Database and Ollama). The Ollama
step reports why Ollama did not answer before starting or installing it, and
on macOS waits for `open` so a damaged app's error shows. It looks for an
installed Ollama in `app_candidates` (macOS `~/Applications`, then
`/Applications`; Windows `%LOCALAPPDATA%\Programs\Ollama`, then
`%ProgramFiles%\Ollama`), then an `ollama` command on `PATH` (Homebrew,
Linux). An app is started; a command is not (setup tells the person how to
start it). On macOS the zip is unpacked into
`~/Applications/.bml-ollama-extract` and only then renamed to `Ollama.app`, so
a failed unpack never leaves a partial app that later runs would find. The
installer is deleted only after the app is in place; failing to delete it, or
the staging folder, is a warning (the step then ends in `Warnings`).

Downloads (the Ollama installer, the GGUF, the pgdist bundle) and the stale part-file sweep run
under `lock_downloads`: an OS file lock (`File::try_lock`, hence MSRV 1.89)
on `.bml-setup-download.lock` in the config folder. A second setup in the same
folder fails that step at once ("Another BMLibrarian setup is
downloading…"); the lock is released when the process exits, even by a
crash. Once the lock is held, the Ollama, Embedding and Database (pgdist) steps check again
whether the other setup already finished, so nothing is downloaded twice. A
disk without file locks fails with a message saying so.
`SetupError::Other` is for errors that are neither Ollama's nor the database
layer's (e.g. a saved existing server without `bml-admin.env`, no home
folder, the download lock held or unsupported, `current_exe` failing).
`DatabasePlan::Existing` goes through `bml_pgserver::external::adopt`
(loopback only, role `bml_app` and database `bmlibrarian` only).

The CLI prints progress at most once per `PROGRESS_PRINT_INTERVAL` (5 s) per
step. Failed steps and warnings go to stderr, everything else to stdout; the
summary (stdout) lists every step and each step's warnings. Before any step
runs it calls `bml_pgserver::external::check_request`, so a remote
`--existing-server` or an unusable password (an empty `--password-stdin` line)
exits 1 at once; the Tauri screen should call it too. The superuser password comes from `BML_PG_SUPERUSER_PASSWORD` or
`--password-stdin`, never argv. `--existing-server [::1]:5432` has its
brackets stripped before reaching `ExternalRequest`, and `adopt` strips them
too, for library callers (the postgres crate cannot resolve them). `needs_pg_search` is `!cfg!(windows)`.

## Pins and how to bump them

- **Ollama**: v0.40.10 (published 2026-10-23), constants in
  `ollama_install.rs`: macOS `Ollama-darwin.zip` (220350228 bytes),
  Windows `OllamaSetup.exe` (1661645848), Linux `install.sh` (15902, run with
  `OLLAMA_VERSION=0.40.10`). To bump: pick a release at least two weeks old,
  read the sha256 of each asset from that release's `sha256sum.txt` and the
  size from the asset list, update every place the version appears (`grep -rn 0.40.10 rust/`), the URL base, sizes and hashes
  together, and run `cargo test`.
- **Embedding model**: `bmlib::embed::ARCTIC_EMBED_L_V2_F16` (pinned size and
  checksum live in bmlib).
- **bmlib**: git dependency pinned by rev `9670f4e978d0b1d4e283b97458c4d177b1abfca3`
  (workspace `Cargo.toml`, features `http-ureq`, `model-download`) because
  the llama-free `model-download` feature is in bmlib PR hherb/bmlib#703. When
  bmlib 0.3.1 is on crates.io, switch to the version dependency and drop the rev.
- Approved models are fixed by policy; never substitute.
- **PostgreSQL bundle (pgdist)**: `bml-setup/pgdist-release.json` pins the
  published `pgdist-<version>` release (asset name, size and sha256 per
  target), embedded at build time. `DatabasePlan::Bundled` (the CLI default)
  resumes a saved server, else `pgdist::ensure_pgdist` downloads the asset
  under the download lock, unpacks it with the system `tar` into
  `<config>/pgdist/.<version>.partial`, renames the one bundle folder inside
  it to `<config>/pgdist/<version>` once its `pgdist.json` names that version
  and target, and deletes the archive; then `init` runs with `pg/bin` and
  `ext/` and the data folder (`Bundled { data_dir: None }` means
  `<config>/pgdata`). A `data_dir` the person gave must equal a saved private
  server's (else `StateMismatch`) and is refused when an existing server is
  saved. Building and bumping the
  bundle: `doc/developers/pgdist.md`.

## Not verified

- Ollama install on Windows (Inno Setup silent flags; see issue #397 for the
  Windows work) and on Linux (`install.sh` downloads its tarball and GPU
  add-ons with no checksum we can verify; it uses `sudo`).
- Only macOS has been run end to end by hand.

## Tests

`bml-cli/tests/setup_cli.rs` (argument handling, loopback refusal,
skip-everything run) runs under plain `cargo test`. The library has unit tests
with a scripted `HttpClient` fake. Database steps run in the `--include-ignored`
integration job against a real PG18.

## Autostart and the executable

`bml setup` enables autostart by default and the login entry records the
running executable's path. Run it from an installed `bml`, not `cargo run`
(whose binary lives in `target/`); with `cargo run` pass `--skip autostart`.
