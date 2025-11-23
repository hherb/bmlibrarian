# Semantic Chunking Guide

This guide explains how to use BMLibrarian's semantic chunking system for full-text document analysis.

## Overview

The semantic chunking system enables the Paper Weight Assessment Agent to analyze full research papers rather than just abstracts. It provides:

- **PDF ingestion**: Convert PDFs to text and store in the database
- **Text chunking**: Split large documents into overlapping chunks
- **Embedding generation**: Create vector embeddings for each chunk
- **Semantic search**: Find relevant passages within documents

## Quick Start

### 1. Apply the Database Migration

First, apply the semantic schema migration:

```bash
psql -h localhost -U your_user -d knowledgebase -f migrations/015_create_semantic_chunking_schema.sql
```

### 2. Ingest a PDF (GUI - Immediate)

For interactive use in the GUI, PDFs are processed immediately:

```python
from bmlibrarian.importers import PDFIngestor
from pathlib import Path

ingestor = PDFIngestor()
result = ingestor.ingest_pdf_immediate(
    document_id=12345,
    pdf_path=Path("/path/to/paper.pdf"),
    progress_callback=lambda stage, cur, tot: print(f"{stage}: {cur}/{tot}")
)

if result.success:
    print(f"Created {result.chunks_created} chunks")
    print(f"Extracted {result.char_count} characters from {result.page_count} pages")
```

### 3. Batch Processing (CLI - Background Worker)

For bulk processing, use the background worker:

```bash
# Show queue status
uv run python chunk_worker.py status

# Process queued documents
uv run python chunk_worker.py process --batch-size 100

# Continuous processing mode
uv run python chunk_worker.py process --continuous

# Queue a specific document
uv run python chunk_worker.py queue 12345 --priority 10
```

### 4. Assess Full Papers

Use the Paper Weight Agent's new `assess_full_paper` method:

```python
from bmlibrarian.agents import PaperWeightAssessmentAgent
from pathlib import Path

agent = PaperWeightAssessmentAgent()

# With PDF ingestion
result = agent.assess_full_paper(
    document_id=12345,
    pdf_path=Path("/path/to/paper.pdf"),
    force_reassess=True
)

# Without PDF (uses existing full_text and chunks)
result = agent.assess_full_paper(document_id=12345)

print(f"Final weight: {result.final_weight}/10")
```

## Configuration

### Chunk Parameters

Default chunking parameters can be customized:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `chunk_size` | 350 | Target chunk size in characters |
| `chunk_overlap` | 50 | Overlap between consecutive chunks |

```python
ingestor = PDFIngestor(
    chunk_size=500,
    chunk_overlap=75
)
```

### PDF Converter

The default PDF converter is PyMuPDF. To list available converters:

```python
from bmlibrarian.importers import list_converters
print(list_converters())  # ['pymupdf']
```

## How It Works

### Automatic Queue Trigger

When a document's `full_text` field is updated, a PostgreSQL trigger automatically queues it for chunking:

1. Document inserted/updated with `full_text`
2. Trigger adds document to `semantic.chunk_queue`
3. Background worker processes queue
4. Chunks and embeddings created in `semantic.chunks`

### Chunk Storage

Chunks are stored efficiently using position references:

```sql
-- Chunks table stores positions, not redundant text
SELECT
    chunk_no,
    start_pos,
    end_pos,
    -- Text extracted on-the-fly
    substr(d.full_text, c.start_pos + 1, c.end_pos - c.start_pos + 1) as chunk_text
FROM semantic.chunks c
JOIN document d ON c.document_id = d.id
WHERE c.document_id = 12345;
```

### Semantic Search

Search within document chunks:

```sql
SELECT * FROM semantic.chunksearch(
    'randomized controlled trial methodology',
    0.7,  -- threshold
    20    -- limit
);
```

## CLI Reference

### chunk_worker.py

```
Usage: chunk_worker.py [OPTIONS] COMMAND [ARGS]...

Commands:
  process       Process documents from the chunk queue
  status        Show chunk queue status and statistics
  queue         Add a document to the chunk queue
  clear-failed  Clear or reset failed items from queue

Options:
  -v, --verbose  Enable verbose logging

Examples:
  # Process with custom chunk parameters
  uv run python chunk_worker.py process --chunk-size 500 --overlap 75

  # High-priority queue
  uv run python chunk_worker.py queue 12345 --priority 10

  # Reset failed items for retry
  uv run python chunk_worker.py clear-failed --reset
```

## Troubleshooting

### PDF Conversion Issues

If PDF conversion fails:

1. Check the PDF is not corrupted
2. Verify PyMuPDF is installed: `pip install pymupdf`
3. Check conversion result warnings:

```python
result = ingestor.ingest_pdf(document_id=123, pdf_path=path)
for warning in result.warnings:
    print(warning)
```

### Queue Processing Failures

Check failed items in the queue:

```bash
uv run python chunk_worker.py status
```

Reset failed items for retry:

```bash
uv run python chunk_worker.py clear-failed --reset
```

### Missing Chunks

If a document has `full_text` but no chunks:

```bash
# Queue for processing
uv run python chunk_worker.py queue <document_id>

# Process immediately
uv run python chunk_worker.py process --batch-size 1
```

## Performance Considerations

- **Chunk size**: Larger chunks (500-1000 chars) reduce database storage but may lose precision in semantic search
- **Overlap**: Higher overlap (75-100 chars) improves semantic continuity but increases storage
- **Batch processing**: Process large backlogs during off-peak hours
- **Embedding model**: The default `snowflake-arctic-embed2:latest` produces 1024-dimension embeddings
