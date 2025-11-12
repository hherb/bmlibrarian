## Document Embedding Guide

## Overview

The Document Embedder creates vector embeddings for documents in your BMLibrarian knowledge base. These embeddings enable semantic search capabilities, allowing you to find documents based on meaning rather than just keywords.

## Features

- **Automatic Processing**: Finds and embeds documents without existing embeddings
- **Multiple Models**: Support for any Ollama embedding model
- **Source Filtering**: Embed specific document sources (medRxiv, PubMed, etc.)
- **Progress Tracking**: Visual progress bars and detailed statistics
- **Batch Processing**: Efficient batch processing for large datasets
- **Database Integration**: Seamless integration with bmlibrarian's chunk and embedding tables

## Installation Requirements

The document embedder requires:

```bash
# Core dependency
uv pip install ollama

# Optional: Progress bars
uv pip install tqdm
```

## Quick Start

### Basic Embedding

Embed 100 documents from medRxiv:

```bash
uv run python embed_documents_cli.py embed --source medrxiv --limit 100
```

### Check Status

View embedding statistics:

```bash
uv run python embed_documents_cli.py status
```

### Count Unembedded Documents

Count documents that need embeddings:

```bash
uv run python embed_documents_cli.py count --source medrxiv
```

## Command Reference

### `embed` - Generate Embeddings

Generate embeddings for documents without existing embeddings.

**Usage:**
```bash
uv run python embed_documents_cli.py embed [OPTIONS]
```

**Options:**
- `--source NAME`: Filter by source name (e.g., medrxiv, pubmed)
- `--limit N`: Maximum number of documents to embed
- `--batch-size N`: Documents per batch (default: 100)
- `--model NAME`: Ollama model to use (default: snowflake-arctic-embed2:latest)
- `-v, --verbose`: Enable verbose logging

**Examples:**

1. **Embed medRxiv abstracts:**
   ```bash
   uv run python embed_documents_cli.py embed --source medrxiv --limit 100
   ```

2. **Embed all documents:**
   ```bash
   uv run python embed_documents_cli.py embed
   ```

3. **Use a different model:**
   ```bash
   uv run python embed_documents_cli.py embed --model nomic-embed-text:latest --limit 50
   ```

4. **Large batch processing:**
   ```bash
   uv run python embed_documents_cli.py embed --source medrxiv --batch-size 500
   ```

### `count` - Count Unembedded Documents

Count how many documents don't have embeddings yet.

**Usage:**
```bash
uv run python embed_documents_cli.py count [OPTIONS]
```

**Options:**
- `--source NAME`: Filter by source name
- `--model NAME`: Check for specific model's embeddings

**Examples:**

1. **Count all unembedded documents:**
   ```bash
   uv run python embed_documents_cli.py count
   ```

2. **Count by source:**
   ```bash
   uv run python embed_documents_cli.py count --source medrxiv
   ```

### `status` - Show Embedding Statistics

Display detailed statistics about embeddings in the database.

**Usage:**
```bash
uv run python embed_documents_cli.py status [OPTIONS]
```

**Options:**
- `--model NAME`: Check status for specific model

**Output includes:**
- Model information (name, ID, dimension)
- Total documents with abstracts
- Documents with/without embeddings
- Breakdown by source
- Percentage embedded per source

## Configuration

### Model Selection

BMLibrarian supports any Ollama embedding model. Common choices:

| Model | Dimension | Speed | Quality | Use Case |
|-------|-----------|-------|---------|----------|
| `snowflake-arctic-embed2:latest` | 1024 | Medium | Excellent | Recommended default |
| `nomic-embed-text:latest` | 768 | Fast | Good | Quick embeddings |
| `mxbai-embed-large:latest` | 1024 | Slow | Excellent | Highest quality |

To use a different model:

```bash
uv run python embed_documents_cli.py embed --model nomic-embed-text:latest
```

### Ollama Configuration

The embedder connects to Ollama at `http://localhost:11434` by default. Ensure Ollama is running:

```bash
# Check Ollama status
ollama list

# Pull a model if needed
ollama pull snowflake-arctic-embed2:latest
```

## Programmatic Usage

You can use the embedder directly in Python code:

```python
from bmlibrarian.embeddings import DocumentEmbedder

# Initialize embedder
embedder = DocumentEmbedder(model_name="snowflake-arctic-embed2:latest")

# Embed documents
stats = embedder.embed_documents(
    source_name='medrxiv',
    limit=100,
    batch_size=50
)

print(f"Embedded {stats['embedded_count']} documents")
print(f"Failed: {stats['failed_count']}")

# Count unembedded documents
count = embedder.count_documents_without_embeddings(source_name='medrxiv')
print(f"Remaining: {count} documents")
```

## Workflow Recommendations

### Initial Setup

1. **Start with a small batch** to test:
   ```bash
   uv run python embed_documents_cli.py embed --source medrxiv --limit 10
   ```

2. **Check status**:
   ```bash
   uv run python embed_documents_cli.py status
   ```

3. **Scale up gradually**:
   ```bash
   uv run python embed_documents_cli.py embed --source medrxiv --limit 1000
   ```

### Production Workflow

1. **Import documents** (e.g., from medRxiv):
   ```bash
   uv run python medrxiv_import_cli.py update --days-to-fetch 7
   ```

2. **Embed new documents**:
   ```bash
   uv run python embed_documents_cli.py embed --source medrxiv
   ```

3. **Monitor progress**:
   ```bash
   uv run python embed_documents_cli.py status
   ```

### Daily Maintenance

Set up automated embedding generation:

```bash
#!/bin/bash
# daily_embedding.sh

# Embed new medRxiv papers
uv run python embed_documents_cli.py embed --source medrxiv --limit 500

# Check status
uv run python embed_documents_cli.py status
```

Schedule with cron:
```cron
# Run daily at 4 AM
0 4 * * * cd /path/to/bmlibrarian && ./daily_embedding.sh
```

## Performance Considerations

### Embedding Speed

Typical performance on a modern CPU:

| Model | Embeddings/sec | Time for 1000 docs |
|-------|----------------|-------------------|
| snowflake-arctic-embed2 | 5-10 | 2-3 minutes |
| nomic-embed-text | 10-20 | 1-2 minutes |
| mxbai-embed-large | 2-5 | 3-5 minutes |

**Factors affecting speed:**
- CPU performance
- Model size
- Abstract length
- Ollama configuration

### Database Performance

The embedder:
- Uses connection pooling for efficiency
- Batch commits every 100 documents
- Checks for existing embeddings to avoid duplicates
- Creates indexes automatically via schema

### Memory Usage

- **Small models** (768-dim): ~2GB RAM
- **Large models** (1024-dim): ~4GB RAM
- **Batch processing**: Minimal memory overhead

## Database Schema

### Tables Involved

**`chunks`** - Text chunks:
```sql
CREATE TABLE chunks (
    id INT PRIMARY KEY,
    document_id INT REFERENCES document(id),
    chunking_strategy_id INT,
    chunktype_id INT,
    document_title TEXT,
    text TEXT,
    chunklength INT,
    chunk_no INT
);
```

**`embedding_base`** - Base embedding info:
```sql
CREATE TABLE embedding_base (
    id INT PRIMARY KEY,
    chunk_id INT REFERENCES chunks(id),
    model_id INT REFERENCES embedding_models(id)
);
```

**`emb_768` / `emb_1024`** - Actual vectors:
```sql
CREATE TABLE emb_768 (
    embedding vector(768)
) INHERITS (embedding_base);

CREATE TABLE emb_1024 (
    embedding vector(1024)
) INHERITS (embedding_base);
```

### For Abstracts

The embedder creates:
- One chunk per document (chunk_no=0)
- Chunk text = document abstract
- Embedding stored in emb_768 or emb_1024 based on model

## Troubleshooting

### "ollama not installed"

**Problem:** Ollama Python package not found.

**Solution:**
```bash
uv pip install ollama
```

### "Model not found in Ollama"

**Problem:** Specified model not available.

**Solution:**
```bash
# Pull the model
ollama pull snowflake-arctic-embed2:latest

# Or use a different model
uv run python embed_documents_cli.py embed --model nomic-embed-text:latest
```

### "Connection refused to Ollama"

**Problem:** Ollama server not running.

**Solution:**
```bash
# Start Ollama (varies by OS)
ollama serve

# Or check if it's running
curl http://localhost:11434/api/tags
```

### Slow Embedding Generation

**Problem:** Embeddings taking too long.

**Solutions:**
1. Use a faster model: `--model nomic-embed-text:latest`
2. Reduce batch size: `--batch-size 50`
3. Check Ollama configuration
4. Consider GPU acceleration for Ollama

### "Unsupported embedding dimension"

**Problem:** Model produces dimension other than 768 or 1024.

**Solution:** BMLibrarian currently supports 768 and 1024 dimensions. Use a supported model:
- 768-dim: nomic-embed-text, gte-base
- 1024-dim: snowflake-arctic-embed2, mxbai-embed-large

## Integration with Research Workflows

### Semantic Search

Once documents are embedded, use semantic search in queries:

```python
from bmlibrarian.database import search_with_semantic

# Semantic search uses embeddings automatically
results = search_with_semantic(
    search_text="cardiovascular benefits of exercise",
    threshold=0.7,
    max_results=50
)

for doc in results:
    print(f"{doc['title']} - Similarity: {doc['semantic_score']:.3f}")
```

### Hybrid Search

Combine keyword and semantic search:

```python
from bmlibrarian.database import search_hybrid

documents, metadata = search_hybrid(
    search_text="cardiovascular benefits of exercise",
    query_text="cardiovascular & exercise",
    search_config={
        'semantic': {'enabled': True, 'similarity_threshold': 0.7},
        'bm25': {'enabled': True},
        'keyword': {'enabled': True}
    }
)
```

## Future Enhancements

Planned features:
- **Full-text chunking**: Embed document full text in addition to abstracts
- **Chunk overlap**: Sliding window chunking for better coverage
- **Multiple embedding models**: Use different models for different purposes
- **Incremental updates**: Re-embed when documents are updated
- **Quality metrics**: Track embedding quality and coverage

## See Also

- [MedRxiv Import Guide](medrxiv_import_guide.md) - Import documents to embed
- [Query Agent Guide](query_agent_guide.md) - Use embeddings in queries
- [Multi-Model Query Guide](multi_model_query_guide.md) - Advanced search with embeddings
