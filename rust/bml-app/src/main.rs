//! BMLibrarian's app window (Tauri): a thin front end over `bml-setup`,
//! `bml-library` and `bml-search`. Developer notes: `doc/developers/bml_app.md`.

// No console window behind the app on Windows release builds.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod library_worker;
mod setup_view;
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
    /// Whether setup is running.
    setup_running: Mutex<bool>,
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

/// Screen 2: the library folder, its free space and a rough size estimate.
#[derive(Serialize)]
struct FolderInfo {
    path: String,
    free_bytes: Option<u64>,
    estimate_bytes: u64,
}

/// The default library folder (`~/BMLibrarian`), as setup will create it.
#[tauri::command]
fn library_folder() -> Result<FolderInfo, String> {
    let home = std::env::home_dir().ok_or("BMLibrarian cannot find your home folder")?;
    let path = home.join(LIBRARY_FOLDER_NAME);
    Ok(FolderInfo {
        free_bytes: bml_setup::hardware::free_space_at(&path, &bml_setup::hardware::mounts()),
        path: path.display().to_string(),
        estimate_bytes: setup_view::largest_topic_bytes(),
    })
}

/// The default library folder's name in the home folder (`bml setup`'s).
const LIBRARY_FOLDER_NAME: &str = "BMLibrarian";

/// Run setup on its own thread: a `setup-step` event per step event, then one
/// `setup-done` event (`true` when no step failed). Running it twice at once
/// is refused.
#[tauri::command]
fn start_setup(app: State<'_, App>, handle: AppHandle) -> Result<(), String> {
    let mut running = app
        .setup_running
        .lock()
        .map_err(|_| "the setup state is unreadable".to_string())?;
    if *running {
        return Err("Setup is already running.".into());
    }
    *running = true;
    let config_dir = app.config_dir.clone();
    let login = std::env::current_exe()
        .ok()
        .as_deref()
        .and_then(setup_view::bml_beside);
    std::thread::spawn(move || {
        let mut skip = std::collections::BTreeSet::new();
        if login.is_none() {
            // No `bml` beside the app: a login entry would run the app itself.
            skip.insert(bml_setup::StepId::Autostart);
        }
        let ok = match bml_setup::ollama::parse_ollama_host(
            std::env::var(bml_setup::ollama::OLLAMA_HOST_ENV)
                .ok()
                .as_deref(),
        ) {
            Ok(ollama_host) => {
                let plan = bml_setup::runner::SetupPlan {
                    login_program: login,
                    config_dir,
                    database: Some(bml_setup::runner::DatabasePlan::Bundled),
                    ollama_host,
                    skip,
                    library_dir: None,
                    home: std::env::home_dir(),
                };
                let results = bml_setup::runner::run_setup(
                    &plan,
                    &bml_setup::ollama::pull_http_client(),
                    &mut |event| {
                        let _ = handle.emit("setup-step", setup_view::step_line(&event));
                    },
                );
                !results
                    .iter()
                    .any(|(_, o)| matches!(o, bml_setup::StepOutcome::Failed(_)))
            }
            Err(e) => {
                let _ = handle.emit(
                    "setup-step",
                    setup_view::step_line(&bml_setup::StepEvent::Finished(
                        bml_setup::StepId::Ollama,
                        bml_setup::StepOutcome::Failed(e.to_string()),
                    )),
                );
                false
            }
        };
        if let Some(app) = tauri::Manager::try_state::<App>(&handle) {
            if let Ok(mut running) = app.setup_running.lock() {
                *running = false;
            }
        }
        let _ = handle.emit("setup-done", ok);
    });
    Ok(())
}

/// Screen 4: every preset topic with its paper count (live when Europe PMC
/// answers in time, else as measured).
#[tauri::command]
async fn topic_counts() -> Vec<setup_view::TopicCount> {
    setup_view::topic_counts_with(
        std::sync::Arc::new(bmlib::http::UreqClient::new()),
        setup_view::TOPIC_COUNT_TIMEOUT,
    )
}

/// How often the library is brought up to date.
#[derive(serde::Deserialize)]
#[serde(rename_all = "lowercase")]
enum Schedule {
    /// Every week (the default).
    Weekly,
    /// Every `days` days.
    Every { days: u32 },
    /// Only when asked.
    Manual,
}

/// Days in a week, for [`Schedule::Weekly`].
const WEEKLY_DAYS: u32 = 7;

/// Make the new library topic `id`'s library and record how often to update
/// it. Returns a note for a toast when the schedule could not be recorded.
#[tauri::command]
async fn choose_topic(
    app: State<'_, App>,
    id: String,
    schedule: Schedule,
) -> Result<Option<String>, String> {
    let config_dir = app.config_dir.clone();
    // On a plain thread: the `postgres` client panics on Tauri's runtime.
    std::thread::spawn(move || -> Result<Option<String>, String> {
        let topic = bml_library::topics::topic(&id).ok_or_else(|| format!("There is no topic {id:?}."))?;
        let mut db = library_worker::open_db(&config_dir)?;
        bml_library::topics::set_topic(&mut db, topic).map_err(|e| e.to_string())?;
        let Some(bml) = std::env::current_exe().ok().as_deref().and_then(setup_view::bml_beside) else {
            return Ok(Some(
                "Automatic updates need the installed BMLibrarian; this copy updates while its window is open.".into(),
            ));
        };
        match schedule {
            Schedule::Manual => bml_pgserver::schedule::unschedule_updates(),
            Schedule::Weekly => bml_pgserver::schedule::schedule_updates(&bml, &config_dir, WEEKLY_DAYS),
            Schedule::Every { days } => bml_pgserver::schedule::schedule_updates(&bml, &config_dir, days),
        }
        .map_err(|e| format!("The update schedule could not be recorded: {e}"))?;
        Ok(None)
    })
    .join()
    .map_err(|_| "choosing the topic failed unexpectedly".to_string())?
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
        setup_running: Mutex::new(false),
    };
    let result = tauri::Builder::default()
        .manage(app)
        .invoke_handler(tauri::generate_handler![
            start_screen,
            search,
            open_paper,
            library_counts,
            start_update,
            pause_update,
            library_folder,
            start_setup,
            topic_counts,
            choose_topic
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
