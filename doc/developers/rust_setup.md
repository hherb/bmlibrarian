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
`FnMut(StepEvent)` callback (`Started`, `Progress`, `Notice`, `Warning`) and
end in a `StepOutcome` (`AlreadyPresent`, `Installed`, `Started`, `Skipped`,
`Failed(message)`). Hardware never fails. The Database step with no plan
resumes from saved state, and reports when nothing is saved.
`DatabasePlan::Existing` goes through `bml_pgserver::external::adopt`
(loopback only, role `bml_app` and database `bmlibrarian` only).

The CLI prints progress at most once per `PROGRESS_PRINT_INTERVAL` (5 s) per
step. The superuser password comes from `BML_PG_SUPERUSER_PASSWORD` or
`--password-stdin`, never argv. `--existing-server [::1]:5432` has its
brackets stripped before reaching `ExternalRequest` (the postgres crate cannot
resolve them). `needs_pg_search` is `!cfg!(windows)`.

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
