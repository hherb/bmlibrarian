# Multi-Strategy Search Guide

## Overview

PaperChecker uses a sophisticated multi-strategy search system to find counter-evidence in the literature database. By combining three different search approaches, it achieves better coverage than any single method alone.

## Search Strategies

### 1. Semantic Search

**What it does:** Finds documents that are conceptually similar to the counter-statement.

**How it works:**
- Converts the counter-statement into a numerical representation (embedding)
- Searches for documents with similar embeddings
- Captures conceptual relationships even when exact words differ

**Best for:** Finding documents that discuss the same topic using different terminology.

**Example:** Searching for "GLP-1 agonists are superior to metformin" would also find documents about "semaglutide outperforming first-line diabetes therapy."

### 2. HyDE Search (Hypothetical Document Embedding)

**What it does:** Generates hypothetical abstracts that would support the counter-claim, then searches for real documents similar to these hypotheticals.

**How it works:**
- Creates 2 fake abstracts that would support the counter-statement
- Converts each hypothetical abstract into an embedding
- Searches for real documents similar to these hypotheticals

**Best for:** Finding documents with similar structure and conclusions.

**Example:** A hypothetical abstract about "GLP-1 superiority in a meta-analysis" helps find actual meta-analyses with similar conclusions.

### 3. Keyword Search

**What it does:** Traditional full-text search using medical terminology.

**How it works:**
- Uses extracted keywords (drug names, conditions, study types)
- Searches document titles and abstracts
- Ranks by relevance using PostgreSQL text search

**Best for:** Finding documents that contain specific medical terms or drug names.

**Example:** Keywords like "semaglutide," "metformin," "HbA1c" will find documents mentioning these exact terms.

## How Results Are Combined

### Deduplication

When the same document is found by multiple strategies, it is only included once in the final results.

### Provenance Tracking

For each document, PaperChecker records which strategies found it:
- Documents found by all 3 strategies are typically most relevant
- Documents found by 2 strategies are likely relevant
- Documents found by 1 strategy may still be valuable

### Prioritization

When the total results exceed the limit, documents are prioritized:
1. Documents found by 3 strategies (most relevant)
2. Documents found by 2 strategies
3. Documents found by 1 strategy

## Configuration

### Default Settings

```json
{
  "paper_checker": {
    "search": {
      "semantic_limit": 50,
      "hyde_limit": 50,
      "keyword_limit": 50,
      "max_deduplicated": 100
    }
  }
}
```

### Configuration Options

| Setting | Default | Description |
|---------|---------|-------------|
| `semantic_limit` | 50 | Maximum documents from semantic search |
| `hyde_limit` | 50 | Maximum documents per HyDE abstract |
| `keyword_limit` | 50 | Maximum documents from keyword search |
| `max_deduplicated` | 100 | Maximum total unique documents |
| `embedding_model` | snowflake-arctic-embed2:latest | Model for embeddings |

### Adjusting for Performance

**Faster searches (fewer results):**
```json
{
  "paper_checker": {
    "search": {
      "semantic_limit": 20,
      "hyde_limit": 20,
      "keyword_limit": 20,
      "max_deduplicated": 40
    }
  }
}
```

**More comprehensive searches (slower):**
```json
{
  "paper_checker": {
    "search": {
      "semantic_limit": 100,
      "hyde_limit": 100,
      "keyword_limit": 100,
      "max_deduplicated": 200
    }
  }
}
```

## Understanding Search Results

### Search Statistics

After each search, you'll see statistics like:

```
Search found 85 unique documents:
  Semantic: 45
  HyDE: 52
  Keyword: 38
```

This shows:
- **Semantic: 45** - 45 documents found via semantic search
- **HyDE: 52** - 52 documents found via HyDE search
- **Keyword: 38** - 38 documents found via keyword search
- **85 unique** - After removing duplicates, 85 unique documents

### Provenance Information

Each document in the results includes provenance:

```json
{
  "doc_id": 12345,
  "found_by": ["semantic", "hyde", "keyword"]
}
```

Documents found by multiple strategies are typically the most relevant.

## Troubleshooting

### "All search strategies failed"

This error occurs when none of the search strategies return results.

**Possible causes:**
1. **Ollama not running:** Semantic and HyDE searches require Ollama for embeddings
2. **Database connection issues:** Keyword search requires database access
3. **No embeddings in database:** Semantic/HyDE require pre-computed embeddings

**Solutions:**
1. Ensure Ollama is running: `ollama serve`
2. Check database connection in config.json
3. Run embedding generation: `uv run python embed_documents_cli.py embed --source pubmed`

### Search returns no results

**Possible causes:**
1. Counter-statement is too specific
2. Keywords don't match database content
3. Database lacks relevant documents

**Solutions:**
1. Broaden the original statement being checked
2. Ensure the database contains relevant literature
3. Check if embeddings exist for documents

### Search is slow

**Possible causes:**
1. High search limits
2. Slow embedding generation
3. Database missing indexes

**Solutions:**
1. Reduce search limits in configuration
2. Use a faster embedding model
3. Ensure pgvector indexes are created

## Performance Tips

### For Development/Testing

Use lower limits for faster iteration:
```json
{
  "paper_checker": {
    "search": {
      "semantic_limit": 10,
      "hyde_limit": 10,
      "keyword_limit": 10,
      "max_deduplicated": 20
    }
  }
}
```

### For Production

Use balanced settings for comprehensive coverage:
```json
{
  "paper_checker": {
    "search": {
      "semantic_limit": 50,
      "hyde_limit": 50,
      "keyword_limit": 50,
      "max_deduplicated": 100
    }
  }
}
```

## Expected Timing

Typical search times:
- Semantic search: 2-5 seconds
- HyDE search (2 abstracts): 4-10 seconds
- Keyword search: <1 second
- **Total:** 6-16 seconds

Factors affecting timing:
- Embedding model speed
- Database size and indexing
- Network latency to Ollama

## Related Documentation

- [PaperChecker User Guide](paperchecker_guide.md)
- [Document Embedding Guide](document_embedding_guide.md)
- [Configuration Guide](../CLAUDE.md)
