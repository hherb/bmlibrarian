//! The library's database schema and [`migrate`].
//!
//! [`migrate`] brings a database up to date: bmlib's publication tables
//! (`ensure_schema`, run every time so columns a newer bmlib adds appear),
//! then BMLibrarian's own [`migrations`] through bmlib's runner, which records
//! applied versions in `schema_version`. Each migration runs its statements
//! one per `execute` call, so bmlib's SQL splitter (which knows no `$$`
//! blocks) is never involved, and choices such as BM25 or tsvector are plain
//! Rust.

use bmlib::db::{execute, fetch_one, run_migrations, Db, DbError, Migration, Value};
use bmlib::embed::EMBEDDING_DIM;
use bmlib::publications::schema::ensure_schema;

/// Session advisory lock key held while migrating, so two setups never apply
/// the same migration at once (an arbitrary constant owned by BMLibrarian).
pub const MIGRATION_LOCK_KEY: i64 = 0x424D_4C5F_4442; // "BML_DB"

/// Per-paper full-text state: which form is held, or why only the abstract.
pub const PUBLICATION_FULLTEXT: &str = "publication_fulltext";
/// Chunks of a paper's title + abstract and canonical full text.
pub const CHUNKS: &str = "chunks";
/// One `halfvec` embedding per chunk.
pub const CHUNK_EMBEDDINGS: &str = "chunk_embeddings";
/// Per-paper indexing state and the label of its chunk set.
pub const PUBLICATION_INDEX: &str = "publication_index";
/// The pg_search BM25 index on chunk text (where pg_search is installed).
pub const CHUNKS_BM25_INDEX: &str = "chunks_text_bm25";
/// The GIN index on the chunk text's tsvector (where pg_search is not).
pub const CHUNKS_TSV_INDEX: &str = "chunks_text_tsv_gin";
/// The HNSW index on chunk embeddings.
pub const CHUNK_EMBEDDINGS_HNSW_INDEX: &str = "chunk_embeddings_hnsw";
/// HNSW `m` (Rust plan §3.3, measured).
pub const HNSW_M: u32 = 16;
/// HNSW `ef_construction` (Rust plan §3.3, measured).
pub const HNSW_EF_CONSTRUCTION: u32 = 64;

/// Which lexical index the chunk text has.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum LexicalIndex {
    /// pg_search BM25: query `text ||| $1 ORDER BY pdb.score(id) DESC`.
    Bm25,
    /// `tsvector` + GIN: query `text_tsv @@ plainto_tsquery('english', $1)`.
    TsVector,
}

/// The `chunk_embeddings` table and its HNSW index.
fn vector_ddl() -> String {
    format!(
        "CREATE TABLE IF NOT EXISTS {CHUNK_EMBEDDINGS} (\
         chunk_id BIGINT PRIMARY KEY REFERENCES {CHUNKS}(id) ON DELETE CASCADE, \
         embedding halfvec({EMBEDDING_DIM}) NOT NULL)"
    )
}

/// Migration 1: the library tables.
fn library_tables(db: &mut dyn Db) -> bmlib::db::Result<()> {
    let statements = [
        format!(
            "CREATE TABLE IF NOT EXISTS {PUBLICATION_FULLTEXT} (\
             publication_id INTEGER PRIMARY KEY REFERENCES publications(id) ON DELETE CASCADE, \
             form TEXT NOT NULL CHECK (form IN ('jats', 'pdf', 'html', 'abstract')), \
             version_held TEXT, \
             cache_key TEXT, \
             cache_path TEXT, \
             attempts INTEGER NOT NULL DEFAULT 0, \
             last_error TEXT, \
             last_error_kind TEXT CHECK (last_error_kind IN ('lasting', 'passing')), \
             retry_after TIMESTAMPTZ, \
             updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), \
             CHECK (form = 'abstract' OR cache_path IS NOT NULL))"
        ),
        format!(
            "CREATE INDEX IF NOT EXISTS {PUBLICATION_FULLTEXT}_retry \
             ON {PUBLICATION_FULLTEXT} (retry_after) WHERE form = 'abstract'"
        ),
        format!(
            "CREATE TABLE IF NOT EXISTS {CHUNKS} (\
             id BIGSERIAL PRIMARY KEY, \
             publication_id INTEGER NOT NULL REFERENCES publications(id) ON DELETE CASCADE, \
             ordinal INTEGER NOT NULL, \
             kind TEXT NOT NULL CHECK (kind IN ('abstract', 'fulltext')), \
             text TEXT NOT NULL, \
             span_start INTEGER, \
             span_end INTEGER, \
             UNIQUE (publication_id, ordinal), \
             CHECK (kind = 'abstract' OR (span_start IS NOT NULL AND span_end IS NOT NULL \
               AND span_start >= 0 AND span_end >= span_start)))"
        ),
        vector_ddl(),
        format!(
            "CREATE INDEX IF NOT EXISTS {CHUNK_EMBEDDINGS_HNSW_INDEX} ON {CHUNK_EMBEDDINGS} \
             USING hnsw (embedding halfvec_cosine_ops) \
             WITH (m = {HNSW_M}, ef_construction = {HNSW_EF_CONSTRUCTION})"
        ),
        format!(
            "CREATE TABLE IF NOT EXISTS {PUBLICATION_INDEX} (\
             publication_id INTEGER PRIMARY KEY REFERENCES publications(id) ON DELETE CASCADE, \
             status TEXT NOT NULL CHECK (status IN ('pending', 'complete')), \
             model_sha256 TEXT, \
             recipe_version INTEGER, \
             chunker_version INTEGER, \
             converter_version TEXT, \
             text_sha256 TEXT, \
             chunk_count INTEGER, \
             updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), \
             CHECK (status <> 'complete' OR (model_sha256 IS NOT NULL \
               AND recipe_version IS NOT NULL AND chunker_version IS NOT NULL \
               AND converter_version IS NOT NULL AND text_sha256 IS NOT NULL \
               AND chunk_count IS NOT NULL)))"
        ),
    ];
    for sql in &statements {
        execute(db, sql, &[])?;
    }
    // shortcut: decided once, here; pg_search installed after this migration
    // ran is not picked up (needs a later migration that switches indexes).
    let pg_search = fetch_one(
        db,
        "SELECT 1 AS present FROM pg_extension WHERE extname = 'pg_search'",
        &[],
    )?
    .is_some();
    let lexical = if pg_search {
        vec![format!(
            "CREATE INDEX IF NOT EXISTS {CHUNKS_BM25_INDEX} ON {CHUNKS} USING bm25 \
             (id, (text::pdb.simple('stemmer=english', 'stopwords_language=English'))) \
             WITH (key_field = 'id')"
        )]
    } else {
        vec![
            format!(
                "ALTER TABLE {CHUNKS} ADD COLUMN IF NOT EXISTS text_tsv tsvector \
                 GENERATED ALWAYS AS (to_tsvector('english', text)) STORED"
            ),
            format!(
                "CREATE INDEX IF NOT EXISTS {CHUNKS_TSV_INDEX} ON {CHUNKS} USING gin (text_tsv)"
            ),
        ]
    };
    for sql in &lexical {
        execute(db, sql, &[])?;
    }
    Ok(())
}

/// BMLibrarian's migrations, in version order.
#[must_use]
pub fn migrations() -> Vec<Migration> {
    vec![Migration::new(1, "library_tables", library_tables)]
}

/// Bring the database up to date (see the module docs); returns how many of
/// BMLibrarian's migrations were applied. Holds [`MIGRATION_LOCK_KEY`] while
/// it runs, and releases it even when a migration fails.
///
/// # Errors
///
/// Whatever the server reports. A failed BMLibrarian migration leaves neither
/// its tables nor its version row; bmlib's `ensure_schema` runs statement by
/// statement, so it can stop part way (re-running completes it).
pub fn migrate(db: &mut dyn Db) -> Result<usize, DbError> {
    execute(
        db,
        "SELECT pg_advisory_lock(?)",
        &[Value::Int(MIGRATION_LOCK_KEY)],
    )?;
    let result = ensure_schema(db).and_then(|()| run_migrations(db, migrations()));
    let unlocked = execute(
        db,
        "SELECT pg_advisory_unlock(?)",
        &[Value::Int(MIGRATION_LOCK_KEY)],
    );
    let applied = result?;
    unlocked?;
    Ok(applied)
}

/// Which lexical index the chunk text has; `None` before migration 1 ran.
///
/// # Errors
///
/// Whatever the catalog query reports.
pub fn lexical_index(db: &mut dyn Db) -> Result<Option<LexicalIndex>, DbError> {
    let mut has = |index: &str| -> Result<bool, DbError> {
        Ok(fetch_one(
            db,
            "SELECT 1 AS present FROM pg_indexes WHERE schemaname = current_schema() \
             AND tablename = ? AND indexname = ?",
            &[Value::Text(CHUNKS.into()), Value::Text(index.into())],
        )?
        .is_some())
    };
    Ok(if has(CHUNKS_BM25_INDEX)? {
        Some(LexicalIndex::Bm25)
    } else if has(CHUNKS_TSV_INDEX)? {
        Some(LexicalIndex::TsVector)
    } else {
        None
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use bmlib::embed::EMBEDDING_DIM;

    #[test]
    fn migration_versions_are_unique_and_ascending() {
        let versions: Vec<i64> = migrations().iter().map(|m| m.version).collect();
        assert!(!versions.is_empty());
        assert!(versions.windows(2).all(|w| w[0] < w[1]), "{versions:?}");
        assert_eq!(versions[0], 1);
    }

    #[test]
    fn ddl_uses_embedding_dim() {
        assert!(vector_ddl().contains(&format!("halfvec({EMBEDDING_DIM})")));
    }
}
