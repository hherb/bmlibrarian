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
use crate::models::{model_action, ApprovedModel, ModelAction, APPROVED_MODELS};
use crate::ollama::{copy_model, installed_models, pull_model, OllamaHost, PullEvent};
use crate::ollama_install::ensure_ollama;
use crate::pgdist::{
    bundled_release, ensure_pgdist, host_target, no_bundle_message, PgdistRelease,
};
use crate::runner::{DatabasePlan, SetupPlan, DEFAULT_DATA_DIR_NAME};
use crate::{report_warnings, sweep_stale_parts};
use crate::{SetupError, StepEvent, StepId, StepOutcome};

/// The folder in the configuration folder that holds downloaded GGUF models.
pub const MODELS_DIR_NAME: &str = "models";

/// The environment variable that moves Ollama's model folder.
const OLLAMA_MODELS_ENV: &str = "OLLAMA_MODELS";

/// Ollama's model folder, relative to the home folder.
const OLLAMA_MODELS_HOME_DIR: &str = ".ollama/models";

/// Home folder of the `ollama` system user that Ollama's Linux install
/// script creates; its service keeps the models there.
const LINUX_OLLAMA_SERVICE_HOME: &str = "/usr/share/ollama";

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
    // A remote Ollama keeps its models on its own disks.
    let ollama_dir = ollama_models_dir(
        // Ollama treats an empty value as unset.
        std::env::var_os(OLLAMA_MODELS_ENV)
            .filter(|v| !v.is_empty())
            .map(PathBuf::from),
        std::env::home_dir(),
        cfg!(target_os = "linux").then_some(Path::new(LINUX_OLLAMA_SERVICE_HOME)),
    )
    .filter(|_| plan.ollama_host.loopback);
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
    let warnings = warnings.iter().map(ToString::to_string).collect();
    Ok(report_warnings(
        step,
        warnings,
        StepOutcome::AlreadyPresent,
        report,
    ))
}

/// Where a local Ollama keeps its models: `OLLAMA_MODELS` if set; else, when
/// `service_home` is given (Linux), `<service_home>/.ollama/models` if
/// `service_home` exists or `~/.ollama/models` does not (a fresh install
/// uses the service); else the user's own `~/.ollama/models`.
fn ollama_models_dir(
    env: Option<PathBuf>,
    home: Option<PathBuf>,
    service_home: Option<&Path>,
) -> Option<PathBuf> {
    if env.is_some() {
        return env;
    }
    let own = home.map(|h| h.join(OLLAMA_MODELS_HOME_DIR));
    match service_home {
        Some(service) if service.exists() || !own.as_ref().is_some_and(|o| o.exists()) => {
            Some(service.join(OLLAMA_MODELS_HOME_DIR))
        }
        _ => own,
    }
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

/// Warnings for a database that works but lacks something; returns the
/// outcome, which repeats them.
fn database_outcome(
    created_now: bool,
    pg_search: bool,
    app_password_reset: bool,
    report: &mut dyn FnMut(StepEvent),
) -> StepOutcome {
    let mut warnings = Vec::new();
    if !pg_search {
        warnings.push("pg_search is not installed, so the database has no BM25 search index. To add it, run setup again with --pg-bindir and an --extension-dir holding a pg_search build.".to_string());
    }
    if app_password_reset {
        warnings.push(format!("the server refused the password in {APP_ENV_FILE_NAME}, so it was reset; other copies of the old password no longer work."));
    }
    report_warnings(StepId::Database, warnings, created(created_now), report)
}

/// Set up (or resume) the private server `req` describes.
fn private_database(
    req: &InitRequest,
    config_dir: &Path,
    report: &mut dyn FnMut(StepEvent),
) -> Result<StepOutcome, SetupError> {
    let o = init(req, config_dir)?;
    Ok(database_outcome(
        o.created,
        o.pg_search,
        o.app_password_reset,
        report,
    ))
}

/// A new private server from `release`'s bundle for `target` (`None`: this
/// computer has no bundle target), with its data in `data_dir`.
fn bundled_database(
    config_dir: &Path,
    data_dir: &Path,
    release: &PgdistRelease,
    target: Option<&str>,
    report: &mut dyn FnMut(StepEvent),
) -> Result<StepOutcome, SetupError> {
    let Some(target) = target else {
        return Ok(StepOutcome::Failed(no_bundle_message(None)));
    };
    if !release.assets.contains_key(target) {
        return Ok(StepOutcome::Failed(no_bundle_message(Some(target))));
    }
    let (pg, _) = ensure_pgdist(config_dir, release, target, &mut |done, total| {
        report(StepEvent::Progress {
            step: StepId::Database,
            detail: "Downloading the database".into(),
            done,
            total,
        });
    })?;
    let req = InitRequest {
        bindir: pg.bindir(),
        data_dir: data_dir.to_path_buf(),
        extension_dirs: vec![pg.extension_dir()],
    };
    private_database(&req, config_dir, report)
}

/// Set up the chosen database, or resume the saved one.
fn database(
    plan: &SetupPlan,
    report: &mut dyn FnMut(StepEvent),
) -> Result<StepOutcome, SetupError> {
    let dir = &plan.config_dir;
    let private =
        |req: &InitRequest, report: &mut dyn FnMut(StepEvent)| private_database(req, dir, report);
    let existing = |req: &ExternalRequest, report: &mut dyn FnMut(StepEvent)| {
        let o = adopt(req, dir)?;
        Ok(database_outcome(
            o.created,
            o.pg_search,
            o.app_password_reset,
            report,
        ))
    };
    // The saved private server, else the saved existing one, else `None`.
    let resume_saved = |report: &mut dyn FnMut(StepEvent)| {
        if let Some(s) = load_state(dir).map_err(PgServerError::from)? {
            let req = InitRequest {
                bindir: s.bindir,
                data_dir: s.data_dir,
                extension_dirs: s.extension_dirs,
            };
            return private(&req, report).map(Some);
        }
        match saved_external_request(dir)? {
            Some(req) => existing(&req, report).map(Some),
            None => Ok(None),
        }
    };
    match &plan.database {
        Some(DatabasePlan::Private(req)) => private(req, report),
        Some(DatabasePlan::Existing(req)) => existing(req, report),
        Some(DatabasePlan::Bundled { data_dir }) => {
            if let Some(wanted) = data_dir {
                // A folder the person named must not be silently replaced by
                // the saved server's.
                if let Some(s) = load_state(dir).map_err(PgServerError::from)? {
                    let requested =
                        std::path::absolute(wanted).map_err(|source| SetupError::Io {
                            path: wanted.clone(),
                            source,
                        })?;
                    if requested != s.data_dir {
                        return Err(PgServerError::StateMismatch {
                            field: "data folder",
                            saved: s.data_dir,
                            requested,
                        }
                        .into());
                    }
                }
                if load_external_state(dir)
                    .map_err(PgServerError::from)?
                    .is_some()
                {
                    return Ok(StepOutcome::Failed(
                        "--data-dir does not apply: this setup uses an existing server. Run setup without --data-dir.".into(),
                    ));
                }
            }
            if let Some(outcome) = resume_saved(report)? {
                return Ok(outcome);
            }
            let data_dir = data_dir
                .clone()
                .unwrap_or_else(|| dir.join(DEFAULT_DATA_DIR_NAME));
            bundled_database(dir, &data_dir, &bundled_release()?, host_target(), report)
        }
        None => Ok(resume_saved(report)?.unwrap_or_else(|| {
            StepOutcome::Failed("no database chosen; pass --pg-bindir or --existing-server".into())
        })),
    }
}

/// Register the private server to start at login (skipped for an existing server).
fn autostart(plan: &SetupPlan) -> Result<StepOutcome, SetupError> {
    let dir = &plan.config_dir;
    let existing_server = matches!(plan.database, Some(DatabasePlan::Existing(_)))
        // No plan, or the bundled plan, resumes whatever was saved.
        || (matches!(plan.database, None | Some(DatabasePlan::Bundled { .. }))
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
    let exe = std::env::current_exe().map_err(|e| SetupError::Other {
        message: format!(
            "Could not find where the bml program itself is ({e}), which start at login needs. Run setup from an installed bml, or pass --skip autostart."
        ),
    })?;
    if bml_pgserver::autostart::is_enabled(&exe, dir)? {
        return Ok(StepOutcome::AlreadyPresent);
    }
    bml_pgserver::autostart::enable(&exe, dir)?;
    Ok(StepOutcome::Installed)
}

/// Pull each approved model that is missing and copy it to its approved name.
/// A failure for one model does not stop the others; the step then fails
/// with every model's error.
fn models(
    plan: &SetupPlan,
    http: &dyn HttpClient,
    report: &mut dyn FnMut(StepEvent),
) -> Result<StepOutcome, SetupError> {
    let mut changed = false;
    let mut errors = Vec::new();
    for model in &APPROVED_MODELS {
        match ensure_model(model, plan, http, report) {
            Ok(c) => changed |= c,
            Err(e) => errors.push(e.to_string()),
        }
    }
    // An unreachable Ollama gives every model the same error.
    errors.dedup();
    if errors.is_empty() {
        Ok(created(changed))
    } else {
        Ok(StepOutcome::Failed(errors.join(" ")))
    }
}

/// Pull and copy `model` as needed; `true` if anything changed.
fn ensure_model(
    model: &ApprovedModel,
    plan: &SetupPlan,
    http: &dyn HttpClient,
    report: &mut dyn FnMut(StepEvent),
) -> Result<bool, SetupError> {
    let step = StepId::Models;
    let host: &OllamaHost = &plan.ollama_host;
    let action = model_action(model, &installed_models(http, host)?);
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
    }
    if matches!(action, ModelAction::Copy | ModelAction::PullThenCopy) {
        // Re-list: the copy needs the name Ollama actually stored.
        let installed = installed_models(http, host)?;
        let source = installed
            .iter()
            .find(|i| crate::ollama::same_model(i, model.pull_as))
            .map_or(model.pull_as, String::as_str);
        copy_model(http, host, source, model.name)?;
    }
    Ok(action != ModelAction::Present)
}

/// Download and verify the embedding model's GGUF file, unless it is already good.
fn embedding_model(
    plan: &SetupPlan,
    report: &mut dyn FnMut(StepEvent),
) -> Result<StepOutcome, SetupError> {
    let model = &ARCTIC_EMBED_L_V2_F16;
    let good = || verify_model(&gguf_path(&plan.config_dir), model).is_ok();
    if good() {
        return Ok(StepOutcome::AlreadyPresent);
    }
    let models_dir = plan.config_dir.join(MODELS_DIR_NAME);
    let _lock = crate::lock_downloads(&plan.config_dir)?;
    // Another setup may have finished the download while this one waited.
    if good() {
        return Ok(StepOutcome::AlreadyPresent);
    }
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

    /// A plan for the bundled database, with `data_dir` if given.
    fn bundled(dir: &Path, data_dir: Option<PathBuf>) -> SetupPlan {
        SetupPlan {
            database: Some(DatabasePlan::Bundled { data_dir }),
            ..plan(dir)
        }
    }

    /// Save a private server whose (fake) bin folder `init` cannot use.
    fn save_fake_private_server(dir: &Path) {
        let saved = bml_pgserver::state::ServerState {
            bindir: dir.join("saved-fake-bin"),
            data_dir: std::path::absolute(dir.join("saved-data")).unwrap(),
            port: 5418,
            extension_dirs: vec![],
        };
        bml_pgserver::state::save_state(dir, &saved).unwrap();
    }

    #[test]
    fn bundled_plan_resumes_saved_private_server() {
        let dir = tempfile::tempdir().unwrap();
        save_fake_private_server(dir.path());
        // Resuming the saved (fake) server fails on its bin folder, which
        // proves the saved state was chosen over the bundle.
        let err = database(&bundled(dir.path(), None), &mut |_| {}).unwrap_err();
        assert!(err.to_string().contains("saved-fake-bin"), "{err}");
        assert!(!dir.path().join(crate::pgdist::PGDIST_DIR_NAME).exists());
    }

    #[test]
    fn bundled_plan_refuses_another_data_dir_than_the_saved_one() {
        let dir = tempfile::tempdir().unwrap();
        save_fake_private_server(dir.path());
        let other = dir.path().join("elsewhere");
        let err = database(&bundled(dir.path(), Some(other)), &mut |_| {})
            .unwrap_err()
            .to_string();
        assert!(
            err.contains("saved-data") && err.contains("elsewhere"),
            "{err}"
        );
        assert!(!dir.path().join(crate::pgdist::PGDIST_DIR_NAME).exists());
    }

    #[test]
    fn bundled_plan_refuses_data_dir_for_a_saved_existing_server() {
        let dir = tempfile::tempdir().unwrap();
        let state = bml_pgserver::external::ExternalState {
            host: "127.0.0.1".into(),
            port: 5432,
            superuser: "postgres".into(),
        };
        bml_pgserver::external::save_external_state(dir.path(), &state).unwrap();
        let outcome = database(
            &bundled(dir.path(), Some(dir.path().join("pgdata"))),
            &mut |_| {},
        )
        .unwrap();
        assert!(
            matches!(&outcome, StepOutcome::Failed(m) if m.contains("--data-dir")),
            "{outcome:?}"
        );
    }

    #[test]
    fn bundle_missing_for_this_computer_fails_plainly() {
        let dir = tempfile::tempdir().unwrap();
        let release = PgdistRelease {
            version: "18.6-r1".into(),
            base_url: "https://example.invalid/".into(),
            assets: std::collections::BTreeMap::new(),
        };
        let data = dir.path().join("pgdata");
        for target in [Some("aarch64-apple-darwin"), None] {
            let outcome =
                bundled_database(dir.path(), &data, &release, target, &mut |_| {}).unwrap();
            assert!(
                matches!(&outcome, StepOutcome::Failed(m) if m.contains("--pg-bindir")),
                "{outcome:?}"
            );
        }
        assert_eq!(std::fs::read_dir(dir.path()).unwrap().count(), 0);
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
        assert_eq!(outcome, StepOutcome::Warnings(warnings.clone()));
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
    fn models_present_is_already_present() {
        let dir = tempfile::tempdir().unwrap();
        let mut fake = Fake::new();
        fake.get = Ok(tags(&["gpt-oss:20b", APPROVED_AS]));
        let outcome = models(&plan(dir.path()), &fake, &mut |_| {}).unwrap();
        assert_eq!(outcome, StepOutcome::AlreadyPresent);
        assert!(fake.urls.borrow().iter().all(|u| u.ends_with("/api/tags")));
    }

    #[test]
    fn models_pulls_gpt_oss_without_copying() {
        let dir = tempfile::tempdir().unwrap();
        let mut fake = Fake::new();
        fake.get = Ok(tags(&[APPROVED_AS]));
        fake.stream = Some((200, "{\"status\":\"success\"}\n".into()));
        let outcome = models(&plan(dir.path()), &fake, &mut |_| {}).unwrap();
        assert_eq!(outcome, StepOutcome::Installed);
        let urls = fake.urls.borrow();
        let ends: Vec<&str> = urls.iter().map(|u| u.rsplit('/').next().unwrap()).collect();
        assert_eq!(ends, ["tags", "pull", "tags"], "{urls:?}");
    }

    #[test]
    fn models_tries_every_model_and_reports_each_error() {
        let dir = tempfile::tempdir().unwrap();
        let mut fake = Fake::new();
        fake.get = Ok(tags(&[]));
        fake.stream = Some((200, "{\"error\":\"disk full\"}\n".into()));
        let outcome = models(&plan(dir.path()), &fake, &mut |_| {}).unwrap();
        let StepOutcome::Failed(message) = outcome else {
            panic!("{outcome:?}");
        };
        assert!(
            message.contains("gpt-oss:20b") && message.contains(PULLED_AS),
            "{message}"
        );
        let pulls = fake
            .urls
            .borrow()
            .iter()
            .filter(|u| u.ends_with("/api/pull"))
            .count();
        assert_eq!(pulls, 2);
    }

    #[test]
    fn ollama_models_dir_choice() {
        let tmp = tempfile::tempdir().unwrap();
        let home = tmp.path().join("home");
        let service = tmp.path().join("service");
        let own = home.join(OLLAMA_MODELS_HOME_DIR);
        let env = Some(PathBuf::from("/env"));
        assert_eq!(
            ollama_models_dir(env.clone(), Some(home.clone()), Some(&service)),
            env
        );
        assert_eq!(
            ollama_models_dir(None, Some(home.clone()), None),
            Some(own.clone())
        );
        // Neither exists yet: Linux installs the service.
        let service_models = Some(service.join(OLLAMA_MODELS_HOME_DIR));
        assert_eq!(
            ollama_models_dir(None, Some(home.clone()), Some(&service)),
            service_models
        );
        std::fs::create_dir_all(&own).unwrap();
        assert_eq!(
            ollama_models_dir(None, Some(home.clone()), Some(&service)),
            Some(own)
        );
        std::fs::create_dir_all(&service).unwrap();
        assert_eq!(
            ollama_models_dir(None, Some(home), Some(&service)),
            service_models
        );
    }

    #[test]
    fn bundled_plan_with_saved_existing_server_skips_autostart() {
        use bml_pgserver::external::{save_external_state, ExternalState};
        let dir = tempfile::tempdir().unwrap();
        save_external_state(
            dir.path(),
            &ExternalState {
                host: "127.0.0.1".into(),
                port: 5433,
                superuser: "postgres".into(),
            },
        )
        .unwrap();
        let outcome = autostart(&bundled(dir.path(), None)).unwrap();
        assert!(
            matches!(outcome, StepOutcome::Skipped { .. }),
            "{outcome:?}"
        );
    }

    #[test]
    fn saved_external_request_reads_state_and_admin_password() {
        use bml_pgserver::envfile::{render_env, ConnInfo};
        use bml_pgserver::external::{save_external_state, ExternalState};
        let dir = tempfile::tempdir().unwrap();
        assert!(saved_external_request(dir.path()).unwrap().is_none());
        save_external_state(
            dir.path(),
            &ExternalState {
                host: "::1".into(),
                port: 5433,
                superuser: "postgres".into(),
            },
        )
        .unwrap();
        let admin = ConnInfo {
            host: "::1".into(),
            port: 5433,
            dbname: "bmlibrarian".into(),
            user: "postgres".into(),
            password: "s3cret".into(),
        };
        std::fs::write(dir.path().join(ADMIN_ENV_FILE_NAME), render_env(&admin)).unwrap();
        let req = saved_external_request(dir.path()).unwrap().unwrap();
        assert_eq!(
            (req.host.as_str(), req.port, req.superuser.as_str()),
            ("::1", 5433, "postgres")
        );
        assert_eq!(req.password, "s3cret");
        assert_eq!(req.needs_pg_search, !cfg!(windows));
    }

    #[test]
    fn hardware_ignores_local_ollama_disk_for_a_remote_host() {
        let dir = tempfile::tempdir().unwrap();
        let mut p = plan(dir.path());
        p.ollama_host = parse_ollama_host(Some("http://gpu-box:11434")).unwrap();
        // Remote and unreachable: models count as missing, but no Ollama
        // disk need, so the only disk warning possible is the GGUF's.
        let mut messages = Vec::new();
        let outcome = hardware(&p, &Fake::new(), &mut |e| {
            if let StepEvent::Warning { message, .. } = e {
                messages.push(message);
            }
        })
        .unwrap();
        assert!(
            !messages.iter().any(|m| m.contains(".ollama")),
            "{messages:?}"
        );
        // The outcome repeats exactly the warnings reported.
        if messages.is_empty() {
            assert_eq!(outcome, StepOutcome::AlreadyPresent);
        } else {
            assert_eq!(outcome, StepOutcome::Warnings(messages));
        }
    }

    #[test]
    fn embedding_model_waits_for_another_setups_download() {
        let dir = tempfile::tempdir().unwrap();
        let held = crate::lock_downloads(dir.path()).unwrap();
        let models_dir = dir.path().join(MODELS_DIR_NAME);
        std::fs::create_dir_all(&models_dir).unwrap();
        let part = models_dir.join(format!(".{}.123.part", ARCTIC_EMBED_L_V2_F16.file));
        std::fs::write(&part, b"in progress").unwrap();
        let e = embedding_model(&plan(dir.path()), &mut |_| {}).unwrap_err();
        assert!(e.to_string().contains("Another BMLibrarian setup"), "{e}");
        // The other setup's part file is left alone.
        assert!(part.exists());
        drop(held);
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
