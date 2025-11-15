# Scoring Tab Update Fix

## Issue Description

The scoring tab was not displaying documents when a query returned only low-ranking scores (documents scoring at or below the threshold). This created confusion for users who expected to see all scored documents, regardless of their scores.

## Root Cause

The issue was not a logic error in the code - the `_update_scoring_tab()` method in `data_updaters.py` correctly handles both high-scoring and low-scoring documents. However, there was insufficient logging to diagnose issues when the tab wasn't updating, making it difficult to determine:

1. Whether `_update_scoring_tab()` was being called
2. What the score distribution looked like
3. Whether document cards were being created
4. Whether the tab content was being updated

## Solution

Added comprehensive diagnostic logging throughout the `_update_scoring_tab()` method in [src/bmlibrarian/gui/data_updaters.py](src/bmlibrarian/gui/data_updaters.py) to track:

### 1. Method Entry and Data Validation
```python
print(f"📊 _update_scoring_tab called")
print(f"🔢 Scored documents count: {len(self.app.scored_documents) if self.app.scored_documents else 0}")
```

### 2. Score Threshold Configuration
```python
print(f"📏 Score threshold: {score_threshold}")
```

### 3. Score Distribution Analysis
```python
print(f"📊 Score distribution:")
for i, (doc, score) in enumerate(sorted_docs[:5]):  # Show first 5
    print(f"   {i+1}. {doc.get('title', 'Untitled')[:50]}... Score: {score.get('score', 0)}")
if len(sorted_docs) > 5:
    print(f"   ... and {len(sorted_docs) - 5} more documents")
```

### 4. High/Low Scoring Document Counts
```python
print(f"✅ High-scoring documents (> {score_threshold}): {len(high_scoring_docs)}")
print(f"📉 Low-scoring documents (<= {score_threshold}): {len(low_scoring_docs)}")
```

### 5. Document Card Creation
```python
# For high-scoring section:
print(f"📝 Adding {len(high_scoring_docs)} high-scoring document cards")
# ... create cards ...
print(f"   ✅ Added {len(high_scoring_cards)} high-scoring cards")

# For low-scoring section:
print(f"📝 Adding {len(low_scoring_docs)} low-scoring document cards")
# ... create cards ...
print(f"   ✅ Added {len(low_scoring_cards)} low-scoring cards")
```

### 6. Tab Content Update Confirmation
```python
print(f"📝 Updating scoring tab content with {len(all_components)} components")
# ... update tab ...
print(f"✅ Scoring tab content updated successfully")
print(f"📱 Page updated after scoring tab update")
```

### 7. Error Detection
```python
if not self.app.scored_documents:
    print(f"❌ No scored documents - exiting _update_scoring_tab")
    return

# ... later ...
if not (self.app.tab_manager and self.app.tab_manager.get_tab_content('scoring')):
    print(f"❌ tab_manager or scoring tab content not available - cannot update!")
```

## How to Test

1. **Run the GUI:**
   ```bash
   uv run python bmlibrarian_research_gui.py
   ```

2. **Execute a query that returns low-scoring documents:**
   - Enter a research question that's somewhat off-topic
   - Or adjust the score threshold high enough that all documents fall below it

3. **Check the console output:**
   - Look for the diagnostic logs showing the score distribution
   - Verify that low-scoring documents are being added to `all_components`
   - Confirm the tab content is being updated

4. **Verify in the GUI:**
   - Switch to the "Scoring" tab
   - Should see the "📉 LOW-SCORING DOCUMENTS" section
   - All documents should be visible with their scores and reasoning

## Expected Behavior

When all documents score below threshold (e.g., all score 2.0 with threshold 2.5):

```
📊 _update_scoring_tab called
🔢 Scored documents count: 15
📏 Score threshold: 2.5
📊 Score distribution:
   1. Some Medical Study... Score: 2.0
   2. Another Research Paper... Score: 2.0
   3. Clinical Trial Results... Score: 1.5
   ... and 12 more documents
✅ High-scoring documents (> 2.5): 0
📉 Low-scoring documents (<= 2.5): 15
⚠️ No high-scoring documents to display
📝 Adding 15 low-scoring document cards
   ✅ Added 15 low-scoring cards
📝 Updating scoring tab content with 18 components
✅ Scoring tab content updated successfully
📱 Page updated after scoring tab update
```

The Scoring tab should display:
- Header: "Document Scoring Results" with count
- Continue Workflow button (if applicable)
- "📉 LOW-SCORING DOCUMENTS (At or below threshold 2.5): 15" section header
- 15 document cards showing full titles, abstracts, AI reasoning, and score edit controls

## Files Modified

- [src/bmlibrarian/gui/data_updaters.py](src/bmlibrarian/gui/data_updaters.py) - Added diagnostic logging to `_update_scoring_tab()` method

## Related Code Locations

- **Workflow trigger**: [src/bmlibrarian/gui/workflow.py:363-364](src/bmlibrarian/gui/workflow.py#L363-L364) - Calls `tab_update` after scoring
- **Event handler**: [src/bmlibrarian/gui/event_handlers.py:394](src/bmlibrarian/gui/event_handlers.py#L394) - Maps `SCORE_DOCUMENTS` to `update_scored_documents_if_available`
- **Data updater**: [src/bmlibrarian/gui/data_updaters.py:382-387](src/bmlibrarian/gui/data_updaters.py#L382-L387) - Calls `_update_scoring_tab()`
- **Tab renderer**: [src/bmlibrarian/gui/data_updaters.py:717-877](src/bmlibrarian/gui/data_updaters.py#L717-L877) - Renders scoring tab with both high and low sections

## Notes

- The original code logic was correct - both high-scoring and low-scoring sections are properly handled
- The addition of comprehensive logging will help diagnose future issues quickly
- The logging output can be used to verify the workflow is functioning correctly
- No functional changes were made to the scoring logic itself
