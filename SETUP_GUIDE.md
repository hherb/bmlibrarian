# BMLibrarian Setup and Battle Test Guide

This guide explains how to use the `initial_setup_and_download.py` script to set up a fresh BMLibrarian database and test the import functionality.

## Purpose

The `initial_setup_and_download.py` script is designed to:

1. **Create a test database** from scratch
2. **Apply the baseline schema** (tables, extensions, functions)
3. **Run all migrations** to bring the database to the current version
4. **Test MedRxiv import** by fetching recent preprints
5. **Test PubMed import** by searching for sample articles
6. **Verify end-to-end functionality** of the import pipeline

This is particularly useful for:
- Setting up development/test environments
- Verifying database migrations work correctly
- Battle-testing import scripts before production use
- Creating fresh instances of BMLibrarian

## Prerequisites

1. **PostgreSQL Server**: Running PostgreSQL instance with pgvector extension
2. **Python Dependencies**: BMLibrarian dependencies installed (`uv sync`)
3. **Database User**: PostgreSQL user with `CREATE DATABASE` privilege
4. **Network Access**: Ability to reach MedRxiv and PubMed APIs

## Quick Start

### 1. Create Configuration File

Copy the example environment file:

```bash
cp test_database.env.example test_database.env
```

Edit `test_database.env` and fill in your database credentials:

```bash
# Minimum required configuration
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=your_username
POSTGRES_PASSWORD=your_password
POSTGRES_DB=bmlibrarian_test  # Use a test database name!
```

**⚠️ IMPORTANT**: Use a **test database name**, not your production database! The script will create this database if it doesn't exist.

### 2. Run the Setup Script

```bash
# Full setup with all tests (recommended first run)
uv run python initial_setup_and_download.py test_database.env

# Quick setup with minimal imports
uv run python initial_setup_and_download.py test_database.env \
    --medrxiv-days 1 \
    --pubmed-max-results 10

# Schema setup only (no imports)
uv run python initial_setup_and_download.py test_database.env \
    --skip-medrxiv \
    --skip-pubmed
```

### 3. Review Results

The script will output a detailed summary:

```
==================================================================
BATTLE TEST SUMMARY
==================================================================
Database Schema Setup..................................... ✓ PASSED
MedRxiv Import............................................ ✓ PASSED
PubMed Import............................................. ✓ PASSED
==================================================================
Total operations: 3
Passed: 3
Failed: 0
==================================================================
```

## Command Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `env_file` | Path to .env configuration file | **(required)** |
| `--skip-medrxiv` | Skip MedRxiv import test | False |
| `--skip-pubmed` | Skip PubMed import test | False |
| `--medrxiv-days N` | Number of days to fetch from MedRxiv | 7 |
| `--medrxiv-download-pdfs` | Download PDFs during MedRxiv import | False |
| `--pubmed-max-results N` | Maximum PubMed results to import | 100 |
| `-v, --verbose` | Enable verbose logging | False |

## Usage Examples

### Example 1: Full Battle Test

Test everything with default settings:

```bash
uv run python initial_setup_and_download.py test_database.env
```

This will:
- Create database `bmlibrarian_test` (from your .env file)
- Apply baseline schema
- Apply all migrations (003-008)
- Import 7 days of MedRxiv preprints (metadata only)
- Import 100 PubMed articles matching "COVID-19 vaccine"

### Example 2: Quick Validation Test

Minimal import for fast validation:

```bash
uv run python initial_setup_and_download.py test_database.env \
    --medrxiv-days 1 \
    --pubmed-max-results 10
```

This runs a quick test with minimal data (completes in ~1-2 minutes).

### Example 3: Schema Setup Only

Set up database without running imports:

```bash
uv run python initial_setup_and_download.py test_database.env \
    --skip-medrxiv \
    --skip-pubmed
```

Useful for:
- Testing migration scripts
- Preparing a database for manual data import
- CI/CD pipeline database initialization

### Example 4: MedRxiv with PDFs

Test MedRxiv import including PDF download:

```bash
uv run python initial_setup_and_download.py test_database.env \
    --medrxiv-days 2 \
    --medrxiv-download-pdfs \
    --skip-pubmed
```

**Note**: PDF download significantly increases runtime and storage requirements.

### Example 5: Large Import Test

Stress test with substantial data:

```bash
uv run python initial_setup_and_download.py test_database.env \
    --medrxiv-days 30 \
    --pubmed-max-results 1000
```

## What Gets Installed

### Database Schema Components

1. **Extensions**:
   - `pgvector` - Vector similarity search
   - `pg_trgm` - Trigram-based text search
   - `plpython3u` - Python stored procedures

2. **Core Tables**:
   - `sources` - Data source registry (PubMed, MedRxiv, etc.)
   - `document` - Article metadata and full text
   - `authors` - Author information
   - `document_author` - Document-author relationships
   - `bmlibrarian_migrations` - Migration tracking

3. **Unpaywall Schema**:
   - `oa_locations` - Open access location data
   - Related tables for DOI-based OA lookup

4. **Migrations** (applied in order):
   - `003_create_audit_schema.sql` - Research workflow tracking
   - `004_update_audit_for_evaluators.sql` - Evaluator updates
   - `005_create_fulltext_search_function.sql` - Full-text search
   - `006_create_search_functions.sql` - BM25 and semantic search
   - `007_create_semantic_docsearch.sql` - Semantic document search
   - `008_create_factcheck_schema.sql` - Fact-checking schema

### Sample Data Imported

**MedRxiv** (with `--medrxiv-days 7`):
- Approximately 50-200 recent preprints
- Metadata: title, abstract, authors, DOI, publication date
- PDFs: Only if `--medrxiv-download-pdfs` is specified

**PubMed** (with `--pubmed-max-results 100`):
- 100 articles matching "COVID-19 vaccine"
- Metadata: title, abstract, authors, PMID, MeSH terms, publication date

## Verifying the Installation

After successful setup, you can verify the database:

### Check Migration Status

```bash
uv run python -c "
from src.bmlibrarian.migrations import MigrationManager
from pathlib import Path

manager = MigrationManager.from_env()
if manager:
    applied = manager._get_applied_migrations()
    print(f'Applied migrations ({len(applied)}):')
    for filename, checksum in applied:
        print(f'  - {filename}')
"
```

### Check Document Counts

```bash
# Connect to your database
psql -h localhost -U your_username -d bmlibrarian_test

# Check document counts by source
SELECT s.name, COUNT(d.id) as count
FROM sources s
LEFT JOIN document d ON s.id = d.source_id
GROUP BY s.name
ORDER BY count DESC;

# Expected output:
#      name      | count
# ---------------+-------
#  PubMed        |   100
#  medRxiv       |    50
```

### Test Search Functionality

```bash
uv run python -c "
from bmlibrarian.database import get_db_manager

db = get_db_manager()
with db.get_connection() as conn:
    with conn.cursor() as cur:
        # Test full-text search
        cur.execute('''
            SELECT title
            FROM fulltext_search('vaccine', 5)
            LIMIT 3
        ''')
        results = cur.fetchall()
        print('Sample search results:')
        for i, (title,) in enumerate(results, 1):
            print(f'{i}. {title[:80]}...')
"
```

## Troubleshooting

### Error: "Database already exists"

**Symptom**: Script fails because the database name is already in use.

**Solution**:
- Use a different database name in your .env file, OR
- Drop the existing database: `dropdb bmlibrarian_test`

### Error: "Missing required environment variables"

**Symptom**: Script exits with "Missing required environment variables: ..."

**Solution**:
- Check your .env file contains all required variables:
  - `POSTGRES_HOST`
  - `POSTGRES_USER`
  - `POSTGRES_PASSWORD`
  - `POSTGRES_DB`

### Error: "Permission denied to create database"

**Symptom**: PostgreSQL permission error during database creation.

**Solution**:
- Grant CREATE DATABASE privilege to your user:
  ```sql
  ALTER USER your_username CREATEDB;
  ```
- Or connect as a superuser (e.g., `postgres`)

### Error: "Extension vector does not exist"

**Symptom**: Migration fails with "extension vector does not exist".

**Solution**:
- Install pgvector extension on your PostgreSQL server
- Ubuntu/Debian: `sudo apt install postgresql-16-pgvector`
- macOS (Homebrew): `brew install pgvector`
- Or compile from source: https://github.com/pgvector/pgvector

### Warning: "tqdm not installed"

**Symptom**: Warning about missing tqdm package.

**Solution**:
- Install tqdm: `uv pip install tqdm`
- Or ignore (progress bars will be disabled, but functionality is unaffected)

### MedRxiv/PubMed Import Fails

**Symptom**: Import test fails with network or API errors.

**Solution**:
- Check internet connectivity
- Verify API endpoints are accessible:
  - MedRxiv: https://api.biorxiv.org/details/medrxiv
  - PubMed: https://eutils.ncbi.nlm.nih.gov/entrez/eutils
- Reduce import size (use `--medrxiv-days 1 --pubmed-max-results 10`)
- Check for rate limiting (add `NCBI_API_KEY` to your .env file)

## Environment File Reference

Complete list of supported environment variables:

```bash
# === Required ===
POSTGRES_HOST=localhost          # Database server hostname
POSTGRES_PORT=5432               # Database server port
POSTGRES_USER=username           # Database user
POSTGRES_PASSWORD=password       # Database password
POSTGRES_DB=bmlibrarian_test     # Database name (will be created)

# === Optional ===
PDF_BASE_DIR=~/knowledgebase/pdf # PDF storage directory
NCBI_EMAIL=you@example.com       # Email for NCBI (recommended)
NCBI_API_KEY=your_key_here       # NCBI API key (for higher rate limits)
OLLAMA_HOST=http://localhost:11434  # Ollama server (for embeddings)
```

## Next Steps

After successful setup:

1. **Generate Embeddings** (optional):
   ```bash
   uv run python embed_documents_cli.py count
   uv run python embed_documents_cli.py embed --limit 100
   ```

2. **Test the CLI**:
   ```bash
   uv run python bmlibrarian_cli.py
   ```

3. **Test the Research GUI**:
   ```bash
   uv run python bmlibrarian_research_gui.py
   ```

4. **Configure Agents**:
   ```bash
   uv run python bmlibrarian_config_gui.py
   ```

## CI/CD Integration

Example GitHub Actions workflow:

```yaml
name: Database Setup Test

on: [push, pull_request]

jobs:
  test-setup:
    runs-on: ubuntu-latest

    services:
      postgres:
        image: pgvector/pgvector:pg16
        env:
          POSTGRES_PASSWORD: testpass
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.12'

      - name: Install uv
        run: pip install uv

      - name: Install dependencies
        run: uv sync

      - name: Create test env file
        run: |
          cat > test.env <<EOF
          POSTGRES_HOST=postgres
          POSTGRES_PORT=5432
          POSTGRES_USER=postgres
          POSTGRES_PASSWORD=testpass
          POSTGRES_DB=bmlibrarian_ci_test
          EOF

      - name: Run setup and test
        run: |
          uv run python initial_setup_and_download.py test.env \
            --skip-medrxiv \
            --skip-pubmed
```

## See Also

- [Main Documentation](README.md)
- [Migration System Guide](migrations/README.md)
- [MedRxiv Import Guide](doc/users/medrxiv_import_guide.md)
- [PubMed Import Documentation](src/bmlibrarian/importers/README.md)
- [Developer Guide](CLAUDE.md)
