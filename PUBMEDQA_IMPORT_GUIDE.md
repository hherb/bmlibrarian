# PubMedQA Abstract Import Guide

This guide explains how to import PubMedQA abstracts (CONTEXTS and LONG_ANSWER fields) into the `factcheck.statements` table.

## Overview

The PubMedQA dataset (`src/bmlibrarian/factchecker/ori_pqal.json`) contains 1000 biomedical questions with:
- **QUESTION**: The research question (stored as `statement_text`)
- **CONTEXTS**: Array of abstract paragraphs (to be imported as `context`)
- **LONG_ANSWER**: Detailed reasoning for the answer (to be imported as `long_answer`)
- **final_decision**: The answer (yes/no/maybe, stored as `expected_answer`)

## Prerequisites

1. **Database Setup**: Ensure PostgreSQL is running and credentials are configured in `.env` file
2. **Migration 009**: Run migration to add `context` and `long_answer` columns to the table

## Step 1: Run Migration 009

The migration adds two new columns to `factcheck.statements`:
- `context TEXT`: Stores joined abstract paragraphs from CONTEXTS field
- `long_answer TEXT`: Stores reasoning from LONG_ANSWER field

### Option A: Using Python Migration Manager

```bash
# Apply all pending migrations (recommended)
uv run python -c "from src.bmlibrarian.migrations import MigrationManager; \
    mm = MigrationManager.from_env(); \
    mm.apply_pending_migrations('migrations')"
```

### Option B: Manual SQL Execution

```bash
# Connect to PostgreSQL and run migration manually
psql -h localhost -U your_user -d knowledgebase -f migrations/009_add_context_long_answer_to_statements.sql
```

### Verify Migration

Check that the columns were added successfully:

```sql
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'factcheck' AND table_name = 'statements'
ORDER BY column_name;
```

You should see `context` and `long_answer` in the column list.

## Step 2: Import PubMedQA Abstracts

Use the `import_pubmedqa_abstracts.py` script to import the data.

### Dry Run (Preview Changes)

```bash
# Preview what will be imported without making changes
uv run python import_pubmedqa_abstracts.py src/bmlibrarian/factchecker/ori_pqal.json --dry-run
```

### Import Data

```bash
# Import abstracts into database
uv run python import_pubmedqa_abstracts.py src/bmlibrarian/factchecker/ori_pqal.json
```

## Import Behavior

The import script handles two scenarios:

### Scenario 1: Empty Table (Fresh Import)

If `factcheck.statements` is empty, the script will **INSERT** all 1000 records:
- Creates new records with all fields including `context` and `long_answer`
- Uses `ON CONFLICT DO NOTHING` to skip duplicates

### Scenario 2: Existing Data (Update)

If the table already contains data, the script will **UPDATE** existing records:
- Matches records by `statement_text` (the question)
- Updates **ONLY** `context` and `long_answer` fields
- **DOES NOT MODIFY** any other existing data (e.g., `expected_answer`, `review_status`, etc.)
- If a question doesn't exist, it will be inserted as a new record

## Data Validation

The import script performs comprehensive validation:

1. **Table Structure Validation**
   - Checks that `factcheck` schema exists
   - Verifies `factcheck.statements` table exists
   - Confirms `context` and `long_answer` columns are present

2. **JSON Structure Validation**
   - Validates JSON is a dictionary with PMID keys
   - Checks required fields: `QUESTION`, `CONTEXTS`, `LONG_ANSWER`, `final_decision`
   - Verifies data types (CONTEXTS must be array, QUESTION must be string, etc.)
   - Validates `final_decision` is one of: yes, no, maybe

3. **Data Integrity**
   - Uses database transactions for atomic operations
   - Reports errors without stopping the import
   - Provides detailed statistics on success/failures

## Testing JSON Structure

To validate the JSON file structure without database access:

```bash
# Test JSON structure and show statistics
uv run python test_json_structure.py src/bmlibrarian/factchecker/ori_pqal.json
```

This will display:
- Total entries (1000 questions)
- Statistics on contexts per entry (avg ~3.36 paragraphs)
- Decision distribution (yes: 55.2%, no: 33.8%, maybe: 11.0%)
- Sample entry with full context and long_answer

## Import Output

The script provides detailed output with progress reporting:

```
================================================================================
PubMedQA Abstract Importer
================================================================================

Loading JSON file: src/bmlibrarian/factchecker/ori_pqal.json

1. Validating table structure...
  ✓ Table structure validated successfully

2. Validating JSON structure...
  ✓ JSON structure validated successfully (1000 entries)

3. Importing data...

Table has 1000 existing rows. Updating records...
  Progress: 100/1000 records processed...
  Progress: 200/1000 records processed...
  Progress: 300/1000 records processed...
  ...
  Progress: 1000/1000 records processed...

================================================================================
Import Summary
================================================================================
  Total records in JSON:  1000
  Inserted (new):         0
  Updated (existing):     1000
  Skipped:                0
  Errors:                 0

✓ Import completed successfully!
```

**Progress Reporting**: The script reports progress every 100 records to provide feedback during long imports.

## Troubleshooting

### Error: Missing columns

**Symptom**: `Missing columns: context, long_answer. Run migration 009 first.`

**Solution**: Run migration 009 as described in Step 1.

### Error: Missing POSTGRES_USER or POSTGRES_PASSWORD

**Symptom**: `Could not create migration manager from environment`

**Solution**: Create a `.env` file in the project root with database credentials:

```bash
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=your_username
POSTGRES_PASSWORD=your_password
POSTGRES_DB=knowledgebase
```

### Error: JSON structure validation failed

**Symptom**: `Entry for PMID XXX missing fields: ...`

**Solution**: Verify you're using the correct JSON file. The file should match the PubMedQA format with PMID keys and required fields.

## Verification

After import, verify the data was imported correctly:

```sql
-- Check total records with context and long_answer
SELECT
    COUNT(*) as total_records,
    COUNT(context) as records_with_context,
    COUNT(long_answer) as records_with_long_answer
FROM factcheck.statements;

-- Sample a few records
SELECT
    statement_id,
    LEFT(statement_text, 60) as question,
    LEFT(context, 100) as context_preview,
    LEFT(long_answer, 100) as long_answer_preview
FROM factcheck.statements
WHERE context IS NOT NULL
LIMIT 5;
```

## Files Created

1. **migrations/009_add_context_long_answer_to_statements.sql**
   - Migration to add new columns

2. **import_pubmedqa_abstracts.py**
   - Main import script with validation

3. **test_json_structure.py**
   - JSON validation script (no database required)

4. **PUBMEDQA_IMPORT_GUIDE.md**
   - This documentation file

## Technical Details

### Column Definitions

```sql
ALTER TABLE factcheck.statements
ADD COLUMN IF NOT EXISTS context TEXT;

ALTER TABLE factcheck.statements
ADD COLUMN IF NOT EXISTS long_answer TEXT;
```

### Data Transformation

The `CONTEXTS` field (array of strings) is joined into a single text field:

```python
context = '\n\n'.join(entry['CONTEXTS'])
```

This preserves paragraph structure while storing as a single text column for easier querying and display.

### Upsert Logic

The script uses PostgreSQL's native UPSERT for efficient and atomic operations:

**Empty table (INSERT with conflict handling)**:
```sql
INSERT INTO factcheck.statements
(statement_text, input_statement_id, expected_answer, source_file, context, long_answer)
VALUES (%s, %s, %s, %s, %s, %s)
ON CONFLICT (statement_text) DO NOTHING
```

**Existing data (PostgreSQL native UPSERT)**:
```sql
INSERT INTO factcheck.statements
(statement_text, input_statement_id, expected_answer, source_file, context, long_answer)
VALUES (%s, %s, %s, %s, %s, %s)
ON CONFLICT (statement_text) DO UPDATE
SET context = EXCLUDED.context,
    long_answer = EXCLUDED.long_answer
RETURNING (xmax = 0) AS inserted
```

**Benefits of UPSERT approach**:
- Single atomic operation (no race conditions)
- More efficient than separate UPDATE + INSERT queries
- Only modifies `context` and `long_answer` on conflict
- Uses `RETURNING (xmax = 0)` to distinguish INSERT vs UPDATE

## Support

For issues or questions:
- Check the troubleshooting section above
- Review migration and import script code for detailed error messages
- Verify database connectivity and credentials
