# Installer walking skeleton: from double-click to a searchable medRxiv library

**Date:** 2026-11-11
**Status:** Draft (design), awaiting approval
**Builds on:** `docs/superpowers/specs/2026-11-07-one-click-installer-design.md`
(the "2026-11-07 spec"). Its goals, anti-goals, constraints and decisions still
hold unless this document says otherwise. Pieces 1–3 of that spec are done
(`bml-pgserver`, `bml-setup`, `bml setup`); this document covers the rest of
piece 2 (portable binaries) and pieces 4–5. It also pulls a thin slice of the
Rust plan's Phases B and C forward (`doc/planning/rust/implementation_plan.md`).

## Intent

A person with limited computer skills downloads one file on a Mac,
double-clicks it, and ends up with the basic infrastructure for the future Rust
BMLibrarian:

- a private PostgreSQL 18 with pgvector and pg_search
- a library folder holding their downloaded papers
- medRxiv downloaded, embedded and indexed
- a minimal search screen to show that it all works

Today `bml setup` can do the server, Ollama, models and embedding model, but
only when pointed at PostgreSQL binaries already on the machine
(`--pg-bindir`), and only from a terminal. Nothing in Rust downloads,
stores, embeds or searches papers yet.

The search screen is a **walking skeleton for testing**: the smallest thing
that proves the pipeline end to end. The real search UI comes later and should
be able to grow out of it.

The owner wants the Rust version to **lean heavily on the bmlib Rust library**
(`../bmlib/rust/bmlib`) wherever possible. Most of this milestone is wiring
bmlib together, not new code.

## Success: the Mac trial

The first user trial is on a Mac. It succeeds when, on a Mac with no
PostgreSQL and no Ollama:

1. The owner's signed and notarised `.dmg` opens without a Gatekeeper warning.
2. The wizard installs everything with no admin password and no terminal.
3. The user chooses "papers from date X onwards", the download starts, the
   user closes the app mid-way, reopens it, and it carries on where it stopped.
4. When it finishes, the summary shows how many papers are stored, how many
   have full text (by form: JATS XML, PDF, HTML) and how many are abstract
   only, and all are indexed.
5. A test search returns relevant papers. Clicking one opens the stored paper.
6. The scheduled update is registered and, when it fires, fetches new
   preprints without the app being open.
7. The user's existing Python BMLibrarian configuration is untouched (2026-11-07 spec anti-goal).

The final app stays multi-platform. Windows and Linux builds come out of CI
in this milestone but are verified by hand later (as with #397).

## The wizard (approved wireframes)

The owner approved this flow from wireframes
(`.superpowers/brainstorm/.../wizard-flow.html`, not committed):

1. **Welcome.** What will happen, in plain words; "no administrator password
   needed". Button: Start.
2. **Where your library lives.** One folder for the papers and their database;
   "Choose…" picks another folder on the internal disk (external disks are a
   follow-up, see B). Shows free space and a rough estimate of what all of
   medRxiv with full text needs.
3. **Installing.** The existing `bml-setup` steps, each with a live status line
   (checked this Mac, private database, starts at login, AI engine, language
   models, search model). Hardware warnings appear as toasts, not modal
   dialogs (owner preference). A failed step shows a plain-language reason and
   "Try again".
4. **Your medRxiv library.**
   - Which papers: "All of medRxiv" or "Only papers from <date> onwards".
   - With "All of medRxiv": two optional fields for the user's own AWS access
     keys, with one plain-language line. Faster bulk download needs your own
     Amazon account, Amazon bills you for it (estimate shown), and without
     keys the papers download one by one. There is no guided AWS account
     setup (owner: "much, much later").
   - Keep it up to date: "Every week" (default), "Every <n> days", or "Only
     when I ask".
   - Button: Start downloading.
5. **Building your library.** Counts: papers found, downloaded (full text split
   by XML / PDF / web page, plus abstract only), ready to search; a time
   estimate. "You can close this window. Next time it carries on where it
   stopped." Button: Pause.
6. **Search** (walking skeleton). Query box and a results list: title,
   authors, date, and whether we hold full text (which form) or the abstract
   only. Usable while the library is still filling. Clicking a result opens the
   stored paper.

Re-opening the app after setup finished goes straight to screen 6. While a
download is still unfinished, screen 6 shows screen 5's progress line too.
"Only when I ask" needs an "Update now" control somewhere on screen 6.

## Goals

### A. Bundled PostgreSQL (removes `--pg-bindir`)

Sourcing, researched and chosen 2026-11-11 (owner asked for "the most
reliable and sustainable" option and approved this one):

| Piece | Source | Notes |
|---|---|---|
| PostgreSQL 18.6 | [theseus-rs/postgresql-binaries](https://github.com/theseus-rs/postgresql-binaries) release `18.6.1` | Relocatable (`@loader_path` on macOS), self-contained libraries, ships `pg_config` and server headers. Each tarball has a `.sha256` and a GitHub build-provenance attestation (`gh attestation verify … --repo theseus-rs/postgresql-binaries`; verified by hand 2026-11-11, with a negative control). `build-manifest.json` records the upstream tag and commit (`REL_18_6`, `724edf9b…`) and configure flags. PostgreSQL licence. |
| pgvector 0.8.7 | Built from source (tag `v0.8.7`, pinned by commit) in our CI against that PostgreSQL | pgvector publishes no binaries. `make PG_CONFIG=…` on macOS/Linux, `nmake /F Makefile.win` on Windows. ≥ 0.8.1 is required for `halfvec`. |
| pg_search 0.26.6 | ParadeDB's release assets: macOS `pg_search-pg18-0.26.6.pkg` (the Postgres.app package), Linux `postgresql-18-pg-search_0.26.6-1PARADEDB-bookworm_{amd64,arm64}.deb` | Each asset has a cosign bundle. The macOS `pg_search.dylib` is arm64-only, minimum macOS 11, links only system libraries (checked with `otool -L`), so it loads into any PostgreSQL 18 build. AGPL-3.0: releases link the exact source (2026-11-07 spec). |

Targets and what they get:

| Target | PostgreSQL + pgvector | pg_search |
|---|---|---|
| `aarch64-apple-darwin` (trial) | yes | yes |
| `x86_64-apple-darwin` | yes | **no**: ParadeDB ships no Intel-Mac build; uses the built-in text-search fallback, like Windows |
| `x86_64-pc-windows-msvc` | yes | no (2026-11-07 spec) |
| `x86_64-unknown-linux-gnu`, `aarch64-unknown-linux-gnu` | yes | yes |

Rejected: building pg_search ourselves with pgrx (a heavy toolchain to keep
current; ParadeDB's signed builds exist), Zonky's embedded binaries (no
extensions), EDB (Windows installers only), Homebrew bottles (hard-coded
paths), repackaging Postgres.app.

**The bundle ("pgdist").**
- A committed manifest pins every input by version, URL and sha256.
- A manually triggered CI workflow builds one tarball per target:
  1. Download each input and verify its sha256, plus the theseus attestation.
  2. Build pgvector against the PostgreSQL.
  3. Extract pg_search from the `.pkg` (`pkgutil --expand-full`) or the
     `.deb` (`dpkg-deb -x`); neither runs install scripts.
  4. Prune what fresh installs never use: `libLLVM`/`llvmjit*` (≈118 MB on
     macOS; the server runs with `jit = off`) and the bundled Python and
     `plpython*` (fresh installs have no `plpython3u`, 2026-11-07 spec).
  5. Keep the upstream licence and dependency notices. The bundled `psql`
     links GPL readline, which is compatible with AGPL.
  6. Smoke-test the result: `initdb`, start on a free port,
     `CREATE EXTENSION vector`, and with pg_search preloaded
     `CREATE EXTENSION pg_search`. Then run one `halfvec` HNSW query and,
     where present, one BM25 query.
  7. Write a contents manifest listing every file and its sha256.
- The tarballs are published, unsigned, as a GitHub Release of this
  repository (e.g. tag `pgdist-18.6-r1`). The bundles never depend on
  theseus or ParadeDB being reachable after that. If theseus is ever
  abandoned, its build scripts are open source and can be forked.
- **macOS/Windows:** the app embeds the matching pgdist tarball's content as
  a bundled resource, so the owner's release script signs every Mach-O file
  in it along with the app.
- **Linux:** `bml` carries the pinned sha256 and downloads the tarball
  itself, matching the 2026-11-07 spec's Linux bootstrap.
- **Install location:** setup copies the binaries into a versioned folder in
  the Rust stack's configuration directory (e.g.
  `~/.bmlibrarian/pgdist/18.6-r1/`), side by side with any other version
  (2026-11-07 spec). They go on the system disk, not into the library
  folder, which may be on an external disk. The LaunchAgent, the import
  profile and app updates all point at this folder, never inside the app
  bundle.
- `bml setup` uses the installed pgdist unless `--pg-bindir` or
  `--existing-server` is given. Both options stay for developers.

### B. Library folder and schema

**Library folder.**
- The wizard asks once (screen 2). The default is a visible `~/BMLibrarian`
  (Claude's call; the 2026-11-07 spec's default was under `~/.bmlibrarian/`,
  but this folder is the user's, holding PDFs they may want to find).
- Inside it:
  - `database/`: the private server's data directory
  - `documents/`: the root of a bmlib `FullTextCache`, unchanged from bmlib:
    `jats/`, `html/`, `pdfs/`, `abstracts/`, files named by
    `sanitize_identifier(doi)`, written atomically
- The folder's path is recorded in the Rust stack's configuration directory.
- **External disks are a follow-up** (owner, 2026-11-11). macOS guards
  access to removable volumes: a `postgres` started by a LaunchAgent may get
  a system permission prompt or be refused silently. For the trial, the
  wizard offers only folders on the internal disk and explains that external
  disks come later. The follow-up must still meet this: when the folder is on
  a disk that is not connected, `bml server status` and the app say so in
  plain words ("the disk holding your library is not connected") and never
  treat the library as empty.

**Schema.**
- Fresh installs get the Rust-layout history in `rust/migrations/` (2026-11-07
  spec). A new `bml-db` crate runs it with bmlib's runner
  (`bmlib::db::migrations::run_migrations` over bmlib's PostgreSQL backend,
  feature `postgres`), using the admin connection from `bml-admin.env`.
- Migration 1 applies bmlib's own PostgreSQL publication schema
  (`bmlib::publications::schema`: `publications`, `fulltext_sources`,
  `download_days`, `download_day_parts`, and the rest). Papers are stored with
  bmlib's `store_publication`, and the resumable day ledger is bmlib's
  `publications::sync`.
  - This is Claude's call, following "lean on bmlib". It means fresh installs
    store papers in bmlib's `publications` table rather than the Rust plan's
    `public.document`, which existed for parity with the Python database. The
    later Rust PubMed importer then also targets `publications`.
- Later migrations add BMLibrarian's own tables:
  - per-paper full-text state: which form we hold (JATS / PDF / HTML /
    abstract only), the version held, its cache path, attempts, the last
    error, and whether a retry is due
  - chunks: paper, ordinal, text, character span, the chunking label
  - vectors: `halfvec(256)` with an HNSW index (Rust plan §3.3; a single table
    is enough at medRxiv scale, the partition manager stays in Phase C)
  - These replace, for this purpose, bmlib's own chunk store
    (`bmlib::embed::store`: `embedded_chunk_sets`/`embedded_chunks`, vectors
    as BYTEA, brute-force cosine). That store cannot search millions of
    chunks. The owner agreed (2026-11-11) to keep `halfvec` + HNSW in
    BMLibrarian for now, reusing bmlib's chunker and `ChunkSetLabel`. Moving
    a pgvector path into bmlib later would need its Python twin too.
  - the lexical index on chunk text: a pg_search BM25 index where the
    extension is available, otherwise `tsvector` + GIN. Migrations detect this
    from `pg_available_extensions` (2026-11-07 spec).
  - the per-paper indexing state, so embedding resumes too
- Migrations stay idempotent and carry no tracking code (golden rules 15–16).

### C. medRxiv download, full text, embedding

**What gets downloaded.**
- All of medRxiv, or from a stated date onwards. No size limits (2026-11-07
  spec goal 5).
- **Two routes** (owner, 2026-11-11):
  - **Bulk (MECA), only for "All of medRxiv" and only when the user entered
    AWS keys.** medRxiv's bulk archive is the MECA packages in the
    requester-pays S3 bucket `s3://medrxiv-src-monthly`. Each package
    contains a paper's JATS XML and PDF. The user's own AWS account pays
    Amazon for the transfer: about $0.09/GB, with the whole archive about
    500 GB+ (2024 figures from `doc/users/medrxiv_import_guide.md`; the
    builder re-measures them for the screen-4 estimate). The owner cannot
    host a copy.
    - Progress is checkpointed per package.
    - After the archive, the paper-by-paper route fills the gap since the
      newest package, because the packages are monthly.
    - Bad keys or a refused request get a plain-language reason and an offer
      to continue paper by paper instead.
  - **Paper by paper:** "from date X onwards", "All of medRxiv" without
    keys, and every update. Metadata comes from bmlib's bioRxiv/medRxiv
    fetcher (`BiorxivFetcher` with server `medrxiv`), walking day by day
    through bmlib's `publications::sync` ledger, so it resumes per day for
    free. The full text for each paper is then fetched as below.
- **MECA support is new code in bmlib** (Python + Rust, shared fixtures).
  bmlib has no MECA reader or requester-pays S3 download. Only BMLibrarian's
  Python `importers/medrxiv_meca_importer.py` does, through boto3, and it is
  the reference for behaviour. The Rust side needs S3 request signing (the
  crate choice is left to the builder; keep it light). Package contents go
  through the same JATS → canonical text path and into the same
  `documents/` cache as the paper-by-paper route.
- **The AWS keys** are stored owner-only in the Rust stack's configuration
  directory, like the database passwords. They are sent only to AWS and never
  logged or shown again. The Python app's AWS settings are not read.
- **Full text priority for each paper** (owner, 2026-11-11):
  1. JATS XML (the API's `jatsxml` link)
  2. PDF (`…/content/<doi>v<n>.full.pdf`)
  3. the paper's medRxiv HTML full-text page, fetched **only when neither JATS
     nor PDF is available**
  4. abstract only, when no full text is available

  bmlib's `FullTextService` and its parsers turn each into canonical text:
  JATS through `fulltext::jats_*`, PDF with feature `pdf` (MuPDF), HTML with
  feature `html`. The source files are kept in the library's `documents/`
  cache.
- **What bmlib lacks (builder check, 2026-11-11).** bmlib's medRxiv fetcher
  lists only the JATS and PDF sources, and `FullTextService` never fetches an
  HTML page. Its `html/` cache folder holds JATS *rendered* as HTML, not a
  downloaded page. Fetching the medRxiv HTML page is therefore new code in
  bmlib. bmlib must stay **functionally identical in Python and Rust**
  (owner), so the addition lands in both languages with shared fixtures,
  through bmlib's own review and release, and BMLibrarian then bumps its bmlib
  pin. The downloaded page needs its own cache location, separate from the
  rendered-JATS `html/` folder, decided in bmlib.
- **Other sources are later work.** PubMed and Europe PMC come later, and
  with them HTML from other sites and Unpaywall. medRxiv papers almost always
  have full text on medRxiv, so this milestone does not query Unpaywall (and
  the wizard asks for no contact email). It also uses none of
  `FullTextService`'s Europe PMC or DOI tiers. Keep the per-paper source
  handling open to further sources.
- **New versions replace old ones** (owner). When medRxiv posts a new version
  of a paper we hold, an update run stores the new metadata, replaces the
  cached full text, deletes that paper's chunks and vectors, and indexes it
  again. bmlib's cache names files by identifier only, so the per-paper state
  records the version held, and the cache key includes the version. For
  example, the key could be `<doi>v<n>`, with the old version's entry deleted
  through `FullTextCache::delete`. This needs no change to bmlib. Withdrawn
  preprints follow bmlib's publication handling; the builder confirms how
  medRxiv marks them.
- **Abstract-only is never final.** A paper whose full text failed is marked
  abstract-only with the reason, stays searchable, and is retried on later
  runs with a back-off. It is never counted as "full text done". Lasting
  refusals (404, not a PDF) and passing ones (timeouts, 5xx, rate limits) are
  told apart, so the retry policy can differ.
- Requests to medRxiv/bioRxiv are polite: one at a time, with a delay set by a
  named constant (golden rule 2).
- **Risk:** medRxiv's website sits behind Cloudflare. The JATS/PDF links may
  be refused to non-browser clients. The builder must measure this early on
  a real sample (bmlib's service docs report ~0.7 % failures on bioRxiv). If
  refusals are common, the fallback is abstract-only plus retry, not
  browser automation, which is out of scope here. The bulk route (above)
  avoids the problem for users who enter AWS keys.

**Embedding (owner: full-text chunk embedding is necessary).**
- Every paper gets its title + abstract embedded. When full text is held, the
  canonical text is chunked (bmlib's chunker) and every chunk is embedded.
- Embedding runs in-process with bmlib's `Embedder` (llama.cpp, Metal on Apple
  silicon; feature `embed-metal`), using the GGUF that setup already
  downloaded and verified. Vectors are 256-d, truncated and normalised by
  bmlib (`EMBEDDING_DIM`, `truncate_and_normalize`).
- Chunk text is also written to the lexical index.

**Checkpoint and resume.**
- All progress lives in the database: the day ledger, the per-paper full-text
  state and the per-paper indexing state. Closing the app, Pause, a crash or
  a power cut lose at most the paper in flight.
- Reopening the app carries on. A scheduled run also carries on an unfinished
  initial download (owner agreed).
- Only one worker runs at a time, held by an OS file lock (the
  `File::try_lock` pattern `bml-setup` already uses). A scheduled run that
  finds the app working exits quietly, and the app shows that a scheduled
  run is working rather than starting a second one.

**Updates.**
- The schedule options are weekly (default), every *n* days, or manual only.
- A scheduled update runs headless, without the app open, through a per-user
  scheduler entry: a LaunchAgent with an interval on macOS, a per-user
  Scheduled Task on Windows, a `systemd --user` timer on Linux. It extends
  the existing `bml-pgserver` autostart module and needs no admin rights.
- The entry runs a `bml` command that does exactly what the wizard's step 5
  does.
- Changing the schedule rewrites the entry. "Only when I ask" removes it.

### D. Tauri app and Mac release

- A new `bml-app` crate holds the Tauri app (2026-11-07 spec). It is a front
  end only: setup, library and search logic live in UI-free crates
  that `bml` also uses (2026-11-07 spec goal 7).
- Long work never blocks the UI thread. Progress reaches the UI as events,
  following `bml-setup`'s existing `StepEvent` pattern.
- Toasts, not modal dialogs (owner preference). Sizes in relative units, one
  central stylesheet: the Tauri counterpart of golden rules 9–10.
- **Search (walking skeleton):**
  - It runs hybrid retrieval as the Rust plan §3.4 specifies: vector top-K
    (HNSW) together with lexical top-K (BM25, or `tsvector` on the fallback
    platforms), ordered by weighted reciprocal-rank fusion with vectors
    weighted 2×.
  - Results are grouped to one row per paper.
  - Opening a result shows JATS/HTML as text inside the app and a PDF in the
    system viewer.
- **Mac release** (2026-11-07 spec piece 5, macOS part only):
  - CI builds the unsigned `.dmg` content.
  - The owner's local release script signs every executable and dylib with
    the Developer ID and hardened runtime, adding the entitlements the
    bundled `postgres` needs to load its extension dylibs. The bundle
    includes pg_search, which ParadeDB signed with its own team ID, so
    re-signing it with the owner's ID is expected.
  - The script then notarises and staples the `.dmg` and publishes it with
    checksums to GitHub Releases.
  - No signing keys go to GitHub.

**Headless parity:** `bml` gains commands for the same work: set up the
library, run/resume a download and index, show its status, set the schedule,
and search. These are what the scheduler entry and Linux users run. Linux keeps
the CLI-only, lighter-touch path from the 2026-11-07 spec.

## Non-goals

- The real search UI: filters, review, reports, LLM answers. Ollama and the
  generation models are installed by setup but unused in this milestone.
- Sources other than medRxiv (PubMed, Europe PMC, PMC) in the wizard, and
  Unpaywall / Europe PMC / DOI fallbacks for medRxiv papers.
- Libraries on external disks (follow-up, see B).
- A guided AWS account / access-key setup (owner: "much, much later"), and
  hosting a copy of the MECA archive (beyond the owner's budget).
- Tauri's self-updater. Trial users install a fix by downloading a new
  `.dmg`; the updater, with its signing key and update feed, comes with the
  first wider release (Claude's call).
- Browser automation for refused downloads; OpenAthens.
- The vector partition manager, the 512-d dimension gate, recall regression
  tests (Rust plan Phase C).
- Windows signing and a Windows release; Windows/Linux hand verification.
- Upgrading PostgreSQL or pg_search under an existing data folder (2026-11-07
  spec: later work).
- Uninstall beyond what the 2026-11-07 spec already leaves to the builder.

## Anti-goals: failure even if it "works"

All of the 2026-11-07 spec's anti-goals, plus:

- A paper counted as having full text when only its abstract was stored, or
  an abstract-only paper that is never retried.
- A failure stored as if it were a result: an empty or broken full text
  cached as a hit, or a chunk set labelled as current that was not embedded
  completely.
- Losing download or indexing progress when the app is closed, paused or
  killed.
- Two workers downloading or embedding at once.
- An unconnected library disk shown as an empty library.
- Downloading or running PostgreSQL binaries whose checksum was not verified.
- AWS keys written to a log, shown again after entry, stored readable by
  other users, or sent anywhere but AWS.
- Showing the user a terminal, a password prompt or a modal dialog anywhere
  in the wizard.

## Constraints

- Everything from the 2026-11-07 spec, especially:
  - PostgreSQL 18
  - the `rust/` workspace
  - the separate Rust-stack config (`bml.env`, `bml-admin.env`)
  - checksum-pinned downloads
  - the AGPL source offer for pg_search
  - signing only on the owner's machine
- bmlib Rust first. Where bmlib nearly fits, contribute the generic piece back
  to bmlib rather than copying it. The GGUF download already follows this,
  through bmlib's `model-download` feature. **bmlib must stay functionally
  identical in Python and Rust** (owner, 2026-11-11): every contribution
  lands in both languages with shared fixtures, so it is a cross-repo task
  with a bmlib release and a pin bump.
- The bmlib dependency is currently a git revision pin. Moving to a crates.io
  release when one is published is #401's business, not this work's.
- Approved models only; no substitution (2026-11-07 spec).
- The project's golden rules (CLAUDE.md, `doc/llm/golden_rules.md`) as they
  apply to Rust: no magic numbers or hard-coded paths, all errors reported,
  type-safe interfaces, pure functions for the logic, documentation in
  `doc/users/` and `doc/developers/`.

## Decisions

### Made by the owner (this conversation, 2026-11-11)

- The milestone: a limited-skills user installs PostgreSQL with extensions,
  gets the document folder structure, and can download, embed and index
  medRxiv, with a walking-skeleton search for testing.
- It has to be a GUI installer; wizard style is fine. The wireframed
  six-screen flow is approved.
- The medRxiv scope options are all, or from a date onwards.
- Full text in the order JATS XML, PDF, then the medRxiv HTML page (only when
  neither JATS nor PDF exists), then abstract only. HTML from other sites and
  Unpaywall come with PubMed / Europe PMC later; Unpaywall is not queried for
  medRxiv.
- bmlib stays functionally identical in Python and Rust.
- `halfvec` + HNSW tables stay in BMLibrarian for now.
- A new preprint version replaces the old one and is re-indexed.
- External-disk libraries are a follow-up; the trial uses the internal disk.
- "All of medRxiv" uses medRxiv's MECA bulk download when the user enters
  their own AWS keys (optional), and otherwise goes paper by paper, as
  updates always do.
- Closing the wizard checkpoints; reopening resumes.
- Updates: weekly (default), every *n* days, or manual only.
- Use bmlib's existing document cache structure.
- Full-text chunk embedding is required.
- First trial on a Mac; the app stays multi-platform.
- Binary sourcing as in Goal A (owner asked for the most reliable and
  sustainable option and approved the recommendation).

### Made by Claude (open to correction)

- Intel Macs use the text-search fallback (no pg_search build exists).
- LLVM/JIT and Python are pruned from the bundle.
- The binaries are embedded in the app on macOS/Windows and copied to a
  versioned folder on the system disk. On Linux, `bml` downloads them.
- The default library folder is `~/BMLibrarian`, with `database/` and
  `documents/` inside.
- Fresh installs use bmlib's `publications` schema, not `public.document`.
- A single vector table at medRxiv scale; the partition manager stays in
  Phase C.
- Scheduled updates also resume an unfinished initial download, and a file
  lock keeps it to one worker.
- Opening a result: text view in the app for JATS/HTML, the system viewer for
  PDFs.

## Pieces of work, in order

Each piece gets its own implementation plan (`docs/superpowers/plans/`).

1. **pgdist**: the manifest, the CI workflow, the first release
   (`pgdist-18.6-r1`), and the `bml setup` change that installs and uses it.
   Verified on the owner's Mac by `bml setup` with no `--pg-bindir`.
2. **`bml-db` + schema**: the library folder, the migrations runner and
   `rust/migrations/`, run by setup after the server is up. *Done
   2026-11-13 (plan `2026-11-13-bml-db-schema.md`): migrations are Rust
   closures in `rust/bml-db/src/schema.rs`, not SQL files (bmlib's splitter
   has no `$$` support, and the BM25/tsvector choice is plain Rust); they run
   as `bml_app`; `--library-dir` replaced `bml setup --data-dir`.*
3. **Library pipeline**: medRxiv metadata, full text (JATS, PDF), version
   replacement, chunking, embedding, checkpoints, the scheduler entry, and
   the `bml` commands. Measure the Cloudflare risk first.
   - **3b, in bmlib (Python + Rust):** fetch the medRxiv HTML full-text page
     as the third tier. It can land after 3; until it does, papers without
     JATS or PDF are stored abstract-only and retried.
   - **3c, in bmlib (Python + Rust):** the MECA reader and requester-pays S3
     download, then the bulk route in the pipeline and the wizard's AWS-key
     fields. It can also land after 3, since paper by paper covers "All of
     medRxiv" too, only more slowly.
4. **Hybrid search**: the crate and `bml search`.
5. **`bml-app`**: the six wizard screens and the search screen over pieces
   1–4.
6. **Mac release**: the signed, notarised `.dmg` and the trial.

Pieces 1–4 are testable from the command line before the app exists.

## Left to the builder

- The exact manifest format and file names; the pgdist release tag scheme.
- The Tauri front-end stack (keep it lean, 2026-11-07 spec).
- The chunk size, overlap and chunking label, within bmlib's chunker, and
  the HNSW build parameters. The Rust plan's measured settings are a
  starting point.
- The retry back-off schedule for abstract-only papers, and the request
  delay value.
- The disk-space estimate shown on screen 2. The wireframe's "~150 GB" was a
  guess; measure it on a sample.
- The time-left estimate on screen 5.
- The exact entitlements for the bundled `postgres` on macOS.
- Where "Update now" sits on the search screen.
- Documentation: `doc/users/` (the wizard, the library folder, updates) and
  `doc/developers/` (pgdist, schema, pipeline, app), per project rules.
