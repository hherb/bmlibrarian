# PubMed Bulk Import — Developer Notes

Code: `src/bmlibrarian/importers/pubmed_bulk_importer.py`,
`src/bmlibrarian/db_import_profile.py`, `src/bmlibrarian/env_loader.py`, CLI
`pubmed_bulk_cli.py`. Schema: `migrations/031_ingest_ledger_and_revisions.sql`.
Background and measurements: `doc/planning/rust/implementation_plan.md`
(Phase A) and `spikes/pubmed-ingest/FINDINGS.md`.

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
| `tests/test_pubmed_bulk_importer_parsing.py` | keyword/DOI/retraction/date_revised extraction | no |
| `tests/test_pubmed_bulk_importer_copy.py` | staging rows (unit); atomic store, idempotency, revisions, resume, rollback, parallel workers | opt-in |
| `tests/test_migration_031_ingest_ledger.py` | migration 031, applied twice | opt-in |
| `tests/test_env_loader.py` | env selection, explicit conninfo | no |
| `tests/test_db_import_profile.py` | profile helpers and flow (fake server) | no |
| `tests/test_pubmed_bulk_cli.py` | CLI arguments and profile ordering | no |

The opt-in tests run only when `BMLIBRARIAN_TEST_DB_ENV` names the env file of
a **development** database with the BMLibrarian schema, and they refuse
`knowledgebase`:

```bash
BMLIBRARIAN_TEST_DB_ENV=~/.bmlibrarian/.env_pg18_dev uv run python -m pytest tests/test_pubmed_bulk_importer_copy.py
```
