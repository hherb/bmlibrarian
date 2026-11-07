//! One function per setup step.

use std::path::{Path, PathBuf};

use bml_pgserver::envfile::{read_conn_info, ADMIN_ENV_FILE_NAME};
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
        StepId::Database => database(plan),
        StepId::Autostart => autostart(plan),
        StepId::Ollama => ensure_ollama(http, &plan.ollama_host, &plan.config_dir, report),
        StepId::Models => models(plan, http, report),
        StepId::EmbeddingModel => embedding_model(plan, report),
    }
}

fn created(created: bool) -> StepOutcome {
    if created {
        StepOutcome::Installed
    } else {
        StepOutcome::AlreadyPresent
    }
}

fn gguf_path(config_dir: &Path) -> PathBuf {
    config_dir
        .join(MODELS_DIR_NAME)
        .join(ARCTIC_EMBED_L_V2_F16.file)
}

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
        .ok_or_else(|| SetupError::Ollama {
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

fn database(plan: &SetupPlan) -> Result<StepOutcome, SetupError> {
    let dir = &plan.config_dir;
    let private = |req: &InitRequest| Ok(created(init(req, dir)?.created));
    let existing = |req: &ExternalRequest| Ok(created(adopt(req, dir)?.created));
    match &plan.database {
        Some(DatabasePlan::Private(req)) => private(req),
        Some(DatabasePlan::Existing(req)) => existing(req),
        None => {
            if let Some(s) = load_state(dir).map_err(PgServerError::from)? {
                return private(&InitRequest {
                    bindir: s.bindir,
                    data_dir: s.data_dir,
                    extension_dirs: s.extension_dirs,
                });
            }
            match saved_external_request(dir)? {
                Some(req) => existing(&req),
                None => Ok(StepOutcome::Failed(
                    "no database chosen; pass --pg-bindir or --existing-server".into(),
                )),
            }
        }
    }
}

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

fn embedding_model(
    plan: &SetupPlan,
    report: &mut dyn FnMut(StepEvent),
) -> Result<StepOutcome, SetupError> {
    let model = &ARCTIC_EMBED_L_V2_F16;
    if verify_model(&gguf_path(&plan.config_dir), model).is_ok() {
        return Ok(StepOutcome::AlreadyPresent);
    }
    download_model(
        model,
        &plan.config_dir.join(MODELS_DIR_NAME),
        &mut |done, total| {
            report(StepEvent::Progress {
                step: StepId::EmbeddingModel,
                detail: "Downloading the embedding model".into(),
                done,
                total,
            });
            true
        },
    )?;
    Ok(StepOutcome::Installed)
}
