# Counterfactual Search Fix: Statement vs Question

## Problem

The counterfactual search was not working as intended because it was using **questions** instead of **statements** for database searches.

### Example of the Issue:

**Original Implementation:**
- Claim: "Lipophilic statins with clarithromycin cause significant drug interactions"
- Generated: "What clinical studies report no significant interaction between simvastatin and clarithromycin?"
- **Problem**: Medical literature contains statements, not questions. Documents don't say "What studies show X?" - they say "X was observed" or "No X was found."

### Why This Failed:

1. Questions are rare in medical abstracts and full text
2. Searching for "What studies..." won't match documents that say "No interaction was observed..."
3. The search query derived from a question is less likely to match contradictory evidence

## Solution

The CounterfactualAgent now generates **both**:

1. **Counterfactual Statement** - A declarative statement expressing the opposite claim
2. **Research Question** - A question for human understanding

### Example of Fixed Implementation:

**New Implementation:**
- **Original Claim**: "Lipophilic statins with clarithromycin cause significant drug interactions"
- **Counterfactual Statement**: "No significant interactions occur between lipophilic statins and clarithromycin"
  - ✓ This is what gets converted to a database query
  - ✓ This matches how evidence appears in literature
- **Research Question**: "What studies report no significant interaction between simvastatin and clarithromycin?"
  - ✓ This helps humans understand what we're looking for
  - ✓ This provides context but is NOT used for search

## Changes Made

### 1. CounterfactualQuestion Dataclass
```python
@dataclass
class CounterfactualQuestion:
    """Represents a research question designed to find contradictory evidence."""
    counterfactual_statement: str  # NEW: The opposite claim as a declarative statement
    question: str                   # Research question for human understanding
    reasoning: str
    target_claim: str
    search_keywords: List[str]
    priority: str
    created_at: Optional[datetime] = None
```

### 2. System Prompt Enhancement
The prompt now explicitly instructs the LLM to generate both:
- A counterfactual STATEMENT (declarative, not interrogative)
- A research QUESTION (for context)

Example from the prompt:
```
- Original: "Lipophilic statins with clarithromycin cause significant interactions"
  → Statement: "No significant interactions occur between lipophilic statins and clarithromycin"
  → Question: "What studies report safe co-prescription of lipophilic statins with clarithromycin?"
```

### 3. Query Generation
```python
# OLD: Used the question for database search
db_query = query_agent.convert_question(question.question)

# NEW: Uses the statement for database search
db_query = query_agent.convert_question(question.counterfactual_statement)
```

### 4. Document Scoring and Citation Extraction
```python
# Now uses counterfactual_statement instead of question for:
# - Scoring document relevance
# - Extracting citations
score_result = scoring_agent.evaluate_document(
    query_info['counterfactual_statement'], result
)

citation = citation_agent.extract_citation_from_document(
    query_info['counterfactual_statement'], doc, min_relevance=0.4
)
```

### 5. Display Updates
All display code now shows both fields properly labeled:
- CLI formatting ([formatting.py](src/bmlibrarian/cli/formatting.py))
- GUI report builder ([report_builder.py](src/bmlibrarian/gui/report_builder.py))
- GUI display utilities ([display_utils.py](src/bmlibrarian/gui/display_utils.py))

Example output:
```markdown
**Original Claim:** Lipophilic statins with clarithromycin cause significant interactions

**Counterfactual Statement:** No significant interactions occur between lipophilic statins and clarithromycin

**Research Question:** What studies report no significant interaction between simvastatin and clarithromycin?
```

## Impact

### Before Fix:
- Counterfactual searches often returned no results
- Questions didn't match declarative statements in literature
- Lower success rate in finding contradictory evidence

### After Fix:
- Counterfactual statements better match medical literature content
- Database searches more likely to find contradictory evidence
- Both statement (for search) and question (for understanding) are available
- Improved transparency about what is being searched vs. what is being asked

## Testing

A test script ([test_counterfactual_fix.py](test_counterfactual_fix.py)) verifies:
1. CounterfactualAgent generates both statements and questions
2. Statements are used for database queries
3. Questions are available for display
4. Formatted reports include both fields
5. Query generation uses statements, not questions

Run test with:
```bash
uv run python test_counterfactual_fix.py
```

## Files Modified

1. **Core Agent**:
   - `src/bmlibrarian/agents/counterfactual_agent.py`
     - Updated system prompt
     - Modified CounterfactualQuestion dataclass
     - Updated query generation to use statements
     - Updated scoring/citation to use statements
     - Updated formatting methods

2. **Display/Output**:
   - `src/bmlibrarian/cli/formatting.py` - CLI display
   - `src/bmlibrarian/gui/report_builder.py` - GUI report building
   - `src/bmlibrarian/gui/display_utils.py` - GUI display components

3. **Testing**:
   - `test_counterfactual_fix.py` - New test script

## Backward Compatibility

⚠️ **Breaking Change**: The JSON structure returned by CounterfactualAgent has changed:

**Old Structure:**
```json
{
  "claim": "...",
  "counterfactual_statement": "What studies show...?",  // Actually a question
  "counterfactual_evidence": [...]
}
```

**New Structure:**
```json
{
  "claim": "...",
  "counterfactual_statement": "No interaction occurs...",  // Now a statement
  "counterfactual_question": "What studies show...?",      // Explicit question field
  "counterfactual_evidence": [...]
}
```

Any code parsing the CounterfactualAgent output should be updated to use the new field structure.

## Future Improvements

1. **A/B Testing**: Compare success rates of statement-based vs question-based searches
2. **Hybrid Approach**: Use both statements and questions in parallel searches
3. **Statement Quality**: Add validation that statements are truly declarative
4. **Query Optimization**: Fine-tune query generation specifically for counterfactual statements

## Summary

The counterfactual search now uses **declarative statements** instead of **interrogative questions** for database searches, significantly improving the likelihood of finding contradictory evidence in medical literature. Both statements and questions are available for appropriate contexts: statements for search, questions for human understanding.
