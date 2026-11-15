//! BMLibrarian search (walking skeleton): hybrid retrieval over the library's
//! chunks — vector top-K (HNSW, cosine) with word top-K (BM25, or tsvector
//! where pg_search is missing), fused by weighted reciprocal rank, one hit per
//! paper. Developer notes: `doc/developers/search.md`.

pub mod filter;
pub mod fusion;

use std::collections::HashMap;

use bml_db::{lexical_index, LexicalIndex};
use bml_library::index::{halfvec_literal, ChunkEmbedder};
use bmlib::db::{execute, fetch_all, Db, DbError, Row, Value};
use serde::Serialize;

use crate::filter::is_boilerplate;
use crate::fusion::{best_per_paper, fuse};

/// How many chunks the vector list holds before fusion.
pub const VECTOR_K: usize = 100;
/// How many chunks the word list holds before fusion.
pub const LEXICAL_K: usize = 100;

/// One search result: a paper and the passage of it that matched best.
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct SearchHit {
    /// `publications.id`, for opening the paper.
    pub publication_id: i64,
    /// The paper's title.
    pub title: String,
    /// Its journal, when known.
    pub journal: Option<String>,
    /// Its publication year, when known.
    pub year: Option<i32>,
    /// Its authors, in order.
    pub authors: Vec<String>,
    /// The passage that matched best.
    pub passage: String,
    /// The fused score (higher is better; comparable within one search).
    pub score: f64,
}

/// Why a search could not run.
#[derive(Debug, thiserror::Error)]
pub enum SearchError {
    /// The database failed.
    #[error("the library's database failed: {0}")]
    Db(#[from] DbError),
    /// The embedding model failed.
    #[error("the search model failed: {0}")]
    Embed(String),
    /// The schema is not set up (no chunk index).
    #[error("the library's search index is not set up yet; run `bml setup`")]
    NoIndex,
}

/// ASCII whitespace, as bmlib trims it.
const ASCII_SPACE: &[char] = &[' ', '\t', '\n', '\r', '\x0C', '\x0B'];

/// The `limit` papers best matching `query`, best first; a blank query or an
/// empty library finds nothing.
///
/// # Errors
///
/// The database or the embedding model failed, or the index is not set up.
pub fn search(
    db: &mut dyn Db,
    embedder: &mut dyn ChunkEmbedder,
    query: &str,
    limit: usize,
) -> Result<Vec<SearchHit>, SearchError> {
    let query = query.trim_matches(ASCII_SPACE);
    if query.is_empty() || limit == 0 {
        return Ok(Vec::new());
    }
    let lexical = lexical_index(db)?.ok_or(SearchError::NoIndex)?;
    let vector = embedder.embed_query(query).map_err(SearchError::Embed)?;
    let by_vector = vector_ids(db, &vector)?;
    let by_words = word_ids(db, lexical, query)?;
    let fused = fuse(&by_vector, &by_words);
    if fused.is_empty() {
        return Ok(Vec::new());
    }
    let ids: Vec<i64> = fused.iter().map(|(id, _)| *id).collect();
    // Reference lists and funding statements are never shown (spec anti-goal);
    // a paper whose only matches are such passages drops out.
    let mut paper_of: HashMap<i64, i64> = HashMap::new();
    for row in select_in(
        db,
        "SELECT id, publication_id, text FROM chunks WHERE id IN",
        &ids,
    )? {
        if !is_boilerplate(row.get_str("text")?) {
            paper_of.insert(row.get_i64("id")?, row.get_i64("publication_id")?);
        }
    }
    let mut best = best_per_paper(&fused, &paper_of);
    best.truncate(limit);
    let chunk_ids: Vec<i64> = best.iter().map(|(_, chunk, _)| *chunk).collect();
    let rows = select_in(
        db,
        "SELECT c.id AS chunk_id, c.text AS passage, p.title AS title, p.journal AS journal, \
         p.publication_date AS publication_date, p.authors AS authors \
         FROM chunks c JOIN publications p ON p.id = c.publication_id WHERE c.id IN",
        &chunk_ids,
    )?;
    let mut by_chunk: HashMap<i64, &Row> = HashMap::new();
    for row in &rows {
        by_chunk.insert(row.get_i64("chunk_id")?, row);
    }
    best.iter()
        .filter_map(|(paper, chunk, score)| by_chunk.get(chunk).map(|row| (*paper, *row, *score)))
        .map(|(paper, row, score)| hit(paper, row, score))
        .collect()
}

/// The [`VECTOR_K`] chunks nearest `vector` (cosine, HNSW).
fn vector_ids(db: &mut dyn Db, vector: &[f32]) -> Result<Vec<i64>, DbError> {
    // HNSW returns at most `ef_search` rows; the default (40) is below K.
    execute(db, &format!("SET hnsw.ef_search = {VECTOR_K}"), &[])?;
    ids(fetch_all(
        db,
        "SELECT chunk_id AS id FROM chunk_embeddings \
         ORDER BY embedding <=> CAST(CAST(? AS TEXT) AS halfvec) LIMIT ?",
        &[
            Value::Text(halfvec_literal(vector)),
            Value::Int(limit_value(VECTOR_K)),
        ],
    )?)
}

/// The [`LEXICAL_K`] chunks best matching `query`'s words.
fn word_ids(db: &mut dyn Db, index: LexicalIndex, query: &str) -> Result<Vec<i64>, DbError> {
    let rows = match index {
        LexicalIndex::Bm25 => fetch_all(
            db,
            "SELECT id FROM chunks WHERE text ||| CAST(? AS TEXT) ORDER BY pdb.score(id) DESC LIMIT ?",
            &[Value::Text(query.to_string()), Value::Int(limit_value(LEXICAL_K))],
        )?,
        LexicalIndex::TsVector => fetch_all(
            db,
            "SELECT id FROM chunks WHERE text_tsv @@ plainto_tsquery('english', CAST(? AS TEXT)) \
             ORDER BY ts_rank(text_tsv, plainto_tsquery('english', CAST(? AS TEXT))) DESC, id \
             LIMIT ?",
            &[
                Value::Text(query.to_string()),
                Value::Text(query.to_string()),
                Value::Int(limit_value(LEXICAL_K)),
            ],
        )?,
    };
    ids(rows)
}

/// `k` as an SQL `LIMIT` value.
fn limit_value(k: usize) -> i64 {
    i64::try_from(k).unwrap_or(i64::MAX)
}

/// The `id` column of `rows`, in order.
fn ids(rows: Vec<Row>) -> Result<Vec<i64>, DbError> {
    rows.iter().map(|row| row.get_i64("id")).collect()
}

/// `sql` (ending in `… IN`) with a placeholder list for `ids`.
fn select_in(db: &mut dyn Db, sql: &str, ids: &[i64]) -> Result<Vec<Row>, DbError> {
    if ids.is_empty() {
        return Ok(Vec::new());
    }
    let placeholders = vec!["?"; ids.len()].join(", ");
    let params: Vec<Value> = ids.iter().map(|id| Value::Int(*id)).collect();
    fetch_all(db, &format!("{sql} ({placeholders})"), &params)
}

/// Column `name` of `row` as text, `None` when null.
fn text(row: &Row, name: &str) -> Result<Option<String>, DbError> {
    Ok(row.get(name)?.as_str().map(str::to_string))
}

/// One hit from its metadata row.
fn hit(publication_id: i64, row: &Row, score: f64) -> Result<SearchHit, SearchError> {
    let date = text(row, "publication_date")?;
    let authors = text(row, "authors")?
        .and_then(|json| serde_json::from_str::<Vec<String>>(&json).ok())
        .unwrap_or_default();
    Ok(SearchHit {
        publication_id,
        title: text(row, "title")?.unwrap_or_default(),
        journal: text(row, "journal")?,
        year: date.as_deref().and_then(year_of),
        authors,
        passage: text(row, "passage")?.unwrap_or_default(),
        score,
    })
}

/// The year of an ISO date (`2024-03-05`, `2024`).
fn year_of(date: &str) -> Option<i32> {
    date.get(..4)?.parse().ok()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn year_of_reads_iso_dates() {
        assert_eq!(year_of("2024-03-05"), Some(2024));
        assert_eq!(year_of("2021"), Some(2021));
        assert_eq!(year_of("n/a"), None);
        assert_eq!(year_of(""), None);
    }
}
