# Query Performance Tracking - Quick Start Guide

## What is it?

Track which AI models find which documents, showing you which model configurations work best for your research questions.

## Quick Enable

**1. Enable multi-model in config:**

Edit `~/.bmlibrarian/config.json`:
```json
{
  "query_generation": {
    "multi_model_enabled": true,
    "models": ["medgemma-27b-text-it-Q8_0:latest", "gpt-oss:20b", "medgemma4B_it_q8:latest"],
    "queries_per_model": 1
  }
}
```

**2. Run GUI:**
```bash
uv run python bmlibrarian_research_gui.py
```

**3. View results:**
- Statistics appear in **Search tab** after document scoring
- Also printed to console

## What You'll See

### GUI (Search Tab)

**Top Summary:**
```
[2 Queries]  [97 Total Docs]  [27 High-Scoring]  [23 Unique]  [2.7s Avg Time]
```

**Per-Query Cards:**
```
Query #1 (medgemma-27b, T=0.10)
  45 Total  |  12 ≥3.0  |  8 Unique  |  3 Unique High  |  2.34s

Query #2 (gpt-oss, T=0.10)
  52 Total  |  15 ≥3.0  |  15 Unique  |  6 Unique High  |  3.12s
```

### Key Metrics Explained

- **Total**: Documents found by this query
- **≥3.0**: High-scoring documents (relevance ≥3.0)
- **Unique**: Documents ONLY found by this query (not others)
- **Unique High**: High-scoring docs unique to this query ⭐ **MOST IMPORTANT**
- **Time**: Query execution time

## What to Look For

### Best Performing Models

✅ **High "Unique High-Scoring" count** = Model finds relevant documents others miss

✅ **High "≥3.0" count** = Model finds many relevant documents overall

✅ **Low execution time** = Fast model

### Example Analysis

```
Query #1 (model-a): 3 unique high-scoring docs, 2.3s
Query #2 (model-b): 6 unique high-scoring docs, 3.1s  ⭐ Better!
```

**Conclusion**: Model-b finds more unique relevant documents. Consider using it more.

## Try the Demo

```bash
uv run python examples/query_performance_demo.py
```

## Documentation

- **User Guide**: `doc/users/query_performance_tracking.md`
- **Technical Details**: `QUERY_PERFORMANCE_TRACKING.md`
- **GUI Details**: `GUI_PERFORMANCE_TRACKING.md`
- **Complete Overview**: `PERFORMANCE_TRACKING_COMPLETE.md`

## Quick Tips

1. **Start with 2-3 models** - More isn't always better
2. **Focus on "Unique High-Scoring"** - Shows model value
3. **Try different temperatures** - Adjust `queries_per_model` to 2-3
4. **Track over time** - Note which models work for your domain
5. **Disable underperformers** - Remove models with few unique high-scoring docs

## Troubleshooting

**No statistics shown?**
- Check multi-model is enabled in config
- Verify documents were scored
- Look for statistics in console output

**All queries find same documents?**
- Try more diverse models
- Increase temperature for more variation
- Check queries are actually different

## Support

Questions? Check the documentation files or create an issue at the project repository.
