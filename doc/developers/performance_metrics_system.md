# Performance Metrics System

This document describes the performance metrics tracking system implemented in BMLibrarian's agent architecture.

## Overview

All agents inheriting from `BaseAgent` automatically track performance metrics for LLM operations, including:
- Token usage (prompt and completion tokens)
- Timing information (wall clock time, model inference time)
- Request statistics (request count, retry count)

## Architecture

### PerformanceMetrics Dataclass

Located in `src/bmlibrarian/agents/base.py:27-152`, the `PerformanceMetrics` dataclass stores cumulative metrics:

```python
@dataclass
class PerformanceMetrics:
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0
    total_requests: int = 0
    total_retries: int = 0
    total_wall_time_seconds: float = 0.0
    total_model_time_seconds: float = 0.0
    total_prompt_eval_seconds: float = 0.0
    start_time: Optional[float] = None
    end_time: Optional[float] = None
```

### Metric Sources

Metrics are extracted from Ollama API responses which include:

| Response Field | Description | Used For |
|----------------|-------------|----------|
| `prompt_eval_count` | Number of tokens in the prompt | `total_prompt_tokens` |
| `eval_count` | Number of tokens generated | `total_completion_tokens` |
| `eval_duration` | Model inference time (nanoseconds) | `total_model_time_seconds` |
| `prompt_eval_duration` | Prompt processing time (nanoseconds) | `total_prompt_eval_seconds` |

### Integration Points

Metrics are captured automatically in two BaseAgent methods:

1. **`_make_ollama_request()`** - Chat-based requests (lines 189-197)
2. **`_generate_from_prompt()`** - Simple generation requests (lines 341-349)

Both use the `add_request_metrics()` method to accumulate statistics.

## API Reference

### BaseAgent Methods

| Method | Description |
|--------|-------------|
| `get_performance_metrics()` | Returns a copy of current metrics (prevents external modification) |
| `reset_metrics()` | Clears all accumulated metrics to initial state |
| `start_metrics()` | Marks start time for elapsed time calculation |
| `stop_metrics()` | Marks end time for elapsed time calculation |
| `format_metrics_report(include_header=True)` | Generates human-readable report string |
| `get_metrics_dict()` | Returns metrics as dictionary with agent metadata |

### PerformanceMetrics Methods

| Method/Property | Description |
|-----------------|-------------|
| `add_request_metrics(...)` | Add metrics from a single LLM request |
| `mark_start()` / `mark_end()` | Mark timing boundaries |
| `reset()` | Reset all metrics to zero |
| `to_dict()` | Convert to dictionary for serialization |
| `elapsed_time_seconds` | Property: time between start and end |
| `tokens_per_second` | Property: completion tokens / model time |
| `average_tokens_per_request` | Property: total tokens / request count |

## Usage Patterns

### Basic Usage

```python
from bmlibrarian.agents import QueryAgent

agent = QueryAgent(model="gpt-oss:20b")

# Perform operations (metrics accumulate automatically)
results = agent.search_documents("cardiovascular disease")

# Get metrics
metrics = agent.get_performance_metrics()
print(f"Used {metrics.total_tokens} tokens in {metrics.total_requests} requests")
```

### Tracking a Specific Operation

```python
# Reset and start fresh tracking
agent.reset_metrics()
agent.start_metrics()

# Perform operation
results = agent.process_documents(documents)

# Stop timing
agent.stop_metrics()

# Display report
print(agent.format_metrics_report())
```

### Comparing Multiple Agents

```python
agents = [query_agent, scoring_agent, citation_agent]

for agent in agents:
    metrics = agent.get_metrics_dict()
    print(f"{metrics['agent_type']}: {metrics['total_tokens']} tokens")
```

### Logging Metrics

```python
import json
import logging

logger = logging.getLogger(__name__)

# After operation completes
metrics_dict = agent.get_metrics_dict()
logger.info("Agent metrics", extra={'structured_data': metrics_dict})

# Or serialize for storage
json.dumps(metrics_dict)
```

## Report Format

The `format_metrics_report()` method generates output like:

```
=== QueryAgent Performance Metrics ===
Requests:     5 (2 retries)
Tokens:       12,450 total (10,200 prompt + 2,250 completion)
Time:         15.32s elapsed (12.45s model time)
Speed:        180.7 tokens/sec
Avg/Request:  2,490 tokens
```

## Implementation Notes

### Nanosecond Conversion

Ollama returns timing in nanoseconds. The constant `NANOSECONDS_PER_SECOND = 1_000_000_000` is used for conversion:

```python
self.total_model_time_seconds += model_time_ns / NANOSECONDS_PER_SECOND
```

### Missing Response Fields

The implementation handles missing fields gracefully using `.get()` with defaults:

```python
prompt_tokens = response.get('prompt_eval_count', 0)
completion_tokens = response.get('eval_count', 0)
```

### Copy Semantics

`get_performance_metrics()` returns a copy of the internal metrics object to prevent external modification of agent state.

### Thread Safety

The current implementation is **not thread-safe**. If using agents across multiple threads, external synchronization is required.

## Testing

Comprehensive tests are located in `tests/test_performance_metrics.py`:

- `TestPerformanceMetrics` - 13 tests for the dataclass
- `TestBaseAgentMetrics` - 7 tests for BaseAgent methods
- `TestMetricsIntegration` - 4 tests for LLM call integration

Run tests with:
```bash
uv run python -m pytest tests/test_performance_metrics.py -v
```

## Future Enhancements

Potential improvements for future iterations:

1. **Persistent metrics storage** - Save metrics to database for historical analysis
2. **Per-operation tracking** - Track metrics per logical operation, not just per agent
3. **Cost estimation** - Calculate estimated costs based on token usage and model pricing
4. **Aggregated reports** - Combine metrics across multiple agents for workflow-level reporting
5. **Thread-safe implementation** - Add locking for multi-threaded use cases
