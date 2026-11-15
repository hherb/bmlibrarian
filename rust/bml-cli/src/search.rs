//! `bml search`: search the library by meaning (for checking a library; the
//! app's search screen calls the same `bml_search::search`).

use std::path::Path;
use std::process::ExitCode;

use bml_db::library::load_library;
use bml_library::index::load_model_embedder;
use clap::Args;

use crate::library::{database, LibraryCliError};
use crate::server::{say, EXIT_FAILED, EXIT_HEALTHY, EXIT_NOT_SET_UP};

/// How many papers `bml search` shows unless told otherwise.
pub const DEFAULT_LIMIT: usize = 10;

/// `bml search` arguments.
#[derive(Args)]
pub struct SearchArgs {
    /// What to look for, in plain words.
    query: String,
    /// How many papers to show.
    #[arg(long, default_value_t = DEFAULT_LIMIT, value_parser = parse_limit)]
    limit: usize,
}

/// `--limit`: a whole number of papers, at least one.
fn parse_limit(raw: &str) -> Result<usize, String> {
    match raw.parse::<usize>() {
        Ok(n) if n > 0 => Ok(n),
        _ => Err(format!("{raw:?} is not a number of papers (1 or more)")),
    }
}

/// Run `bml search` with configuration in `config_dir`.
///
/// # Errors
///
/// The library record or the database settings cannot be read.
pub fn run(args: &SearchArgs, config_dir: &Path) -> Result<ExitCode, LibraryCliError> {
    if load_library(config_dir)?.is_none() {
        eprintln!("No library is set up yet. Run `bml setup` first.");
        return Ok(ExitCode::from(EXIT_NOT_SET_UP));
    }
    let mut db = match database(config_dir)? {
        Ok(db) => db,
        Err(code) => return Ok(code),
    };
    let mut embedder = match load_model_embedder(&bml_setup::gguf_path(config_dir)) {
        Ok(e) => e,
        Err(e) => {
            eprintln!("error: {e}");
            return Ok(ExitCode::from(EXIT_FAILED));
        }
    };
    let hits = match bml_search::search(&mut db, embedder.as_mut(), &args.query, args.limit) {
        Ok(hits) => hits,
        Err(e) => {
            eprintln!("error: {e}");
            return Ok(ExitCode::from(EXIT_FAILED));
        }
    };
    if hits.is_empty() {
        say!("No papers match yet.");
    }
    for (rank, hit) in hits.iter().enumerate() {
        let year = hit.year.map(|y| format!(" · {y}")).unwrap_or_default();
        say!("{}. {}", rank + 1, hit.title);
        say!(
            "   {}{year}",
            hit.journal.as_deref().unwrap_or("(journal unknown)")
        );
        say!("   {}", hit.passage.replace('\n', " "));
        say!("");
    }
    Ok(ExitCode::from(EXIT_HEALTHY))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn limit_is_a_positive_number() {
        assert_eq!(parse_limit("5"), Ok(5));
        assert!(parse_limit("0").is_err());
        assert!(parse_limit("-1").is_err());
        assert!(parse_limit("ten").is_err());
    }
}
