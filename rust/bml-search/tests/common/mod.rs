//! Helpers for integration tests that need a real PostgreSQL 18.
#![allow(dead_code)]

use std::path::PathBuf;
use std::sync::{Mutex, MutexGuard};

/// PostgreSQL bin folder from `BML_TEST_PG_BINDIR`; tests skip without it,
/// except on CI, where a skipped integration test would pass unnoticed.
pub fn test_bindir() -> Option<PathBuf> {
    let bindir = std::env::var_os("BML_TEST_PG_BINDIR")
        .filter(|v| !v.is_empty())
        .map(PathBuf::from);
    assert!(
        bindir.is_some() || std::env::var_os("CI").is_none(),
        "BML_TEST_PG_BINDIR must be set when integration tests run on CI"
    );
    bindir
}

/// Extension folders from `BML_TEST_PG_EXTENSION_DIRS` (OS path-list syntax).
pub fn test_extension_dirs() -> Vec<PathBuf> {
    std::env::var_os("BML_TEST_PG_EXTENSION_DIRS")
        .map(|v| {
            std::env::split_paths(&v)
                .filter(|p| !p.as_os_str().is_empty())
                .collect()
        })
        .unwrap_or_default()
}

/// Whether one of the [`test_extension_dirs`] holds pg_search (a pgdist
/// bundle's extension folder may hold only pgvector).
pub fn test_provides_pg_search() -> bool {
    test_extension_dirs()
        .iter()
        .any(|d| bml_pgserver::conf::provides_pg_search(d))
}

static SERIAL: Mutex<()> = Mutex::new(());

/// Serialise integration tests so two never race for the same port.
pub fn serial() -> MutexGuard<'static, ()> {
    SERIAL
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner())
}
