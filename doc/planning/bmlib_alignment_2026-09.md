# bmlib alignment analysis — September 2026

Status: analysis / proposal. No code changed by this document.

## TL;DR

bmlibrarian pins `bmlib[ollama]>=0.5.1,<0.6.0` and uses bmlib for **one thing
only**: the LLM abstraction layer (`src/bmlibrarian/llm/` wraps
`bmlib.llm.LLMClient`). Nothing else in `src/` imports bmlib.

bmlib is now at **0.10.0**. Between 0.5.1 and 0.10.0 it gained seven capability
areas that bmlibrarian already implements locally — several of them *ported out
of bmlibrarian itself* and then hardened. That is roughly **7,400 lines of
near-duplicate code** in this repository that upstream now owns, tests and
type-checks.

In the other direction, bmlibrarian holds a dozen modules that are generic
biomedical-literature infrastructure with no bmlib equivalent, and which the
sibling projects (BioMedicalNews, bmlibrarian_lite) would plausibly use.

## 1. The version pin is stale and costs nothing to lift

`pyproject.toml` justifies the `<0.6.0` ceiling as precautionary ("bmlib is
pre-1.0, so a minor bump may change the API this package delegates its whole
LLM layer to"). Checked against the actual releases:

- The diff of `bmlib/llm/` between 0.5.1 and 0.10.0 is **purely additive**:
  `**kwargs: object` → `**kwargs: Any` on `generate()`/`embed_batch()`, plus
  two new exports (`salvage_json_fields`, `iter_json_spans`) and internal
  hardening of `json_repair`/`utils`.
- `LLMClient`, `LLMMessage`, `LLMResponse`, `EmbeddingResponse`,
  `BatchEmbeddingResponse`, `get_llm_client`, `list_models`,
  `test_connection`, `TokenTracker` and `bmlib.llm.providers` all keep their
  signatures.
- bmlib's CHANGELOG marks `Changed — breaking` sections only under 0.4.0 and
  0.5.0. Nothing since.
- Licensing is a non-issue: both projects are AGPL-3.0.

**Action:** bump to `bmlib[ollama]>=0.10.0,<0.11.0` and re-run
`tests/test_llm_module.py`, `tests/test_llm_layer_boundary.py`,
`tests/llm_test_support.py`. Note bmlib requires Python >=3.11 while
bmlibrarian requires >=3.12, so no floor conflict.

Everything in section 2 depends on this bump.

## 2. What bmlibrarian should adopt from bmlib

Ordered by (value ÷ migration cost). LOC figures are the local modules that
become deletable or reduce to thin adapters.

### 2.1 Tier 1 — straight duplicates, tiny blast radius

| Local module | LOC | bmlib replacement | Consumers to update |
|---|---|---|---|
| `utils/json_repair.py` | 663 | `bmlib.llm.json_repair` (superset: adds `salvage_json_fields`) | 2 (`paperchecker/components/hyde_generator.py`, `utils/__init__.py`) |
| `agents/text_chunking.py` | 220 | `bmlib.llm.text_utils` (superset: adds `process_with_map_reduce`, `process_with_rolling_summary`, `get_text_with_priority`, `combine_title_and_text`) | 2 (`agents/__init__.py`, `document_interrogation_agent.py`) |
| `importers/pdf_converter.py` | 317 | `bmlib.fulltext.pdf_converter` (superset: adds `extract_blocks()`, `LayoutExtractor`, `ConversionResult.title`, password-protected-PDF handling, `pymupdf>=1.28.2`) | 2 (`importers/__init__.py`, `importers/pdf_ingestor.py`) |

`json_repair` and `text_chunking` are function-for-function identical to the
bmlib versions. Keep `bmlibrarian.utils.json_repair` and
`bmlibrarian.agents.text_chunking` as re-export shims for one release so the
`utils/__init__.py` and `agents/__init__.py` public surfaces don't churn.

The tests (`tests/test_pdf_converter.py`, `tests/test_text_chunking.py`) mostly
transfer as-is and become a useful contract check against upstream.

### 2.2 Tier 2 — ports of bmlibrarian code that upstream has since improved

**`agents/context_processor/` → `bmlib.context_processor`** (1,817 LOC).
bmlib's version is the same design, refactored: it adds `OversizedItemError`,
a `ConsolidatedItem` type, `_split_to_fit()`, and `LLMChunkProcessor` +
`ScoredChunk`, which is exactly what
`context_processor/semantic_chunk_processor.py` does locally (including the
`{query}`/`{content}` template validation). Only 5 files reference it, and the
one real consumer is `agents/prisma2020_agent.py` plus the
`create_prisma_chunk_processor()` factory. That factory is the only thing worth
keeping locally — subclass or configure `LLMChunkProcessor` instead.

Caveat: bmlib's `LLMChunkProcessor` drives `bmlib.agents.BaseAgent`, not
`bmlibrarian.agents.base.BaseAgent`. Either pass a small adapter, or route the
extraction call through `bmlibrarian.llm.LLMClient` in a thin subclass of
`IterativeContextProcessor` (the harness itself has no LLM dependency, which is
the point of its split).

**`writing/citation_*.py` + the pure half of `writing/models.py` and
`writing/reference_builder.py` → `bmlib.citations`** (~1,560 LOC).
bmlib's docstring says outright that this was "ported from bmlibrarian's
`writing` package … with the database-backed pieces severed". The four
formatters (Vancouver/APA/Harvard/Chicago), the `[@id:N:Label]` parser and the
reference builder are all there as pure functions over a caller-supplied
`DocumentMetadata`.

What stays local: `writing/document_store.py` (596 LOC, DB-backed),
`WritingDocument`/`DocumentVersion`, and the DB-fetching half of
`ReferenceBuilder` — which becomes a thin `DatabaseManager` →
`dict[int, DocumentMetadata]` adapter feeding `bmlib.citations.build_references()`.
Consumers: three GUI files under `gui/qt/widgets/citation_editor/` and two
test modules.

Note the API shape changes from class-with-methods (`CitationParser.parse_citations`)
to module-level functions (`bmlib.citations.parse_citations`). Cheap, but it is
a real signature change for the citation editor widget.

**`agents/systematic_review/cochrane_*.py` → `bmlib.quality`** (1,975 LOC).
`cochrane_formatter.py` is function-for-function identical to
`bmlib.quality.cochrane_formatter`. `cochrane_models.py` matches class-for-class
and upstream adds `collapse_risk_of_bias()`. `cochrane_assessor.py` matches
`bmlib.quality.CochraneAssessor`, which additionally handles oversized full text
by routing it through `bmlib.context_processor` (returning a `ProcessingStatus`)
— something the local version does not do.

Same `BaseAgent` caveat as above. This is the highest-value item in the list
because it also opens the door to `bmlib.quality.QualityManager`'s tiered
pipeline (metadata → cheap-model classification → deep assessment → Cochrane),
which is a better-factored version of what
`agents/systematic_review/quality.py` (1,060 LOC) hand-rolls across four agents.

**`pdf_processor/` → `bmlib.fulltext`** (671 LOC). `SectionType`, `TextBlock`,
`Section` and `Document`→`SegmentedDocument` are all in
`bmlib.fulltext.models`; `SectionSegmenter` is in `bmlib.fulltext.segmenter`,
explicitly ported from here with documented improvements (line-granularity
blocks, front matter retained, partial matcher searching the compiled pattern
rather than comparing regex source). `PDFExtractor` is superseded by
`PyMuPDFConverter.extract_blocks()`. Consumers:
`agents/paper_reviewer/resolver.py`, two tests, one example.

### 2.3 Tier 3 — capability gain rather than de-duplication

**`bmlib.publications.retractions`.** `importers/retraction_watch_importer.py`
(356 LOC) reads the Retraction Watch CSV into the local `retraction_watch`
table. bmlib's version (735 LOC) is markedly more careful about the same file:
encoding detection with whole-file decode validation, `RetractionNature`
enumeration with unknown-value reporting, date normalisation, per-row skip
callbacks, and `is_retracted()` / `lookup_retractions()` against either backend.
Worth adopting the *parser* (`parse_retraction_watch_csv`) even if the storage
side stays on `DatabaseManager`, because the parser is where the fragility is.

**`bmlib.transparency.TransparencyAnalyzer` — complementary, not duplicate.**
This is the most interesting finding. `agents/transparency_agent.py` +
`transparency_data.py` assess transparency **offline**, by having a local LLM
read the paper's own text for funding/COI/data-availability/registration
statements. bmlib's `TransparencyAnalyzer` assesses the same five dimensions
**online**, from CrossRef, Europe PMC, PubMed `efetch` (`<CoiStatement>`,
`<DataBankList>`, `<GrantList>`), OpenAlex and ClinicalTrials.gov — including
whether a registered trial actually posted results.

These should be two tiers of one assessment, not two assessments. The obvious
move: keep `TransparencyAgent` as the offline tier, and use
`bmlib.transparency` in place of / alongside
`TransparencyAgent.enrich_with_metadata()`, which currently enriches only from
locally-imported ClinicalTrials.gov and Retraction Watch tables. Reconciling
the two score models (`TransparencyAssessment` 0–10 vs `TransparencyResult`
`TransparencyRisk`) is the real work here.

**`bmlib.templates.TemplateEngine`.** bmlibrarian has no prompt-template system
at all — prompts are string literals scattered through the agent modules
(`agents/paper_weight/prompts.py` is the nearest thing). bmlib ships a Jinja2
engine with user-dir override and packaged defaults, and `BaseAgent.render_template()`
is wired to it. Adopting this would make prompts user-tunable without a code
change, which is exactly what the config GUI wants.

**`bmlib.db.backend` (`is_sqlite` / `placeholder` / `placeholders`).** Small,
but `factchecker/db/` maintains a hand-rolled PostgreSQL/SQLite abstraction
(`abstract_db.py` + `postgresql_db.py` + `sqlite_db.py`, 912 LOC) whose whole
reason to exist is dialect differences. The three bmlib helpers would remove
the duplicated-SQL half of it.

### 2.4 Explicitly *not* worth adopting

- **`bmlib.publications` storage/sync/schema** — bmlib owns its own
  `publications` schema and `Publication` model. bmlibrarian has a mature,
  much richer PostgreSQL schema with migrations, pgvector, semantic chunks and
  MeSH. Adopting bmlib's storage layer would be a regression. The *fetchers*
  (`fetch_pubmed`, `fetch_biorxiv`, `fetch_openalex`) are interesting as
  incremental-sync sources, but bmlibrarian's bulk importers (PubMed baseline,
  PMC OA, Europe PMC, MECA) solve a different problem and are far ahead.
- **`bmlib.agents.BaseAgent`** — bmlibrarian's `BaseAgent` (1,271 LOC) carries
  orchestrator/queue integration, config-driven model resolution, progress
  callbacks and Ollama option filtering that bmlib's 585-line version does not.
  Keep ours. Do adopt `bmlib.agents.PerformanceMetrics` though: it is the same
  class ported, made thread-safe with `snapshot()`, and gains `add_retry()`
  and `from_dict()`.
- **`bmlib.fulltext.FullTextService`** — overlaps `discovery/` but does less:
  no CrossRef title resolution, no OpenAthens, no browser fallback, no PDF
  verification. Keep `discovery/`. (See 3.1 — this one should go the other way.)

## 3. What bmlibrarian has that bmlib could use

These are modules with no bmlib equivalent that are generic to
biomedical-literature tooling, i.e. plausibly wanted by BioMedicalNews and
bmlibrarian_lite. Listed with the coupling that would have to be severed first.

### 3.1 Strong candidates

**Full-text discovery (`discovery/`, 6,153 LOC).** bmlib's `FullTextService`
covers Europe PMC → NCBI → Unpaywall → DOI. bmlibrarian adds, as pluggable
`BaseResolver` subclasses: `CrossRefTitleResolver` (find a DOI from a title —
the single most useful thing when metadata is incomplete), `OpenAthensResolver`
(institutional access), `pdf_verifier.py` (LLM-checked "is this PDF actually
the paper I asked for", 664 LOC), and `browser_downloader.py` (Playwright
fallback for Cloudflare/anti-bot publishers). The resolver protocol is the
right shape for upstreaming — `resolvers.py` imports nothing from bmlibrarian
beyond its own `data_types`.

**PubMed API search (`pubmed_search/`, 3,556 LOC).** Natural-language →
PubMed query conversion with MeSH terms, field tags and boolean operators,
plus a rate-limited E-utilities client and result processor. bmlib's
`fetch_pubmed` only takes a query string; it has no query *construction*. Only
coupling is `bmlibrarian.llm` for the converter, which maps 1:1 onto
`bmlib.llm`.

**MeSH (`mesh/`, 1,037 LOC) and thesaurus (`thesaurus/`, 598 LOC).**
Term lookup, partial search, synonym/entry-term expansion, with local-DB-first
and NLM-API fallback. `mesh/lookup.py` imports only its own `data_types`;
`thesaurus/expander.py` imports nothing from bmlibrarian at all. Any tool doing
literature search wants this and bmlib has none of it.

**URL/path/archive safety (`utils/url_validation.py`,
`utils/path_utils.py`, the tar/zip path-traversal hardening documented in
`doc/llm/archive_extraction_safety.md`).** Zero bmlibrarian imports. bmlib
downloads and extracts remote archives in `publications/` and `fulltext/` and
has no equivalent guard. This is the cheapest and highest-safety-value
upstream contribution on the list.

**`bmlib.quality` gaps that bmlibrarian fills.** bmlib has study-design
classification and Cochrane RoB. bmlibrarian additionally has:
`agents/pico_agent.py` (PICO extraction), `agents/prisma2020_agent.py`
(27-item PRISMA 2020 checklist with suitability pre-screening), and
`agents/paper_weight/` (4,715 LOC — evidential-weight assessment with rule-based
extractors, LLM assessors and validators). All three are the same *kind* of
thing as `bmlib.quality.QualityAgent` and would slot into `QualityManager`'s
tier structure.

### 3.2 Worth considering

- **`exporters/pdf_exporter.py` (568 LOC)** — Markdown → publication-quality
  PDF via ReportLab. Pure, no bmlibrarian coupling, BSD-licensed deps.
  Complements bmlib's `render_html()`.
- **`agents/utils/hyde_search.py`** — HyDE (hypothetical document embeddings)
  search, and `agents/utils/query_syntax.py` (2 imports, essentially pure).
- **`embeddings/` chunkers (3,069 LOC)** — adaptive/semantic/sentence chunkers
  with a measured performance comparison (`doc/CHUNKER_PERFORMANCE_COMPARISON.md`).
  bmlib's `TextChunker` is character-window-with-boundary-adjustment only.
  The chunkers are separable from the embedders (which are backend-specific).
- **`evaluations/` + `audit/` (4,121 LOC)** — run-scoped, database-backed
  evaluation storage with an evaluator registry and versioning. This is
  infrastructure any LLM-assessment library needs, and bmlib currently returns
  assessments without any provenance story. Would need the `DatabaseManager`
  coupling replaced with `bmlib.db`'s connection-passing style.
- **`utils/openathens_auth.py`** — institutional proxy auth with secure
  (JSON, 0600) session persistence. Niche but genuinely hard to get right, and
  documented in `doc/developers/openathens_security.md`.

### 3.3 Keep local

GUI (`gui/`, 67,885 LOC), labs (`lab/`), CLI (`cli/`), auth/user settings,
migrations, the orchestrator/queue system, and all bulk importers. These are
application concerns or are tied to bmlibrarian's schema.

## 4. Suggested sequencing

1. **Bump the pin** to `>=0.10.0,<0.11.0`; confirm the LLM test suite is green.
   Update the comment in `pyproject.toml` to record *why* the new ceiling is
   where it is.
2. **Tier 1 swaps** (`json_repair`, `text_chunking`, `importers/pdf_converter`)
   behind re-export shims. ~1,200 LOC removed, ~6 files touched.
3. **`pdf_processor/` → `bmlib.fulltext`** — self-contained, 4 consumers.
4. **`writing/` → `bmlib.citations`**, keeping `document_store.py` and a
   DB→`DocumentMetadata` adapter.
5. **Decide the `BaseAgent` bridge** (adapter vs. thin subclass). This gates
   both `context_processor` and `bmlib.quality`, so it is worth resolving once,
   deliberately, rather than twice ad hoc.
6. **`context_processor` and `cochrane_*`** once 5 is settled. ~3,800 LOC.
7. **Transparency two-tier reconciliation** — design work, not a swap.
8. **Upstream**, in this order: archive/URL safety helpers → MeSH + thesaurus →
   PubMed query converter → discovery resolvers. Each needs a bmlib PR with its
   own tests; the first is small enough to be a good template for the rest.

Every step in 2–6 should keep a shim and land with its existing tests
re-pointed at the bmlib implementation, so that a regression upstream surfaces
here as a test failure rather than as silent behaviour drift.

## 5. Figures

| Item | LOC |
|---|---|
| `agents/context_processor/` | 1,817 |
| `agents/systematic_review/cochrane_*.py` | 1,975 |
| `writing/` (pure half) | ~1,560 |
| `pdf_processor/` | 671 |
| `utils/json_repair.py` | 663 |
| `importers/pdf_converter.py` | 317 |
| `agents/text_chunking.py` | 220 |
| **Total near-duplicate** | **~7,400** |

Against roughly 207,000 LOC of `src/`, that is ~3.6% of the codebase that a
shared library already maintains, tests and type-checks (bmlib ships `py.typed`
and gates on mypy).
