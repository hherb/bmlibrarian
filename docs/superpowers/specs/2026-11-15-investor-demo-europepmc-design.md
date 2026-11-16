# Investor demo: an app window that builds a searchable full-text library

**Date:** 2026-11-15
**Status:** Draft (design), awaiting approval
**Deadline:** the sponsor/investor meeting after the Melbourne AI conference,
**2026-11-23**. Everything below is cut to fit that date.
**Builds on:** `2026-11-11-installer-walking-skeleton-design.md` (the
"walking-skeleton spec"). Its constraints and the approved wizard wireframes
still hold unless this document says otherwise. It changes the paper source
(Europe PMC instead of medRxiv), drops the MECA/AWS route, and pulls the
search (piece 4) and the app (piece 5) forward in trimmed form.

## Intent

The owner shows potential sponsors and investors, who are not technical
people, two things:

1. **A finished library** on the owner's Mac, built in the days before:
   several thousand good-quality full-text papers on one topic, chunked,
   embedded and searchable by meaning, in an app window.
2. **A live install:** the same app on the same Mac, started fresh. It sets
   everything up, and papers start arriving and become searchable while the
   audience watches. It does not have to finish.

**Everything happens in an app window.** The owner has watched non-technical
audiences lose interest in terminal programs, so the demo never shows a
terminal.

**Why the source changed.** medRxiv was the planned source, but neither of
the owner's AWS accounts can read the medRxiv bulk bucket (both are AWS
"projects" locked to ap-southeast-2, and the bucket is in us-east-1; see
HANDOVER 3c/M0). Paper-by-paper medRxiv is slow (30 s per request), often
yields no article body, and its PDF fallback is often blocked by Cloudflare.
Europe PMC's own preprint full texts are about 24% of medRxiv and are mostly
COVID-era, which the owner rejects as poor quality. Europe PMC's
**peer-reviewed open-access** full texts have none of these problems: 4.8
million from 2021–2026, complete JATS, served by a public API.

## Goals

1. **The demo library topic: depression & anxiety, trials and reviews**
   (owner, 2026-11-15). Peer-reviewed, open access with full text, published
   2021–2026, the topic in title or abstract, and the publication type a
   randomized controlled trial, systematic review or meta-analysis. Measured
   on 2026-11-15: **8,372 papers** (the type labels are incomplete for recent
   years, so this is a floor). The query, as Europe PMC syntax:

   ```
   OPEN_ACCESS:Y AND HAS_FT:Y AND NOT SRC:PPR AND PUB_YEAR:[2021 TO 2026]
   AND (TITLE:"depression" OR ABSTRACT:"depression"
        OR TITLE:"anxiety disorder" OR ABSTRACT:"anxiety disorder")
   AND (PUB_TYPE:"Randomized Controlled Trial" OR PUB_TYPE:"Systematic Review"
        OR PUB_TYPE:"Meta-Analysis")
   ```

2. **The app window walks the six approved wizard screens** (walking-skeleton
   spec, "The wizard"), with screen 4 changed (below). The live install
   reaches screen 6 with the first papers searchable **within minutes** of
   pressing "Start downloading".
3. **Search finds papers by meaning**: hybrid retrieval over the existing
   chunk tables, one result per paper, with the passage that matched.
4. **The finished library is built with the same code** a few days before the
   meeting (target: complete by 2026-11-20), so problems surface before the
   meeting, not in it.

## Non-goals (cut for the deadline)

- AWS keys, MECA, medRxiv choices in the wizard. The existing medRxiv
  pipeline stays in the code and keeps passing its tests, but the app does not
  offer it.
- A folder chooser on screen 2 (the default `~/BMLibrarian` only, free space
  shown).
- Opening PDFs. Results open the stored text inside the app.
- The signed, notarized `.dmg` (piece 6). The owner runs a locally built app
  on their own Mac.
- Windows and Linux builds of the app (the crates below them must still build
  and pass on CI as today).
- Editing the topic query in the app. Screen 4 offers presets only.
- The scheduler UI beyond what screen 4 already lists (the existing
  `library schedule` code may be called; no new scheduling work).

## Anti-goals (failure even if it technically works)

- **A terminal window appears**, or the audience has to read log lines.
- **A modal dialog blocks the window** (owner preference: toasts).
- **Garbage results**: preprints or COVID-era filler in the demo library, or
  search hits that are reference lists, author affiliations or funding
  statements rather than findings.
- **The live install damages the prepared library**: same folder, same
  database, same config, or a shared lock that stops one of them.
- **Impolite traffic**: hammering Europe PMC during the overnight build and
  getting blocked the day before the meeting.

## Constraints

- **Deadline 2026-11-23.** A working, rehearsed demo beats completeness.
- **bmlib first** (walking-skeleton spec): new source code lives in bmlib,
  **in Python and Rust together** with shared fixtures (owner rule on bmlib
  parity). BMLibrarian pins the bmlib commit that contains it.
- The project's golden rules: type hints and docstrings (Rust doc comments),
  no magic numbers, errors handled and shown in plain language, no inline
  styles (one central stylesheet for the app), relative units instead of
  pixels, idempotent migrations.
- UI-free crates hold all logic; `bml-app` is a front end only
  (walking-skeleton spec D). Long work never blocks the UI thread; progress
  reaches the UI as events (`bml-setup`'s `StepEvent`, `bml-library`'s
  `Progress`).
- Tests stay hermetic: no live Europe PMC or Ollama calls in the default
  suite; recorded fixtures instead.
- Licences: the open-access subset mixes CC BY, CC BY-NC and others. A private
  demo of locally stored text is fine; record each paper's licence (the
  fetcher already carries it) so later public use can filter.

## Approaches considered

**Source of full text** (owner picked A):

- **A. Europe PMC open access, chosen by a topic search (picked).** Good
  quality (peer-reviewed), complete JATS, fast, any topic. Needs a new bmlib
  sync source. Turns "your medRxiv library" into "your library on a topic",
  which suits the demo better.
- B. Europe PMC open-access bulk files. Fast, but grouped by ID range, so a
  random mix of fields; search demos on a random mix are weaker.
- C. Recent medRxiv through the existing pipeline. No new download code, but
  preprints, 30 s per paper, and unmeasured Cloudflare/body-rate problems.
- (Rejected earlier: MECA over AWS, blocked by the accounts; Europe PMC
  preprint bulk, 24% coverage and mostly COVID-era.)

**What the audience looks at** (owner picked the app for both):

- Terminal for both: cheapest, but loses non-technical audiences.
- App window for search, terminal for the install: rejected for the same
  reason.
- **App window for both (picked)**, trimmed as listed under non-goals.

## Design

### 1. bmlib: a `europepmc` sync source (Python + Rust)

A new source in bmlib's registry, so `publications::sync` walks it day by day
like `medrxiv-details` and `openalex` and gets the per-day ledger, resume and
settle days for free.

- **Config:** `query` (required): the topic search, without a date clause.
  The fetcher adds the day: `(<query>) AND FIRST_PDATE:[<day> TO <day>]`.
  Optional `email`, sent as Europe PMC suggests for polite clients.
- **Walk:** `GET {EUROPEPMC_REST_BASE}/search` with `resultType=core`,
  `format=json`, `pageSize` at the API maximum, and `cursorMark` paging until
  the cursor stops moving. Each hit goes through the existing
  `fetchers::europepmc::normalize` (already in Python and Rust), which builds
  the `fullTextXML` source entry for a PMC accession.
- **Reconciliation:** the day's promise is the first page's `hitCount`, so a
  short walk is a failed day and is fetched again next run (bmlib's existing
  rule).
- **Settle days:** Europe PMC adds records for past dates late. The builder
  picks a settle period (a named constant) so recent days are re-fetched.
- **Request spacing:** a named constant, starting at one request per second.
  Europe PMC publishes no hard limit; measure on the first sample run and
  keep it polite.
- **Fixtures:** recorded Europe PMC JSON pages, shared by the Python and Rust
  tests; the Rust oracle cases follow the existing fetcher pattern.
- **Pinning under the deadline (builder check, my call).** BMLibrarian may
  pin the bmlib branch commit before the bmlib PR is merged, so the prepared
  library's build is not waiting on review. The bmlib PR is still opened and
  reviewed as usual, and BMLibrarian is re-pinned to the merged commit after
  the meeting.

### 2. `bml-library`: a library defined by a source and a query

- **What a library is:** `library_state` gains the library's source and its
  query (migration 4, idempotent). Existing libraries read as medRxiv, so
  nothing changes for them. A Europe PMC library records its `query` and its
  first day (from the year range of the preset).
- **Metadata phase:** for a Europe PMC library, `sync` runs the `europepmc`
  source with the stored query as its config, in the same day windows.
- **Full-text phase:** `next_paper` and `sources` are medRxiv-only today
  (source, version, `xml`/`pdf`). Add the Europe PMC case: papers with a
  `europepmc` `xml` source and no usable `publication_fulltext` row, newest
  first. Fetch through `FullTextService` with the paper's `pmc_id` set, so
  bmlib's Tier 1a (Europe PMC XML → JATS → text) runs. Same retry,
  `attempts` and abstract-only bookkeeping as the medRxiv case. Europe PMC has
  no versions; treat every paper as version 1.
- **Spacing:** the full-text client gets its own Europe PMC delay constant
  (same starting value as the metadata one), not the 30 s medRxiv delay.
- **Index phase:** unchanged (it is source-agnostic: chunk, embed, store).
- **Rounds, newest first (builder check, my call).** Today `Pipeline::update`
  runs all metadata, then indexes abstracts, then all full text, then indexes
  again. For 2021–2026 that means no full text is searchable for hours, which
  breaks goal 2. For a Europe PMC library, `update` instead loops over
  **rounds**, newest window first. Each round syncs one metadata window, then
  fetches full text for that window's papers, then indexes them. So the first
  full texts become searchable after one window (minutes), and abstracts from
  that window even sooner. The existing checkpoints still decide what is done,
  so a stop or crash loses at most the paper in flight. Whether bmlib's `sync`
  can walk a window's days newest first, or the pipeline simply asks for
  windows in descending order, is the builder's choice. The medRxiv path keeps
  its current order and tests.
- **The CLI** (`bml library update`) works for a Europe PMC library too. That
  lets the finished demo library be built from the command line while the app
  is still being written.

### 3. `bml-search`: hybrid search (new UI-free crate)

As the walking-skeleton spec D specifies, trimmed:

- Embed the query with the same GGUF embedder the index phase uses (apply the
  model's query prefix if it has one; the builder checks Arctic's card).
- Vector top-K over `chunk_embeddings` (HNSW, cosine) and lexical top-K over
  `chunks` (BM25 where pg_search is installed, else the tsvector index;
  `LexicalIndex` already tells which). Combine by weighted reciprocal-rank
  fusion, vectors weighted 2×. K and the weights are named constants.
- Group to one result per paper: title, journal, year, authors, the best
  matching passage, and the paper id for opening it.
- A `bml search "query"` CLI command for testing and checking the demo
  library. The demo itself never uses it.
- **Result quality:** check the demo topic's top results by hand (see 5). If
  reference lists, affiliations or funding statements rank high, filter those
  chunk kinds out (or down) in search. Prefer that over re-chunking.

### 4. `bml-app`: the Tauri app (new crate)

The six approved screens, each a thin view over the crates above:

1. **Welcome:** what will happen, in plain words; "no administrator password
   needed". [Start]
2. **Where your library lives:** `~/BMLibrarian`, with free space and a
   rough size estimate for the chosen topic. No chooser.
3. **Installing:** `bml-setup`'s steps, each with a live status line from its
   `StepEvent`s. A failed step shows a plain-language reason and "Try again".
   Hardware warnings are toasts. On the demo Mac, Ollama and the models are
   already there, so these steps show "already installed" quickly. That's
   fine: it keeps the live demo short.
4. **Your library (changed):** a short list of preset topics, each with a
   live paper count from Europe PMC's `hitCount` (falling back to the stored
   count when offline). "Depression & anxiety: trials & reviews" is
   preselected. "Keep it up to date": every week (default), every n days, or
   only when I ask. [Start downloading]
5. **Building your library:** found / downloaded (full text or abstract only)
   / ready to search counts, a time estimate, [Pause]. "You can close this
   window. Next time it carries on where it stopped."
6. **Search:** a search box and result cards (title, journal, year, the
   matching passage). It works while the library is still filling and shows
   screen 5's progress line while a download runs. A result opens the stored
   text inside the app.

- **The presets (owner, 2026-11-15).** All four use the same filter as goal
  1 (peer-reviewed, open access with full text, 2021–2026, trials,
  systematic reviews and meta-analyses), the terms matched in title or
  abstract. Any of them really downloads if picked in the live demo. Counts
  as measured on 2026-11-15:

  | Preset | Terms | Papers |
  |---|---|---:|
  | Depression & anxiety (preselected) | "depression", "anxiety disorder" | 8,372 |
  | Heart failure & cardiology | "heart failure", "atrial fibrillation", "myocardial infarction", "coronary artery disease" | 5,513 |
  | Obesity & GLP-1 drugs | "obesity", "GLP-1", "semaglutide", "tirzepatide" | 5,058 |
  | Stroke | "stroke" | 5,391 |

- The presets live in one list in a UI-free crate (name, Europe PMC query,
  year range, stored count), so adding a topic later is a one-line change.
- The pipeline runs on a worker thread inside the app. [Pause] and closing
  the window set the pipeline's `stop` flag. The existing library lock keeps
  the scheduled update and the app from running at once.
- Re-opening after setup goes straight to screen 6 (spec).
- **Front end:** plain HTML, one stylesheet and a little vanilla JavaScript.
  No framework (the 2026-11-07 spec asks for a lean stack). Sizes in `rem`/`em`.
- **Two installs on one Mac (builder check, my calls).**
  - The **prepared library uses non-default folders**: its own config folder
    and a library folder such as `~/BMLibrarian-demo`, built with
    `bml --config-dir … setup --library-dir … --skip autostart`. The **live
    install gets the real defaults**, so screen 2 shows `~/BMLibrarian` as a
    real user would see it. Before the meeting, the default config and
    library folders on the demo Mac must be empty.
  - The app accepts a config-folder setting (environment variable or launch
    argument, builder's choice; `bml` already has `--config-dir`). The
    prepared library is opened with it.
  - **The prepared library creates no login items.** The login entries have
    fixed names (`org.bmlibrarian.pgserver`, `org.bmlibrarian.library-update`,
    open issue #451), so the live install would overwrite them. The prepared
    library therefore skips autostart and scheduling. When the app opens a
    library whose database is not running, it starts it (as `bml server
    start` does). The live install creates its login items normally. #451
    itself is not fixed for the demo.
  - Setting up the private database already picks a free port
    (`bml-pgserver` `choose_port`), so both databases can run at once.
- **Network at the meeting (owner, 2026-11-15): not guaranteed, possibly the
  owner's phone.**
  - **Pre-downloaded caches (owner-approved).** The embedding model file
    (Arctic GGUF, about 1.16 GB, `<config>/models/`) and the bundled
    PostgreSQL (`<config>/pgdist/`) live inside the config folder. Before the
    meeting, copy both into the live install's (default) config folder.
    Screen 3 then shows those steps as already downloaded. The database and
    library are still created fresh, and papers download for real.
  - Paper downloads must work over a slow phone connection. Europe PMC
    full-text XML is small, so this is about timeouts and retries, not
    bandwidth: a dropped connection is a plain-language toast and a retry,
    never a frozen window or a failed step that needs "Try again" to
    recover.
  - With no network at all, screen 4 falls back to the stored counts and
    screen 5 says plainly that it is waiting for the internet. The fallback
    demo is the prepared library.

### 5. Building and rehearsing the demo

- **Measure first, on a 200-paper sample** of the demo query: Europe PMC
  request time, full-text success rate, chunks per paper, and embedding
  throughput on the demo Mac. These numbers set the overnight build time and
  screen 5's estimate. If the whole query would not finish by 2026-11-20,
  narrow the year range rather than cutting quality.
- **Build the finished library** from the CLI as soon as parts 1 and 2 work,
  in parallel with the app work.
- **Check search quality by hand** with a handful of questions a clinician
  would ask about depression and anxiety treatment.
- **Rehearse the live install** end to end at least once on the demo Mac,
  with the prepared library's database running, by 2026-11-22.

## Order of work (suggested)

1. bmlib `europepmc` source, Python + Rust, with fixtures; pin it. (11-15/16)
2. `bml-library` Europe PMC library; 200-paper sample and measurements;
   start the full build. (11-16/17)
3. `bml-search` and `bml search`; check result quality on the growing library.
   (11-17/18)
4. `bml-app`, screens 6 and 5 first (the payoff), then 1–4. (11-18 to 11-21)
5. Rehearsal, fixes, buffer. (11-21 to 11-22)

## Left to the builder

- Settle period, request spacing, K and fusion weights (named constants,
  values from the sample run).
- How the config folder reaches the app (environment variable or argument).
- The size-estimate formula on screen 2.
- The exact wording on every screen, within the walking-skeleton spec's
  plain-language rule.
- Whether screen 4's live count is fetched on open or cached at start-up.
- How the existing schedule code is called from screen 4, if at all
  (a weekly default is fine).
