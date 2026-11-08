//! Adopting a PostgreSQL 18 that is already running on this computer.
//!
//! bml creates its own role and database there and never reuses or changes
//! anything it did not create. Like [`crate::init::init`] it is resumable:
//! the credentials and state files are written before anything is created.

use std::path::Path;

use postgres::Client;
use serde::{Deserialize, Serialize};

use crate::control::MIN_PG_MAJOR;
use crate::envfile::{
    generate_password, is_storable_password, is_storable_value, read_conn_info, render_env,
    ConnInfo, ADMIN_ENV_FILE_NAME, APP_ENV_FILE_NAME,
};
use crate::error::{file_error, PgServerError};
use crate::init::{
    connect_maintenance, ensure_app_login, ensure_extensions, ensure_role_and_database,
    write_if_changed, APP_ROLE, DATABASE, PG_SEARCH,
};
use crate::state::{load_json, save_json, StateError, STATE_FILE_NAME};

/// The state file naming the existing server, in the configuration folder.
pub const EXTERNAL_STATE_FILE_NAME: &str = "bml-external.json";

/// The oldest `pgvector` that is accepted.
pub const MIN_VECTOR_VERSION: (u32, u32, u32) = (0, 8, 1);

/// The `pgvector` extension's name.
const VECTOR: &str = "vector";

/// `server_version_num` is major * this + minor.
const VERSION_NUM_MAJOR_DIVISOR: i32 = 10_000;

/// Where the existing server is and who administers it.
#[derive(Serialize, Deserialize, Debug, Clone, PartialEq, Eq)]
pub struct ExternalState {
    /// The server's host (always a loopback address).
    pub host: String,
    /// Its TCP port.
    pub port: u16,
    /// The superuser bml uses to create its role and database.
    pub superuser: String,
}

/// The saved state in `config_dir`; `Ok(None)` only when there is none.
pub fn load_external_state(config_dir: &Path) -> Result<Option<ExternalState>, StateError> {
    load_json(config_dir, EXTERNAL_STATE_FILE_NAME)
}

/// Save `state` in `config_dir` (owner-only, atomic).
pub fn save_external_state(config_dir: &Path, state: &ExternalState) -> Result<(), StateError> {
    save_json(config_dir, EXTERNAL_STATE_FILE_NAME, state)
}

/// Which existing server to adopt.
#[derive(Clone, PartialEq, Eq)]
pub struct ExternalRequest {
    /// Host; must be this computer.
    pub host: String,
    /// TCP port.
    pub port: u16,
    /// A superuser of that server.
    pub superuser: String,
    /// The superuser's password.
    pub password: String,
    /// Whether `pg_search` must be there (no Windows build exists).
    pub needs_pg_search: bool,
}

impl std::fmt::Debug for ExternalRequest {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("ExternalRequest")
            .field("host", &self.host)
            .field("port", &self.port)
            .field("superuser", &self.superuser)
            .field("password", &"<redacted>")
            .field("needs_pg_search", &self.needs_pg_search)
            .finish()
    }
}

/// What [`probe`] learned about the server.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ServerFacts {
    /// `server_version_num` (180002 is 18.2).
    pub server_version_num: i32,
    /// Whether the connecting role is a superuser.
    pub is_superuser: bool,
    /// The `pgvector` version this server offers (`default_version` in
    /// `pg_available_extensions`), if it offers one.
    pub vector_version: Option<String>,
    /// Whether `pg_search` is available.
    pub pg_search_available: bool,
    /// Whether `pg_search` is in `shared_preload_libraries`.
    pub pg_search_preloaded: bool,
}

/// One reason a server cannot be used.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Unusable {
    /// The server is older than PostgreSQL 18.
    TooOld {
        /// Its major version.
        major: u32,
    },
    /// The role is not a superuser.
    NotSuperuser {
        /// The role.
        role: String,
    },
    /// `pgvector` is not installed.
    NoVector,
    /// `pgvector` is older than [`MIN_VECTOR_VERSION`].
    VectorTooOld {
        /// The version found.
        version: String,
    },
    /// `pg_search` is not installed.
    NoPgSearch,
    /// `pg_search` is installed but not loaded at server start.
    PgSearchNotPreloaded,
}

impl std::fmt::Display for Unusable {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        let (a, b, c) = MIN_VECTOR_VERSION;
        match self {
            Self::TooOld { major } => write!(
                f,
                "it is PostgreSQL {major}; install PostgreSQL {MIN_PG_MAJOR} or newer"
            ),
            Self::NotSuperuser { role } => write!(
                f,
                "{role} is not a superuser; use an administrator role such as postgres"
            ),
            Self::NoVector => write!(
                f,
                "the pgvector extension ({VECTOR}) is not installed; install pgvector {a}.{b}.{c} or newer for this PostgreSQL"
            ),
            Self::VectorTooOld { version } => write!(
                f,
                "pgvector {version} is too old; update it to {a}.{b}.{c} or newer"
            ),
            Self::NoPgSearch => write!(
                f,
                "the {PG_SEARCH} extension is not installed; install it for this PostgreSQL"
            ),
            Self::PgSearchNotPreloaded => write!(
                f,
                "{PG_SEARCH} is installed but not loaded at start; add it to shared_preload_libraries and restart that PostgreSQL"
            ),
        }
    }
}

/// Everything wrong with a server that has `facts`, connected as `role`;
/// empty means usable.
pub fn verdict(facts: &ServerFacts, role: &str, needs_pg_search: bool) -> Vec<Unusable> {
    let mut problems = Vec::new();
    let major = facts.server_version_num / VERSION_NUM_MAJOR_DIVISOR;
    if major < MIN_PG_MAJOR as i32 {
        problems.push(Unusable::TooOld {
            major: major.max(0) as u32,
        });
    }
    if !facts.is_superuser {
        problems.push(Unusable::NotSuperuser {
            role: role.to_owned(),
        });
    }
    match &facts.vector_version {
        None => problems.push(Unusable::NoVector),
        Some(version) => {
            if parse_extension_version(version).is_none_or(|v| v < MIN_VECTOR_VERSION) {
                problems.push(Unusable::VectorTooOld {
                    version: version.clone(),
                });
            }
        }
    }
    if needs_pg_search {
        if !facts.pg_search_available {
            problems.push(Unusable::NoPgSearch);
        } else if !facts.pg_search_preloaded {
            problems.push(Unusable::PgSearchNotPreloaded);
        }
    }
    problems
}

/// `"0.8.1"` as `(0, 8, 1)`; missing parts are 0 and a suffix such as
/// `-rc1` on a part is ignored. `None` if there is no leading number.
pub fn parse_extension_version(v: &str) -> Option<(u32, u32, u32)> {
    let mut parts = v.trim().split('.').map(|p| {
        let digits: String = p.chars().take_while(char::is_ascii_digit).collect();
        digits.parse::<u32>().ok()
    });
    let major = parts.next()??;
    let minor = parts.next().flatten().unwrap_or(0);
    let patch = parts.next().flatten().unwrap_or(0);
    Some((major, minor, patch))
}

/// Whether the `shared_preload_libraries` value `setting` loads `lib`
/// (quotes and a `$libdir/` prefix are ignored).
pub fn preload_list_has(setting: &str, lib: &str) -> bool {
    setting.split(',').any(|item| {
        let item = item.trim().trim_matches(|c| c == '\'' || c == '"').trim();
        item.strip_prefix("$libdir/").unwrap_or(item) == lib
    })
}

/// Whether `host` is this computer.
pub fn is_loopback_host(host: &str) -> bool {
    matches!(
        host.to_ascii_lowercase().as_str(),
        "127.0.0.1" | "::1" | "[::1]" | "localhost"
    )
}

/// Ask the server (as `admin`, through the maintenance database) what it is.
pub fn probe(admin: &ConnInfo) -> Result<ServerFacts, PgServerError> {
    let mut client: Client = connect_maintenance(admin)?;
    let server_version_num: i32 = client
        .query_one("SELECT current_setting('server_version_num')::int", &[])?
        .get(0);
    let is_superuser: bool = client
        .query_one(
            "SELECT rolsuper FROM pg_roles WHERE rolname = current_user",
            &[],
        )?
        .get(0);
    let vector_version: Option<String> = client
        .query_opt(
            "SELECT default_version FROM pg_available_extensions WHERE name = $1",
            &[&VECTOR],
        )?
        .and_then(|row| row.get(0));
    let pg_search_available = client
        .query_opt(
            "SELECT 1 FROM pg_available_extensions WHERE name = $1",
            &[&PG_SEARCH],
        )?
        .is_some();
    let preload: String = client
        .query_one("SELECT current_setting('shared_preload_libraries')", &[])?
        .get(0);
    Ok(ServerFacts {
        server_version_num,
        is_superuser,
        vector_version,
        pg_search_available,
        pg_search_preloaded: preload_list_has(&preload, PG_SEARCH),
    })
}

/// What [`adopt`] produced.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AdoptOutcome {
    /// The server now in use.
    pub state: ExternalState,
    /// Whether `pg_search` was ensured in the database.
    pub pg_search: bool,
    /// Whether this run created the role or database, reset the app role's
    /// password, or wrote `bml.env`.
    pub created: bool,
    /// Whether the app role's password was refused and reset to the one in
    /// `bml.env`.
    pub app_password_reset: bool,
}

/// Whether `path` exists.
fn exists(path: &Path) -> Result<bool, PgServerError> {
    path.try_exists().map_err(file_error(path))
}

/// `host` without the brackets of an IPv6 literal (`[::1]` → `::1`).
fn unbracket(host: &str) -> &str {
    host.strip_prefix('[')
        .and_then(|h| h.strip_suffix(']'))
        .unwrap_or(host)
}

/// Refuse a request [`adopt`] would refuse before touching anything: a host
/// that is not this computer, or a password or superuser name that cannot be
/// stored. Front ends call it before running other setup steps.
pub fn check_request(req: &ExternalRequest) -> Result<(), PgServerError> {
    if !is_loopback_host(&req.host) {
        return Err(PgServerError::NotLoopback {
            host: req.host.clone(),
        });
    }
    if !is_storable_password(&req.password) {
        return Err(PgServerError::PasswordNotStorable);
    }
    if !is_storable_value(&req.superuser) {
        return Err(PgServerError::SuperuserNotStorable);
    }
    Ok(())
}

/// Create bml's role and database on the existing server `req` names, and
/// keep its files in `config_dir`. Safe to run again after an interruption.
pub fn adopt(req: &ExternalRequest, config_dir: &Path) -> Result<AdoptOutcome, PgServerError> {
    check_request(req)?;
    // libpq and bml.env take an IPv6 host without brackets.
    let req = &ExternalRequest {
        host: unbracket(&req.host).to_owned(),
        ..req.clone()
    };
    let private_state = config_dir.join(STATE_FILE_NAME);
    if exists(&private_state)? {
        return Err(PgServerError::PrivateServerConfigured {
            state_file: private_state,
        });
    }

    let state = ExternalState {
        host: req.host.clone(),
        port: req.port,
        superuser: req.superuser.clone(),
    };
    let saved = load_external_state(config_dir)?;
    if let Some(saved) = &saved {
        if (&saved.host, saved.port) != (&state.host, state.port) {
            return Err(PgServerError::ExistingServerMismatch {
                saved: format!("{}:{}", saved.host, saved.port),
                requested: format!("{}:{}", state.host, state.port),
            });
        }
    }
    // Before connecting: never replace another server's only superuser
    // password. An interrupted adopt wrote the same host, port and user.
    let admin_env = config_dir.join(ADMIN_ENV_FILE_NAME);
    if let Some(saved) = read_conn_info(&admin_env)? {
        if (&saved.host, saved.port, &saved.user) != (&req.host, req.port, &req.superuser) {
            return Err(PgServerError::AdminCredentialsInUse {
                admin_env,
                host: saved.host,
                port: saved.port,
                user: saved.user,
            });
        }
    }

    let admin = ConnInfo {
        host: req.host.clone(),
        port: req.port,
        dbname: DATABASE.to_owned(),
        user: req.superuser.clone(),
        password: req.password.clone(),
    };
    let problems = verdict(&probe(&admin)?, &req.superuser, req.needs_pg_search);
    if !problems.is_empty() {
        return Err(PgServerError::Unusable { problems });
    }

    if saved.is_none() {
        refuse_foreign_names(&admin)?;
    }

    // Before creating anything, so an interrupted run can be repeated.
    std::fs::create_dir_all(config_dir).map_err(file_error(config_dir))?;
    write_if_changed(&admin_env, &render_env(&admin))?;
    save_external_state(config_dir, &state)?;

    let app_env = config_dir.join(APP_ENV_FILE_NAME);
    let app_password = read_conn_info(&app_env)?
        .map(|info| info.password)
        .unwrap_or_else(generate_password);
    let mut created = ensure_role_and_database(&admin, &app_password)?;
    let pg_search = ensure_extensions(&admin, req.needs_pg_search)?;
    let app = ConnInfo {
        user: APP_ROLE.to_owned(),
        password: app_password,
        ..admin.clone()
    };
    let app_password_reset = ensure_app_login(&admin, &app)?;
    created |= app_password_reset;
    created |= write_if_changed(&app_env, &render_env(&app))?;

    Ok(AdoptOutcome {
        state,
        pg_search,
        created,
        app_password_reset,
    })
}

/// Refuse when the app role or database exist before bml made them.
fn refuse_foreign_names(admin: &ConnInfo) -> Result<(), PgServerError> {
    let mut client = connect_maintenance(admin)?;
    if client
        .query_opt("SELECT 1 FROM pg_roles WHERE rolname = $1", &[&APP_ROLE])?
        .is_some()
    {
        return Err(PgServerError::NameTaken {
            kind: "role",
            name: APP_ROLE,
        });
    }
    if client
        .query_opt("SELECT 1 FROM pg_database WHERE datname = $1", &[&DATABASE])?
        .is_some()
    {
        return Err(PgServerError::NameTaken {
            kind: "database",
            name: DATABASE,
        });
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn good() -> ServerFacts {
        ServerFacts {
            server_version_num: 180002,
            is_superuser: true,
            vector_version: Some("0.8.1".into()),
            pg_search_available: true,
            pg_search_preloaded: true,
        }
    }

    #[test]
    fn good_server_is_usable() {
        assert_eq!(verdict(&good(), "postgres", true), vec![]);
    }

    #[test]
    fn verdict_lists_every_problem() {
        let facts = ServerFacts {
            server_version_num: 170005,
            is_superuser: false,
            vector_version: None,
            pg_search_available: false,
            pg_search_preloaded: false,
        };
        assert_eq!(
            verdict(&facts, "me", true),
            vec![
                Unusable::TooOld { major: 17 },
                Unusable::NotSuperuser { role: "me".into() },
                Unusable::NoVector,
                Unusable::NoPgSearch
            ]
        );
    }

    #[test]
    fn verdict_old_vector() {
        let facts = ServerFacts {
            vector_version: Some("0.7.4".into()),
            ..good()
        };
        assert_eq!(
            verdict(&facts, "p", true),
            vec![Unusable::VectorTooOld {
                version: "0.7.4".into()
            }]
        );
    }

    #[test]
    fn verdict_windows_ignores_pg_search() {
        let facts = ServerFacts {
            pg_search_available: false,
            pg_search_preloaded: false,
            ..good()
        };
        assert_eq!(verdict(&facts, "p", false), vec![]);
    }

    #[test]
    fn verdict_pg_search_not_preloaded() {
        let facts = ServerFacts {
            pg_search_preloaded: false,
            ..good()
        };
        assert_eq!(
            verdict(&facts, "p", true),
            vec![Unusable::PgSearchNotPreloaded]
        );
    }

    #[test]
    fn parse_extension_version_forms() {
        assert_eq!(parse_extension_version("0.8.1"), Some((0, 8, 1)));
        assert_eq!(parse_extension_version("0.8"), Some((0, 8, 0)));
        assert_eq!(parse_extension_version("1"), Some((1, 0, 0)));
        assert_eq!(parse_extension_version("0.9.0-rc1"), Some((0, 9, 0)));
        assert_eq!(parse_extension_version("0.10.2"), Some((0, 10, 2)));
        assert_eq!(parse_extension_version("unknown"), None);
        assert_eq!(parse_extension_version(""), None);
    }

    #[test]
    fn preload_list_forms() {
        assert!(preload_list_has("pg_search", "pg_search"));
        assert!(preload_list_has(
            "pg_stat_statements, pg_search",
            "pg_search"
        ));
        assert!(preload_list_has("'pg_search'", "pg_search"));
        assert!(preload_list_has("$libdir/pg_search", "pg_search"));
        assert!(!preload_list_has("", "pg_search"));
        assert!(!preload_list_has("pg_search_other", "pg_search"));
    }

    #[test]
    fn loopback_hosts() {
        for host in ["127.0.0.1", "::1", "[::1]", "localhost", "LocalHost"] {
            assert!(is_loopback_host(host), "{host}");
        }
        for host in ["192.168.1.5", "pg.example", "", "0.0.0.0"] {
            assert!(!is_loopback_host(host), "{host}");
        }
    }

    #[test]
    fn unusable_message_joins_problems() {
        let err = PgServerError::Unusable {
            problems: vec![Unusable::NoVector, Unusable::NoPgSearch],
        };
        let text = err.to_string();
        assert!(
            text.starts_with("This PostgreSQL can't be used: "),
            "{text}"
        );
        assert!(text.contains("; "), "{text}");
    }

    #[test]
    fn external_state_roundtrip() {
        let dir = tempfile::tempdir().unwrap();
        let cfg = dir.path().join("cfg");
        assert_eq!(load_external_state(&cfg).unwrap(), None);
        let state = ExternalState {
            host: "localhost".into(),
            port: 5432,
            superuser: "postgres".into(),
        };
        save_external_state(&cfg, &state).unwrap();
        assert_eq!(load_external_state(&cfg).unwrap(), Some(state));
    }

    fn request(host: &str, password: &str) -> ExternalRequest {
        ExternalRequest {
            host: host.into(),
            port: 5432,
            superuser: "postgres".into(),
            password: password.into(),
            needs_pg_search: false,
        }
    }

    #[test]
    fn bad_requests_are_refused_before_anything_is_written() {
        let dir = tempfile::tempdir().unwrap();
        let cfg = dir.path().join("cfg");
        let e = adopt(&request("db.example", "pw"), &cfg).unwrap_err();
        assert!(matches!(e, PgServerError::NotLoopback { .. }), "{e}");
        for pw in ["", " pw", "p\tw"] {
            let e = adopt(&request("127.0.0.1", pw), &cfg).unwrap_err();
            assert!(
                matches!(e, PgServerError::PasswordNotStorable),
                "{pw:?}: {e}"
            );
        }
        assert!(!cfg.exists());
        check_request(&request("[::1]", "pw")).unwrap();
    }

    #[test]
    fn ipv6_brackets_are_dropped() {
        assert_eq!(unbracket("[::1]"), "::1");
        assert_eq!(unbracket("::1"), "::1");
        assert_eq!(unbracket("localhost"), "localhost");
    }

    #[test]
    fn another_saved_address_is_refused_by_address() {
        let dir = tempfile::tempdir().unwrap();
        let state = ExternalState {
            host: "::1".into(),
            port: 5433,
            superuser: "postgres".into(),
        };
        save_external_state(dir.path(), &state).unwrap();
        // `[::1]` is compared unbracketed, so only the port differs here.
        let e = adopt(&request("[::1]", "pw"), dir.path()).unwrap_err();
        let text = e.to_string();
        assert!(
            matches!(e, PgServerError::ExistingServerMismatch { .. }),
            "{text}"
        );
        assert!(
            text.contains("::1:5433") && text.contains("::1:5432"),
            "{text}"
        );
    }

    #[test]
    fn bracketed_ipv6_rerun_matches_the_saved_server() {
        let dir = tempfile::tempdir().unwrap();
        // A port nothing listens on, so the rerun stops at connecting.
        let port = std::net::TcpListener::bind("127.0.0.1:0")
            .unwrap()
            .local_addr()
            .unwrap()
            .port();
        save_external_state(
            dir.path(),
            &ExternalState {
                host: "::1".into(),
                port,
                superuser: "postgres".into(),
            },
        )
        .unwrap();
        let admin_env = dir.path().join(ADMIN_ENV_FILE_NAME);
        let saved = render_env(&ConnInfo {
            host: "::1".into(),
            port,
            dbname: DATABASE.into(),
            user: "postgres".into(),
            password: "pw".into(),
        });
        std::fs::write(&admin_env, &saved).unwrap();
        let req = ExternalRequest {
            port,
            ..request("[::1]", "pw")
        };
        let e = adopt(&req, dir.path()).unwrap_err();
        assert!(
            !matches!(
                e,
                PgServerError::ExistingServerMismatch { .. }
                    | PgServerError::AdminCredentialsInUse { .. }
            ),
            "{e}"
        );
        assert_eq!(std::fs::read_to_string(&admin_env).unwrap(), saved);
    }
}
