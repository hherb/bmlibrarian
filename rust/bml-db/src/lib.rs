//! The BMLibrarian library: the folder holding the papers (and, for a private
//! server, the database), and the database schema the library is stored in.

pub mod library;
pub mod schema;

pub use schema::*;
