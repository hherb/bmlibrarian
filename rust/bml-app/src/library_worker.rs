//! The app's two background workers: the search worker (one thread holding
//! the database connection and the embedding model between searches) and the
//! library update (`Pipeline::update` on its own thread). The window never
//! waits on either: commands hand work over and results come back as replies
//! or events.

use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::mpsc::{channel, Sender};
use std::sync::{Arc, Mutex};
use std::thread::JoinHandle;
use std::time::{Duration, Instant};

use bml_db::library::{load_library, Library};
use bml_library::index::{load_model_embedder, paper_text, ChunkEmbedder, PaperText};
use bml_library::status::library_status;
use bml_library::topics::library_source;
use bml_library::{try_lock_worker, PhaseSet, Pipeline, Progress, UpdateOptions, UpdateReport};
use bml_pgserver::control::{start, status, ServerStatus};
use bml_pgserver::envfile::{read_conn_info, APP_ENV_FILE_NAME};
use bml_pgserver::init::connect;
use bml_pgserver::state::load_state;
use bml_search::{search, SearchHit};
use postgres::Client;

use crate::view::{counts_from_status, LibraryCounts};

/// The library recorded in `config_dir`, or a plain-language reason.
///
/// # Errors
///
/// None is recorded, or the record cannot be read.
pub fn library(config_dir: &Path) -> Result<Library, String> {
    load_library(config_dir)
        .map_err(|e| e.to_string())?
        .ok_or_else(|| "No library is set up yet.".to_string())
}

/// A connection to the library's database, starting the private server first
/// when it is stopped (a library set up without a login item).
///
/// # Errors
///
/// Not set up, the server will not start, or the connection fails.
pub fn open_db(config_dir: &Path) -> Result<Client, String> {
    if let Some(state) = load_state(config_dir).map_err(|e| e.to_string())? {
        if status(&state).map_err(|e| e.to_string())? == ServerStatus::Stopped {
            start(&state).map_err(|e| format!("the library's database would not start: {e}"))?;
        }
    }
    let info = read_conn_info(&config_dir.join(APP_ENV_FILE_NAME))
        .map_err(|e| e.to_string())?
        .ok_or_else(|| "No database is set up yet.".to_string())?;
    connect(&info).map_err(|e| format!("the library's database cannot be reached: {e}"))
}

/// What the library holds, for screen 5.
///
/// # Errors
///
/// The library or its database cannot be read.
pub fn counts(config_dir: &Path) -> Result<LibraryCounts, String> {
    let library = library(config_dir)?;
    let mut db = open_db(config_dir)?;
    let status = library_status(&mut db, &library.cache()).map_err(|e| e.to_string())?;
    let source = library_source(&mut db).map_err(|e| e.to_string())?;
    Ok(counts_from_status(&status, &source))
}

/// One request to the search worker.
enum Ask {
    /// Search the library.
    Search {
        /// The question.
        query: String,
        /// How many papers to return.
        limit: usize,
        /// Where the hits go.
        reply: Sender<Result<Vec<SearchHit>, String>>,
    },
    /// Read one paper.
    Paper {
        /// `publications.id`.
        id: i64,
        /// Where its text goes.
        reply: Sender<Result<PaperText, String>>,
    },
    /// Count what the library holds.
    Counts {
        /// Where the counts go.
        reply: Sender<Result<LibraryCounts, String>>,
    },
    /// Connect and load the model now, so the first search is quick.
    Warm,
}

/// The search worker: a thread that keeps the connection and the model.
pub struct SearchWorker {
    asks: Mutex<Sender<Ask>>,
}

impl SearchWorker {
    /// Start the worker for `config_dir` (nothing loads until the first ask).
    #[must_use]
    pub fn spawn(config_dir: PathBuf) -> Self {
        let (tx, rx) = channel::<Ask>();
        std::thread::spawn(move || {
            let mut db: Option<Client> = None;
            let mut model: Option<Box<dyn ChunkEmbedder>> = None;
            for ask in rx {
                match ask {
                    Ask::Search {
                        query,
                        limit,
                        reply,
                    } => {
                        let found =
                            ready(&config_dir, &mut db, &mut model).and_then(|(db, model)| {
                                search(db, model.as_mut(), &query, limit).map_err(|e| e.to_string())
                            });
                        if found.is_err() {
                            db = None; // reconnect next time (a restarted server)
                        }
                        let _ = reply.send(found);
                    }
                    Ask::Paper { id, reply } => {
                        let text = library(&config_dir).and_then(|lib| {
                            connected(&config_dir, &mut db).and_then(|db| {
                                paper_text(&lib.cache(), db, id).map_err(|e| e.to_string())
                            })
                        });
                        if text.is_err() {
                            db = None; // reconnect next time (a restarted server)
                        }
                        let _ = reply.send(text);
                    }
                    Ask::Warm => {
                        // A failure here is reported by the next search, which retries.
                        if ready(&config_dir, &mut db, &mut model).is_err() {
                            db = None;
                        }
                    }
                    Ask::Counts { reply } => {
                        // Here, off Tauri's async runtime: the `postgres` client
                        // runs its own and panics inside another.
                        let _ = reply.send(counts(&config_dir));
                    }
                }
            }
        });
        SearchWorker {
            asks: Mutex::new(tx),
        }
    }

    /// The `limit` best papers for `query` (blocks this caller, not the window).
    ///
    /// # Errors
    ///
    /// The search failed, in plain words.
    pub fn search(&self, query: String, limit: usize) -> Result<Vec<SearchHit>, String> {
        let (reply, answer) = channel();
        self.send(Ask::Search {
            query,
            limit,
            reply,
        })?;
        answer.recv().map_err(|_| WORKER_GONE.to_string())?
    }

    /// The readable text of paper `id`.
    ///
    /// # Errors
    ///
    /// The paper cannot be read, in plain words.
    pub fn paper(&self, id: i64) -> Result<PaperText, String> {
        let (reply, answer) = channel();
        self.send(Ask::Paper { id, reply })?;
        answer.recv().map_err(|_| WORKER_GONE.to_string())?
    }

    /// What the library holds now (screen 5).
    ///
    /// # Errors
    ///
    /// The library or its database cannot be read.
    pub fn counts(&self) -> Result<LibraryCounts, String> {
        let (reply, answer) = channel();
        self.send(Ask::Counts { reply })?;
        answer.recv().map_err(|_| WORKER_GONE.to_string())?
    }

    /// Load the connection and the model in the background (the model takes
    /// seconds), so the first search does not wait for them.
    pub fn warm(&self) {
        // A stopped worker is reported by the next search.
        let _ = self.send(Ask::Warm);
    }

    /// Hand `ask` to the worker thread.
    fn send(&self, ask: Ask) -> Result<(), String> {
        self.asks
            .lock()
            .map_err(|_| WORKER_GONE.to_string())?
            .send(ask)
            .map_err(|_| WORKER_GONE.to_string())
    }
}

/// When the search worker has stopped.
const WORKER_GONE: &str = "search stopped working; close and reopen BMLibrarian";

/// The worker's connection, opened (and the server started) when there is none.
fn connected<'a>(config_dir: &Path, db: &'a mut Option<Client>) -> Result<&'a mut Client, String> {
    if db.is_none() {
        *db = Some(open_db(config_dir)?);
    }
    db.as_mut().ok_or_else(|| WORKER_GONE.to_string())
}

/// The connection and the embedding model, each loaded on first use.
fn ready<'a>(
    config_dir: &Path,
    db: &'a mut Option<Client>,
    model: &'a mut Option<Box<dyn ChunkEmbedder>>,
) -> Result<(&'a mut Client, &'a mut Box<dyn ChunkEmbedder>), String> {
    if model.is_none() {
        *model = Some(load_model_embedder(&bml_setup::gguf_path(config_dir))?);
    }
    let db = connected(config_dir, db)?;
    let model = model.as_mut().ok_or_else(|| WORKER_GONE.to_string())?;
    Ok((db, model))
}

/// A running library update: its stop flag and thread.
pub struct Update {
    stop: Arc<AtomicBool>,
    thread: JoinHandle<()>,
}

impl Update {
    /// Whether the update's thread is still running.
    #[must_use]
    pub fn running(&self) -> bool {
        !self.thread.is_finished()
    }

    /// Ask the update to stop after the paper in flight.
    pub fn pause(&self) {
        self.stop.store(true, Ordering::Relaxed);
    }

    /// Ask the update to stop and wait up to `limit` for its thread to end;
    /// `true` when it ended. Past `limit` the paper in flight is redone next
    /// time (its work is in one transaction, so nothing is half stored).
    pub fn pause_and_wait(&self, limit: Duration) -> bool {
        self.pause();
        let deadline = Instant::now() + limit;
        while self.running() {
            if Instant::now() >= deadline {
                return false;
            }
            std::thread::sleep(STOP_POLL);
        }
        true
    }
}

/// How often [`Update::pause_and_wait`] looks whether the update has ended.
const STOP_POLL: Duration = Duration::from_millis(100);

/// Start a library update on its own thread; `progress` gets every progress
/// event and `done` the report. Another update holding the library's lock is
/// refused in plain words.
///
/// # Errors
///
/// No library, an update already running, or the lock cannot be taken.
pub fn start_update(
    config_dir: PathBuf,
    progress: impl Fn(&Progress) + Send + 'static,
    done: impl FnOnce(Result<UpdateReport, String>) + Send + 'static,
) -> Result<Update, String> {
    let library = library(&config_dir)?;
    let lock = try_lock_worker(&library.dir)
        .map_err(|e| format!("the library's update lock cannot be taken: {e}"))?
        .ok_or_else(|| ALREADY_RUNNING.to_string())?;
    let stop = Arc::new(AtomicBool::new(false));
    let flag = stop.clone();
    let thread = std::thread::spawn(move || {
        let _lock = lock; // held until the update ends
                          // A panic inside the pipeline still reaches the window as an error.
        let result = guarded(|| {
            open_db(&config_dir).map(|mut db| {
                let pipeline = Pipeline::new(library.cache(), bml_setup::gguf_path(&config_dir));
                let options = UpdateOptions {
                    from: None,
                    phases: PhaseSet::all(),
                    stop: &flag,
                };
                pipeline.update(&mut db, &options, &mut |p| progress(&p))
            })
        });
        done(result);
    });
    Ok(Update { stop, thread })
}

/// `work`'s result, or a plain-language error when it panics (bmlib, MuPDF
/// or the embedder failing in a way they did not report), so a background
/// thread always ends with an answer for the window.
///
/// # Errors
///
/// `work`'s own error, or the panic's message.
pub fn guarded<T>(work: impl FnOnce() -> Result<T, String>) -> Result<T, String> {
    std::panic::catch_unwind(std::panic::AssertUnwindSafe(work)).unwrap_or_else(|payload| {
        let why = payload
            .downcast_ref::<&str>()
            .map(|s| (*s).to_string())
            .or_else(|| payload.downcast_ref::<String>().cloned())
            .unwrap_or_else(|| "no details".to_string());
        Err(format!(
            "It stopped unexpectedly ({why}). Start it again; nothing is lost."
        ))
    })
}

/// When the library's lock is held (another window, or a scheduled update).
pub const ALREADY_RUNNING: &str = "An update of this library is already running.";

#[cfg(test)]
mod tests {
    use super::*;
    use bml_db::library::ensure_library;
    use bml_pgserver::control::stop;
    use bml_pgserver::init::{init, InitRequest};

    /// Stops the test's server when dropped.
    struct StopOnDrop(PathBuf);
    impl Drop for StopOnDrop {
        fn drop(&mut self) {
            if let Ok(Some(state)) = load_state(&self.0) {
                let _ = stop(&state);
            }
        }
    }

    /// A config folder with a library and a running, migrated database.
    fn set_up(tmp: &Path) -> Option<(StopOnDrop, PathBuf)> {
        let bindir = std::env::var_os("BML_TEST_PG_BINDIR")
            .filter(|v| !v.is_empty())
            .map(PathBuf::from)?;
        let cfg = tmp.join("cfg");
        let guard = StopOnDrop(cfg.clone());
        init(
            &InitRequest {
                bindir,
                data_dir: tmp.join("data"),
                extension_dirs: Vec::new(),
            },
            &cfg,
        )
        .unwrap();
        let mut db = open_db(&cfg).unwrap();
        bml_db::migrate(&mut db).unwrap();
        ensure_library(
            &cfg,
            &Library {
                dir: tmp.join("library"),
            },
        )
        .unwrap();
        Some((guard, cfg))
    }

    #[test]
    fn guarded_turns_a_panic_into_an_error() {
        assert_eq!(guarded(|| Ok::<_, String>(7)), Ok(7));
        assert_eq!(
            guarded(|| Err::<i32, _>("no".to_string())),
            Err("no".to_string())
        );
        let error = guarded(|| -> Result<i32, String> { panic!("the model crashed") }).unwrap_err();
        assert!(error.contains("stopped unexpectedly"), "{error}");
        assert!(error.contains("the model crashed"), "{error}");
    }

    /// An update whose thread runs `work` with the update's stop flag.
    fn fake_update(work: impl FnOnce(Arc<AtomicBool>) + Send + 'static) -> Update {
        let stop = Arc::new(AtomicBool::new(false));
        let flag = stop.clone();
        Update {
            stop,
            thread: std::thread::spawn(move || work(flag)),
        }
    }

    #[test]
    fn pause_and_wait_returns_once_the_update_stops() {
        let update = fake_update(|stop| {
            while !stop.load(Ordering::Relaxed) {
                std::thread::sleep(Duration::from_millis(5));
            }
        });
        assert!(update.pause_and_wait(Duration::from_secs(10)));
        assert!(!update.running());
    }

    #[test]
    fn pause_and_wait_gives_up_after_the_limit() {
        let (release, wait) = channel::<()>();
        // Ignores the stop flag, like a request still waiting for its turn.
        let update = fake_update(move |_| {
            let _ = wait.recv();
        });
        assert!(!update.pause_and_wait(Duration::from_millis(50)));
        assert!(update.running());
        drop(release);
    }

    #[test]
    fn start_update_refuses_a_held_lock() {
        let tmp = tempfile::tempdir().unwrap();
        let cfg = tmp.path().join("cfg");
        let library = Library {
            dir: tmp.path().join("library"),
        };
        ensure_library(&cfg, &library).unwrap();
        // Another update (a scheduled `bml`) holds the library.
        let _held = try_lock_worker(&library.dir).unwrap().unwrap();
        let refused = start_update(cfg, |_| {}, |_| panic!("must not run")).err();
        assert_eq!(refused.as_deref(), Some(ALREADY_RUNNING));
    }

    #[test]
    #[ignore = "needs BML_TEST_PG_BINDIR"]
    fn counts_from_an_async_command_do_not_panic() {
        let tmp = tempfile::tempdir().unwrap();
        let Some((_s, cfg)) = set_up(tmp.path()) else {
            return;
        };
        let worker = SearchWorker::spawn(cfg);
        // As the `library_counts` command runs: on Tauri's async runtime.
        let counts = tauri::async_runtime::block_on(async { worker.counts() }).unwrap();
        assert_eq!(counts.found, 0);
        // Set up, no topic chosen yet: the window goes back to screen 4.
        assert!(counts.needs_topic);
    }
}
