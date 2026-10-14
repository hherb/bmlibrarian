# BMLibrarian Database Migrations

This directory contains database migration files for the BMLibrarian knowledge base.

## Migration System

BMLibrarian uses a custom migration system managed by the `MigrationManager` class in `src/bmlibrarian/migrations.py`. Migrations are tracked in the `bmlibrarian_migrations` table.

## Naming Convention

Migration files must follow this naming pattern:

```
NNN_descriptive_name.sql
```

Where:
- `NNN` is a zero-padded sequence number (e.g., 001, 002, 003)
- `descriptive_name` is a brief description using underscores
- Extension must be `.sql`

Examples:
- `003_create_audit_schema.sql`
- `004_update_audit_for_evaluators.sql`
- `005_create_fulltext_search_function.sql`

## Migration File Structure

Each migration file should include:

1. **Header comments** with metadata:
   ```sql
   -- Migration: [Title]
   -- Description: [Detailed description]
   -- Author: BMLibrarian
   -- Date: YYYY-MM-DD
   ```

2. **Idempotent operations**: Use `IF EXISTS`, `IF NOT EXISTS`, etc. to allow re-running
   ```sql
   DROP FUNCTION IF EXISTS my_function(text, integer);
   CREATE TABLE IF NOT EXISTS my_table (...);
   ```

3. **Section markers** for organization:
   ```sql
   -- ============================================================================
   -- Section Description
   -- ============================================================================
   ```

4. **Comments** explaining the purpose of each operation

5. **Permissions**: Grant appropriate access to database roles

6. **Documentation**: Add COMMENT ON statements for functions/tables

## Running Migrations

### From Python Code

```python
from src.bmlibrarian.migrations import MigrationManager
from pathlib import Path

# Create manager from environment variables
manager = MigrationManager.from_env()

# Apply all pending migrations
applied = manager.apply_pending_migrations(Path('migrations'))
print(f'Applied {applied} migrations')
```

### From Command Line

```bash
# Apply pending migrations
uv run python -c "
from src.bmlibrarian.migrations import MigrationManager
from pathlib import Path

manager = MigrationManager.from_env()
if manager:
    applied = manager.apply_pending_migrations(Path('migrations'))
    print(f'Total migrations applied: {applied}')
"
```

### Manual Application (Not Recommended)

```bash
# Apply migration directly with psql (bypasses tracking)
psql -d knowledgebase -f migrations/005_create_fulltext_search_function.sql
```

**Warning**: Manual application doesn't update the `bmlibrarian_migrations` table, which can cause issues.

## Checking Migration Status

### View Applied Migrations

```sql
SELECT id, filename, LEFT(checksum, 16) || '...' as checksum, applied_at
FROM bmlibrarian_migrations
ORDER BY id;
```

### Check if Specific Migration Applied

```sql
SELECT * FROM bmlibrarian_migrations
WHERE filename = '005_create_fulltext_search_function.sql';
```

## Creating New Migrations

1. **Determine next sequence number**:
   ```bash
   ls -1 migrations/*.sql | tail -1
   # If last file is 005_..., next should be 006_...
   ```

2. **Create migration file**:
   ```bash
   touch migrations/006_your_migration_name.sql
   ```

3. **Write migration SQL** following the structure above

4. **Test migration**:
   ```bash
   # Test on development database first
   POSTGRES_DB=bmlibrarian_dev uv run python -c "..."
   ```

5. **Apply to production** (with caution):
   ```bash
   uv run python -c "from src.bmlibrarian.migrations import MigrationManager; ..."
   ```

## Migration Safety Guidelines

### DO:
- ✅ Use `IF EXISTS` / `IF NOT EXISTS` for idempotency
- ✅ Include comprehensive comments
- ✅ Test on development database first
- ✅ Use transactions where appropriate
- ✅ Add permissions grants
- ✅ Document functions/tables with COMMENT ON
- ✅ Keep migrations focused (one logical change per file)

### DON'T:
- ❌ Modify existing migration files after they're applied
- ❌ Delete migration files from the directory
- ❌ Skip sequence numbers in naming
- ❌ Make destructive changes without backups
- ❌ Apply untested migrations to production
- ❌ Hardcode database names (use current database)

## Migration Tracking

The migration system uses SHA-256 checksums to detect changes to migration files:

```sql
CREATE TABLE bmlibrarian_migrations (
    id SERIAL PRIMARY KEY,
    filename VARCHAR(255) NOT NULL UNIQUE,
    checksum VARCHAR(64) NOT NULL,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

- **filename**: Migration file name (e.g., `005_create_fulltext_search_function.sql`)
- **checksum**: SHA-256 hash of the file contents
- **applied_at**: Timestamp when migration was applied

## Rollback Strategy

BMLibrarian migrations don't include automatic rollback. For rollback:

1. **Create a new migration** that reverses the changes:
   ```
   006_add_feature.sql        # Original migration
   007_rollback_feature.sql   # Rollback migration
   ```

2. **Document rollback procedure** in comments:
   ```sql
   -- To rollback this migration, apply 007_rollback_feature.sql
   ```

3. **For functions/views**: Simply create a new migration with `DROP` statements

4. **For schema changes**: Create reverse migration with care

## Current Migrations

| ID | Filename | Description | Date |
|----|----------|-------------|------|
| 003 | 003_create_audit_schema.sql | Create Audit Schema for Research Workflow Tracking | 2025-11-05 |
| 004 | 004_update_audit_for_evaluators.sql | Update Audit Schema to Use Evaluators | 2025-11-05 |
| 005 | 005_create_fulltext_search_function.sql | Create Full-Text Search Function | 2025-11-08 |
| 006 | 006_create_search_functions.sql | Create BM25 and Semantic Search Functions | 2025-11-09 |
| 007 | 007_create_semantic_docsearch.sql | Create Semantic Document Search Convenience Function | 2025-11-10 |
| 008 | 008_create_factcheck_schema.sql | Create Factcheck Schema for Biomedical Statement Verification | 2025-11-12 |
| 009 | 009_add_context_long_answer_to_statements.sql | Add context and long_answer columns to factcheck.statements | 2025-11-19 |
| 010 | 010_create_papercheck_schema.sql | Create PaperCheck Schema for Paper Abstract Weight Assessment | 2025-11-21 |
| 011 | 011_add_paper_weight_schema.sql | Create Paper Weight Assessment Schema | 2025-11-21 |
| 012 | 012_create_bmlsettings_schema.sql | Create BMLibrarian User Settings Schema | 2025-11-22 |
| 013 | 013_create_debug_schema.sql | Create Debug Schema for PDF Conversion Tracking | 2025-11-22 |
| 014 | 014_add_pgcrypto_extension.sql | Add pgcrypto extension | 2025-11-22 |
| 015 | 015_create_semantic_chunking_schema.sql | Create Semantic Chunking Schema | 2025-11-23 |
| 016 | 016_add_source_metadata_to_abstracts_checked.sql | Add source_metadata column to abstracts_checked | 2025-11-23 |
| 017 | 017_add_generation_metadata_columns.sql | Add generation_metadata columns to papercheck tables | 2025-11-23 |
| 018 | 018_create_document_specific_search_functions.sql | Create Document-Specific Semantic Search Functions | 2025-11-24 |
| 019 | 019_create_pdf_download_history.sql | Create PDF Download History Table | 2025-11-25 |
| 020 | 020_add_chunk_tsvector_hybrid_search.sql | Add ts_vector to semantic.chunks and create hybrid search function | 2025-11-26 |
| 021 | 021_create_thesaurus_schema.sql | Create Medical Thesaurus Schema | 2025-11-26 |
| 022 | 022_create_results_cache_schema.sql | Create Results Cache Schema | 2025-11-26 |
| 023 | 023_create_writing_schema.sql | Create Writing Schema | 2025-11-27 |
| 024 | 024_create_benchmarking_schema.sql | Create Benchmarking Schema for Model Performance Evaluation | 2025-11-28 |
| 025 | 025_create_audit_validation_schema.sql | Create Human Validation Schema for Audit Trail | 2025-11-28 |
| 026 | 026_create_unified_evaluations_schema.sql | Create Unified Evaluations Schema | 2025-12-07 |
| 027 | 027_create_pubmed_api_search_tables.sql | Create PubMed API Search Tracking Tables | 2025-12-13 |
| 028 | 028_create_mesh_schema.sql | Create MeSH (Medical Subject Headings) Schema | 2025-12-13 |
| 029 | 029_create_transparency_schema.sql | Create transparency schema | 2026-02-13 |
| 030 | 030_extend_settings_categories.sql | Extend bmlsettings category whitelists | 2026-07-19 |
| 031 | 031_ingest_ledger_and_revisions.sql | Resumable bulk-import bookkeeping and revision-aware merges | 2026-10-13 |
| 032 | 032_withdrawn_documents.sql | PubMed withdrawals (DeleteCitation) are marked, not deleted | 2026-10-14 |

031 and 032 carry the PubMed bulk-import changes (resumable ledger,
revision-aware merges, withdrawals). See
`doc/developers/pubmed_bulk_import_system.md`. Both are additive: new nullable
columns (a metadata-only change, no table rewrite), new tables in schema
`ingest`, a re-defined trigger function and an index storage option.

## The Test Suite Never Migrates Production

While pytest is loaded, `MigrationManager.apply_pending_migrations()` and
`initialize_database()` raise `ProtectedDatabaseError` for a protected database
(`knowledgebase`). `DatabaseManager` skips its auto-migration there and opens
its connections read-only (`bmlibrarian.db_test_guard`). Point tests that need
a writable database at a development database, either with
`BMLIBRARIAN_ENV_FILE` or with the opt-in `BMLIBRARIAN_TEST_DB_ENV` tests.

This guard was added after a test run on 2026-10-13/14 auto-applied 031 and
032 to production. The owner chose to keep both migrations there.

## Environment Variables

The migration system requires these environment variables (in `.env`):

```bash
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=your_user
POSTGRES_PASSWORD=your_password
POSTGRES_DB=knowledgebase
```

## Troubleshooting

### Migration fails with "already exists"
- Ensure your migration uses `IF EXISTS` / `IF NOT EXISTS`
- Check if migration was partially applied

### Migration not detected as pending
- Verify filename matches pattern `NNN_*.sql`
- Check file is in the `migrations/` directory
- Ensure file has `.sql` extension

### Permission denied errors
- Check database user has appropriate permissions
- Add GRANT statements to migration if needed

### Checksum mismatch
- Never modify migration files after they're applied
- If you must change, create a new migration instead

## See Also

- [Migration Manager Code](../src/bmlibrarian/migrations.py)
- [Migration Tests](../tests/test_migrations.py)
- [PostgreSQL Search Functions Documentation](../doc/developers/postgres_search_functions.md)
