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
/// How often moving the unpacked bundle into place is tried: on Windows,
/// antivirus scanners briefly hold freshly written files open, which fails
/// the move with "access denied" (as rustup also found).
const RENAME_ATTEMPTS: u32 = if cfg!(windows) { 6 } else { 1 };
/// Wait before the second attempt; it doubles after each further one.
const RENAME_FIRST_BACKOFF: std::time::Duration = std::time::Duration::from_millis(100);
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

/// The oldest systems a release's bundles run on (`doc/developers/pgdist.md`
/// "What the bundles need").
#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
pub struct PgdistRequires {
    /// Oldest macOS, such as `15.0` (`inputs.json` `macos_build.min_os`).
    pub macos: String,
    /// Oldest glibc on Linux, such as `2.36` (`inputs.json` `linux_build.glibc`).
    pub glibc: String,
}

/// A published pgdist release.
#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
pub struct PgdistRelease {
    /// Bundle version, such as `18.6-r1`; also the installed folder's name.
    pub version: String,
    /// URL the asset file names are appended to (ends in `/`).
    pub base_url: String,
    /// The oldest systems its bundles run on.
    pub requires: PgdistRequires,
    /// Assets by target triple; a target without one has no bundle.
    pub assets: BTreeMap<String, PgdistAsset>,
}

/// The fields of a bundle's `pgdist.json` that installing checks.
#[derive(Deserialize)]
struct Manifest {
    /// The bundle version it was built as.
    version: String,
    /// The target triple it was built for.
    target: String,
    /// Whether it holds pg_search (`None`: a manifest that does not say).
    #[serde(default)]
    pg_search: Option<bool>,
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

/// The bundle target for an operating system, CPU and C library (Rust's
/// `OS`, `ARCH` and `target_env` names), or `None` where no bundle is built.
/// The Linux bundles need glibc, so a musl build gets none.
#[must_use]
pub fn target_for(os: &str, arch: &str, env: &str) -> Option<&'static str> {
    match (os, arch, env) {
        ("macos", "aarch64", _) => Some("aarch64-apple-darwin"),
        ("macos", "x86_64", _) => Some("x86_64-apple-darwin"),
        ("windows", "x86_64", _) => Some("x86_64-pc-windows-msvc"),
        ("linux", "x86_64", "gnu") => Some("x86_64-unknown-linux-gnu"),
        ("linux", "aarch64", "gnu") => Some("aarch64-unknown-linux-gnu"),
        _ => None,
    }
}

/// The C library this bml was built for, as Rust's `target_env` names it.
fn host_env() -> &'static str {
    if cfg!(target_env = "gnu") {
        "gnu"
    } else if cfg!(target_env = "musl") {
        "musl"
    } else if cfg!(target_env = "msvc") {
        "msvc"
    } else {
        ""
    }
}

/// The bundle target of this computer.
#[must_use]
pub fn host_target() -> Option<&'static str> {
    target_for(std::env::consts::OS, std::env::consts::ARCH, host_env())
}

/// What to tell someone for whose computer no bundle is published.
#[must_use]
pub fn no_bundle_message(target: Option<&str>) -> String {
    format!(
        "No ready-made database is published for this computer ({}) yet; pass --pg-bindir with a PostgreSQL 18 bin folder, or --existing-server.",
        target.unwrap_or("this platform")
    )
}

/// Whether dot-separated version `found` is older than `floor` (`14.7.1` is
/// older than `15.0`, `15` is not); `None` when either is not such a version.
#[must_use]
pub fn older_than(found: &str, floor: &str) -> Option<bool> {
    let parse = |v: &str| -> Option<Vec<u32>> {
        let mut parts = v
            .trim()
            .split('.')
            .map(|p| p.parse().ok())
            .collect::<Option<Vec<u32>>>()?;
        // `15` and `15.0` are the same version.
        while parts.len() > 1 && parts.last() == Some(&0) {
            parts.pop();
        }
        Some(parts)
    };
    Some(parse(found)? < parse(floor)?)
}

/// What to tell someone whose `system` (`macOS` or `glibc`) at version
/// `found` is older than the bundle's `floor`; `None` when it is not, or
/// when `found` is unknown or unreadable: then the download goes ahead and
/// the error from running the bundled `postgres` says what is missing.
#[must_use]
pub fn too_old_message(system: &str, floor: &str, found: Option<&str>) -> Option<String> {
    let found = found?;
    older_than(found, floor)?.then(|| {
        format!(
            "This computer has {system} {found}, but the ready-made database needs {system} {floor} or newer. Update the system, or pass --pg-bindir with a PostgreSQL 18 bin folder, or --existing-server."
        )
    })
}

/// The macOS version this computer runs, if it runs macOS.
fn macos_version() -> Option<String> {
    if cfg!(target_os = "macos") {
        sysinfo::System::os_version()
    } else {
        None
    }
}

/// The glibc version this computer runs (`getconf GNU_LIBC_VERSION` prints
/// `glibc 2.36`), if this bml is a glibc build and the version is readable.
fn glibc_version() -> Option<String> {
    if !cfg!(all(target_os = "linux", target_env = "gnu")) {
        return None;
    }
    let out = Command::new("getconf")
        .arg("GNU_LIBC_VERSION")
        .output()
        .ok()
        .filter(|o| o.status.success())?;
    String::from_utf8_lossy(&out.stdout)
        .trim()
        .strip_prefix("glibc ")
        .map(|v| v.trim().to_string())
}

/// Why `target`'s bundle cannot run on this computer, when its macOS or
/// glibc is older than `requires` says ([`too_old_message`]); checked before
/// downloading, so an old system is told so instead of downloading a
/// bundle (31-115 MB) whose binaries then fail to load.
#[must_use]
pub fn system_too_old(target: &str, requires: &PgdistRequires) -> Option<String> {
    if target.ends_with("-apple-darwin") {
        too_old_message("macOS", &requires.macos, macos_version().as_deref())
    } else if target.ends_with("-linux-gnu") {
        too_old_message("glibc", &requires.glibc, glibc_version().as_deref())
    } else {
        None
    }
}

/// Whether the bundle whose PostgreSQL bin folder is `bindir` says in its
/// manifest that it was built without pg_search (no ParadeDB build exists
/// for its target); `false` when `bindir` is not in a bundle or the
/// manifest does not say.
#[must_use]
pub fn built_without_pg_search(bindir: &Path) -> bool {
    if !bindir.ends_with(PGDIST_BIN_SUBDIR) {
        return false;
    }
    let depth = Path::new(PGDIST_BIN_SUBDIR).components().count();
    bindir.ancestors().nth(depth).is_some_and(|root| {
        matches!(
            read_manifest(root),
            Ok(Some(Manifest {
                pg_search: Some(false),
                ..
            }))
        )
    })
}

/// Delete the downloaded `archive` once its bundle is installed; a warning
/// when it is there and cannot be deleted (none when it is already gone).
fn remove_archive(archive: &Path) -> Vec<String> {
    match std::fs::remove_file(archive) {
        Err(e) if e.kind() != std::io::ErrorKind::NotFound => vec![format!(
            "the database is installed, but its downloaded archive {} could not be deleted ({e}); you can delete it yourself.",
            archive.display()
        )],
        _ => Vec::new(),
    }
}

/// A [`SetupError`] carrying `message` as is.
fn other(message: String) -> SetupError {
    SetupError::Other { message }
}

/// Turns an I/O error on `path` into a [`SetupError`] naming that path.
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
    // Best effort: the partial folder is ours alone, and a leftover is
    // removed by the next install before it unpacks.
    let _ = std::fs::remove_dir_all(&partial);
    result
}

/// [`install_from_archive`] once `partial` exists and is empty: unpack,
/// check the single bundle folder's manifest, move it to `pgdist_dir/<version>`.
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
            "Unpacking {} failed ({status}). Check that there is free space and that {} is writable, then run `bml setup` again.",
            archive.display(),
            pgdist_dir.display()
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
            "{} holds the database bundle {} for {}, not {version} for {target}; this is a bug in this build of bml. Meanwhile, pass --pg-bindir or --existing-server.",
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
    rename_with_retry(top, &root).map_err(|e| {
        other(format!(
            "Could not move the unpacked database into {} ({e}). Check that the folder is writable and nothing (such as a virus scanner) holds it open, then run `bml setup` again.",
            root.display()
        ))
    })?;
    Ok(InstalledPgdist { root })
}

/// `std::fs::rename`, retried with a growing wait while it fails with
/// "permission denied"; tried at most [`RENAME_ATTEMPTS`] times in all.
fn rename_with_retry(from: &Path, to: &Path) -> std::io::Result<()> {
    let mut wait = RENAME_FIRST_BACKOFF;
    let mut attempt = 1;
    loop {
        match std::fs::rename(from, to) {
            Err(e)
                if e.kind() == std::io::ErrorKind::PermissionDenied
                    && attempt < RENAME_ATTEMPTS =>
            {
                std::thread::sleep(wait);
                wait *= 2;
                attempt += 1;
            }
            result => return result,
        }
    }
}

/// The bundle for `target`, downloaded and unpacked under `config_dir` unless
/// it already is, with warnings about anything left over that did not stop
/// the install (a downloaded archive that could not be deleted; an earlier
/// run's leftover is deleted, or warned about, by a later call that finds the
/// bundle installed, which setup makes only while no server is saved).
/// `progress` gets bytes done and total while downloading.
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
) -> Result<(InstalledPgdist, Vec<String>), SetupError> {
    let dir = config_dir.join(PGDIST_DIR_NAME);
    let downloads = dir.join(DOWNLOADS_DIR_NAME);
    // Without the lock: once the bundle is in place no setup reads its
    // archive any more.
    let leftover = |asset: Option<&PgdistAsset>| {
        asset.map_or_else(Vec::new, |a| remove_archive(&downloads.join(&a.file)))
    };
    if let Some(found) = installed(&dir, &release.version, target)? {
        return Ok((found, leftover(release.assets.get(target))));
    }
    let asset = release
        .assets
        .get(target)
        .ok_or_else(|| other(no_bundle_message(Some(target))))?;
    let _lock = lock_downloads(config_dir)?;
    // Another setup may have finished the install between the check above
    // and taking the lock.
    if let Some(found) = installed(&dir, &release.version, target)? {
        return Ok((found, leftover(Some(asset))));
    }
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
    Ok((found, remove_archive(&archive)))
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

    /// Floors every computer that runs these tests meets.
    fn test_requires() -> PgdistRequires {
        PgdistRequires {
            macos: "10.0".into(),
            glibc: "2.0".into(),
        }
    }

    /// A release with a placeholder asset for [`TARGET`] (never downloadable).
    fn release_with_asset() -> PgdistRelease {
        PgdistRelease {
            version: VERSION.into(),
            base_url: "https://example.invalid/".into(),
            requires: test_requires(),
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

    /// A release pinning `archive` for [`TARGET`], served from nowhere: any
    /// fetch fails, so only an already downloaded copy can satisfy it.
    fn release_for(archive: &Path) -> PgdistRelease {
        use sha2::{Digest, Sha256};
        let bytes = std::fs::read(archive).unwrap();
        let sha256 = Sha256::digest(&bytes)
            .iter()
            .map(|b| format!("{b:02x}"))
            .collect();
        PgdistRelease {
            version: VERSION.into(),
            base_url: "http://127.0.0.1:1/".into(),
            requires: test_requires(),
            assets: BTreeMap::from([(
                TARGET.to_string(),
                PgdistAsset {
                    file: format!("bml-pgdist-{VERSION}-{TARGET}.tar.gz"),
                    size: bytes.len() as u64,
                    sha256,
                },
            )]),
        }
    }

    /// Put `bytes` where `ensure_pgdist` keeps the download of `release`'s
    /// [`TARGET`] asset under `config_dir`; returns that path.
    fn seed_download(config_dir: &Path, release: &PgdistRelease, bytes: &[u8]) -> PathBuf {
        let dir = config_dir.join(PGDIST_DIR_NAME).join(DOWNLOADS_DIR_NAME);
        std::fs::create_dir_all(&dir).unwrap();
        let path = dir.join(&release.assets[TARGET].file);
        std::fs::write(&path, bytes).unwrap();
        path
    }

    #[test]
    fn bundled_release_is_well_formed() {
        let release = bundled_release().unwrap();
        let inputs: serde_json::Value =
            serde_json::from_str(include_str!("../../pgdist/inputs.json")).unwrap();
        assert_eq!(inputs["version"], release.version.as_str());
        assert!(
            release.base_url.starts_with("https://")
                && release
                    .base_url
                    .ends_with(&format!("/pgdist-{}/", release.version)),
            "{}",
            release.base_url
        );
        for (target, asset) in &release.assets {
            assert!(inputs["targets"].get(target).is_some(), "{target}");
            assert_eq!(
                asset.file,
                format!("bml-pgdist-{}-{target}.tar.gz", release.version)
            );
            assert!(asset.size > 0, "{target}");
            assert!(
                asset.sha256.len() == 64
                    && asset
                        .sha256
                        .bytes()
                        .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)),
                "{target}"
            );
        }
    }

    #[test]
    fn release_floors_match_the_build_inputs() {
        let requires = bundled_release().unwrap().requires;
        let inputs: serde_json::Value =
            serde_json::from_str(include_str!("../../pgdist/inputs.json")).unwrap();
        assert_eq!(inputs["macos_build"]["min_os"], requires.macos.as_str());
        assert_eq!(inputs["linux_build"]["glibc"], requires.glibc.as_str());
        for floor in [&requires.macos, &requires.glibc] {
            assert_eq!(older_than(floor, floor), Some(false), "{floor}");
        }
    }

    #[test]
    fn versions_compare_numerically() {
        let cases = [
            ("14.7.1", "15.0", Some(true)),
            ("15", "15.0", Some(false)),
            ("15.0", "15", Some(false)),
            ("15.0.1", "15.0", Some(false)),
            ("26.1", "15.0", Some(false)),
            ("2.35", "2.36", Some(true)),
            ("2.36", "2.36", Some(false)),
            ("2.100", "2.36", Some(false)),
            (" 2.39\n", "2.36", Some(false)),
            ("2.36-ubuntu", "2.36", None),
            ("", "2.36", None),
            ("2.36", "x", None),
        ];
        for (found, floor, expected) in cases {
            assert_eq!(older_than(found, floor), expected, "{found:?} vs {floor}");
        }
    }

    #[test]
    fn too_old_system_is_told_the_way_out() {
        let m = too_old_message("glibc", "2.36", Some("2.35")).unwrap();
        assert!(
            m.contains("glibc 2.35") && m.contains("2.36") && m.contains("--pg-bindir"),
            "{m}"
        );
        assert_eq!(too_old_message("glibc", "2.36", Some("2.36")), None);
        // Unknown or unreadable: let it through.
        assert_eq!(too_old_message("macOS", "15.0", None), None);
        assert_eq!(too_old_message("macOS", "15.0", Some("fifteen")), None);
        // No floor for a Windows bundle yet (#397).
        assert_eq!(
            system_too_old(
                "x86_64-pc-windows-msvc",
                &bundled_release().unwrap().requires
            ),
            None
        );
    }

    #[test]
    fn this_computers_system_version_is_readable() {
        let _spawn = crate::test_support::spawn_guard();
        let version = if cfg!(target_os = "macos") {
            macos_version()
        } else if cfg!(all(target_os = "linux", target_env = "gnu")) {
            glibc_version()
        } else {
            return;
        };
        let version = version.expect("the system version is readable");
        assert_eq!(older_than(&version, "1.0"), Some(false), "{version}");
        let target = host_target().unwrap();
        assert_eq!(system_too_old(target, &test_requires()), None);
    }

    #[test]
    fn pg_search_flag_is_read_from_the_manifest() {
        let tmp = tempfile::tempdir().unwrap();
        let root = tmp.path().join(VERSION);
        let bindir = root.join(PGDIST_BIN_SUBDIR);
        std::fs::create_dir_all(&bindir).unwrap();
        let manifest = root.join(PGDIST_MANIFEST_FILE);
        let write = |pg_search: &str| {
            std::fs::write(
                &manifest,
                format!(r#"{{"version":"{VERSION}","target":"{TARGET}"{pg_search}}}"#),
            )
            .unwrap();
        };
        write(r#","pg_search":false"#);
        assert!(built_without_pg_search(&bindir));
        assert!(!built_without_pg_search(&root.join("bin")));
        write(r#","pg_search":true"#);
        assert!(!built_without_pg_search(&bindir));
        write("");
        assert!(!built_without_pg_search(&bindir));
        std::fs::remove_file(&manifest).unwrap();
        assert!(!built_without_pg_search(&bindir));
    }

    #[test]
    fn leftover_archive_is_deleted_by_a_later_run() {
        let _spawn = crate::test_support::spawn_guard();
        let tmp = tempfile::tempdir().unwrap();
        let cfg = tmp.path().join("cfg");
        let a = archive(tmp.path(), VERSION, TARGET, true);
        let release = release_for(&a);
        let bytes = std::fs::read(&a).unwrap();
        seed_download(&cfg, &release, &bytes);
        ensure_pgdist(&cfg, &release, TARGET, &mut |_, _| {}).unwrap();
        // As if the first run could not delete it.
        let left = seed_download(&cfg, &release, &bytes);
        let (_, warnings) = ensure_pgdist(&cfg, &release, TARGET, &mut |_, _| {}).unwrap();
        assert!(warnings.is_empty(), "{warnings:?}");
        assert!(!left.exists());
    }

    #[test]
    fn undeletable_archive_is_a_warning() {
        let tmp = tempfile::tempdir().unwrap();
        // A non-empty folder in its place cannot be removed as a file.
        let blocked = tmp.path().join("archive.tar.gz");
        std::fs::create_dir_all(blocked.join("x")).unwrap();
        let warnings = remove_archive(&blocked);
        assert!(
            warnings.len() == 1 && warnings[0].contains("could not be deleted"),
            "{warnings:?}"
        );
        assert!(remove_archive(&tmp.path().join("gone")).is_empty());
    }

    #[test]
    fn release_pins_every_target() {
        let release = bundled_release().unwrap();
        let inputs: serde_json::Value =
            serde_json::from_str(include_str!("../../pgdist/inputs.json")).unwrap();
        let built: std::collections::BTreeSet<&String> =
            inputs["targets"].as_object().unwrap().keys().collect();
        let pinned: std::collections::BTreeSet<&String> = release.assets.keys().collect();
        assert_eq!(pinned, built, "every built target needs a pinned asset");
    }

    #[test]
    fn verified_download_is_installed_once() {
        let _spawn = crate::test_support::spawn_guard();
        let tmp = tempfile::tempdir().unwrap();
        let cfg = tmp.path().join("cfg");
        let a = archive(tmp.path(), VERSION, TARGET, true);
        let release = release_for(&a);
        let seeded = seed_download(&cfg, &release, &std::fs::read(&a).unwrap());
        let (got, warnings) = ensure_pgdist(&cfg, &release, TARGET, &mut |_, _| {}).unwrap();
        assert!(warnings.is_empty(), "{warnings:?}");
        assert!(got.bindir().join("marker").is_file());
        assert!(!seeded.exists(), "the archive is deleted once unpacked");
        let pgdist = cfg.join(PGDIST_DIR_NAME);
        assert!(!pgdist.join(format!(".{VERSION}{PARTIAL_SUFFIX}")).exists());
        // The archive is gone, the release cannot be fetched and no longer
        // lists this target, so this succeeds only by finding the installed
        // bundle.
        let mut release = release;
        release.assets.clear();
        let (again, warnings) = ensure_pgdist(&cfg, &release, TARGET, &mut |_, _| {}).unwrap();
        assert!(warnings.is_empty(), "{warnings:?}");
        assert_eq!(again, got);
    }

    #[test]
    fn damaged_download_is_never_unpacked() {
        let _spawn = crate::test_support::spawn_guard();
        let tmp = tempfile::tempdir().unwrap();
        let cfg = tmp.path().join("cfg");
        let a = archive(tmp.path(), VERSION, TARGET, true);
        let release = release_for(&a);
        let mut bytes = std::fs::read(&a).unwrap();
        bytes[0] ^= 0xff;
        seed_download(&cfg, &release, &bytes);
        let err = ensure_pgdist(&cfg, &release, TARGET, &mut |_, _| {})
            .unwrap_err()
            .to_string();
        assert!(err.contains("127.0.0.1:1"), "{err}");
        assert!(!cfg.join(PGDIST_DIR_NAME).join(VERSION).exists());
    }

    #[test]
    fn installed_bundle_for_another_target_is_an_error() {
        let tmp = tempfile::tempdir().unwrap();
        let pgdist = tmp.path().join(PGDIST_DIR_NAME);
        let root = pgdist.join(VERSION);
        std::fs::create_dir_all(&root).unwrap();
        let manifest = root.join(PGDIST_MANIFEST_FILE);
        std::fs::write(
            &manifest,
            format!(r#"{{"version":"{VERSION}","target":"x86_64-apple-darwin"}}"#),
        )
        .unwrap();
        assert!(installed(&pgdist, VERSION, TARGET).is_err());
        std::fs::write(&manifest, "{").unwrap();
        assert!(installed(&pgdist, VERSION, TARGET).is_err());
    }

    #[test]
    fn targets_map_to_bundles() {
        let cases = [
            (("macos", "aarch64", ""), Some("aarch64-apple-darwin")),
            (("macos", "x86_64", ""), Some("x86_64-apple-darwin")),
            (
                ("windows", "x86_64", "msvc"),
                Some("x86_64-pc-windows-msvc"),
            ),
            (("linux", "x86_64", "gnu"), Some("x86_64-unknown-linux-gnu")),
            (
                ("linux", "aarch64", "gnu"),
                Some("aarch64-unknown-linux-gnu"),
            ),
            // A musl bml most likely runs where glibc is missing (Alpine),
            // and the Linux bundles need glibc.
            (("linux", "x86_64", "musl"), None),
            (("windows", "aarch64", "msvc"), None),
            (("freebsd", "x86_64", ""), None),
        ];
        for ((os, arch, env), expected) in cases {
            assert_eq!(target_for(os, arch, env), expected, "{os} {arch} {env}");
        }
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
    fn rename_retry_gives_up_on_other_errors() {
        let tmp = tempfile::tempdir().unwrap();
        let missing = tmp.path().join("missing");
        let err = rename_with_retry(&missing, &tmp.path().join("to")).unwrap_err();
        assert_eq!(err.kind(), std::io::ErrorKind::NotFound);
        let from = tmp.path().join("from");
        std::fs::create_dir(&from).unwrap();
        rename_with_retry(&from, &tmp.path().join("to")).unwrap();
        assert!(tmp.path().join("to").is_dir());
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
