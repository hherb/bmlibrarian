# Citation Extraction Progress Enhancements

> **Note (2026-10-16)**: this describes the Citations tab of the former Flet Research GUI (`bmlibrarian_research_gui.py`), which has been removed together with all Flet GUIs. It is kept as a historical record; the Qt Research tab (`bmlibrarian_qt.py`) has its own implementation.

## Overview
Enhanced the Citations tab with improved progress feedback during citation extraction.

## What Was Added

### 1. Spinner Animation (✅ Implemented)
- **Component**: Animated `ProgressRing` (purple spinning circle)
- **Location**: Left side of progress section in Citations tab
- **Purpose**: Provides visual indication that processing is active
- **Specs**: 20x20px, 2px stroke width, purple color

### 2. Current Document Display (✅ Implemented)
- **Component**: Text field showing current document title
- **Format**: `📄 Processing: [Document Title]`
- **Location**: Below main progress bar
- **Features**:
  - Truncates long titles (max 80 chars + "...")
  - Updates in real-time as each document is processed
  - Hidden when not processing

### 3. Estimated Time Remaining (✅ Implemented)
- **Component**: Text field with calculated ETA
- **Format**: `⏱️ ETA: Xm Ys` or `⏱️ ETA: Xh Ym` or `⏱️ ETA: Xs`
- **Location**: Below current document display
- **Features**:
  - Dynamically calculated based on average time per document
  - Updates after each document is processed
  - Automatically formats for seconds, minutes, or hours
  - Hidden when not applicable

## Visual Layout

```
┌─────────────────────────────────────────────────────────────┐
│ Citation Extraction                                          │
│ Relevant passages extracted from high-scoring documents.     │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│ ⭕ Extracting citations: 12/25 (48.0%)                      │
│    📄 Processing: Long-term cardiovascular benefits of...   │
│    ⏱️ ETA: 1m 23s                                           │
│                                                              │
│ ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓░░░░░░░░░░░░░░░░░░░░░░░░  48%          │
│                                                              │
│ [Citation Cards Will Appear Here]                           │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## Implementation Details

### Modified Files

1. **[tab_manager.py](src/bmlibrarian/gui/tab_manager.py#L455-L530)**
   - Added `citations_progress_ring` (spinner)
   - Added `citations_current_doc` (document title)
   - Added `citations_eta` (time estimate)
   - Organized components in progress container
   - Enhanced progress bar thickness (6px)

2. **[data_updaters.py](src/bmlibrarian/gui/data_updaters.py#L83-L153)**
   - Extended `show_citations_progress()` method signature
   - Added `current_doc_title` parameter
   - Added `elapsed_time` parameter
   - Implemented ETA calculation algorithm
   - Added progress container visibility control

3. **[workflow.py](src/bmlibrarian/gui/workflow.py#L277-L313)**
   - Added time tracking with `time.time()`
   - Created mutable dict to share document info
   - Enhanced progress callback to pass document title and elapsed time
   - Integrated with existing StepCard progress updates

4. **[citation_agent.py](src/bmlibrarian/agents/citation_agent.py#L212-L216)**
   - Modified progress callback to include document title
   - Extracts title from document dict
   - Maintains backwards compatibility with optional parameter

### Progress Callback Signature

**Before:**
```python
progress_callback(current: int, total: int)
```

**After:**
```python
progress_callback(current: int, total: int, doc_title: str = None)
```

The optional `doc_title` parameter maintains backwards compatibility with existing code.

### ETA Calculation Algorithm

```python
if current > 0 and elapsed_time > 0:
    time_per_doc = elapsed_time / current
    remaining_docs = total - current
    eta_seconds = time_per_doc * remaining_docs

    # Format appropriately
    if eta_seconds < 60:
        return f"{int(eta_seconds)}s"
    elif eta_seconds < 3600:
        minutes, seconds = divmod(eta_seconds, 60)
        return f"{int(minutes)}m {int(seconds)}s"
    else:
        hours = eta_seconds / 3600
        minutes = (eta_seconds % 3600) / 60
        return f"{int(hours)}h {int(minutes)}m"
```

## User Experience Improvements

### Before Enhancement
- Basic progress bar
- Percentage text only
- No indication of what's being processed
- No time estimate

### After Enhancement
- ✅ Animated spinner showing active processing
- ✅ Real-time document titles showing current work
- ✅ Accurate time estimates for completion
- ✅ Enhanced progress bar (thicker, more visible)
- ✅ Better organized progress information

## Testing

### Unit Tests
Run the test script to verify functionality:
```bash
uv run python test_citation_progress.py
```

Expected output:
- Progress updates with percentages
- Document titles displayed correctly
- ETA calculations shown
- Callback signature validation

### Integration Testing
The Flet GUI used for these tests has been removed (2026-10-16). Citation extraction progress can be observed in the Citations sub-tab of the Qt Research tab:
```bash
uv run python bmlibrarian_qt.py
```

## Performance Impact

- **Minimal overhead**: Time calculations and string formatting are negligible
- **No blocking**: Progress updates happen in existing callback, no additional waits
- **Efficient**: Only updates visible components when tab is active

## Future Enhancements (Optional)

Potential improvements for future iterations:
- Show number of citations found vs documents processed
- Color-code progress based on citation success rate
- Add pause/cancel button for long extractions
- Show preview of extracted citation text in progress area
- Export progress log for debugging

## Backwards Compatibility

✅ All changes are backwards compatible:
- Optional parameter in callback signature
- Existing code without document titles will still work
- Progress display gracefully handles missing data
- No breaking changes to existing APIs
