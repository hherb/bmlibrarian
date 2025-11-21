# Citation Review System - Implementation Summary

## Overview

BMLibrarian now features an interactive citation review interface that allows users to accept or refuse each extracted citation. Citations are displayed with their full abstract and highlighted passages, making it easy to validate the AI's extraction quality.

## Features

### Interactive Review Interface
- **Full Abstract Display**: See the complete abstract for each citation
- **Highlighted Passages**: Cited text is highlighted within the abstract context
- **Three-State Toggle**: Each citation can be: ❌ Refused → ⚪ Unrated → ✅ Accepted
- **Citation Summary**: AI-generated summary for quick review
- **Document Metadata**: Title, authors, publication date

### Visual Design

```
┌───────────────────────────────────────────────────────────┐
│ Citation Review (5 citations extracted)                  │
│ Review each citation. Toggle: Refuse ❌ → Unrated ⚪ → Accept ✅ │
│                                                           │
│ ┌─────────────────────────────────────────────────────┐ │
│ │ Citation 1                                    [⚪]    │ │
│ │ 📄 Fish Oil and Heart Health: A Meta-Analysis        │ │
│ │                                                       │ │
│ │ Summary:                                              │ │
│ │ This meta-analysis found significant cardiovascular   │ │
│ │ benefits from omega-3 supplementation...              │ │
│ │                                                       │ │
│ │ Abstract (highlighted passage):                       │ │
│ │ Fish oil supplements have been widely studied for     │ │
│ │ their potential health benefits. **==➤ Our analysis   │ │
│ │ of 25 randomized controlled trials demonstrated a     │ │
│ │ 15% reduction in cardiovascular events ⬅==**          │ │
│ │ among patients taking omega-3 fatty acids...          │ │
│ └─────────────────────────────────────────────────────┘ │
│                                                           │
│ [Continue with Reviewed Citations] [Continue with All]   │
└───────────────────────────────────────────────────────────┘
```

## User Workflow

1. **Citation Extraction Complete**
   - System extracts relevant passages from high-scoring documents
   - Citations displayed in scrollable review interface

2. **Review Each Citation**
   - Click toggle button to cycle through states:
     - ⚪ **Unrated** (default) - No decision made
     - ✅ **Accepted** - Citation is accurate and relevant
     - ❌ **Refused** - Citation is inaccurate or irrelevant

3. **Continue Workflow**
   - **"Continue with Reviewed Citations"** - Only use accepted/unrated citations
   - **"Continue with All Citations"** - Use all citations regardless of review

## Database Logging

### Citation Review Data

Reviews are logged to the `human_edited` table:

```sql
-- Accepted citation
{
  "context": "User Question: What are the benefits of fish oil?\n\nDocument: Fish Oil and Heart Health...\n\nAI Summary: ...\n\nExtracted Passage: ...\n\nFull Abstract: ...",
  "machine": "{\"passage\": \"...\", \"summary\": \"...\", \"relevance_score\": 0.92}",
  "human": "ACCEPTED"
}

-- Refused citation
{
  "context": "User Question: What are the benefits of fish oil?\n\nDocument: ...",
  "machine": "{\"passage\": \"...\", \"summary\": \"...\", \"relevance_score\": 0.85}",
  "human": "REFUSED"
}

-- Unrated citations are NOT logged (passive acceptance)
```

### Human Column Values
- `"ACCEPTED"` - User explicitly approved this citation
- `"REFUSED"` - User explicitly rejected this citation
- `NULL` - Citation was not logged (unrated/passive)

## Implementation Details

### Citation Model Enhancement
[citation_agent.py](src/bmlibrarian/agents/citation_agent.py:34-35)

```python
@dataclass
class Citation:
    # ... existing fields ...
    human_review_status: Optional[str] = None  # 'accepted', 'refused', or None
    abstract: Optional[str] = None  # Full abstract for review display
```

### GUI Component
[components.py](src/bmlibrarian/gui/components.py:748-976)

Key methods:
- `enable_citation_review()` - Show citation review interface
- `_create_citation_review_card()` - Build each citation card
- `_highlight_passage_in_abstract()` - Highlight cited text
- `_toggle_citation_status()` - Handle status changes
- `disable_citation_review()` - Clean up after review

### Interactive Handler
[interactive_handler.py](src/bmlibrarian/gui/interactive_handler.py:230-309)

- `get_user_approval_for_citations()` - Entry point for citation review
- `_show_interactive_citation_review()` - Display and manage review interface
- Returns: `Dict[int, str]` mapping citation indices to status

### Logging
[human_edit_logger.py](src/bmlibrarian/agents/human_edit_logger.py:205-257)

```python
logger.log_citation_review(
    user_question="What are the benefits of fish oil?",
    citation=citation_obj,
    review_status='accepted'  # or 'refused' or None
)
```

## Usage Example

```python
# In workflow
citations = citation_agent.extract_citations(scored_documents)

if interactive_mode:
    # Show review interface
    citation_reviews = interactive_handler.get_user_approval_for_citations(
        citations, update_callback
    )

    # Filter citations based on reviews
    filtered_citations = []
    for i, citation in enumerate(citations):
        review_status = citation_reviews.get(i)

        if review_status == 'refused':
            continue  # Skip refused citations
        elif review_status == 'accepted':
            citation.human_review_status = 'accepted'
            filtered_citations.append(citation)
        else:  # unrated
            citation.human_review_status = None
            filtered_citations.append(citation)

    # Log reviews to database
    for i, citation in enumerate(citations):
        if i in citation_reviews:
            logger.log_citation_review(
                user_question=research_question,
                citation=citation,
                review_status=citation_reviews[i]
            )
```

## SQL Queries

### Count citation reviews by status
```sql
SELECT
    COUNT(CASE WHEN human = 'ACCEPTED' THEN 1 END) as accepted,
    COUNT(CASE WHEN human = 'REFUSED' THEN 1 END) as refused,
    COUNT(*) as total_reviewed
FROM human_edited
WHERE context LIKE '%AI Summary:%' AND context LIKE '%Extracted Passage:%';
```

### Acceptance rate
```sql
SELECT
    ROUND(
        100.0 * COUNT(CASE WHEN human = 'ACCEPTED' THEN 1 END) /
        NULLIF(COUNT(*), 0),
        2
    ) as acceptance_rate_percent
FROM human_edited
WHERE context LIKE '%Extracted Passage:%';
```

### Recent rejections (to identify problematic citations)
```sql
SELECT
    LEFT(machine::json->>'summary', 100) as summary_preview,
    machine::json->>'relevance_score' as ai_relevance,
    timestamp
FROM human_edited
WHERE human = 'REFUSED'
  AND context LIKE '%Extracted Passage:%'
ORDER BY timestamp DESC
LIMIT 10;
```

## Benefits

### Quality Control
1. **Catch Hallucinations**: Identify when AI extracts incorrect passages
2. **Verify Relevance**: Confirm citations actually answer the question
3. **Context Validation**: See passage in full abstract context

### Training Data
1. **Positive Examples**: Accepted citations show good extractions
2. **Negative Examples**: Refused citations identify failure patterns
3. **Quality Metrics**: Acceptance rate indicates model performance

### User Experience
1. **Transparency**: Users see exactly what's being cited
2. **Control**: Users can filter out irrelevant citations
3. **Confidence**: Review builds trust in generated reports

## Highlighting Algorithm

```python
def _highlight_passage_in_abstract(abstract, passage):
    # Clean whitespace
    clean_passage = ' '.join(passage.split())

    # Case-insensitive search
    pattern = re.compile(re.escape(clean_passage), re.IGNORECASE)
    match = pattern.search(abstract)

    if match:
        # Highlight with markdown
        start, end = match.span()
        return (
            abstract[:start] +
            f"**==➤ {abstract[start:end]} ⬅==**" +
            abstract[end:]
        )
    else:
        # Fallback: show separately
        return f"**📌 Cited Passage:** {passage}\n\n**Full Abstract:** {abstract}"
```

## Future Enhancements

### Partial Edits
Allow users to edit the citation text or summary rather than just accept/refuse.

### Batch Operations
- "Accept All" / "Refuse All" buttons
- Filter by relevance score
- Search citations

### Citation Quality Scores
Track and display:
- AI confidence score
- Historical acceptance rate for similar patterns
- Warning flags for low-quality extractions

### Integration with Reports
- Mark reviewed citations in generated reports
- Show review status to readers
- Link back to original review

## Testing

```bash
# Test in GUI
python bmlibrarian_research_gui.py

# Workflow:
# 1. Enter research question: "What are the benefits of fish oil?"
# 2. Review document scores
# 3. Extract citations
# 4. **NEW**: Review citations interface appears
# 5. Toggle each citation's status
# 6. Continue with reviewed citations

# Verify database
psql -d knowledgebase -c "
    SELECT COUNT(*), human
    FROM human_edited
    WHERE context LIKE '%Extracted Passage:%'
    GROUP BY human;
"
```

## Summary

✅ **Interactive Review UI** - Full abstract display with highlighted passages
✅ **Three-State Toggle** - Accept / Refuse / Unrated
✅ **Database Logging** - ACCEPTED / REFUSED tracked in human_edited table
✅ **Citation Filtering** - Use only reviewed citations in reports
✅ **Quality Control** - Catch hallucinations and verify relevance

This provides essential human-in-the-loop validation for citation extraction! 🎯
