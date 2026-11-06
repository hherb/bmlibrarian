//! Private, per-user PostgreSQL server for BMLibrarian.
//!
//! Turns a set of PostgreSQL 18 binaries (plus optional extension folders) into
//! a server that runs as the user, listens only on `127.0.0.1` on a
//! non-standard port, and holds an empty `bmlibrarian` database with its
//! extensions. It never touches another PostgreSQL or the Python app's
//! configuration.

pub mod conf;
pub mod envfile;
pub mod port;
pub mod state;
