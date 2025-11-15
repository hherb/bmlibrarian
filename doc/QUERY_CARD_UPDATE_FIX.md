# Query Card Statistics Update Fix

## Issue

Query cards were not updating consistently during workflow execution:
- Cards remained stuck showing "Executing query..." even after queries completed
- Statistics (total docs, unique docs, high-scoring docs) were not displayed until ALL scoring completed
- Users saw no feedback during the 1-2 minute scoring phase despite queries completing successfully

**Example from user screenshot:**
- Queries #1 and #2 showed "30 docs"
- Queries #3-6 showed "Executing query..."
- Yet 91 documents were already found and scoring was in progress
- No indication that queries had executed successfully

## Root Causes

### 1. Single Update Point (After Scoring Only)

**Location**: [workflow_steps_handler.py:748](src/bmlibrarian/gui/workflow_steps_handler.py#L748)

Query cards were only updated ONCE - after document scoring completed:

```python
# Line 748 - Only update point (after scoring completes)
if hasattr(self, 'data_updaters') and self.data_updaters:
    self.data_updaters.update_query_cards_with_scoring_stats(stats)
```

**Impact**:
- Query execution completes in ~5-10 seconds
- Document scoring takes 1-2 minutes
- Users see "Executing query..." for the entire 2+ minute period
- No indication that queries have completed and documents are being scored

### 2. UI Update Method Created New Container

**Location**: [query_cards.py:280](src/bmlibrarian/gui/query_cards.py#L280)

The `update_stats()` method called `self._build()` which created a NEW container:

```python
def update_stats(self, ...):
    # Update statistics fields
    self.total_documents = total_documents
    # ...

    # BUG: This creates a NEW container, doesn't update the existing one
    self._build()  # Line 280 - creates new self.card_container
```

At line 126 of `_build()`:
```python
self.card_container = ft.Container(...)  # NEW container created
```

**Impact**:
- The old container displayed in the UI was never updated
- The new container was created but not added to the UI
- Even when stats were updated, UI showed old "Executing query..." state

## Solution

### Fix 1: Early Query Card Update (After Search)

**Location**: [workflow_steps_handler.py:486-513](src/bmlibrarian/gui/workflow_steps_handler.py#L486-L513)

Added query card update immediately after search completes, BEFORE scoring begins:

```python
# After search completes (line 486+)
if self.performance_tracker and self.session_id and hasattr(self, 'data_updaters') and self.data_updaters:
    try:
        # Get query statistics (total_documents, unique_documents available)
        stats = self.performance_tracker.get_query_statistics(
            session_id=self.session_id,
            score_threshold=threshold
        )

        if stats:
            # Update query cards with initial stats (total_documents, unique_documents)
            # high_scoring_documents will be 0 until scoring completes
            self.data_updaters.update_query_cards_with_scoring_stats(stats)
            print(f"✅ Query cards updated with initial statistics (total/unique docs)")
```

**Benefits**:
- Query cards update within 5-10 seconds after search starts
- Shows "30 docs", "15 unique" immediately
- high_scoring stats show as 0 until scoring completes
- Users see clear indication that queries executed successfully

### Fix 2: In-Place Stats Row Update

**Location**: [query_cards.py:279-287](src/bmlibrarian/gui/query_cards.py#L279-L287)

Changed `update_stats()` to update EXISTING container in place:

```python
def update_stats(self, ...):
    # Update statistics fields
    if total_documents is not None:
        self.total_documents = total_documents
    # ...

    # Rebuild ONLY the stats row
    new_stats_row = self._build_stats_row()

    # Update the existing card's content in place
    if self.card_container and self.card_container.content:
        # card_container.content is a Column with [header, spacer, query_display, spacer, stats_row]
        self.card_container.content.controls[4] = new_stats_row
        self.stats_row = new_stats_row
```

**Benefits**:
- Updates the container already displayed in the UI
- More efficient (only rebuilds stats row, not entire card)
- UI properly reflects stat changes when `page.update()` is called

### Fix 3: Improved Logging

**Location**: [workflow_steps_handler.py:749](src/bmlibrarian/gui/workflow_steps_handler.py#L749)

Clarified console logging for the second update (after scoring):

```python
print("✅ Query cards updated with COMPLETE statistics (including high-scoring docs)")
```

## Two-Phase Update Timeline

### Phase 1: After Search Completes (~5-10 seconds)

**Trigger**: Search completes, documents found
**Location**: workflow_steps_handler.py:486-513
**Statistics Available**:
- ✅ `total_documents`: Total docs found by each query
- ✅ `unique_documents`: Docs unique to each query
- ❌ `high_scoring_documents`: 0 (scoring not started)
- ❌ `unique_high_scoring`: 0 (scoring not started)

**User Experience**:
```
Query #1: 30 docs, 15 unique, 0 high-scoring
Query #2: 25 docs, 10 unique, 0 high-scoring
...
```

### Phase 2: After Scoring Completes (~1-2 minutes later)

**Trigger**: All documents scored
**Location**: workflow_steps_handler.py:748
**Statistics Available**:
- ✅ `total_documents`: Same as Phase 1
- ✅ `unique_documents`: Same as Phase 1
- ✅ `high_scoring_documents`: Docs scoring ≥ threshold
- ✅ `unique_high_scoring`: High-scoring docs unique to each query

**User Experience**:
```
Query #1: 30 docs, 15 unique, 8 high-scoring, 4 unique high
Query #2: 25 docs, 10 unique, 5 high-scoring, 2 unique high
...
```

## Console Output

### Successful Two-Phase Update

**After Search Completes (Phase 1):**
```
🔍 DEBUG: Updating query cards with initial statistics after search completes
🔍 DEBUG: Got 6 query statistics, updating query cards
   Card 1: 30 total, 15 unique, 0 high-scoring, 0 unique high, 2.35s
   Card 2: 25 total, 10 unique, 0 high-scoring, 0 unique high, 1.87s
   ...
✅ Query cards updated with initial statistics (total/unique docs)
```

**After Scoring Completes (Phase 2):**
```
🔍 DEBUG: Updating performance tracker with 91 document scores
🔍 DEBUG: Getting query statistics for session abc123 with threshold 2.5
🔍 DEBUG: Got 6 query statistics
   Card 1: 30 total, 15 unique, 8 high-scoring, 4 unique high, 2.35s
   Card 2: 25 total, 10 unique, 5 high-scoring, 2 unique high, 1.87s
   ...
✅ Query cards updated with COMPLETE statistics (including high-scoring docs)
```

## Files Modified

1. **[src/bmlibrarian/gui/workflow_steps_handler.py](src/bmlibrarian/gui/workflow_steps_handler.py)**
   - Lines 486-513: Added early query card update after search completes
   - Line 749: Improved logging for second update after scoring completes

2. **[src/bmlibrarian/gui/query_cards.py](src/bmlibrarian/gui/query_cards.py)**
   - Lines 279-287: Changed `update_stats()` to update existing container in place instead of creating new container

## Benefits

### User Experience
- **Immediate Feedback**: Query cards update within 5-10 seconds showing search results
- **Clear Progress**: Users see "30 docs" immediately, then "8 high-scoring" after scoring
- **No More Stuck Cards**: All cards update consistently, no "Executing query..." for 2+ minutes
- **Better Understanding**: Two-phase update shows search vs. scoring progress clearly

### Technical
- **More Efficient**: Only rebuilds stats row instead of entire card
- **Proper UI Updates**: Updates existing container that's already displayed
- **Consistent State**: Performance tracker provides stats at both phases
- **Better Logging**: Clear console messages for debugging

## Testing

To verify the fix works:

1. **Start Research GUI**: `uv run python bmlibrarian_research_gui.py`
2. **Enter Research Question** and start automated workflow
3. **Watch Query Cards** during execution:
   - Should update within 5-10 seconds showing total/unique docs
   - Should update again after scoring with high-scoring stats
4. **Check Console Output** for the two update messages:
   - "✅ Query cards updated with initial statistics (total/unique docs)"
   - "✅ Query cards updated with COMPLETE statistics (including high-scoring docs)"

## Related Issues

- **Scoring Tab Update**: [SCORING_TAB_ITERATIVE_SEARCH_FIX.md](SCORING_TAB_ITERATIVE_SEARCH_FIX.md)
- **Query Statistics Display**: Previous issue with inconsistent badge display
- **Performance Tracker**: Uses SQLite-based tracker for query performance analytics

## Technical Notes

### QueryPerformanceStats Structure

```python
@dataclass
class QueryPerformanceStats:
    model: str
    temperature: float
    query: str
    total_documents: int        # Available immediately after search
    unique_documents: int       # Available immediately after search
    high_scoring_documents: int  # Available after scoring (0 before)
    unique_high_scoring: int    # Available after scoring (0 before)
    execution_time: float       # Available immediately after search
```

### Performance Tracker Timing

The performance tracker can provide statistics at any time:
- **After Search**: `total_documents`, `unique_documents`, `execution_time` are accurate
- **Before Scoring**: `high_scoring_documents` and `unique_high_scoring` are 0
- **After Scoring**: All fields are accurate

This is why the two-phase update works - we can call `get_query_statistics()` twice:
1. After search (partial stats)
2. After scoring (complete stats)

### Flet UI Update Pattern

For Flet to properly update UI:
1. Modify the EXISTING control (don't create new ones)
2. Call `page.update()` to refresh the display

The old code violated #1 by creating new containers. The new code follows this pattern correctly.
