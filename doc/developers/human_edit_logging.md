# Human Edit Logging System

## Overview

The BMLibrarian system now captures all human edits, approvals, and rejections of LLM output for training data collection and analysis. This allows us to build datasets for fine-tuning and improving our AI models.

## Database Schema

The system uses the existing `human_edited` table in PostgreSQL:

```sql
CREATE TABLE human_edited (
    id SERIAL PRIMARY KEY,
    context TEXT,           -- Complete prompt/context fed to the LLM
    machine TEXT,           -- LLM's output/response
    human TEXT,             -- Human edit/override (NULL if accepted as-is)
    timestamp TIMESTAMP DEFAULT NOW()
);
```

## Architecture

### Core Component: HumanEditLogger

Location: `src/bmlibrarian/agents/human_edit_logger.py`

The `HumanEditLogger` class provides a flexible, reusable interface for logging various types of human edits.

**Key Methods:**

1. **`log_edit(context, machine_output, human_edit=None, log_all=False, explicitly_approved=False)`**
   - Generic method for logging any LLM interaction
   - Only logs when `human_edit` is provided or `explicitly_approved=True`
   - Prevents database clutter from unchanged outputs
   - Stores "APPROVED" for explicit approvals vs actual edit text for changes

2. **`log_document_score_edit(user_question, document, ai_score, ai_reasoning, human_score=None, explicitly_approved=False)`**
   - Specialized method for document scoring edits
   - Captures the full evaluation context
   - Only logs when human overrides the AI score OR explicitly approves it

3. **`log_query_edit(user_question, system_prompt, ai_query, human_query=None, explicitly_approved=False)`**
   - Specialized method for query generation edits
   - Captures query refinement interactions
   - Only logs when human modifies the AI-generated query OR explicitly approves it

4. **`log_citation_review(user_question, citation, review_status=None)`**
   - Specialized method for citation acceptance/rejection
   - Logs human review decisions on extracted citations
   - Only logs when review_status is provided ('accepted' or 'refused')

### Singleton Pattern

The logger uses a singleton pattern to avoid multiple database connections:

```python
from bmlibrarian.agents import get_human_edit_logger

logger = get_human_edit_logger()
```

## Integration Points

### 1. Document Scoring (GUI Workflow)

**File:** `src/bmlibrarian/gui/workflow_steps_handler.py`

When users override AI document scores or explicitly approve them in the Research GUI, the edit is logged:

```python
# Applied in execute_document_scoring() when score_overrides or score_approvals exist
if score_overrides and i in score_overrides:
    result_dict['score'] = score_overrides[i]
    result_dict['human_override'] = True
    result_dict['original_ai_score'] = original_score

    # Log the human edit to database
    from bmlibrarian.agents import get_human_edit_logger
    logger = get_human_edit_logger()
    logger.log_document_score_edit(
        user_question=research_question,
        document=doc,
        ai_score=int(original_score),
        ai_reasoning=scoring_result.get('reasoning', ''),
        human_score=int(score_overrides[i])
    )

# Log explicit approvals
if score_approvals and i in score_approvals and score_approvals[i]:
    logger.log_document_score_edit(
        user_question=research_question,
        document=doc,
        ai_score=int(original_score),
        ai_reasoning=scoring_result.get('reasoning', ''),
        explicitly_approved=True
    )
```

**Data Captured:**
- **Context:** User question + document metadata (title, abstract, authors, publication info)
- **Machine:** JSON with AI score and reasoning
- **Human:** JSON with human score, edit type ("override" or "approval"), and original AI score

**UI Component:** Checkbox in scoring interface (`src/bmlibrarian/gui/components.py`):
```python
ft.Checkbox(
    label="Approve AI score",
    value=False,
    on_change=lambda e: self._on_score_approval_change(index, e.control.value)
)
```

### 2. Query Generation (GUI Workflow)

**File:** `src/bmlibrarian/gui/interactive_handler.py`

When users edit AI-generated queries in the GUI:

```python
def handle_edit_result(approved: bool, new_query: str = ""):
    if approved:
        cleaned_query = query_cleaner(new_query if new_query.strip() else query_text)
        edited_query = cleaned_query

        # Log query edit if changed
        if edited_query != query_text:
            from bmlibrarian.agents import get_human_edit_logger
            logger = get_human_edit_logger()
            logger.log_query_edit(
                user_question=research_question,
                system_prompt="Query generation system prompt (see QueryAgent.system_prompt)",
                ai_query=query_text,
                human_query=edited_query
            )
```

**Data Captured:**
- **Context:** System prompt + user question
- **Machine:** AI-generated ts_query
- **Human:** Human-edited ts_query

### 3. Citation Review (GUI Workflow)

**File:** `src/bmlibrarian/gui/interactive_handler.py`

When users accept or refuse extracted citations:

```python
def _show_interactive_citation_review(self, citations: List, update_callback: Callable) -> Dict[int, str]:
    # ... citation review UI ...

    # Log citation reviews
    from bmlibrarian.agents import get_human_edit_logger
    logger = get_human_edit_logger()

    for idx, status in citation_reviews.items():
        logger.log_citation_review(
            user_question=research_question,
            citation=citations[idx],
            review_status=status
        )
```

**Data Captured:**
- **Context:** User question + document title + cited passage
- **Machine:** JSON with citation details and AI reasoning
- **Human:** Review status ('accepted' or 'refused')

**UI Component:** Interactive citation review cards (`src/bmlibrarian/gui/components.py`) with:
- Full abstract display
- Yellow-highlighted passages (using TextSpan with bgcolor)
- Three-state toggle button (Unrated → Accepted → Refused)
- 📌 markers around highlighted text for visibility

### 4. Query Generation (CLI Workflow)

**File:** `src/bmlibrarian/cli/query_processing.py`

When users manually edit AI-generated queries in the CLI:

```python
elif choice == '2':
    # Manual editing
    original_query = current_query
    new_query = self.ui.get_manual_query_edit(current_query)

    if new_query != current_query:
        current_query = new_query

        # Log the human edit to database
        from bmlibrarian.agents import get_human_edit_logger
        logger = get_human_edit_logger()
        logger.log_query_edit(
            user_question=question,
            system_prompt="QueryAgent system prompt for converting natural language to PostgreSQL ts_query",
            ai_query=original_query,
            human_query=current_query
        )
```

**Data Captured:**
- **Context:** System prompt + user question
- **Machine:** Original AI-generated ts_query
- **Human:** Human-edited ts_query

## Usage Examples

### Document Scoring Edit

When a user changes an AI score from 3 to 4:

```
Context:
User Question: What are the cardiovascular benefits of exercise in elderly populations?

Document to Evaluate:
Title: Cardiovascular Benefits of Exercise in Elderly Patients
Abstract: This randomized controlled trial examined the effects...
Authors: Smith, J., Johnson, A., Williams, B.
Publication: Journal of Cardiology
Publication Date: 2023-05-15

Machine:
{
  "score": 3,
  "reasoning": "Document provides relevant information on exercise and cardiovascular health in elderly, but lacks comprehensive data on all cardiovascular benefits."
}

## Querying the Data

### View Recent Edits

```sql
SELECT 
    id,
    LEFT(context, 100) as context_preview,
    LEFT(machine, 80) as machine_preview,
    LEFT(human, 80) as human_preview,
    timestamp
FROM human_edited
ORDER BY timestamp DESC
LIMIT 10;
```

### Count Edits by Type

To distinguish between scoring and query edits, examine the context:

```sql
-- Query edits (context contains "ts_query" or "PostgreSQL")
SELECT COUNT(*) as query_edit_count
FROM human_edited
WHERE context LIKE '%ts_query%' OR context LIKE '%PostgreSQL%';

-- Scoring edits (context contains "Document to Evaluate")
SELECT COUNT(*) as scoring_edit_count
FROM human_edited
WHERE context LIKE '%Document to Evaluate%';
```

### Export Training Data

```sql
-- Export for training
COPY (
    SELECT context, machine, human
    FROM human_edited
    WHERE human IS NOT NULL
    ORDER BY timestamp
) TO '/tmp/human_edits_training_data.csv' WITH CSV HEADER;
```

## Future Extensions

The flexible `log_edit()` method can be easily extended for other types of human edits:

### Citation Review Logging

```python
logger.log_edit(
    context=f"User Question: {question}\n\nDocument: {doc_title}\n\nPassage: {passage}",
    machine_output=json.dumps({"relevance": ai_relevance, "summary": ai_summary}),
    human_edit=json.dumps({"relevance": human_relevance, "summary": human_summary}) if edited else None
)
```

### Report Revision Logging

```python
logger.log_edit(
    context=f"User Question: {question}\n\nCitations: {citation_count}",
    machine_output=original_report_text,
    human_edit=revised_report_text if revised else None
)
```

### Counterfactual Question Approval

```python
logger.log_edit(
    context=f"Original Claims: {claims}\n\nOriginal Report: {report}",
    machine_output=json.dumps({"questions": ai_questions, "priority": priorities}),
    human_edit=json.dumps({"questions": approved_questions}) if user_modified else None
)
```

## Best Practices

1. **Only Log Changes**: Set `log_all=False` (default) to only log when humans make edits
2. **Fail Gracefully**: Wrap logging calls in try-except to prevent workflow failures
3. **Preserve Context**: Include complete prompts in the context field for accurate reconstruction
4. **Use JSON for Structured Data**: Format machine and human outputs as JSON when data is structured
5. **Privacy Considerations**: Be mindful that research questions and document content are logged

## Testing

Run the test suite to verify logging functionality:

```bash
uv run python test_human_edit_logging.py
```

Expected output:
- ✅ Successfully logged document score edit (override: 3 → 4)
- ✅ Successfully handled no edit case (AI score accepted)
- ✅ Successfully logged query edit
- ✅ Found entries in database

## Troubleshooting

### "relation 'human_edited' does not exist"

Ensure the table exists and you have permissions:

```sql
-- Create table if needed (should already exist)
CREATE TABLE IF NOT EXISTS human_edited (
    id SERIAL PRIMARY KEY,
    context TEXT,
    machine TEXT,
    human TEXT,
    timestamp TIMESTAMP DEFAULT NOW()
);

-- Grant permissions
GRANT ALL PRIVILEGES ON TABLE human_edited TO your_username;
GRANT USAGE, SELECT ON SEQUENCE human_edited_id_seq TO your_username;
```

### Connection Issues

Verify environment variables are set:

```bash
echo $POSTGRES_HOST
echo $POSTGRES_USER
echo $POSTGRES_DB
```

These should match your PostgreSQL configuration.
