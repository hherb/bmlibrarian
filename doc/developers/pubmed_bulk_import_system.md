# PubMed Bulk Import — Developer Notes

Code: `src/bmlibrarian/importers/pubmed_bulk_importer.py`, `src/bmlibrarian/importers/ncbi_https.py`,
`src/bmlibrarian/db_import_profile.py`, `src/bmlibrarian/env_loader.py`, CLI
`pubmed_bulk_cli.py`. Schema: `migrations/031_ingest_ledger_and_revisions.sql`.
Background and measurements: `doc/planning/rust/implementation_plan.md`
(Phase A) and `spikes/pubmed-ingest/FINDINGS.md`.

## Download path (HTTPS, MD5-verified)

`importers/ncbi_https.py`, `HttpsDownloader`:

- Listing: the HTTPS directory page, parsed by `parse_directory_listing()`.
  Only bare `pubmedNNnNNNN.xml.gz` names are accepted.
- Each file's expected MD5 comes from NCBI's `<name>.md5`
  (`parse_md5_file()`).
- Data goes to `<name>.part`. An interrupted transfer resumes with
  `Range: bytes=<size>-`. A `206` must start at exactly that offset; a `200`
  (Range ignored) restarts the file; a `416` means nothing is left and the MD5
  check decides.
- If the MD5 matches, the file is moved into place with `os.replace`; if not,
  the `.part` file is deleted and the download retried. An existing final file
  is accepted only if its MD5 matches, so files left over from the FTP era are
  re-checked.
- The session and the sleep function are injected, and tests use a fake
  session (`tests/test_ncbi_https.py`).

Importer side: `_download_directory()` (shared by `download_baseline`,
`download_updates` and `download_and_import_baseline`) and `_download_one()`.
A file is skipped only if the tracker records it **and** it exists on disk.
The tracker's checksum column now stores NCBI's MD5.

**Why not FTP:** in October 2026 the NCBI FTP data stream was observed to
rewind mid-transfer. In a 35.5 MB file, the stream jumped from 6.5 MB back to
5.0 MB, re-sent that data, and so on; the server still reported
`226 Transfer complete`. Every received byte was genuine file data, so this is
a server-side fault that no client can fix. Two of 117 files were left
truncated at their final names and only the XML parser caught them.
Over HTTPS the same file downloaded correctly every time, at the same speed.

## Write path (one transaction per file)

`PubMedBulkImporter.import_file(path, force=False)`:

1. Skip the file if it is in `ingest.ledger` (unless `force`).
2. Parse the whole file with `ET.iterparse` → `_parse_article` dicts.
3. `_store_file` runs everything in **one transaction**:
   - `CREATE TEMP TABLE stage_document / stage_metadata … ON COMMIT DROP`;
   - COPY the rows produced by `to_staging_rows()`. That function is pure:
     empty strings become NULL, invalid dates become NULL, and only meaningful
     metadata is kept;
   - `MERGE_DOCUMENTS_SQL`;
   - `MERGE_METADATA_SQL`, skipped if `transparency.document_metadata` is
     absent;
   - `LEDGER_UPSERT_SQL`: the ledger row (source, file, sha256, records,
     seconds).

An interruption therefore leaves the whole file or nothing. Resuming means
running again.

### Revision semantics

PubMed republishes revised records under the same PMID. The newest
`MedlineCitation/DateRevised` wins:

- **Within a file:** `DISTINCT ON (external_id) ORDER BY external_id,
  date_revised DESC NULLS LAST, ord DESC`.
- **Against the stored row:** the `ON CONFLICT … DO UPDATE` has
  `WHERE EXCLUDED.date_revised IS NULL OR document.date_revised IS NULL OR
  EXCLUDED.date_revised >= document.date_revised`.
- **Metadata:** written only where the staged revision equals the stored
  `document.date_revised`, i.e. the metadata of the revision that won.

Because of this, files can be imported in any order and in parallel. Field
semantics otherwise match the old row-by-row importer: `doi`, `abstract`,
`publication` and `publication_date` are COALESCEd; title, authors, MeSH and
keywords are replaced.

### Withdrawals (DeleteCitation)

Withdrawn documents are marked in the baseline schema's existing columns
`document.withdrawn_date` / `withdrawn_reason` (`'PubMed DeleteCitation'`,
`WITHDRAWN_REASON`). Migration 032 adds `ingest.withdrawn_pmid(pmid PK, file,
withdrawn)`; `withdrawn` is the date BMLibrarian recorded the withdrawal (the
import or backfill run), not a date published by NCBI. Migration 033 folds the
`document.withdrawn` column of 032's first revision into `withdrawn_date` and
drops it.

`import_file` collects `<DeleteCitation>` PMIDs (`parse_deleted_pmids()`,
numeric only; invalid entries are counted in `withdrawals_invalid`). Inside the
file's transaction, `_store_file` then:

1. records them (`RECORD_WITHDRAWN_SQL`, `ON CONFLICT DO NOTHING`);
2. marks their documents (`MARK_WITHDRAWN_SQL`);
3. marks the file's own staged records that are already listed as withdrawn
   (`MARK_STAGED_WITHDRAWN_SQL`).

Step 3 keeps any serial file order correct: a deletion imported before its
record still applies. With `--workers > 1`, a record and its deletion in two
files committed at the same moment cannot see each other (READ COMMITTED), so
`import_all_files` ends with one set-based pass over all recorded withdrawals
(`_reconcile_withdrawals`, `RECONCILE_WITHDRAWN_SQL`; reported as
`withdrawals_reconciled`). Such concurrent files can also deadlock; PostgreSQL
aborts one, the worker failure is logged, the file is not in the ledger, and a
re-run imports it.

The merge never touches `withdrawn_date`, so a later revision does not clear
it, and a record that reappears in a later file is marked again: withdrawals
are permanent, matching NCBI, which never reuses or re-instates a deleted PMID
(there is no element for it).

Per-file stats: `withdrawals_listed` (distinct PMIDs in DeleteCitation),
`withdrawals_invalid`, `documents_withdrawn` (documents newly marked; PMIDs not
in the database are recorded but mark nothing). `import_all_files` sums them
into `total_withdrawals_listed` / `total_documents_withdrawn`.

`backfill_withdrawals(file_type)` (CLI `backfill-withdrawals`) re-scans files
that were imported before this existed. It runs one transaction per file
(files without deletions open no connection) and is idempotent. It returns
`files_scanned`, `pmids_listed`, `pmids_invalid`, `pmids_recorded` (newly added
to `ingest.withdrawn_pmid`), `documents_marked` and `files_failed`. An
unreadable file is logged, listed and skipped; the CLI then exits 1. If none of
the selected directories holds a file it raises `FileNotFoundError`.

**Searches:** every SQL search function (`fulltext_search`, `bm25`,
`semantic_docsearch`, `semantic.chunksearch`, `chunksearch_document`,
`hybrid_chunksearch_document`) has always filtered on `withdrawn_date IS
NULL`. In `database.py`, `find_abstracts`, `find_abstract_ids`,
`search_by_embedding` and `search_with_semantic` filter too
(`NOT_WITHDRAWN_SQL`), as do the raw full-text queries in PaperChecker's search
coordinator and the paper reviewer's contradictory finder.
`tests/test_withdrawn_search_filters.py` pins this: it checks the latest
definition of each SQL function, and scans `src/` for full-text queries on
`document` without the filter. Fetching a document by id still returns it,
which is intended for existing references.

### Parsing notes (DTD layout)

`KeywordList` and `CommentsCorrectionsList` are children of
`MedlineCitation`, not of `Article` or `PubmedData`. The article's DOI is in
`PubmedData/ArticleIdList` (direct child); `.//ArticleIdList` would also reach
`ReferenceList/Reference/ArticleIdList` (the DOIs of cited works). Tests:
`tests/test_pubmed_bulk_importer_parsing.py`.

## Parallel import

`import_all_files(file_type, workers=N)`:

- Committed files are filtered up front (one ledger query).
- With `workers > 1`, the remaining files go to a `ProcessPoolExecutor` with
  the **spawn** context.
- `_init_import_worker(data_dir, conninfo)` builds each worker's importer from
  `DatabaseManager(auto_migrate=False, conninfo=<parent's conninfo>)`. **Do
  not let workers derive the database from the environment:** a fresh process
  re-imports `bmlibrarian.database`, which loads the default env file and
  could point somewhere else.
- Cancellation stops submitting; running files finish their own
  transactions.
- Spawn re-imports the parent's `__main__`, so callers must be real modules or
  scripts with an `if __name__ == "__main__"` guard (stdin scripts fail with
  `BrokenProcessPool`).

## Env file selection

`env_loader.resolve_env_file(environ, home)` is pure and tested:
`BMLIBRARIAN_ENV_FILE` (must exist, never a silent fallback), else
`~/.bmlibrarian/.env`, else none. `database.py` loads with `override=True`;
`migrations.py` and `utils/pdf_manager.py` with `override=False`.

## Import profile

`db_import_profile.ImportProfile`. Its server interactions are injected
callables; `for_server(conninfo)` builds the real ones.

- **apply:**
  1. Validate names (allow-list) and values (`^[0-9]+(kB|MB|GB|TB)?$`).
     `ALTER SYSTEM` cannot bind parameters.
  2. Require a superuser.
  3. Refuse while other `client backend` sessions exist (unless forced).
  4. Write the state file (the previous `postgresql.auto.conf` values per
     setting, None = RESET).
  5. Run `ALTER SYSTEM`, then `pg_reload_conf()`.
  6. `pg_ctl restart` if any managed setting has `pending_restart`.
- **restore:** the same, using the state file, which is then deleted.
- `pg_ctl` comes from the binary path in `postmaster.opts` (Postgres.app
  writes it unquoted, with spaces).
- **Connection pools break on restart.** Open them inside `import_profile()`
  and close them before it exits (the CLI's `run_import` does both and resets
  the `get_db_manager()` singleton with `close_database()`).

## Tests

| File | Covers | Needs DB |
|---|---|---|
| `tests/test_ncbi_https.py` | listing/MD5/Content-Range parsing; resume, Range ignored, corrupt stream, stale files | no |
| `tests/test_pubmed_bulk_download.py` | importer download paths, skipping, tracking, failures | no |
| `tests/test_pubmed_bulk_importer_parsing.py` | keyword/DOI/retraction/date_revised extraction | no |
| `tests/test_pubmed_bulk_importer_copy.py` | staging rows (unit); atomic store, idempotency, revisions, resume, rollback, parallel workers, withdrawals (either order), backfill, search exclusion | opt-in |
| `tests/test_migration_031_ingest_ledger.py` | migration 031, applied twice | opt-in |
| `tests/test_migration_032_033_withdrawn.py` | migrations 032 and 033, applied twice; 033 copies first-revision marks before dropping the column | opt-in |
| `tests/test_withdrawn_search_filters.py` | SQL search functions and Python full-text queries exclude withdrawn rows | hermetic |
| `tests/test_env_loader.py` | env selection, explicit conninfo | no |
| `tests/test_db_import_profile.py` | profile helpers and flow (fake server) | no |
| `tests/test_pubmed_bulk_cli.py` | CLI arguments and profile ordering | no |

The opt-in tests run only when `BMLIBRARIAN_TEST_DB_ENV` names the env file of
a **development** database with the BMLibrarian schema, and they refuse
`knowledgebase`:

```bash
BMLIBRARIAN_TEST_DB_ENV=~/.bmlibrarian/.env_pg18_dev uv run python -m pytest tests/test_pubmed_bulk_importer_copy.py
```
