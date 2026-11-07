//! Memory and disk checks that warn, never block, before the big downloads.

use std::fmt;
use std::path::{Path, PathBuf};

/// Bytes in a decimal gigabyte, for messages shown to people.
const BYTES_PER_GB: f64 = 1_000_000_000.0;

/// Memory below which the language models are very slow (16 GB).
pub const MIN_RAM_BYTES: u64 = 16_000_000_000;

/// Something worth telling the user about before setup continues.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum HardwareWarning {
    /// Less memory than the models need.
    LowRam {
        /// Memory this computer has.
        total: u64,
        /// Memory the models need.
        recommended: u64,
    },
    /// Less free disk space than the downloads need.
    LowDisk {
        /// A folder on the short disk.
        path: PathBuf,
        /// Free bytes there.
        free: u64,
        /// Bytes setup will put there.
        needed: u64,
    },
}

fn gb(bytes: u64) -> f64 {
    bytes as f64 / BYTES_PER_GB
}

impl fmt::Display for HardwareWarning {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::LowRam { total, recommended } => write!(
                f,
                "This computer has {:.1} GB of memory; the models need about {:.1} GB. \
                 Setup continues, but answers may be very slow.",
                gb(*total),
                gb(*recommended)
            ),
            Self::LowDisk { path, free, needed } => write!(
                f,
                "The disk holding {} has {:.1} GB free; setup needs about {:.1} GB there. \
                 Free some space or choose another location.",
                path.display(),
                gb(*free),
                gb(*needed)
            ),
        }
    }
}

/// Free bytes on the disk holding `path`: the mount point that is the longest
/// prefix of it, matched by path components. `None` if no mount contains it.
pub fn free_space_at(path: &Path, mounts: &[(PathBuf, u64)]) -> Option<u64> {
    mounts
        .iter()
        .filter(|(mount, _)| path.starts_with(mount))
        .max_by_key(|(mount, _)| mount.components().count())
        .map(|(_, free)| *free)
}

/// `path` itself or its nearest parent that exists.
pub fn nearest_existing_ancestor(path: &Path) -> Option<PathBuf> {
    path.ancestors().find(|p| p.exists()).map(Path::to_path_buf)
}

/// A warning when `total` memory is under [`MIN_RAM_BYTES`].
pub fn ram_warning(total: u64) -> Option<HardwareWarning> {
    (total < MIN_RAM_BYTES).then_some(HardwareWarning::LowRam {
        total,
        recommended: MIN_RAM_BYTES,
    })
}

/// One warning per disk whose free space is below the sum of the `needs`
/// (folder, bytes) placed on it. Needs on unknown disks are skipped.
pub fn disk_warnings(needs: &[(PathBuf, u64)], mounts: &[(PathBuf, u64)]) -> Vec<HardwareWarning> {
    // (mount, free, needed, first path)
    let mut per_mount: Vec<(&Path, u64, u64, &Path)> = Vec::new();
    for (path, need) in needs {
        let probe = nearest_existing_ancestor(path).unwrap_or_else(|| path.clone());
        let Some((mount, free)) = mounts
            .iter()
            .filter(|(m, _)| probe.starts_with(m))
            .max_by_key(|(m, _)| m.components().count())
        else {
            continue;
        };
        match per_mount.iter_mut().find(|e| e.0 == mount.as_path()) {
            Some(e) => e.2 += need,
            None => per_mount.push((mount, *free, *need, path)),
        }
    }
    per_mount
        .into_iter()
        .filter(|(_, free, needed, _)| free < needed)
        .map(|(_, free, needed, path)| HardwareWarning::LowDisk {
            path: path.to_path_buf(),
            free,
            needed,
        })
        .collect()
}

/// Mount points of this computer's disks with their free bytes.
pub fn mounts() -> Vec<(PathBuf, u64)> {
    sysinfo::Disks::new_with_refreshed_list()
        .iter()
        .map(|d| (d.mount_point().to_path_buf(), d.available_space()))
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn m(p: &str, free: u64) -> (PathBuf, u64) {
        (PathBuf::from(p), free)
    }

    #[test]
    fn free_space_uses_longest_mount_prefix() {
        let mounts = [m("/", 10), m("/Volumes/Data", 99)];
        assert_eq!(
            free_space_at(Path::new("/Volumes/Data/x/y"), &mounts),
            Some(99)
        );
        assert_eq!(free_space_at(Path::new("/Users/me"), &mounts), Some(10));
        assert_eq!(
            free_space_at(Path::new("/Volumes/Data2/x"), &mounts),
            Some(10)
        );
    }

    #[cfg(windows)]
    #[test]
    fn free_space_distinguishes_drives() {
        let mounts = [m("C:\\", 1), m("D:\\", 2)];
        assert_eq!(free_space_at(Path::new("D:\\x"), &mounts), Some(2));
        assert_eq!(free_space_at(Path::new("C:\\x"), &mounts), Some(1));
    }

    #[test]
    fn disk_warnings_sum_per_mount() {
        let mounts = [m("/", 10)];
        let needs = [(PathBuf::from("/a"), 6), (PathBuf::from("/b"), 6)];
        let w = disk_warnings(&needs, &mounts);
        assert_eq!(w.len(), 1);
        assert!(matches!(
            w[0],
            HardwareWarning::LowDisk {
                needed: 12,
                free: 10,
                ..
            }
        ));
        assert!(disk_warnings(&[(PathBuf::from("/a"), 6)], &mounts).is_empty());
    }

    #[test]
    fn ram_warning_threshold() {
        assert!(ram_warning(MIN_RAM_BYTES).is_none());
        assert!(ram_warning(MIN_RAM_BYTES - 1).is_some());
    }

    #[test]
    fn ancestor_walks_up_to_existing() {
        let tmp = tempfile::tempdir().unwrap();
        let deep = tmp.path().join("a/b/c");
        assert_eq!(
            nearest_existing_ancestor(&deep).as_deref(),
            Some(tmp.path())
        );
    }

    #[test]
    fn warnings_read_in_plain_language() {
        let text = ram_warning(8_000_000_000).unwrap().to_string();
        assert!(
            text.contains("8.0 GB of memory") && text.contains("16.0 GB"),
            "{text}"
        );
    }
}
