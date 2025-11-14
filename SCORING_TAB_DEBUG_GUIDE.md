# Scoring Tab Debug Guide

## Problem Statement

The scoring tab does not display scored documents when a query returns only low-ranking scores (documents scoring at or below the threshold). Users need to see ALL scored documents, including low-scoring ones, to understand why documents were scored low and to potentially adjust scores manually.

## Diagnostic Logging Added

I've added comprehensive diagnostic logging throughout the scoring tab update chain to help identify where the issue occurs:

### 1. Event Handler (event_handlers.py)

When a workflow step completes with "tab_update" or "completed" status:
```python
print(f"📌 {step.name} completed - updating tab...")
```

### 2. Data Updater Entry (data_updaters.py:update_scored_documents_if_available)

```python
print(f"🔍 update_scored_documents_if_available called")
print(f"   - workflow_executor exists: {hasattr(self.app, 'workflow_executor')}")
print(f"📈 Found {len(scored_docs) if scored_docs else 0} scored documents in workflow_executor")
```

### 3. Data Updater Main (data_updaters.py:update_scored_documents)

```python
print(f"📊 update_scored_documents called with {len(scored_documents)} documents")
print(f"   - Stored in app.scored_documents")
print(f"   - Calling _update_scoring_tab()...")
# ... call _update_scoring_tab() ...
print(f"   - Back from _update_scoring_tab()")
print(f"   - Calling page.update()...")
# ... call page.update() ...
print(f"   - Page updated")
```

### 4. Tab Update Method (data_updaters.py:_update_scoring_tab)

Detailed logging at every step:

```python
print(f"📊 _update_scoring_tab called")
print(f"🔢 Scored documents count: {len(self.app.scored_documents)}")
print(f"📏 Score threshold: {score_threshold}")

print(f"📊 Score distribution:")
for i, (doc, score) in enumerate(sorted_docs[:5]):  # Show first 5
    print(f"   {i+1}. {doc.get('title', 'Untitled')[:50]}... Score: {score.get('score', 0)}")

print(f"✅ High-scoring documents (> {score_threshold}): {len(high_scoring_docs)}")
print(f"📉 Low-scoring documents (<= {score_threshold}): {len(low_scoring_docs)}")

# For high-scoring section:
print(f"📝 Adding {len(high_scoring_docs)} high-scoring document cards")
print(f"   ✅ Added {len(high_scoring_cards)} high-scoring cards")
# OR
print(f"⚠️ No high-scoring documents to display")

# For low-scoring section:
print(f"📝 Adding {len(low_scoring_docs)} low-scoring document cards")
print(f"   ✅ Added {len(low_scoring_cards)} low-scoring cards")
# OR
print(f"⚠️ No low-scoring documents to display")

print(f"📝 Updating scoring tab content with {len(all_components)} components")
print(f"✅ Scoring tab content updated successfully")
print(f"📱 Page updated after scoring tab update")
# OR
print(f"❌ tab_manager or scoring tab content not available - cannot update!")
```

## How to Use This Logging

### Step 1: Run the GUI

```bash
uv run python bmlibrarian_research_gui.py
```

### Step 2: Execute a Query

Enter a research question and run the workflow. The console will show detailed output.

### Step 3: Analyze the Output

Look for this sequence in the console output when scoring completes:

#### Expected Output (Successful Update):

```
🔄 Triggering manual tab update for SCORE_DOCUMENTS
📊 Workflow stored 15 scored documents for tab access
📌 SCORE_DOCUMENTS completed - updating tab...
🔍 update_scored_documents_if_available called
   - workflow_executor exists: True
📈 Found 15 scored documents in workflow_executor
✅ Updating Scoring tab with 15 scored documents
📊 update_scored_documents called with 15 documents
   - Stored in app.scored_documents
   - Calling _update_scoring_tab()...
📊 _update_scoring_tab called
🔢 Scored documents count: 15
📏 Score threshold: 2.5
📊 Score distribution:
   1. Some Study Title... Score: 2.0
   2. Another Paper... Score: 2.0
   3. Third Document... Score: 1.5
   ... and 12 more documents
✅ High-scoring documents (> 2.5): 0
📉 Low-scoring documents (<= 2.5): 15
⚠️ No high-scoring documents to display
📝 Adding 15 low-scoring document cards
   ✅ Added 15 low-scoring cards
📝 Updating scoring tab content with 18 components
✅ Scoring tab content updated successfully
📱 Page updated after scoring tab update
   - Back from _update_scoring_tab()
   - Calling page.update()...
   - Page updated
```

#### Diagnostic Points:

1. **If you see** `❌ workflow_executor has no 'scored_documents' attribute`
   - **Problem**: Workflow executor isn't storing scored documents
   - **Check**: workflow.py line 358 - is `self.scored_documents = scored_documents` being executed?

2. **If you see** `❌ No scored documents to update Scoring tab`
   - **Problem**: scored_documents is empty or None
   - **Check**: workflow.py line 352-355 - is `execute_document_scoring()` returning an empty list?

3. **If you see** `❌ No scored documents - exiting _update_scoring_tab`
   - **Problem**: app.scored_documents is empty
   - **Check**: data_updaters.py line 385 - was the assignment successful?

4. **If you see** `⚠️ No low-scoring documents to display` (when you expect low-scoring docs)
   - **Problem**: Score threshold logic issue or scores are higher than expected
   - **Check**: The "Score distribution" output above this line - what are the actual scores?

5. **If you see** `❌ tab_manager or scoring tab content not available - cannot update!`
   - **Problem**: Tab infrastructure not initialized properly
   - **Check**: tab_manager.py - is the scoring tab created correctly?

6. **If logging stops before** `✅ Scoring tab content updated successfully`
   - **Problem**: Exception in `_update_scoring_tab()` or `update_tab_content()`
   - **Check**: Look for Python exceptions/tracebacks above the incomplete log output

7. **If you see** `⚠️  CRITICAL: No documents scored above threshold` **before** the tab update logs
   - **Problem**: Workflow is returning early when all docs are low-scoring
   - **Status**: This is expected behavior, but the tab update should still happen at line 364
   - **Check**: Does the "tab_update" callback happen before the workflow returns?

## Workflow Flow for Low-Scoring Documents

Here's what SHOULD happen when all documents score below the threshold:

1. **Scoring Completes** (workflow.py:352-355)
   ```python
   scored_documents = self.steps_handler.execute_document_scoring(...)
   ```

2. **Store Results** (workflow.py:358-359)
   ```python
   self.scored_documents = scored_documents
   ```

3. **Trigger Tab Update** (workflow.py:363-365) **← CRITICAL: This happens BEFORE the check**
   ```python
   update_callback(WorkflowStep.SCORE_DOCUMENTS, "tab_update", ...)
   ```

4. **Check for High-Scoring Docs** (workflow.py:370-377)
   ```python
   high_scoring_docs = [(doc, score) for doc, score in scored_documents
                        if score.get('score', 0) >= score_threshold]
   ```

5. **If No High-Scoring Docs** (workflow.py:378-415)
   - Update step card with "warning" status
   - Show dialog in interactive mode
   - **Return early** (workflow stops here)

The key insight is that **step 3 happens before step 5**, so the tab update should occur even when the workflow stops early.

## Testing Scenarios

### Scenario 1: All Documents Score Low

**Setup:**
- Run a query that returns documents
- All documents score <= 2.5 (default threshold)

**Expected:**
- Console shows all the logging sequence above
- Scoring tab displays all documents in "📉 LOW-SCORING DOCUMENTS" section
- User can review scores and reasoning
- User can manually adjust scores if needed

### Scenario 2: Mixed Scores

**Setup:**
- Some documents score > 2.5, some <= 2.5

**Expected:**
- Console shows both high and low-scoring sections being created
- Scoring tab displays both sections
- Workflow continues to citation extraction

### Scenario 3: Interactive Mode with Low Scores

**Setup:**
- Enable "Interactive mode" toggle
- Run query with all low-scoring results

**Expected:**
- Console shows tab update happening
- Workflow shows dialog: "Insufficient scoring results"
- User can choose "Retry with different queries" or "Halt workflow"
- Either way, scoring tab should show the low-scoring documents

## Next Steps

Once you have the console output:

1. **Share the console output** - This will help identify exactly where the process breaks
2. **Check the GUI** - Switch to the Scoring tab manually and see if it shows anything
3. **Try manual update** - In the GUI, try clicking any refresh/continue buttons

## Files Modified

- [src/bmlibrarian/gui/data_updaters.py](src/bmlibrarian/gui/data_updaters.py) - Added comprehensive logging
- [src/bmlibrarian/gui/workflow.py](src/bmlibrarian/gui/workflow.py) - Minor comment clarification

## Related Issues

- Workflow early return when no high-scoring docs (workflow.py:409, 415)
- Tab update timing relative to score threshold check (workflow.py:364 vs 378)
- Thread safety for GUI updates from background thread
- ScoringInterface container vs normal tab content updates
