# Migration 008: Fact-Checker PostgreSQL Schema

## Overview

This migration refactors the fact-checker system from SQLite to PostgreSQL, eliminating data duplication and improving concurrent access capabilities.

## What Changed

### Architecture
- **Before**: SQLite database files (`.db`) stored separately from main BMLibrarian database
- **After**: PostgreSQL `factcheck` schema integrated into main knowledgebase database

### Key Improvements
1. **No Data Duplication**: Evidence now references `public.document(id)` directly (foreign key constraint)
2. **Concurrent Access**: Multiple users can review fact-checking results simultaneously
3. **Better Performance**: PostgreSQL connection pooling and optimized queries
4. **Unified Database**: All BMLibrarian data in one PostgreSQL database

### Breaking Changes
- **CLI**: Removed `--db-path`, `--json-only`, `--export-json` flags
- **Agent**: `FactCheckerAgent` no longer takes `db_path` or `use_database` parameters
- **GUI**: Review GUI loads directly from PostgreSQL (no more `.db` file selection)

## Running the Migration

### Prerequisites
1. PostgreSQL database with pgvector extension
2. BMLibrarian environment configured (`.env` file with database credentials)
3. psycopg >= 3.2.9 installed

### Step 1: Run Migration SQL

```bash
# From bmlibrarian root directory
psql -h localhost -U your_user -d knowledgebase -f migrations/008_create_factcheck_schema.sql
```

Or use your preferred PostgreSQL client to execute the migration.

### Step 2: Migrate Existing SQLite Data (Optional)

If you have existing fact-checker data in SQLite files:

```python
from bmlibrarian.factchecker.db.database import FactCheckerDB

# Initialize PostgreSQL database
db = FactCheckerDB()

# Import from legacy SQLite/JSON files
db.import_json_results('old_results.json', skip_existing=True)
```

The import process:
- Detects and skips duplicate statements
- Preserves existing AI evaluations and human annotations
- Validates document_id references against `public.document` table

### Step 3: Verify Migration

```bash
# Test fact-checker CLI with incremental mode (resume functionality)
uv run python fact_checker_cli.py test_statements.json --incremental -v

# Verify PostgreSQL schema
psql -d knowledgebase -c "\\dt factcheck.*"

# Check data
psql -d knowledgebase -c "SELECT COUNT(*) FROM factcheck.statements;"
```

## New Features Enabled

### Resume Functionality (Incremental Mode)

The fact-checker now supports automatic resume:

```bash
# Start fact-checking
python fact_checker_cli.py statements.json

# If interrupted (Ctrl+C), resume with:
python fact_checker_cli.py statements.json --incremental
```

The `--incremental` flag:
- Queries PostgreSQL for statements without AI evaluations
- Skips already-processed statements
- Continues from where it left off

### Concurrent Review

Multiple reviewers can now annotate simultaneously:

```bash
# Reviewer 1
python fact_checker_review_gui.py --user alice

# Reviewer 2 (simultaneous access)
python fact_checker_review_gui.py --user bob
```

PostgreSQL handles concurrent writes with row-level locking.

## Schema Details

### Tables Created

1. **factcheck.statements** - Biomedical statements to verify
2. **factcheck.annotators** - Human reviewers
3. **factcheck.ai_evaluations** - AI-generated fact-checks
4. **factcheck.evidence** - Literature citations (FK to public.document)
5. **factcheck.human_annotations** - Human review annotations
6. **factcheck.processing_metadata** - Batch processing sessions
7. **factcheck.export_history** - Data export audit trail

### Key Constraints

- **Foreign Key**: `factcheck.evidence.document_id` → `public.document(id)`
- **Unique Constraints**: Prevent duplicate statements and annotations
- **Check Constraints**: Validate enum values (evaluation, confidence, etc.)

### Helper Functions

- `factcheck.get_or_create_statement()` - Upsert statements
- `factcheck.has_ai_evaluation()` - Check processing status
- `factcheck.get_statements_needing_evaluation()` - Support incremental mode
- `factcheck.calculate_inter_annotator_agreement()` - Quality metrics

### Views

- `factcheck.v_complete_results` - Full results with AI + human annotations
- `factcheck.v_statements_needing_evaluation` - Unprocessed statements
- `factcheck.v_inter_annotator_agreement` - Agreement analysis
- `factcheck.v_model_accuracy` - Model performance metrics

## Backward Compatibility

### JSON Export/Import

JSON import/export still supported for data exchange:

```bash
# Export to JSON
python fact_checker_cli.py statements.json -o results.json

# Import JSON into PostgreSQL
python -c "from bmlibrarian.factchecker.db.database import FactCheckerDB; \
           FactCheckerDB().import_json_results('results.json')"
```

### Legacy SQLite Files

Old `.db` files can be converted:

1. Export SQLite to JSON using old version
2. Import JSON into PostgreSQL using new version

## Troubleshooting

### Migration fails with "relation does not exist"

Ensure migration 008 was run on the correct database:

```bash
psql -d knowledgebase -c "SELECT COUNT(*) FROM factcheck.statements;"
```

### "foreign key violation" on evidence insert

Verify document_id exists in public.document table:

```sql
SELECT id, title FROM document WHERE id = <your_document_id>;
```

### Performance issues with large datasets

Ensure indexes are created (automatic with migration):

```sql
SELECT indexname, tablename FROM pg_indexes WHERE schemaname = 'factcheck';
```

## Rollback (NOT RECOMMENDED)

If you must rollback:

```sql
DROP SCHEMA factcheck CASCADE;
```

**WARNING**: This deletes all fact-checker data. Export to JSON first if needed.

## Support

For issues or questions:
- Check migration logs: `migrations/migration.log` (if applicable)
- Review schema: `migrations/008_create_factcheck_schema.sql`
- BMLibrarian documentation: `doc/users/fact_checker_guide.md`
