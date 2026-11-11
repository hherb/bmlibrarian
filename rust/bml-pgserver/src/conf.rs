//! Text of the configuration files the private server is given.
//!
//! Our settings live in their own `bml.conf`, included from the
//! `postgresql.conf` that `initdb` writes, so initdb's defaults stay intact
//! and `ALTER SYSTEM` (the import profile) keeps `postgresql.auto.conf`.

use std::path::{Path, PathBuf};

/// Name of our settings file inside the data directory.
pub const BML_CONF_NAME: &str = "bml.conf";

/// The line that pulls `bml.conf` into `postgresql.conf`.
pub const INCLUDE_LINE: &str = "include 'bml.conf'";

/// Where the server listens: loopback only, never the network.
pub const LISTEN_ADDRESS: &str = "127.0.0.1";

/// JIT compilation is off on every private server, because the bundled
/// PostgreSQL ships without LLVM.
pub const JIT_SETTING: &str = "jit = off";

/// Separator between entries of a PostgreSQL path-list setting.
pub const PATH_LIST_SEPARATOR: &str = if cfg!(windows) { ";" } else { ":" };

/// Library and control-file folders inside an extension folder (the layout
/// Postgres.app uses for extensions).
const EXT_LIB_SUBDIR: &str = "lib/postgresql";
const EXT_SHARE_SUBDIR: &str = "share/postgresql";

/// What `bml.conf` must say.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ServerConfig {
    /// TCP port on `127.0.0.1`.
    pub port: u16,
    /// Extension folders, each holding `lib/postgresql` and `share/postgresql`.
    pub extension_dirs: Vec<PathBuf>,
    /// Whether to preload `pg_search` (required by it at server start).
    pub preload_pg_search: bool,
}

/// `value` as a single-quoted configuration string, with `'` doubled.
pub fn quote_conf_value(value: &str) -> String {
    format!("'{}'", value.replace('\'', "''"))
}

/// A path as PostgreSQL configuration expects it: `/` separators everywhere.
fn conf_path(path: &Path) -> String {
    let text = path.to_string_lossy().into_owned();
    if cfg!(windows) {
        text.replace('\\', "/")
    } else {
        text
    }
}

/// `first` followed by `<dir>/<subdir>` for every extension folder.
fn path_list(first: &str, dirs: &[PathBuf], subdir: &str) -> String {
    std::iter::once(first.to_owned())
        .chain(dirs.iter().map(|d| conf_path(&d.join(subdir))))
        .collect::<Vec<_>>()
        .join(PATH_LIST_SEPARATOR)
}

/// The full text of `bml.conf`.
pub fn render_bml_conf(cfg: &ServerConfig) -> String {
    let mut lines = vec![
        format!("port = {}", cfg.port),
        format!("listen_addresses = {}", quote_conf_value(LISTEN_ADDRESS)),
        "unix_socket_directories = ''".to_owned(),
        "password_encryption = 'scram-sha-256'".to_owned(),
        JIT_SETTING.to_owned(),
        format!(
            "dynamic_library_path = {}",
            quote_conf_value(&path_list("$libdir", &cfg.extension_dirs, EXT_LIB_SUBDIR))
        ),
        format!(
            "extension_control_path = {}",
            quote_conf_value(&path_list("$system", &cfg.extension_dirs, EXT_SHARE_SUBDIR))
        ),
    ];
    if cfg.preload_pg_search {
        lines.push("shared_preload_libraries = 'pg_search'".to_owned());
    }
    lines.iter().map(|l| format!("{l}\n")).collect()
}

/// The full text of `pg_hba.conf`: password logins over loopback TCP only.
pub fn render_pg_hba() -> String {
    "host all all 127.0.0.1/32 scram-sha-256\nhost all all ::1/128 scram-sha-256\n".to_owned()
}

/// `postgresql_conf` with [`INCLUDE_LINE`] appended, or `None` if present.
pub fn ensure_include(postgresql_conf: &str) -> Option<String> {
    if postgresql_conf.lines().any(|l| l.trim() == INCLUDE_LINE) {
        return None;
    }
    let mut text = postgresql_conf.to_owned();
    if !text.is_empty() && !text.ends_with('\n') {
        text.push('\n');
    }
    text.push_str(INCLUDE_LINE);
    text.push('\n');
    Some(text)
}

/// The folder of extension control files inside `extension_dir`.
pub fn extension_control_dir(extension_dir: &Path) -> PathBuf {
    extension_dir.join(EXT_SHARE_SUBDIR).join("extension")
}

/// Whether the extension folder `extension_dir` contains `pg_search`.
pub fn provides_pg_search(extension_dir: &Path) -> bool {
    extension_control_dir(extension_dir)
        .join("pg_search.control")
        .is_file()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn quotes_single_quote() {
        assert_eq!(quote_conf_value("a'b c"), "'a''b c'");
    }

    #[cfg(unix)]
    #[test]
    fn conf_with_spaced_ext_dir() {
        let cfg = ServerConfig {
            port: 5418,
            extension_dirs: vec![PathBuf::from("/Users/x/Ext 18/pg_search")],
            preload_pg_search: true,
        };
        let text = render_bml_conf(&cfg);
        assert!(text.contains(
            "extension_control_path = '$system:/Users/x/Ext 18/pg_search/share/postgresql'"
        ));
        assert!(text.contains("shared_preload_libraries = 'pg_search'"));
        assert!(text.contains("port = 5418\n"));
        assert!(text.contains("listen_addresses = '127.0.0.1'\n"));
        assert!(text.contains("unix_socket_directories = ''\n"));
    }

    #[test]
    fn conf_without_ext_dirs() {
        let cfg = ServerConfig {
            port: 5418,
            extension_dirs: vec![],
            preload_pg_search: false,
        };
        let text = render_bml_conf(&cfg);
        assert!(text.contains("dynamic_library_path = '$libdir'"));
        assert!(!text.contains("shared_preload_libraries"));
    }

    #[test]
    fn renders_jit_off() {
        for preload_pg_search in [false, true] {
            let cfg = ServerConfig {
                port: 5418,
                extension_dirs: vec![],
                preload_pg_search,
            };
            assert!(render_bml_conf(&cfg).lines().any(|l| l == "jit = off"));
        }
    }

    #[test]
    fn hba_has_no_local_or_trust() {
        let hba = render_pg_hba();
        assert!(!hba.contains("local"));
        assert!(!hba.contains("trust"));
        assert!(hba.contains("host all all 127.0.0.1/32 scram-sha-256"));
    }

    #[test]
    fn include_added_once() {
        let once = ensure_include("a = 1\n").expect("include missing, so text changes");
        assert!(once.ends_with("include 'bml.conf'\n"));
        assert_eq!(ensure_include(&once), None);
    }

    #[test]
    fn detects_pg_search() {
        let with = tempfile::tempdir().unwrap();
        let ext = with.path().join("share/postgresql/extension");
        std::fs::create_dir_all(&ext).unwrap();
        std::fs::write(ext.join("pg_search.control"), "").unwrap();
        assert!(provides_pg_search(with.path()));
        let without = tempfile::tempdir().unwrap();
        assert!(!provides_pg_search(without.path()));
    }
}
