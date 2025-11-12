# Fact-Checker SQLite to PostgreSQL Migration Guide

This guide explains how to migrate your fact-checker data from the legacy SQLite database to the new PostgreSQL schema.

## Prerequisites

1. **PostgreSQL database** with the `factcheck` schema already created
   - Run migration `008_create_factcheck_schema.sql` if not already applied
   - Verify with: `psql -d knowledgebase -c "\dn factcheck"`

2. **Python environment** with BMLibrarian installed
   - `uv sync` (if using uv)
   - or your preferred Python environment manager

3. **Database credentials** configured in `.env` file:
   ```bash
   POSTGRES_DB=knowledgebase
   POSTGRES_USER=your_user
   POSTGRES_PASSWORD=your_password
   POSTGRES_HOST=localhost
   POSTGRES_PORT=5432
   ```

4. **SQLite database file** with your fact-checker data

## Migration Steps

### Step 1: Locate Your SQLite Database

Find your fact-checker SQLite database file. Common locations:
- `~/.bmlibrarian/factchecker.db`
- `~/factchecker_results.db`
- Any `.db` file created by the fact-checker GUI or CLI

### Step 2: Upload Database (if using GitHub/Cloud)

If you're working in a cloud environment like GitHub Codespaces:

1. Upload your `.db` file to the repository:
   ```bash
   # Option A: Via git (if small enough)
   cp /path/to/your/factchecker.db /home/user/bmlibrarian/
   git add factchecker.db
   git commit -m "Add fact-checker database for migration"
   git push

   # Option B: Via GitHub web interface
   # - Navigate to repository
   # - Click "Add file" > "Upload files"
   # - Upload your .db file
   ```

2. Or use a temporary location (won't be committed):
   ```bash
   cp /path/to/your/factchecker.db /tmp/factchecker.db
   ```

### Step 3: Run Dry-Run (Recommended)

First, run a dry-run to see what will be migrated without making changes:

```bash
cd /home/user/bmlibrarian

# Dry run to preview migration
uv run python scripts/migrate_factchecker_sqlite_to_postgres.py \
    --sqlite-db /path/to/your/factchecker.db \
    --dry-run \
    --verbose
```

Review the output to ensure:
- All expected tables are found
- Record counts look correct
- No unexpected errors

### Step 4: Run Full Migration

Once satisfied with the dry-run, execute the actual migration:

```bash
# Run full migration
uv run python scripts/migrate_factchecker_sqlite_to_postgres.py \
    --sqlite-db /path/to/your/factchecker.db \
    --verbose
```

**Options:**
- `--skip-existing`: Skip statements already in PostgreSQL (useful for incremental migrations)
- `--dry-run`: Preview without making changes
- `--verbose`: Show detailed progress

### Step 5: Verify Migration

Check that data was migrated successfully:

```sql
-- Connect to PostgreSQL
psql -d knowledgebase

-- Check record counts
SELECT 'statements' as table_name, COUNT(*) FROM factcheck.statements
UNION ALL
SELECT 'ai_evaluations', COUNT(*) FROM factcheck.ai_evaluations
UNION ALL
SELECT 'evidence', COUNT(*) FROM factcheck.evidence
UNION ALL
SELECT 'human_annotations', COUNT(*) FROM factcheck.human_annotations
UNION ALL
SELECT 'annotators', COUNT(*) FROM factcheck.annotators;

-- View sample data
SELECT * FROM factcheck.statements LIMIT 5;

-- Check latest evaluations
SELECT * FROM factcheck.v_complete_results LIMIT 5;
```

## Migration Script Features

### What Gets Migrated

The script migrates all data from these SQLite tables:

1. **statements** - Biomedical statements to be fact-checked
2. **annotators** - Human reviewers
3. **ai_evaluations** - AI-generated evaluations (with versioning)
4. **evidence** - Literature citations supporting evaluations
5. **human_annotations** - Human review annotations
6. **processing_metadata** - Batch processing sessions
7. **export_history** - Export audit trail

### ID Mapping

The script maintains internal ID mappings to preserve relationships:
- SQLite `statements.id` → PostgreSQL `statements.statement_id`
- SQLite `annotators.id` → PostgreSQL `annotators.annotator_id`
- SQLite `ai_evaluations.id` → PostgreSQL `ai_evaluations.evaluation_id`

All foreign key relationships are preserved.

### Error Handling

- Skips records with missing foreign key references
- Logs errors without stopping the migration
- Provides detailed summary at the end
- Supports `--skip-existing` for idempotent migrations

### Progress Reporting

The script provides real-time progress updates:
```
Migrating statements...
  Migrated 100 statements...
  Migrated 200 statements...
✓ Statements: 250/250
```

## Common Issues

### Issue 1: Missing document_id in evidence

**Error:** `Invalid document_id for evidence X: None`

**Solution:** Some evidence records may have NULL `document_id`. These are skipped automatically. Check your SQLite database:

```sql
-- In SQLite
SELECT COUNT(*) FROM evidence WHERE document_id IS NULL;
```

### Issue 2: Database connection failed

**Error:** `could not connect to server`

**Solution:** Verify PostgreSQL is running and credentials are correct:

```bash
# Test connection
psql -d knowledgebase -c "SELECT 1"

# Check .env file
cat .env | grep POSTGRES
```

### Issue 3: Foreign key constraint violations

**Error:** `violates foreign key constraint`

**Solution:** Ensure the `factcheck` schema exists and `document` table has the referenced IDs:

```sql
-- Check if factcheck schema exists
\dn factcheck

-- Check if document IDs exist
SELECT COUNT(*) FROM document
WHERE id IN (SELECT DISTINCT document_id FROM factcheck.evidence);
```

## Post-Migration

### Test the Fact-Checker GUI

Verify the migration worked by loading the PostgreSQL data:

```bash
# Launch fact-checker review GUI (now uses PostgreSQL)
uv run python fact_checker_review_gui.py
```

The GUI should now connect to PostgreSQL instead of SQLite and display all your migrated data.

### Update Applications

All BMLibrarian fact-checker applications now use PostgreSQL by default:
- ✅ `fact_checker_cli.py` - Uses PostgreSQL
- ✅ `fact_checker_review_gui.py` - Uses PostgreSQL
- ✅ All new evaluations saved to PostgreSQL

### Backup Considerations

After successful migration:

1. **Keep SQLite backup:**
   ```bash
   # Move original to backup location
   mv /path/to/factchecker.db /path/to/factchecker.db.backup
   ```

2. **PostgreSQL backups:**
   ```bash
   # Backup PostgreSQL factcheck schema
   pg_dump -d knowledgebase -n factcheck -F c -f factcheck_backup.dump

   # Restore if needed
   pg_restore -d knowledgebase -c -n factcheck factcheck_backup.dump
   ```

## Advanced Usage

### Incremental Migration

If you've already migrated some data and want to add new records:

```bash
# Only migrate new/missing records
uv run python scripts/migrate_factchecker_sqlite_to_postgres.py \
    --sqlite-db /path/to/updated_factchecker.db \
    --skip-existing \
    --verbose
```

### Migration from Multiple Databases

If you have multiple SQLite databases to consolidate:

```bash
# Migrate first database
uv run python scripts/migrate_factchecker_sqlite_to_postgres.py \
    --sqlite-db /path/to/db1.db

# Migrate second database (skip duplicates)
uv run python scripts/migrate_factchecker_sqlite_to_postgres.py \
    --sqlite-db /path/to/db2.db \
    --skip-existing
```

## Getting Help

If you encounter issues:

1. Check the migration logs for specific error messages
2. Verify database connections with `psql`
3. Run with `--verbose --dry-run` to diagnose issues
4. Check the [BMLibrarian documentation](../doc/developers/fact_checker_system.md)

## Schema Differences

### SQLite → PostgreSQL Field Mappings

| SQLite Field | PostgreSQL Field | Notes |
|--------------|------------------|-------|
| `id` | `statement_id` | Auto-incrementing BIGSERIAL |
| `id` (ai_evaluations) | `evaluation_id` | With version support |
| `id` (evidence) | `evidence_id` | References `public.document` |
| `agent_config` (TEXT) | `agent_config` (JSONB) | Automatically converted |
| `config_snapshot` (TEXT) | `config_snapshot` (JSONB) | Automatically converted |

### New PostgreSQL Features

The PostgreSQL schema adds several enhancements:

- **Views:** `v_complete_results`, `v_model_accuracy`, `v_inter_annotator_agreement`
- **Functions:** `get_or_create_statement()`, `calculate_inter_annotator_agreement()`
- **Proper JSONB:** Native JSON support for configuration data
- **Better indexes:** Optimized for large-scale queries
- **No duplication:** Evidence links to `public.document` table

## Success Criteria

Your migration is complete when:

- ✅ All records migrated successfully (check summary)
- ✅ Zero or minimal errors reported
- ✅ PostgreSQL counts match SQLite counts
- ✅ Fact-checker GUI displays all data correctly
- ✅ No foreign key constraint violations

Congratulations! Your fact-checker data is now in PostgreSQL. 🎉
