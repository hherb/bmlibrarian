# Investor Demo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An app window that installs BMLibrarian, downloads a topic's
peer-reviewed open-access full texts from Europe PMC, indexes them and searches
them by meaning, plus a prepared depression & anxiety library, ready by
2026-11-23.

**Architecture:** A new `europepmc` day-by-day sync source in bmlib (Python and
Rust together) feeds a "topic library" in `bml-library`, which runs in rounds
(newest window first: metadata, full text, index). A new UI-free `bml-search`
crate does hybrid retrieval over the existing chunk tables. A new Tauri crate
`bml-app` is a thin front end over `bml-setup`, `bml-library` and `bml-search`.

**Tech Stack:** Rust 1.89 workspace (`rust/`), bmlib (Rust + Python, pinned by
git rev), PostgreSQL 18 + pgvector + pg_search, Tauri 2 with a static
HTML/CSS/JS front end, Europe PMC REST API.

**Spec:** `docs/superpowers/specs/2026-11-15-investor-demo-europepmc-design.md`
(builds on `docs/superpowers/specs/2026-11-11-installer-walking-skeleton-design.md`).

## Global Constraints

- Deadline: finished library built by **2026-11-20**, rehearsal by
  **2026-11-22**, meeting **2026-11-23**.
- bmlib additions land in **Python and Rust together**, with shared fixtures
  (the oracle pattern: `rust/oracle/*_cases.json` → `rust/oracle/dump_*.py` →
  `rust/bmlib/tests/data/*_expected.json` → a Rust test).
- bmlib's main checkout (`/Users/hherb/src/bmlib`) has someone's uncommitted
  work on `master`. Do bmlib work in a **new worktree** off `origin/master`;
  never touch that checkout's working tree.
- BMLibrarian may pin the **unmerged bmlib branch commit** (spec); re-pin to the
  merged commit after the meeting. The bmlib PR is still opened and reviewed.
- Golden rules: type hints / doc comments on everything, no magic numbers
  (named constants), errors shown in plain language, no inline styles (one
  stylesheet), relative units (`rem`/`em`), idempotent migrations, toasts not
  modal dialogs.
- Hermetic tests: no live Europe PMC, Ollama or model calls in `cargo test` or
  `pytest`; PostgreSQL tests are `#[ignore]` like the existing ones
  (`--include-ignored` with `BML_TEST_PG_BINDIR`).
- CI runs `cargo fmt --check`, `cargo clippy --all-targets -- -D warnings` and
  `cargo test` on macOS, Windows and Linux. `bml-app` is **not** a default
  workspace member, so CI never builds Tauri. Everything else must stay green
  on every runner.
- The medRxiv path keeps its behaviour and passes its existing tests.
- The demo topic query (spec goal 1, verbatim):
  `OPEN_ACCESS:Y AND HAS_FT:Y AND NOT SRC:PPR AND PUB_YEAR:[2021 TO 2026] AND (TITLE:"depression" OR ABSTRACT:"depression" OR TITLE:"anxiety disorder" OR ABSTRACT:"anxiety disorder") AND (PUB_TYPE:"Randomized Controlled Trial" OR PUB_TYPE:"Systematic Review" OR PUB_TYPE:"Meta-Analysis")`

## Review Focus

1. **A phone connection drops mid-download.** Expected: the paper or day in
   flight is retried later, nothing is recorded as permanently failed, and the
   app shows "waiting for the internet", not a failed step. Test in Task 6
   (`transport_error_leaves_paper_retryable`) and Task 7
   (`a_round_with_no_network_stops_cleanly`).
2. **Europe PMC answers 200 with an error body, or delivers fewer records than
   `hitCount` promised.** Expected: that day is `failed` and fetched again next
   run, never stored as complete. Test in Tasks 1 and 2 (`error_body_fails_day`,
   `short_walk_fails_day`).
3. **A paper's `fullTextXML` has no body or 404s.** Expected: the paper is kept
   abstract-only, its abstract is searchable, and it is not refetched every
   round. Test in Task 6 (`missing_body_is_abstract_only`).
4. **Search on an empty, whitespace-only or no-match query, or on an empty
   library.** Expected: a plain message, never an error or a panic. Test in
   Task 9 (`blank_query_returns_no_hits`, `empty_library_returns_no_hits`).
5. **The live install and the prepared library on one Mac.** Expected: an app
   started with config folder A never opens, locks or writes library B. Test in
   Task 12 (`config_dir_comes_from_env_then_default`), and checked by hand in
   Task 16.

---

## Part A: bmlib `europepmc` sync source

Work in a bmlib worktree:
`git -C /Users/hherb/src/bmlib worktree add ../bmlib-europepmc -b feat/europepmc-sync origin/master`.
Run Python commands with `env -u VIRTUAL_ENV` so BMLibrarian's venv is not used.

### Task 1: Python `fetch_europepmc` and its registration

**Files:**
- Modify: `bmlib/publications/fetchers/europepmc.py` (add the walker beside
  the existing `normalize`)
- Modify: `bmlib/publications/fetchers/registry.py` (register `europepmc`)
- Create: `tests/test_europepmc_fetcher.py`
- Modify: `CHANGELOG.md`

**Interfaces:**
- Produces:
  `fetch_europepmc(client, target_date: date, *, on_record: Callable[[FetchedRecord], None], on_progress: Callable[[SyncProgress], None] | None = None, query: str, email: str | None = None) -> FetchResult`
  with the same contract as `fetch_openalex`.
- Constants: `_SEARCH_URL = f"{EUROPEPMC_REST_BASE}/search"`,
  `_PAGE_SIZE = 1000`, `_RATE_LIMIT_SECONDS = 1.0`,
  `EUROPEPMC_SETTLE_DAYS = 14`, `_FIRST_CURSOR = "*"`.
- Registry: `SourceDescriptor(name="europepmc", display_name="Europe PMC", description="Europe PMC search (peer-reviewed and preprint records)", params=[SourceParam("query", "Europe PMC search, without a date clause", required=True), SourceParam("email", "Contact email sent to Europe PMC")], settle_days=EUROPEPMC_SETTLE_DAYS)`.

- [ ] **Step 1: Write the failing tests** in `tests/test_europepmc_fetcher.py`,
  using a mocked client in the style of `tests/test_openalex_fetcher.py`:
  - `test_query_gets_the_day_clause`: the first request's `query` param equals
    `'(<query>) AND FIRST_PDATE:[2024-03-05 TO 2024-03-05]'`, and has
    `resultType=core`, `format=json`, `pageSize=1000`, `cursorMark=*`.
  - `test_two_pages_follow_the_cursor`: page 1 (`hitCount` 3, two results,
    `nextCursorMark` "AoE1"), page 2 (one result, `nextCursorMark` "AoE1"
    again). Three records reach `on_record`, the second request carries
    `cursorMark=AoE1`, the walk stops, and the result is `completed` with
    3 records.
  - `test_unchanged_cursor_on_first_page_stops`: one page whose
    `nextCursorMark` equals the cursor sent ends the walk (bounded loop).
  - `error_body_fails_day`: an HTTP 200 body without `resultList` gives
    status `failed`, and the message names Europe PMC.
  - `short_walk_fails_day`: `hitCount` 5 with 2 records delivered and then an
    empty page gives `failed`.
  - `test_oa_record_has_fulltext_xml_source`: a hit with `pmcid` "PMC123" and
    `isOpenAccess` "Y" yields a `fulltext_sources` entry whose URL ends
    `/PMC123/fullTextXML` (this goes through the existing `normalize`).

- [ ] **Step 2: Run them to verify they fail.** Run:
  `env -u VIRTUAL_ENV uv run python -m pytest tests/test_europepmc_fetcher.py -v`.
  Expected: FAIL (`fetch_europepmc` not defined).

- [ ] **Step 3: Implement `fetch_europepmc` and register it.** Reuse
  `normalize` for every hit and bmlib's shared reconciliation
  (`_reconcile.py`, the same calls as OpenAlex). The promise is the first
  page's `hitCount`. Sleep `_RATE_LIMIT_SECONDS` between pages. Send `email`
  as the `email` query parameter when given.

- [ ] **Step 4: Run the tests to verify they pass**, then the whole suite.
  Run: `env -u VIRTUAL_ENV uv run python -m pytest tests/ -q`.
  Expected: all pass, including `tests/test_europepmc_normalizer.py` and the
  registry tests that list the sources.

- [ ] **Step 5: Add a `CHANGELOG.md` entry and commit.**
  `git commit -m "feat(publications): europepmc day-by-day sync source (Python)"`

### Task 2: Rust port and the shared oracle

**Files:**
- Modify: `rust/bmlib/src/publications/fetchers/europepmc.rs` (walker beside
  `normalize`)
- Modify: `rust/bmlib/src/publications/fetchers/registry.rs`
  (`builtin_descriptors` entry, and a `builtin_registry` arm)
- Create: `rust/oracle/europepmc_sync_cases.json`,
  `rust/oracle/dump_europepmc_sync.py`,
  `rust/bmlib/tests/data/europepmc_sync_expected.json`,
  `rust/bmlib/tests/europepmc_sync.rs`
- Modify: `rust/bmlib/CHANGELOG.md`

**Interfaces:**
- Consumes: Task 1's behaviour (the oracle cases are run through it).
- Produces: `pub struct EuropePmcFetcher { pub client: Arc<dyn HttpClient + Send + Sync> }`
  implementing `Fetcher`. It reads `request.config_value("query")` (required:
  a missing query is a `failed` outcome naming the parameter) and `"email"`.
  Constants as in Task 1: `SEARCH_URL`, `PAGE_SIZE: usize = 1000`,
  `RATE_LIMIT_SECONDS: f64 = 1.0`, `EUROPEPMC_SETTLE_DAYS`.

- [ ] **Step 1: Write the oracle cases.** Follow `openalex_cases.json` /
  `dump_openalex.py` / `tests/openalex.rs`. Cover the same scenarios as
  Task 1's tests (cursor follow, unchanged cursor, error body, short walk,
  OA record), plus a missing `query`.
- [ ] **Step 2: Generate the expected file from Python.** Run:
  `env -u VIRTUAL_ENV uv run python rust/oracle/dump_europepmc_sync.py`.
  Expected: `rust/bmlib/tests/data/europepmc_sync_expected.json` written.
- [ ] **Step 3: Write `tests/europepmc_sync.rs`** asserting that the Rust
  walker reproduces every expected case, and **run it to see it fail.** Run:
  `cd rust/bmlib && cargo test --test europepmc_sync`. Expected: FAIL (no
  `EuropePmcFetcher`).
- [ ] **Step 4: Implement `EuropePmcFetcher`** and register it under
  `"europepmc"` with the Task 1 descriptor values.
- [ ] **Step 5: Run the Rust tests.** Run:
  `cd rust/bmlib && cargo test && cargo clippy --all-targets -- -D warnings && cargo fmt --check`.
  Expected: all pass, including the test that checks `list_sources()`
  against `builtin_descriptors()`.
- [ ] **Step 6: Update the CHANGELOG, commit, push the branch and open the
  bmlib PR.** Confirm with the owner before the push (it is outward-facing).
  `git commit -m "feat(publications): europepmc sync source (Rust port, oracle)"`,
  then `git push -u origin feat/europepmc-sync` and `gh pr create`.

### Task 3: Pin BMLibrarian to the bmlib branch

**Files:**
- Modify: `rust/Cargo.toml:23` (`rev = "<feat/europepmc-sync head>"`)
- Modify: `rust/Cargo.lock` (by cargo)

- [ ] **Step 1: Change the rev and build.** Run:
  `cd rust && cargo build && cargo test`. Expected: builds; the existing
  tests pass unchanged.
- [ ] **Step 2: Commit.**
  `git commit -m "build(rust): pin bmlib to the europepmc sync branch"`

---

## Part B: topic libraries in `bml-library`

### Task 4: Topics, the library's source, migration 4

**Files:**
- Create: `rust/bml-library/src/topics.rs`
- Modify: `rust/bml-library/src/lib.rs` (`pub mod topics;`, new constants)
- Modify: `rust/bml-db/src/schema.rs` (migration 4)

**Interfaces:**
- Produces, in `topics.rs`:
  - `pub struct Topic { pub id: &'static str, pub name: &'static str, pub terms: &'static [&'static str], pub stored_count: u32 }`
  - `pub const TOPICS: &[Topic]` with exactly these four, in this order:
    `depression-anxiety` "Depression & anxiety" ["depression", "anxiety disorder"] 8372;
    `cardiology` "Heart failure & cardiology" ["heart failure", "atrial fibrillation", "myocardial infarction", "coronary artery disease"] 5513;
    `obesity-glp1` "Obesity & GLP-1 drugs" ["obesity", "GLP-1", "semaglutide", "tirzepatide"] 5058;
    `stroke` "Stroke" ["stroke"] 5391.
  - `pub fn topic(id: &str) -> Option<&'static Topic>`
  - `pub fn topic_query(topic: &Topic) -> String` (the filter + the terms, as
    in Global Constraints)
  - `pub fn count_url(topic: &Topic) -> String` and
    `pub fn parse_hit_count(body: &str) -> Option<u64>` (screen 4's live count)
  - `pub enum LibrarySource { Medrxiv, EuropePmc { topic_id: String, query: String } }`
  - `pub fn library_source(db: &mut dyn Db) -> Result<LibrarySource, PipelineError>`
  - `pub fn set_topic(db: &mut dyn Db, topic: &Topic) -> Result<(), PipelineError>`:
    records the topic. A library that already holds papers from another source
    or topic is refused, in plain words.
- In `lib.rs`: `pub const EUROPEPMC_SOURCE: &str = "europepmc";`,
  `pub const EUROPEPMC_FIRST_DAY: &str = "2021-01-01";`,
  `pub const EUROPEPMC_REQUEST_DELAY: Duration = Duration::from_secs(1);`,
  `pub const EUROPEPMC_ROUND_DAYS: u64 = 30;`.
- Migration 4 `library_topic`: `ALTER TABLE library_state ADD COLUMN IF NOT EXISTS topic_id TEXT`,
  `... ADD COLUMN IF NOT EXISTS topic_query TEXT`. A NULL `topic_id` means
  medRxiv.

- [ ] **Step 1: Write the failing unit tests** in `topics.rs`:
  - `depression_query_is_the_spec_query`: `topic_query(topic("depression-anxiety").unwrap())`
    equals the Global Constraints string exactly.
  - `ids_are_unique_and_topics_have_terms`.
  - `parse_hit_count_reads_the_field` (`{"hitCount":8372,...}` gives
    `Some(8372)`; malformed JSON or a missing field gives `None`).
  - `count_url_asks_for_one_record` (contains `pageSize=1` and
    `format=json`, the query URL-encoded).
  - `#[ignore]` PG test `library_without_topic_reads_medrxiv`, and
    `set_topic_refuses_another_topic`, in the style of `tests/pipeline.rs`.
- [ ] **Step 2: Run them to verify they fail.**
  `cd rust && cargo test -p bml-library topics`. Expected: FAIL.
- [ ] **Step 3: Implement** `topics.rs` and migration 4. Extend
  `migration_versions_are_unique_and_ascending`'s list implicitly by adding
  `Migration::new(4, "library_topic", library_topic)`.
- [ ] **Step 4: Run the tests.** `cargo test -p bml-library -p bml-db`, then
  with `BML_TEST_PG_BINDIR` set: `cargo test -p bml-library -p bml-db -- --include-ignored`.
  Expected: pass.
- [ ] **Step 5: Commit.** `git commit -m "feat(bml-library): topic presets and the library's source (migration 4)"`

### Task 5: Metadata for a window and a source

**Files:**
- Modify: `rust/bml-library/src/metadata.rs`

**Interfaces:**
- Consumes: `EUROPEPMC_SOURCE`, `LibrarySource` (Task 4).
- Produces:
  `pub fn run_window(db: &mut dyn Db, client: Arc<PoliteClient>, source: &str, config: &BTreeMap<String, BTreeMap<String, String>>, from: NaiveDate, to: NaiveDate, stop: &AtomicBool, clock: &dyn Fn() -> DateTime<Utc>, progress: &mut dyn FnMut(Progress)) -> Result<MetadataReport, PipelineError>`.
  The existing `run` keeps its signature and calls `run_window` per 30-day
  window, so the medRxiv behaviour is unchanged.

- [ ] **Step 1: Write the failing test** `europepmc_window_sends_the_query`
  (in `tests/pipeline.rs`, `#[ignore]` PG): with `FakeHttp` scripted with a
  one-record Europe PMC page, `run_window` for one day stores one publication
  with source `europepmc`. The recorded request's query contains the topic
  query and `FIRST_PDATE`.
- [ ] **Step 2: Run it to verify it fails.** Expected: FAIL (`run_window`
  missing).
- [ ] **Step 3: Implement `run_window`**, moving the window body of `run`
  into it unchanged.
- [ ] **Step 4: Run the bml-library tests,** including the ignored ones.
  Expected: the new test and every existing medRxiv test pass.
- [ ] **Step 5: Commit.** `git commit -m "refactor(bml-library): metadata per window and source"`

### Task 6: Full text for Europe PMC papers

**Files:**
- Modify: `rust/bml-library/src/fulltext.rs`
- Create: `rust/bml-library/tests/fixtures/europepmc_article.xml` (a small,
  hand-made JATS article with a `<body>`) and
  `rust/bml-library/tests/fixtures/europepmc_no_body.xml`
- Modify: `rust/bml-library/tests/pipeline.rs`

**Interfaces:**
- Consumes: `EUROPEPMC_SOURCE` (Task 4).
- Produces: `fulltext::run` gains one parameter, `source: &str`
  (`MEDRXIV_SERVER` or `EUROPEPMC_SOURCE`), which selects the papers it
  picks. The existing caller in `update` passes `MEDRXIV_SERVER`. Internally,
  `next_paper(db, source)` gains the Europe PMC case: a `fulltext_sources`
  row with `source = 'europepmc'` and `format = 'xml'`, version treated as 1,
  newest `publication_date` first, with the same `publication_fulltext`
  retry/attempts rules. The `FullTextService` request has `pmc_id` set from
  `publications.pmc_id`, and `identifier = <pmc_id>`.

- [ ] **Step 1: Write the failing tests** (`#[ignore]` PG, `FakeHttp`):
  - `europepmc_paper_gets_full_text`: a held `europepmc` paper, with
    `fullTextXML` serving the fixture, ends with form `xml`. Exactly one
    request goes to `…/PMC…/fullTextXML`, and none to medRxiv.
  - `missing_body_is_abstract_only`: the no-body fixture gives form
    `abstract`. A second `run` makes no request for it (before its
    `retry_after`).
  - `transport_error_leaves_paper_retryable`: a transport error leaves the
    paper without a lasting failure, with a `retry_after` set.
  - `source_selects_the_papers`: with one medRxiv and one Europe PMC paper
    held, `run(…, EUROPEPMC_SOURCE, …)` requests only the Europe PMC paper,
    and the medRxiv run only the medRxiv one.
- [ ] **Step 2: Run them to verify they fail.**
- [ ] **Step 3: Implement the Europe PMC case** in `next_paper`, `sources`
  and the request building. Keep `classify` shared.
- [ ] **Step 4: Run all bml-library tests** (with `--include-ignored`).
  Expected: pass, including every existing full-text test.
- [ ] **Step 5: Commit.** `git commit -m "feat(bml-library): Europe PMC full text through Tier 1a"`

### Task 7: Rounds, newest first

**Files:**
- Modify: `rust/bml-library/src/lib.rs` (`Pipeline` and `update`)
- Modify: `rust/bml-library/tests/pipeline.rs`
- Modify: `doc/developers/library_pipeline.md`, `doc/users/library_updates_guide.md`

**Interfaces:**
- Consumes: `library_source`, `topic_query`, `run_window`, `fulltext::run`,
  `index::run`.
- Produces: `Pipeline` gains `pub europepmc: Arc<dyn HttpClient + Send + Sync>`
  and `pub europepmc_delay: Duration` (`Pipeline::new` sets them to the real
  client and `EUROPEPMC_REQUEST_DELAY`). For an `EuropePmc` library, `update`
  loops windows of `EUROPEPMC_ROUND_DAYS`, from today back to
  `EUROPEPMC_FIRST_DAY`. Each round runs `run_window` (query config
  `{"europepmc": {"query": …}}`), then `fulltext::run`, then `index::run`,
  each when its phase is enabled. `stop` is checked between rounds.
  `last_update_at` is stamped as today, only for a complete update. A medRxiv
  library runs exactly as before.

- [ ] **Step 1: Write the failing tests** (`#[ignore]` PG, `FakeHttp`, stub
  embedder):
  - `first_round_is_searchable_before_the_second_starts`: two windows of
    scripted papers. Assert, from the recorded request order and the
    `chunks` rows, that the newest window's papers have chunks before the
    first request for the older window is sent.
  - `stop_between_rounds_resumes`: set `stop` after round one; a second
    `update` fetches no day of round one again (bmlib's ledger) and completes
    round two.
  - `a_round_with_no_network_stops_cleanly`: transport errors in every
    request give a report with failures and no lasting full-text failure;
    `last_update_at` is not stamped.
  - `medrxiv_library_order_is_unchanged`: the existing order test still
    passes. Add one if none asserts the order.
- [ ] **Step 2: Run them to verify they fail.**
- [ ] **Step 3: Implement the rounds** in `update`, reusing the existing
  `index` closure.
- [ ] **Step 4: Run the whole workspace:** `cd rust && cargo test && cargo clippy --all-targets -- -D warnings && cargo fmt --check`,
  then `cargo test -p bml-library -- --include-ignored`. Expected: pass.
- [ ] **Step 5: Update both docs** (rounds; topic libraries; that medRxiv is
  unchanged), reflowed to the existing width, and **commit.**
  `git commit -m "feat(bml-library): topic libraries update in rounds, newest first"`

### Task 8: `bml library update --topic`, then measure and start the build

**Files:**
- Modify: `rust/bml-cli/src/library.rs`
- Modify: `HANDOVER.md` (measurements)

**Interfaces:**
- Consumes: `topics::{topic, set_topic, TOPICS}`.
- Produces: `bml library update --topic <ID>`. On a library with no topic and
  no papers it records the topic. On a library with that topic it is a no-op.
  On anything else it gives a plain-language refusal, exit 1. An unknown ID
  lists the valid IDs. `bml library status` prints the topic's name.

- [ ] **Step 1: Write the failing CLI tests:** `unknown_topic_lists_ids`,
  and `status_shows_topic` (`#[ignore]` PG).
- [ ] **Step 2: Run them to verify they fail. Step 3: Implement. Step 4: Run
  them to verify they pass.**
- [ ] **Step 5: Commit.** `git commit -m "feat(bml-cli): library update --topic"`
- [ ] **Step 6: Set up the prepared library (manual, on the demo Mac).** Run:
  `bml --config-dir ~/.bml-demo setup --library-dir ~/BMLibrarian-demo --skip autostart`,
  then `bml --config-dir ~/.bml-demo library schedule manual`.
  Expected: exit 0; `bml --config-dir ~/.bml-demo server status` exits 0.
- [ ] **Step 7: Measure.** Run
  `bml --config-dir ~/.bml-demo library update --topic depression-anxiety`,
  tee the output to a scratchpad file, and stop it with Ctrl-C after about
  200 papers. Record in HANDOVER: seconds per Europe PMC request, full-text
  success rate, chunks per paper, and embedding throughput. Compute whether
  8,372 papers finish by 2026-11-20. If they won't, narrow the year range in
  the topic query rather than the publication types, and record that.
- [ ] **Step 8: Start the full build** (the same command, run again; it
  resumes). Leave it running. Check `library status` daily.

---

## Part C: search

### Task 9: `bml-search` crate

**Files:**
- Create: `rust/bml-search/Cargo.toml`, `rust/bml-search/src/lib.rs`,
  `rust/bml-search/src/fusion.rs`
- Modify: `rust/Cargo.toml` (add to `members` and to a new `default-members`
  list holding every member except `bml-app`)
- Modify: `rust/bml-library/src/index.rs` (expose the reader text)
- Create: `doc/developers/search.md`

**Interfaces:**
- Consumes: `bml_library::index::ChunkEmbedder`,
  `bml_db::schema::{lexical_index, LexicalIndex}` (BM25 or tsvector), the
  `chunks`, `chunk_embeddings` and `publications` tables.
- Produces:
  - `pub struct SearchHit { pub publication_id: i64, pub title: String, pub journal: Option<String>, pub year: Option<i32>, pub authors: Vec<String>, pub passage: String, pub score: f64 }`
  - `pub fn search(db: &mut dyn Db, embedder: &mut dyn ChunkEmbedder, query: &str, limit: usize) -> Result<Vec<SearchHit>, SearchError>`
  - `pub enum SearchError` (plain-language `Display`)
  - in `fusion.rs`, pure functions:
    `pub fn fuse(vector: &[i64], lexical: &[i64]) -> Vec<(i64, f64)>` (chunk
    ids in rank order, highest score first) and
    `pub fn best_per_paper(scored: &[(i64, f64)], paper_of: &HashMap<i64, i64>) -> Vec<(i64, i64, f64)>`
    (publication, best chunk, score).
  - Constants: `VECTOR_K: usize = 100`, `LEXICAL_K: usize = 100`,
    `RRF_K: f64 = 60.0`, `VECTOR_WEIGHT: f64 = 2.0`,
    `LEXICAL_WEIGHT: f64 = 1.0`, and `QUERY_PREFIX`. Take that prefix from the
    Snowflake Arctic Embed L v2 model card, and pin the source in a comment.
  - In `bml-library`:
    `pub fn paper_text(cache: &FullTextCache, db: &mut dyn Db, publication_id: i64) -> Result<PaperText, PipelineError>`
    with `pub struct PaperText { pub title: String, pub meta: String, pub text: String }`,
    built on the existing private `canonical` (the abstract when only that
    is held).

- [ ] **Step 1: Write the failing unit tests** in `fusion.rs`:
  - `vector_rank_counts_double`: a chunk first in vectors only beats a chunk
    first in lexical only.
  - `both_lists_beat_one`.
  - `best_per_paper_keeps_one_row_per_paper`, ordered by score.
  - In `lib.rs`: `blank_query_returns_no_hits` (`""` and `"   "` give
    `Ok(vec![])` without calling the embedder).
  - `#[ignore]` PG tests: `empty_library_returns_no_hits`,
    `finds_the_paper_by_meaning` (stub embedder, two papers), and
    `works_with_tsvector_fallback`.
- [ ] **Step 2: Run them to verify they fail.**
  `cd rust && cargo test -p bml-search`. Expected: FAIL.
- [ ] **Step 3: Implement.** Use one SQL query per list (the HNSW
  `<=>` ordering for vectors, the BM25 or tsvector query that
  `LexicalIndex` documents for words), then fuse and group in Rust, then one
  query for the hits' metadata.
- [ ] **Step 4: Run them, and the whole workspace's gates.** Expected: pass.
- [ ] **Step 5: Commit.** `git commit -m "feat(bml-search): hybrid search with weighted RRF, one hit per paper"`

### Task 10: `bml search`, and a result-quality check

**Files:**
- Create: `rust/bml-cli/src/search.rs`
- Modify: `rust/bml-cli/src/main.rs`
- Modify: `rust/bml-search/src/lib.rs` (only if the check below needs a
  filter)

**Interfaces:**
- Consumes: `bml_search::search`, `bml_library::index::load_model_embedder`.
- Produces: `bml [--config-dir DIR] search "<query>" [--limit N]`
  (`DEFAULT_LIMIT: usize = 10`). It prints title, journal, year and the passage,
  one block per hit. Exit 0 on hits or none; exit 2 when not set up.

- [ ] **Step 1: Write `search_without_setup_exits_2`** (CLI test in the
  existing style). Run it to see it fail, implement, run it to see it pass,
  then commit: `git commit -m "feat(bml-cli): bml search"`.
- [ ] **Step 2: Check quality by hand** on the growing prepared library with
  these questions, saving the output to a scratchpad file:
  "does exercise reduce depressive symptoms", "SSRIs versus CBT for
  generalised anxiety", "ketamine for treatment-resistant depression",
  "digital mental health apps for anxiety", "postpartum depression
  screening", "depression in older adults and dementia risk",
  "psilocybin depression trial", "mindfulness for anxiety in students".
  Expected: each top 5 is on topic, and no passage is a reference list,
  affiliation or funding statement.
- [ ] **Step 3: Only if Step 2 shows boilerplate,** add
  `pub fn is_boilerplate(passage: &str) -> bool` in `bml-search` with tests
  (`reference_list_is_boilerplate`, `funding_statement_is_boilerplate`,
  `findings_are_not_boilerplate`). Exclude such chunks from both lists, then
  rerun Step 2 and commit.

---

## Part D: the app (`bml-app`, Tauri 2, macOS)

### Task 11: Shared app logic in a UI-free module

**Files:**
- Create: `rust/bml-app/Cargo.toml`, `rust/bml-app/build.rs`,
  `rust/bml-app/tauri.conf.json`, `rust/bml-app/src/main.rs`,
  `rust/bml-app/src/state.rs`, `rust/bml-app/ui/index.html`,
  `rust/bml-app/ui/app.css`, `rust/bml-app/ui/app.js`
- Modify: `rust/Cargo.toml` (add `bml-app` to `members` only)

**Interfaces:**
- Consumes: `bml_pgserver::state::{resolve_config_dir, CONFIG_DIR_ENV}`, the
  library record (`bml-library.json`), `bml_library::status::library_status`.
- Produces, in `state.rs` (plain Rust, unit-testable):
  - `pub fn config_dir() -> Result<PathBuf, String>`: the `CONFIG_DIR_ENV`
    variable, else the default, through `resolve_config_dir`.
  - `pub enum StartScreen { Welcome, Search }` and
    `pub fn start_screen(config_dir: &Path) -> StartScreen` (`Search` when
    setup has recorded a library).
- Tauri 2, latest 2.x, with `frontendDist: "ui"` and no Node build step. One
  window titled "BMLibrarian".

- [ ] **Step 1: Write the failing tests** in `state.rs`:
  `config_dir_comes_from_env_then_default`, `fresh_config_starts_at_welcome`,
  `recorded_library_starts_at_search` (temp folders).
- [ ] **Step 2: Run them to verify they fail.** `cd rust && cargo test -p bml-app`.
- [ ] **Step 3: Implement `state.rs`; scaffold the window** that shows
  "Welcome" or "Search" per `start_screen`. One stylesheet, `rem` units, no
  `style=` attributes.
- [ ] **Step 4: Run the tests; build and open the app.**
  `cargo test -p bml-app && cargo run -p bml-app`. Expected: tests pass; a
  window opens on the right screen. Confirm `cargo test` at `rust/` still does
  not build `bml-app`.
- [ ] **Step 5: Commit.** `git commit -m "feat(bml-app): Tauri shell and start screen"`

### Task 12: Screen 6 (search) and screen 5 (building)

**Files:**
- Create: `rust/bml-app/src/library_worker.rs`, `rust/bml-app/src/commands.rs`
- Modify: `rust/bml-app/ui/*`

**Interfaces:**
- Consumes: `bml_search::search`, `bml_library::{paper_text, Pipeline, try_lock_worker}`,
  `bml_library::status::library_status`, `bml_pgserver` start (when the
  library's server is not running, start it, as `bml server start` does).
- Produces, as Tauri commands:
  `search(query: String) -> Result<Vec<SearchHit>, String>`,
  `open_paper(id: i64) -> Result<PaperText, String>`,
  `start_update() -> Result<(), String>`, `pause_update()`, and
  `library_counts() -> Result<LibraryCounts, String>`, where
  `LibraryCounts { found, full_text, abstract_only, searchable }` is mapped
  from `LibraryStatus`.
  The event `"library-progress"` carries `{ phase, message }`.
  `library_worker.rs` runs `Pipeline::update` on its own thread, sharing one
  `AtomicBool` stop flag. A held worker lock is shown as "an update is
  already running", not as an error.

- [ ] **Step 1: Write the failing tests** for the pure mapping
  `counts_from_status` and for `progress_line(&Progress) -> String`
  (plain-language, one line), including
  `offline_failure_reads_waiting_for_internet`: a round that failed on
  transport errors reads "Waiting for the internet. Downloading carries on
  when it's back."
- [ ] **Step 2: Run them to verify they fail. Step 3: Implement** the
  commands, the worker and the two screens:
  - Screen 6: a search box; result cards (title, journal · year, passage);
    clicking a card opens the reader view (title, meta, text) with a Back
    button. "No papers match yet" for empty results. Screen 5's progress line
    is at the top while an update runs.
  - Screen 5: counts, a time estimate (remaining papers × measured seconds
    per paper from Task 8, as a named constant), [Pause], and "You can close
    this window. Next time it carries on where it stopped." Closing the window
    sets `stop`.
  - Errors are toasts, never `alert()`.
- [ ] **Step 4: Run the tests, then try it by hand** with
  `BML_CONFIG_DIR=~/.bml-demo cargo run -p bml-app` (use whatever
  `CONFIG_DIR_ENV` names) against the prepared library. Expected: searches
  return cards; a paper opens; Pause stops after the paper in flight.
- [ ] **Step 5: Commit.** `git commit -m "feat(bml-app): search and library progress screens"`

### Task 13: Screens 1–4 (welcome, folder, installing, topic)

**Files:**
- Create: `rust/bml-app/src/setup_worker.rs`
- Modify: `rust/bml-app/src/commands.rs`, `rust/bml-app/ui/*`

**Interfaces:**
- Consumes: `bml_setup::{run_setup, SetupPlan, StepEvent, StepOutcome}`,
  `bml_setup::hardware::free_space_at`,
  `bml_library::topics::{TOPICS, count_url, parse_hit_count, set_topic}`.
- Produces: commands `library_folder() -> FolderInfo { path, free_bytes }`,
  `start_setup()`, `topic_counts() -> Vec<TopicCount { id, name, count, live: bool }>`
  (each count fetched with `TOPIC_COUNT_TIMEOUT: Duration = Duration::from_secs(5)`,
  falling back to `stored_count` with `live: false`),
  `choose_topic(id: String, schedule: Schedule)`. Event `"setup-step"` carries
  one `StepEvent`. `Schedule` maps onto the existing `library schedule`
  options (weekly is the default).

- [ ] **Step 1: Write the failing tests:** `step_line` (pure: `StepEvent` →
  a status line), `topic_counts_fall_back_when_offline` (a client that times
  out gives the stored counts with `live: false`).
- [ ] **Step 2: Run them to verify they fail. Step 3: Implement:**
  - Screen 1: what will happen, "no administrator password needed".
  - Screen 2: `~/BMLibrarian`, its free space, and a rough size estimate for
    the largest preset (`stored_count` × `MB_PER_PAPER`, a named constant
    from Task 8's measurement). Nothing to choose.
  - Screen 3: one live line per step; "Try again" on a failed step; hardware
    warnings as toasts.
  - Screen 4: four topic radio buttons with counts, "Depression & anxiety"
    preselected; the schedule choice; [Start downloading] runs `set_topic`,
    then the schedule, then `start_update`, then shows screen 5.
- [ ] **Step 4: Run the tests, then do a full run by hand** with a temporary
  config folder and library folder. Expected: welcome → search with papers
  arriving, no terminal involved.
- [ ] **Step 5: Commit.** `git commit -m "feat(bml-app): welcome, folder, installing and topic screens"`

### Task 14: Docs for the app

**Files:**
- Create: `doc/users/bmlibrarian_app_guide.md`,
  `doc/developers/bml_app.md`
- Modify: `HANDOVER.md`, `ROADMAP.md`, `CLAUDE.md` (Development Commands:
  `bml search`, `library update --topic`, `cargo run -p bml-app`)

- [ ] **Step 1: Write the docs** (each screen; the config-folder variable; the
  two-install rule), reflowed to the files' width.
- [ ] **Step 2: Commit.** `git commit -m "docs: BMLibrarian app, topic libraries, search"`

---

## Part E: the demo

### Task 15: Demo runbook

**Files:**
- Create: `doc/users/investor_demo_runbook.md`

- [ ] **Step 1: Write the runbook.** Cover:
  - Before the meeting: the prepared library complete; the default config
    and library folders empty; copy `~/.bml-demo/models/` and
    `~/.bml-demo/pgdist/` into the default config folder; phone hotspot
    tested.
  - Order on the day: prepared library first (search the eight Task 10
    questions), then the live install with the default config folder.
  - Fallbacks: no network → stay on the prepared library.
  - Afterwards: how to remove the live install.
- [ ] **Step 2: Commit.** `git commit -m "docs: investor demo runbook"`

### Task 16: Rehearsal (manual, by 2026-11-22)

- [ ] **Step 1: Follow the runbook end to end on the demo Mac,** with the
  prepared library's database running. Expected: the live install reaches
  search with its first full texts within minutes. Afterwards, the prepared
  library's `bml --config-dir ~/.bml-demo library status` and `server status`
  are unchanged, and its login items are untouched (it has none).
- [ ] **Step 2: Rehearse once on the phone hotspot.** Expected: slow is fine;
  no failed step, no frozen window.
- [ ] **Step 3: Record what you found in HANDOVER and fix** anything that
  breaks an anti-goal. Commit.
