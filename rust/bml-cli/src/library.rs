//! `bml library …`: bring the library up to date with medRxiv, show what it
//! holds, and schedule updates.

use std::path::Path;
use std::process::ExitCode;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;

use bml_db::library::{load_library, Library};
use bml_library::fulltext::FulltextEnd;
use bml_library::status::library_status;
use bml_library::{
    try_lock_worker, updated_within, Phase, PhaseSet, Pipeline, UpdateOptions, UpdateReport,
};
use bml_pgserver::envfile::{read_conn_info, APP_ENV_FILE_NAME};
use bml_pgserver::init::connect;
use bml_pgserver::schedule::{
    schedule_updates, unschedule_updates, update_log_path, DAILY_RUN_HOUR, WEEKLY_DAYS,
};
use chrono::NaiveDate;
use clap::{Subcommand, ValueEnum};
use postgres::Client;

use crate::server::{say, EXIT_FAILED, EXIT_HEALTHY, EXIT_NOT_SET_UP};

/// Exit code of `update`: it stopped before its work was done (Ctrl-C, or
/// medRxiv asked us to slow down); running it again carries on.
pub const EXIT_STOPPED_EARLY: u8 = 4;

/// `bml library …` subcommands.
#[derive(Subcommand)]
pub enum LibraryCommand {
    /// Bring the library up to date with medRxiv (safe to stop and run again).
    Update {
        /// The first posting day to download (default: medRxiv's first day).
        #[arg(long, value_name = "YYYY-MM-DD")]
        from: Option<NaiveDate>,
        /// Leave out a phase; repeatable.
        #[arg(long = "skip", value_enum, value_name = "PHASE")]
        skip: Vec<SkipPhase>,
        /// Do nothing if the last complete update is younger than DAYS days
        /// (what a scheduled run passes).
        #[arg(long, value_name = "DAYS",
              value_parser = clap::value_parser!(u32).range(1..=i64::from(MAX_SCHEDULE_DAYS)))]
        if_older_than: Option<u32>,
    },
    /// Show what the library holds and how the last update went.
    Status,
    /// Run updates automatically, or only when asked.
    #[command(subcommand)]
    Schedule(ScheduleWhen),
}

/// The longest schedule interval accepted, in days.
pub const MAX_SCHEDULE_DAYS: u32 = 365;

/// `bml library schedule …`.
#[derive(Subcommand)]
pub enum ScheduleWhen {
    /// Once a week (the default schedule).
    Weekly,
    /// Every DAYS days.
    Every {
        /// Days between updates (1 is daily).
        #[arg(value_parser = clap::value_parser!(u32).range(1..=i64::from(MAX_SCHEDULE_DAYS)))]
        days: u32,
    },
    /// Only when you run `bml library update` (removes the schedule).
    Manual,
}

/// Phases a person may leave out.
#[derive(Clone, Copy, ValueEnum)]
pub enum SkipPhase {
    /// Paper details from medRxiv, day by day.
    Metadata,
    /// Full text (JATS XML or PDF), paper by paper.
    Fulltext,
    /// Chunking and embedding for search.
    Index,
}

impl SkipPhase {
    fn phase(self) -> Phase {
        match self {
            SkipPhase::Metadata => Phase::Metadata,
            SkipPhase::Fulltext => Phase::Fulltext,
            SkipPhase::Index => Phase::Index,
        }
    }
}

/// Why a library command could not run.
#[derive(Debug, thiserror::Error)]
pub enum LibraryCliError {
    /// The library record could not be read.
    #[error(transparent)]
    Library(#[from] bml_db::library::LibraryError),
    /// The database settings could not be read.
    #[error(transparent)]
    PgServer(#[from] bml_pgserver::error::PgServerError),
    /// The worker lock could not be taken.
    #[error("could not take the library's update lock: {0}")]
    Lock(std::io::Error),
    /// Updating the schema failed.
    #[error("updating the library's database failed: {0}. Run the command again; finished updates are kept.")]
    Migrate(bmlib::db::DbError),
    /// A status query failed.
    #[error(transparent)]
    Pipeline(#[from] bml_library::PipelineError),
}

/// Run `command` with configuration in `config_dir`.
pub fn run(command: LibraryCommand, config_dir: &Path) -> Result<ExitCode, LibraryCliError> {
    let Some(library) = load_library(config_dir)? else {
        eprintln!("No library is set up yet. Run `bml setup` first.");
        return Ok(ExitCode::from(EXIT_NOT_SET_UP));
    };
    match command {
        LibraryCommand::Update {
            from,
            skip,
            if_older_than,
        } => {
            let phases = skip
                .iter()
                .fold(PhaseSet::all(), |set, s| set.without(s.phase()));
            update(&library, config_dir, from, phases, if_older_than)
        }
        LibraryCommand::Status => status(&library, config_dir),
        LibraryCommand::Schedule(when) => schedule(when, config_dir),
    }
}

fn schedule(when: ScheduleWhen, config_dir: &Path) -> Result<ExitCode, LibraryCliError> {
    let days = match when {
        ScheduleWhen::Weekly => WEEKLY_DAYS,
        ScheduleWhen::Every { days } => days,
        ScheduleWhen::Manual => {
            unschedule_updates()?;
            say!("Updates now run only when you run `bml library update`.");
            return Ok(ExitCode::from(EXIT_HEALTHY));
        }
    };
    let exe = std::env::current_exe().map_err(bml_pgserver::error::PgServerError::Io)?;
    schedule_updates(&exe, config_dir, days)?;
    say!(
        "The library will be brought up to date every {days} day(s) by {} (checked daily at \
         {DAILY_RUN_HOUR}:00 and at login; an unfinished update carries on the next day).",
        exe.display()
    );
    match update_log_path(config_dir) {
        Some(log) => say!("Output goes to {}.", log.display()),
        None => say!("Scheduled runs keep no log here; `bml library status` shows how they went."),
    }
    Ok(ExitCode::from(EXIT_HEALTHY))
}

/// The library's database connection, or the exit code to return.
fn database(config_dir: &Path) -> Result<Result<Client, ExitCode>, LibraryCliError> {
    let Some(info) = read_conn_info(&config_dir.join(APP_ENV_FILE_NAME))
        .map_err(bml_pgserver::error::PgServerError::from)?
    else {
        eprintln!("No database is set up yet. Run `bml setup` first.");
        return Ok(Err(ExitCode::from(EXIT_NOT_SET_UP)));
    };
    match connect(&info) {
        Ok(client) => Ok(Ok(client)),
        Err(e) => {
            eprintln!("error: {e}. Is the database running? Try `bml server start`.");
            Ok(Err(ExitCode::from(EXIT_FAILED)))
        }
    }
}

fn update(
    library: &Library,
    config_dir: &Path,
    from: Option<NaiveDate>,
    phases: PhaseSet,
    if_older_than: Option<u32>,
) -> Result<ExitCode, LibraryCliError> {
    let Some(_lock) = try_lock_worker(&library.dir).map_err(LibraryCliError::Lock)? else {
        say!("An update is already running; this one has nothing to do.");
        return Ok(ExitCode::from(EXIT_HEALTHY));
    };
    let mut db = match database(config_dir)? {
        Ok(db) => db,
        Err(code) => return Ok(code),
    };
    bml_db::migrate(&mut db).map_err(LibraryCliError::Migrate)?;
    if let Some(days) = if_older_than {
        if updated_within(&mut db, days)? {
            say!("The library was brought up to date less than {days} day(s) ago; nothing to do.");
            return Ok(ExitCode::from(EXIT_HEALTHY));
        }
    }

    let stop = Arc::new(AtomicBool::new(false));
    let flag = stop.clone();
    if let Err(e) = ctrlc::set_handler(move || {
        flag.store(true, Ordering::Relaxed);
        eprintln!("Stopping after the paper in flight…");
    }) {
        eprintln!("warning: Ctrl-C will stop the update at once ({e})");
    }
    let pipeline = Pipeline::new(library.cache(), bml_setup::gguf_path(config_dir));
    let options = UpdateOptions {
        from,
        phases,
        stop: &stop,
    };
    let report = pipeline.update(&mut db, &options, &mut |p| {
        say!("[{}] {}", p.phase.as_str(), p.message);
    });
    summarise(&report);
    Ok(ExitCode::from(if report.failed() {
        EXIT_FAILED
    } else if report.stopped_early() {
        EXIT_STOPPED_EARLY
    } else {
        EXIT_HEALTHY
    }))
}

fn summarise(report: &UpdateReport) {
    if let Some(m) = &report.metadata {
        say!(
            "Metadata: {} day(s) fetched, {} new, {} updated{}",
            m.days,
            m.added,
            m.merged,
            if m.stopped { " (stopped)" } else { "" }
        );
        for line in &m.errors {
            eprintln!("  {line} (fetched again next time)");
        }
    }
    if let Some(f) = &report.fulltext {
        say!(
            "Full text: {} tried, {} JATS, {} PDF, {} abstract only ({} may pass, {} lasting), {} new version(s)",
            f.tried,
            f.jats,
            f.pdf,
            f.lasting + f.passing,
            f.passing,
            f.lasting,
            f.replaced
        );
        match &f.end {
            FulltextEnd::Done => {}
            FulltextEnd::Stopped => say!("  Stopped; run again to carry on."),
            FulltextEnd::RateLimited { until } => {
                say!("  medRxiv asked us to slow down; full text resumes after {until}.");
            }
        }
    }
    if let Some(i) = &report.index {
        say!(
            "Index: {} paper(s) indexed ({} with full text), {} chunks{}",
            i.indexed,
            i.fulltext,
            i.chunks,
            if i.stopped { " (stopped)" } else { "" }
        );
        for line in &i.failed {
            eprintln!("  {line} (tried again next time)");
        }
    }
    for (phase, message) in &report.failures {
        eprintln!("error: {} phase: {message}", phase.as_str());
    }
}

fn status(library: &Library, config_dir: &Path) -> Result<ExitCode, LibraryCliError> {
    let mut db = match database(config_dir)? {
        Ok(db) => db,
        Err(code) => return Ok(code),
    };
    bml_db::migrate(&mut db).map_err(LibraryCliError::Migrate)?;
    let s = library_status(&mut db, &library.cache())?;
    say!("Library: {}", library.dir.display());
    say!("Papers: {}", s.papers);
    say!(
        "Full text: {} JATS, {} PDF, {} abstract only, {} not tried yet",
        s.jats,
        s.pdf,
        s.abstract_only,
        s.not_tried
    );
    for r in &s.reasons {
        say!("  {:>7} {} ({})", r.papers, r.reason, r.kind);
    }
    say!(
        "Index: {} paper(s) indexed, {} to do, {} chunks",
        s.indexed,
        s.to_index,
        s.chunks
    );
    say!(
        "Metadata days: {} complete, {} to fetch again",
        s.days_complete,
        s.days_failed
    );
    say!(
        "Last complete update: {}",
        s.last_update.as_deref().unwrap_or("never")
    );
    if let Some(until) = &s.rate_limited_until {
        say!("Full text paused after a rate limit until {until}");
    }
    if s.pending_deletions > 0 {
        say!(
            "{} old file(s) waiting to be deleted (the next update does it)",
            s.pending_deletions
        );
    }
    if s.unreferenced_files > 0 {
        say!(
            "{} file(s) in the documents folder belong to no paper (kept)",
            s.unreferenced_files
        );
    }
    Ok(ExitCode::from(EXIT_HEALTHY))
}
