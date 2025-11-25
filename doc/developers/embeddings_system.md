# Embeddings System Architecture

This document describes the embedding system architecture in BMLibrarian, including backend selection, configuration management, and integration points.

## Overview

The embedding system provides text-to-vector conversion for semantic search and document chunking. It supports multiple backends to balance stability, performance, and deployment requirements.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      Application Layer                          │
│  (PDFIngestor, DocumentProcessor, SemanticSearch, etc.)        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                       ChunkEmbedder                             │
│  - Loads config from get_embeddings_config()                    │
│  - Routes to appropriate backend                                │
│  - Handles batching and error recovery                          │
└─────────────────────────────────────────────────────────────────┘
                              │
          ┌───────────────────┼───────────────────┐
          ▼                   ▼                   ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│ SentenceTransf. │ │  OllamaHTTP     │ │   LlamaCpp      │
│   Embedder      │ │   Embedder      │ │   Embedder      │
└─────────────────┘ └─────────────────┘ └─────────────────┘
          │                   │                   │
          ▼                   ▼                   ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│   HuggingFace   │ │  Ollama Server  │ │   GGUF Model    │
│     Models      │ │  (localhost)    │ │     File        │
└─────────────────┘ └─────────────────┘ └─────────────────┘
```

## Configuration System

### Config Location

Embeddings configuration is stored in the main BMLibrarian config system:

```python
# In config.py
DEFAULT_CONFIG = {
    # ... other config ...
    "embeddings": {
        "backend": "sentence_transformers",
        "model": "snowflake-arctic-embed2:latest",
        "huggingface_model": "Snowflake/snowflake-arctic-embed-l-v2.0",
        "batch_size": 32,
        "n_ctx": 8192,
        "device": "auto"
    }
}
```

### Accessing Configuration

```python
from bmlibrarian.config import get_embeddings_config

config = get_embeddings_config()
# Returns dict with backend, model, huggingface_model, etc.
```

### Valid Settings Category

The `embeddings` category is registered in `VALID_SETTINGS_CATEGORIES` for database-backed user settings support.

## ChunkEmbedder Class

### Initialization

The `ChunkEmbedder` class now loads defaults from config when parameters are `None`:

```python
def __init__(
    self,
    model_name: Optional[str] = None,    # Uses config if None
    model_id: Optional[int] = None,
    backend: Optional[EmbeddingBackend] = None,  # Uses config if None
    model_path: Optional[str] = None,
    n_ctx: Optional[int] = None,         # Uses config if None
) -> None:
```

### Backend Selection Logic

```python
# Load defaults from config
embeddings_config = get_embeddings_config()

if backend is None:
    backend = embeddings_config.get("backend", "ollama")

if model_name is None:
    if backend == "sentence_transformers":
        # Prefer HuggingFace model name for sentence_transformers
        model_name = embeddings_config.get(
            "huggingface_model",
            embeddings_config.get("model", DEFAULT_EMBEDDING_MODEL_NAME)
        )
    else:
        model_name = embeddings_config.get("model", DEFAULT_EMBEDDING_MODEL_NAME)
```

### Usage Examples

```python
# Use config defaults (recommended)
embedder = ChunkEmbedder()

# Override backend
embedder = ChunkEmbedder(backend="ollama")

# Override model
embedder = ChunkEmbedder(model_name="all-MiniLM-L6-v2")

# Full customization
embedder = ChunkEmbedder(
    backend="llama_cpp",
    model_path="/path/to/model.gguf",
    n_ctx=4096
)
```

## Backend Implementations

### SentenceTransformerEmbedder

Located in `bmlibrarian/embeddings/sentence_transformer_embedder.py`.

**Features**:
- Uses HuggingFace sentence-transformers library
- Automatic model download and caching
- Efficient batch processing
- Device selection (CPU, CUDA, MPS)

**Model Name Mapping**:

```python
OLLAMA_TO_HF_MODEL_MAP = {
    "snowflake-arctic-embed2:latest": "Snowflake/snowflake-arctic-embed-l-v2.0",
    "nomic-embed-text:latest": "nomic-ai/nomic-embed-text-v1.5",
    "all-minilm:latest": "sentence-transformers/all-MiniLM-L6-v2",
    # ... more mappings
}
```

### OllamaHTTPEmbedder

Located in `bmlibrarian/embeddings/ollama_http_embedder.py`.

**Features**:
- Raw HTTP requests to Ollama API
- More stable than Python library for some workloads
- Configurable retry logic

### LlamaCppEmbedder

Located in `bmlibrarian/embeddings/llama_cpp_embedder.py`.

**Features**:
- Direct GGUF model inference
- No external service dependency
- Automatic Ollama cache detection

## Integration Points

### PDFIngestor

```python
# In pdf_ingestor.py
@property
def embedder(self) -> ChunkEmbedder:
    """Lazy-load the chunk embedder."""
    if self._embedder is None:
        self._embedder = ChunkEmbedder()  # Uses config defaults
    return self._embedder
```

### DocumentProcessor

```python
# In document_processor.py
embedder = ChunkEmbedder()  # Uses config defaults
```

### Semantic Search

The embedding model configured here should match the model used for document embeddings to ensure vector compatibility.

## Error Handling

### Retry Logic

The Ollama backends include retry logic for transient failures:

```python
MAX_RETRY_ATTEMPTS = 5
RETRY_BASE_DELAY = 2.0  # Doubles each retry (exponential backoff)
```

### Backend Fallback

There is no automatic fallback between backends. If the configured backend fails, the error is propagated to the caller. Applications should handle embedding failures appropriately.

## Testing

### Unit Tests

```bash
uv run python -m pytest tests/test_chunk_embedder.py
```

### Manual Testing

```python
from bmlibrarian.embeddings.chunk_embedder import ChunkEmbedder
from bmlibrarian.config import get_embeddings_config

# Verify config
config = get_embeddings_config()
print(f"Backend: {config['backend']}")

# Test single embedding
embedder = ChunkEmbedder()
result = embedder.create_embedding("Test text")
assert result is not None
assert len(result) == 1024  # For snowflake-arctic-embed

# Test batch embedding
texts = ["First chunk", "Second chunk", "Third chunk"]
results = embedder.create_embeddings_batch(texts)
assert len(results) == 3
assert all(r is not None for r in results)
```

## Performance Considerations

### sentence_transformers

- **First load**: Model download may take several minutes
- **Subsequent loads**: Fast (cached locally)
- **Batch processing**: Very efficient, handles large batches well
- **Memory**: ~2GB for snowflake-arctic-embed-l-v2.0

### ollama

- **Stability**: Can fail with larger text chunks (EOF errors)
- **Batch processing**: Limited by Ollama server capacity
- **Memory**: Managed by Ollama server

### llama_cpp

- **Memory**: Loads entire model into RAM/VRAM
- **Batch processing**: Single-threaded, slower for large batches
- **Stability**: Very stable once loaded

## Future Improvements

1. **Automatic fallback**: Consider implementing backend fallback on failure
2. **Embedding cache**: Cache embeddings to avoid regeneration
3. **Dimension validation**: Verify embedding dimensions match database schema
4. **Model versioning**: Track which model generated each embedding

## Related Files

- `src/bmlibrarian/embeddings/chunk_embedder.py` - Main embedder class
- `src/bmlibrarian/embeddings/sentence_transformer_embedder.py` - ST backend
- `src/bmlibrarian/embeddings/ollama_http_embedder.py` - HTTP backend
- `src/bmlibrarian/embeddings/llama_cpp_embedder.py` - GGUF backend
- `src/bmlibrarian/config.py` - Configuration system
- `doc/users/embeddings_configuration_guide.md` - User guide
