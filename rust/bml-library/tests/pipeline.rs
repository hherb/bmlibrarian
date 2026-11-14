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
    let due = bml_library::fulltext::next_paper(&mut db).unwrap().unwrap();
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
    assert!(bml_library::fulltext::next_paper(&mut db)
        .unwrap()
        .is_none());
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
    assert!(bml_library::fulltext::next_paper(&mut db)
        .unwrap()
        .is_some());
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
        bml_library::fulltext::next_paper(&mut db)
            .unwrap()
            .is_none(),
        "waits for retry_after"
    );
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
