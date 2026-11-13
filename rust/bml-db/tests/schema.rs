//! `migrate()` against a real PostgreSQL 18 (`BML_TEST_PG_BINDIR`), each test
//! on its own private server in a temp folder. With pg_search in
//! `BML_TEST_PG_EXTENSION_DIRS` the BM25 branch runs, otherwise tsvector.

mod common;

use std::path::{Path, PathBuf};

use bml_db::{lexical_index, migrate, migrations, LexicalIndex, CHUNK_EMBEDDINGS_HNSW_INDEX};
use bml_pgserver::control::stop;
use bml_pgserver::envfile::{read_conn_info, APP_ENV_FILE_NAME};
use bml_pgserver::init::{connect, init, InitRequest, APP_ROLE};
use bml_pgserver::state::load_state;
use bmlib::embed::EMBEDDING_DIM;
use postgres::Client;

/// Stops the server of the config dir when the test ends, pass or fail.
struct StopOnDrop(PathBuf);
impl Drop for StopOnDrop {
    fn drop(&mut self) {
        if let Ok(Some(state)) = load_state(&self.0) {
            let _ = stop(&state);
        }
    }
}

/// A fresh private server; `None` when no PG18 is configured.
fn server(tmp: &Path) -> Option<StopOnDrop> {
    let bindir = common::test_bindir()?;
    let cfg = tmp.join("cfg");
    let stop = StopOnDrop(cfg.clone());
    init(
        &InitRequest {
            bindir,
            data_dir: tmp.join("data"),
            extension_dirs: common::test_extension_dirs(),
        },
        &cfg,
    )
    .unwrap();
    Some(stop)
}

/// A connection as the app role.
fn app(stop: &StopOnDrop) -> Client {
    let info = read_conn_info(&stop.0.join(APP_ENV_FILE_NAME))
        .unwrap()
        .unwrap();
    connect(&info).unwrap()
}

/// A `halfvec` literal: 1 on `axis`, 0 elsewhere.
fn axis_vector(axis: usize) -> String {
    let v: Vec<&str> = (0..EMBEDDING_DIM)
        .map(|i| if i == axis { "1" } else { "0" })
        .collect();
    format!("[{}]", v.join(","))
}

/// Store a publication and one chunk per text; returns the chunk ids.
fn chunks(c: &mut Client, texts: &[&str]) -> Vec<i64> {
    let pid: i32 = c
        .query_one(
            "INSERT INTO publications (title, first_seen_source, created_at, updated_at) \
             VALUES ('t', 'medrxiv', 'now', 'now') RETURNING id",
            &[],
        )
        .unwrap()
        .get(0);
    texts
        .iter()
        .enumerate()
        .map(|(i, text)| {
            c.query_one(
                "INSERT INTO chunks (publication_id, ordinal, kind, text, span_start, span_end) \
                 VALUES ($1, $2, 'fulltext', $3, 0, 1) RETURNING id",
                &[&pid, &(i as i32), text],
            )
            .unwrap()
            .get(0)
        })
        .collect()
}

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn migrate_is_idempotent() {
    let _g = common::serial();
    let tmp = tempfile::tempdir().unwrap();
    let Some(s) = server(tmp.path()) else { return };
    let mut c = app(&s);
    assert!(migrate(&mut c).unwrap() > 0);
    assert_eq!(migrate(&mut c).unwrap(), 0);
    for table in [
        "publications",
        "publication_fulltext",
        "chunks",
        "chunk_embeddings",
        "publication_index",
    ] {
        let owner: String = c
            .query_one(
                "SELECT tableowner::text FROM pg_tables WHERE schemaname = 'public' AND tablename = $1",
                &[&table],
            )
            .unwrap()
            .get(0);
        assert_eq!(owner, APP_ROLE, "{table}");
    }
}

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn bmlib_store_publication_works_after_migrate() {
    let _g = common::serial();
    let tmp = tempfile::tempdir().unwrap();
    let Some(s) = server(tmp.path()) else { return };
    let mut c = app(&s);
    migrate(&mut c).unwrap();
    let mut p = bmlib::publications::models::Publication::new("A preprint", "medrxiv");
    p.doi = Some("10.1101/2026.01.01.26000001".into());
    let outcome =
        bmlib::publications::storage::store_publication(&mut c, &mut p, &[], &[], &[]).unwrap();
    assert_eq!(outcome, bmlib::publications::storage::StoreOutcome::Added);
    let n: i64 = c
        .query_one(
            "SELECT count(*) FROM publications WHERE title = 'A preprint'",
            &[],
        )
        .unwrap()
        .get(0);
    assert_eq!(n, 1);
}

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn migrate_restores_a_dropped_bmlib_column() {
    let _g = common::serial();
    let tmp = tempfile::tempdir().unwrap();
    let Some(s) = server(tmp.path()) else { return };
    let mut c = app(&s);
    migrate(&mut c).unwrap();
    c.batch_execute("ALTER TABLE publications DROP COLUMN pmcid")
        .unwrap();
    assert_eq!(migrate(&mut c).unwrap(), 0);
    let n: i64 = c
        .query_one(
            "SELECT count(*) FROM information_schema.columns \
             WHERE table_name = 'publications' AND column_name = 'pmcid'",
            &[],
        )
        .unwrap()
        .get(0);
    assert_eq!(n, 1);
}

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn concurrent_migrations_both_succeed() {
    let _g = common::serial();
    let tmp = tempfile::tempdir().unwrap();
    let Some(s) = server(tmp.path()) else { return };
    let (mut a, mut b) = (app(&s), app(&s));
    let ta = std::thread::spawn(move || migrate(&mut a).map_err(|e| e.to_string()));
    let tb = std::thread::spawn(move || migrate(&mut b).map_err(|e| e.to_string()));
    let (ra, rb) = (ta.join().unwrap(), tb.join().unwrap());
    assert_eq!(
        ra.clone().unwrap() + rb.clone().unwrap(),
        migrations().len(),
        "{ra:?} {rb:?}"
    );
}

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn hnsw_returns_nearest_chunk() {
    let _g = common::serial();
    let tmp = tempfile::tempdir().unwrap();
    let Some(s) = server(tmp.path()) else { return };
    let mut c = app(&s);
    migrate(&mut c).unwrap();
    let ids = chunks(&mut c, &["a", "b", "c"]);
    for (axis, id) in ids.iter().enumerate() {
        c.execute(
            "INSERT INTO chunk_embeddings (chunk_id, embedding) VALUES ($1, $2::text::halfvec)",
            &[id, &axis_vector(axis)],
        )
        .unwrap();
    }
    let query = "SELECT chunk_id FROM chunk_embeddings \
                 ORDER BY embedding <=> $1::text::halfvec LIMIT 1";
    let nearest: i64 = c.query_one(query, &[&axis_vector(1)]).unwrap().get(0);
    assert_eq!(nearest, ids[1]);
    c.batch_execute("SET enable_seqscan = off").unwrap();
    let plan: Vec<String> = c
        .query(&format!("EXPLAIN {query}"), &[&axis_vector(1)])
        .unwrap()
        .iter()
        .map(|r| r.get(0))
        .collect();
    assert!(
        plan.iter().any(|l| l.contains(CHUNK_EMBEDDINGS_HNSW_INDEX)),
        "{plan:#?}"
    );
}

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn lexical_index_matches_extension() {
    let _g = common::serial();
    let tmp = tempfile::tempdir().unwrap();
    let Some(s) = server(tmp.path()) else { return };
    let mut c = app(&s);
    migrate(&mut c).unwrap();
    let ids = chunks(
        &mut c,
        &["myocardial infarction outcomes", "unrelated text"],
    );
    let kind = lexical_index(&mut c).unwrap();
    let sql = if common::test_provides_pg_search() {
        assert_eq!(kind, LexicalIndex::Bm25);
        "SELECT id FROM chunks WHERE text ||| 'myocardial' ORDER BY pdb.score(id) DESC"
    } else {
        assert_eq!(kind, LexicalIndex::TsVector);
        "SELECT id FROM chunks WHERE text_tsv @@ plainto_tsquery('english', 'myocardial')"
    };
    let found: Vec<i64> = c
        .query(sql, &[])
        .unwrap()
        .iter()
        .map(|r| r.get(0))
        .collect();
    assert_eq!(found, vec![ids[0]]);
}

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn constraints_refuse_failures_stored_as_results() {
    let _g = common::serial();
    let tmp = tempfile::tempdir().unwrap();
    let Some(s) = server(tmp.path()) else { return };
    let mut c = app(&s);
    migrate(&mut c).unwrap();
    let pid: i32 = c
        .query_one(
            "INSERT INTO publications (title, first_seen_source, created_at, updated_at) \
             VALUES ('t', 'medrxiv', 'now', 'now') RETURNING id",
            &[],
        )
        .unwrap()
        .get(0);
    let refused = |c: &mut Client, sql: &str| {
        let err = c.execute(sql, &[&pid]).unwrap_err();
        assert_eq!(
            err.code(),
            Some(&postgres::error::SqlState::CHECK_VIOLATION),
            "{sql}: {err}"
        );
    };
    refused(
        &mut c,
        "INSERT INTO publication_fulltext (publication_id, form) VALUES ($1, 'pdf')",
    );
    refused(
        &mut c,
        "INSERT INTO publication_index (publication_id, status) VALUES ($1, 'complete')",
    );
    // The same rows in the shapes that are allowed.
    c.execute(
        "INSERT INTO publication_fulltext (publication_id, form) VALUES ($1, 'abstract')",
        &[&pid],
    )
    .unwrap();
    c.execute(
        "INSERT INTO publication_index (publication_id, status) VALUES ($1, 'pending')",
        &[&pid],
    )
    .unwrap();
}
