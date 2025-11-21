# Fact-Checker Distribution System - Quick Start Guide

## Overview

This system enables you to distribute fact-check results to external reviewers for inter-rater reliability analysis. The workflow uses self-contained SQLite packages that require no PostgreSQL installation.

## Complete Workflow

### Step 1: Export Review Package from PostgreSQL

Generate a self-contained SQLite database with all data needed for review:

```bash
# Export all statements with AI evaluations and full document abstracts
python export_review_package.py --output review_package_2024.db --exported-by your_name
```

**What's Included:**
- All statements with AI evaluations
- Evidence citations with full document abstracts
- Document metadata (titles, PMIDs, DOIs)
- NO human annotations from other reviewers

**Output:** Single `.db` file (typically 100-500 MB for 1000 statements)

---

### Step 2: Distribute Review Package

Send the `.db` file to external reviewers via:
- Secure file sharing (Dropbox, Google Drive, etc.)
- Email attachment (if small enough)
- USB drive

**What Reviewers Need:**
- Python 3.12+
- Flet library (`pip install flet`)
- The review package `.db` file
- The `fact_checker_review_gui.py` script

---

### Step 3: Reviewer Annotates Statements

Each reviewer runs the GUI with the SQLite package:

```bash
# Launch review GUI with SQLite package
python fact_checker_review_gui.py --user alice --db-file review_package_2024.db
```

**Features:**
- Read-write mode: Annotations saved to SQLite in real-time
- Full abstract display for all citations
- Same interface as PostgreSQL version
- Works offline (no database server required)

**What Reviewers Do:**
- Review each statement
- Read AI evaluation and supporting citations
- Make their own evaluation (yes/no/maybe/unclear)
- Optionally add explanation text
- Navigate through statements

---

### Step 4: Export Human Evaluations

After reviewing, each reviewer exports ONLY their annotations:

```bash
# Export annotations to lightweight JSON file
python export_human_evaluations.py --db-file review_package_2024.db --annotator alice --output alice_evaluations.json
```

**Output:** Lightweight JSON file (typically 1-10 KB per statement) containing:
- `statement_id` - For matching during import
- `statement_text` - For validation to prevent mismatches
- `annotation` - Human evaluation (yes/no/maybe/unclear)
- `explanation` - Optional explanation text

**Reviewer sends back:** Just the small `.json` file (NOT the full `.db` file)

---

### Step 5: Re-import to PostgreSQL

Import all reviewers' annotations back into your main PostgreSQL database:

```bash
# Import evaluations from all reviewers
python import_human_evaluations.py alice_evaluations.json bob_evaluations.json charlie_evaluations.json
```

**What Happens:**
- Creates/updates annotator records (tagged with usernames)
- Validates statements match by ID and text
- Inserts/updates annotations (one per annotator per statement)
- Reports statistics (inserted, updated, errors)

**Import Behavior:**
- **Duplicate handling:** Updates existing annotation from same annotator
- **Validation:** Ensures statement text matches to prevent mismatches
- **Multi-file support:** Import multiple reviewers in one command

---

### Step 6: Analyze Inter-Rater Agreement

Query PostgreSQL to calculate agreement statistics:

```sql
-- View inter-annotator agreement
SELECT * FROM factcheck.v_inter_annotator_agreement;

-- Calculate agreement statistics
SELECT * FROM factcheck.calculate_inter_annotator_agreement();

-- Find statements with disagreements
SELECT statement_text, annotator1_annotation, annotator2_annotation
FROM factcheck.v_inter_annotator_agreement
WHERE agreement = FALSE;
```

---

## Example Session

### Scenario: Send Review Package to 3 External Reviewers

**1. Export Package (You):**
```bash
python export_review_package.py --output cardio_study_2024.db --exported-by john_doe
# Output: cardio_study_2024.db (250 MB, 500 statements)
```

**2. Distribute (You):**
- Send `cardio_study_2024.db` to Alice, Bob, Charlie via secure file sharing
- Send `fact_checker_review_gui.py` (or standalone package)

**3. Review (Alice, Bob, Charlie independently):**
```bash
# Alice reviews
python fact_checker_review_gui.py --user alice --db-file cardio_study_2024.db

# Bob reviews
python fact_checker_review_gui.py --user bob --db-file cardio_study_2024.db

# Charlie reviews
python fact_checker_review_gui.py --user charlie --db-file cardio_study_2024.db
```

**4. Export Annotations (Each reviewer):**
```bash
# Alice exports
python export_human_evaluations.py --db-file cardio_study_2024.db --annotator alice -o alice.json
# Output: alice.json (45 KB)

# Bob exports
python export_human_evaluations.py --db-file cardio_study_2024.db --annotator bob -o bob.json

# Charlie exports
python export_human_evaluations.py --db-file cardio_study_2024.db --annotator charlie -o charlie.json
```

**5. Send Back (Reviewers):**
- Alice sends: `alice.json` (45 KB)
- Bob sends: `bob.json` (47 KB)
- Charlie sends: `charlie.json` (43 KB)

**6. Re-import (You):**
```bash
python import_human_evaluations.py alice.json bob.json charlie.json
# Output:
# Files processed: 3/3
# Total annotations: 1500 (500 per reviewer)
# Successfully inserted: 1500
# Successfully updated: 0
# Errors: 0
```

**7. Analyze Agreement (You):**
```sql
-- PostgreSQL query
SELECT * FROM factcheck.calculate_inter_annotator_agreement();
-- Result: 85% agreement across all pairwise comparisons
```

---

## Command Reference

### Export Review Package
```bash
python export_review_package.py --output <file.db> [--exported-by <name>] [--session-id <id>]

# Options:
#   --output, -o      Output SQLite database file (required)
#   --session-id      Export only statements from specific session
#   --exported-by     Your username for audit trail
```

### Review GUI
```bash
python fact_checker_review_gui.py --user <username> --db-file <file.db> [--incremental] [--blind]

# Options:
#   --user            Reviewer username (required with SQLite)
#   --db-file         SQLite database file (omit for PostgreSQL)
#   --incremental     Only show unannotated statements
#   --blind           Hide original/AI annotations
```

### Export Human Evaluations
```bash
python export_human_evaluations.py --db-file <file.db> --annotator <username> --output <file.json>

# Options:
#   --db-file         SQLite database (omit for PostgreSQL)
#   --annotator       Annotator username to export
#   --output, -o      Output JSON file (required)
```

### Import Human Evaluations
```bash
python import_human_evaluations.py <file1.json> [file2.json ...] [--annotator <name>] [--dry-run]

# Options:
#   json_files        One or more JSON files with annotations
#   --annotator       Override username (if not in JSON)
#   --dry-run         Preview import without committing
```

---

## File Sizes

Typical file sizes for 1000 statements:

- **SQLite Review Package:** 100-500 MB
  - Includes full document abstracts, titles, authors
  - Self-contained, no external dependencies

- **Human Evaluation JSON:** 100-500 KB
  - Just annotations and minimal statement context
  - Tiny files for easy emailing

---

## Troubleshooting

### Error: "SQLite database file not found"
- Check file path is correct
- Ensure `.db` extension is present

### Error: "No annotator username specified"
- For SQLite GUI: Use `--user <username>` parameter
- For export: Use `--annotator <username>` parameter
- For import: Ensure JSON has `annotator_username` in metadata

### Error: "Statement text mismatch"
- Occurs during import when statement changed in PostgreSQL
- Check if database was modified after export
- Re-export fresh review package

### GUI shows "No abstract available"
- Check document was included in export
- Verify evidence references valid document_id
- Re-export package to include missing documents

---

## Best Practices

### For Distribution:
1. **Use descriptive filenames:** `cardio_study_2024_v1.db`
2. **Document export date:** Include in filename or metadata
3. **Test package locally:** Review 1-2 statements before distributing
4. **Provide instructions:** Send this quick start guide to reviewers

### For Reviewers:
1. **Use consistent username:** Same username for all reviews
2. **Export frequently:** Don't lose work by forgetting to export
3. **Add explanations:** Help identify disagreement sources
4. **Review systematically:** Go through statements in order

### For Analysis:
1. **Import all at once:** Process all reviewers' files together
2. **Check statistics:** Review import report for errors
3. **Validate totals:** Ensure all expected annotations imported
4. **Document conflicts:** Track disagreements for follow-up

---

## Security & Privacy

- **SQLite packages contain sensitive data:** Full abstracts and AI evaluations
- **Distribute securely:** Use encrypted channels, access control
- **Annotator privacy:** Usernames tracked, comply with privacy policies
- **No deletion:** Import is additive (creates/updates, never deletes)
- **Audit trail:** Export history tracked in factcheck.export_history

---

## Next Steps

1. Export your first review package
2. Test locally with GUI
3. Distribute to one reviewer as pilot
4. Process returned annotations
5. Scale to multiple reviewers

For detailed technical documentation, see `FACT_CHECKER_DISTRIBUTION_PLAN.md`.
