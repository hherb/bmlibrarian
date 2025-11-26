# Map-Reduce Synthesis for Large Citation Sets

## Overview

When BMLibrarian processes research questions that return many relevant documents (typically 15+ citations), the ReportingAgent automatically uses a **map-reduce synthesis pattern** to prevent context window overflow and ensure reliable report generation.

This feature is transparent to users - it activates automatically when needed and produces the same high-quality medical reports as the standard synthesis method.

## When Map-Reduce is Used

The ReportingAgent automatically switches to map-reduce synthesis when:

1. **Citation count exceeds threshold**: By default, when more than 15 citations are being synthesized
2. **Estimated token count is too high**: When the combined size of citations would overflow the model's context window (default: 6000 tokens)

You'll see log messages like:
```
Map-reduce triggered: 25 citations (threshold: 15)
```
or
```
Map-reduce triggered: estimated 8500 tokens (limit: 6000)
```

## How It Works

### 1. MAP Phase
Citations are split into batches (default: 8 citations per batch). Each batch is analyzed independently to extract:
- **Key themes and findings**
- **Supporting reference numbers**
- **Contradictory or nuanced findings**
- **Evidence strength assessment**

### 2. REDUCE Phase
All extracted themes from the MAP phase are synthesized into a single, coherent medical report with:
- Introduction answering the research question
- Evidence and discussion section
- Conclusion summarizing key findings

## Configuration

Map-reduce settings can be configured in `~/.bmlibrarian/config.json` under the `agents.reporting` section:

```json
{
  "agents": {
    "reporting": {
      "temperature": 0.1,
      "top_p": 0.9,
      "max_tokens": 3000,
      "map_reduce_citation_threshold": 15,
      "map_batch_size": 8,
      "effective_context_limit": 6000,
      "map_passage_max_length": 500
    }
  }
}
```

### Configuration Options

| Setting | Default | Description |
|---------|---------|-------------|
| `map_reduce_citation_threshold` | 15 | Use map-reduce when citations exceed this count |
| `map_batch_size` | 8 | Number of citations processed per batch in MAP phase |
| `effective_context_limit` | 6000 | Estimated token limit that triggers map-reduce |
| `map_passage_max_length` | 500 | Maximum characters per passage in MAP phase |

### Tuning Recommendations

- **Increase `map_reduce_citation_threshold`** if you have a model with a larger context window
- **Decrease `map_batch_size`** if you're experiencing empty responses during MAP phase
- **Decrease `effective_context_limit`** for smaller models (e.g., 7B parameters)
- **Increase `map_passage_max_length`** if you need more passage detail (at cost of smaller batches)

## Benefits

1. **Reliability**: Prevents context window overflow that causes empty model responses
2. **Scalability**: Can process hundreds of citations without memory issues
3. **Quality**: Extracts themes systematically, often improving report coherence
4. **Transparency**: Preserves all reference numbers for accurate citations

## Troubleshooting

### Empty responses during report generation
If you see "Empty response from model" errors:
1. Decrease `map_batch_size` (try 5 or 6)
2. Decrease `effective_context_limit` (try 4000)
3. Decrease `map_passage_max_length` (try 300)

### Report seems to miss some citations
1. Increase `map_batch_size` to reduce the number of batches
2. Check logs to ensure all batches completed successfully

### Map-reduce activates too often
1. Increase `map_reduce_citation_threshold` (try 20 or 25)
2. Increase `effective_context_limit` if your model supports larger context

## See Also

- [Reporting Agent Guide](reporting_guide.md) - Complete reporting system documentation
- [Configuration Guide](../SETUP_GUIDE.md) - General configuration instructions
