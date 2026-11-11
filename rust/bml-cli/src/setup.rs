//! `bml setup`: check this computer and install what BMLibrarian needs.

use std::collections::{BTreeMap, BTreeSet};
use std::io::BufRead;
use std::path::{Path, PathBuf};
use std::process::ExitCode;
use std::time::{Duration, Instant};

use bml_pgserver::error::PgServerError;
use bml_pgserver::external::{check_request, is_loopback_host, ExternalRequest};
use bml_pgserver::init::InitRequest;
use bml_setup::ollama::{parse_ollama_host, pull_http_client, OLLAMA_HOST_ENV};
use bml_setup::runner::{run_setup, DatabasePlan, SetupPlan, DEFAULT_DATA_DIR_NAME};
use bml_setup::{StepEvent, StepId, StepOutcome};
use clap::{Args, ValueEnum};

use crate::server::{say, EXIT_FAILED, EXIT_HEALTHY};

/// Environment variable holding the existing server's superuser password
/// (kept out of the command line, where other users could read it).
pub const PASSWORD_ENV: &str = "BML_PG_SUPERUSER_PASSWORD";
/// Least time between two progress lines of one step.
pub const PROGRESS_PRINT_INTERVAL: Duration = Duration::from_secs(5);
/// Bytes in a megabyte, for progress lines.
const MEGABYTE: u64 = 1_000_000;

/// Steps a person may leave out (the hardware check always runs).
#[derive(Clone, Copy, ValueEnum)]
pub enum SkipStep {
    /// The PostgreSQL database.
    Database,
    /// Starting the database at login.
    Autostart,
    /// The Ollama runtime.
    Ollama,
    /// The language models.
    Models,
    /// The embedding model.
    EmbeddingModel,
}

impl SkipStep {
    /// The setup step this option leaves out.
    fn id(self) -> StepId {
        match self {
            Self::Database => StepId::Database,
            Self::Autostart => StepId::Autostart,
            Self::Ollama => StepId::Ollama,
            Self::Models => StepId::Models,
            Self::EmbeddingModel => StepId::EmbeddingModel,
        }
    }
}

/// `bml setup` options.
#[derive(Args)]
pub struct SetupArgs {
    /// Folder with the PostgreSQL 18 tools, to set up a private database from
    /// them instead of the bundled PostgreSQL.
    #[arg(long, value_name = "DIR", conflicts_with = "existing_server")]
    pg_bindir: Option<PathBuf>,
    /// Where the private database lives (default: <config folder>/pgdata); must
    /// match the saved one when a private database is already set up.
    #[arg(long, value_name = "DIR", conflicts_with = "existing_server")]
    data_dir: Option<PathBuf>,
    /// An extension folder (with lib/postgresql and share/postgresql); repeatable.
    #[arg(long = "extension-dir", value_name = "DIR", requires = "pg_bindir")]
    extension_dirs: Vec<PathBuf>,
    /// Use a PostgreSQL 18 already running on this computer, as HOST:PORT
    /// (IPv6 as [::1]:5432). The password is read from BML_PG_SUPERUSER_PASSWORD
    /// or, with --password-stdin, from standard input.
    #[arg(long, value_name = "HOST:PORT", requires = "pg_superuser")]
    existing_server: Option<String>,
    /// Superuser of the existing server.
    #[arg(long, value_name = "NAME", requires = "existing_server")]
    pg_superuser: Option<String>,
    /// Read the superuser password from one line of standard input.
    #[arg(long, requires = "existing_server")]
    password_stdin: bool,
    /// Where Ollama is (default: $OLLAMA_HOST, else the local one).
    #[arg(long, value_name = "URL")]
    ollama_host: Option<String>,
    /// Leave a step out; repeatable.
    #[arg(long = "skip", value_name = "STEP", value_enum)]
    skip: Vec<SkipStep>,
}

/// Build an error in the form `main` prints.
fn fail(message: String) -> PgServerError {
    PgServerError::Io(std::io::Error::other(message))
}

/// Split `HOST:PORT` (host may be `[v6]`), returning the bare host.
fn parse_host_port(raw: &str) -> Result<(String, u16), PgServerError> {
    let bad = || {
        fail(format!("--existing-server \"{raw}\" must look like HOST:PORT, for example 127.0.0.1:5432 or [::1]:5432"))
    };
    let (host, port) = raw.rsplit_once(':').ok_or_else(bad)?;
    let host = host
        .strip_prefix('[')
        .and_then(|h| h.strip_suffix(']'))
        .unwrap_or(host);
    let port: u16 = port.parse().map_err(|_| bad())?;
    if host.is_empty() || port == 0 {
        return Err(bad());
    }
    Ok((host.to_string(), port))
}

/// The password from the environment or one line of standard input.
fn read_password(from_stdin: bool) -> Result<String, PgServerError> {
    if from_stdin {
        let mut line = String::new();
        std::io::stdin()
            .lock()
            .read_line(&mut line)
            .map_err(PgServerError::Io)?;
        let line = line.strip_suffix('\n').unwrap_or(&line);
        return Ok(line.strip_suffix('\r').unwrap_or(line).to_string());
    }
    match std::env::var(PASSWORD_ENV) {
        Ok(p) if !p.is_empty() => Ok(p),
        _ => Err(fail(format!(
            "the existing server's password is needed: set {PASSWORD_ENV}, or pass --password-stdin and pipe it in from a password manager"
        ))),
    }
}

/// Choose the database plan from the options.
fn database_plan(
    args: &SetupArgs,
    config_dir: &Path,
) -> Result<Option<DatabasePlan>, PgServerError> {
    if let Some(raw) = &args.existing_server {
        let (host, port) = parse_host_port(raw)?;
        // Refuse a remote host before asking for a password it would not need.
        if !is_loopback_host(&host) {
            return Err(PgServerError::NotLoopback { host });
        }
        let superuser = args.pg_superuser.clone().unwrap_or_default();
        let password = read_password(args.password_stdin)?;
        let req = ExternalRequest {
            host,
            port,
            superuser,
            password,
            needs_pg_search: !cfg!(windows),
        };
        // Refuse an unusable password or superuser name before any step runs.
        check_request(&req)?;
        return Ok(Some(DatabasePlan::Existing(req)));
    }
    Ok(Some(match &args.pg_bindir {
        Some(bindir) => DatabasePlan::Private(InitRequest {
            bindir: bindir.clone(),
            data_dir: args
                .data_dir
                .clone()
                .unwrap_or_else(|| config_dir.join(DEFAULT_DATA_DIR_NAME)),
            extension_dirs: args.extension_dirs.clone(),
        }),
        // A saved server is resumed; otherwise the bundled PostgreSQL.
        None => DatabasePlan::Bundled {
            data_dir: args.data_dir.clone(),
        },
    }))
}

/// How a step ended, in words.
fn outcome_text(outcome: &StepOutcome) -> String {
    match outcome {
        StepOutcome::AlreadyPresent => "already in place".to_string(),
        StepOutcome::Installed => "installed".to_string(),
        StepOutcome::Started => "started".to_string(),
        StepOutcome::Warnings(w) if w.len() == 1 => "done, with 1 warning".to_string(),
        StepOutcome::Warnings(w) => format!("done, with {} warnings", w.len()),
        StepOutcome::Skipped { reason } => format!("skipped ({reason})"),
        StepOutcome::Failed(m) => format!("FAILED: {m}"),
    }
}

/// Print step events, throttling progress to one line per interval per step.
fn make_reporter() -> impl FnMut(StepEvent) {
    let mut last: BTreeMap<StepId, Instant> = BTreeMap::new();
    move |event| match event {
        StepEvent::Started(s) => say!("{}...", s.label()),
        // Failures and warnings go to stderr, so scripts reading it see them.
        StepEvent::Finished(s, outcome @ StepOutcome::Failed(_)) => {
            eprintln!("{}: {}", s.label(), outcome_text(&outcome));
        }
        StepEvent::Finished(s, outcome) => say!("{}: {}", s.label(), outcome_text(&outcome)),
        StepEvent::Notice { step, message } => say!("{}: {message}", step.label()),
        StepEvent::Warning { step, message } => eprintln!("Warning: {}: {message}", step.label()),
        StepEvent::Progress {
            step,
            detail,
            done,
            total,
        } => {
            let due = last
                .get(&step)
                .is_none_or(|t| t.elapsed() >= PROGRESS_PRINT_INTERVAL);
            if due {
                last.insert(step, Instant::now());
                if total > 0 {
                    say!(
                        "{}: {detail} ({} of {} MB)",
                        step.label(),
                        done / MEGABYTE,
                        total / MEGABYTE
                    );
                } else {
                    say!("{}: {detail}", step.label());
                }
            }
        }
    }
}

/// Run setup and print the summary; exit 1 if any step failed.
pub fn run(args: SetupArgs, config_dir: &Path) -> Result<ExitCode, PgServerError> {
    let host = match std::env::var(OLLAMA_HOST_ENV) {
        Ok(h) => Some(h),
        Err(std::env::VarError::NotPresent) => None,
        Err(std::env::VarError::NotUnicode(_)) => {
            return Err(fail(format!(
                "{OLLAMA_HOST_ENV} is not valid text; fix or unset it"
            )))
        }
    };
    let plan = SetupPlan {
        config_dir: config_dir.to_path_buf(),
        database: database_plan(&args, config_dir)?,
        ollama_host: parse_ollama_host(args.ollama_host.as_deref().or(host.as_deref()))
            .map_err(|e| fail(e.to_string()))?,
        skip: args.skip.iter().map(|s| s.id()).collect::<BTreeSet<_>>(),
    };
    let results = run_setup(&plan, &pull_http_client(), &mut make_reporter());
    say!("\nSummary");
    let mut failed = false;
    for (step, outcome) in &results {
        failed |= matches!(outcome, StepOutcome::Failed(_));
        let text = outcome_text(outcome);
        say!("  {:<18} {text}", step.label());
        if let StepOutcome::Warnings(warnings) = outcome {
            for w in warnings {
                say!("    - {w}");
            }
        }
    }
    if failed {
        say!("\nRun `bml setup` again to retry; finished steps are not repeated.");
        return Ok(ExitCode::from(EXIT_FAILED));
    }
    Ok(ExitCode::from(EXIT_HEALTHY))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn host_port_forms() {
        let ok = |raw: &str| parse_host_port(raw).unwrap();
        assert_eq!(ok("127.0.0.1:5432"), ("127.0.0.1".into(), 5432));
        assert_eq!(ok("[::1]:5432"), ("::1".into(), 5432));
        assert_eq!(ok("localhost:5433"), ("localhost".into(), 5433));
        for bad in ["host", ":5432", "host:0", "host:x", "[]:5432", "host:70000"] {
            assert!(parse_host_port(bad).is_err(), "{bad}");
        }
    }
}
