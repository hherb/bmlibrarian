//! Helpers for integration tests that need a real PostgreSQL 18.
#![allow(dead_code)]

use std::path::PathBuf;
use std::sync::{Mutex, MutexGuard};

/// PostgreSQL bin folder from `BML_TEST_PG_BINDIR`; tests skip without it.
pub fn test_bindir() -> Option<PathBuf> {
    std::env::var_os("BML_TEST_PG_BINDIR")
        .filter(|v| !v.is_empty())
        .map(PathBuf::from)
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

static SERIAL: Mutex<()> = Mutex::new(());

/// Serialise integration tests so two never race for the same port.
pub fn serial() -> MutexGuard<'static, ()> {
    SERIAL
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner())
}
