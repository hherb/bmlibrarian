//! One function per setup step.

use std::path::{Path, PathBuf};

use bml_pgserver::envfile::{read_conn_info, ADMIN_ENV_FILE_NAME, APP_ENV_FILE_NAME};
use bml_pgserver::error::PgServerError;
use bml_pgserver::external::{adopt, load_external_state, ExternalRequest};
use bml_pgserver::init::{init, InitRequest};
use bml_pgserver::state::load_state;
use bmlib::embed::{download_model, verify_model, ARCTIC_EMBED_L_V2_F16};
use bmlib::publications::fetchers::registry::HttpClient;

use crate::hardware::{disk_warnings, mounts, ram_warning};
use crate::models::{model_action, ModelAction, APPROVED_MODELS};
use crate::ollama::{copy_model, installed_models, pull_model, OllamaHost, PullEvent};
use crate::ollama_install::ensure_ollama;
use crate::runner::{DatabasePlan, SetupPlan};
use crate::sweep_stale_parts;
use crate::{SetupError, StepEvent, StepId, StepOutcome};

/// The folder in the configuration folder that holds downloaded GGUF models.
pub const MODELS_DIR_NAME: &str = "models";

/// The environment variable that moves Ollama's model folder.
const OLLAMA_MODELS_ENV: &str = "OLLAMA_MODELS";

/// Ollama's model folder, relative to the home folder.
const OLLAMA_MODELS_HOME_DIR: &str = ".ollama/models";

/// Run `step`.
pub(crate) fn run(
    step: StepId,
    plan: &SetupPlan,
    http: &dyn HttpClient,
    report: &mut dyn FnMut(StepEvent),
) -> Result<StepOutcome, SetupError> {
    match step {
        StepId::Hardware => hardware(plan, http, report),
        StepId::Database => database(plan, report),
        StepId::Autostart => autostart(plan),
        StepId::Ollama => ensure_ollama(http, &plan.ollama_host, &plan.config_dir, report),
        StepId::Models => models(plan, http, report),
        StepId::EmbeddingModel => embedding_model(plan, report),
    }
}

/// `Installed` if this run changed something, else `AlreadyPresent`.
fn created(created: bool) -> StepOutcome {
    if created {
        StepOutcome::Installed
    } else {
        StepOutcome::AlreadyPresent
    }
}

/// Where the embedding model's GGUF file lives in `config_dir`.
fn gguf_path(config_dir: &Path) -> PathBuf {
    config_dir
        .join(MODELS_DIR_NAME)
        .join(ARCTIC_EMBED_L_V2_F16.file)
}

/// Warn about too little memory or disk; only a missing memory reading fails.
fn hardware(
    plan: &SetupPlan,
    http: &dyn HttpClient,
    report: &mut dyn FnMut(StepEvent),
) -> Result<StepOutcome, SetupError> {
    let step = StepId::Hardware;
    let mut warnings = Vec::new();
    warnings.extend(ram_warning(bml_pgserver::control::total_memory_bytes()?));

    // A listing failure means we assume every model is missing.
    let installed = installed_models(http, &plan.ollama_host).unwrap_or_default();
    let model_bytes: u64 = APPROVED_MODELS
        .iter()
        .filter(|m| model_action(m, &installed) != ModelAction::Present)
        .map(|m| m.approx_bytes)
        .sum();
    let mut needs = Vec::new();
    let ollama_dir = std::env::var_os(OLLAMA_MODELS_ENV)
        .map(PathBuf::from)
        .or_else(|| std::env::home_dir().map(|h| h.join(OLLAMA_MODELS_HOME_DIR)));
    if let (Some(dir), true) = (ollama_dir, model_bytes > 0) {
        needs.push((dir, model_bytes));
    }
    if !gguf_path(&plan.config_dir).exists() {
        needs.push((
            plan.config_dir.join(MODELS_DIR_NAME),
            ARCTIC_EMBED_L_V2_F16.size,
        ));
    }
    warnings.extend(disk_warnings(&needs, &mounts()));
    for w in warnings {
        report(StepEvent::Warning {
            step,
            message: w.to_string(),
        });
    }
    Ok(StepOutcome::AlreadyPresent)
}

/// The superuser request for the saved existing server, with its password
/// from `bml-admin.env`; `None` if no existing server is saved.
fn saved_external_request(config_dir: &Path) -> Result<Option<ExternalRequest>, SetupError> {
    let Some(state) = load_external_state(config_dir).map_err(PgServerError::from)? else {
        return Ok(None);
    };
    let admin = read_conn_info(&config_dir.join(ADMIN_ENV_FILE_NAME))
        .map_err(PgServerError::from)?
        .ok_or_else(|| SetupError::Other {
            message: format!(
                "The existing server is saved but {ADMIN_ENV_FILE_NAME} is missing from {}; run `bml setup --existing-server` again.",
                config_dir.display()
            ),
        })?;
    Ok(Some(ExternalRequest {
        host: state.host,
        port: state.port,
        superuser: state.superuser,
        password: admin.password,
        needs_pg_search: !cfg!(windows),
    }))
}

/// Warnings for a database that works but lacks something; returns the outcome.
fn database_outcome(
    created_now: bool,
    pg_search: bool,
    app_password_reset: bool,
    report: &mut dyn FnMut(StepEvent),
) -> StepOutcome {
    let step = StepId::Database;
    if !pg_search {
        report(StepEvent::Warning {
            step,
            message: "pg_search is not installed, so the database has no BM25 search index. For a private server, run setup again with --extension-dir pointing at a pg_search build.".into(),
        });
    }
    if app_password_reset {
        report(StepEvent::Warning {
            step,
            message: format!("the server refused the password in {APP_ENV_FILE_NAME}, so it was reset; other copies of the old password no longer work."),
        });
    }
    created(created_now)
}

/// Set up the chosen database, or resume the saved one.
fn database(
    plan: &SetupPlan,
    report: &mut dyn FnMut(StepEvent),
) -> Result<StepOutcome, SetupError> {
    let dir = &plan.config_dir;
    let private = |req: &InitRequest, report: &mut dyn FnMut(StepEvent)| {
        let o = init(req, dir)?;
        Ok(database_outcome(
            o.created,
            o.pg_search,
            o.app_password_reset,
            report,
        ))
    };
    let existing = |req: &ExternalRequest, report: &mut dyn FnMut(StepEvent)| {
        let o = adopt(req, dir)?;
        Ok(database_outcome(
            o.created,
            o.pg_search,
            o.app_password_reset,
            report,
        ))
    };
    match &plan.database {
        Some(DatabasePlan::Private(req)) => private(req, report),
        Some(DatabasePlan::Existing(req)) => existing(req, report),
        None => {
            if let Some(s) = load_state(dir).map_err(PgServerError::from)? {
                return private(
                    &InitRequest {
                        bindir: s.bindir,
                        data_dir: s.data_dir,
                        extension_dirs: s.extension_dirs,
                    },
                    report,
                );
            }
            match saved_external_request(dir)? {
                Some(req) => existing(&req, report),
                None => Ok(StepOutcome::Failed(
                    "no database chosen; pass --pg-bindir or --existing-server".into(),
                )),
            }
        }
    }
}

/// Register the private server to start at login (skipped for an existing server).
fn autostart(plan: &SetupPlan) -> Result<StepOutcome, SetupError> {
    let dir = &plan.config_dir;
    let existing_server = matches!(plan.database, Some(DatabasePlan::Existing(_)))
        || (plan.database.is_none()
            && load_state(dir).map_err(PgServerError::from)?.is_none()
            && load_external_state(dir)
                .map_err(PgServerError::from)?
                .is_some());
    if existing_server {
        return Ok(StepOutcome::Skipped {
            reason: "existing server is not managed by bml".into(),
        });
    }
    if load_state(dir).map_err(PgServerError::from)?.is_none() {
        return Ok(StepOutcome::Failed(
            "the private database is not set up; run the Database step first (`bml setup`)".into(),
        ));
    }
    let exe = std::env::current_exe().map_err(|source| SetupError::Io {
        path: PathBuf::from("the bml program"),
        source,
    })?;
    if bml_pgserver::autostart::is_enabled(&exe, dir)? {
        return Ok(StepOutcome::AlreadyPresent);
    }
    bml_pgserver::autostart::enable(&exe, dir)?;
    Ok(StepOutcome::Installed)
}

/// Pull each approved model that is missing and copy it to its approved name.
fn models(
    plan: &SetupPlan,
    http: &dyn HttpClient,
    report: &mut dyn FnMut(StepEvent),
) -> Result<StepOutcome, SetupError> {
    let step = StepId::Models;
    let host: &OllamaHost = &plan.ollama_host;
    let mut changed = false;
    for model in &APPROVED_MODELS {
        let installed = installed_models(http, host)?;
        let action = model_action(model, &installed);
        if matches!(action, ModelAction::Pull | ModelAction::PullThenCopy) {
            let detail = format!("Downloading {}", model.pull_as);
            pull_model(http, host, model.pull_as, &mut |e| {
                if let PullEvent::Progress {
                    completed, total, ..
                } = e
                {
                    report(StepEvent::Progress {
                        step,
                        detail: detail.clone(),
                        done: *completed,
                        total: *total,
                    });
                }
            })?;
            changed = true;
        }
        if matches!(action, ModelAction::Copy | ModelAction::PullThenCopy) {
            // Re-list: the copy needs the name Ollama actually stored.
            let installed = installed_models(http, host)?;
            let source = installed
                .iter()
                .find(|i| crate::ollama::same_model(i, model.pull_as))
                .map_or(model.pull_as, String::as_str);
            copy_model(http, host, source, model.name)?;
            changed = true;
        }
    }
    Ok(created(changed))
}

/// Download and verify the embedding model's GGUF file, unless it is already good.
fn embedding_model(
    plan: &SetupPlan,
    report: &mut dyn FnMut(StepEvent),
) -> Result<StepOutcome, SetupError> {
    let model = &ARCTIC_EMBED_L_V2_F16;
    if verify_model(&gguf_path(&plan.config_dir), model).is_ok() {
        return Ok(StepOutcome::AlreadyPresent);
    }
    let models_dir = plan.config_dir.join(MODELS_DIR_NAME);
    sweep_stale_parts(&models_dir, model.file)?;
    download_model(model, &models_dir, &mut |done, total| {
        report(StepEvent::Progress {
            step: StepId::EmbeddingModel,
            detail: "Downloading the embedding model".into(),
            done,
            total,
        });
        true
    })?;
    Ok(StepOutcome::Installed)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::ollama::parse_ollama_host;
    use crate::test_support::Fake;
    use std::collections::BTreeSet;

    const PULLED_AS: &str = "medgemma1.5:4b-it-q8_0";
    const APPROVED_AS: &str = "medgemma4B_it_q8:latest";

    fn plan(dir: &Path) -> SetupPlan {
        SetupPlan {
            config_dir: dir.to_path_buf(),
            database: None,
            ollama_host: parse_ollama_host(Some("http://127.0.0.1:11434")).unwrap(),
            skip: BTreeSet::new(),
        }
    }

    fn tags(names: &[&str]) -> (u16, String) {
        let models: Vec<_> = names
            .iter()
            .map(|n| serde_json::json!({"model": n}))
            .collect();
        (200, serde_json::json!({"models": models}).to_string())
    }

    #[test]
    fn autostart_without_private_database_fails_and_writes_nothing() {
        let dir = tempfile::tempdir().unwrap();
        let outcome = autostart(&plan(dir.path())).unwrap();
        assert!(
            matches!(&outcome, StepOutcome::Failed(m) if m.contains("Database step")),
            "{outcome:?}"
        );
        assert_eq!(std::fs::read_dir(dir.path()).unwrap().count(), 0);
    }

    #[test]
    fn saved_existing_server_without_admin_credentials_fails() {
        let dir = tempfile::tempdir().unwrap();
        std::fs::write(
            dir.path()
                .join(bml_pgserver::external::EXTERNAL_STATE_FILE_NAME),
            r#"{"host":"127.0.0.1","port":5432,"superuser":"postgres"}"#,
        )
        .unwrap();
        let e = database(&plan(dir.path()), &mut |_| {}).unwrap_err();
        assert!(
            matches!(&e, SetupError::Other { message } if message.contains("missing")),
            "{e}"
        );
    }

    #[test]
    fn database_outcome_warns_about_missing_pg_search_and_password_reset() {
        let mut warnings = Vec::new();
        let outcome = database_outcome(false, false, true, &mut |e| {
            if let StepEvent::Warning { message, .. } = e {
                warnings.push(message);
            }
        });
        assert_eq!(outcome, StepOutcome::AlreadyPresent);
        assert_eq!(warnings.len(), 2, "{warnings:?}");
        assert!(warnings[0].contains("pg_search"));
        assert!(warnings[1].contains("reset"));
        let mut quiet = true;
        assert_eq!(
            database_outcome(true, true, false, &mut |_| quiet = false),
            StepOutcome::Installed
        );
        assert!(quiet);
    }

    #[test]
    fn models_copies_the_pulled_name_to_the_approved_name() {
        let dir = tempfile::tempdir().unwrap();
        let mut fake = Fake::new();
        fake.get = Ok(tags(&["gpt-oss:20b", PULLED_AS]));
        fake.post = Some((200, String::new()));
        let outcome = models(&plan(dir.path()), &fake, &mut |_| {}).unwrap();
        assert_eq!(outcome, StepOutcome::Installed);
        let urls = fake.urls.borrow();
        assert!(urls.last().unwrap().ends_with("/api/copy"), "{urls:?}");
        assert!(!urls.iter().any(|u| u.ends_with("/api/pull")), "{urls:?}");
        assert_eq!(
            fake.bodies.borrow().last().unwrap(),
            &serde_json::json!({"source": PULLED_AS, "destination": APPROVED_AS})
        );
    }

    #[test]
    fn models_pulls_then_copies() {
        let dir = tempfile::tempdir().unwrap();
        let mut fake = Fake::new();
        // Listings: gpt-oss present, then (for the other model) tags before
        // and after the pull.
        fake.get_script.borrow_mut().extend([
            tags(&["gpt-oss:20b"]),
            tags(&["gpt-oss:20b"]),
            tags(&["gpt-oss:20b", PULLED_AS]),
        ]);
        fake.get = Ok(tags(&["gpt-oss:20b", PULLED_AS]));
        fake.stream = Some((200, "{\"status\":\"success\"}\n".into()));
        fake.post = Some((200, String::new()));
        let outcome = models(&plan(dir.path()), &fake, &mut |_| {}).unwrap();
        assert_eq!(outcome, StepOutcome::Installed);
        let urls = fake.urls.borrow();
        let tail: Vec<&str> = urls
            .iter()
            .rev()
            .take(3)
            .map(|u| u.rsplit('/').next().unwrap())
            .collect();
        assert_eq!(tail, ["copy", "tags", "pull"], "{urls:?}");
        assert_eq!(
            fake.bodies.borrow().last().unwrap()["source"],
            serde_json::json!(PULLED_AS)
        );
    }
}
