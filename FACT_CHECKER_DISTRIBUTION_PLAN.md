# Fact-Checker Distribution System - Implementation Plan

## Overview

This plan outlines the implementation of a complete distribution system for external fact-checker review, enabling inter-rater reliability analysis across multiple human evaluators.

## Objectives

1. **Export Review Packages**: Create self-contained SQLite databases with ALL data needed for human review (statements, AI evaluations, citations, document abstracts)
2. **Portable Review**: Enable the GUI to work with SQLite packages (no PostgreSQL required for reviewers)
3. **Human Evaluation Export**: Export ONLY human annotations as lightweight JSON files
4. **Re-import System**: Import human evaluations back into PostgreSQL with proper username tagging
5. **Inter-Rater Analysis**: Support evaluation of agreement between multiple human reviewers

## Architecture

### Current State
- **PostgreSQL Database**:
  - `factcheck` schema: statements, ai_evaluations, evidence, human_annotations
  - `public` schema: `document` table with title, abstract, authors, etc.
- **GUI Dependencies**:
  - Queries `factcheck.evidence` for citations
  - Queries `public.document` (via `document_id` FK) for full abstracts and metadata
- **Data Flow**: GUI → PostgreSQL → Display citations with full abstracts

### Target State
- **Dual Database Support**:
  - PostgreSQL: Main database (production)
  - SQLite: Portable review packages (distribution)
- **Database Abstraction**: Unified interface supporting both backends
- **Export/Import Pipeline**: PostgreSQL → SQLite → Human Review → JSON → PostgreSQL

## Component Design

### 1. SQLite Review Package Schema

**File**: `src/bmlibrarian/factchecker/db/sqlite_schema.sql`

Tables to include:
- `statements` - Biomedical statements to review (from factcheck.statements)
- `ai_evaluations` - AI-generated evaluations (from factcheck.ai_evaluations)
- `evidence` - Citations/evidence (from factcheck.evidence)
- `documents` - **Full document data** (from public.document, filtered to evidence-referenced docs only)
- `human_annotations` - Human annotations (for current reviewer only)
- `annotators` - Annotator metadata
- `package_metadata` - Export date, PostgreSQL source, version, etc.

**Key Differences from PostgreSQL**:
- No foreign keys to separate schemas (everything in one SQLite file)
- `evidence.document_id` references `documents.id` (within SQLite)
- Simplified data types (no JSONB, use JSON TEXT)
- All timestamps as TEXT (ISO 8601 format)

### 2. Export Script

**File**: `export_review_package.py`

**Purpose**: Generate self-contained SQLite review packages from PostgreSQL

**Functionality**:
```bash
# Export all statements (full package)
python export_review_package.py --output review_package_2024.db

# Export specific statements (filtered)
python export_review_package.py --output review_subset.db --statement-ids 1,2,3,100-200

# Export with session filter
python export_review_package.py --output session_abc.db --session-id abc123

# Include specific annotator's existing annotations
python export_review_package.py --output package.db --include-annotator alice
```

**Implementation Steps**:
1. Connect to PostgreSQL
2. Query statements with AI evaluations
3. Query evidence for those statements
4. Extract unique `document_id` values from evidence
5. Query `public.document` table for those document IDs (title, abstract, authors, etc.)
6. Create SQLite database with schema
7. Insert all data (statements, evaluations, evidence, documents)
8. Add package metadata (export date, source database, version)
9. Create indexes for performance
10. Optimize database (VACUUM, ANALYZE)

**Output**: Single `.db` file ready for distribution

### 3. Database Abstraction Layer

**File**: `src/bmlibrarian/factchecker/db/abstract_db.py`

**Purpose**: Unified interface supporting both PostgreSQL and SQLite

**Design**:
```python
class AbstractFactCheckerDB(ABC):
    """Abstract base class for fact-checker database operations."""

    @abstractmethod
    def get_all_statements_with_evaluations(self) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def insert_human_annotation(self, annotation: HumanAnnotation) -> int:
        pass

    @abstractmethod
    def get_document_abstract(self, document_id: int) -> Optional[str]:
        pass

    @abstractmethod
    def get_document_metadata(self, document_id: int) -> Optional[Dict]:
        pass

    # ... other methods


class PostgreSQLFactCheckerDB(AbstractFactCheckerDB):
    """PostgreSQL implementation (current FactCheckerDB)."""
    # Existing implementation


class SQLiteFactCheckerDB(AbstractFactCheckerDB):
    """SQLite implementation for review packages."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)

    def get_all_statements_with_evaluations(self):
        # Query SQLite database
        # JOIN with local documents table
        pass

    def get_document_abstract(self, document_id: int):
        # Query local documents table in SQLite
        pass
```

**Factory Function**:
```python
def get_fact_checker_db(db_type: str = "postgresql", **kwargs) -> AbstractFactCheckerDB:
    """Factory function to create appropriate database instance."""
    if db_type == "postgresql":
        return PostgreSQLFactCheckerDB()
    elif db_type == "sqlite":
        return SQLiteFactCheckerDB(db_path=kwargs['db_path'])
    else:
        raise ValueError(f"Unknown database type: {db_type}")
```

### 4. GUI Modifications

**File**: `src/bmlibrarian/factchecker/gui/data_manager.py`

**Changes**:
1. Detect database type on initialization:
   - If `.db` file provided → SQLite
   - Otherwise → PostgreSQL
2. Use factory function to create appropriate database instance
3. Update `load_from_database()` to work with abstraction
4. Update `citation_display.py` to query documents table (works for both backends)

**File**: `src/bmlibrarian/factchecker/gui/review_app.py`

**Changes**:
1. Add command-line option: `--db-file review_package.db`
2. Pass database configuration to DataManager
3. Display package metadata (source, export date) if SQLite

**Usage**:
```bash
# Review with PostgreSQL (current behavior)
python fact_checker_review_gui.py --user alice

# Review with SQLite package
python fact_checker_review_gui.py --user alice --db-file review_package_2024.db
```

### 5. Human Evaluation Export

**File**: `export_human_evaluations.py`

**Purpose**: Export ONLY human annotations to lightweight JSON file

**Functionality**:
```bash
# Export specific annotator's evaluations from SQLite
python export_human_evaluations.py --db-file review_package.db --annotator alice --output alice_evaluations.json

# Export from PostgreSQL
python export_human_evaluations.py --annotator alice --output alice_evaluations.json

# Export all annotators
python export_human_evaluations.py --db-file review_package.db --output all_evaluations.json
```

**Output Format** (JSON):
```json
{
  "export_metadata": {
    "export_date": "2024-11-15T10:30:00Z",
    "annotator_username": "alice",
    "source_database": "review_package_2024.db",
    "total_annotations": 150
  },
  "annotations": [
    {
      "statement_id": 123,
      "statement_text": "Aspirin reduces cardiovascular risk",
      "annotation": "yes",
      "explanation": "Strong evidence from multiple RCTs",
      "confidence": "high",
      "review_date": "2024-11-15T09:15:00Z",
      "review_duration_seconds": 180
    }
  ]
}
```

**Implementation**:
1. Load from database (SQLite or PostgreSQL)
2. Filter to specific annotator(s)
3. Extract annotations with statement context
4. Export as JSON with metadata

### 6. Import Script

**File**: `import_human_evaluations.py`

**Purpose**: Re-import human evaluations into PostgreSQL with username tagging

**Functionality**:
```bash
# Import evaluations from JSON file
python import_human_evaluations.py alice_evaluations.json

# Import with specific annotator override (if not in JSON)
python import_human_evaluations.py evaluations.json --annotator bob

# Import multiple files
python import_human_evaluations.py alice.json bob.json charlie.json

# Dry run (preview import without committing)
python import_human_evaluations.py evaluations.json --dry-run
```

**Implementation Steps**:
1. Read JSON file(s)
2. Extract annotator metadata
3. Connect to PostgreSQL
4. Create/get annotator record (factcheck.annotators)
5. For each annotation:
   - Match statement by `statement_id` OR `statement_text` (fallback)
   - Insert into `factcheck.human_annotations` table
   - Handle duplicates (ON CONFLICT UPDATE)
6. Report statistics (inserted, updated, errors)

**Error Handling**:
- Statement not found → Warning, skip
- Invalid annotation value → Error, skip
- Duplicate annotation → Update existing
- Database errors → Rollback, report

### 7. Inter-Rater Agreement Analysis

**File**: `analyze_inter_rater_agreement.py`

**Purpose**: Calculate agreement statistics between multiple annotators

**Functionality**:
```bash
# Calculate agreement for all annotators
python analyze_inter_rater_agreement.py

# Calculate agreement between specific annotators
python analyze_inter_rater_agreement.py --annotators alice,bob,charlie

# Export detailed agreement report
python analyze_inter_rater_agreement.py --output agreement_report.json

# Calculate Cohen's Kappa (pairwise)
python analyze_inter_rater_agreement.py --metric kappa
```

**Metrics**:
- Percent agreement
- Cohen's Kappa (pairwise)
- Fleiss' Kappa (multi-rater)
- Confusion matrices
- Per-statement agreement

**Output**:
- Console summary
- JSON report with detailed statistics
- CSV with per-statement agreement

## Workflow Examples

### Workflow 1: Distribute to Single External Reviewer

1. **Export Review Package**:
   ```bash
   python export_review_package.py --output alice_review_2024.db
   ```

2. **Distribute Package**:
   - Send `alice_review_2024.db` to reviewer Alice
   - Send `fact_checker_review_gui.py` and dependencies (or standalone package)

3. **Alice Reviews Statements**:
   ```bash
   python fact_checker_review_gui.py --user alice --db-file alice_review_2024.db
   ```
   - GUI saves annotations to SQLite database in real-time

4. **Alice Exports Her Evaluations**:
   ```bash
   python export_human_evaluations.py --db-file alice_review_2024.db --annotator alice --output alice_evaluations.json
   ```

5. **Re-import to PostgreSQL**:
   ```bash
   python import_human_evaluations.py alice_evaluations.json
   ```

6. **Analyze Agreement** (if multiple reviewers):
   ```bash
   python analyze_inter_rater_agreement.py --annotators alice,bob
   ```

### Workflow 2: Distribute to Multiple External Reviewers

1. **Export Single Package**:
   ```bash
   python export_review_package.py --output multi_reviewer_2024.db
   ```

2. **Distribute to Multiple Reviewers**:
   - Send same `multi_reviewer_2024.db` to Alice, Bob, Charlie

3. **Each Reviewer Annotates Independently**:
   ```bash
   # Alice
   python fact_checker_review_gui.py --user alice --db-file multi_reviewer_2024.db

   # Bob
   python fact_checker_review_gui.py --user bob --db-file multi_reviewer_2024.db

   # Charlie
   python fact_checker_review_gui.py --user charlie --db-file multi_reviewer_2024.db
   ```

4. **Each Exports Their Evaluations**:
   ```bash
   python export_human_evaluations.py --db-file multi_reviewer_2024.db --annotator alice --output alice.json
   python export_human_evaluations.py --db-file multi_reviewer_2024.db --annotator bob --output bob.json
   python export_human_evaluations.py --db-file multi_reviewer_2024.db --annotator charlie --output charlie.json
   ```

5. **Re-import All Evaluations**:
   ```bash
   python import_human_evaluations.py alice.json bob.json charlie.json
   ```

6. **Calculate Inter-Rater Agreement**:
   ```bash
   python analyze_inter_rater_agreement.py --annotators alice,bob,charlie --output agreement_report.json
   ```

## Testing Strategy

### Unit Tests
- Test SQLite schema creation
- Test export with various filters
- Test database abstraction layer (both backends)
- Test import with edge cases (missing statements, duplicates)

### Integration Tests
- Full workflow: Export → Review → Export annotations → Import
- Multi-reviewer workflow
- Agreement calculation with known data

### Manual Testing
- Export real PostgreSQL data
- Review statements in GUI with SQLite
- Verify abstracts display correctly
- Export and re-import annotations
- Check data integrity

## File Structure

```
bmlibrarian/
├── src/bmlibrarian/factchecker/
│   ├── db/
│   │   ├── database.py (existing - PostgreSQL)
│   │   ├── abstract_db.py (NEW - abstraction layer)
│   │   ├── sqlite_db.py (NEW - SQLite implementation)
│   │   └── sqlite_schema.sql (NEW - SQLite schema)
│   ├── gui/
│   │   ├── review_app.py (MODIFIED - SQLite support)
│   │   ├── data_manager.py (MODIFIED - abstraction)
│   │   └── citation_display.py (MODIFIED - abstraction)
│   └── utils/
│       └── db_factory.py (NEW - database factory)
├── export_review_package.py (NEW)
├── export_human_evaluations.py (NEW)
├── import_human_evaluations.py (NEW)
├── analyze_inter_rater_agreement.py (NEW)
└── FACT_CHECKER_DISTRIBUTION_PLAN.md (this file)
```

## Implementation Order

1. ✅ Create implementation plan (this document)
2. Design and create SQLite schema
3. Implement database abstraction layer
4. Create export_review_package.py script
5. Modify GUI to support SQLite
6. Create export_human_evaluations.py script
7. Create import_human_evaluations.py script
8. Test complete workflow
9. Create analyze_inter_rater_agreement.py (bonus)
10. Update documentation

## Security & Privacy Considerations

- **SQLite packages contain sensitive data**: Full abstracts, AI evaluations
- **Distribute packages securely**: Encrypted channels, access control
- **Annotator usernames**: Used for tagging, ensure privacy policies complied with
- **No deletion of annotations**: Import is additive (creates/updates, never deletes)
- **Audit trail**: Track exports via factcheck.export_history table

## Performance Considerations

- **SQLite package size**: ~100-500 KB per statement (with abstracts)
  - 1000 statements ≈ 100-500 MB
  - 10,000 statements ≈ 1-5 GB
- **Export time**: ~1-5 seconds per 1000 statements
- **GUI performance**: SQLite queries should be equally fast (add indexes)
- **Import time**: ~0.5-2 seconds per 1000 annotations

## Future Enhancements

1. **Standalone GUI Package**: PyInstaller/Briefcase bundle (GUI + SQLite, no PostgreSQL needed)
2. **Conflict Resolution**: UI for resolving annotation conflicts
3. **Collaborative Review**: Real-time multi-user annotation (web-based)
4. **Advanced Analytics**: Krippendorff's Alpha, confusion matrices, per-category agreement
5. **Export Formats**: CSV, Excel, SPSS for statistical analysis
6. **Annotation Versioning**: Track changes to annotations over time
7. **Quality Metrics**: Review time, confidence distributions, annotator consistency

## Questions for User

Before implementation, please confirm:

1. **Scope**: Should we support filtering exports by:
   - Date range?
   - AI evaluation quality (confidence, matches_expected)?
   - Specific categories/keywords?

2. **Human Evaluation Export**: Should JSON include:
   - AI evaluation for comparison?
   - Expected answer for reference?
   - Just annotation, or full context?

3. **Import Behavior**: On conflict (duplicate annotation from same user):
   - Always update?
   - Skip?
   - Prompt user?

4. **GUI Modes**: Should SQLite-based GUI be:
   - Read-only (no annotations saved back to SQLite)?
   - Read-write (annotations saved to SQLite)?
   - Configurable?

5. **Distribution**: How will packages be distributed?
   - Manual file sharing?
   - Web download?
   - Email attachments?

## Next Steps

1. Review this plan and provide feedback
2. Answer questions above
3. Approve implementation order
4. Begin implementation with Task 2 (SQLite schema design)
