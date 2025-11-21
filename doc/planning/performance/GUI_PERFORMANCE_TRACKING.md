# GUI Performance Tracking Integration

## Overview

Extended the query performance tracking system to display statistics in the Research GUI's Search tab. After document scoring completes, users can see detailed performance metrics for each query in a visually appealing, interactive format.

## Implementation Summary

### UI Components Added

1. **Performance Statistics Container** (`tab_manager.py`)
   - Blue-bordered container in Search tab
   - Initially hidden, shown after scoring completes
   - Scrollable content with formatted statistics

2. **Summary Metrics Cards** (5 cards at top)
   - **Queries**: Total number of queries executed
   - **Total Docs**: Sum of documents found across all queries
   - **High-Scoring**: Documents meeting relevance threshold
   - **Unique**: Documents found by only one query
   - **Avg Time**: Average query execution time

3. **Per-Query Performance Cards** (one per query)
   - Header with query number, model name, and temperature
   - Metrics grid with 5 columns:
     - **Total**: Total documents found
     - **≥Threshold**: High-scoring documents (≥3.0 by default)
     - **Unique**: Documents unique to this query
     - **Unique High**: High-scoring docs unique to this query
     - **Time**: Execution time in seconds
   - Query text display (truncated at 80 characters)

### Visual Design

**Color Scheme:**
- Container background: Light blue (BLUE_50)
- Container border: Blue (BLUE_200)
- Metric cards: White background with colored text
  - Queries: Blue (BLUE_700)
  - Total Docs: Green (GREEN_700)
  - High-Scoring: Orange (ORANGE_700)
  - Unique: Purple (PURPLE_700)
  - Avg Time: Teal (TEAL_700)

**Layout:**
- Cards use responsive wrapping for different screen sizes
- Metrics displayed in columns for easy comparison
- Dividers separate different metric categories
- Query text is selectable for copying

### Integration Flow

```
1. User starts workflow with multi-model enabled
2. Document search executes multiple queries
   └─> Performance tracker records query metadata
3. Documents are scored for relevance
   └─> Performance tracker updated with scores
4. Scoring completes
   └─> Statistics calculated from tracker
   └─> GUI display updated via TabManager
5. User views statistics in Search tab
```

### Code Changes

#### 1. `tab_manager.py` (3 new methods + UI component)

**New UI Component:**
```python
self.search_performance_stats = ft.Container(
    visible=False,
    border=ft.border.all(1, ft.Colors.BLUE_200),
    border_radius=8,
    padding=15,
    bgcolor=ft.Colors.BLUE_50
)
```

**New Methods:**
- `update_search_performance_stats(stats, score_threshold)` - Main update method
- `_create_metric_card(label, value, color)` - Creates summary metric cards
- `_create_query_performance_card(query_num, stat, threshold)` - Creates per-query cards

#### 2. `workflow_steps_handler.py` (2 modifications)

**Constructor Update:**
```python
def __init__(self, agents, config_overrides=None, tab_manager=None):
    # ... existing code ...
    self.tab_manager = tab_manager  # New parameter
```

**GUI Update Call (in `execute_document_scoring`):**
```python
if self.tab_manager:
    self.tab_manager.update_search_performance_stats(stats, score_threshold=threshold)
```

#### 3. `workflow.py` (1 modification)

**Constructor Update:**
```python
def __init__(self, agents, config_overrides=None, tab_manager=None):
    # ... existing code ...
    self.steps_handler = WorkflowStepsHandler(agents, self.config_overrides, tab_manager)
```

#### 4. `research_app.py` (1 modification)

**Manager Initialization Order Change:**
```python
def _initialize_managers(self):
    self.dialog_manager = DialogManager(self.page)
    self.tab_manager = TabManager(self.page)  # Create first
    self.workflow_executor = WorkflowExecutor(self.agents, self.config_overrides, self.tab_manager)  # Pass to executor
    self.event_handlers = EventHandlers(self)
    self.data_updaters = DataUpdaters(self)
```

### Usage

**Automatic Display:**
When multi-model query generation is enabled and a workflow runs:

1. User enters research question and starts workflow
2. Multiple queries are generated and executed
3. Documents are retrieved and scored
4. After scoring completes, performance statistics automatically appear in Search tab
5. Statistics show which models found which documents

**Manual Access:**
```python
# In workflow_steps_handler or similar
if self.tab_manager and stats:
    self.tab_manager.update_search_performance_stats(
        stats=statistics_list,
        score_threshold=3.0
    )
```

### Example Display

```
┌─────────────────────────────────────────────────────────────────────┐
│ 📊 Multi-Model Query Performance                                    │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  [2]        [97]         [27]         [23]         [2.7s]          │
│  Queries    Total Docs   High-Scoring Unique       Avg Time        │
│                                                                      │
│ Per-Query Results (threshold ≥3.0):                                │
│                                                                      │
│ ┌─────────────────────────────────────────────────────────────────┐ │
│ │ Query #1                    medgemma-27b-text-it    T=0.10     │ │
│ │ ─────────────────────────────────────────────────────────────── │ │
│ │   45      │    12     │    8      │     3        │   2.34s     │ │
│ │   Total   │    ≥3.0   │   Unique  │ Unique High  │   Time      │ │
│ │                                                                  │ │
│ │ Query: cardiovascular & exercise & (benefit | advantage)...     │ │
│ └─────────────────────────────────────────────────────────────────┘ │
│                                                                      │
│ ┌─────────────────────────────────────────────────────────────────┐ │
│ │ Query #2                    gpt-oss                  T=0.10     │ │
│ │ ─────────────────────────────────────────────────────────────── │ │
│ │   52      │    15     │    15     │     6        │   3.12s     │ │
│ │   Total   │    ≥3.0   │   Unique  │ Unique High  │   Time      │ │
│ │                                                                  │ │
│ │ Query: (cardio | heart) & (physical activity | exercise)...     │ │
│ └─────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

### Key Metrics Explained

**For Users:**

1. **Total Documents**: How many documents each query retrieved
   - *Useful for*: Understanding query breadth

2. **High-Scoring (≥threshold)**: Documents meeting relevance criteria
   - *Useful for*: Evaluating query quality

3. **Unique**: Documents found ONLY by this query
   - *Useful for*: Identifying which models provide unique coverage

4. **Unique High-Scoring**: High-scoring docs unique to this query
   - *Useful for*: Finding the most valuable unique contributions

5. **Execution Time**: How long the query took
   - *Useful for*: Balancing speed vs. thoroughness

### Benefits

**For Researchers:**
- Visual feedback on query performance
- Easy comparison between models
- Identification of most valuable model configurations
- Understanding of result overlap and diversity

**For System Optimization:**
- Data-driven model selection
- Performance tuning insights
- Quality vs. speed tradeoffs
- Coverage analysis

### Technical Notes

**Performance:**
- Minimal overhead: Statistics calculated once after scoring
- GUI update is non-blocking
- Scrollable content handles many queries gracefully

**Compatibility:**
- Only shown when multi-model is enabled
- Gracefully hidden if no statistics available
- Works with any number of models/queries
- Adapts to different screen sizes (responsive layout)

**Future Enhancements:**
- Click to expand/collapse query details
- Sort queries by different metrics
- Export statistics to CSV/JSON
- Historical comparison charts
- Model recommendation based on past performance

## Files Modified

1. `src/bmlibrarian/gui/tab_manager.py` (+197 lines)
   - Added `search_performance_stats` container
   - Added `update_search_performance_stats()` method
   - Added `_create_metric_card()` helper
   - Added `_create_query_performance_card()` helper

2. `src/bmlibrarian/gui/workflow_steps_handler.py` (+2 parameters, +3 lines)
   - Added `tab_manager` parameter to constructor
   - Added GUI update call after statistics calculation

3. `src/bmlibrarian/gui/workflow.py` (+1 parameter, +2 lines)
   - Added `tab_manager` parameter to constructor
   - Pass `tab_manager` to `WorkflowStepsHandler`

4. `src/bmlibrarian/gui/research_app.py` (+1 line)
   - Reordered manager initialization
   - Pass `tab_manager` to `WorkflowExecutor`

## Testing

```bash
# Test imports
uv run python -c "from src.bmlibrarian.gui.tab_manager import TabManager; print('✓')"

# Test GUI (with multi-model enabled)
uv run python bmlibrarian_research_gui.py
```

**Test Checklist:**
- [ ] Statistics appear after scoring completes
- [ ] Summary metrics display correctly
- [ ] Per-query cards show all metrics
- [ ] Colors and styling render properly
- [ ] Query text is selectable
- [ ] Statistics update when re-running workflow
- [ ] Hidden when multi-model is disabled

## Conclusion

The GUI performance tracking integration provides researchers with immediate, visual feedback on multi-model query performance. By displaying statistics directly in the Search tab, users can quickly understand which models are finding the most relevant documents and make informed decisions about their research strategy.

The implementation is clean, modular, and maintains the existing GUI architecture while adding valuable new functionality.
