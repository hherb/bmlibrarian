//! The pipeline against a real PostgreSQL 18 (`BML_TEST_PG_BINDIR`), each
//! test on its own private server in a temp folder, with fake HTTP clients
//! and a stub embedder.

mod common;

use std::path::{Path, PathBuf};
use std::sync::atomic::AtomicBool;
use std::sync::{Arc, Mutex};
use std::time::Duration;

use bml_db::migrate;
use bml_library::index::ChunkEmbedder;
use bml_library::testing::FakeHttp;
use bml_library::{fulltext::FulltextEnd, Phase, PhaseSet, Pipeline, UpdateOptions, UpdateReport};
use bml_pgserver::control::stop;
use bml_pgserver::envfile::{read_conn_info, APP_ENV_FILE_NAME};
use bml_pgserver::init::{connect, init, InitRequest};
use bml_pgserver::state::load_state;
use bmlib::embed::EMBEDDING_DIM;
use bmlib::fulltext::cache::FullTextCache;
use bmlib::publications::fetchers::{FetchError, HttpClient, HttpResponse};
use chrono::{DateTime, NaiveDate, Utc};
use postgres::Client;

const DOI: &str = "10.1101/2024.01.15.24000001";
const JATS: &str = include_str!("fixtures/article.xml");
const PDF: &[u8] = include_bytes!("fixtures/article.pdf");

/// Stops the server of the config dir when the test ends, pass or fail.
struct StopOnDrop(PathBuf);
impl Drop for StopOnDrop {
    fn drop(&mut self) {
        if let Ok(Some(state)) = load_state(&self.0) {
            let _ = stop(&state);
        }
    }
}

/// A fresh, migrated private server and an app connection; `None` when no
/// PG18 is configured.
fn server(tmp: &Path) -> Option<(StopOnDrop, Client)> {
    let bindir = common::test_bindir()?;
    let cfg = tmp.join("cfg");
    let guard = StopOnDrop(cfg.clone());
    init(
        &InitRequest {
            bindir,
            data_dir: tmp.join("data"),
            extension_dirs: common::test_extension_dirs(),
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

/// One vector per text; fails on call number `fail_on` (1-based) if set,
/// and on any text containing `fail_on_text`.
struct StubEmbedder {
    sha: String,
    calls: usize,
    fail_on: Option<usize>,
    fail_on_text: Option<&'static str>,
}

fn stub(sha: &str, fail_on_text: Option<&'static str>) -> StubEmbedder {
    StubEmbedder {
        sha: sha.into(),
        calls: 0,
        fail_on: None,
        fail_on_text,
    }
}

impl ChunkEmbedder for StubEmbedder {
    fn model_sha256(&self) -> &str {
        &self.sha
    }
    fn embed(&mut self, texts: &[&str]) -> Result<Vec<Vec<f32>>, String> {
        self.calls += 1;
        let poisoned = self
            .fail_on_text
            .is_some_and(|bad| texts.iter().any(|t| t.contains(bad)));
        if self.fail_on == Some(self.calls) || poisoned {
            return Err("the stub model failed".into());
        }
        Ok(texts
            .iter()
            .enumerate()
            .map(|(i, _)| {
                let mut v = vec![0.0; EMBEDDING_DIM];
                v[i % EMBEDDING_DIM] = 1.0;
                v
            })
            .collect())
    }
}

fn instant(at: &str) -> DateTime<Utc> {
    DateTime::parse_from_rfc3339(at)
        .unwrap()
        .with_timezone(&Utc)
}

/// A pipeline over fake clients, no request spacing, and a stub model.
fn pipeline(tmp: &Path, api: &FakeHttp, web: &FakeHttp, sha: &str) -> Pipeline {
    let sha = sha.to_string();
    Pipeline {
        cache: FullTextCache {
            cache_dir: tmp.join("documents"),
        },
        api: Arc::new(api.clone()),
        api_delay: Duration::ZERO,
        web: Arc::new(web.clone()),
        web_delay: Duration::ZERO,
        europepmc: Arc::new(FakeHttp::new()),
        europepmc_delay: Duration::ZERO,
        embedder: Box::new(move || Ok(Box::new(stub(&sha, None)))),
        clock: Box::new(|| instant("2024-01-17T13:00:00Z")),
    }
}

fn run(p: &Pipeline, db: &mut Client, phases: PhaseSet, from: &str) -> UpdateReport {
    run_from(p, db, phases, Some(from))
}

fn run_from(p: &Pipeline, db: &mut Client, phases: PhaseSet, from: Option<&str>) -> UpdateReport {
    let stop = AtomicBool::new(false);
    let options = UpdateOptions {
        from: from.map(|f| NaiveDate::parse_from_str(f, "%Y-%m-%d").unwrap()),
        phases,
        stop: &stop,
    };
    p.update(db, &options, &mut |_| {})
}

fn only(phase: Phase) -> PhaseSet {
    let none = PhaseSet {
        metadata: false,
        fulltext: false,
        index: false,
    };
    match phase {
        Phase::Metadata => PhaseSet {
            metadata: true,
            ..none
        },
        Phase::Fulltext => PhaseSet {
            fulltext: true,
            ..none
        },
        Phase::Index => PhaseSet {
            index: true,
            ..none
        },
    }
}

fn details_url(day: &str) -> String {
    format!("https://api.biorxiv.org/details/medrxiv/{day}/{day}/0")
}

fn jats_url(version: i64) -> String {
    format!("https://www.medrxiv.org/content/early/2024/01/17/{DOI}v{version}.source.xml")
}

fn pdf_url(version: i64) -> String {
    format!("https://www.medrxiv.org/content/{DOI}v{version}.full.pdf")
}

/// A `/details/` page holding `records`.
fn details_page(records: &[serde_json::Value]) -> String {
    serde_json::json!({
        "messages": [{"status": "ok", "total": records.len()}],
        "collection": records,
    })
    .to_string()
}

fn record(day: &str, version: i64) -> serde_json::Value {
    serde_json::json!({
        "doi": DOI,
        "title": "Exercise and the heart",
        "authors": "Smith, J.; Jones, A.",
        "date": day,
        "version": version.to_string(),
        "type": "new results",
        "category": "cardiovascular medicine",
        "jatsxml": jats_url(version),
        "abstract": "We studied exercise.",
        "published": "NA",
        "server": "medrxiv",
    })
}

fn scalar_i64(db: &mut Client, sql: &str) -> i64 {
    db.query_one(sql, &[]).unwrap().get(0)
}

/// Insert a publication with medRxiv sources for each version given.
fn paper(db: &mut Client, versions: &[i64]) -> i32 {
    let id: i32 = db
        .query_one(
            "INSERT INTO publications (title, doi, abstract, publication_date, first_seen_source, \
             created_at, updated_at) VALUES ('Exercise and the heart', $1, 'We studied exercise.', \
             '2024-01-15', 'medrxiv', 'now', 'now') RETURNING id",
            &[&DOI],
        )
        .unwrap()
        .get(0);
    for v in versions {
        add_version(db, id, *v);
    }
    id
}

fn add_version(db: &mut Client, id: i32, version: i64) {
    for (url, format) in [(jats_url(version), "xml"), (pdf_url(version), "pdf")] {
        db.execute(
            "INSERT INTO fulltext_sources (publication_id, source, url, format, version, created_at) \
             VALUES ($1, 'medrxiv', $2, $3, $4, 'now')",
            &[&id, &url, &format, &version.to_string()],
        )
        .unwrap();
    }
}

/// (form, version_held, attempts, last_error_kind) of the paper's row.
fn fulltext_row(db: &mut Client, id: i32) -> Option<(String, Option<String>, i32, Option<String>)> {
    db.query_opt(
        "SELECT form, version_held, attempts, last_error_kind FROM publication_fulltext \
         WHERE publication_id = $1",
        &[&id],
    )
    .unwrap()
    .map(|r| (r.get(0), r.get(1), r.get(2), r.get(3)))
}

/// The paper's `version_tried`.
fn version_tried(db: &mut Client, id: i32) -> Option<i32> {
    db.query_one(
        "SELECT version_tried FROM publication_fulltext WHERE publication_id = $1",
        &[&id],
    )
    .unwrap()
    .get(0)
}

// ---- metadata ------------------------------------------------------------

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn resume_after_day_commit() {
    let _g = common::serial();
    let tmp = tempfile::tempdir().unwrap();
    let Some((_s, mut db)) = server(tmp.path()) else {
        return;
    };
    let api = FakeHttp::new()
        .route(
            &details_url("2024-01-15"),
            200,
            details_page(&[record("2024-01-15", 1)]),
        )
        .route(&details_url("2024-01-17"), 200, details_page(&[]));
    // 2024-01-16 is not routed: its fetch fails, the other days complete.
    let p = pipeline(tmp.path(), &api, &FakeHttp::new(), "sha");
    let first = run(&p, &mut db, only(Phase::Metadata), "2024-01-15");
    let m = first.metadata.unwrap();
    assert_eq!(m.added, 1);
    assert_eq!(m.errors.len(), 1, "{:?}", m.errors);
    assert!(first.failures.is_empty());

    api.set(&details_url("2024-01-16"), 200, details_page(&[]));
    api.seen().lock().unwrap().clear();
    let second = run(&p, &mut db, only(Phase::Metadata), "2024-01-15");
    assert!(second.metadata.unwrap().errors.is_empty());
    let seen = api.seen().lock().unwrap().clone();
    assert!(seen.contains(&details_url("2024-01-16")), "{seen:?}");
    assert_eq!(scalar_i64(&mut db, "SELECT count(*) FROM publications"), 1);
}

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn a_v2_record_adds_its_version_to_the_same_paper() {
    let _g = common::serial();
    let tmp = tempfile::tempdir().unwrap();
    let Some((_s, mut db)) = server(tmp.path()) else {
        return;
    };
    let api = FakeHttp::new()
        .route(
            &details_url("2024-01-15"),
            200,
            details_page(&[record("2024-01-15", 1)]),
        )
        .route(
            &details_url("2024-01-16"),
            200,
            details_page(&[record("2024-01-16", 2)]),
        )
        .route(&details_url("2024-01-17"), 200, details_page(&[]));
    let p = pipeline(tmp.path(), &api, &FakeHttp::new(), "sha");
    run(&p, &mut db, only(Phase::Metadata), "2024-01-15");
    assert_eq!(scalar_i64(&mut db, "SELECT count(*) FROM publications"), 1);
    let versions: Vec<String> = db
        .query(
            "SELECT DISTINCT version FROM fulltext_sources WHERE source = 'medrxiv' ORDER BY 1",
            &[],
        )
        .unwrap()
        .iter()
        .map(|r| r.get(0))
        .collect();
    assert_eq!(versions, ["1", "2"]);
    let due = bml_library::fulltext::next_paper(&mut db, bml_library::FulltextSource::Medrxiv)
        .unwrap()
        .unwrap();
    assert_eq!(due.version, 2);
}

// ---- full text -----------------------------------------------------------

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn jats_is_stored_and_the_pdf_never_asked() {
    let _g = common::serial();
    let tmp = tempfile::tempdir().unwrap();
    let Some((_s, mut db)) = server(tmp.path()) else {
        return;
    };
    let id = paper(&mut db, &[1]);
    let web = FakeHttp::new().route(&jats_url(1), 200, JATS);
    let p = pipeline(tmp.path(), &FakeHttp::new(), &web, "sha");
    let r = run(&p, &mut db, only(Phase::Fulltext), "2024-01-15")
        .fulltext
        .unwrap();
    assert_eq!((r.tried, r.jats, r.end), (1, 1, FulltextEnd::Done));
    assert_eq!(fulltext_row(&mut db, id).unwrap().0, "jats");
    assert_eq!(web.seen().lock().unwrap().as_slice(), [jats_url(1)]);
    let path: String = db
        .query_one("SELECT cache_path FROM publication_fulltext", &[])
        .unwrap()
        .get(0);
    assert!(Path::new(&path).is_relative(), "{path}");
    assert!(p.cache.cache_dir.join(&path).is_file(), "{path}");
}

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn jats_404_then_pdf_200_stores_the_pdf() {
    let _g = common::serial();
    let tmp = tempfile::tempdir().unwrap();
    let Some((_s, mut db)) = server(tmp.path()) else {
        return;
    };
    let id = paper(&mut db, &[1]);
    let web = FakeHttp::new()
        .route(&jats_url(1), 404, "")
        .route(&pdf_url(1), 200, PDF);
    let p = pipeline(tmp.path(), &FakeHttp::new(), &web, "sha");
    let r = run(&p, &mut db, only(Phase::Fulltext), "2024-01-15")
        .fulltext
        .unwrap();
    assert_eq!(r.pdf, 1, "{r:?}");
    assert_eq!(fulltext_row(&mut db, id).unwrap().0, "pdf");
}

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn a_refused_pdf_leaves_the_abstract_with_a_lasting_reason() {
    let _g = common::serial();
    let tmp = tempfile::tempdir().unwrap();
    let Some((_s, mut db)) = server(tmp.path()) else {
        return;
    };
    let id = paper(&mut db, &[1]);
    let web = FakeHttp::new().route(&jats_url(1), 404, "").route(
        &pdf_url(1),
        403,
        "Sorry, you have been blocked",
    );
    let p = pipeline(tmp.path(), &FakeHttp::new(), &web, "sha");
    let r = run(&p, &mut db, only(Phase::Fulltext), "2024-01-15")
        .fulltext
        .unwrap();
    assert_eq!(r.lasting, 1);
    let (form, held, attempts, kind) = fulltext_row(&mut db, id).unwrap();
    assert_eq!(
        (form.as_str(), held, attempts, kind.as_deref()),
        ("abstract", None, 1, Some("lasting"))
    );
    let later: bool = db
        .query_one(
            "SELECT retry_after > now() + interval '29 days' FROM publication_fulltext",
            &[],
        )
        .unwrap()
        .get(0);
    assert!(later, "a lasting failure waits LASTING_RETRY");
    // Not due again in this run's view.
    assert!(
        bml_library::fulltext::next_paper(&mut db, bml_library::FulltextSource::Medrxiv)
            .unwrap()
            .is_none()
    );
}

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn a_timeout_is_passing_and_retried_once_its_time_passes() {
    let _g = common::serial();
    let tmp = tempfile::tempdir().unwrap();
    let Some((_s, mut db)) = server(tmp.path()) else {
        return;
    };
    let id = paper(&mut db, &[1]);
    // Nothing routed: both requests get no answer.
    let p = pipeline(tmp.path(), &FakeHttp::new(), &FakeHttp::new(), "sha");
    let r = run(&p, &mut db, only(Phase::Fulltext), "2024-01-15")
        .fulltext
        .unwrap();
    assert_eq!(r.passing, 1);
    assert_eq!(
        fulltext_row(&mut db, id).unwrap().3.as_deref(),
        Some("passing")
    );
    db.execute(
        "UPDATE publication_fulltext SET retry_after = now() - interval '1 second'",
        &[],
    )
    .unwrap();
    assert!(
        bml_library::fulltext::next_paper(&mut db, bml_library::FulltextSource::Medrxiv)
            .unwrap()
            .is_some()
    );
}

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn rate_limit_ends_phase_without_charging_paper() {
    let _g = common::serial();
    let tmp = tempfile::tempdir().unwrap();
    let Some((_s, mut db)) = server(tmp.path()) else {
        return;
    };
    let id = paper(&mut db, &[1]);
    let web = FakeHttp::new()
        .route(&jats_url(1), 429, "")
        .route(&pdf_url(1), 200, PDF);
    let p = pipeline(tmp.path(), &FakeHttp::new(), &web, "sha");
    let report = run(&p, &mut db, only(Phase::Fulltext), "2024-01-15");
    assert!(report.stopped_early());
    let r = report.fulltext.unwrap();
    assert!(matches!(r.end, FulltextEnd::RateLimited { .. }), "{r:?}");
    assert_eq!(r.tried, 0);
    assert_eq!(
        web.seen().lock().unwrap().as_slice(),
        [jats_url(1)],
        "no PDF after the 429"
    );
    assert!(
        fulltext_row(&mut db, id).is_none(),
        "the paper is not charged"
    );
    // The next run skips the phase without a request.
    web.seen().lock().unwrap().clear();
    let again = run(&p, &mut db, only(Phase::Fulltext), "2024-01-15")
        .fulltext
        .unwrap();
    assert!(matches!(again.end, FulltextEnd::RateLimited { .. }));
    assert!(web.seen().lock().unwrap().is_empty());
    // Once the pause is over, the paper is fetched.
    db.execute(
        "UPDATE library_state SET rate_limited_until = now() - interval '1 second'",
        &[],
    )
    .unwrap();
    web.set(&jats_url(1), 200, JATS);
    let after = run(&p, &mut db, only(Phase::Fulltext), "2024-01-15")
        .fulltext
        .unwrap();
    assert_eq!(
        (after.jats, &after.end),
        (1, &FulltextEnd::Done),
        "{after:?}"
    );
}

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn new_version_replaces_old() {
    let _g = common::serial();
    let tmp = tempfile::tempdir().unwrap();
    let Some((_s, mut db)) = server(tmp.path()) else {
        return;
    };
    let id = paper(&mut db, &[1]);
    let web = FakeHttp::new().route(&jats_url(1), 200, JATS);
    let p = pipeline(tmp.path(), &FakeHttp::new(), &web, "sha");
    run(
        &p,
        &mut db,
        PhaseSet::all().without(Phase::Metadata),
        "2024-01-15",
    );
    let v1_path: String = db
        .query_one("SELECT cache_path FROM publication_fulltext", &[])
        .unwrap()
        .get(0);
    let v1_chunks = scalar_i64(&mut db, "SELECT count(*) FROM chunks");
    assert!(v1_chunks > 1, "abstract + full-text chunks");

    add_version(&mut db, id, 2);
    web.set(
        &jats_url(2),
        200,
        JATS.replace(
            "Cancer is a complex disease",
            "Tumours are a complex disease",
        ),
    );
    let report = run(&p, &mut db, only(Phase::Fulltext), "2024-01-15");
    assert_eq!(report.fulltext.unwrap().replaced, 1);
    assert_eq!(
        scalar_i64(&mut db, "SELECT count(*) FROM chunks"),
        v1_chunks,
        "v1's chunks stay searchable until v2 is indexed"
    );
    run(&p, &mut db, only(Phase::Index), "2024-01-15");
    let (form, held, _, _) = fulltext_row(&mut db, id).unwrap();
    assert_eq!((form.as_str(), held.as_deref()), ("jats", Some("2")));
    let v2_path: String = db
        .query_one("SELECT cache_path FROM publication_fulltext", &[])
        .unwrap()
        .get(0);
    assert!(p.cache.cache_dir.join(&v2_path).is_file());
    assert!(
        !p.cache.cache_dir.join(&v1_path).exists(),
        "v1's file is gone"
    );
    let v2_text = scalar_i64(
        &mut db,
        "SELECT count(*) FROM chunks WHERE text LIKE '%Tumours are a complex disease%'",
    );
    assert!(v2_text > 0, "the chunks come from v2");
    assert_eq!(
        scalar_i64(
            &mut db,
            "SELECT count(*) FROM chunks WHERE text LIKE '%Cancer is a complex disease%'"
        ),
        0,
        "v1's chunks are gone"
    );
}

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn failed_new_version_keeps_old() {
    let _g = common::serial();
    let tmp = tempfile::tempdir().unwrap();
    let Some((_s, mut db)) = server(tmp.path()) else {
        return;
    };
    let id = paper(&mut db, &[1]);
    let web = FakeHttp::new().route(&jats_url(1), 200, JATS);
    let p = pipeline(tmp.path(), &FakeHttp::new(), &web, "sha");
    run(
        &p,
        &mut db,
        PhaseSet::all().without(Phase::Metadata),
        "2024-01-15",
    );
    let chunks = scalar_i64(&mut db, "SELECT count(*) FROM chunks");

    add_version(&mut db, id, 2);
    web.set(&jats_url(2), 404, "");
    web.set(&pdf_url(2), 403, "");
    run(
        &p,
        &mut db,
        PhaseSet::all().without(Phase::Metadata),
        "2024-01-15",
    );
    let (form, held, attempts, kind) = fulltext_row(&mut db, id).unwrap();
    assert_eq!(
        (form.as_str(), held.as_deref(), attempts, kind.as_deref()),
        ("jats", Some("1"), 1, Some("lasting"))
    );
    let path: String = db
        .query_one("SELECT cache_path FROM publication_fulltext", &[])
        .unwrap()
        .get(0);
    assert!(p.cache.cache_dir.join(&path).is_file(), "v1's file stays");
    assert_eq!(
        scalar_i64(&mut db, "SELECT count(*) FROM chunks"),
        chunks,
        "v1's chunks stay"
    );
    assert!(
        bml_library::fulltext::next_paper(&mut db, bml_library::FulltextSource::Medrxiv)
            .unwrap()
            .is_none(),
        "waits for retry_after"
    );
    add_version(&mut db, id, 3);
    let due = bml_library::fulltext::next_paper(&mut db, bml_library::FulltextSource::Medrxiv)
        .unwrap()
        .expect("a newer version than the one that failed is due at once");
    assert_eq!((due.version, due.attempts), (3, 0));
}

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn a_new_version_of_an_abstract_only_paper_is_due_at_once() {
    let _g = common::serial();
    let tmp = tempfile::tempdir().unwrap();
    let Some((_s, mut db)) = server(tmp.path()) else {
        return;
    };
    let id = paper(&mut db, &[1]);
    let web = FakeHttp::new()
        .route(&jats_url(1), 404, "")
        .route(&pdf_url(1), 403, "");
    let p = pipeline(tmp.path(), &FakeHttp::new(), &web, "sha");
    run(&p, &mut db, only(Phase::Fulltext), "2024-01-15");
    let (form, _, attempts, kind) = fulltext_row(&mut db, id).unwrap();
    assert_eq!(
        (form.as_str(), attempts, kind.as_deref()),
        ("abstract", 1, Some("lasting"))
    );
    assert!(
        bml_library::fulltext::next_paper(&mut db, bml_library::FulltextSource::Medrxiv)
            .unwrap()
            .is_none()
    );

    // A new version that fails too counts its attempts from 0 and then
    // waits like any other: it is not picked again and again.
    add_version(&mut db, id, 2);
    web.set(&jats_url(2), 404, "");
    web.set(&pdf_url(2), 403, "");
    let r = run(&p, &mut db, only(Phase::Fulltext), "2024-01-15")
        .fulltext
        .unwrap();
    assert_eq!(r.tried, 1);
    let (form, _, attempts, _) = fulltext_row(&mut db, id).unwrap();
    assert_eq!((form.as_str(), attempts), ("abstract", 1));
    assert_eq!(version_tried(&mut db, id), Some(2));
    assert!(
        bml_library::fulltext::next_paper(&mut db, bml_library::FulltextSource::Medrxiv)
            .unwrap()
            .is_none()
    );

    add_version(&mut db, id, 3);
    web.set(&jats_url(3), 200, JATS);
    let r = run(&p, &mut db, only(Phase::Fulltext), "2024-01-15")
        .fulltext
        .unwrap();
    assert_eq!((r.tried, r.jats), (1, 1));
    let (form, held, attempts, _) = fulltext_row(&mut db, id).unwrap();
    assert_eq!(
        (form.as_str(), held.as_deref(), attempts),
        ("jats", Some("3"), 0)
    );
    assert_eq!(version_tried(&mut db, id), Some(3));
}

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn a_row_from_before_version_tried_waits_for_its_retry_time() {
    let _g = common::serial();
    let tmp = tempfile::tempdir().unwrap();
    let Some((_s, mut db)) = server(tmp.path()) else {
        return;
    };
    let id = paper(&mut db, &[1]);
    let web = FakeHttp::new()
        .route(&jats_url(1), 404, "")
        .route(&pdf_url(1), 403, "");
    let p = pipeline(tmp.path(), &FakeHttp::new(), &web, "sha");
    run(&p, &mut db, only(Phase::Fulltext), "2024-01-15");
    // As written before migration 3: no version_tried.
    db.execute(
        "UPDATE publication_fulltext SET version_tried = NULL, attempts = 4 \
         WHERE publication_id = $1",
        &[&id],
    )
    .unwrap();
    assert!(
        bml_library::fulltext::next_paper(&mut db, bml_library::FulltextSource::Medrxiv)
            .unwrap()
            .is_none(),
        "waits for retry_after"
    );
    db.execute(
        "UPDATE publication_fulltext SET retry_after = now() - interval '1 second'",
        &[],
    )
    .unwrap();
    let due = bml_library::fulltext::next_paper(&mut db, bml_library::FulltextSource::Medrxiv)
        .unwrap()
        .expect("due once its retry time has passed");
    assert_eq!((due.version, due.attempts), (1, 4), "attempts kept");
}

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn resume_after_fulltext_commit_before_cache_delete() {
    let _g = common::serial();
    let tmp = tempfile::tempdir().unwrap();
    let Some((_s, mut db)) = server(tmp.path()) else {
        return;
    };
    paper(&mut db, &[1]);
    let web = FakeHttp::new().route(&jats_url(1), 200, JATS);
    let p = pipeline(tmp.path(), &FakeHttp::new(), &web, "sha");
    // A crash after the commit: the old file is queued for deletion, still there.
    p.cache.save_jats(JATS.as_bytes(), "old_v1").unwrap();
    db.execute(
        "INSERT INTO cache_deletions (cache_key) VALUES ('old_v1')",
        &[],
    )
    .unwrap();
    // A file no row names (another database's, say): never deleted for that.
    p.cache.save_jats(JATS.as_bytes(), "unknown_v1").unwrap();
    let status = bml_library::status::library_status(&mut db, &p.cache).unwrap();
    assert_eq!(
        (status.pending_deletions, status.unreferenced_files),
        (1, 2)
    );
    let r = run(&p, &mut db, only(Phase::Fulltext), "2024-01-15")
        .fulltext
        .unwrap();
    assert_eq!((r.old_files_removed, r.jats), (1, 1));
    assert!(
        p.cache.get_jats("old_v1").unwrap().is_none(),
        "the queued file is gone"
    );
    assert!(
        p.cache.get_jats("unknown_v1").unwrap().is_some(),
        "the unknown file stays"
    );
    let status = bml_library::status::library_status(&mut db, &p.cache).unwrap();
    assert_eq!(
        (
            status.pending_deletions,
            status.unreferenced_files,
            status.jats
        ),
        (0, 1, 1)
    );
}

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn the_from_day_is_remembered() {
    let _g = common::serial();
    let tmp = tempfile::tempdir().unwrap();
    let Some((_s, mut db)) = server(tmp.path()) else {
        return;
    };
    let api = FakeHttp::new()
        .route(&details_url("2024-01-16"), 200, details_page(&[]))
        .route(&details_url("2024-01-17"), 200, details_page(&[]));
    let p = pipeline(tmp.path(), &api, &FakeHttp::new(), "sha");
    run(&p, &mut db, only(Phase::Metadata), "2024-01-16");
    api.seen().lock().unwrap().clear();
    // No --from now: the library keeps the day chosen first, not 2019.
    let again = run_from(&p, &mut db, only(Phase::Metadata), None);
    assert!(again.metadata.unwrap().errors.is_empty());
    let seen = api.seen().lock().unwrap().clone();
    assert!(seen.iter().all(|u| !u.contains("2024-01-15")), "{seen:?}");
}

/// Every GET and every embedding call, in order.
type Events = Arc<Mutex<Vec<&'static str>>>;

struct LoggingHttp(FakeHttp, Events);
impl HttpClient for LoggingHttp {
    fn get(&self, url: &str) -> Result<HttpResponse, FetchError> {
        self.1.lock().unwrap().push("get");
        self.0.get(url)
    }
}

struct LoggingEmbedder(StubEmbedder, Events);
impl ChunkEmbedder for LoggingEmbedder {
    fn model_sha256(&self) -> &str {
        self.0.model_sha256()
    }
    fn embed(&mut self, texts: &[&str]) -> Result<Vec<Vec<f32>>, String> {
        self.1.lock().unwrap().push("embed");
        self.0.embed(texts)
    }
}

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn abstracts_are_indexed_before_full_text_is_fetched() {
    let _g = common::serial();
    let tmp = tempfile::tempdir().unwrap();
    let Some((_s, mut db)) = server(tmp.path()) else {
        return;
    };
    paper(&mut db, &[1]);
    let events: Events = Arc::new(Mutex::new(Vec::new()));
    let web = FakeHttp::new().route(&jats_url(1), 200, JATS);
    let mut p = pipeline(tmp.path(), &FakeHttp::new(), &web, "sha");
    p.web = Arc::new(LoggingHttp(web, events.clone()));
    let log = events.clone();
    p.embedder = Box::new(move || Ok(Box::new(LoggingEmbedder(stub("sha", None), log.clone()))));
    let report = run(
        &p,
        &mut db,
        PhaseSet::all().without(Phase::Metadata),
        "2024-01-15",
    );
    assert!(report.failures.is_empty(), "{:?}", report.failures);
    let events = events.lock().unwrap().clone();
    assert_eq!(events.first(), Some(&"embed"), "{events:?}");
    assert_eq!(
        events.last(),
        Some(&"embed"),
        "full text indexed after: {events:?}"
    );
    assert!(
        scalar_i64(
            &mut db,
            "SELECT count(*) FROM chunks WHERE kind = 'fulltext'"
        ) > 0
    );
}

/// A second paper (another DOI) with `title`; returns its id.
fn other_paper(db: &mut Client, doi: &str, title: &str) -> i32 {
    db.query_one(
        "INSERT INTO publications (title, doi, abstract, publication_date, first_seen_source, \
         created_at, updated_at) VALUES ($1, $2, 'An abstract.', '2024-01-15', 'medrxiv', \
         'now', 'now') RETURNING id",
        &[&title, &doi],
    )
    .unwrap()
    .get(0)
}

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn a_paper_that_fails_to_index_does_not_block_the_others() {
    let _g = common::serial();
    let tmp = tempfile::tempdir().unwrap();
    let Some((_s, mut db)) = server(tmp.path()) else {
        return;
    };
    let bad = other_paper(&mut db, "10.1101/bad", "poison");
    let good = other_paper(&mut db, "10.1101/good", "Fine");
    let mut p = pipeline(tmp.path(), &FakeHttp::new(), &FakeHttp::new(), "sha");
    p.embedder = Box::new(|| Ok(Box::new(stub("sha", Some("poison")))));
    let report = run(&p, &mut db, only(Phase::Index), "2024-01-15");
    assert!(
        report.failures.is_empty(),
        "no phase failure: {:?}",
        report.failures
    );
    assert!(report.failed(), "a paper failure is still a failure");
    let index = report.index.unwrap();
    assert_eq!((index.indexed, index.failed.len()), (1, 1), "{index:?}");
    let complete = |db: &mut Client, id: i32| {
        db.query_opt(
            "SELECT 1 FROM publication_index WHERE publication_id = $1 AND status = 'complete'",
            &[&id],
        )
        .unwrap()
        .is_some()
    };
    assert!(complete(&mut db, good));
    assert!(!complete(&mut db, bad));
}

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn failures_in_a_row_end_the_index_phase() {
    let _g = common::serial();
    let tmp = tempfile::tempdir().unwrap();
    let Some((_s, mut db)) = server(tmp.path()) else {
        return;
    };
    for i in 0..=bml_library::index::MAX_FAILURES_IN_A_ROW {
        other_paper(&mut db, &format!("10.1101/p{i}"), "poison");
    }
    let mut p = pipeline(tmp.path(), &FakeHttp::new(), &FakeHttp::new(), "sha");
    p.embedder = Box::new(|| Ok(Box::new(stub("sha", Some("poison")))));
    let report = run(&p, &mut db, only(Phase::Index), "2024-01-15");
    assert_eq!(report.failures.len(), 1, "{:?}", report.failures);
    assert!(
        report.failures[0].1.contains("stub"),
        "{:?}",
        report.failures
    );
}

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn only_a_complete_update_counts_as_the_last_update() {
    let _g = common::serial();
    let tmp = tempfile::tempdir().unwrap();
    let Some((_s, mut db)) = server(tmp.path()) else {
        return;
    };
    paper(&mut db, &[1]);
    let mut p = pipeline(tmp.path(), &FakeHttp::new(), &FakeHttp::new(), "sha");
    p.embedder = Box::new(|| Err("no model".into()));
    run(&p, &mut db, only(Phase::Index), "2024-01-15");
    assert!(!bml_library::updated_within(&mut db, 1).unwrap());
    let p = pipeline(tmp.path(), &FakeHttp::new(), &FakeHttp::new(), "sha");
    let partial = run(&p, &mut db, only(Phase::Index), "2024-01-15");
    assert!(!partial.failed() && !partial.stopped_early(), "{partial:?}");
    assert!(
        !bml_library::updated_within(&mut db, 1).unwrap(),
        "a run with skipped phases is not a complete update"
    );
    let api = FakeHttp::new();
    for day in ["2024-01-15", "2024-01-16", "2024-01-17"] {
        api.set(&details_url(day), 200, details_page(&[]));
    }
    let web = FakeHttp::new().route(&jats_url(1), 200, JATS);
    let p = pipeline(tmp.path(), &api, &web, "sha");
    let full = run(&p, &mut db, PhaseSet::all(), "2024-01-15");
    assert!(!full.failed() && !full.stopped_early(), "{full:?}");
    assert!(bml_library::updated_within(&mut db, 1).unwrap());
}

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn a_scheduled_run_allows_the_slack_but_no_more() {
    let _g = common::serial();
    let tmp = tempfile::tempdir().unwrap();
    let Some((_s, mut db)) = server(tmp.path()) else {
        return;
    };
    let finished_ago = |db: &mut Client, ago: &str| {
        db.execute(
            &format!(
                "INSERT INTO library_state (id, last_update_at) VALUES (1, now() - interval '{ago}') \
                 ON CONFLICT (id) DO UPDATE SET last_update_at = excluded.last_update_at"
            ),
            &[],
        )
        .unwrap();
    };
    // SCHEDULE_SLACK_HOURS is 2: a trigger a little early still waits...
    finished_ago(&mut db, "6 days 21 hours");
    assert!(bml_library::updated_within(&mut db, 7).unwrap());
    // ...but one within the slack of the interval runs.
    finished_ago(&mut db, "6 days 23 hours");
    assert!(!bml_library::updated_within(&mut db, 7).unwrap());
}

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn metadata_crossing_windows_asks_every_day_once() {
    let _g = common::serial();
    let tmp = tempfile::tempdir().unwrap();
    let Some((_s, mut db)) = server(tmp.path()) else {
        return;
    };
    let from = NaiveDate::from_ymd_opt(2023, 12, 13).unwrap();
    let today = NaiveDate::from_ymd_opt(2024, 1, 17).unwrap();
    let days: Vec<String> = from
        .iter_days()
        .take_while(|d| *d <= today)
        .map(|d| d.to_string())
        .collect();
    assert!(days.len() as u64 > bml_library::metadata::METADATA_WINDOW_DAYS);
    let api = FakeHttp::new();
    for day in &days {
        api.set(&details_url(day), 200, details_page(&[]));
    }
    let p = pipeline(tmp.path(), &api, &FakeHttp::new(), "sha");
    let report = run(&p, &mut db, only(Phase::Metadata), "2023-12-13");
    assert!(!report.failed(), "{report:?}");
    let seen = api.seen().lock().unwrap().clone();
    // bmlib asks the last week's unsettled days again (its settle rule), so
    // only settled days must be asked exactly once; none may be missed.
    let settled = (today - chrono::Days::new(7)).to_string();
    for day in &days {
        let asked = seen.iter().filter(|u| **u == details_url(day)).count();
        if *day < settled {
            assert_eq!(asked, 1, "{day}: {seen:?}");
        } else {
            assert!(asked >= 1, "{day}: {seen:?}");
        }
    }
}

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn a_metadata_429_stops_the_run_early_and_sends_nothing_more() {
    let _g = common::serial();
    let tmp = tempfile::tempdir().unwrap();
    let Some((_s, mut db)) = server(tmp.path()) else {
        return;
    };
    let api = FakeHttp::new().route(&details_url("2024-01-15"), 429, "");
    let p = pipeline(tmp.path(), &api, &FakeHttp::new(), "sha");
    let report = run(&p, &mut db, only(Phase::Metadata), "2024-01-15");
    let m = report.metadata.as_ref().unwrap();
    assert!(m.stopped && m.rate_limited, "{m:?}");
    assert!(
        !report.failed(),
        "a rate limit is not a failure: {report:?}"
    );
    assert!(report.stopped_early());
    assert_eq!(
        api.seen().lock().unwrap().as_slice(),
        [details_url("2024-01-15")]
    );
    assert!(!bml_library::updated_within(&mut db, 1).unwrap());
    // The refused day is fetched again next run.
    for day in ["2024-01-15", "2024-01-16", "2024-01-17"] {
        api.set(&details_url(day), 200, details_page(&[]));
    }
    api.seen().lock().unwrap().clear();
    let again = run(&p, &mut db, only(Phase::Metadata), "2024-01-15");
    assert!(!again.failed() && !again.stopped_early(), "{again:?}");
    assert!(api
        .seen()
        .lock()
        .unwrap()
        .contains(&details_url("2024-01-15")));
}

/// Run every phase, stopping as `stop` says.
fn run_stopping(
    p: &Pipeline,
    db: &mut Client,
    stop: &AtomicBool,
    progress: &mut dyn FnMut(bml_library::Progress),
) -> UpdateReport {
    let options = UpdateOptions {
        from: Some(NaiveDate::from_ymd_opt(2024, 1, 15).unwrap()),
        phases: PhaseSet::all().without(Phase::Metadata),
        stop,
    };
    p.update(db, &options, progress)
}

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn stop_ends_the_run_after_the_paper_in_flight() {
    let _g = common::serial();
    let tmp = tempfile::tempdir().unwrap();
    let Some((_s, mut db)) = server(tmp.path()) else {
        return;
    };
    paper(&mut db, &[1]);
    let second = other_paper(&mut db, "10.1101/second", "Second");
    db.execute(
        "INSERT INTO fulltext_sources (publication_id, source, url, format, version, created_at) \
         VALUES ($1, 'medrxiv', 'https://www.medrxiv.org/second.source.xml', 'xml', '1', 'now')",
        &[&second],
    )
    .unwrap();
    // Either paper may be fetched first; each one's JATS is there.
    let web = FakeHttp::new().route(&jats_url(1), 200, JATS).route(
        "https://www.medrxiv.org/second.source.xml",
        200,
        JATS,
    );
    let p = pipeline(tmp.path(), &FakeHttp::new(), &web, "sha");
    let stop = AtomicBool::new(false);
    let report = run_stopping(&p, &mut db, &stop, &mut |progress| {
        if progress.phase == Phase::Fulltext {
            stop.store(true, std::sync::atomic::Ordering::Relaxed);
        }
    });
    let f = report.fulltext.as_ref().unwrap();
    assert_eq!((f.tried, &f.end), (1, &FulltextEnd::Stopped), "{f:?}");
    assert!(report.index.as_ref().unwrap().stopped, "{report:?}");
    assert!(report.stopped_early() && !report.failed());
    assert_eq!(web.seen().lock().unwrap().len(), 1, "one paper fetched");
    assert!(!bml_library::updated_within(&mut db, 1).unwrap());
}

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn stop_set_before_the_run_sends_nothing() {
    let _g = common::serial();
    let tmp = tempfile::tempdir().unwrap();
    let Some((_s, mut db)) = server(tmp.path()) else {
        return;
    };
    paper(&mut db, &[1]);
    let api = FakeHttp::new();
    let web = FakeHttp::new();
    let p = pipeline(tmp.path(), &api, &web, "sha");
    let stop = AtomicBool::new(true);
    let options = UpdateOptions {
        from: Some(NaiveDate::from_ymd_opt(2024, 1, 15).unwrap()),
        phases: PhaseSet::all(),
        stop: &stop,
    };
    let report = p.update(&mut db, &options, &mut |_| {});
    assert!(report.stopped_early() && !report.failed(), "{report:?}");
    assert!(api.seen().lock().unwrap().is_empty());
    assert!(web.seen().lock().unwrap().is_empty());
}

// ---- index ---------------------------------------------------------------

/// The cached file of the paper's held full text.
fn cached_file(p: &Pipeline, db: &mut Client) -> PathBuf {
    let path: String = db
        .query_one("SELECT cache_path FROM publication_fulltext", &[])
        .unwrap()
        .get(0);
    p.cache.cache_dir.join(path)
}

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn a_full_text_that_cannot_be_read_now_is_kept_and_tried_again() {
    let _g = common::serial();
    let tmp = tempfile::tempdir().unwrap();
    let Some((_s, mut db)) = server(tmp.path()) else {
        return;
    };
    let id = paper(&mut db, &[1]);
    let web = FakeHttp::new().route(&jats_url(1), 200, JATS);
    let p = pipeline(tmp.path(), &FakeHttp::new(), &web, "sha");
    run(&p, &mut db, only(Phase::Fulltext), "2024-01-15");
    let file = cached_file(&p, &mut db);
    // A directory in the file's place: reading it is an I/O error, as a
    // busy or unmounted disk would give.
    std::fs::rename(&file, tmp.path().join("aside.xml")).unwrap();
    std::fs::create_dir(&file).unwrap();
    let report = run(&p, &mut db, only(Phase::Index), "2024-01-15");
    assert!(report.failed(), "{report:?}");
    assert_eq!(report.index.as_ref().unwrap().failed.len(), 1, "{report:?}");
    assert_eq!(fulltext_row(&mut db, id).unwrap().0, "jats");
    assert_eq!(
        scalar_i64(&mut db, "SELECT count(*) FROM cache_deletions"),
        0
    );
    std::fs::remove_dir(&file).unwrap();
    std::fs::rename(tmp.path().join("aside.xml"), &file).unwrap();
    let index = run(&p, &mut db, only(Phase::Index), "2024-01-15")
        .index
        .unwrap();
    assert_eq!((index.indexed, index.fulltext), (1, 1), "{index:?}");
}

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn a_full_text_that_does_not_parse_leaves_the_abstract() {
    let _g = common::serial();
    let tmp = tempfile::tempdir().unwrap();
    let Some((_s, mut db)) = server(tmp.path()) else {
        return;
    };
    let id = paper(&mut db, &[1]);
    let web = FakeHttp::new().route(&jats_url(1), 200, JATS);
    let p = pipeline(tmp.path(), &FakeHttp::new(), &web, "sha");
    run(&p, &mut db, only(Phase::Fulltext), "2024-01-15");
    let file = cached_file(&p, &mut db);
    std::fs::write(&file, "<article><unclosed>").unwrap();
    let index = run(&p, &mut db, only(Phase::Index), "2024-01-15")
        .index
        .unwrap();
    assert_eq!((index.indexed, index.unreadable), (1, 1), "{index:?}");
    let row = fulltext_row(&mut db, id).unwrap();
    assert_eq!(
        (row.0.as_str(), row.3.as_deref()),
        ("abstract", Some("lasting"))
    );
    assert!(!file.exists());
}

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn an_abstract_only_paper_is_indexed_and_reindexed_when_full_text_arrives() {
    let _g = common::serial();
    let tmp = tempfile::tempdir().unwrap();
    let Some((_s, mut db)) = server(tmp.path()) else {
        return;
    };
    let id = paper(&mut db, &[1]);
    let web = FakeHttp::new();
    let p = pipeline(tmp.path(), &FakeHttp::new(), &web, "sha");
    let r = run(&p, &mut db, only(Phase::Index), "2024-01-15")
        .index
        .unwrap();
    assert_eq!((r.indexed, r.fulltext, r.chunks), (1, 0, 1));
    let row = db
        .query_one(
            "SELECT status, converter_version FROM publication_index",
            &[],
        )
        .unwrap();
    assert_eq!(
        (row.get::<_, &str>(0), row.get::<_, &str>(1)),
        ("complete", "abstract")
    );
    assert_eq!(
        scalar_i64(&mut db, "SELECT count(*) FROM chunk_embeddings"),
        1
    );

    // A second run has nothing to do.
    assert_eq!(
        run(&p, &mut db, only(Phase::Index), "2024-01-15")
            .index
            .unwrap()
            .indexed,
        0
    );

    web.set(&jats_url(1), 200, JATS);
    run(
        &p,
        &mut db,
        PhaseSet::all().without(Phase::Metadata),
        "2024-01-15",
    );
    let converter: String = db
        .query_one(
            "SELECT converter_version FROM publication_index WHERE publication_id = $1",
            &[&id],
        )
        .unwrap()
        .get(0);
    assert!(converter.starts_with("jats-"), "{converter}");
    assert!(
        scalar_i64(
            &mut db,
            "SELECT count(*) FROM chunks WHERE kind = 'fulltext'"
        ) > 0
    );
    assert_eq!(
        scalar_i64(&mut db, "SELECT count(*) FROM chunks c LEFT JOIN chunk_embeddings e ON e.chunk_id = c.id WHERE e.chunk_id IS NULL"),
        0,
        "every chunk has its vector"
    );
}

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn changed_label_reindexes() {
    let _g = common::serial();
    let tmp = tempfile::tempdir().unwrap();
    let Some((_s, mut db)) = server(tmp.path()) else {
        return;
    };
    paper(&mut db, &[1]);
    let p = pipeline(tmp.path(), &FakeHttp::new(), &FakeHttp::new(), "model-a");
    assert_eq!(
        run(&p, &mut db, only(Phase::Index), "2024-01-15")
            .index
            .unwrap()
            .indexed,
        1
    );
    let q = pipeline(tmp.path(), &FakeHttp::new(), &FakeHttp::new(), "model-b");
    assert_eq!(
        run(&q, &mut db, only(Phase::Index), "2024-01-15")
            .index
            .unwrap()
            .indexed,
        1
    );
    let sha: String = db
        .query_one("SELECT model_sha256 FROM publication_index", &[])
        .unwrap()
        .get(0);
    assert_eq!(sha, "model-b");
    assert_eq!(
        scalar_i64(&mut db, "SELECT count(*) FROM chunks"),
        1,
        "no duplicate chunks"
    );
}

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn resume_after_index_crash() {
    let _g = common::serial();
    let tmp = tempfile::tempdir().unwrap();
    let Some((_s, mut db)) = server(tmp.path()) else {
        return;
    };
    paper(&mut db, &[1]);
    let web = FakeHttp::new().route(&jats_url(1), 200, JATS);
    let mut p = pipeline(tmp.path(), &FakeHttp::new(), &web, "sha");
    run(&p, &mut db, only(Phase::Fulltext), "2024-01-15");
    // The model fails while the paper is being embedded.
    p.embedder = Box::new(|| {
        Ok(Box::new(StubEmbedder {
            fail_on: Some(1),
            ..stub("sha", None)
        }))
    });
    let failed = run(&p, &mut db, only(Phase::Index), "2024-01-15");
    assert_eq!(
        failed.index.unwrap().failed.len(),
        1,
        "a paper failure, not the phase's"
    );
    assert_eq!(scalar_i64(&mut db, "SELECT count(*) FROM chunks"), 0);
    let status: String = db
        .query_one("SELECT status FROM publication_index", &[])
        .unwrap()
        .get(0);
    assert_eq!(status, "pending");

    let p = pipeline(tmp.path(), &FakeHttp::new(), &web, "sha");
    let r = run(&p, &mut db, only(Phase::Index), "2024-01-15")
        .index
        .unwrap();
    assert_eq!(r.indexed, 1);
    let n = scalar_i64(&mut db, "SELECT count(*) FROM chunks");
    let label = scalar_i64(&mut db, "SELECT chunk_count::bigint FROM publication_index");
    assert_eq!(n, label, "complete means every chunk is stored");
}

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn a_missing_model_fails_the_index_phase_only() {
    let _g = common::serial();
    let tmp = tempfile::tempdir().unwrap();
    let Some((_s, mut db)) = server(tmp.path()) else {
        return;
    };
    let api = FakeHttp::new()
        .route(
            &details_url("2024-01-15"),
            200,
            details_page(&[record("2024-01-15", 1)]),
        )
        .route(&details_url("2024-01-16"), 200, details_page(&[]))
        .route(&details_url("2024-01-17"), 200, details_page(&[]));
    let web = FakeHttp::new().route(&jats_url(1), 200, JATS);
    let real = Pipeline::new(
        FullTextCache {
            cache_dir: tmp.path().join("documents"),
        },
        tmp.path().join("no-such-model.gguf"),
    );
    let p = Pipeline {
        api: Arc::new(api),
        api_delay: Duration::ZERO,
        web: Arc::new(web),
        web_delay: Duration::ZERO,
        clock: Box::new(|| instant("2024-01-17T13:00:00Z")),
        ..real
    };
    let report = run(&p, &mut db, PhaseSet::all(), "2024-01-15");
    assert_eq!(report.metadata.unwrap().added, 1);
    assert_eq!(report.fulltext.unwrap().jats, 1);
    assert!(report.index.is_none());
    let (phase, message) = &report.failures[0];
    assert_eq!(*phase, Phase::Index);
    assert!(message.contains("bml setup"), "{message}");
}

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn library_without_topic_reads_medrxiv() {
    use bml_library::topics::{library_source, set_topic, topic, topic_query, LibrarySource};
    let _g = common::serial();
    let tmp = tempfile::tempdir().unwrap();
    let Some((_s, mut db)) = server(tmp.path()) else {
        return;
    };
    assert_eq!(library_source(&mut db).unwrap(), LibrarySource::Medrxiv);
    let depression = topic("depression-anxiety").unwrap();
    set_topic(&mut db, depression).unwrap();
    assert_eq!(
        library_source(&mut db).unwrap(),
        LibrarySource::EuropePmc {
            topic_id: "depression-anxiety".into(),
            query: topic_query(depression),
        }
    );
    // Choosing the same topic again changes nothing.
    set_topic(&mut db, depression).unwrap();
}

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn set_topic_refuses_another_topic() {
    use bml_library::topics::{set_topic, topic};
    let _g = common::serial();
    let tmp = tempfile::tempdir().unwrap();
    let Some((_s, mut db)) = server(tmp.path()) else {
        return;
    };
    set_topic(&mut db, topic("stroke").unwrap()).unwrap();
    let error = set_topic(&mut db, topic("cardiology").unwrap())
        .unwrap_err()
        .to_string();
    assert!(error.contains("Stroke"), "{error}");

    // A medRxiv library with papers is refused too.
    let tmp2 = tempfile::tempdir().unwrap();
    let Some((_s2, mut db2)) = server(tmp2.path()) else {
        return;
    };
    other_paper(&mut db2, "10.1101/2024.01.15.24000099", "A medRxiv paper");
    let error = set_topic(&mut db2, topic("stroke").unwrap())
        .unwrap_err()
        .to_string();
    assert!(error.contains("medRxiv"), "{error}");
}

/// The Europe PMC search URL bmlib's fetcher builds for `day`'s first page.
fn europepmc_url(query: &str, day: &str) -> String {
    use bmlib::publications::fetchers::europepmc::{page_params, SEARCH_URL};
    let params = page_params(day, "*", query, None);
    let pairs: Vec<(&str, &str)> = params
        .iter()
        .map(|(k, v)| (k.as_str(), v.as_str()))
        .collect();
    format!(
        "{SEARCH_URL}?{}",
        bmlib::transparency::analyzer::encode_query(&pairs)
    )
}

/// The undated search bmlib sends after an empty day, to tell an empty day
/// from a query that matches nothing on any day.
fn europepmc_probe_url(query: &str) -> String {
    use bmlib::publications::fetchers::europepmc::SEARCH_URL;
    let query = format!("({query})");
    let pairs = [
        ("query", query.as_str()),
        ("resultType", "lite"),
        ("format", "json"),
        ("pageSize", "1"),
    ];
    format!(
        "{SEARCH_URL}?{}",
        bmlib::transparency::analyzer::encode_query(&pairs)
    )
}

/// The probe's answer: the query finds papers on other days.
const EUROPEPMC_PROBE_HIT: &str = r#"{"hitCount": 1, "resultList": {"result": []}}"#;

/// A Europe PMC search page holding open-access hits for `pmcids`.
fn europepmc_page(pmcids: &[&str], day: &str) -> String {
    let hits: Vec<serde_json::Value> = pmcids
        .iter()
        .map(|pmcid| {
            // A PMID of its own per paper (bmlib merges records sharing one).
            let pmid = format!("39{}", pmcid.trim_start_matches("PMC"));
            serde_json::json!({
                "id": pmid,
                "source": "MED",
                "pmid": pmid,
                "pmcid": pmcid,
                "doi": format!("10.1000/demo.{pmcid}"),
                "title": format!("Trial {pmcid}"),
                "abstractText": "We randomised adults with depression.",
                "firstPublicationDate": day,
                "firstIndexDate": day,
                "isOpenAccess": "Y",
                "inEPMC": "Y",
            })
        })
        .collect();
    serde_json::json!({
        "hitCount": hits.len(),
        "nextCursorMark": "*",
        "resultList": {"result": hits},
    })
    .to_string()
}

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn europepmc_window_sends_the_query() {
    use bml_library::metadata::run_window;
    use bml_library::polite_client::PoliteClient;
    use bml_library::EUROPEPMC_SOURCE;
    use std::collections::BTreeMap;
    let _g = common::serial();
    let tmp = tempfile::tempdir().unwrap();
    let Some((_s, mut db)) = server(tmp.path()) else {
        return;
    };
    let query = "OPEN_ACCESS:Y AND TITLE:\"depression\"";
    let url = europepmc_url(query, "2024-01-16");
    let api = FakeHttp::new().route(&url, 200, europepmc_page(&["PMC100"], "2024-01-16"));
    let client = Arc::new(PoliteClient::new(Arc::new(api.clone()), Duration::ZERO));
    let configs = BTreeMap::from([(
        bml_library::FulltextSource::EuropePmc
            .metadata_source()
            .to_string(),
        BTreeMap::from([("query".to_string(), query.to_string())]),
    )]);
    let day = NaiveDate::from_ymd_opt(2024, 1, 16).unwrap();
    let stop = AtomicBool::new(false);
    let report = run_window(
        &mut db,
        client,
        bml_library::FulltextSource::EuropePmc,
        &configs,
        day,
        day,
        &stop,
        &|| instant("2024-01-17T13:00:00Z"),
        &mut |_| {},
    )
    .unwrap();
    assert_eq!(report.added, 1, "{report:?}");
    assert_eq!(api.seen().lock().unwrap().as_slice(), [url]);
    let source: String = db
        .query_one("SELECT first_seen_source FROM publications", &[])
        .unwrap()
        .get(0);
    assert_eq!(source, EUROPEPMC_SOURCE);
}

const EUROPEPMC_NO_BODY: &str = include_str!("fixtures/europepmc_no_body.xml");

/// The `fullTextXML` URL of `pmcid`.
fn europepmc_xml_url(pmcid: &str) -> String {
    format!("https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML")
}

/// Insert an open-access Europe PMC paper with its `fullTextXML` source.
fn europepmc_paper(db: &mut Client, pmcid: &str) -> i32 {
    let id: i32 = db
        .query_one(
            "INSERT INTO publications (title, pmcid, abstract, publication_date, \
             first_seen_source, created_at, updated_at) VALUES ($1, $2, \
             'We randomised adults with depression.', '2024-01-15', 'europepmc', 'now', 'now') \
             RETURNING id",
            &[&format!("Trial {pmcid}"), &pmcid],
        )
        .unwrap()
        .get(0);
    db.execute(
        "INSERT INTO fulltext_sources (publication_id, source, url, format, created_at) \
         VALUES ($1, 'europepmc', $2, 'xml', 'now')",
        &[&id, &europepmc_xml_url(pmcid)],
    )
    .unwrap();
    id
}

fn run_fulltext(
    db: &mut Client,
    tmp: &Path,
    web: &FakeHttp,
    source: bml_library::FulltextSource,
) -> bml_library::fulltext::FulltextReport {
    let stop = AtomicBool::new(false);
    bml_library::fulltext::run(
        db,
        source,
        Arc::new(web.clone()),
        Duration::ZERO,
        &FullTextCache {
            cache_dir: tmp.join("documents"),
        },
        &stop,
        &mut |_| {},
    )
    .unwrap()
}

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn europepmc_paper_gets_full_text() {
    let _g = common::serial();
    let tmp = tempfile::tempdir().unwrap();
    let Some((_s, mut db)) = server(tmp.path()) else {
        return;
    };
    let id = europepmc_paper(&mut db, "PMC100");
    let web = FakeHttp::new().route(&europepmc_xml_url("PMC100"), 200, JATS);
    let report = run_fulltext(
        &mut db,
        tmp.path(),
        &web,
        bml_library::FulltextSource::EuropePmc,
    );
    assert_eq!(report.jats, 1, "{report:?}");
    assert_eq!(
        web.seen().lock().unwrap().as_slice(),
        [europepmc_xml_url("PMC100")]
    );
    assert_eq!(fulltext_row(&mut db, id).unwrap().0, "jats");
}

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn missing_body_is_abstract_only() {
    let _g = common::serial();
    let tmp = tempfile::tempdir().unwrap();
    let Some((_s, mut db)) = server(tmp.path()) else {
        return;
    };
    let id = europepmc_paper(&mut db, "PMC200");
    let web = FakeHttp::new().route(&europepmc_xml_url("PMC200"), 200, EUROPEPMC_NO_BODY);
    run_fulltext(
        &mut db,
        tmp.path(),
        &web,
        bml_library::FulltextSource::EuropePmc,
    );
    assert_eq!(fulltext_row(&mut db, id).unwrap().0, "abstract");
    web.seen().lock().unwrap().clear();
    // Before its retry time it is not asked for again.
    let again = run_fulltext(
        &mut db,
        tmp.path(),
        &web,
        bml_library::FulltextSource::EuropePmc,
    );
    assert_eq!(again.tried, 0, "{again:?}");
    assert!(web.seen().lock().unwrap().is_empty());
}

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn transport_error_leaves_paper_retryable() {
    let _g = common::serial();
    let tmp = tempfile::tempdir().unwrap();
    let Some((_s, mut db)) = server(tmp.path()) else {
        return;
    };
    let id = europepmc_paper(&mut db, "PMC300");
    // No route: every request is a transport error (the phone dropped out).
    let report = run_fulltext(
        &mut db,
        tmp.path(),
        &FakeHttp::new(),
        bml_library::FulltextSource::EuropePmc,
    );
    assert_eq!(report.passing, 1, "{report:?}");
    assert_eq!(report.lasting, 0, "{report:?}");
    let (form, _, attempts, kind) = fulltext_row(&mut db, id).unwrap();
    assert_eq!(form, "abstract");
    assert_eq!(attempts, 1);
    assert_eq!(kind.as_deref(), Some("passing"));
    let retry_set: bool = db
        .query_one(
            "SELECT retry_after IS NOT NULL FROM publication_fulltext WHERE publication_id = $1",
            &[&id],
        )
        .unwrap()
        .get(0);
    assert!(retry_set);
}

/// Every file under `dir` (none when it does not exist).
fn files_under(dir: &Path) -> Vec<std::path::PathBuf> {
    let Ok(entries) = std::fs::read_dir(dir) else {
        return Vec::new();
    };
    entries
        .flatten()
        .flat_map(|e| {
            let path = e.path();
            if path.is_dir() {
                files_under(&path)
            } else {
                vec![path]
            }
        })
        .collect()
}

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn a_sign_in_page_in_place_of_the_xml_is_passing_and_ends_the_phase() {
    use bml_library::fulltext::FulltextEnd;
    use bml_library::polite_client::NO_ANSWER_LIMIT;
    let _g = common::serial();
    let tmp = tempfile::tempdir().unwrap();
    let Some((_s, mut db)) = server(tmp.path()) else {
        return;
    };
    // An XHTML page with a <body><p>, which bmlib's JATS reader would take
    // for an article body.
    let page = "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n\
        <!DOCTYPE html PUBLIC \"-//W3C//DTD XHTML 1.0 Strict//EN\" \"x\">\n\
        <html xmlns=\"http://www.w3.org/1999/xhtml\"><head><title>Wi-Fi</title></head>\
        <body><p>Please accept the terms of the hotel Wi-Fi to continue.</p></body></html>";
    let portal = FakeHttp::new();
    for pmcid in ["PMC310", "PMC311", "PMC312", "PMC313", "PMC314"] {
        europepmc_paper(&mut db, pmcid);
        portal.set(&europepmc_xml_url(pmcid), 200, page);
    }
    let report = run_fulltext(
        &mut db,
        tmp.path(),
        &portal,
        bml_library::FulltextSource::EuropePmc,
    );
    assert_eq!(report.end, FulltextEnd::NoNetwork, "{report:?}");
    assert_eq!(report.jats, 0, "{report:?}");
    assert_eq!(report.lasting, 0, "{report:?}");
    assert_eq!(
        portal.seen().lock().unwrap().len(),
        NO_ANSWER_LIMIT as usize
    );
    // The paper whose request gave up is not recorded; the others wait an
    // hour, as abstracts.
    assert_eq!(
        scalar_i64(
            &mut db,
            "SELECT count(*) FROM publication_fulltext \
             WHERE form = 'abstract' AND last_error_kind = 'passing'"
        ),
        i64::from(NO_ANSWER_LIMIT - 1)
    );
    assert_eq!(
        scalar_i64(&mut db, "SELECT count(*) FROM publication_fulltext"),
        i64::from(NO_ANSWER_LIMIT - 1)
    );
    // Nothing of the page was cached as the paper's full text.
    let cached = files_under(&tmp.path().join("documents"));
    assert!(cached.is_empty(), "{cached:?}");
}

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn source_selects_the_papers() {
    let _g = common::serial();
    let tmp = tempfile::tempdir().unwrap();
    let Some((_s, mut db)) = server(tmp.path()) else {
        return;
    };
    let medrxiv = paper(&mut db, &[1]);
    let europepmc = europepmc_paper(&mut db, "PMC400");
    let web = FakeHttp::new()
        .route(&europepmc_xml_url("PMC400"), 200, JATS)
        .route(&jats_url(1), 200, JATS);
    run_fulltext(
        &mut db,
        tmp.path(),
        &web,
        bml_library::FulltextSource::EuropePmc,
    );
    assert_eq!(
        web.seen().lock().unwrap().as_slice(),
        [europepmc_xml_url("PMC400")]
    );
    assert!(fulltext_row(&mut db, medrxiv).is_none());
    web.seen().lock().unwrap().clear();
    run_fulltext(
        &mut db,
        tmp.path(),
        &web,
        bml_library::FulltextSource::Medrxiv,
    );
    assert_eq!(web.seen().lock().unwrap().as_slice(), [jats_url(1)]);
    assert_eq!(fulltext_row(&mut db, europepmc).unwrap().0, "jats");
}

/// A pipeline for a topic library whose Europe PMC traffic goes to `epmc`,
/// on 2024-02-20.
fn topic_pipeline(tmp: &Path, epmc: &FakeHttp) -> Pipeline {
    Pipeline {
        cache: FullTextCache {
            cache_dir: tmp.join("documents"),
        },
        api: Arc::new(FakeHttp::new()),
        api_delay: Duration::ZERO,
        web: Arc::new(FakeHttp::new()),
        web_delay: Duration::ZERO,
        europepmc: Arc::new(epmc.clone()),
        europepmc_delay: Duration::ZERO,
        embedder: Box::new(|| Ok(Box::new(stub("sha", None)))),
        clock: Box::new(|| instant("2024-02-20T13:00:00Z")),
    }
}

/// Every day from `from` to `to` answers an empty page, except `papers`
/// (day, PMC ID), each with its full text.
fn topic_days(query: &str, from: &str, to: &str, papers: &[(&str, &str)]) -> FakeHttp {
    let http = FakeHttp::new();
    let mut day = NaiveDate::parse_from_str(from, "%Y-%m-%d").unwrap();
    let last = NaiveDate::parse_from_str(to, "%Y-%m-%d").unwrap();
    while day <= last {
        let d = day.to_string();
        let held: Vec<&str> = papers
            .iter()
            .filter(|(pd, _)| *pd == d)
            .map(|(_, id)| *id)
            .collect();
        http.set(&europepmc_url(query, &d), 200, europepmc_page(&held, &d));
        day = day.succ_opt().unwrap();
    }
    http.set(&europepmc_probe_url(query), 200, EUROPEPMC_PROBE_HIT);
    for (_, pmcid) in papers {
        http.set(&europepmc_xml_url(pmcid), 200, JATS);
    }
    http
}

fn stroke_library(db: &mut Client) -> String {
    use bml_library::topics::{set_topic, topic, topic_query};
    let stroke = topic("stroke").unwrap();
    set_topic(db, stroke).unwrap();
    topic_query(stroke)
}

fn update_topic(
    p: &Pipeline,
    db: &mut Client,
    stop: &AtomicBool,
    progress: &mut dyn FnMut(bml_library::Progress),
) -> UpdateReport {
    let options = UpdateOptions {
        from: Some(NaiveDate::from_ymd_opt(2024, 1, 1).unwrap()),
        phases: PhaseSet::all(),
        stop,
    };
    p.update(db, &options, progress)
}

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn first_round_is_searchable_before_the_second_starts() {
    let _g = common::serial();
    let tmp = tempfile::tempdir().unwrap();
    let Some((_s, mut db)) = server(tmp.path()) else {
        return;
    };
    let query = stroke_library(&mut db);
    // Rounds: 2024-02-14..2024-02-20 (the short first week), then
    // 2024-01-15..2024-02-13, then 2024-01-01..2024-01-14.
    let epmc = topic_days(
        &query,
        "2024-01-01",
        "2024-02-20",
        &[("2024-02-18", "PMC500"), ("2024-02-01", "PMC501")],
    );
    let p = topic_pipeline(tmp.path(), &epmc);
    let stop = AtomicBool::new(false);
    let mut lines: Vec<bml_library::Progress> = Vec::new();
    let report = update_topic(&p, &mut db, &stop, &mut |line| lines.push(line));
    assert!(!report.failed() && !report.stopped_early(), "{report:?}");
    // A complete topic update is the library's last update.
    assert_eq!(
        scalar_i64(
            &mut db,
            "SELECT count(*) FROM library_state WHERE last_update_at IS NOT NULL"
        ),
        1
    );
    let first_index = lines
        .iter()
        .position(|l| l.phase == Phase::Index)
        .expect("an index line");
    let second_round = lines
        .iter()
        .position(|l| {
            l.phase == Phase::Metadata && l.message.starts_with("2024-01-15 to 2024-02-13")
        })
        .expect("the second round's metadata line");
    assert!(first_index < second_round, "{lines:#?}");
    let seen = epmc.seen().lock().unwrap().clone();
    let newest_text = seen
        .iter()
        .position(|u| u == &europepmc_xml_url("PMC500"))
        .unwrap();
    let older_day = seen
        .iter()
        .position(|u| u == &europepmc_url(&query, "2024-02-13"))
        .unwrap();
    assert!(newest_text < older_day);
    assert_eq!(
        scalar_i64(
            &mut db,
            "SELECT count(DISTINCT publication_id) FROM chunks WHERE kind = 'fulltext'"
        ),
        2
    );
}

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn stop_between_rounds_resumes() {
    let _g = common::serial();
    let tmp = tempfile::tempdir().unwrap();
    let Some((_s, mut db)) = server(tmp.path()) else {
        return;
    };
    let query = stroke_library(&mut db);
    let epmc = topic_days(
        &query,
        "2024-01-01",
        "2024-02-20",
        &[("2024-02-18", "PMC600"), ("2024-01-10", "PMC601")],
    );
    let p = topic_pipeline(tmp.path(), &epmc);
    let stop = AtomicBool::new(false);
    let first = update_topic(&p, &mut db, &stop, &mut |line| {
        if line.phase == Phase::Index {
            stop.store(true, std::sync::atomic::Ordering::Relaxed);
        }
    });
    assert!(first.stopped_early(), "{first:?}");
    assert!(!epmc
        .seen()
        .lock()
        .unwrap()
        .contains(&europepmc_url(&query, "2024-02-13")));
    epmc.seen().lock().unwrap().clear();
    let resumed = AtomicBool::new(false);
    let second = update_topic(&p, &mut db, &resumed, &mut |_| {});
    assert!(!second.failed() && !second.stopped_early(), "{second:?}");
    let seen = epmc.seen().lock().unwrap().clone();
    // The rounds not reached before the stop run now.
    assert!(seen.contains(&europepmc_url(&query, "2024-02-13")));
    assert!(seen.contains(&europepmc_url(&query, "2024-01-10")));
    assert_eq!(
        scalar_i64(
            &mut db,
            "SELECT count(DISTINCT publication_id) FROM chunks WHERE kind = 'fulltext'"
        ),
        2
    );
}

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn a_round_with_no_network_stops_cleanly() {
    let _g = common::serial();
    let tmp = tempfile::tempdir().unwrap();
    let Some((_s, mut db)) = server(tmp.path()) else {
        return;
    };
    stroke_library(&mut db);
    // No routes: every Europe PMC request is a transport error.
    let epmc = FakeHttp::new();
    let p = topic_pipeline(tmp.path(), &epmc);
    let stop = AtomicBool::new(false);
    let mut lines: Vec<bml_library::Progress> = Vec::new();
    let report = update_topic(&p, &mut db, &stop, &mut |line| lines.push(line));
    assert!(report.failed(), "{report:?}");
    assert!(report.stopped_early(), "{report:?}");
    // One round's days were tried, not the whole range.
    let tried = epmc.seen().lock().unwrap().len();
    assert!(tried <= 30, "{tried} requests");
    assert!(
        lines.iter().any(|l| l.message.contains("internet")),
        "{lines:#?}"
    );
    assert_eq!(
        scalar_i64(
            &mut db,
            "SELECT count(*) FROM publication_fulltext WHERE last_error_kind = 'lasting'"
        ),
        0
    );
    assert_eq!(
        scalar_i64(
            &mut db,
            "SELECT count(*) FROM library_state WHERE last_update_at IS NOT NULL"
        ),
        0
    );
}

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn paper_text_reads_the_stored_text_or_the_abstract() {
    use bml_library::index::paper_text;
    let _g = common::serial();
    let tmp = tempfile::tempdir().unwrap();
    let Some((_s, mut db)) = server(tmp.path()) else {
        return;
    };
    let full = europepmc_paper(&mut db, "PMC700");
    let bare = europepmc_paper(&mut db, "PMC701");
    let web = FakeHttp::new()
        .route(&europepmc_xml_url("PMC700"), 200, JATS)
        .route(&europepmc_xml_url("PMC701"), 200, EUROPEPMC_NO_BODY);
    run_fulltext(
        &mut db,
        tmp.path(),
        &web,
        bml_library::FulltextSource::EuropePmc,
    );
    let cache = FullTextCache {
        cache_dir: tmp.path().join("documents"),
    };
    let text = paper_text(&cache, &mut db, i64::from(full)).unwrap();
    assert_eq!(text.title, "Trial PMC700");
    assert!(text.text.len() > 500, "{}", text.text);
    let abstract_only = paper_text(&cache, &mut db, i64::from(bare)).unwrap();
    assert_eq!(abstract_only.text, "We randomised adults with depression.");
    assert!(!abstract_only.meta.contains("could not be read"));
    assert!(paper_text(&cache, &mut db, 999_999).is_err());
    // A held full text whose file is gone shows the abstract, and says so.
    std::fs::remove_dir_all(tmp.path().join("documents")).unwrap();
    let lost = paper_text(&cache, &mut db, i64::from(full)).unwrap();
    assert_eq!(lost.text, "We randomised adults with depression.");
    assert!(
        lost.meta.contains("full text could not be read"),
        "{}",
        lost.meta
    );
}

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn full_text_down_mid_rounds_indexes_what_arrived_and_stops() {
    use bml_library::polite_client::NO_ANSWER_LIMIT;
    let _g = common::serial();
    let tmp = tempfile::tempdir().unwrap();
    let Some((_s, mut db)) = server(tmp.path()) else {
        return;
    };
    let query = stroke_library(&mut db);
    // The days answer; the newest paper's full text arrives, the others'
    // get no answer (no route).
    let epmc = topic_days(
        &query,
        "2024-01-01",
        "2024-02-20",
        &[("2024-02-19", "PMC954")],
    );
    let pmcids = ["PMC950", "PMC951", "PMC952", "PMC953"];
    epmc.set(
        &europepmc_url(&query, "2024-02-18"),
        200,
        europepmc_page(&pmcids, "2024-02-18"),
    );
    let p = topic_pipeline(tmp.path(), &epmc);
    let stop = AtomicBool::new(false);
    let mut lines: Vec<bml_library::Progress> = Vec::new();
    let report = update_topic(&p, &mut db, &stop, &mut |line| lines.push(line));
    assert!(report.stopped_early(), "{report:?}");
    assert_eq!(
        report.fulltext.as_ref().map(|f| &f.end),
        Some(&bml_library::fulltext::FulltextEnd::NoNetwork),
        "{report:?}"
    );
    assert!(
        lines.iter().any(|l| l.message.contains("internet")),
        "{lines:#?}"
    );
    // The rounds after the first are not started.
    assert!(!epmc
        .seen()
        .lock()
        .unwrap()
        .contains(&europepmc_url(&query, "2024-02-13")));
    // The abstracts that arrived are searchable, and so is the full text
    // that arrived before the network went; no paper is charged a lasting
    // failure, and the one in flight is left untried.
    assert_eq!(
        scalar_i64(
            &mut db,
            "SELECT count(*) FROM publication_index WHERE status = 'complete'"
        ),
        pmcids.len() as i64 + 1
    );
    let converter: String = db
        .query_one(
            "SELECT i.converter_version FROM publication_index i \
             JOIN publications p ON p.id = i.publication_id WHERE p.pmcid = 'PMC954'",
            &[],
        )
        .unwrap()
        .get(0);
    assert!(converter.starts_with("jats-"), "{converter}");
    assert_eq!(
        scalar_i64(&mut db, "SELECT count(*) FROM publication_fulltext"),
        i64::from(NO_ANSWER_LIMIT - 1) + 1
    );
    assert_eq!(
        scalar_i64(
            &mut db,
            "SELECT count(*) FROM publication_fulltext WHERE last_error_kind = 'lasting'"
        ),
        0
    );
    assert_eq!(
        scalar_i64(
            &mut db,
            "SELECT count(*) FROM library_state WHERE last_update_at IS NOT NULL"
        ),
        0
    );
}

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn status_counts_papers_with_no_full_text_link_apart() {
    let _g = common::serial();
    let tmp = tempfile::tempdir().unwrap();
    let Some((_s, mut db)) = server(tmp.path()) else {
        return;
    };
    stroke_library(&mut db);
    europepmc_paper(&mut db, "PMC960");
    let linkless = europepmc_paper(&mut db, "PMC961");
    db.execute(
        "DELETE FROM fulltext_sources WHERE publication_id = $1",
        &[&linkless],
    )
    .unwrap();
    let cache = FullTextCache {
        cache_dir: tmp.path().join("documents"),
    };
    let status = bml_library::status::library_status(&mut db, &cache).unwrap();
    assert_eq!((status.not_tried, status.no_link), (1, 1), "{status:?}");
    // Once the linked paper is tried, nothing is left to try.
    let web = FakeHttp::new().route(&europepmc_xml_url("PMC960"), 200, JATS);
    run_fulltext(
        &mut db,
        tmp.path(),
        &web,
        bml_library::FulltextSource::EuropePmc,
    );
    let status = bml_library::status::library_status(&mut db, &cache).unwrap();
    assert_eq!((status.not_tried, status.no_link), (0, 1), "{status:?}");
    // A tried paper whose link is gone later stays tried, not "none offered".
    db.execute(
        "DELETE FROM fulltext_sources WHERE url = $1",
        &[&europepmc_xml_url("PMC960")],
    )
    .unwrap();
    let status = bml_library::status::library_status(&mut db, &cache).unwrap();
    assert_eq!((status.not_tried, status.no_link), (0, 1), "{status:?}");
}

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn status_counts_medrxiv_papers_the_pipeline_never_fetches_as_none_offered() {
    let _g = common::serial();
    let tmp = tempfile::tempdir().unwrap();
    let Some((_s, mut db)) = server(tmp.path()) else {
        return;
    };
    paper(&mut db, &[1]);
    let linkless = other_paper(&mut db, "10.1101/2024.01.15.000002", "No link");
    // Links, but a DOI that is empty: next_paper never asks for it.
    let no_doi = other_paper(&mut db, "10.1101/2024.01.15.000003", "No DOI");
    add_version(&mut db, no_doi, 1);
    db.execute("UPDATE publications SET doi = '' WHERE id = $1", &[&no_doi])
        .unwrap();
    // Links, but no DOI at all.
    let null_doi = other_paper(&mut db, "10.1101/2024.01.15.000004", "Null DOI");
    add_version(&mut db, null_doi, 1);
    db.execute(
        "UPDATE publications SET doi = NULL WHERE id = $1",
        &[&null_doi],
    )
    .unwrap();
    // Only an html link, which the pipeline does not fetch.
    let html_only = other_paper(&mut db, "10.1101/2024.01.15.000005", "Html only");
    add_link(
        &mut db,
        html_only,
        "https://example.org/5.html",
        "html",
        Some("1"),
    );
    // xml links whose version is missing or not a whole number.
    let no_version = other_paper(&mut db, "10.1101/2024.01.15.000006", "No version");
    add_link(
        &mut db,
        no_version,
        "https://example.org/6.xml",
        "xml",
        None,
    );
    let bad_version = other_paper(&mut db, "10.1101/2024.01.15.000007", "Bad version");
    add_link(
        &mut db,
        bad_version,
        "https://example.org/7.xml",
        "xml",
        Some("1.2"),
    );
    let cache = FullTextCache {
        cache_dir: tmp.path().join("documents"),
    };
    let status = bml_library::status::library_status(&mut db, &cache).unwrap();
    assert_eq!((status.not_tried, status.no_link), (1, 6), "{status:?}");
    // Only the paper status calls "not tried yet" is the one fetched.
    let skipped = [
        linkless,
        no_doi,
        null_doi,
        html_only,
        no_version,
        bad_version,
    ];
    let next = bml_library::fulltext::next_paper(&mut db, bml_library::FulltextSource::Medrxiv)
        .unwrap()
        .unwrap();
    assert!(
        !skipped.iter().any(|&id| next.id == i64::from(id)),
        "{next:?}"
    );
}

/// A medRxiv link with any `format` and `version` (NULL when `None`).
fn add_link(db: &mut Client, id: i32, url: &str, format: &str, version: Option<&str>) {
    db.execute(
        "INSERT INTO fulltext_sources (publication_id, source, url, format, version, created_at) \
         VALUES ($1, 'medrxiv', $2, $3, $4, 'now')",
        &[&id, &url, &format, &version],
    )
    .unwrap();
}

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn status_counts_a_topic_librarys_days() {
    let _g = common::serial();
    let tmp = tempfile::tempdir().unwrap();
    let Some((_s, mut db)) = server(tmp.path()) else {
        return;
    };
    let query = stroke_library(&mut db);
    let epmc = topic_days(&query, "2024-02-19", "2024-02-20", &[]);
    let p = topic_pipeline(tmp.path(), &epmc);
    let stop = AtomicBool::new(false);
    let options = UpdateOptions {
        from: Some(NaiveDate::from_ymd_opt(2024, 2, 19).unwrap()),
        phases: only(Phase::Metadata),
        stop: &stop,
    };
    p.update(&mut db, &options, &mut |_| {});
    let status = bml_library::status::library_status(
        &mut db,
        &FullTextCache {
            cache_dir: tmp.path().join("documents"),
        },
    )
    .unwrap();
    assert_eq!(status.days_complete, 2, "{status:?}");
}

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn abstracts_are_searchable_before_full_text_and_the_first_round_is_short() {
    let _g = common::serial();
    let tmp = tempfile::tempdir().unwrap();
    let Some((_s, mut db)) = server(tmp.path()) else {
        return;
    };
    let query = stroke_library(&mut db);
    let epmc = topic_days(
        &query,
        "2024-01-01",
        "2024-02-20",
        &[("2024-02-18", "PMC800")],
    );
    let p = topic_pipeline(tmp.path(), &epmc);
    let stop = AtomicBool::new(false);
    let mut lines: Vec<bml_library::Progress> = Vec::new();
    update_topic(&p, &mut db, &stop, &mut |line| lines.push(line));
    // The first round is the newest week only.
    assert_eq!(
        lines
            .iter()
            .find(|l| l.phase == Phase::Metadata)
            .unwrap()
            .message,
        "2024-02-14 to 2024-02-20: 7 day(s), 1 new, 0 updated",
        "{lines:#?}"
    );
    // Its abstract is indexed before its full text is downloaded.
    let first_index = lines.iter().position(|l| l.phase == Phase::Index).unwrap();
    let first_text = lines
        .iter()
        .position(|l| l.phase == Phase::Fulltext)
        .unwrap();
    assert!(first_index < first_text, "{lines:#?}");
}

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn a_dead_network_ends_full_text_after_a_few_papers() {
    use bml_library::fulltext::FulltextEnd;
    use bml_library::polite_client::NO_ANSWER_LIMIT;
    let _g = common::serial();
    let tmp = tempfile::tempdir().unwrap();
    let Some((_s, mut db)) = server(tmp.path()) else {
        return;
    };
    for pmcid in ["PMC910", "PMC911", "PMC912", "PMC913", "PMC914"] {
        europepmc_paper(&mut db, pmcid);
    }
    // No routes: the network is down.
    let web = FakeHttp::new();
    let report = run_fulltext(
        &mut db,
        tmp.path(),
        &web,
        bml_library::FulltextSource::EuropePmc,
    );
    assert_eq!(report.end, FulltextEnd::NoNetwork, "{report:?}");
    assert_eq!(web.seen().lock().unwrap().len(), NO_ANSWER_LIMIT as usize);
    // The paper whose request gave up is not recorded; the others wait an hour.
    assert_eq!(
        scalar_i64(&mut db, "SELECT count(*) FROM publication_fulltext"),
        i64::from(NO_ANSWER_LIMIT - 1)
    );
    assert_eq!(
        scalar_i64(
            &mut db,
            "SELECT count(*) FROM publication_fulltext WHERE last_error_kind = 'lasting'"
        ),
        0
    );
}

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn a_topic_librarys_from_day_is_remembered() {
    let _g = common::serial();
    let tmp = tempfile::tempdir().unwrap();
    let Some((_s, mut db)) = server(tmp.path()) else {
        return;
    };
    let query = stroke_library(&mut db);
    let epmc = topic_days(&query, "2024-01-01", "2024-02-20", &[]);
    let p = topic_pipeline(tmp.path(), &epmc);
    let stop = AtomicBool::new(false);
    let from = |day: Option<&str>| UpdateOptions {
        from: day.map(|d| NaiveDate::parse_from_str(d, "%Y-%m-%d").unwrap()),
        phases: only(Phase::Metadata),
        stop: &stop,
    };
    p.update(&mut db, &from(Some("2024-02-10")), &mut |_| {});
    epmc.seen().lock().unwrap().clear();
    // A scheduled run passes no --from: the library keeps the day chosen.
    p.update(&mut db, &from(None), &mut |_| {});
    let seen = epmc.seen().lock().unwrap().clone();
    assert!(
        !seen.contains(&europepmc_url(&query, "2024-02-09")),
        "{seen:#?}"
    );
    assert!(
        !seen.contains(&europepmc_url(&query, "2024-01-01")),
        "{seen:#?}"
    );
}

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn offline_days_are_fetched_when_the_network_is_back() {
    let _g = common::serial();
    let tmp = tempfile::tempdir().unwrap();
    let Some((_s, mut db)) = server(tmp.path()) else {
        return;
    };
    let query = stroke_library(&mut db);
    let offline = FakeHttp::new();
    let stop = AtomicBool::new(false);
    update_topic(
        &topic_pipeline(tmp.path(), &offline),
        &mut db,
        &stop,
        &mut |_| {},
    );
    assert_eq!(
        scalar_i64(
            &mut db,
            "SELECT count(*) FROM download_days WHERE status = 'completed'"
        ),
        0
    );
    // The network is back.
    let online = topic_days(
        &query,
        "2024-01-01",
        "2024-02-20",
        &[("2024-02-18", "PMC950")],
    );
    let report = update_topic(
        &topic_pipeline(tmp.path(), &online),
        &mut db,
        &stop,
        &mut |_| {},
    );
    assert!(!report.failed() && !report.stopped_early(), "{report:?}");
    assert_eq!(
        scalar_i64(
            &mut db,
            "SELECT count(DISTINCT publication_id) FROM chunks WHERE kind = 'fulltext'"
        ),
        1
    );
}

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn a_captive_portal_reads_as_offline_after_one_round() {
    let _g = common::serial();
    let tmp = tempfile::tempdir().unwrap();
    let Some((_s, mut db)) = server(tmp.path()) else {
        return;
    };
    let query = stroke_library(&mut db);
    // Every day answers 200 with a hotel's sign-in page.
    let portal = FakeHttp::new();
    let mut day = NaiveDate::from_ymd_opt(2024, 1, 1).unwrap();
    while day <= NaiveDate::from_ymd_opt(2024, 2, 20).unwrap() {
        portal.set(
            &europepmc_url(&query, &day.to_string()),
            200,
            "<html>Sign in to the Wi-Fi</html>",
        );
        day = day.succ_opt().unwrap();
    }
    let stop = AtomicBool::new(false);
    let mut lines: Vec<bml_library::Progress> = Vec::new();
    let report = update_topic(
        &topic_pipeline(tmp.path(), &portal),
        &mut db,
        &stop,
        &mut |l| lines.push(l),
    );
    assert!(report.stopped_early(), "{report:?}");
    assert!(
        lines
            .iter()
            .any(|l| l.message == bml_library::WAITING_FOR_INTERNET),
        "{lines:#?}"
    );
    // The first round's week only, not every round back to 2024-01-01.
    assert!(portal.seen().lock().unwrap().len() <= 7);
}

#[test]
#[ignore = "needs BML_TEST_PG_BINDIR"]
fn one_bad_day_does_not_stop_the_update() {
    let _g = common::serial();
    let tmp = tempfile::tempdir().unwrap();
    let Some((_s, mut db)) = server(tmp.path()) else {
        return;
    };
    let query = stroke_library(&mut db);
    let epmc = topic_days(
        &query,
        "2024-01-01",
        "2024-02-20",
        &[("2024-01-10", "PMC960")],
    );
    // One day of the first round answers with an error body.
    epmc.set(
        &europepmc_url(&query, "2024-02-19"),
        200,
        r#"{"errMsg":"busy"}"#,
    );
    let stop = AtomicBool::new(false);
    let mut lines: Vec<bml_library::Progress> = Vec::new();
    let report = update_topic(
        &topic_pipeline(tmp.path(), &epmc),
        &mut db,
        &stop,
        &mut |l| lines.push(l),
    );
    assert!(
        lines
            .iter()
            .all(|l| l.message != bml_library::WAITING_FOR_INTERNET),
        "{lines:#?}"
    );
    assert!(report.failed(), "the bad day is reported");
    // The older rounds still ran.
    assert_eq!(
        scalar_i64(
            &mut db,
            "SELECT count(DISTINCT publication_id) FROM chunks WHERE kind = 'fulltext'"
        ),
        1
    );
}
