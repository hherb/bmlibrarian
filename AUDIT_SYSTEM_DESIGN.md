# BMLibrarian Audit System Design

## Overview

The audit system provides comprehensive tracking of the complete research workflow in PostgreSQL, enabling:
- **Resumption**: Continue research sessions without re-processing documents
- **Provenance**: Complete audit trail from question → queries → documents → scores → citations → reports
- **Multi-Evaluator Support**: Track scores from different AI models and human reviewers
- **Performance Analysis**: Identify which models/parameters work best
- **Reproducibility**: Full configuration snapshots and execution history

## Key Design Principles

### 1. Research Question as Central Anchor

**Everything** links back to `research_question_id`:
- Enables finding all work done for a research question
- Supports resumption: "What have we already processed?"
- Allows incremental research: "Add more documents to existing question"

### 2. Integration with Existing `public.evaluators` Table

The audit system integrates with the existing database infrastructure:
- **`public.evaluators`**: Combines user_id + model_id + parameters → unique evaluator
- **Critical for resumption**: Check if document scored **by this specific evaluator**
- Supports multiple scoring approaches: different models, different users, different parameters

### 3. BIGSERIAL Primary Keys

Uses `BIGSERIAL` (not UUIDs) for consistency with existing database:
- Lower storage overhead
- Faster joins and indexes
- Consistent with rest of knowledge base schema

## Schema Structure

### Core Tables (namespace: `audit`)

```
research_questions (1)
    ↓
research_sessions (many) ──→ workflow_steps (many)
    ↓
generated_queries (many) ──→ query_documents (many)
    ↓                              ↓
    └──────────────────────→ document_scores (1 per question+document+evaluator)
                                   ↓
                            extracted_citations (many)
                                   ↓
                            generated_reports (many)
                                   ↓
                         counterfactual_analyses (optional)
```

### Table Descriptions

#### 1. `audit.research_questions`
- **Purpose**: Central anchor - one row per unique research question
- **Deduplication**: Uses MD5 hash of normalized question text
- **Key Fields**:
  - `research_question_id` (BIGSERIAL PK)
  - `question_text` (TEXT UNIQUE)
  - `question_hash` (TEXT) - for fast lookups
  - `total_sessions` - tracks how many times researched
  - `status` - 'active', 'archived', 'superseded'

#### 2. `audit.research_sessions`
- **Purpose**: Multiple sessions per question (initial, expansion, reanalysis)
- **Key Fields**:
  - `session_id` (BIGSERIAL PK)
  - `research_question_id` (FK)
  - `session_type` - 'initial', 'expansion', 'reanalysis', 'counterfactual_only'
  - `config_snapshot` (JSONB) - full config for reproducibility
  - `workflow_status` - 'in_progress', 'completed', 'failed', 'cancelled'

#### 3. `audit.generated_queries`
- **Purpose**: All database queries generated for research questions
- **Key Fields**:
  - `query_id` (BIGSERIAL PK)
  - `research_question_id` (FK)
  - `session_id` (FK)
  - `evaluator_id` (FK to public.evaluators) - **NEW**: which model/params generated
  - `query_text` - original generated query
  - `query_text_sanitized` - after syntax fixes
  - `human_edited` (BOOLEAN)
  - `documents_found_count` - cache for performance

#### 4. `audit.query_documents`
- **Purpose**: Many-to-many relationship between queries and documents
- **Key Fields**:
  - `research_question_id` (FK)
  - `query_id` (FK)
  - `document_id` (FK to public.document)
  - `rank_in_results` - position in search results
- **Critical Index**: `(research_question_id, document_id)` for resumption

#### 5. `audit.document_scores` ⭐ **MOST CRITICAL FOR RESUMPTION**
- **Purpose**: ONE score per question + document + evaluator combination
- **Unique Constraint**: `(research_question_id, document_id, evaluator_id)`
- **Key Fields**:
  - `scoring_id` (BIGSERIAL PK)
  - `research_question_id` (FK)
  - `document_id` (FK to public.document)
  - `evaluator_id` (FK to public.evaluators) - **WHO scored this**
  - `session_id` (FK) - when it was scored
  - `first_query_id` (FK) - which query found it
  - `relevance_score` (INTEGER 0-5)
  - `reasoning` (TEXT)
  - `scored_at`, `last_updated_at`

**Why evaluator_id?**
- Different AI models score differently
- Different users (humans) score differently
- Different parameters produce different scores
- **Resumption check**: "Has THIS evaluator scored THIS document for THIS question?"

#### 6. `audit.extracted_citations`
- **Purpose**: Citations extracted from high-scoring documents
- **Key Fields**:
  - `citation_id` (BIGSERIAL PK)
  - `research_question_id` (FK)
  - `document_id` (FK)
  - `scoring_id` (FK) - which score triggered extraction
  - `evaluator_id` (FK to public.evaluators) - who extracted it
  - `passage` (TEXT) - direct quote
  - `summary` (TEXT) - AI summary
  - `relevance_confidence` (REAL 0.0-1.0)
  - `human_review_status` - 'accepted', 'rejected', 'modified'

#### 7. `audit.generated_reports`
- **Purpose**: All reports generated for research questions
- **Key Fields**:
  - `report_id` (BIGSERIAL PK)
  - `research_question_id` (FK)
  - `session_id` (FK)
  - `report_type` - 'preliminary', 'comprehensive', 'counterfactual'
  - `evaluator_id` (FK to public.evaluators) - which model generated
  - `report_text` (TEXT)
  - `methodology_metadata` (JSONB) - stats
  - `is_final` (BOOLEAN) - mark final version

#### 8. `audit.counterfactual_analyses`
- **Purpose**: Track counterfactual analysis sessions
- **Key Fields**:
  - `analysis_id` (BIGSERIAL PK)
  - `research_question_id` (FK)
  - `session_id` (FK)
  - `source_report_id` (FK) - report analyzed
  - `evaluator_id` (FK to public.evaluators)
  - Statistics: num_questions, num_queries, num_documents, num_citations

#### 9. `audit.counterfactual_questions`
- **Purpose**: Individual questions for finding contradictory evidence
- **Key Fields**:
  - `question_id` (BIGSERIAL PK)
  - `research_question_id` (FK)
  - `analysis_id` (FK)
  - `question_text` (TEXT)
  - `target_claim` (TEXT)
  - `priority` - 'high', 'medium', 'low'

#### 10. `audit.human_edits`
- **Purpose**: Complete audit trail of human interventions
- **Key Fields**:
  - `edit_id` (BIGSERIAL PK)
  - `research_question_id` (FK)
  - `session_id` (FK)
  - `edit_type` - 'query_edit', 'score_override', 'citation_review', 'report_edit'
  - `target_table`, `target_id` - what was edited
  - `original_value`, `edited_value`
  - `user_id` (FK to users)

#### 11. `audit.workflow_steps`
- **Purpose**: Track workflow execution (from WorkflowStep enum)
- **Key Fields**:
  - `step_id` (BIGSERIAL PK)
  - `research_question_id` (FK)
  - `session_id` (FK)
  - `step_name` (TEXT) - e.g., 'SCORE_DOCUMENTS', 'EXTRACT_CITATIONS'
  - `step_status` - 'pending', 'in_progress', 'completed', 'failed', 'skipped'
  - `duration_ms`, `error_message`
  - `execution_count` - for repeatable steps

## Helper Functions

### `audit.get_or_create_research_question(question_text, user_id)`
- Handles deduplication via question hash
- Returns existing `research_question_id` or creates new one
- Updates `last_activity_at` and increments `total_sessions`

### `audit.get_unscored_document_ids(research_question_id, evaluator_id)`
- **CRITICAL FOR RESUMPTION**
- Returns document IDs **not yet scored by this evaluator**
- Enables: "Only score new documents with this model/params"

### `audit.is_document_scored(research_question_id, document_id, evaluator_id)`
- Fast boolean check
- Returns TRUE if document already scored by this evaluator

## Helper Views

### `audit.v_latest_sessions`
- Latest session for each research question
- Useful for resumption: "What was the last session?"

### `audit.v_document_processing_status`
- Shows: discovered → scored → citations extracted
- Includes evaluator information
- Per-question view of document processing pipeline

### `audit.v_evaluator_performance`
- Aggregated stats per evaluator:
  - Queries generated
  - Documents scored
  - Average relevance scores
  - Citations extracted
  - Reports generated

## Python Tracker Classes

Located in `src/bmlibrarian/audit/`:

### `SessionTracker`
- `get_or_create_research_question(question_text, user_id)`
- `start_session(question_id, session_type, config, notes)`
- `complete_session(session_id, status)`
- `get_latest_session(question_id)`
- `list_recent_questions(limit, user_id, status)`

### `DocumentTracker`
- `record_query_documents(question_id, query_id, document_ids)`
- `is_document_scored(question_id, document_id, evaluator_id)` ⭐
- `get_unscored_documents(question_id, evaluator_id)` ⭐
- `record_document_score(question_id, doc_id, session_id, query_id, evaluator_id, score, reasoning)`
- `get_high_scoring_documents(question_id, min_score)`
- `count_documents_by_score(question_id)`

### `CitationTracker`
- `record_citation(question_id, doc_id, session_id, scoring_id, evaluator_id, passage, summary, confidence)`
- `update_human_review_status(citation_id, status)`
- `get_accepted_citations(question_id)`
- `get_all_citations(question_id, session_id)`
- `count_citations(question_id, by_status)`

### `ReportTracker`
- `record_report(question_id, session_id, report_type, evaluator_id, report_text, ...)`
- `mark_report_as_final(report_id)`
- `get_latest_report(question_id, report_type)`
- `get_final_report(question_id)`
- `record_counterfactual_analysis(...)`
- `record_counterfactual_question(...)`

## Typical Workflow

```python
import psycopg
from bmlibrarian.audit import SessionTracker, DocumentTracker, CitationTracker

# Connect to database
conn = psycopg.connect(dbname="knowledgebase", user="hherb", host="localhost")

# Initialize trackers
session_tracker = SessionTracker(conn)
document_tracker = DocumentTracker(conn)
citation_tracker = CitationTracker(conn)

# 1. Get or create research question
question = "What are the benefits of aspirin?"
question_id = session_tracker.get_or_create_research_question(question, user_id=1)

# 2. Check if this is a resumption (question already exists)
latest_session = session_tracker.get_latest_session(question_id)
if latest_session:
    print(f"Resuming previous session {latest_session['session_id']}")

# 3. Start new session
session_id = session_tracker.start_session(
    question_id,
    session_type='expansion',  # or 'initial'
    config_snapshot={'model': 'medgemma-27b', 'temperature': 0.1}
)

# 4. Generate queries (QueryAgent)
# ... query_id = ...

# 5. Record found documents
document_ids = [12345, 12346, 12347]
document_tracker.record_query_documents(question_id, query_id, document_ids)

# 6. Get evaluator_id for scoring
# Assume evaluator_id = 10 (from public.evaluators table)
evaluator_id = 10  # medgemma-27b with specific params

# 7. Check which documents need scoring BY THIS EVALUATOR
unscored = document_tracker.get_unscored_documents(question_id, evaluator_id)
print(f"Need to score {len(unscored)} documents (already scored: {len(document_ids) - len(unscored)})")

# 8. Score only unscored documents
for doc_id in unscored:
    # Check if already scored (safety check)
    if document_tracker.is_document_scored(question_id, doc_id, evaluator_id):
        continue  # Skip - already scored by this evaluator

    # Score the document
    scoring_id = document_tracker.record_document_score(
        question_id, doc_id, session_id, query_id,
        evaluator_id, relevance_score=4, reasoning="Highly relevant"
    )

# 9. Extract citations from high-scoring documents
high_scoring = document_tracker.get_high_scoring_documents(question_id, min_score=3)
for score_info in high_scoring:
    citation_id = citation_tracker.record_citation(
        question_id, score_info['document_id'], session_id,
        score_info['scoring_id'], evaluator_id,
        passage="...", summary="..."
    )

# 10. Complete session
session_tracker.complete_session(session_id, status='completed')
```

## Resumption Example

```python
# User starts research on Monday
question_id = session_tracker.get_or_create_research_question(
    "What are the cardiovascular benefits of exercise?",
    user_id=1
)
session_id = session_tracker.start_session(question_id, 'initial')

# ... process 100 documents with evaluator_id=10 (medgemma-27b)
# All 100 documents scored and stored in audit.document_scores

session_tracker.complete_session(session_id, 'completed')

# ---

# User returns on Tuesday to add more documents
# SAME question text → returns SAME question_id (deduplication works!)
question_id_2 = session_tracker.get_or_create_research_question(
    "What are the cardiovascular benefits of exercise?",  # identical
    user_id=1
)
# question_id_2 == question_id ✓

# Start new session for expansion
session_id_2 = session_tracker.start_session(question_id, 'expansion')

# New query finds 150 documents (50 new, 100 overlap with Monday)
new_document_ids = list(range(1, 151))

document_tracker.record_query_documents(question_id, new_query_id, new_document_ids)

# Check which need scoring BY SAME EVALUATOR
unscored = document_tracker.get_unscored_documents(question_id, evaluator_id=10)
# Result: only 50 documents! (100 were already scored Monday)

# Score only the 50 new documents - HUGE TIME SAVINGS!
for doc_id in unscored:
    document_tracker.record_document_score(...)

# Can also get previously accepted citations for reuse
existing_citations = citation_tracker.get_accepted_citations(question_id)
# Result: all citations from Monday session available!
```

## Migration Files

1. **`003_create_audit_schema.sql`**: Initial audit schema with BIGSERIAL PKs
2. **`004_update_audit_for_evaluators.sql`**: Updates to use `public.evaluators` table

## Benefits

✅ **Resumption**: Never re-process same documents with same evaluator
✅ **Multi-Evaluator**: Compare different models scoring same documents
✅ **Provenance**: Complete audit trail from question to final report
✅ **Performance**: Identify best-performing models and parameters
✅ **Reproducibility**: Full config snapshots and execution history
✅ **Human-AI Collaboration**: Track all human interventions
✅ **Incremental Research**: Add documents to existing research over time
✅ **Database Integration**: Uses existing `public.evaluators` infrastructure

## Future Enhancements

- Add dashboard for visualizing evaluator performance
- Implement automatic evaluator selection based on historical performance
- Add query performance prediction based on past results
- Create recommendation system for optimal model/parameter combinations
- Support exporting complete research lineage for publication
