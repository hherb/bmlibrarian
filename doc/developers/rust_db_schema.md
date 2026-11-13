# Rust library schema (`bml-db`)

`rust/bml-db` holds the library folder record and the database schema of the
Rust stack. It has no UI and no server management; `bml-setup`'s Library step
and, later, the library pipeline and search use it. Design: Goal B of
`docs/superpowers/specs/2026-11-11-installer-walking-skeleton-design.md`;
plan: `docs/superpowers/plans/2026-11-13-bml-db-schema.md`.

## Library folder (`bml_db::library`)

- `Library { dir }` with `database_dir()` (`database/`, the private server's
  data folder, created by `initdb`), `documents_dir()` (`documents/`) and
  `cache()` (a bmlib `FullTextCache` rooted at `documents/`, layout
  unchanged from bmlib).
- The record is `bml-library.json` in the config folder, written with
  `bmlib::atomic::atomic_write`.
- `resolve_library(config_dir, requested, home)` is read-only: the saved
  record wins, a different `requested` folder (compared after
  `std::path::absolute`, not canonicalised) is `LibraryError::Mismatch`,
  otherwise `requested`, otherwise `home/BMLibrarian`.
- `ensure_library(config_dir, &library)` creates the folder and
  `documents/`, saves the record when none is saved, and returns whether it
  changed anything. A path that is a file is `NotAFolder`.
- External disks are not handled yet (spec, Goal B follow-up).

## `migrate(db: &mut dyn bmlib::db::Db) -> Result<usize, DbError>`

1. Takes the session advisory lock `MIGRATION_LOCK_KEY`. Two concurrent
   `CREATE TABLE IF NOT EXISTS` on one database collide in the catalog
   (`pg_class_relname_nsp_index`), so without it two setups at once fail
   (`concurrent_migrations_both_succeed` fails without the lock).
2. Runs `bmlib::publications::schema::ensure_schema` **every time**, not as a
   migration, so columns a newer bmlib adds (`ADDED_COLUMNS`) appear after a
   bmlib bump.
3. Runs `migrations()` with bmlib's `run_migrations`, which records versions
   in `schema_version` and runs each migration in one transaction.
4. Releases the lock, also on error. Returns the number of BMLibrarian
   migrations applied.

Migrations are Rust closures that run one statement per `execute` call.
bmlib's SQL splitter knows no `$$` blocks, and choices such as BM25 or tsvector
stay plain Rust. Every statement is `IF NOT EXISTS`, and none tracks itself.

The Library step connects as **`bml_app`** (`bml.env`), not the admin role:
`bml_app` owns the `bmlibrarian` database and so its `public` schema, the
tables it creates are its own, and no GRANTs are needed.

## Migration 1: `library_tables`

All foreign keys reference `publications(id) ON DELETE CASCADE` (bmlib's
table; `id` is `SERIAL`, so `INTEGER`).

| Table | Purpose and guards |
|---|---|
| `publication_fulltext` | One row per paper: `form` (`jats`/`pdf`/`html`/`abstract`), `version_held`, `cache_key`, `cache_path` (relative to `documents/`), `attempts`, `last_error`, `last_error_kind` (`lasting`/`passing`), `retry_after`. `CHECK (form = 'abstract' OR cache_path IS NOT NULL)`: a full-text form is never recorded without its file. Partial index on `retry_after` for abstract-only papers (the retry queue). |
| `chunks` | `id BIGSERIAL`, `publication_id`, `ordinal`, `kind` (`abstract` for title + abstract, `fulltext` for canonical text), `text`, `span_start`/`span_end` (code points in the canonical text, required for `fulltext`). `UNIQUE (publication_id, ordinal)`. |
| `chunk_embeddings` | `chunk_id` → `chunks(id)`, `embedding halfvec(EMBEDDING_DIM)` (256, from bmlib). HNSW index `chunk_embeddings_hnsw` (`halfvec_cosine_ops`, `m = 16`, `ef_construction = 64`, Rust plan §3.3). A single table at medRxiv scale; the partition manager is Phase C. |
| `publication_index` | Per-paper indexing state: `status` (`pending`/`complete`), the five `ChunkSetLabel` fields (`model_sha256`, `recipe_version`, `chunker_version`, `converter_version`, `text_sha256`), `chunk_count`. `CHECK`: `complete` needs every label field and the count, so a set is never marked current without its label. |
| lexical index | If `pg_search` is installed in the database (`pg_extension`): BM25 index `chunks_text_bm25` on `(id, text::pdb.simple('stemmer=english', 'stopwords_language=English'))`; query `text ||| $1 ORDER BY pdb.score(id) DESC`. Otherwise a generated `text_tsv tsvector` (`to_tsvector('english', text)`) with GIN index `chunks_text_tsv_gin`; query `text_tsv @@ plainto_tsquery('english', $1)`. `lexical_index(db)` says which one a database has. |

The lexical choice is made once, when migration 1 runs. pg_search installed
later is not picked up; switching needs a later migration (marked
`shortcut:` in `schema.rs`).

## Tests

- Unit: `cargo test -p bml-db` (library record, migration list, DDL uses
  `EMBEDDING_DIM`).
- Real PG18 (`#[ignore]`d, each test on its own temp server):
  `BML_TEST_PG_BINDIR=<PG18 bin> [BML_TEST_PG_EXTENSION_DIRS=<pg_search dir>]
  cargo test -p bml-db -- --include-ignored`. Run it with and without the
  pg_search folder to cover both lexical branches; CI has no pg_search
  (#399), so only a local run covers BM25.
