# The app (`rust/bml-app`, Tauri 2)

A thin front end over `bml-setup`, `bml-library` and `bml-search`. Design:
`docs/superpowers/specs/2026-11-15-investor-demo-europepmc-design.md`
(part 4). The six screens follow the walking-skeleton spec's approved
wireframes; screen 4 offers Europe PMC topics instead of medRxiv and AWS keys.

## Build and run

`bml-app` is a workspace member but not a default member, so `cargo test`,
`cargo clippy` and CI never build Tauri. On macOS:

```bash
cd rust
cargo build -p bml-cli -p bml-app        # the app needs `bml` beside it
./target/debug/bml-app                   # default config: ~/.bmlibrarian
BML_CONFIG_DIR=~/.bml-demo ./target/debug/bml-app   # another library
```

Tauri 2.12 needs Rust 1.90 (`rust-version` on this crate only). The front
end (`ui/`) is static HTML, one stylesheet (`app.css`, sizes in `rem`/`em`,
light and dark) and vanilla JavaScript through `withGlobalTauri`. There is no
Node build step and no inline style. `gen/` is Tauri's generated schemas and
is git-ignored. `icons/icon.png` (RGBA, the window icon) is required by
`tauri-build`; `icons/icon.icns` is the macOS bundle icon. Both are
BMLibrarian Lite's icon (`assets/AppIcon.iconset`, `assets/icon.icns`).

## macOS installer

`scripts/build_bmlibrarianV2_installer.sh` builds
`rust/target/release/bundle/dmg/BMLibrarian_<version>_<arch>.dmg` (the
version comes from `tauri.conf.json`). It builds `bml` in release, ships it
as a Tauri `externalBin` so the bundle holds `Contents/MacOS/bml` beside
`bml-app` (where `bml_beside` looks), and turns bundling on through
`--config`; the committed `tauri.conf.json` keeps `bundle.active` false so
dev builds stay fast. By default it signs with the Keychain's Developer ID
Application certificate (`DEVELOPER_ID` overrides it), then notarizes and
staples the DMG through the notarytool Keychain profile
`bmlibrarian-notarize` (`NOTARY_PROFILE` overrides it; BMLibrarian Lite
uses the same one). `--unsigned` signs ad hoc, for local testing only. The
DMG is for the build machine's architecture only. Tauri's `bundle_dmg.sh`
lays out the window through a Finder AppleScript that fails now and then;
the script detaches the read-write image a failed run leaves mounted and
retries once.

## Layout

| File | What it holds |
|---|---|
| `state.rs` | `config_dir_from(env, home)` (the `BML_CONFIG_DIR` variable, as `bml` resolves it) and `start_screen` (Search when a library is recorded and the embedding GGUF is at `bml_setup::gguf_path`). |
| `view.rs` | Screen 5's `LibraryCounts` from `LibraryStatus`, `progress_line` (plain words per phase), and `minutes_left` from `SECONDS_PER_PAPER` (10, measured). |
| `setup_view.rs` | `bml_beside` (the `bml` next to the app), `step_line` (a status line per `StepEvent`), and `topic_counts_with` (live Europe PMC counts, the stored ones after `TOPIC_COUNT_TIMEOUT`). |
| `library_worker.rs` | `open_db` (starts a stopped private server and runs the `bml-db` migrations, as `bml library update` and `status` do, so a library made by an older version still updates), the `SearchWorker` thread, and `start_update` (`Pipeline::update` on its own thread under the library's worker lock). |
| `main.rs` | The Tauri commands and events. |

## Rules the code keeps

- **No `postgres` call on Tauri's async runtime.** The `postgres` client
  runs its own runtime and panics inside another ("Cannot start a runtime
  from within a runtime"). Database work happens on the search worker's
  plain thread (search, open paper, counts), the update thread, or a
  spawned thread (`choose_topic`).
- **Login entries run `bml`, never the app.** `SetupPlan::login_program`
  and `schedule_updates` get the `bml` beside the app. Without one, setup
  skips start-at-login (its status line says "Left out: …") and the
  schedule is not recorded (a toast says so).
- **The schedule comes after the lock.** `choose_topic(id)` only records the
  topic. `set_schedule(schedule)` runs once `start_update` holds the
  library's lock, because on macOS the scheduler starts a `bml library
  update` at once; that one then finds the lock taken and exits.
  `Schedule::days` refuses an interval outside 1–365 days.
- **The window never blocks.** Setup and updates report through events:
  `setup-step` (a `StepLine`), `setup-done` (bool), `library-progress` (a
  line) and `library-done` (`view::Finished`, `{complete, waiting,
  message}`). `view::finished` names a failure first, then no network
  (`waiting`: the window starts the update again after 45 s), a rate limit,
  then a pause.
- **Quitting stops the update cleanly.** ⌘Q and closing the window both
  end in `RunEvent::Exit` (⌘Q on macOS skips `ExitRequested`, so `Exit` is
  the one hook every quit reaches), where `pause_before_exit` hides the
  window and waits up to `QUIT_WAIT` (15 s) for the update to stop after
  the paper in flight (`Update::pause_and_wait`). Past that, the paper is
  done again next time, and a line on stderr says so.
- **The search model loads before the first search.** The search screen
  calls `warm_search`, which has the search worker connect and load the
  1.16 GB model in the background; a search asked meanwhile waits behind it
  on the same thread.
- **A window closed mid-setup reopens the wizard.** Setup records the
  library early but downloads the GGUF last, so `start_screen` also
  requires the GGUF (the download is renamed into place only once
  verified). Without it the window opens on Welcome, and setup, safe to
  re-run, skips the steps already done; a cut-off download starts again
  (#462). Screen 2's `library_folder` shows the saved library folder
  (`resolve_library`), so a re-run never shows a folder setup will not use.
- **Screen 4 is not skipped.** A recorded library that holds no papers and
  no topic (the window was closed after setup finished, before a topic was
  chosen) reopens on topic choice: `LibraryCounts::needs_topic`.
  The window shows search at once and switches once the counts arrive. An
  update of such a library is refused (`CHOOSE_TOPIC_FIRST`): it would
  fill the library with medRxiv papers, after which no topic can be set.
- **No thread dies silently.** The update and setup threads run under
  `library_worker::guarded`, which turns a panic into a plain error for the
  window.
- **Toasts, never `alert()`**.

## Commands

`start_screen`, `library_folder`, `start_setup`, `topic_counts`,
`choose_topic(id)`, `set_schedule(schedule)`, `start_update`, `pause_update`,
`library_counts`, `warm_search`, `search(query)` (20 hits), `open_paper(id)`.

## Tests

`cargo test -p bml-app` runs the pure modules' tests. `--include-ignored`
with `BML_TEST_PG_BINDIR` also runs `counts_from_an_async_command_do_not_panic`,
which runs the counts as the command does, on Tauri's async runtime, and
guards against the runtime panic above coming back.
