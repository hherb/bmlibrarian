//! `bml_search::search` against a real PostgreSQL 18 (`BML_TEST_PG_BINDIR`).

mod common;

use std::path::{Path, PathBuf};

use bml_db::migrate;
use bml_library::index::ChunkEmbedder;
use bml_pgserver::control::stop;
use bml_pgserver::envfile::{read_conn_info, APP_ENV_FILE_NAME};
use bml_pgserver::init::{connect, init, InitRequest};
use bml_pgserver::state::load_state;
use bml_search::search;
use bmlib::embed::EMBEDDING_DIM;
use postgres::Client;

struct StopOnDrop(PathBuf);
impl Drop for StopOnDrop {
    fn drop(&mut self) {
        if let Ok(Some(state)) = load_state(&self.0) {
            let _ = stop(&state);
        }
    }
}

/// A migrated database; `pg_search` only when asked for and available.
fn server(tmp: &Path, pg_search: bool) -> Option<(StopOnDrop, Client)> {
    let bindir = common::test_bindir()?;
    let cfg = tmp.join("cfg");
    let guard = StopOnDrop(cfg.clone());
    let extension_dirs = if pg_search {
        common::test_extension_dirs()
    } else {
        // Leave out the folders that bring pg_search. Where pgvector shares
        // one with it (a pgdist bundle's `ext`), a server without pg_search
        // cannot be had here; bml-db's tests cover tsvector on such a run.
        let (search, rest): (Vec<PathBuf>, Vec<PathBuf>) = common::test_extension_dirs()
            .into_iter()
            .partition(|d| bml_pgserver::conf::provides_pg_search(d));
        if search.iter().any(|d| {
            bml_pgserver::conf::extension_control_dir(d)
                .join("vector.control")
                .is_file()
        }) {
            eprintln!("skipped: pgvector and pg_search share an extension folder here");
            return None;
        }
        rest
    };
    init(
        &InitRequest {
            bindir,
            data_dir: tmp.join("data"),
            extension_dirs,
        },
        &cfg,
    )
    .unwrap();
    let info = read_conn_info(&cfg.join(APP_ENV_FILE_NAME))
        .unwrap()
        .unwrap();
    let mut client = connect(&info).unwrap();
    migrate(&mut client).unwrap();
    Some((guard, client))
}

/// Puts a text on one axis by topic: exercise-like words, sleep-like words,
/// or anything else.
struct TopicEmbedder;

fn topic_vector(text: &str) -> Vec<f32> {
    let text = text.to_lowercase();
    let axis = if ["exercise", "running", "physical activity"]
        .iter()
        .any(|w| text.contains(w))
    {
        0
    } else if ["sleep", "insomnia"].iter().any(|w| text.contains(w)) {
        1
    } else {
        2
    };
    let mut v = vec![0.0; EMBEDDING_DIM];
    v[axis] = 1.0;
    v
}

impl ChunkEmbedder for TopicEmbedder {
    fn model_sha256(&self) -> &str {
        "topic-stub"
    }
    fn embed(&mut self, texts: &[&str]) -> Result<Vec<Vec<f32>>, String> {
        Ok(texts.iter().map(|t| topic_vector(t)).collect())
    }
}

/// Fails the test if asked to embed anything.
struct NeverEmbedder;

impl ChunkEmbedder for NeverEmbedder {
    fn model_sha256(&self) -> &str {
        "never"
    }
    fn embed(&mut self, _texts: &[&str]) -> Result<Vec<Vec<f32>>, String> {
        panic!("the embedder must not be called for a blank query");
    }
}

/// A paper with one abstract chunk embedded by [`topic_vector`].
fn paper_with_chunk(db: &mut Client, title: &str, text: &str) -> i32 {
    let id: i32 = db
        .query_one(
            "INSERT INTO publications (title, abstract, authors, journal, publication_date, \
             first_seen_source, created_at, updated_at) VALUES ($1, $2, \
             '[\"Smith J\", \"Jones A\"]', 'Journal of Affective Disorders', '2024-03-05', \
             'europepmc', 'now', 'now') RETURNING id",
            &[&title, &text],
        )
        .unwrap()
        .get(0);
    let chunk: i64 = db
        .query_one(
            "INSERT INTO chunks (publication_id, ordinal, kind, text) VALUES ($1, 0, 'abstract', $2) \
             RETURNING id",
            &[&id, &text],
        )
        .unwrap()
        .get(0);
    let literal = format!(
        "[{}]",
        topic_vector(text)
            .iter()
            .map(f32::to_string)
            .collect::<Vec<_>>()
            .join(",")
    );
    db.execute(
        &format!(
            "INSERT INTO chunk_embeddings (chunk_id, embedding) VALUES ($1, '{literal}'::halfvec)"
        ),
        &[&chunk],
    )
    .unwrap();
    id
}

fn library(db: &mut Client) -> (i32, i32) {
    let exercise = paper_with_chunk(
        db,
        "Exercise for major depression",
        "Supervised aerobic exercise reduced depressive symptoms in adults.",
    );
    let sleep = paper_with_chunk(
        db,
        "CBT for insomnia",
        "Cognitive behavioural therapy improved insomnia and mood.",
    );
    (exercise, sleep)
}

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn blank_query_returns_no_hits() {
    let _g = common::serial();
    let tmp = tempfile::tempdir().unwrap();
    let Some((_s, mut db)) = server(tmp.path(), true) else {
        return;
    };
    library(&mut db);
    for query in ["", "   ", "\t\n"] {
        assert!(search(&mut db, &mut NeverEmbedder, query, 10)
            .unwrap()
            .is_empty());
    }
}

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn empty_library_returns_no_hits() {
    let _g = common::serial();
    let tmp = tempfile::tempdir().unwrap();
    let Some((_s, mut db)) = server(tmp.path(), true) else {
        return;
    };
    assert!(search(&mut db, &mut TopicEmbedder, "exercise", 10)
        .unwrap()
        .is_empty());
}

fn finds_by_meaning(pg_search: bool) {
    let _g = common::serial();
    let tmp = tempfile::tempdir().unwrap();
    let Some((_s, mut db)) = server(tmp.path(), pg_search) else {
        return;
    };
    let (exercise, sleep) = library(&mut db);
    // No word of the query is in the exercise paper; its meaning is.
    let hits = search(&mut db, &mut TopicEmbedder, "does running help", 10).unwrap();
    assert_eq!(hits[0].publication_id, i64::from(exercise), "{hits:#?}");
    assert_eq!(hits[0].title, "Exercise for major depression");
    assert_eq!(
        hits[0].journal.as_deref(),
        Some("Journal of Affective Disorders")
    );
    assert_eq!(hits[0].year, Some(2024));
    assert_eq!(hits[0].authors, ["Smith J", "Jones A"]);
    assert!(hits[0].passage.contains("aerobic exercise"));
    // One hit per paper.
    let ids: Vec<i64> = hits.iter().map(|h| h.publication_id).collect();
    let unique: std::collections::BTreeSet<i64> = ids.iter().copied().collect();
    assert_eq!(unique.len(), ids.len());
    // A word query still finds its paper.
    let words = search(
        &mut db,
        &mut TopicEmbedder,
        "cognitive behavioural therapy",
        1,
    )
    .unwrap();
    assert_eq!(words.len(), 1);
    assert_eq!(words[0].publication_id, i64::from(sleep), "{words:#?}");
}

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn finds_the_paper_by_meaning() {
    finds_by_meaning(true);
}

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn works_with_tsvector_fallback() {
    finds_by_meaning(false);
}

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn the_fallback_server_has_the_tsvector_index() {
    let _g = common::serial();
    let tmp = tempfile::tempdir().unwrap();
    let Some((_s, mut db)) = server(tmp.path(), false) else {
        return;
    };
    assert_eq!(
        bml_db::lexical_index(&mut db).unwrap(),
        Some(bml_db::LexicalIndex::TsVector)
    );
}

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn boilerplate_passages_are_not_shown() {
    let _g = common::serial();
    let tmp = tempfile::tempdir().unwrap();
    let Some((_s, mut db)) = server(tmp.path(), true) else {
        return;
    };
    let (exercise, _) = library(&mut db);
    let references = paper_with_chunk(
        &mut db,
        "A review that only cites exercise trials",
        "Mol Psychiatr. (2022) 27:1286–99. doi: 10.1038/s41380-021-01381-x  5. Mcintyre RS, \
         Alsuwaidan M, et al. Exercise and running for depression: definition, management",
    );
    let hits = search(
        &mut db,
        &mut TopicEmbedder,
        "exercise running depression",
        10,
    )
    .unwrap();
    assert!(
        hits.iter()
            .all(|h| h.publication_id != i64::from(references)),
        "{hits:#?}"
    );
    assert_eq!(hits[0].publication_id, i64::from(exercise));
}
