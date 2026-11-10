//! The extensions a fresh private server provides, exercised with real
//! queries: a `halfvec` HNSW nearest-neighbour search, and a pg_search BM25
//! match when pg_search is present. This is the smoke test the pgdist
//! workflow runs against every bundle (`BML_TEST_PG_BINDIR` +
//! `BML_TEST_PG_EXTENSION_DIRS`).

mod common;

use std::path::PathBuf;

use bml_pgserver::control::stop;
use bml_pgserver::envfile::{read_conn_info, ADMIN_ENV_FILE_NAME};
use bml_pgserver::init::{connect, init, InitRequest, DATABASE};
use bml_pgserver::state::load_state;

/// Stops the server of the config dir when the test ends, pass or fail.
struct StopOnDrop(PathBuf);

impl Drop for StopOnDrop {
    fn drop(&mut self) {
        if let Ok(Some(state)) = load_state(&self.0) {
            let _ = stop(&state);
        }
    }
}

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn vector_and_lexical_queries() {
    let Some(bindir) = common::test_bindir() else {
        return;
    };
    let _guard = common::serial();
    let tmp = tempfile::tempdir().unwrap();
    let config_dir = tmp.path().join("config");
    let _stop = StopOnDrop(config_dir.clone());
    let req = InitRequest {
        bindir,
        data_dir: tmp.path().join("data"),
        extension_dirs: common::test_extension_dirs(),
    };
    let outcome = init(&req, &config_dir).unwrap();

    let mut admin = read_conn_info(&config_dir.join(ADMIN_ENV_FILE_NAME))
        .unwrap()
        .unwrap();
    admin.dbname = DATABASE.into();
    let mut client = connect(&admin).unwrap();
    client
        .batch_execute(
            "CREATE TABLE smoke(id int PRIMARY KEY, body text, v halfvec(3));
             CREATE INDEX ON smoke USING hnsw (v halfvec_cosine_ops);
             INSERT INTO smoke VALUES (1, 'aspirin trial', '[1,0,0]'),
                                      (2, 'statin cohort', '[0,1,0]');",
        )
        .unwrap();
    let nearest: i32 = client
        .query_one(
            "SELECT id FROM smoke ORDER BY v <=> '[0.9,0.1,0]' LIMIT 1",
            &[],
        )
        .unwrap()
        .get(0);
    assert_eq!(nearest, 1);

    if outcome.pg_search {
        client
            .batch_execute(
                "CREATE INDEX smoke_bm25 ON smoke USING bm25 (id, body) WITH (key_field='id')",
            )
            .unwrap();
        let hits: Vec<i32> = client
            .query("SELECT id FROM smoke WHERE body @@@ 'statin'", &[])
            .unwrap()
            .iter()
            .map(|row| row.get(0))
            .collect();
        assert_eq!(hits, vec![2]);
    }
}
