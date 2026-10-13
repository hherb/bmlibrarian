# PubMed Bulk Import Guide

`pubmed_bulk_cli.py` keeps a local mirror of PubMed: it downloads the annual
baseline (about 1 300 files, about 38 M records) and the daily update files
from the NCBI FTP server, and imports them into the BMLibrarian database.

## Quick start

```bash
# Download, then import (8 parallel workers by default)
uv run python pubmed_bulk_cli.py download-baseline
uv run python pubmed_bulk_cli.py import --type baseline

# Keep the mirror current
uv run python pubmed_bulk_cli.py sync --updates-only

# Progress and statistics
uv run python pubmed_bulk_cli.py status
```

To import into another database (for example a PostgreSQL 18 server), select
its environment file. See "Database Environment File" in
`configuration_guide.md`:

```bash
BMLIBRARIAN_ENV_FILE=~/.bmlibrarian/.env_pg18 uv run python pubmed_bulk_cli.py import --type baseline
```

## Stopping and resuming

**An import can be stopped at any moment** (Ctrl-C, closing the terminal,
even a crash or power loss) **and resumed by running the same command
again.**

Each file is stored in a single database transaction, together with an entry
in the import ledger (`ingest.ledger`). After an interruption, a file is
either completely in the database or not at all. On the next run, files
already in the ledger are skipped and the rest are imported. Running the
command again after a complete import does nothing.

To re-import one file deliberately (for example after a parser fix), delete
its row from `ingest.ledger`, or use `force=True` from Python.

## Speed: parallel workers

```bash
uv run python pubmed_bulk_cli.py import --type baseline --workers 8
```

`--workers` (default: 8, or fewer on machines with fewer cores) imports that
many files at once, each in its own process. Measured on an Apple M3 Max with
PostgreSQL 18 and default server settings: 8 workers imported 2 729
articles/s, against 782/s with one worker.

The order in which files finish does not matter. When a PubMed record appears
more than once (PubMed republishes revised records), **the most recently
revised version always wins**, according to the record's `DateRevised`.

## Speed: the import profile (borrowing RAM for the import)

```bash
uv run python pubmed_bulk_cli.py import --type baseline --import-profile
```

By default the database server uses little memory and checkpoints often,
which slows large imports. `--import-profile` temporarily gives the server
more memory (32 GB of shared buffers) and a large write-ahead-log allowance
for the duration of the import, then **restores your normal settings
automatically**. Day to day that memory stays free for other work, such as
running local language models.

What to know:

- **The database server restarts twice**, once when the profile is applied
  and once when it is restored. This drops every connection to *that server*,
  including other applications' databases on it. The import therefore refuses
  to apply the profile while other clients are connected; close them, or add
  `--force-profile`.
- It needs a database role with superuser rights (the settings are changed
  with `ALTER SYSTEM`).
- **If an import is killed**, the server stays in the import profile, and a
  resumed import keeps using it and restores it at the end. To restore it by
  hand:

  ```bash
  uv run python pubmed_bulk_cli.py profile status
  uv run python pubmed_bulk_cli.py profile restore
  ```

  The original values are kept in `~/.bmlibrarian/pg_import_profile_<port>.json`
  until the restore is done.

## What is imported

For each record:
- title and abstract, with Markdown formatting (section labels, sub- and
  superscripts, emphasis);
- authors, journal, publication date, DOI, MeSH terms;
- **author keywords**;
- the revision date.

Transparency data goes to `transparency.document_metadata`: grants,
publication types, author affiliations, and **retraction status**, including
retraction cross-references.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `BMLIBRARIAN_ENV_FILE=… does not exist` | The named env file is missing; fix the path (there is deliberately no fallback). |
| `other client session(s) would be dropped by the restart` | Another application is connected to the server; close it, or use `--force-profile`. |
| `the import profile needs a superuser connection` | Use a superuser role, or import without `--import-profile`. |
| Import restarts files you thought were done | Only files whose transaction committed are in `ingest.ledger`; files that were in progress are redone, as designed. |
