# Remaining red tests

Written after completing `ollama_bypass_migration_plan.md`. That plan
listed "the full test suite hangs" as a known issue and a prerequisite
for CI. Fixing it made a large body of pre-existing test debt visible for
the first time. This note records what each remaining failure is, so the
next session does not have to re-derive it.

Nothing here is caused by the ollama migration. Everything below either
pre-dates it or was already failing and merely unreachable.

## What changed

`pytest tests/` used to collect 2,000 tests, hit 6 collection errors and
abort — producing zero output for over an hour. It now collects **3,157**
with no collection errors, and completes.

The 1,157 newly-visible tests are the reason the failure count went up.
They were not passing before; they were never reached.

## Fixed

| Problem | Cause |
|---|---|
| 6 collection errors | `test_paper_weight_lab_workers.py` ran `sys.modules['bmlibrarian'] = type(sys)('bmlibrarian')` at import, replacing the real package for the rest of the session. Five other modules then failed with "'bmlibrarian' is not a package" — which is why each passed when run alone. |
| `test_pubmedqa_importer` | Put the repo root on `sys.path` to import `import_pubmedqa_abstracts`, which `f8971f1` moved into `scripts/` without updating the test. |
| `test_spacy_chunker_performance` | Imported spaCy, an optional extra and not a declared dependency, turning a missing optional package into a collection error. |
| Suite hang #1 | `test_browser_download.py` drives a real Playwright browser at a live URL. A script pytest collects by name. |
| Suite hang #2 | `test_database_multi_query.py` queries the production database. Its comment claimed it did not, and its `try/except` caught nothing — an unreachable DB blocks in psycopg's socket wait rather than raising. |
| Suite hang #3 | `test_prisma2020_lab_plugin.py` opens a `QMessageBox` modal that waits for a click. |
| 3 benchmark scripts | `test_chunker_performance` took the corpus as a required argument, so pytest collected it and errored with "fixture 'documents' not found". Never runnable as tests; renamed `benchmark_*`. |
| `DEFAULT_CHUNK_SIZE == 350` | Constants deliberately retuned (1800/320, then 1000/100 in `2995951`); the test was never updated. Now asserts the invariant that matters — overlap is a minor fraction of chunk size — instead of restating the source. |
| `test_generate_hybrid_queries` | Asserted exactly one query; the method now also expands drug classes and adds a PICO query. Now asserts the contract (non-empty, all HYBRID, research question present) rather than a count that grows with the feature. |
| 2 paperchecker counter-report tests | Assigned `agent.client = Mock()`, but `client` is a read-only property. Moved onto the provider boundary via `patch_llm`. |

## Outstanding

### 1. Qt GUI tests — ~21 failures across two files

`tests/test_qt_integration.py` (9) and `tests/test_qt_research_tab.py`
(12).

**Cause.** `ResearchTabWidget` gained an `agents` parameter and now
builds its `workflow_executor` only when given one; without it, it logs
"No agents provided - workflow functionality disabled" and leaves the
attribute `None`. Both test files still construct `ResearchTabWidget()`
bare, so every test touching `self.executor.<anything>` fails with
`AttributeError: 'NoneType' object has no attribute ...`.

**Why it is not a one-line fix.** Passing a dict of `Mock()` agents was
tried and rejected: it satisfies the constructor, but the tests then
reach real workflow code that starts Qt threads and *hangs*, which is
worse than failing. These tests need their threading boundary mocked,
not just their agents. That is a design decision about what these tests
are meant to cover, and belongs with whoever owns the Qt workflow.

**Note on timing.** Each hanging test now burns the 120s ceiling before
failing, so these two files alone cost ~8 minutes. Worth fixing for
suite speed, not only for correctness.

### 2. `test_prisma2020_lab_plugin.py` — 18 failures

**Cause.** Test/implementation drift. The tests reference widget
attributes that no longer exist (`doc_id_input`, `model_combo`,
`_get_score_color`, `_clear_layout`) and a module-level
`fetch_documents_by_ids`. The implementation was refactored and this
module was never updated.

Verified pre-existing: applying only the modal-stubbing fixture to
`master`, with nothing else from the migration branch, reproduces the
identical 18 failed / 5 passed.

Left failing rather than skipped, so the drift stays visible. Skipping
would restore the silence that hid it.

### 3. `test_pubmed_bulk_importer_formatting.py` — 24 errors

All `AttributeError: __enter__` — a fixture returns a plain `Mock()`
where the code under test uses it as a context manager. Needs
`MagicMock()` (which supports the protocol) or an explicit
`__enter__`/`__exit__`. Mechanical, but 24 call sites; not attempted
here because it is unrelated to the migration.

### 4. Scattered PDF-discovery/upload failures

`test_pdf_discovery_download.py`, `test_pdf_discovery_gui.py`,
`test_pdf_upload_validators.py` — a handful each. Not investigated.
These were among the 1,157 tests that became reachable only after the
collection errors were fixed, so they have never been triaged.

## Recommendations

1. **Add CI now.** The suite completes, so the boundary guard added in
   PR #247 can finally do its job. It fails someone else's future PR,
   which is worthless without CI. Start with
   `pytest tests/ -m "not integration and not requires_database"`.
2. **Decide the default marker selection.** `pytest tests/` still runs
   the browser and production-database tests unless deselected. Adding
   `-m "not integration and not requires_database"` to `addopts` would
   make the plain command safe by default; it was left alone here
   because it changes test selection semantics project-wide.
3. **Prefer toasts to modals in Qt code.** A modal is not just a UI
   annoyance — it hangs the suite in a way `pytest-timeout` cannot
   interrupt, because Qt's event loop swallows `SIGALRM`. The 120s
   ceiling rescues database and network stalls, but not blocked Qt event
   loops; those must be fixed at the source.
