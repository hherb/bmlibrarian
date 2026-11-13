# `bml-db` + Schema (Installer Piece 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `bml setup` creates the library folder (`~/BMLibrarian` with
`database/` and `documents/`) and brings the database schema up to date:
bmlib's publications tables plus BMLibrarian's full-text state, chunk,
`halfvec(256)` + HNSW vector, lexical (BM25 or tsvector) and indexing-state
tables.

**Architecture:** A new UI-free crate `rust/bml-db` holds the library folder
record (`bml-library.json` in the config folder) and `migrate()`. `migrate()`
runs bmlib's `publications::schema::ensure_schema` on every call, then
BMLibrarian's migrations through bmlib's `run_migrations`, under a session
advisory lock. The migrations are Rust closures, so the BM25-or-tsvector choice
is plain Rust (bmlib's SQL splitter cannot handle `$$` blocks). `bml-setup`
gains a `Library` step after `Database`. `bml setup --library-dir` replaces
`--data-dir`.

**Tech Stack:** Rust 1.89 workspace `rust/`, bmlib (git pin `9670f4e`,
features `postgres` added), `postgres` 0.19, pgvector `halfvec`, ParadeDB
pg_search 0.26 (where present).

**Spec:** `docs/superpowers/specs/2026-11-11-installer-walking-skeleton-design.md`
(Goal B, piece 2). Owner decisions taken 2026-11-13: all Goal B tables land
now; `--library-dir` **replaces** `bml setup --data-dir` (`bml server init
--data-dir` is unchanged); the schema runs in a new setup step `Library`.

## Global Constraints

- PostgreSQL 18 only. The vector dimension comes from `bmlib::embed::EMBEDDING_DIM` (256). Never write the literal 256.
- HNSW: `m = 16`, `ef_construction = 64`, `halfvec_cosine_ops` (Rust plan §3.3), as named constants.
- BM25: `USING bm25 (id, (text::pdb.simple('stemmer=english', 'stopwords_language=English'))) WITH (key_field = 'id')`. Query with `text ||| $1 ORDER BY pdb.score(id) DESC` (Rust plan §3.4).
- Fallback where pg_search is not installed in the database: a generated `tsvector` column (`to_tsvector('english', text)`) plus a GIN index.
- Migrations are idempotent (`IF NOT EXISTS`) and contain no tracking code. bmlib's runner records versions in `schema_version` (golden rules 15–16).
- Migrations connect as `bml_app` (`bml.env`). It owns the `bmlibrarian` database, and so its `public` schema, which means the tables it creates need no GRANTs. This is a deliberate deviation from the spec's "admin connection".
- Default library folder `~/BMLibrarian`, holding `database/` and `documents/`. `documents/` is a bmlib `FullTextCache` root and stays unchanged.
- No magic numbers or hard-coded paths; every error reaches the user as plain words; every public item has a doc comment (`missing_docs` is on).
- A server that is already saved always resumes where it is (for example the owner's `<config>/pgdata`). Only new servers go in `<library>/database`.

## Review Focus

1. Library path with a space and non-ASCII (`My Library ü`): stored, reloaded and created unchanged. Task 1, `library_path_with_space_and_umlaut_round_trips`.
2. The chosen library path is an existing *file*: plain `LibraryError::NotAFolder`, no panic, nothing saved. Task 1, `file_as_library_is_refused`.
3. A bmlib upgrade adds a publications column: `migrate()` restores it even when every BMLibrarian migration is already applied. Task 2, `migrate_restores_a_dropped_bmlib_column`.
4. Two setups migrate at once: both succeed and each migration is applied once. Task 2, `concurrent_migrations_both_succeed`.
5. The Library step runs with no `bml.env`, or with the server stopped: `Failed` with a plain reason naming `bml setup` / `bml server start`, never a panic. Task 3, `library_step_without_database_fails_plainly` and `library_step_with_stopped_server_fails_plainly`.

---

### Task 1: `bml-db` crate and the library folder

**Files:**
- Create: `rust/bml-db/Cargo.toml`, `rust/bml-db/src/lib.rs`, `rust/bml-db/src/library.rs`
- Modify: `rust/Cargo.toml` (member `bml-db`, workspace dep `bml-db = { path = "bml-db" }`, add `"postgres"` to bmlib's features)

**Interfaces:**
- Produces (`bml_db::library`):
  - `pub const LIBRARY_FILE_NAME: &str = "bml-library.json";`
  - `pub const DEFAULT_LIBRARY_DIR_NAME: &str = "BMLibrarian";`
  - `pub const DATABASE_DIR_NAME: &str = "database";`
  - `pub const DOCUMENTS_DIR_NAME: &str = "documents";`
  - `#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)] pub struct Library { pub dir: PathBuf }` with
    `fn database_dir(&self) -> PathBuf`, `fn documents_dir(&self) -> PathBuf`,
    `fn cache(&self) -> bmlib::fulltext::cache::FullTextCache` (rooted at `documents_dir()`).
  - `pub fn load_library(config_dir: &Path) -> Result<Option<Library>, LibraryError>`
  - `pub fn resolve_library(config_dir: &Path, requested: Option<&Path>, home: Option<PathBuf>) -> Result<Library, LibraryError>`.
    Read-only. A saved record wins. A `requested` path that differs from it (both made absolute) is `LibraryError::Mismatch`. With no record: `requested`, else `home/BMLibrarian`, else `LibraryError::NoHome`. The result is always absolute.
  - `pub fn ensure_library(config_dir: &Path, library: &Library) -> Result<bool, LibraryError>`.
    Creates `dir` and `documents/` (`database/` is left to `initdb`) and saves the record when none is saved. Returns whether it created or saved anything. A `dir` that exists as a file is `NotAFolder`.
  - `#[derive(Debug, thiserror::Error)] pub enum LibraryError { NoHome, Mismatch { saved: PathBuf, requested: PathBuf }, NotAFolder(PathBuf), Io { path: PathBuf, source: io::Error }, Corrupt { path: PathBuf, message: String } }`.
    Messages are plain words. `Mismatch` says moving a library is not supported yet and names both paths.

- [ ] **Step 1: Write the failing tests** (`#[cfg(test)]` in `library.rs`, using `tempfile`)
  - `default_is_home_bmlibrarian`: `resolve_library(cfg, None, Some(home))?.dir == home.join("BMLibrarian")`, and `load_library(cfg)? == None` (nothing written).
  - `requested_wins_without_record`; `saved_record_wins_over_default`.
  - `requested_differing_from_saved_is_mismatch`: `matches!(err, LibraryError::Mismatch { .. })`. The same path given relatively (from the current dir) is **not** a mismatch.
  - `ensure_creates_documents_and_saves_once`: the first call returns `true`, `documents_dir()` is a dir, `database_dir()` does not exist, and `load_library == Some(lib)`. The second call returns `false`.
  - `file_as_library_is_refused`: `dir` is an existing file → `NotAFolder`, and no record is saved.
  - `library_path_with_space_and_umlaut_round_trips`: `My Library ü` survives save → load → ensure.
  - `corrupt_record_is_reported`: garbage JSON in `bml-library.json` → `Corrupt` naming the path.
  - `no_home_without_record_or_request`: `NoHome`.

- [ ] **Step 2:** `cd rust && cargo test -p bml-db`. Expected: compile failure (the crate does not exist yet).

- [ ] **Step 3: Implement.** Write the record with `bmlib::atomic::atomic_write` (pretty JSON). Add `serde`, `serde_json`, `thiserror` and `bmlib` from the workspace, and `tempfile` as a dev-dependency. `lib.rs` declares `pub mod library;` and `[lints] workspace = true`.

- [ ] **Step 4:** `cargo test -p bml-db` passes, and `cargo clippy -p bml-db --all-targets` is clean.

- [ ] **Step 5: Commit** `feat(bml-db): library folder record (~/BMLibrarian, documents/, database/)`

---

### Task 2: Migrations, `migrate()` and the lexical-index probe

**Files:**
- Create: `rust/bml-db/src/schema.rs` (migrations, constants), `rust/bml-db/tests/common/mod.rs` (copy of `bml-pgserver/tests/common/mod.rs`), `rust/bml-db/tests/schema.rs`
- Modify: `rust/bml-db/src/lib.rs`, `rust/bml-db/Cargo.toml` (dev-deps `bml-pgserver`, `postgres`, `tempfile`)

**Interfaces:**
- Consumes: bmlib `db::{Db, DbError, Migration, run_migrations, execute, fetch_all}`, `publications::schema::ensure_schema`, `embed::EMBEDDING_DIM`.
- Produces (`bml_db`, re-exported from `schema`):
  - `pub fn migrate(db: &mut dyn Db) -> Result<usize, DbError>`. It takes `pg_advisory_lock(MIGRATION_LOCK_KEY)`, calls `ensure_schema`, calls `run_migrations(db, migrations())`, then always calls `pg_advisory_unlock`, even on error. It returns the count of BMLibrarian migrations applied.
  - `pub fn migrations() -> Vec<Migration>`
  - `pub const MIGRATION_LOCK_KEY: i64` (any fixed value, documented as BMLibrarian's).
  - `pub enum LexicalIndex { Bm25, TsVector }` and `pub fn lexical_index(db: &mut dyn Db) -> Result<LexicalIndex, DbError>`. `Bm25` iff an index named `CHUNKS_BM25_INDEX` exists on `chunks` (`pg_indexes`). Piece 4 uses this to choose its query.
  - Table/index name constants: `PUBLICATION_FULLTEXT`, `CHUNKS`, `CHUNK_EMBEDDINGS`, `PUBLICATION_INDEX`, `CHUNKS_BM25_INDEX`, `CHUNKS_TSV_INDEX`, `CHUNK_EMBEDDINGS_HNSW_INDEX`; `HNSW_M = 16`, `HNSW_EF_CONSTRUCTION = 64`.

**Migration 1 `library_tables`** (every statement `IF NOT EXISTS`; FKs to `publications(id) ON DELETE CASCADE`):

| Table | Columns / constraints |
|---|---|
| `publication_fulltext` | `publication_id INTEGER PK`, `form TEXT NOT NULL CHECK (form IN ('jats','pdf','html','abstract'))`, `version_held TEXT`, `cache_key TEXT`, `cache_path TEXT` (relative to `documents/`), `attempts INTEGER NOT NULL DEFAULT 0`, `last_error TEXT`, `last_error_kind TEXT CHECK (… IN ('lasting','passing'))`, `retry_after TIMESTAMPTZ`, `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`. `CHECK (form = 'abstract' OR cache_path IS NOT NULL)`: no full-text form without a stored file. Partial index on `retry_after WHERE form = 'abstract'`. |
| `chunks` | `id BIGSERIAL PK`, `publication_id INTEGER NOT NULL`, `ordinal INTEGER NOT NULL`, `kind TEXT NOT NULL CHECK (kind IN ('abstract','fulltext'))` (title + abstract vs canonical text), `text TEXT NOT NULL`, `span_start INTEGER`, `span_end INTEGER` (code points in the canonical text), `UNIQUE (publication_id, ordinal)`, `CHECK (kind = 'abstract' OR (span_start IS NOT NULL AND span_end >= span_start))` |
| `chunk_embeddings` | `chunk_id BIGINT PK REFERENCES chunks(id) ON DELETE CASCADE`, `embedding halfvec({EMBEDDING_DIM}) NOT NULL`. HNSW index `USING hnsw (embedding halfvec_cosine_ops) WITH (m = {HNSW_M}, ef_construction = {HNSW_EF_CONSTRUCTION})` |
| `publication_index` | `publication_id INTEGER PK`, `status TEXT NOT NULL CHECK (status IN ('pending','complete'))`, the five `ChunkSetLabel` fields (`model_sha256 TEXT`, `recipe_version INTEGER`, `chunker_version INTEGER`, `converter_version TEXT`, `text_sha256 TEXT`), `chunk_count INTEGER`, `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`. `CHECK (status <> 'complete' OR (all five label fields AND chunk_count IS NOT NULL))`: a set is never marked current without its label. |
| lexical | If `SELECT 1 FROM pg_extension WHERE extname = 'pg_search'` returns a row: the BM25 index `CHUNKS_BM25_INDEX`. Otherwise: `ALTER TABLE chunks ADD COLUMN IF NOT EXISTS text_tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', text)) STORED` plus GIN index `CHUNKS_TSV_INDEX`. Doc comment: pg_search installed *after* this migration ran is not picked up (later work). |

- [ ] **Step 1: Write the failing tests.**
  - Unit (`schema.rs`): `migration_versions_are_unique_and_ascending`; `ddl_uses_embedding_dim` (the vector DDL string contains `halfvec(` + `EMBEDDING_DIM`). For this, factor the DDL into `fn vector_ddl() -> String`.
  - Integration (`tests/schema.rs`, every test `#[ignore]`d, real PG18 via `common::test_bindir()`, `serial()`, `bml_pgserver::init::init` into temp dirs, stopped on drop as in `bml-setup/tests/database.rs`; connect with `bml.env` through `bml_pgserver::init::connect`):
    - `migrate_is_idempotent`: first call `> 0`, second call `== 0`. `publications` and all four tables exist, and their `tableowner` is `bml_pgserver::init::APP_ROLE`.
    - `bmlib_store_publication_works_after_migrate`: `bmlib::publications::storage::store_publication` with a minimal publication succeeds.
    - `migrate_restores_a_dropped_bmlib_column`: `ALTER TABLE publications DROP COLUMN pmcid`, then migrate → `0`, and the column is back.
    - `concurrent_migrations_both_succeed`: two threads, two connections, `migrate` on a fresh database; both `Ok`, sum of counts `== migrations().len()`.
    - `hnsw_returns_nearest_chunk`: three chunks with unit vectors on different axes (built from `EMBEDDING_DIM`); `ORDER BY embedding <=> $1::halfvec LIMIT 1` returns the matching chunk, and `EXPLAIN` with `SET enable_seqscan = off` names `CHUNK_EMBEDDINGS_HNSW_INDEX`.
    - `lexical_index_matches_extension`: `lexical_index()` is `Bm25` iff `common::test_extension_dirs()` provides pg_search. With `Bm25`, `text ||| 'myocardial'` finds the chunk "myocardial infarction outcomes"; with `TsVector`, `text_tsv @@ plainto_tsquery('english','myocardial')` finds it.
    - `constraints_refuse_failures_stored_as_results`: `form = 'pdf'` with NULL `cache_path` is refused (`check_violation`), and `status = 'complete'` with NULL `model_sha256` is refused.

- [ ] **Step 2:** `cargo test -p bml-db` fails (no `migrate`). Then `BML_TEST_PG_BINDIR=<PG18 bin> cargo test -p bml-db -- --include-ignored` (bindir: memory `reference-local-pg18-bindir`; add `BML_TEST_PG_EXTENSION_DIRS` for the BM25 branch).

- [ ] **Step 3: Implement** `schema.rs` as specified. Run statements one at a time with bmlib `execute`. Do not use `create_tables` for DDL containing `pdb.simple(...)`: it is safe, but stay consistent.

- [ ] **Step 4:** Both commands pass. Run the integration suite **twice**: once without and once with the pg_search extension dir, so that both lexical branches are exercised. Run clippy as well.

- [ ] **Step 5: Commit** `feat(bml-db): migrate() with bmlib publications + chunks, halfvec HNSW, BM25/tsvector`

---

### Task 3: Setup step `Library`, `--library-dir`, docs

**Files:**
- Modify: `rust/bml-setup/Cargo.toml` (dep `bml-db`), `rust/bml-setup/src/lib.rs` (`StepId::Library`, label `"Library"`), `rust/bml-setup/src/runner.rs`, `rust/bml-setup/src/steps.rs`, `rust/bml-setup/tests/database.rs`, `rust/bml-cli/src/setup.rs`, `rust/bml-cli/tests/setup_cli.rs`
- Docs: `doc/users/bml_setup_guide.md` (library folder section, `--library-dir`, the new step), `doc/developers/rust_setup.md` (step list, ordering rule), new `doc/developers/rust_db_schema.md` (tables, constraints, lexical choice, `migrate()` contract, why `bml_app`), `CLAUDE.md` (`bml setup` line: `--data-dir` → `--library-dir`), the spec's piece list (mark piece 2 done), `HANDOVER.md`

**Interfaces:**
- Consumes: Task 1 `resolve_library`, `ensure_library`, `Library`. Task 2 `migrate`, `MIGRATION_LOCK_KEY` (not needed directly).
- Changes:
  - `ALL_STEPS: [StepId; 7]` = Hardware, Database, **Library**, Autostart, Ollama, Models, EmbeddingModel. `depends_on(Library) = &[Database]`.
  - `SetupPlan` gains `pub library_dir: Option<PathBuf>` (the `--library-dir` value) and `pub home: Option<PathBuf>` (the CLI passes `std::env::home_dir()`; tests pass a temp dir).
  - `DatabasePlan::Bundled` becomes a unit variant. `DEFAULT_DATA_DIR_NAME` is removed (grep for callers).
  - Database step: for a **new** private server (`Private`, or `Bundled` with nothing saved), it calls `resolve_library` + `ensure_library` before `init`. `Bundled` puts its data in `library.database_dir()`. A resumed saved server or an existing server never consults the library here.
  - Library step: `resolve_library` → `ensure_library` → read `bml.env` (`read_conn_info`; missing → `Failed("no database is set up yet; run `bml setup` with the Database step first")`) → `connect` (an error adds "is the database running? Try `bml server start`.") → `migrate`. The outcome is `Installed` if `ensure_library` returned `true` or `migrate > 0`, otherwise `AlreadyPresent`.
  - CLI: `--library-dir DIR` (no `conflicts_with`; it is valid with `--existing-server`, where it holds documents only). `--data-dir` is removed. `SkipStep::Library`. For `--pg-bindir`, `InitRequest.data_dir = resolve_library(config, args.library_dir, home)?.database_dir()`, and a `LibraryError` becomes the CLI error.

- [ ] **Step 1: Write the failing tests.**
  - `runner.rs`: update `runner_continues_after_a_failure` to seven steps (Library is `Skipped` because Database failed). Add `should_run_skips_library_when_database_failed`.
  - `steps.rs`: replace `bundled_plan_refuses_another_data_dir_than_the_saved_one` / `..._for_a_saved_existing_server` with:
    - `bundled_plan_refuses_a_library_other_than_the_saved_one` (a saved `bml-library.json` plus a different `library_dir` → `Failed`/`Err` naming both paths)
    - `library_dir_is_allowed_with_a_saved_existing_server`
    - `library_step_without_database_fails_plainly` (no `bml.env` → `Failed` containing `bml setup`)
    - `library_step_with_stopped_server_fails_plainly` (a `bml.env` pointing at an unused loopback port → `Failed` containing `bml server start`)
  - `tests/database.rs` (`#[ignore]`d, real PG18): a `Bundled`-style new private server from `BML_TEST_PG_BINDIR` via `DatabasePlan::Private` with `data_dir` from `resolve_library` → `run_step(Database)` then `run_step(Library)` is `Installed`, and a second `run_step(Library)` is `AlreadyPresent`. `<library>/documents` exists, and the server's data dir is `<library>/database`. The existing-server test gains a `run_step(Library)` → `Installed`.
  - `setup_cli.rs`: `--data-dir` is now rejected by clap (exit 2). `--skip library` is accepted. `--library-dir` together with `--existing-server` is accepted by the parser.

- [ ] **Step 2:** `cd rust && cargo test` fails as expected.

- [ ] **Step 3: Implement** the changes above. Grep `rust/` and `doc/` for `data-dir`/`DEFAULT_DATA_DIR_NAME`/`pgdata` and fix every `bml setup` mention. Leave `bml server init --data-dir` alone.

- [ ] **Step 4: Verify**
  - `cargo test`, `cargo clippy --all-targets`, `cargo fmt --check`
  - `BML_TEST_PG_BINDIR=… [BML_TEST_PG_EXTENSION_DIRS=…] cargo test -- --include-ignored`
  - Python suite unaffected (docs only): `QT_QPA_PLATFORM=offscreen uv run python -m pytest tests/ -p no:cacheprovider --no-cov -q`, output saved to the scratchpad
  - By hand on the Mac: a fresh `--config-dir`, `cargo run -p bml-cli -- --config-dir <tmp> setup --library-dir "<tmp>/My Library" --skip autostart --skip ollama --skip models --skip embedding-model`. Library reads `installed`, `\dt` shows the tables, and a second run reads `already in place`.

- [ ] **Step 5: Commit** `feat(setup): Library step creates the library folder and migrates the schema; --library-dir replaces --data-dir`, then update HANDOVER.md, push, and open the PR.
