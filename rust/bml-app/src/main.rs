//! BMLibrarian's app window (Tauri): a thin front end over `bml-setup`,
//! `bml-library` and `bml-search`. Developer notes: `doc/developers/bml_app.md`.

// No console window behind the app on Windows release builds.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod library_worker;
mod state;
mod view;

use std::path::PathBuf;
use std::sync::Mutex;

use bml_search::SearchHit;
use serde::Serialize;
use tauri::{AppHandle, Emitter, State};

use library_worker::{SearchWorker, Update, ALREADY_RUNNING};
use state::StartScreen;
use view::{minutes_left, progress_line, LibraryCounts};

/// How many papers a search shows.
const SEARCH_LIMIT: usize = 20;

/// What every command shares.
struct App {
    /// The configuration folder of this run (`$BML_CONFIG_DIR` or the default).
    config_dir: PathBuf,
    /// Holds the database connection and the model between searches.
    search: SearchWorker,
    /// The library update this window started, if any.
    update: Mutex<Option<Update>>,
}

/// The screen to open on (`welcome` or `search`).
#[tauri::command]
fn start_screen(app: State<'_, App>) -> StartScreen {
    state::start_screen(&app.config_dir)
}

/// The best papers for `query` (empty for a blank query).
#[tauri::command]
async fn search(app: State<'_, App>, query: String) -> Result<Vec<SearchHit>, String> {
    app.search.search(query, SEARCH_LIMIT)
}

/// A paper to read: title, one line of journal and year, and its text.
#[derive(Serialize)]
struct PaperView {
    title: String,
    meta: String,
    text: String,
}

/// The readable text of paper `id`.
#[tauri::command]
async fn open_paper(app: State<'_, App>, id: i64) -> Result<PaperView, String> {
    let paper = app.search.paper(id)?;
    Ok(PaperView {
        title: paper.title,
        meta: paper.meta,
        text: paper.text,
    })
}

/// Screen 5's counts and how many minutes are left (none when done).
#[derive(Serialize)]
struct Progress {
    counts: LibraryCounts,
    minutes_left: Option<u64>,
    running: bool,
}

/// What the library holds now, and whether this window's update runs.
#[tauri::command]
async fn library_counts(app: State<'_, App>) -> Result<Progress, String> {
    let counts = app.search.counts()?;
    let running = app
        .update
        .lock()
        .map_err(|_| "the update state is unreadable".to_string())?
        .as_ref()
        .is_some_and(Update::running);
    Ok(Progress {
        counts,
        minutes_left: minutes_left(&counts),
        running,
    })
}

/// How an update ended, for the window.
#[derive(Clone, Serialize)]
struct Finished {
    /// Every paper found so far is downloaded and searchable.
    complete: bool,
    /// One plain-language line.
    message: String,
}

/// Start (or resume) downloading the library; progress arrives as
/// `library-progress` events and the end as one `library-done` event.
#[tauri::command]
fn start_update(app: State<'_, App>, handle: AppHandle) -> Result<(), String> {
    let mut slot = app
        .update
        .lock()
        .map_err(|_| "the update state is unreadable".to_string())?;
    if slot.as_ref().is_some_and(Update::running) {
        return Err(ALREADY_RUNNING.to_string());
    }
    let events = handle.clone();
    let update = library_worker::start_update(
        app.config_dir.clone(),
        move |p| {
            let _ = events.emit("library-progress", progress_line(p));
        },
        move |result| {
            let finished = match result {
                Ok(report) if !report.failed() && !report.stopped_early() => Finished {
                    complete: true,
                    message: "Your library is up to date.".to_string(),
                },
                Ok(report) if report.stopped_early() => Finished {
                    complete: false,
                    message: "Paused. Next time it carries on where it stopped.".to_string(),
                },
                Ok(_) => Finished {
                    complete: false,
                    message: "Some papers could not be downloaded; they are tried again next time."
                        .to_string(),
                },
                Err(e) => Finished {
                    complete: false,
                    message: e,
                },
            };
            let _ = handle.emit("library-done", finished);
        },
    )?;
    *slot = Some(update);
    Ok(())
}

/// Stop the update after the paper in flight.
#[tauri::command]
fn pause_update(app: State<'_, App>) {
    if let Ok(slot) = app.update.lock() {
        if let Some(update) = slot.as_ref() {
            update.pause();
        }
    }
}

fn main() {
    let config_dir = match state::config_dir() {
        Ok(dir) => dir,
        Err(e) => {
            eprintln!("BMLibrarian cannot find its settings folder: {e}");
            std::process::exit(1);
        }
    };
    let app = App {
        search: SearchWorker::spawn(config_dir.clone()),
        config_dir,
        update: Mutex::new(None),
    };
    let result = tauri::Builder::default()
        .manage(app)
        .invoke_handler(tauri::generate_handler![
            start_screen,
            search,
            open_paper,
            library_counts,
            start_update,
            pause_update
        ])
        .on_window_event(|window, event| {
            // Closing the window stops the update after the paper in flight.
            if let tauri::WindowEvent::CloseRequested { .. } = event {
                if let Some(app) = tauri::Manager::try_state::<App>(window) {
                    if let Ok(slot) = app.update.lock() {
                        if let Some(update) = slot.as_ref() {
                            update.pause();
                        }
                    }
                }
            }
        })
        .run(tauri::generate_context!());
    if let Err(e) = result {
        eprintln!("BMLibrarian's window could not open: {e}");
        std::process::exit(1);
    }
}
