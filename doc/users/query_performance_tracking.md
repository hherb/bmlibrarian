# Query Performance Tracking Guide

## Overview

The Query Performance Tracking system helps you understand which AI models with which parameters are most effective at finding relevant documents for your research questions. This feature is especially useful when using multi-model query generation, as it allows you to identify the best-performing model/parameter combinations over time.

## How It Works

When multi-model query generation is enabled, the system:

1. **Tracks Query Execution**: Records which model generated which query, along with parameters (temperature, top_p, etc.)
2. **Links Documents to Queries**: Tracks which documents were found by each query
3. **Integrates Scoring Results**: After documents are scored for relevance, updates the tracking database with scores
4. **Calculates Statistics**: Computes detailed performance metrics for each query and model

## Key Metrics

For each query, the system tracks:

- **Total documents found**: How many documents this query retrieved
- **High-scoring documents**: Documents with relevance score ≥ threshold (default: 3.0)
- **Unique documents**: Documents found ONLY by this query (not by others)
- **Unique high-scoring**: High-scoring documents unique to this query
- **Execution time**: How long the query took to execute

## Using Performance Tracking

### Automatic Integration

Performance tracking is automatically enabled when you use multi-model query generation through:

- **Research GUI** (`bmlibrarian_research_gui.py`): Statistics displayed in console after document scoring
- **CLI** (`bmlibrarian_cli.py`): Statistics shown after the scoring step (future implementation)

### Manual Integration

You can manually use the performance tracker in your own code:

```python
from bmlibrarian.agents import QueryAgent
from bmlibrarian.agents.query_generation import QueryPerformanceTracker
import hashlib

# Create session ID
research_question = "Your research question here"
session_id = hashlib.md5(research_question.encode()).hexdigest()

# Initialize tracker
tracker = QueryPerformanceTracker()  # Uses in-memory database
tracker.start_session(session_id)

# Execute multi-query search with tracking
query_agent = QueryAgent()
documents = list(query_agent.find_abstracts_multi_query(
    question=research_question,
    max_rows=100,
    performance_tracker=tracker,
    session_id=session_id
))

# After scoring documents, update tracker with scores
document_scores = {doc['id']: score for doc, score in scored_documents}
tracker.update_document_scores(session_id, document_scores)

# Get statistics
stats = tracker.get_query_statistics(session_id, score_threshold=3.0)
formatted = QueryAgent.format_query_performance_stats(stats, score_threshold=3.0)
print(formatted)

# Get model summary
model_summary = tracker.get_model_performance_summary(session_id)
for model, metrics in model_summary.items():
    print(f"{model}: {metrics['avg_high_scoring']:.1f} avg high-scoring docs")
```

## Interpreting Results

### Example Output

```
================================================================================
QUERY PERFORMANCE STATISTICS
================================================================================
Score threshold: 3.0

Query #1 (medgemma-27b-text-it-Q8_0:latest, T=0.10):
  Total documents: 45
  High-scoring (>=3.0): 12
  Unique to this query: 8
  Unique high-scoring: 3
  Execution time: 2.34s
  Query: cardiovascular & exercise & (benefit | advantage)...

Query #2 (gpt-oss:20b, T=0.10):
  Total documents: 52
  High-scoring (>=3.0): 15
  Unique to this query: 15
  Unique high-scoring: 6
  Execution time: 3.12s
  Query: (cardio | heart) & (physical activity | exercise)...

================================================================================
SUMMARY
================================================================================
Total queries executed: 2
Total documents found (with duplicates): 97
Total high-scoring (with duplicates): 27
Total unique documents found: 23
Total unique high-scoring: 9
Average execution time: 2.73s
================================================================================
```

### What to Look For

1. **Unique High-Scoring Documents**: Models that find many unique high-scoring documents are discovering relevant literature that other models miss. These models are particularly valuable.

2. **Total High-Scoring**: Models with consistently high counts of high-scoring documents are generally performing well for your research domain.

3. **Execution Time**: Balance between speed and quality. Faster models that still find many relevant documents may be preferable for iterative research.

4. **Model Diversity**: If queries from different models find largely overlapping results, you may not need all models. If they find different documents, diversity is beneficial.

## Best Practices

### Over Time Analysis

To identify best-performing models over time:

1. Keep a log of performance statistics for each research session
2. Track which models consistently find unique high-scoring documents
3. Adjust your model configuration to emphasize top performers
4. Experiment with temperature values to optimize diversity vs. consistency

### Model Selection

Based on performance data:

- **High performers**: Models consistently finding many unique high-scoring documents
- **Fast performers**: Models with good results and low execution time
- **Diverse performers**: Models finding documents others miss, even if total count is lower

### Temperature Optimization

- Lower temperatures (0.1-0.3): More consistent, focused queries
- Higher temperatures (0.4-0.8): More diverse, exploratory queries
- Track which temperature ranges work best for your research domain

## Persistent Tracking

By default, the tracker uses an in-memory database that is reset each session. For long-term analysis, you can use a persistent database:

```python
# Use persistent database file
tracker = QueryPerformanceTracker(db_path="~/.bmlibrarian/query_performance.db")
```

This allows you to:
- Analyze performance trends across multiple research questions
- Compare model performance over time
- Build a dataset of effective query strategies
- Identify your most productive model configurations

## Example Script

See `examples/query_performance_demo.py` for a complete demonstration of the performance tracking system.

## Configuration

Performance tracking works with your existing multi-model configuration in `~/.bmlibrarian/config.json`:

```json
{
  "query_generation": {
    "multi_model_enabled": true,
    "models": [
      "medgemma-27b-text-it-Q8_0:latest",
      "gpt-oss:20b",
      "medgemma4B_it_q8:latest"
    ],
    "queries_per_model": 1,
    "execution_mode": "serial",
    "deduplicate_results": true,
    "show_all_queries_to_user": true,
    "allow_query_selection": true
  }
}
```

## Technical Details

- **Storage**: SQLite database (in-memory by default, optionally persistent)
- **Performance**: Minimal overhead, tracking adds ~0.1s per query
- **Memory**: In-memory mode uses negligible RAM (<1MB for typical sessions)
- **Privacy**: All data stored locally, no external services

## Troubleshooting

### No Statistics Displayed

- Ensure multi-model query generation is enabled
- Verify that documents were scored (statistics require score data)
- Check that performance_tracker and session_id were passed to `find_abstracts_multi_query()`

### Incomplete Statistics

- Statistics require both query execution and document scoring
- If scoring is interrupted, statistics will be based on documents scored so far
- In-memory database is reset when program exits; use persistent storage if needed

## Future Enhancements

Planned features:
- Historical performance dashboard
- Automated model selection based on past performance
- Query strategy recommendations
- Cross-session performance comparison
