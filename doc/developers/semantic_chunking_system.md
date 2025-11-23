# Semantic Chunking System - Developer Documentation

This document describes the architecture and implementation of the semantic chunking system for full-text document analysis.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         PDF Ingestion Flow                          │
└─────────────────────────────────────────────────────────────────────┘

    PDF File                    Database                    Ollama
       │                           │                           │
       ▼                           │                           │
┌──────────────┐                   │                           │
│ PDFConverter │                   │                           │
│  (PyMuPDF)   │                   │                           │
└──────┬───────┘                   │                           │
       │ plaintext                 │                           │
       ▼                           ▼                           │
┌──────────────┐           ┌──────────────┐                    │
│ PDFIngestor  │──────────▶│document.     │                    │
│              │           │full_text     │                    │
└──────┬───────┘           └──────┬───────┘                    │
       │                          │                            │
       │                          │ TRIGGER                    │
       │                          ▼                            │
       │                   ┌──────────────┐                    │
       │                   │semantic.     │                    │
       │                   │chunk_queue   │                    │
       │                   └──────┬───────┘                    │
       │                          │                            │
       ▼                          ▼                            │
┌──────────────────────────────────────────┐                   │
│            ChunkEmbedder                 │                   │
│  ┌────────────────┐ ┌─────────────────┐  │                   │
│  │  chunk_text()  │ │create_embedding()│──┼───────────────────▶
│  │  pure function │ │  ollama API     │  │                   │
│  └────────┬───────┘ └─────────┬───────┘  │                   │
│           │                   │          │                   │
│           └─────────┬─────────┘          │                   │
└─────────────────────┼────────────────────┘                   │
                      │
                      ▼
               ┌──────────────┐
               │semantic.     │
               │chunks        │
               │(positions +  │
               │ embeddings)  │
               └──────────────┘
```

## Module Structure

```
src/bmlibrarian/
├── importers/
│   ├── pdf_converter.py      # PDF → text abstraction
│   └── pdf_ingestor.py       # Full ingestion workflow
├── embeddings/
│   ├── chunk_embedder.py     # Chunking and embedding
│   └── document_embedder.py  # Legacy abstract embeddings
└── agents/
    └── paper_weight_agent.py # assess_full_paper() method

migrations/
└── 015_create_semantic_chunking_schema.sql

chunk_worker.py               # Background processing CLI
```

## Key Components

### 1. PDF Converter (`pdf_converter.py`)

Abstract interface for PDF conversion with pluggable implementations.

```python
class PDFConverter(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def version(self) -> str: ...

    @abstractmethod
    def convert(self, pdf_path: Path) -> ConversionResult: ...

class PyMuPDFConverter(PDFConverter):
    """Default implementation using PyMuPDF (fitz)."""
    pass
```

**Design Decisions:**

- **Factory pattern**: `get_converter(name)` returns appropriate implementation
- **ConversionResult dataclass**: Stable interface regardless of converter
- **Completeness validation**: `is_complete` property checks all pages converted
- **Easy extensibility**: Add new converters to `_CONVERTER_REGISTRY`

### 2. Chunk Embedder (`chunk_embedder.py`)

Pure functions for chunking + class for embedding integration.

```python
# Pure function - no side effects, easy to test
def chunk_text(text: str, chunk_size: int, overlap: int) -> List[ChunkPosition]:
    """Returns positions only, no text storage."""
    pass

class ChunkEmbedder:
    """Coordinates chunking, embedding, and database storage."""

    def chunk_and_embed(self, document_id: int, ...) -> int:
        """Main entry point - returns chunks created."""
        pass

    def process_queue(self, batch_size: int, ...) -> Tuple[int, int]:
        """Process background queue - returns (processed, failed)."""
        pass
```

**Design Decisions:**

- **Position-based storage**: `ChunkPosition` stores `start_pos`/`end_pos`, not text
- **On-the-fly extraction**: Text extracted via `substr()` from `document.full_text`
- **Progress callbacks**: Support GUI progress updates
- **Queue integration**: Both immediate and async processing paths

### 3. PDF Ingestor (`pdf_ingestor.py`)

Orchestrates the complete ingestion workflow.

```python
class PDFIngestor:
    def ingest_pdf(self, document_id, pdf_path, ...) -> IngestResult:
        """Basic ingestion - stores PDF, extracts text, updates DB."""
        pass

    def ingest_pdf_immediate(self, document_id, pdf_path, ...) -> IngestResult:
        """Immediate processing - includes embedding generation."""
        pass

    def ingest_from_text(self, document_id, text, ...) -> IngestResult:
        """Direct text ingestion (no PDF)."""
        pass
```

**Design Decisions:**

- **Two paths**: `ingest_pdf()` for queue-based, `ingest_pdf_immediate()` for GUI
- **Storage conventions**: Uses year-based directory structure
- **Composable**: Uses `PDFConverter` and `ChunkEmbedder` internally

### 4. Database Schema (`semantic` schema)

```sql
-- Main chunks table
CREATE TABLE semantic.chunks (
    id SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES public.document(id),
    model_id INTEGER NOT NULL REFERENCES public.embedding_models(id),
    chunk_size INTEGER NOT NULL,
    chunk_overlap INTEGER NOT NULL,
    chunk_no INTEGER NOT NULL,
    start_pos INTEGER NOT NULL,
    end_pos INTEGER NOT NULL,
    embedding vector(1024) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(document_id, model_id, chunk_size, chunk_overlap, chunk_no)
);

-- Background processing queue
CREATE TABLE semantic.chunk_queue (
    document_id INTEGER PRIMARY KEY REFERENCES public.document(id),
    queued_at TIMESTAMP NOT NULL DEFAULT NOW(),
    priority INTEGER NOT NULL DEFAULT 0,
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    last_attempt_at TIMESTAMP
);

-- Trigger for automatic queuing
CREATE TRIGGER trg_queue_chunking
AFTER INSERT OR UPDATE OF full_text ON public.document
FOR EACH ROW EXECUTE FUNCTION semantic.queue_for_chunking();
```

**Design Decisions:**

- **No redundant text storage**: With 40M+ documents, storing text in chunks would be wasteful
- **Position references**: `start_pos`/`end_pos` reference `document.full_text`
- **Async queue pattern**: Trigger queues, background worker processes
- **HNSW index**: Fast approximate nearest neighbor search

## Integration Points

### Paper Weight Agent

```python
class PaperWeightAssessmentAgent:
    def assess_full_paper(
        self,
        document_id: int,
        pdf_path: Optional[Path] = None,
        force_reassess: bool = False,
        progress_callback: Optional[Callable] = None,
    ) -> PaperWeightResult:
        """
        1. Check if PDF ingestion needed
        2. Search document chunks
        3. Combine chunks for analysis
        4. Call standard assess_paper()
        """
        pass
```

### GUI Integration

```python
# In paper_weight_lab.py or research GUI
async def on_pdf_uploaded(pdf_path: Path, document_id: int):
    ingestor = PDFIngestor()
    result = ingestor.ingest_pdf_immediate(
        document_id=document_id,
        pdf_path=pdf_path,
        progress_callback=update_progress_bar
    )

    if result.success:
        agent = PaperWeightAssessmentAgent()
        assessment = agent.assess_full_paper(document_id)
```

## Testing

### Unit Tests

```bash
# Test chunk_text pure function
uv run pytest tests/test_chunk_embedder.py -v

# Test PDF converter
uv run pytest tests/test_pdf_converter.py -v
```

### Integration Tests

```python
def test_full_ingestion_workflow(db_connection, sample_pdf):
    """Test complete PDF → chunks → search workflow."""
    ingestor = PDFIngestor()
    result = ingestor.ingest_pdf_immediate(
        document_id=test_doc_id,
        pdf_path=sample_pdf
    )

    assert result.success
    assert result.chunks_created > 0

    # Verify semantic search works
    chunks = search_document_chunks(test_doc_id)
    assert len(chunks) > 0
```

## Performance Considerations

### Embedding Generation

- ~0.5-2 seconds per chunk via Ollama
- Batch processing recommended for bulk imports
- GUI uses immediate path with progress feedback

### Storage Efficiency

| Approach | Storage per 1000 chunks |
|----------|------------------------|
| Redundant text | ~350KB text + ~4MB vectors |
| Position-based | ~24 bytes positions + ~4MB vectors |

### Query Performance

- HNSW index provides O(log n) similarity search
- On-the-fly text extraction adds ~1ms per chunk
- Consider caching frequently accessed chunks

## Future Enhancements

1. **Additional converters**: Enable pymupdf4llm when stable
2. **Chunk caching**: Redis cache for hot chunks
3. **Smart chunking**: Section-aware chunking using PDF structure
4. **Multi-model embeddings**: Support different embedding dimensions
