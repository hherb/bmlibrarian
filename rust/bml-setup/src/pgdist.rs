//! The bundled PostgreSQL ("pgdist"): PostgreSQL 18 with pgvector, plus
//! pg_search where it exists, published by the `pgdist` workflow as one
//! tarball per target and pinned here by size and sha256
//! (`pgdist-release.json`). [`ensure_pgdist`] downloads the tarball for this
//! computer and unpacks it into `<config dir>/pgdist/<version>/`, all or
//! nothing. Developer docs: `doc/developers/pgdist.md`.

use std::collections::BTreeMap;
use std::path::{Path, PathBuf};
use std::process::Command;

use serde::Deserialize;

use crate::{lock_downloads, sweep_stale_parts, SetupError};

/// Folder under the configuration folder that holds installed bundles.
pub const PGDIST_DIR_NAME: &str = "pgdist";
/// The contents manifest at the root of every bundle.
pub const PGDIST_MANIFEST_FILE: &str = "pgdist.json";
/// The PostgreSQL bin folder inside a bundle.
pub const PGDIST_BIN_SUBDIR: &str = "pg/bin";
/// The extension folder (pgvector, pg_search) inside a bundle.
pub const PGDIST_EXT_SUBDIR: &str = "ext";
/// Where downloaded archives wait, under [`PGDIST_DIR_NAME`].
const DOWNLOADS_DIR_NAME: &str = "downloads";
/// Suffix of the folder a bundle is unpacked into before it is moved in place.
const PARTIAL_SUFFIX: &str = ".partial";
/// The pinned release, published by `.github/workflows/pgdist.yml`.
const RELEASE_JSON: &str = include_str!("../pgdist-release.json");

/// One published bundle.
#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
pub struct PgdistAsset {
    /// File name of the tarball in the release.
    pub file: String,
    /// Its size in bytes.
    pub size: u64,
    /// Its sha256, 64 lower-case hex digits.
    pub sha256: String,
}

/// A published pgdist release.
#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
pub struct PgdistRelease {
    /// Bundle version, such as `18.6-r1`; also the installed folder's name.
    pub version: String,
    /// URL the asset file names are appended to (ends in `/`).
    pub base_url: String,
    /// Assets by target triple; a target without one has no bundle.
    pub assets: BTreeMap<String, PgdistAsset>,
}

/// The fields of a bundle's `pgdist.json` that installing checks.
#[derive(Deserialize)]
struct Manifest {
    version: String,
    target: String,
}

/// An unpacked bundle.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct InstalledPgdist {
    /// The bundle's root folder (`<config dir>/pgdist/<version>`).
    pub root: PathBuf,
}

impl InstalledPgdist {
    /// The PostgreSQL bin folder.
    #[must_use]
    pub fn bindir(&self) -> PathBuf {
        self.root.join(PGDIST_BIN_SUBDIR)
    }

    /// The extension folder to hand to the server.
    #[must_use]
    pub fn extension_dir(&self) -> PathBuf {
        self.root.join(PGDIST_EXT_SUBDIR)
    }
}

/// The release this build of bml installs.
///
/// # Errors
///
/// The embedded `pgdist-release.json` does not parse (a build defect).
pub fn bundled_release() -> Result<PgdistRelease, SetupError> {
    serde_json::from_str(RELEASE_JSON).map_err(|e| other(format!("The built-in list of database bundles is unreadable ({e}); this is a bug in this build of bml.")))
}

/// The bundle target for an operating system and CPU (Rust's `OS`/`ARCH`
/// names), or `None` where no bundle is built.
#[must_use]
pub fn target_for(os: &str, arch: &str) -> Option<&'static str> {
    match (os, arch) {
        ("macos", "aarch64") => Some("aarch64-apple-darwin"),
        ("macos", "x86_64") => Some("x86_64-apple-darwin"),
        ("windows", "x86_64") => Some("x86_64-pc-windows-msvc"),
        ("linux", "x86_64") => Some("x86_64-unknown-linux-gnu"),
        ("linux", "aarch64") => Some("aarch64-unknown-linux-gnu"),
        _ => None,
    }
}

/// The bundle target of this computer.
#[must_use]
pub fn host_target() -> Option<&'static str> {
    target_for(std::env::consts::OS, std::env::consts::ARCH)
}

/// What to tell someone for whose computer no bundle is published.
#[must_use]
pub fn no_bundle_message(target: Option<&str>) -> String {
    format!(
        "No ready-made database is published for this computer ({}) yet; pass --pg-bindir with a PostgreSQL 18 bin folder, or --existing-server.",
        target.unwrap_or("this platform")
    )
}

fn other(message: String) -> SetupError {
    SetupError::Other { message }
}

fn io(path: &Path) -> impl Fn(std::io::Error) -> SetupError + '_ {
    move |source| SetupError::Io {
        path: path.to_path_buf(),
        source,
    }
}

/// The manifest of the bundle in `root`, or `None` when it has none.
fn read_manifest(root: &Path) -> Result<Option<Manifest>, SetupError> {
    let path = root.join(PGDIST_MANIFEST_FILE);
    let text = match std::fs::read_to_string(&path) {
        Ok(text) => text,
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(None),
        Err(e) => return Err(io(&path)(e)),
    };
    serde_json::from_str(&text)
        .map(Some)
        .map_err(|e| other(format!("{} is unreadable ({e}).", path.display())))
}

/// The bundle `version` for `target` installed under `pgdist_dir`, if any.
///
/// # Errors
///
/// The version's folder exists but does not hold that bundle; it is left for
/// the person to remove, since bml never deletes a folder it cannot vouch for.
pub fn installed(
    pgdist_dir: &Path,
    version: &str,
    target: &str,
) -> Result<Option<InstalledPgdist>, SetupError> {
    let root = pgdist_dir.join(version);
    if !root.exists() {
        return Ok(None);
    }
    match read_manifest(&root)? {
        Some(m) if m.version == version && m.target == target => Ok(Some(InstalledPgdist { root })),
        _ => Err(other(format!(
            "{} exists but is not the database bundle {version} for {target}. Remove that folder, then run `bml setup` again.",
            root.display()
        ))),
    }
}

/// Unpack `archive` into `pgdist_dir/<version>`, all or nothing: it is
/// unpacked beside it first and moved in place only once its manifest names
/// `version` and `target`.
///
/// # Errors
///
/// `tar` is missing or fails, the archive holds anything but one bundle
/// folder, its manifest is missing or names another version or target, or
/// the version's folder already exists.
pub fn install_from_archive(
    archive: &Path,
    pgdist_dir: &Path,
    version: &str,
    target: &str,
) -> Result<InstalledPgdist, SetupError> {
    // shortcut: per-file sha256s in pgdist.json are not re-checked here (the
    // archive's sha256 already was); check them when piece 5 copies a bundled
    // folder instead.
    let partial = pgdist_dir.join(format!(".{version}{PARTIAL_SUFFIX}"));
    if partial.exists() {
        std::fs::remove_dir_all(&partial).map_err(io(&partial))?;
    }
    std::fs::create_dir_all(&partial).map_err(io(&partial))?;
    let result = unpack_into(archive, &partial, pgdist_dir, version, target);
    // The partial folder is ours alone; it never outlives this call.
    let _ = std::fs::remove_dir_all(&partial);
    result
}

fn unpack_into(
    archive: &Path,
    partial: &Path,
    pgdist_dir: &Path,
    version: &str,
    target: &str,
) -> Result<InstalledPgdist, SetupError> {
    let status = Command::new("tar")
        .arg("-xzf")
        .arg(archive)
        .arg("-C")
        .arg(partial)
        .status()
        .map_err(|e| other(format!("Could not run the system `tar` to unpack the database ({e}); installing it needs `tar` on the PATH.")))?;
    if !status.success() {
        return Err(other(format!(
            "Unpacking {} failed ({status}). Run `bml setup` again; if it keeps failing, the download may be damaged.",
            archive.display()
        )));
    }
    let entries: Vec<PathBuf> = std::fs::read_dir(partial)
        .map_err(io(partial))?
        .map(|e| e.map(|e| e.path()))
        .collect::<Result<_, _>>()
        .map_err(io(partial))?;
    let [top] = entries.as_slice() else {
        return Err(other(format!(
            "{} is not a database bundle (expected one folder inside).",
            archive.display()
        )));
    };
    let manifest = read_manifest(top)?.ok_or_else(|| {
        other(format!(
            "{} is not a database bundle (no {PGDIST_MANIFEST_FILE}).",
            archive.display()
        ))
    })?;
    if manifest.version != version || manifest.target != target {
        return Err(other(format!(
            "{} holds the database bundle {} for {}, not {version} for {target}.",
            archive.display(),
            manifest.version,
            manifest.target
        )));
    }
    let root = pgdist_dir.join(version);
    if root.exists() {
        return Err(other(format!(
            "{} already exists; remove it, then run `bml setup` again.",
            root.display()
        )));
    }
    std::fs::rename(top, &root).map_err(io(&root))?;
    Ok(InstalledPgdist { root })
}

/// The bundle for `target`, downloaded and unpacked under `config_dir` unless
/// it already is; the flag says whether this call installed it. `progress`
/// gets bytes done and total while downloading.
///
/// # Errors
///
/// No bundle is published for `target` ([`no_bundle_message`]), another
/// setup holds the download lock, or downloading or unpacking fails.
pub fn ensure_pgdist(
    config_dir: &Path,
    release: &PgdistRelease,
    target: &str,
    progress: &mut dyn FnMut(u64, u64),
) -> Result<(InstalledPgdist, bool), SetupError> {
    let dir = config_dir.join(PGDIST_DIR_NAME);
    if let Some(found) = installed(&dir, &release.version, target)? {
        return Ok((found, false));
    }
    let asset = release
        .assets
        .get(target)
        .ok_or_else(|| other(no_bundle_message(Some(target))))?;
    let _lock = lock_downloads(config_dir)?;
    // Another setup may have finished the install while this one waited.
    if let Some(found) = installed(&dir, &release.version, target)? {
        return Ok((found, false));
    }
    let downloads = dir.join(DOWNLOADS_DIR_NAME);
    sweep_stale_parts(&downloads, &asset.file)?;
    let url = format!("{}{}", release.base_url, asset.file);
    let archive = bmlib::embed::download_verified(
        &url,
        &asset.file,
        asset.size,
        &asset.sha256,
        &downloads,
        &mut |done, total| {
            progress(done, total);
            true
        },
    )
    .map_err(|e| other(format!("Downloading the database ({url}) failed: {e}. Check your network, then run `bml setup` again.")))?;
    let found = install_from_archive(&archive, &dir, &release.version, target)?;
    std::fs::remove_file(&archive).map_err(io(&archive))?;
    Ok((found, true))
}

#[cfg(test)]
mod tests {
    use super::*;

    const VERSION: &str = "18.6-r1";
    const TARGET: &str = "aarch64-apple-darwin";

    /// A pgdist archive in `dir` whose manifest names `version` and `target`;
    /// `with_manifest: false` leaves the manifest out.
    fn archive(dir: &Path, version: &str, target: &str, with_manifest: bool) -> PathBuf {
        let tree = dir.join("tree");
        let root = tree.join(format!("bml-pgdist-{version}-{target}"));
        std::fs::create_dir_all(root.join("pg/bin")).unwrap();
        std::fs::write(root.join("pg/bin/marker"), "x").unwrap();
        if with_manifest {
            let manifest =
                format!(r#"{{"schema_version":1,"version":"{version}","target":"{target}"}}"#);
            std::fs::write(root.join(PGDIST_MANIFEST_FILE), manifest).unwrap();
        }
        let path = dir.join("bundle.tar.gz");
        let ok = Command::new("tar")
            .arg("-czf")
            .arg(&path)
            .arg("-C")
            .arg(&tree)
            .arg(root.file_name().unwrap())
            .status()
            .unwrap()
            .success();
        assert!(ok);
        path
    }

    fn release_with_asset() -> PgdistRelease {
        PgdistRelease {
            version: VERSION.into(),
            base_url: "https://example.invalid/".into(),
            assets: BTreeMap::from([(
                TARGET.to_string(),
                PgdistAsset {
                    file: format!("bml-pgdist-{VERSION}-{TARGET}.tar.gz"),
                    size: 1,
                    sha256: "0".repeat(64),
                },
            )]),
        }
    }

    #[test]
    fn bundled_release_parses() {
        assert_eq!(bundled_release().unwrap().version, VERSION);
    }

    #[test]
    fn targets_map_to_bundles() {
        assert_eq!(target_for("macos", "aarch64"), Some("aarch64-apple-darwin"));
        assert_eq!(target_for("macos", "x86_64"), Some("x86_64-apple-darwin"));
        assert_eq!(
            target_for("windows", "x86_64"),
            Some("x86_64-pc-windows-msvc")
        );
        assert_eq!(
            target_for("linux", "x86_64"),
            Some("x86_64-unknown-linux-gnu")
        );
        assert_eq!(
            target_for("linux", "aarch64"),
            Some("aarch64-unknown-linux-gnu")
        );
        assert_eq!(target_for("windows", "aarch64"), None);
        assert_eq!(target_for("freebsd", "x86_64"), None);
    }

    #[test]
    fn installs_atomically() {
        let _spawn = crate::test_support::spawn_guard();
        let tmp = tempfile::tempdir().unwrap();
        let pgdist = tmp.path().join(PGDIST_DIR_NAME);
        let got = install_from_archive(
            &archive(tmp.path(), VERSION, TARGET, true),
            &pgdist,
            VERSION,
            TARGET,
        )
        .unwrap();
        assert_eq!(got.root, pgdist.join(VERSION));
        assert!(got.bindir().ends_with("pg/bin"));
        assert!(got.bindir().join("marker").is_file());
        assert_eq!(got.extension_dir(), got.root.join(PGDIST_EXT_SUBDIR));
        assert!(!pgdist.join(format!(".{VERSION}{PARTIAL_SUFFIX}")).exists());
        assert_eq!(installed(&pgdist, VERSION, TARGET).unwrap(), Some(got));
    }

    #[test]
    fn already_installed_is_found() {
        let _spawn = crate::test_support::spawn_guard();
        let tmp = tempfile::tempdir().unwrap();
        let pgdist = tmp.path().join(PGDIST_DIR_NAME);
        let a = archive(tmp.path(), VERSION, TARGET, true);
        install_from_archive(&a, &pgdist, VERSION, TARGET).unwrap();
        std::fs::remove_file(&a).unwrap();
        assert!(installed(&pgdist, VERSION, TARGET).unwrap().is_some());
        assert_eq!(installed(&pgdist, "18.7-r1", TARGET).unwrap(), None);
    }

    #[test]
    fn leftover_partial_is_replaced() {
        let _spawn = crate::test_support::spawn_guard();
        let tmp = tempfile::tempdir().unwrap();
        let pgdist = tmp.path().join(PGDIST_DIR_NAME);
        let partial = pgdist.join(format!(".{VERSION}{PARTIAL_SUFFIX}"));
        std::fs::create_dir_all(&partial).unwrap();
        std::fs::write(partial.join("junk"), "x").unwrap();
        let got = install_from_archive(
            &archive(tmp.path(), VERSION, TARGET, true),
            &pgdist,
            VERSION,
            TARGET,
        )
        .unwrap();
        assert!(!partial.exists());
        assert!(!got.root.join("junk").exists());
    }

    #[test]
    fn mismatched_archive_is_refused() {
        let _spawn = crate::test_support::spawn_guard();
        let tmp = tempfile::tempdir().unwrap();
        let pgdist = tmp.path().join(PGDIST_DIR_NAME);
        let other = "x86_64-pc-windows-msvc";
        let err = install_from_archive(
            &archive(tmp.path(), VERSION, other, true),
            &pgdist,
            VERSION,
            TARGET,
        )
        .unwrap_err()
        .to_string();
        assert!(err.contains(other) && err.contains(TARGET), "{err}");
        assert!(!pgdist.join(VERSION).exists());
        assert!(!pgdist.join(format!(".{VERSION}{PARTIAL_SUFFIX}")).exists());
    }

    #[test]
    fn archive_without_manifest_is_refused() {
        let _spawn = crate::test_support::spawn_guard();
        let tmp = tempfile::tempdir().unwrap();
        let pgdist = tmp.path().join(PGDIST_DIR_NAME);
        assert!(install_from_archive(
            &archive(tmp.path(), VERSION, TARGET, false),
            &pgdist,
            VERSION,
            TARGET
        )
        .is_err());
        assert!(!pgdist.join(VERSION).exists());
    }

    #[test]
    fn foreign_folder_in_place_is_an_error() {
        let _spawn = crate::test_support::spawn_guard();
        let tmp = tempfile::tempdir().unwrap();
        let pgdist = tmp.path().join(PGDIST_DIR_NAME);
        std::fs::create_dir_all(pgdist.join(VERSION)).unwrap();
        assert!(installed(&pgdist, VERSION, TARGET).is_err());
    }

    #[test]
    fn install_refuses_while_another_setup_downloads() {
        let _spawn = crate::test_support::spawn_guard();
        let tmp = tempfile::tempdir().unwrap();
        let _held = crate::lock_downloads(tmp.path()).unwrap();
        let err = ensure_pgdist(tmp.path(), &release_with_asset(), TARGET, &mut |_, _| {})
            .unwrap_err()
            .to_string();
        assert!(err.contains("Another BMLibrarian setup"), "{err}");
        assert!(!tmp.path().join(PGDIST_DIR_NAME).join(VERSION).exists());
    }

    #[test]
    fn missing_asset_names_the_way_out() {
        let _spawn = crate::test_support::spawn_guard();
        let tmp = tempfile::tempdir().unwrap();
        let mut release = release_with_asset();
        release.assets.clear();
        let err = ensure_pgdist(tmp.path(), &release, TARGET, &mut |_, _| {})
            .unwrap_err()
            .to_string();
        assert!(err.contains("--pg-bindir") && err.contains(TARGET), "{err}");
    }
}
