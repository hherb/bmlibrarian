# Human Edit Logging - Quick Reference

BMLibrarian now captures all human edits to LLM outputs for training data collection.

## What Gets Logged

✅ **Document Score Overrides** (GUI only)
- When users change AI relevance scores (1-5 scale)
- Captures: user question, document details, AI score/reasoning, human override

✅ **Query Edits** (GUI + CLI)
- When users modify AI-generated PostgreSQL ts_queries
- Captures: user question, system prompt, AI query, human-edited query

## Database Table

```sql
human_edited (
    id SERIAL PRIMARY KEY,
    context TEXT,      -- Full prompt/context sent to LLM
    machine TEXT,      -- LLM's output
    human TEXT,        -- Human edit (NULL if accepted as-is)
    timestamp TIMESTAMP DEFAULT NOW()
)
```

## Quick Queries

### View recent edits
```sql
SELECT id, LEFT(context, 80), LEFT(machine, 50), LEFT(human, 50), timestamp
FROM human_edited
ORDER BY timestamp DESC
LIMIT 5;
```

### Count by type
```sql
SELECT
    COUNT(*) as total_edits,
    COUNT(CASE WHEN context LIKE '%Document to Evaluate%' THEN 1 END) as scoring_edits,
    COUNT(CASE WHEN context LIKE '%ts_query%' THEN 1 END) as query_edits
FROM human_edited;
```

### Export for training
```sql
COPY (SELECT context, machine, human FROM human_edited WHERE human IS NOT NULL)
TO '/tmp/training_data.csv' WITH CSV HEADER;
```

## Implementation Files

- **Logger**: [src/bmlibrarian/agents/human_edit_logger.py](src/bmlibrarian/agents/human_edit_logger.py)
- **GUI Scoring**: [src/bmlibrarian/gui/workflow_steps_handler.py](src/bmlibrarian/gui/workflow_steps_handler.py) (lines 159-171)
- **GUI Query**: [src/bmlibrarian/gui/interactive_handler.py](src/bmlibrarian/gui/interactive_handler.py) (lines 46-59)
- **CLI Query**: [src/bmlibrarian/cli/query_processing.py](src/bmlibrarian/cli/query_processing.py) (lines 66-78)
- **Test Suite**: [test_human_edit_logging.py](test_human_edit_logging.py)
- **Full Docs**: [doc/developers/human_edit_logging.md](doc/developers/human_edit_logging.md)

## Testing

```bash
uv run python test_human_edit_logging.py
```

## Privacy Note

Research questions and document content are logged. Consider data retention policies for sensitive information.

## Future Extensions

The flexible `log_edit()` API can be extended for:
- Citation review/approval
- Report revisions
- Counterfactual question selection
- Any other human-in-the-loop interactions

See full documentation for examples.

## Troubleshooting

### Error: "module 'psycopg_binary.pq' has no attribute 'PGcancelConn'"

**Cause**: Version mismatch between `psycopg` and `psycopg-binary` packages.

**Solution**:

```bash
# Uninstall all psycopg packages
pip uninstall -y psycopg psycopg-binary psycopg-pool

# Reinstall with matching versions
pip install 'psycopg[binary]>=3.2.9' psycopg-pool>=3.2.6
```

**Or use uv (recommended)**:

```bash
# Always use uv run to ensure correct environment
uv run python bmlibrarian_research_gui.py
```

This ensures you're using the project's virtual environment with properly synced dependencies.
