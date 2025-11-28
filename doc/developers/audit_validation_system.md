# Audit Trail Validation System - Developer Documentation

## Overview

The Audit Trail Validation System provides infrastructure for human review of automated evaluations in BMLibrarian's systematic review workflow. This enables benchmarking AI accuracy and collecting training data for fine-tuning.

## Architecture

### Database Schema

Located in `migrations/025_create_audit_validation_schema.sql`:

```
audit.human_validations          # Core validation records
audit.validation_categories      # Predefined error categories
audit.validation_category_assignments  # M:N linking table
```

### Python Components

```
src/bmlibrarian/audit/
├── validation_tracker.py        # Database layer for validations

src/bmlibrarian/gui/qt/plugins/audit_validation/
├── __init__.py                  # Module exports
├── plugin.py                    # Plugin registration
├── data_manager.py              # Data loading/persistence
├── validation_tab.py            # Main validation UI
└── statistics_widget.py         # Statistics display
```

## Database Schema Details

### human_validations Table

```sql
CREATE TABLE audit.human_validations (
    validation_id BIGSERIAL PRIMARY KEY,
    research_question_id BIGINT NOT NULL,
    session_id BIGINT,
    target_type TEXT NOT NULL,      -- 'query', 'score', 'citation', 'report', 'counterfactual'
    target_id BIGINT NOT NULL,       -- ID in the target table
    validation_status TEXT NOT NULL, -- 'validated', 'incorrect', 'uncertain', 'needs_review'
    reviewer_id INTEGER,
    reviewer_name TEXT NOT NULL,
    comment TEXT,
    suggested_correction TEXT,
    severity TEXT,                   -- 'minor', 'moderate', 'major', 'critical'
    validated_at TIMESTAMPTZ,
    time_spent_seconds INTEGER,
    UNIQUE (target_type, target_id, reviewer_id)
);
```

### validation_categories Table

Pre-populated with error categories for each target type:

```sql
-- Example categories
('score', 'overscored', 'Overscored', 'Document scored too high')
('score', 'underscored', 'Underscored', 'Document scored too low')
('citation', 'misinterpretation', 'Misinterpretation', 'Summary misinterprets passage')
```

## Python API

### ValidationTracker Class

```python
from bmlibrarian.audit import (
    ValidationTracker, TargetType, ValidationStatus, Severity
)

# Initialize with database connection
tracker = ValidationTracker(conn)

# Record a validation
validation_id = tracker.record_validation(
    research_question_id=123,
    target_type=TargetType.SCORE,
    target_id=456,
    validation_status=ValidationStatus.INCORRECT,
    reviewer_id=1,
    reviewer_name="alice",
    comment="Document is not relevant to the research question",
    severity=Severity.MAJOR,
    category_ids=[5, 6]  # Error category IDs
)

# Check if item is validated
is_validated = tracker.is_validated(TargetType.SCORE, 456)

# Get validation statistics
stats = tracker.get_validation_statistics(TargetType.SCORE)
```

### Data Types

```python
from bmlibrarian.audit import (
    TargetType,           # Enum: QUERY, SCORE, CITATION, REPORT, COUNTERFACTUAL
    ValidationStatus,     # Enum: VALIDATED, INCORRECT, UNCERTAIN, NEEDS_REVIEW
    Severity,             # Enum: MINOR, MODERATE, MAJOR, CRITICAL
    ValidationCategory,   # Dataclass for category info
    HumanValidation,      # Dataclass for validation record
    ValidationStatistics, # Dataclass for aggregated stats
    UnvalidatedCounts     # Dataclass for progress tracking
)
```

### AuditValidationDataManager Class

High-level data manager for the GUI:

```python
from bmlibrarian.gui.qt.plugins.audit_validation import AuditValidationDataManager

manager = AuditValidationDataManager(conn)

# Load research questions with validation progress
questions = manager.get_research_questions()

# Load items by type
scores = manager.get_scores_for_question(123, include_validated=True)
citations = manager.get_citations_for_question(123, include_validated=False)

# Record validation
manager.record_validation(
    research_question_id=123,
    target_type=TargetType.SCORE,
    target_id=456,
    validation_status=ValidationStatus.VALIDATED,
    reviewer_id=1,
    reviewer_name="alice"
)
```

## GUI Plugin Architecture

### Plugin Registration

The plugin follows the existing Qt plugin pattern:

```python
from bmlibrarian.gui.qt.plugins.audit_validation import AuditValidationPlugin

plugin = AuditValidationPlugin()
plugin.set_reviewer(reviewer_id, reviewer_name)
plugin.initialize(conn)
widget = plugin.create_widget(parent)
```

### ValidationTabWidget

Main widget providing:
- Research question selector with progress display
- Sub-tabs for each target type (Queries, Scores, Citations, Reports, Counterfactuals)
- Item list with validation status icons
- Detail view with full item information
- Validation controls with status, severity, category, and comment fields
- Review timer for time tracking

### StatisticsWidget

Statistics display showing:
- Summary cards (total reviewed, validated, incorrect, validation rate)
- Detailed table by target type
- Error category breakdown

## Database Views

### v_validation_statistics

Aggregated validation rates by target type:

```sql
SELECT * FROM audit.v_validation_statistics;
-- Returns: target_type, total_validations, validated_count, incorrect_count,
--          uncertain_count, needs_review_count, validation_rate_percent,
--          unique_reviewers, avg_review_time_seconds
```

### v_validation_error_categories

Error category breakdown:

```sql
SELECT * FROM audit.v_validation_error_categories;
-- Returns: target_type, category_code, category_name, error_count, percentage_of_errors
```

### v_evaluator_validation_performance

Per-evaluator accuracy metrics:

```sql
SELECT * FROM audit.v_evaluator_validation_performance;
-- Returns: evaluator_id, evaluator_name, model_id, total_scores, scores_reviewed,
--          scores_validated, scores_incorrect, total_citations, citations_reviewed,
--          citations_validated, citations_incorrect
```

## Helper Functions

### Get unvalidated item counts

```sql
SELECT * FROM audit.get_unvalidated_counts(123);  -- research_question_id
-- Returns: target_type, total_count, validated_count, unvalidated_count
```

### Check if item is validated by specific reviewer

```sql
SELECT audit.is_validated_by_reviewer('score', 456, 1);  -- target_type, target_id, reviewer_id
-- Returns: BOOLEAN
```

## Integration with Existing Audit System

The validation system builds on the existing audit schema:

- `audit.generated_queries` → validated via `target_type='query'`
- `audit.document_scores` → validated via `target_type='score'`
- `audit.extracted_citations` → validated via `target_type='citation'`
- `audit.generated_reports` → validated via `target_type='report'`
- `audit.counterfactual_questions` → validated via `target_type='counterfactual'`

## Benchmarking Workflow

1. **Run systematic review** to generate audit trail data
2. **Human reviewers validate** items using the GUI
3. **Calculate metrics**:
   - Validation rate = validated / total reviewed
   - Error rate = incorrect / total reviewed
   - Agreement rate = consistent across reviewers
4. **Analyze error categories** to identify systematic issues
5. **Export training data** for fine-tuning (incorrect items with corrections)

## Testing

```bash
# Run unit tests
uv run python -m pytest tests/test_validation_tracker.py -v

# Test the GUI
uv run python audit_validation_gui.py --user test_user --debug
```

## Future Enhancements

1. **Export functionality**: Export validated items for training
2. **Inter-rater agreement**: Automatic kappa coefficient calculation
3. **Batch validation**: Validate multiple items at once
4. **Keyboard shortcuts**: Faster review workflow
5. **Filter by evaluator**: Focus on specific model's outputs
