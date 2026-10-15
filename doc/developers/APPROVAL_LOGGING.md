# Human Approval Logging - Implementation Summary

> **Note (2026-10-16)**: the GUI side of this system was part of the Flet-based Research GUI (`bmlibrarian_research_gui.py`), which has been removed. The GUI modules referenced below (`gui/components.py`, `gui/interactive_handler.py`, `gui/workflow.py`, `gui/workflow_steps_handler.py`) no longer exist, and the Qt Research tab does not provide approve/override controls (see ROADMAP §1). The database logging (`human_edit_logger.py`) remains. This document is kept as a record of the design.

## Overview

BMLibrarian now captures **both human edits AND explicit approvals** of LLM outputs. This provides richer training data by distinguishing between:
- **Passive acceptance**: User simply proceeds without review
- **Active approval**: User reviews and explicitly confirms LLM is correct ✅
- **Edit/Override**: User modifies LLM output 📝

## What Gets Logged

### 1. Document Scoring (GUI)

**Scenario A: Human Override**
- AI scores document as 3/5
- User changes to 4/5
- Database logs: `human = {"score": 4, "edit_type": "override", "original_ai_score": 3}`

**Scenario B: Explicit Approval** ⭐ NEW
- AI scores document as 4/5
- User checks "Approve AI score" checkbox
- Database logs: `human = "APPROVED"`

**Scenario C: Passive Acceptance**
- AI scores document as 4/5
- User doesn't interact, clicks continue
- Database logs: Nothing (no entry created)

### 2. Query Generation (GUI & CLI)

**Scenario A: Edit**
- AI generates: `(fish oil) & (heart health)`
- User edits to: `(fish oil | omega-3) & (cardiovascular)`
- Database logs: `human = "(fish oil | omega-3) & (cardiovascular)"`

**Scenario B: Explicit Approval**
- AI generates query
- User accepts without changes (button click)
- Database logs: `human = "APPROVED"`

**Scenario C: Passive Acceptance**
- Query accepted by timeout/default
- Database logs: Nothing

## Database Schema

```sql
human_edited (
    id SERIAL PRIMARY KEY,
    context TEXT,      -- Complete prompt/context
    machine TEXT,      -- LLM output
    human TEXT,        -- NULL | "APPROVED" | JSON override | edited text
    timestamp TIMESTAMP DEFAULT NOW()
)
```

**`human` column values:**
- `NULL` - Not logged (passive acceptance)
- `"APPROVED"` - Explicit approval, no changes
- JSON object - Override with metadata (document scoring)
- Plain text - Edited query (query generation)

## GUI Changes

### Document Scoring Interface

Each document card now shows:

```
┌─────────────────────────────────────────────────┐
│ Document 1: Cardiovascular Benefits of Exercise│
│                                                 │
│ Abstract: This study examined...               │
│                                                 │
│ ┌─────────┐  ┌──────────────┐  ┌─────────────┐│
│ │AI Score │  │Human Review  │  │AI Reasoning ││
│ │  4.0/5  │  │[1-5]: ___   │  │Highly       ││
│ │         │  │☐ Approve AI │  │relevant...  ││
│ └─────────┘  └──────────────┘  └─────────────┘│
└─────────────────────────────────────────────────┘
```

**User Actions:**
1. **Override**: Enter different score → Logs override
2. **Approve**: Check checkbox → Logs approval
3. **Skip**: Leave blank → No logging

### Query Editing Interface

Query review step shows:
- Generated query in editable text field
- "Accept" button (explicit approval) → Logs approval if unchanged
- Edit + Accept → Logs edit if changed

## Implementation Files

### Core Logger
- [human_edit_logger.py](src/bmlibrarian/agents/human_edit_logger.py:24) - `log_edit()` with `explicitly_approved` parameter

### GUI Components
- [components.py](src/bmlibrarian/gui/components.py:426) - Approval checkbox added
- [components.py](src/bmlibrarian/gui/components.py:528) - `_on_score_approval_change()` handler
- [components.py](src/bmlibrarian/gui/components.py:537) - Returns `{overrides, approvals}` dict

### Workflow Integration
- [interactive_handler.py](src/bmlibrarian/gui/interactive_handler.py:160) - Processes approval data
- [workflow.py](src/bmlibrarian/gui/workflow.py:268) - Extracts overrides and approvals
- [workflow_steps_handler.py](src/bmlibrarian/gui/workflow_steps_handler.py:177) - Logs approvals to database

## Data Examples

### Document Scoring Approval
```json
{
  "context": "User Question: What are the benefits of fish oil?\n\nDocument: Title: Omega-3 Fatty Acids...",
  "machine": "{\"score\": 4, \"reasoning\": \"Highly relevant discussion of omega-3 benefits\"}",
  "human": "APPROVED"
}
```

### Document Scoring Override
```json
{
  "context": "User Question: What are the benefits of fish oil?\n\nDocument: Title: Omega-3 Fatty Acids...",
  "machine": "{\"score\": 3, \"reasoning\": \"Moderately relevant\"}",
  "human": "{\"score\": 4, \"edit_type\": \"override\", \"original_ai_score\": 3}"
}
```

### Query Approval
```json
{
  "context": "System: Convert to ts_query...\n\nUser Question: benefits of fish oil",
  "machine": "(fish oil | omega-3) & benefits",
  "human": "APPROVED"
}
```

## SQL Queries

### Count by interaction type
```sql
SELECT
    COUNT(CASE WHEN human = 'APPROVED' THEN 1 END) as approvals,
    COUNT(CASE WHEN human IS NOT NULL AND human != 'APPROVED' THEN 1 END) as edits,
    COUNT(*) as total
FROM human_edited;
```

### Approval rate for document scoring
```sql
SELECT
    COUNT(CASE WHEN human = 'APPROVED' THEN 1 END)::float /
    COUNT(*)::float * 100 as approval_rate_percent
FROM human_edited
WHERE context LIKE '%Document to Evaluate%';
```

### Recent approvals
```sql
SELECT
    CASE
        WHEN context LIKE '%Document to Evaluate%' THEN 'Doc Scoring'
        WHEN context LIKE '%ts_query%' THEN 'Query Gen'
        ELSE 'Other'
    END as type,
    timestamp
FROM human_edited
WHERE human = 'APPROVED'
ORDER BY timestamp DESC
LIMIT 10;
```

## Benefits for Training

### Quality Indicators
1. **High approval rate** → Model performing well
2. **Frequent overrides** → Model needs improvement
3. **Approval patterns** → Shows when model is trusted

### Training Data Quality
- **Positive examples**: Approvals confirm correct outputs
- **Negative examples**: Overrides show preferred outputs
- **Context matters**: Same prompt + different human responses teaches nuance

### Fine-tuning Strategy
```
For each task:
1. Count approvals vs overrides
2. If approval rate > 80% → Model is good
3. If override rate > 50% → Need more training data
4. Focus fine-tuning on high-override scenarios
```

## Testing

```bash
# Run test suite
python test_human_edit_logging.py

# Test in GUI (former Flet Research GUI - removed 2026-10-16;
# the Qt Research tab does not currently offer approve/override controls)
python bmlibrarian_research_gui.py
# 1. Enter research question
# 2. Review document scores
# 3. Check "Approve AI score" for some documents
# 4. Enter overrides for others
# 5. Check database

# Verify database
psql -d knowledgebase -c "SELECT COUNT(*) FROM human_edited WHERE human = 'APPROVED';"
```

## Next Steps

### Query Editing Approval (Future)
Currently query editing logs edits but not explicit approvals. To add:
1. Add "Approve query" button to query editing interface
2. Update interactive_handler to track approval
3. Pass approval flag to log_query_edit()

### Citation Review Approval (Future)
Track when users approve/reject individual citations.

### Report Revision Approval (Future)
Track when users approve final reports vs request revisions.

## Summary

✅ **Document Scoring**: Full approval + override logging
✅ **Query Editing**: Edit logging (approval UI pending)
✅ **Database**: "APPROVED" indicates explicit confirmation
✅ **Training Value**: Distinguishes active approval from passive acceptance

This provides much richer training signals than edit-only logging!
