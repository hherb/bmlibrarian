//! Binary-COPY loader: staging TEMP tables + the shared set-based merge
//! (`../sql/staging.sql`, `../sql/merge.sql`), so Rust runs exactly the SQL that
//! the Python COPY variants run.

use std::path::Path;

use anyhow::{Context, Result, bail};
use chrono::NaiveDate;
use postgres::binary_copy::BinaryCopyInWriter;
use postgres::types::{ToSql, Type};
use postgres::{Client, NoTls};
use serde_json::{Value, json};

use crate::parse::Article;

pub const ALLOWED_DATABASE: &str = "bmlibrarian_dev";
const STATEMENT_SEPARATOR: &str = "-- ;;";

/// Connection settings from `~/.bmlibrarian/.env`, forced to the dev database.
pub fn connection_string() -> Result<String> {
    if let Some(home) = std::env::var_os("HOME") {
        let _ = dotenvy::from_path(Path::new(&home).join(".bmlibrarian/.env"));
    }
    let db = std::env::var("SPIKE_DB").unwrap_or_else(|_| ALLOWED_DATABASE.to_string());
    if db != ALLOWED_DATABASE {
        bail!("refusing to run against {db:?}; only {ALLOWED_DATABASE} is allowed");
    }
    let get = |k: &str, d: &str| std::env::var(k).unwrap_or_else(|_| d.to_string());
    let mut conn = format!(
        "host={} port={} dbname={db} user={}",
        get("POSTGRES_HOST", "localhost"),
        get("POSTGRES_PORT", "5432"),
        get("POSTGRES_USER", "postgres")
    );
    if let Ok(pw) = std::env::var("POSTGRES_PASSWORD") {
        conn.push_str(&format!(" password='{}'", pw.replace('\'', "\\'")));
    }
    Ok(conn)
}

/// Split a shared SQL file into statements.
pub fn statements(sql_dir: &Path, name: &str) -> Result<Vec<String>> {
    let text = std::fs::read_to_string(sql_dir.join(name)).with_context(|| format!("reading {name}"))?;
    Ok(text
        .split(STATEMENT_SEPARATOR)
        .map(str::trim)
        .filter(|s| !s.is_empty())
        .map(str::to_string)
        .collect())
}

/// Same rule as the Python variants: only real ISO dates reach the date column.
fn valid_date(s: &Option<String>) -> Option<NaiveDate> {
    s.as_deref().and_then(|d| NaiveDate::parse_from_str(d, "%Y-%m-%d").ok().filter(|_| d.len() == 10))
}

fn non_empty(s: &Option<String>) -> Option<&str> {
    s.as_deref().filter(|v| !v.is_empty())
}

fn has_metadata(a: &Article) -> bool {
    !a.grants.is_empty() || !a.publication_types.is_empty() || a.is_retracted || !a.affiliations.is_empty()
}

/// COPY one file's articles into staging and merge them, recording the file in
/// the ingest ledger in the same transaction (the resumability checkpoint).
pub fn load_articles(
    client: &mut Client,
    sql_dir: &Path,
    articles: &[Article],
    file: &str,
    started: std::time::Instant,
) -> Result<()> {
    let staging = statements(sql_dir, "staging.sql")?;
    let merge = statements(sql_dir, "merge.sql")?;
    let mut tx = client.transaction()?;
    for s in &staging {
        tx.batch_execute(s)?;
    }

    let doc_types = [
        Type::INT4, Type::TEXT, Type::TEXT, Type::TEXT, Type::TEXT, Type::TEXT_ARRAY,
        Type::TEXT, Type::DATE, Type::TEXT, Type::TEXT_ARRAY, Type::TEXT_ARRAY,
    ];
    let sink = tx.copy_in(
        "COPY stage_document (ord, external_id, doi, title, abstract, authors, publication, \
         publication_date, url, mesh_terms, keywords) FROM STDIN BINARY",
    )?;
    let mut w = BinaryCopyInWriter::new(sink, &doc_types);
    for (ord, a) in articles.iter().enumerate() {
        let ord = ord as i32;
        let abstract_md = Some(a.abstract_md.as_str()).filter(|s| !s.is_empty());
        let url = format!("https://pubmed.ncbi.nlm.nih.gov/{}/", a.pmid);
        let date = valid_date(&a.publication_date);
        let row: [&(dyn ToSql + Sync); 11] = [
            &ord, &a.pmid, &non_empty(&a.doi), &a.title, &abstract_md, &a.authors,
            &non_empty(&a.publication), &date, &url, &a.mesh_terms, &a.keywords,
        ];
        w.write(&row)?;
    }
    w.finish()?;

    let meta_types = [Type::INT4, Type::TEXT, Type::JSONB, Type::TEXT_ARRAY, Type::BOOL, Type::JSONB];
    let sink = tx.copy_in(
        "COPY stage_metadata (ord, external_id, grants, publication_types, is_retracted, \
         author_affiliations) FROM STDIN BINARY",
    )?;
    let mut w = BinaryCopyInWriter::new(sink, &meta_types);
    for (ord, a) in articles.iter().enumerate().filter(|(_, a)| has_metadata(a)) {
        let ord = ord as i32;
        let grants: Option<Value> = (!a.grants.is_empty()).then(|| {
            Value::Array(a.grants.iter()
                .map(|g| json!({"agency": g.agency, "grant_id": g.grant_id, "country": g.country}))
                .collect())
        });
        let pub_types: Option<&Vec<String>> = (!a.publication_types.is_empty()).then_some(&a.publication_types);
        let affs: Option<Value> = (!a.affiliations.is_empty()).then(|| {
            Value::Array(a.affiliations.iter()
                .map(|(n, af)| json!({"author": n, "affiliations": af}))
                .collect())
        });
        let row: [&(dyn ToSql + Sync); 6] = [&ord, &a.pmid, &grants, &pub_types, &a.is_retracted, &affs];
        w.write(&row)?;
    }
    w.finish()?;

    for s in &merge {
        tx.batch_execute(s)?;
    }
    tx.execute(
        "INSERT INTO spike_ingest.ingest_ledger (file, articles, seconds) VALUES ($1, $2, $3) \
         ON CONFLICT (file) DO UPDATE SET articles = EXCLUDED.articles, seconds = EXCLUDED.seconds, \
         finished_at = clock_timestamp()",
        &[&file, &(articles.len() as i32), &(started.elapsed().as_secs_f32())],
    )?;
    tx.commit()?;
    Ok(())
}

/// Open a dev-database connection.
pub fn connect() -> Result<Client> {
    Ok(Client::connect(&connection_string()?, NoTls)?)
}
