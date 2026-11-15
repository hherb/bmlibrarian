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
is git-ignored. `icons/icon.png` is required by `tauri-build`.

## Layout

| File | What it holds |
|---|---|
| `state.rs` | `config_dir_from(env, home)` (the `BML_CONFIG_DIR` variable, as `bml` resolves it) and `start_screen` (Search when a library is recorded). |
| `view.rs` | Screen 5's `LibraryCounts` from `LibraryStatus`, `progress_line` (plain words per phase), and `minutes_left` from `SECONDS_PER_PAPER` (10, measured). |
| `setup_view.rs` | `bml_beside` (the `bml` next to the app), `step_line` (a status line per `StepEvent`), and `topic_counts_with` (live Europe PMC counts, the stored ones after `TOPIC_COUNT_TIMEOUT`). |
| `library_worker.rs` | `open_db` (starts a stopped private server), the `SearchWorker` thread, and `start_update` (`Pipeline::update` on its own thread under the library's worker lock). |
| `main.rs` | The Tauri commands and events. |

## Rules the code keeps

- **No `postgres` call on Tauri's async runtime.** The `postgres` client
  runs its own runtime and panics inside another ("Cannot start a runtime
  from within a runtime"). Database work happens on the search worker's
  plain thread (search, open paper, counts), the update thread, or a
  spawned thread (`choose_topic`).
- **Login entries run `bml`, never the app.** `SetupPlan::login_program`
  and `schedule_updates` get the `bml` beside the app. Without one, setup
  skips start-at-login and the schedule is not recorded, and a toast says
  so.
- **The window never blocks.** Setup and updates report through events:
  `setup-step` (a `StepLine`), `setup-done` (bool), `library-progress` (a
  line) and `library-done` (`{complete, message}`). Closing the window sets
  the update's stop flag.
- **Toasts, never `alert()`**.

## Commands

`start_screen`, `library_folder`, `start_setup`, `topic_counts`,
`choose_topic(id, schedule)`, `start_update`, `pause_update`,
`library_counts`, `search(query)` (20 hits), `open_paper(id)`.

## Tests

`cargo test -p bml-app` runs the pure modules' tests. `--include-ignored`
with `BML_TEST_PG_BINDIR` also runs `counts_from_an_async_command_do_not_panic`,
which reproduces the runtime panic above through the old code path.
