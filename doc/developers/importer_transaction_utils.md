# Importer Transaction Utilities

Module: `bmlibrarian.importers.transaction_utils`

Shared per-record transaction isolation for bulk importers, fixing the
"poisoned transaction" data-loss class found in the July 2026 code review.

## The problem

Bulk importers (medRxiv, PubMed, Europe PMC, ClinicalTrials.gov, Retraction
Watch) process many records inside a single database transaction for
performance. Without per-record isolation, one bad record can destroy a whole
batch that was already partially counted as imported:

- If the per-record error handler calls `conn.rollback()`, every record
  written earlier in the same transaction (already counted as a success) is
  discarded.
- If the error handler does nothing, PostgreSQL leaves the connection in an
  aborted-transaction state ("current transaction is aborted, commands
  ignored until end of transaction block"), so every subsequent record fails
  too — and the final `conn.commit()` silently discards the entire
  transaction (PostgreSQL executes COMMIT of an aborted transaction as
  ROLLBACK).

## The fix: `record_savepoint`

```python
from bmlibrarian.importers.transaction_utils import record_savepoint

with conn.cursor() as cur:
    for record in records:
        try:
            with record_savepoint(cur, "my_importer_record"):
                # this record's INSERT/UPDATE statements
                ...
        except Exception as e:
            stats["errors"] += 1
            logger.error(f"Failed record: {e}")
            continue  # connection is healthy; next record proceeds
    conn.commit()
```

On success the savepoint is released; on failure the transaction is rolled
back **to the savepoint only** — discarding just that record's writes while
keeping every previously-written record and leaving the connection in a
healthy, non-aborted state.

## API

| Name | Purpose |
|------|---------|
| `record_savepoint(cur, name=DEFAULT_SAVEPOINT_NAME)` | Context manager wrapping one record's writes in `SAVEPOINT` / `RELEASE SAVEPOINT` / `ROLLBACK TO SAVEPOINT`. Re-raises the wrapped exception after rolling back. |
| `DEFAULT_SAVEPOINT_NAME` | Default savepoint identifier (`"record_import"`). |
| `MAX_SAVEPOINT_NAME_LENGTH` | Identifier length cap (63, PostgreSQL's limit). |

## Safety rules

Savepoint names are interpolated directly into SQL (neither PostgreSQL nor
SQLite can bind them as parameters), so they are validated against
`^[A-Za-z_][A-Za-z0-9_]*$` and **must always be hardcoded string literals in
the calling code** — never derived from user, file, network, or database
content.

## Testing

The helper works identically on psycopg3 (production) and Python's built-in
`sqlite3` (both support the same SAVEPOINT syntax), which is what makes the
hermetic importer tests in `tests/test_importer_savepoints.py` possible
without a live PostgreSQL instance.

## Current call sites

- `importers/medrxiv_importer.py` (`_process_papers`)
- `importers/pubmed_importer.py` (`_store_articles`)
- `importers/europe_pmc_importer.py` (`_upsert_batch`)
- `importers/clinicaltrials_importer.py` (`import_trials`)
- `importers/retraction_watch_importer.py` (`import_csv`)
