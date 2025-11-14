# Scoring Tab Update During Iterative Search - Fix

## Root Cause Identified

The scoring tab was not displaying documents when the system found fewer high-scoring documents than the `min_relevant` threshold (default: 10) because:

1. **Initial Scoring Completes** - Documents are scored (e.g., 36 documents, 1 high-scoring)
2. **Iterative Search Triggered** - System sees 1 < 10 and starts iterative search to find more
3. **Tab Update Blocked** - The `execute_document_scoring()` method doesn't return until iterative search completes
4. **User Sees Nothing** - The workflow's tab update (workflow.py:364) waits for `execute_document_scoring()` to return

## The Problem Flow

```
workflow.py:
  execute_document_scoring() called
    ↓
workflow_steps_handler.py:
  Score initial documents (e.g., 36 documents, 1 high-scoring)
    ↓
  Check: 1 < min_relevant (10)
    ↓
  Start iterative search (line 743-790)
    ← USER STUCK HERE, NO TAB UPDATE YET
    ↓
  Iterative search runs Phase 1, Phase 2...
    ↓
  Return all_scored_documents
    ↓
workflow.py:
  Store scored_documents (line 358)
    ↓
  Call tab update (line 364) ← FINALLY UPDATES, BUT TOO LATE
```

## The Solution

Update the scoring tab **BEFORE** starting the iterative search, so users can see:
- Documents already found and scored
- Their scores and reasoning
- The system is searching for more relevant documents

### Code Change Location

**File**: [src/bmlibrarian/gui/workflow_steps_handler.py](src/bmlibrarian/gui/workflow_steps_handler.py:746-764)

**What Changed**:
```python
# Before iterative search starts (line 746-764):
print(f"📊 Updating scoring tab with {len(all_scored_documents)} current documents before iterative search...")
if hasattr(self, 'data_updaters') and self.data_updaters:
    # Temporarily store in workflow executor so tab update can access them
    app = self.data_updaters.app
    if app and hasattr(app, 'workflow_executor') and app.workflow_executor:
        old_scored = getattr(app.workflow_executor, 'scored_documents', None)
        app.workflow_executor.scored_documents = all_scored_documents
        print(f"   - Stored {len(all_scored_documents)} scored documents in workflow_executor")
        self.data_updaters.update_scored_documents_if_available()
        print(f"✅ Scoring tab updated with initial results")
        # Restore old value (will be updated again after iterative search)
        if old_scored is not None:
            app.workflow_executor.scored_documents = old_scored
```

## Expected Behavior After Fix

### Scenario: Query finds 36 documents, only 1 high-scoring

**Before Fix**:
1. User sees "Scoring documents..." for a long time
2. Iterative search runs in background (could take minutes)
3. User sees no documents until everything completes
4. ❌ User can't see why documents scored low

**After Fix**:
1. User sees "Scoring documents..."
2. **Scoring tab updates immediately** showing:
   - 1 high-scoring document
   - 35 low-scoring documents with reasoning
3. Console shows: "⚠️ Found only 1/10 documents above threshold"
4. Console shows: "📊 Updating scoring tab with 36 current documents before iterative search..."
5. Console shows: "✅ Scoring tab updated with initial results"
6. Iterative search continues in background
7. ✅ User can review scores while more documents are being searched

### Console Output Pattern

```
📊 Workflow stored 36 scored documents for tab access
🔄 Triggering manual tab update for SCORE_DOCUMENTS

⚠️  Found only 1/10 documents above threshold
    Triggering iterative search for more relevant documents...

📊 Updating scoring tab with 36 current documents before iterative search...
   - Stored 36 scored documents in workflow_executor
🔍 update_scored_documents_if_available called
   - workflow_executor exists: True
📈 Found 36 scored documents in workflow_executor
✅ Updating Scoring tab with 36 scored documents
📊 update_scored_documents called with 36 documents
   - Stored in app.scored_documents
   - Calling _update_scoring_tab()...
📊 _update_scoring_tab called
🔢 Scored documents count: 36
📏 Score threshold: 2.5
📊 Score distribution:
   1. Some Study... Score: 3.0
   2. Another Paper... Score: 2.0
   3. Third Document... Score: 2.0
   ... and 33 more documents
✅ High-scoring documents (> 2.5): 1
📉 Low-scoring documents (<= 2.5): 35
📝 Adding 1 high-scoring document cards
   ✅ Added 1 high-scoring cards
📝 Adding 35 low-scoring document cards
   ✅ Added 35 low-scoring cards
📝 Updating scoring tab content with 38 components
✅ Scoring tab content updated successfully
📱 Page updated after scoring tab update
   - Back from _update_scoring_tab()
   - Calling page.update()...
   - Page updated
✅ Scoring tab updated with initial results

🔍 Starting iterative search to find at least 10 relevant documents...
   [... iterative search continues ...]
```

## Why This Matters

### User Experience Benefits

1. **Immediate Feedback**: Users see results as soon as initial scoring completes
2. **Transparency**: Users can see why documents scored low while more are being searched
3. **Manual Override**: Users can adjust scores if AI scored incorrectly
4. **Decision Making**: Users can decide if they want to wait for more results or proceed with what's found

### Technical Benefits

1. **Non-Blocking UI**: Tab updates don't wait for entire iterative search
2. **Progressive Enhancement**: Show data as it becomes available
3. **Better Debugging**: Users and developers can see what's happening at each stage

## Testing

### Test Case 1: Low-Scoring Query

**Setup**:
- Query: "methylprednisolone for acute mountain sickness prophylaxis"
- Expected: Most documents score ≤ 2.5

**Steps**:
1. Run GUI: `uv run python bmlibrarian_research_gui.py`
2. Enter the query above
3. Start research (auto or interactive mode)
4. Watch the console output

**Expected Result**:
- Scoring tab shows all documents immediately after initial scoring
- Console shows "📊 Updating scoring tab with X current documents before iterative search..."
- User can review documents while iterative search continues
- Iterative search message appears in console: "🔍 Starting iterative search..."

### Test Case 2: Good Query (High-Scoring Documents)

**Setup**:
- Query that typically returns many high-scoring documents
- Expected: ≥10 documents score > 2.5

**Steps**:
1. Same as above with different query

**Expected Result**:
- Scoring tab updates with all documents
- No iterative search triggered (enough high-scoring documents)
- Console does NOT show "Triggering iterative search..."

## Files Modified

1. **[src/bmlibrarian/gui/workflow_steps_handler.py](src/bmlibrarian/gui/workflow_steps_handler.py)** (lines 746-764)
   - Added tab update before iterative search
   - Temporary storage in workflow_executor
   - Proper restoration of old values

2. **[src/bmlibrarian/gui/data_updaters.py](src/bmlibrarian/gui/data_updaters.py)** (multiple locations)
   - Added comprehensive diagnostic logging (previous fix)
   - Helps verify tab updates are happening

## Related Issues

- **Iterative Search Performance**: Long-running searches block UI feedback
- **User Frustration**: No feedback during multi-minute scoring operations
- **Score Review**: Users need to see scores to understand if threshold/query needs adjustment

## Future Improvements

Consider:
1. **Real-time Updates**: Update tab incrementally as iterative search finds new documents
2. **Progress Indicator**: Show iterative search progress in scoring tab
3. **Cancel Button**: Allow users to stop iterative search if initial results are sufficient
4. **Threshold Adjustment**: Let users adjust `min_relevant` during search
