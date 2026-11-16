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
use tauri::{AppHandle, Emitter, Manager, State};

use library_worker::{SearchWorker, Update, ALREADY_RUNNING};
use state::StartScreen;
use view::{minutes_left, progress_line, LibraryCounts};

/// How many papers a search shows.
const SEARCH_LIMIT: usize = 20;

/// How long quitting waits for a running update to stop after the paper in
/// flight (a slow full text or index of one paper, or a medRxiv request
/// waiting up to 30 s for its turn, can take longer: that paper is then done
/// again next time).
const QUIT_WAIT: std::time::Duration = std::time::Duration::from_secs(15);

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

/// Load the search model now (it takes seconds), so the first search is quick.
#[tauri::command]
fn warm_search(app: State<'_, App>) {
    app.search.warm();
}

/// A paper to read: title, one line of journal and year, and its text.
#[derive(Serialize)]
struct PaperView {
    /// The title.
    title: String,
    /// Journal and year, and a note when the full text could not be read.
    meta: String,
    /// The full text, else the abstract.
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
    /// What the library holds.
    counts: LibraryCounts,
    /// Minutes until the papers found so far are searchable; none when done.
    minutes_left: Option<u64>,
    /// Whether this window's update is running.
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
    // Set when the pipeline says it is waiting for the internet, so the end
    // reads "waiting" (and the window retries) rather than "Paused".
    let waited = std::sync::Arc::new(std::sync::atomic::AtomicBool::new(false));
    let seen_waiting = waited.clone();
    let update = library_worker::start_update(
        app.config_dir.clone(),
        move |p| {
            if p.message == bml_library::WAITING_FOR_INTERNET {
                seen_waiting.store(true, std::sync::atomic::Ordering::Relaxed);
            }
            let _ = events.emit("library-progress", progress_line(p));
        },
        move |result| {
            let ended = view::finished(&result, waited.load(std::sync::atomic::Ordering::Relaxed));
            let _ = handle.emit("library-done", ended);
        },
    )?;
    *slot = Some(update);
    Ok(())
}

/// Screen 2: the library folder, its free space and a rough size estimate.
#[derive(Serialize)]
struct FolderInfo {
    /// The library folder setup will create.
    path: String,
    /// Free space on its disk, when known.
    free_bytes: Option<u64>,
    /// Roughly what the largest topic needs.
    estimate_bytes: u64,
}

/// The library folder setup will use: the saved one when setup already
/// recorded it (a re-run after the window closed mid-setup, #462), else the
/// default `~/BMLibrarian`.
#[tauri::command]
fn library_folder(app: State<'_, App>) -> Result<FolderInfo, String> {
    let path = bml_db::library::resolve_library(&app.config_dir, None, std::env::home_dir())
        .map_err(|e| e.to_string())?
        .dir;
    Ok(FolderInfo {
        free_bytes: bml_setup::hardware::free_space_at(&path, &bml_setup::hardware::mounts()),
        path: path.display().to_string(),
        estimate_bytes: setup_view::largest_topic_bytes(),
    })
}

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
        // A panic inside setup still resets the flag and ends the screen.
        let ok = library_worker::guarded(|| Ok(run_app_setup(config_dir, login, &handle)))
            .unwrap_or_else(|e| {
                let _ = handle.emit(
                    "setup-step",
                    setup_view::step_line(&bml_setup::StepEvent::Finished(
                        bml_setup::StepId::Hardware,
                        bml_setup::StepOutcome::Failed(e),
                    )),
                );
                false
            });
        if let Some(app) = tauri::Manager::try_state::<App>(&handle) {
            let mut running = app
                .setup_running
                .lock()
                .unwrap_or_else(std::sync::PoisonError::into_inner);
            *running = false;
        }
        let _ = handle.emit("setup-done", ok);
    });
    Ok(())
}

/// Run setup for `config_dir`, reporting each step as a `setup-step` event;
/// `true` when no step failed.
fn run_app_setup(config_dir: PathBuf, login: Option<PathBuf>, handle: &AppHandle) -> bool {
    let mut skip = std::collections::BTreeSet::new();
    if login.is_none() {
        // No `bml` beside the app: a login entry would run the app itself.
        skip.insert(bml_setup::StepId::Autostart);
    }
    match bml_setup::ollama::parse_ollama_host(
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
    }
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

/// Make the new, empty library topic `id`'s library.
#[tauri::command]
async fn choose_topic(app: State<'_, App>, id: String) -> Result<(), String> {
    let config_dir = app.config_dir.clone();
    // On a plain thread: the `postgres` client panics on Tauri's runtime.
    std::thread::spawn(move || -> Result<(), String> {
        let topic =
            bml_library::topics::topic(&id).ok_or_else(|| format!("There is no topic {id:?}."))?;
        let mut db = library_worker::open_db(&config_dir)?;
        bml_library::topics::set_topic(&mut db, topic).map_err(|e| e.to_string())
    })
    .join()
    .map_err(|_| "choosing the topic failed unexpectedly".to_string())?
}

/// Record how often the library is brought up to date. Call it only once
/// this window's update holds the library's lock: on macOS the scheduler
/// starts a `bml library update` at once, which must find the lock taken
/// (and exit) rather than take it from the window. Returns a note for a toast
/// when the schedule could not be recorded.
#[tauri::command]
fn set_schedule(
    app: State<'_, App>,
    schedule: setup_view::Schedule,
) -> Result<Option<String>, String> {
    let Some(bml) = std::env::current_exe()
        .ok()
        .as_deref()
        .and_then(setup_view::bml_beside)
    else {
        return Ok(Some(
            "Automatic updates need the installed BMLibrarian; this copy updates while its window is open."
                .into(),
        ));
    };
    match schedule.days()? {
        None => bml_pgserver::schedule::unschedule_updates(),
        Some(days) => bml_pgserver::schedule::schedule_updates(&bml, &app.config_dir, days),
    }
    .map_err(|e| format!("The update schedule could not be recorded: {e}"))?;
    Ok(None)
}

/// Stop the update after the paper in flight.
#[tauri::command]
fn pause_update(app: State<'_, App>) {
    let slot = app
        .update
        .lock()
        .unwrap_or_else(std::sync::PoisonError::into_inner);
    if let Some(update) = slot.as_ref() {
        update.pause();
    }
}

/// Open the window on the configuration folder of this run.
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
            warm_search,
            open_paper,
            library_counts,
            start_update,
            pause_update,
            library_folder,
            start_setup,
            topic_counts,
            choose_topic,
            set_schedule
        ])
        .build(tauri::generate_context!());
    match result {
        // Every quit (⌘Q, or closing the window) ends here; ⌘Q on macOS
        // skips `ExitRequested`, so this is the one hook all of them reach.
        // Stop the update after the paper in flight before the process goes.
        Ok(built) => built.run(|handle, event| {
            if let tauri::RunEvent::Exit = event {
                pause_before_exit(handle);
            }
        }),
        Err(e) => {
            eprintln!("BMLibrarian's window could not open: {e}");
            std::process::exit(1);
        }
    }
}

/// Hide the window and wait (at most [`QUIT_WAIT`]) for this window's update
/// to stop after the paper in flight.
fn pause_before_exit(handle: &AppHandle) {
    let Some(app) = handle.try_state::<App>() else {
        return;
    };
    let slot = app
        .update
        .lock()
        .unwrap_or_else(std::sync::PoisonError::into_inner);
    if let Some(update) = slot.as_ref().filter(|u| u.running()) {
        // The window goes at once; only the update's last paper is waited for.
        for window in handle.webview_windows().values() {
            let _ = window.hide();
        }
        if !update.pause_and_wait(QUIT_WAIT) {
            eprintln!("BMLibrarian quit before the update stopped; the paper in flight is done again next time.");
        }
    }
}
