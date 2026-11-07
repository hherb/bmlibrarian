//! Setting up the private server: resumable and safe to run again.
//!
//! Every step checks before it acts, so running [`init`] again after it was
//! interrupted between steps continues where it stopped, and running it on a
//! finished setup changes nothing. A kill during `initdb` itself can leave a
//! half-written data folder; that is refused with an explanation
//! ([`PgServerError::IncompleteDataDir`]) rather than resumed.

use std::fs;
use std::io;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::time::Duration;

use postgres::{Client, NoTls};

use crate::conf::{
    ensure_include, extension_control_dir, provides_pg_search, render_bml_conf, render_pg_hba,
    ServerConfig, BML_CONF_NAME, PATH_LIST_SEPARATOR,
};
use crate::control::{pg_major_version, restart, start, status, tool, ServerStatus};
use crate::envfile::{
    generate_password, read_conn_info, render_env, write_private_file, ConnInfo,
    ADMIN_ENV_FILE_NAME, APP_ENV_FILE_NAME,
};
use crate::error::{file_error, PgServerError};
use crate::port::{choose_port, port_is_free, DEFAULT_PORT};
use crate::state::{load_state, save_state, ServerState, STATE_FILE_NAME};

/// The superuser role `initdb` creates.
pub const ADMIN_ROLE: &str = "bml_admin";

/// The unprivileged role the app connects as.
pub const APP_ROLE: &str = "bml_app";

/// The app's database.
pub const DATABASE: &str = "bmlibrarian";

/// The maintenance database every server has.
const MAINTENANCE_DATABASE: &str = "postgres";

/// The server's address.
pub const HOST: &str = "127.0.0.1";

/// Extensions the database must have.
pub const REQUIRED_EXTENSIONS: [&str; 1] = ["vector"];

/// Extension created when an extension folder provides it (no Windows build
/// of `pg_search` exists).
pub const PG_SEARCH: &str = "pg_search";

/// Seconds to wait for a connection.
const CONNECT_TIMEOUT_SECONDS: u64 = 10;

/// The file marking an initialised PostgreSQL data directory.
const PG_VERSION_FILE: &str = "PG_VERSION";

/// Temporary file passing the superuser password to `initdb`.
const PWFILE_NAME: &str = ".pwfile.tmp";

/// What to set up.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct InitRequest {
    /// Folder with the PostgreSQL tools (version 18 or newer).
    pub bindir: PathBuf,
    /// Where the database lives (new, empty, or set up by us before).
    pub data_dir: PathBuf,
    /// Extension folders (each with `lib/postgresql`, `share/postgresql`).
    pub extension_dirs: Vec<PathBuf>,
}

/// What [`init`] produced.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct InitOutcome {
    /// The server now set up and running.
    pub state: ServerState,
    /// Whether `pg_search` is preloaded and was ensured in the database by
    /// this run.
    pub pg_search: bool,
    /// Whether this run created the data folder, the app role or database,
    /// reset the app role's password, or wrote `bml.env`.
    pub created: bool,
}

/// What the data folder holds.
#[derive(Debug, PartialEq, Eq)]
enum DataDir {
    /// A data directory set up by us.
    Initialised,
    /// Missing or empty: `initdb` may create the server there.
    Free,
}

/// Connect to PostgreSQL with `info` (loopback, no TLS).
pub fn connect(info: &ConnInfo) -> Result<Client, PgServerError> {
    Ok(postgres::Config::new()
        .host(&info.host)
        .port(info.port)
        .dbname(&info.dbname)
        .user(&info.user)
        .password(&info.password)
        .connect_timeout(Duration::from_secs(CONNECT_TIMEOUT_SECONDS))
        .connect(NoTls)?)
}

/// Set up and start the private server described by `req`, and create its
/// role, database and extensions, keeping its files in `config_dir`.
pub fn init(req: &InitRequest, config_dir: &Path) -> Result<InitOutcome, PgServerError> {
    let req = &validated_request(req)?;
    let pg_major = pg_major_version(&req.bindir)?;
    let saved = load_state(config_dir)?;
    let managed_by_us = saved.is_some();
    let port = match saved {
        Some(saved) => {
            for (field, saved, requested) in [
                ("data folder", saved.data_dir, &req.data_dir),
                ("PostgreSQL bin folder", saved.bindir, &req.bindir),
            ] {
                if &saved != requested {
                    return Err(PgServerError::StateMismatch {
                        field,
                        saved,
                        requested: requested.clone(),
                    });
                }
            }
            saved.port
        }
        None => choose_port(DEFAULT_PORT, port_is_free)?,
    };
    let app_env = config_dir.join(APP_ENV_FILE_NAME);
    // `bml.env` is written last, so it existing means a setup once finished.
    let setup_finished = app_env.try_exists().map_err(file_error(&app_env))?;
    let data_dir_kind = match inspect_data_dir(&req.data_dir, managed_by_us, setup_finished)? {
        DataDirCheck::Usable(kind) => kind,
        DataDirCheck::Missing => {
            return Err(PgServerError::DataDirMissing {
                path: req.data_dir.clone(),
                state_file: config_dir.join(STATE_FILE_NAME),
            })
        }
    };
    fs::create_dir_all(config_dir).map_err(file_error(config_dir))?;

    let admin_env = config_dir.join(ADMIN_ENV_FILE_NAME);
    let admin_password = match (read_conn_info(&admin_env)?, &data_dir_kind) {
        (Some(info), _) => info.password,
        (None, DataDir::Initialised) => {
            return Err(PgServerError::AdminCredentialsLost {
                data_dir: req.data_dir.clone(),
                admin_env,
            })
        }
        (None, DataDir::Free) => generate_password(),
    };
    let admin = conn_info(port, ADMIN_ROLE, &admin_password);
    // Written before initdb, so the password can never be lost.
    write_if_changed(&admin_env, &render_env(&admin))?;

    let preload_pg_search = req.extension_dirs.iter().any(|d| provides_pg_search(d));
    let state = ServerState {
        pg_major,
        bindir: req.bindir.clone(),
        data_dir: req.data_dir.clone(),
        port,
        extension_dirs: req.extension_dirs.clone(),
    };
    // Saved before initdb: the state naming this folder is what makes an
    // initialised folder ours when an interrupted run is repeated.
    save_state(config_dir, &state)?;

    let mut created = false;
    if let DataDir::Free = data_dir_kind {
        run_initdb(req, config_dir, &admin_password)?;
        created = true;
    }

    let config = ServerConfig {
        port,
        extension_dirs: req.extension_dirs.clone(),
        preload_pg_search,
    };
    let config_changed = write_server_config(&req.data_dir, &config)?;

    if config_changed && status(&state)? == ServerStatus::Running {
        restart(&state)?;
    } else {
        start(&state)?;
    }

    let existing_app = read_conn_info(&app_env)?;
    let app_password = existing_app
        .as_ref()
        .map(|info| info.password.clone())
        .unwrap_or_else(generate_password);
    created |= ensure_role_and_database(&admin, &app_password, existing_app.is_none())?;
    let pg_search = ensure_extensions(&admin, preload_pg_search)?;
    created |= write_if_changed(
        &app_env,
        &render_env(&conn_info(port, APP_ROLE, &app_password)),
    )?;

    Ok(InitOutcome {
        state,
        pg_search,
        created,
    })
}

/// Connection parameters for `user` on the private server's database.
fn conn_info(port: u16, user: &str, password: &str) -> ConnInfo {
    ConnInfo {
        host: HOST.to_owned(),
        port,
        dbname: DATABASE.to_owned(),
        user: user.to_owned(),
        password: password.to_owned(),
    }
}

/// The outcome of [`inspect_data_dir`] short of an error.
#[derive(Debug, PartialEq, Eq)]
enum DataDirCheck {
    /// The folder can be used as it is.
    Usable(DataDir),
    /// The folder of a finished setup is missing or empty.
    Missing,
}

/// Whether `data_dir` is ours already, free to use, gone, or someone else's.
///
/// An initialised folder is ours only if our state file names it
/// (`managed_by_us`) or it holds our `bml.conf`; any other PostgreSQL data
/// folder belongs to another server and is never touched. Once a setup has
/// finished (`setup_finished`), a missing or empty folder is never
/// re-initialised: it is far more likely an unmounted disk than a wish for
/// a new, empty server.
fn inspect_data_dir(
    data_dir: &Path,
    managed_by_us: bool,
    setup_finished: bool,
) -> Result<DataDirCheck, PgServerError> {
    let incomplete = || PgServerError::IncompleteDataDir {
        path: data_dir.to_owned(),
    };
    if data_dir.join(PG_VERSION_FILE).is_file() {
        let has_our_conf = data_dir.join(BML_CONF_NAME).is_file();
        return if has_our_conf || (managed_by_us && setup_finished) {
            Ok(DataDirCheck::Usable(DataDir::Initialised))
        } else if managed_by_us {
            // Our first run never got past initdb (it writes bml.conf next).
            Err(incomplete())
        } else {
            Err(PgServerError::ForeignDataDir {
                path: data_dir.to_owned(),
            })
        };
    }
    let empty = match fs::read_dir(data_dir) {
        Ok(mut entries) => entries.next().is_none(),
        Err(e) if e.kind() == io::ErrorKind::NotFound => true,
        Err(source) => {
            return Err(PgServerError::File {
                path: data_dir.to_owned(),
                source,
            })
        }
    };
    match (empty, managed_by_us) {
        (true, true) if setup_finished => Ok(DataDirCheck::Missing),
        (true, _) => Ok(DataDirCheck::Usable(DataDir::Free)),
        (false, true) if !setup_finished => Err(incomplete()),
        (false, _) => Err(PgServerError::DataDirNotEmpty {
            path: data_dir.to_owned(),
        }),
    }
}

/// `req` with absolute paths (they are saved and used later from another
/// working directory), refusing paths the server tools or our files cannot
/// hold, before anything is created.
fn validated_request(req: &InitRequest) -> Result<InitRequest, PgServerError> {
    let absolute = |path: &Path| -> Result<PathBuf, PgServerError> {
        let path = std::path::absolute(path).map_err(file_error(path))?;
        if path.to_str().is_none() {
            return Err(PgServerError::NonUnicodePath { path });
        }
        Ok(path)
    };
    let bindir = absolute(&req.bindir)?;
    let data_dir = absolute(&req.data_dir)?;
    for path in [&bindir, &data_dir] {
        check_shell_safe(path)?;
    }
    let extension_dirs = req
        .extension_dirs
        .iter()
        .map(|dir| {
            let dir = absolute(dir)?;
            check_extension_dir(&dir)?;
            Ok(dir)
        })
        .collect::<Result<Vec<_>, PgServerError>>()?;
    Ok(InitRequest {
        bindir,
        data_dir,
        extension_dirs,
    })
}

/// Refuse an extension folder that cannot go into a server path list or
/// does not have the expected layout.
fn check_extension_dir(dir: &Path) -> Result<(), PgServerError> {
    let bad = |reason: String| PgServerError::BadExtensionDir {
        path: dir.to_owned(),
        reason,
    };
    if dir.to_string_lossy().contains(PATH_LIST_SEPARATOR) {
        return Err(bad(format!(
            "contains {PATH_LIST_SEPARATOR:?}, which separates PostgreSQL path lists; choose a folder without it"
        )));
    }
    let control = extension_control_dir(dir);
    if !control.is_dir() {
        return Err(bad(format!(
            "has no {}; expected an extension folder with lib/postgresql and share/postgresql",
            control.display()
        )));
    }
    Ok(())
}

/// Characters `pg_ctl` cannot pass through the `/bin/sh -c "…"` command it
/// builds to start the server (they keep their meaning inside double quotes).
#[cfg(unix)]
const SHELL_UNSAFE_CHARS: [char; 4] = ['"', '$', '`', '\\'];

/// Refuse a path `pg_ctl` would mangle, before anything is created.
fn check_shell_safe(path: &Path) -> Result<(), PgServerError> {
    #[cfg(unix)]
    if let Some(ch) = path
        .to_string_lossy()
        .chars()
        .find(|c| SHELL_UNSAFE_CHARS.contains(c))
    {
        return Err(PgServerError::UnsafePath {
            path: path.to_owned(),
            ch,
        });
    }
    let _ = path;
    Ok(())
}

/// Write `contents` to `path` (owner-only) unless it already holds them.
/// Returns whether the file was written.
fn write_if_changed(path: &Path, contents: &str) -> Result<bool, PgServerError> {
    if fs::read_to_string(path).is_ok_and(|current| current == contents) {
        return Ok(false);
    }
    write_private_file(path, contents).map_err(file_error(path))?;
    Ok(true)
}

/// Run `initdb` with the superuser password passed through a private file
/// that is removed afterwards, whether or not `initdb` succeeded.
fn run_initdb(
    req: &InitRequest,
    config_dir: &Path,
    admin_password: &str,
) -> Result<(), PgServerError> {
    let pwfile = config_dir.join(PWFILE_NAME);
    write_private_file(&pwfile, admin_password).map_err(file_error(&pwfile))?;
    let program = tool(&req.bindir, "initdb");
    let result = Command::new(&program)
        .arg("-D")
        .arg(&req.data_dir)
        .arg("-U")
        .arg(ADMIN_ROLE)
        .arg(format!("--pwfile={}", pwfile.display()))
        .args([
            "--auth=scram-sha-256",
            "--encoding=UTF8",
            "--locale-provider=builtin",
            "--builtin-locale=C.UTF-8",
        ])
        .output();
    let removed = fs::remove_file(&pwfile).map_err(file_error(&pwfile));
    // initdb's own failure is the one to report; a failed removal after it
    // still names the password file left behind.
    let output = result.map_err(|source| PgServerError::Spawn {
        program: program.clone(),
        source,
    })?;
    if !output.status.success() {
        return Err(PgServerError::Command {
            program: program.to_string_lossy().into_owned(),
            status: output.status.code(),
            stderr: String::from_utf8_lossy(&output.stderr).trim().to_owned(),
        });
    }
    removed
}

/// Write `bml.conf`, `pg_hba.conf` and the include line. Returns whether
/// any of them changed (a running server then needs a restart).
fn write_server_config(data_dir: &Path, config: &ServerConfig) -> Result<bool, PgServerError> {
    let mut changed = write_if_changed(&data_dir.join(BML_CONF_NAME), &render_bml_conf(config))?;
    changed |= write_if_changed(&data_dir.join("pg_hba.conf"), &render_pg_hba())?;
    let main_conf = data_dir.join("postgresql.conf");
    let current = fs::read_to_string(&main_conf).map_err(file_error(&main_conf))?;
    if let Some(text) = ensure_include(&current) {
        write_private_file(&main_conf, &text).map_err(file_error(&main_conf))?;
        changed = true;
    }
    Ok(changed)
}

/// Create the app role and database if missing; give the role
/// `app_password` when it is new or its credentials file was lost.
/// Returns whether anything changed.
///
/// Only a SCRAM-SHA-256 verifier of `app_password` is sent (base64, `$`
/// and `:`, so safe inside a SQL string literal), never the password, so it
/// cannot reach the server log; role and database names are constants.
fn ensure_role_and_database(
    admin: &ConnInfo,
    app_password: &str,
    app_env_missing: bool,
) -> Result<bool, PgServerError> {
    let verifier = postgres_protocol::password::scram_sha_256(app_password.as_bytes());
    let mut maintenance = admin.clone();
    maintenance.dbname = MAINTENANCE_DATABASE.to_owned();
    let mut client = connect(&maintenance)?;
    let mut changed = false;
    let role_exists = !client
        .query("SELECT 1 FROM pg_roles WHERE rolname = $1", &[&APP_ROLE])?
        .is_empty();
    if !role_exists {
        client.batch_execute(&format!(
            "CREATE ROLE {APP_ROLE} LOGIN PASSWORD '{verifier}'"
        ))?;
        changed = true;
    } else if app_env_missing {
        client.batch_execute(&format!("ALTER ROLE {APP_ROLE} PASSWORD '{verifier}'"))?;
        changed = true;
    }
    let database_exists = !client
        .query("SELECT 1 FROM pg_database WHERE datname = $1", &[&DATABASE])?
        .is_empty();
    if !database_exists {
        client.batch_execute(&format!("CREATE DATABASE {DATABASE} OWNER {APP_ROLE}"))?;
        changed = true;
    }
    Ok(changed)
}

/// Create the required extensions, and `pg_search` when it is preloaded.
/// Returns whether `pg_search` was ensured.
fn ensure_extensions(admin: &ConnInfo, preload_pg_search: bool) -> Result<bool, PgServerError> {
    let mut client = connect(admin)?;
    let mut available = |name: &str| -> Result<bool, PgServerError> {
        Ok(!client
            .query(
                "SELECT 1 FROM pg_available_extensions WHERE name = $1",
                &[&name],
            )?
            .is_empty())
    };
    for name in REQUIRED_EXTENSIONS {
        if !available(name)? {
            return Err(PgServerError::ExtensionUnavailable { name });
        }
    }
    let pg_search = preload_pg_search && available(PG_SEARCH)?;
    let mut wanted: Vec<&str> = REQUIRED_EXTENSIONS.to_vec();
    if pg_search {
        wanted.push(PG_SEARCH);
    }
    for name in wanted {
        client.batch_execute(&format!("CREATE EXTENSION IF NOT EXISTS {name}"))?;
    }
    Ok(pg_search)
}

#[cfg(test)]
mod tests {
    use super::*;

    /// A data folder in a fresh temp dir: `None` missing, else these files.
    fn data_dir(files: Option<&[&str]>) -> (tempfile::TempDir, PathBuf) {
        let tmp = tempfile::tempdir().unwrap();
        let dir = tmp.path().join("data");
        if let Some(files) = files {
            fs::create_dir(&dir).unwrap();
            for name in files {
                fs::write(dir.join(name), "x").unwrap();
            }
        }
        (tmp, dir)
    }

    /// [`inspect_data_dir`] on a data folder made by [`data_dir`].
    fn check(
        files: Option<&[&str]>,
        managed: bool,
        finished: bool,
    ) -> Result<DataDirCheck, PgServerError> {
        let (_tmp, dir) = data_dir(files);
        inspect_data_dir(&dir, managed, finished)
    }

    const FREE: DataDirCheck = DataDirCheck::Usable(DataDir::Free);
    const OURS: DataDirCheck = DataDirCheck::Usable(DataDir::Initialised);

    #[test]
    fn new_or_empty_folder_is_free() {
        assert_eq!(check(None, false, false).unwrap(), FREE);
        assert_eq!(check(Some(&[]), false, false).unwrap(), FREE);
        // State saved, initdb not yet run (or it failed and cleaned up).
        assert_eq!(check(None, true, false).unwrap(), FREE);
        // State file lost but credentials kept: nothing names the folder.
        assert_eq!(check(None, false, true).unwrap(), FREE);
    }

    #[test]
    fn finished_setup_with_folder_gone_is_refused() {
        assert_eq!(check(None, true, true).unwrap(), DataDirCheck::Missing);
        assert_eq!(check(Some(&[]), true, true).unwrap(), DataDirCheck::Missing);
    }

    #[test]
    fn ours_is_initialised() {
        assert_eq!(
            check(Some(&["PG_VERSION", "bml.conf"]), true, true).unwrap(),
            OURS
        );
        // State lost: our bml.conf still marks the folder as ours.
        assert_eq!(
            check(Some(&["PG_VERSION", "bml.conf"]), false, false).unwrap(),
            OURS
        );
        // bml.conf removed by hand after a finished setup: rewritten later.
        assert_eq!(check(Some(&["PG_VERSION"]), true, true).unwrap(), OURS);
    }

    #[test]
    fn interrupted_initdb_is_refused() {
        for files in [&["PG_VERSION"][..], &["base"][..]] {
            let err = check(Some(files), true, false).unwrap_err();
            assert!(
                matches!(err, PgServerError::IncompleteDataDir { .. }),
                "{err}"
            );
        }
    }

    #[test]
    fn others_are_refused() {
        let err = check(Some(&["PG_VERSION"]), false, false).unwrap_err();
        assert!(matches!(err, PgServerError::ForeignDataDir { .. }), "{err}");
        let err = check(Some(&["notes.txt"]), false, false).unwrap_err();
        assert!(
            matches!(err, PgServerError::DataDirNotEmpty { .. }),
            "{err}"
        );
    }

    #[test]
    fn scram_verifier_is_sql_literal_safe() {
        let verifier = postgres_protocol::password::scram_sha_256(b"secret");
        assert!(verifier.starts_with("SCRAM-SHA-256$"), "{verifier}");
        assert!(!verifier.contains(['\'', '\\']), "{verifier}");
        assert!(!verifier.contains("secret"));
    }

    #[test]
    fn request_paths_become_absolute() {
        let tmp = tempfile::tempdir().unwrap();
        let ext = tmp.path().join("ext");
        fs::create_dir_all(extension_control_dir(&ext)).unwrap();
        let req = validated_request(&InitRequest {
            bindir: "pg/bin".into(),
            data_dir: "data".into(),
            extension_dirs: vec![ext.clone()],
        })
        .unwrap();
        assert!(req.bindir.is_absolute() && req.bindir.ends_with("pg/bin"));
        assert!(req.data_dir.is_absolute() && req.data_dir.ends_with("data"));
        assert_eq!(req.extension_dirs, vec![ext]);
    }

    #[test]
    fn unusable_extension_dirs_are_refused() {
        let tmp = tempfile::tempdir().unwrap();
        let separator = tmp.path().join(format!("a{PATH_LIST_SEPARATOR}b"));
        for dir in [tmp.path().join("missing"), tmp.path().to_owned(), separator] {
            let err = check_extension_dir(&dir).unwrap_err();
            assert!(
                matches!(err, PgServerError::BadExtensionDir { .. }),
                "{err}"
            );
        }
    }

    #[cfg(unix)]
    #[test]
    fn non_unicode_path_is_refused() {
        use std::os::unix::ffi::OsStrExt;
        let req = InitRequest {
            bindir: "/bin".into(),
            data_dir: PathBuf::from(std::ffi::OsStr::from_bytes(b"/tmp/\xff")),
            extension_dirs: vec![],
        };
        let err = validated_request(&req).unwrap_err();
        assert!(matches!(err, PgServerError::NonUnicodePath { .. }), "{err}");
    }

    #[cfg(unix)]
    #[test]
    fn every_shell_unsafe_char_is_refused_and_others_pass() {
        for ch in SHELL_UNSAFE_CHARS {
            let path = PathBuf::from(format!("/tmp/a{ch}b"));
            let err = check_shell_safe(&path).unwrap_err();
            assert!(matches!(err, PgServerError::UnsafePath { .. }), "{err}");
        }
        check_shell_safe(Path::new("/tmp/data dir ü'q")).unwrap();
    }
}
