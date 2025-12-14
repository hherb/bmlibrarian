# Phase 2: Embedding Provider Implementation

## Overview

The embedding provider uses FastEmbed to generate document embeddings locally using ONNX runtime. This enables CPU-optimized embedding generation without requiring external services or GPU hardware.

## Components

### 2.1 Embedding Module (`src/bmlibrarian/lite/embeddings.py`)

```python
"""Local embedding generation using FastEmbed (ONNX runtime)."""

import logging
from typing import List, Optional, Generator

from fastembed import TextEmbedding

from .constants import (
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_EMBEDDING_DIMENSIONS,
)

logger = logging.getLogger(__name__)


class LiteEmbedder:
    """
    Lightweight local embeddings using FastEmbed.

    Uses ONNX runtime for CPU-optimized inference. No GPU or external
    API required.

    Supported models:
    - BAAI/bge-small-en-v1.5 (384 dimensions, ~50MB) - default, fast
    - BAAI/bge-base-en-v1.5 (768 dimensions, ~130MB) - better quality
    - intfloat/multilingual-e5-small (384 dimensions) - multi-language
    """

    # Model specifications for validation
    MODEL_SPECS = {
        "BAAI/bge-small-en-v1.5": {"dimensions": 384, "size_mb": 50},
        "BAAI/bge-base-en-v1.5": {"dimensions": 768, "size_mb": 130},
        "intfloat/multilingual-e5-small": {"dimensions": 384, "size_mb": 50},
    }

    def __init__(
        self,
        model_name: str = DEFAULT_EMBEDDING_MODEL,
        cache_dir: Optional[str] = None,
    ) -> None:
        """
        Initialize the embedder.

        Args:
            model_name: FastEmbed model name
            cache_dir: Optional directory for model cache
        """
        self.model_name = model_name
        self._validate_model(model_name)

        logger.info(f"Loading embedding model: {model_name}")

        # Initialize FastEmbed with optional cache directory
        kwargs = {"model_name": model_name}
        if cache_dir:
            kwargs["cache_dir"] = cache_dir

        self._model = TextEmbedding(**kwargs)
        self._dimensions = self._get_dimensions(model_name)

        logger.info(f"Embedding model loaded: {model_name} ({self._dimensions}d)")

    @property
    def dimensions(self) -> int:
        """Return embedding dimensions."""
        return self._dimensions

    def _validate_model(self, model_name: str) -> None:
        """
        Validate that the model is supported.

        Args:
            model_name: Model name to validate

        Raises:
            ValueError: If model is not supported
        """
        # FastEmbed supports many models, we only validate our recommended ones
        if model_name in self.MODEL_SPECS:
            return

        # For other models, log a warning but don't fail
        logger.warning(
            f"Model {model_name} not in recommended list. "
            f"Recommended models: {list(self.MODEL_SPECS.keys())}"
        )

    def _get_dimensions(self, model_name: str) -> int:
        """
        Get embedding dimensions for a model.

        Args:
            model_name: Model name

        Returns:
            Number of dimensions
        """
        if model_name in self.MODEL_SPECS:
            return self.MODEL_SPECS[model_name]["dimensions"]

        # For unknown models, we need to generate a test embedding
        test_embedding = list(self._model.embed(["test"]))[0]
        return len(test_embedding)

    def embed(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple texts.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors
        """
        if not texts:
            return []

        # FastEmbed returns a generator, convert to list
        embeddings = list(self._model.embed(texts))

        logger.debug(f"Generated {len(embeddings)} embeddings")
        return [list(emb) for emb in embeddings]

    def embed_single(self, text: str) -> List[float]:
        """
        Generate embedding for a single text.

        Args:
            text: Text to embed

        Returns:
            Embedding vector
        """
        embeddings = self.embed([text])
        return embeddings[0] if embeddings else []

    def embed_generator(self, texts: List[str]) -> Generator[List[float], None, None]:
        """
        Generate embeddings as a generator (memory efficient).

        Args:
            texts: List of texts to embed

        Yields:
            Embedding vectors one at a time
        """
        for embedding in self._model.embed(texts):
            yield list(embedding)

    @classmethod
    def list_supported_models(cls) -> List[str]:
        """
        List supported/recommended models.

        Returns:
            List of model names
        """
        return list(cls.MODEL_SPECS.keys())

    @classmethod
    def get_model_info(cls, model_name: str) -> dict:
        """
        Get information about a model.

        Args:
            model_name: Model name

        Returns:
            Dictionary with model info (dimensions, size_mb)
        """
        return cls.MODEL_SPECS.get(model_name, {})
```

### 2.2 ChromaDB Integration (`src/bmlibrarian/lite/chroma_embeddings.py`)

```python
"""ChromaDB embedding function using FastEmbed."""

import logging
from typing import List, Optional

from chromadb import Documents, EmbeddingFunction, Embeddings

from .embeddings import LiteEmbedder
from .constants import DEFAULT_EMBEDDING_MODEL

logger = logging.getLogger(__name__)


class FastEmbedFunction(EmbeddingFunction):
    """
    ChromaDB embedding function using FastEmbed.

    This allows ChromaDB to automatically generate embeddings when
    documents are added or queried.
    """

    def __init__(
        self,
        model_name: str = DEFAULT_EMBEDDING_MODEL,
        cache_dir: Optional[str] = None,
    ) -> None:
        """
        Initialize the embedding function.

        Args:
            model_name: FastEmbed model name
            cache_dir: Optional directory for model cache
        """
        self._embedder = LiteEmbedder(model_name=model_name, cache_dir=cache_dir)

    def __call__(self, input: Documents) -> Embeddings:
        """
        Generate embeddings for documents.

        Args:
            input: List of document texts

        Returns:
            List of embedding vectors
        """
        return self._embedder.embed(input)

    @property
    def dimensions(self) -> int:
        """Return embedding dimensions."""
        return self._embedder.dimensions


def create_embedding_function(
    model_name: str = DEFAULT_EMBEDDING_MODEL,
    cache_dir: Optional[str] = None,
) -> FastEmbedFunction:
    """
    Create a ChromaDB embedding function.

    This is the recommended way to create an embedding function
    for use with LiteStorage.

    Args:
        model_name: FastEmbed model name
        cache_dir: Optional directory for model cache

    Returns:
        ChromaDB-compatible embedding function

    Example:
        >>> from bmlibrarian.lite.chroma_embeddings import create_embedding_function
        >>> from bmlibrarian.lite.storage import LiteStorage
        >>>
        >>> embed_fn = create_embedding_function()
        >>> storage = LiteStorage()
        >>> collection = storage.get_documents_collection(embed_fn)
    """
    return FastEmbedFunction(model_name=model_name, cache_dir=cache_dir)
```

### 2.3 Document Chunking (`src/bmlibrarian/lite/chunking.py`)

```python
"""Document chunking utilities for embedding and retrieval."""

import logging
import uuid
from typing import List, Optional

from .constants import DEFAULT_CHUNK_SIZE, DEFAULT_CHUNK_OVERLAP
from .data_models import DocumentChunk

logger = logging.getLogger(__name__)


def chunk_text(
    text: str,
    document_id: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> List[DocumentChunk]:
    """
    Split text into overlapping chunks for embedding.

    Uses a sliding window approach with overlap to preserve context
    across chunk boundaries.

    Args:
        text: Text to chunk
        document_id: Parent document ID
        chunk_size: Maximum characters per chunk
        chunk_overlap: Overlap between chunks in characters

    Returns:
        List of DocumentChunk objects
    """
    if not text:
        return []

    # Validate parameters
    if chunk_size <= 0:
        raise ValueError(f"chunk_size must be positive, got {chunk_size}")
    if chunk_overlap < 0:
        raise ValueError(f"chunk_overlap must be non-negative, got {chunk_overlap}")
    if chunk_overlap >= chunk_size:
        raise ValueError(
            f"chunk_overlap ({chunk_overlap}) must be less than chunk_size ({chunk_size})"
        )

    chunks = []
    start = 0
    chunk_index = 0

    while start < len(text):
        # Calculate end position
        end = min(start + chunk_size, len(text))

        # Try to break at a natural boundary (sentence/paragraph)
        if end < len(text):
            # Look for sentence boundary
            boundary = _find_boundary(text, start, end)
            if boundary > start:
                end = boundary

        # Extract chunk text
        chunk_text = text[start:end].strip()

        if chunk_text:  # Only add non-empty chunks
            chunk = DocumentChunk(
                id=f"{document_id}_chunk_{chunk_index}",
                document_id=document_id,
                text=chunk_text,
                chunk_index=chunk_index,
                start_char=start,
                end_char=end,
            )
            chunks.append(chunk)
            chunk_index += 1

        # Move start position with overlap
        start = end - chunk_overlap

        # Prevent infinite loop
        if start <= chunks[-1].start_char if chunks else 0:
            start = end

    logger.debug(
        f"Created {len(chunks)} chunks from document {document_id} "
        f"({len(text)} chars)"
    )

    return chunks


def _find_boundary(text: str, start: int, end: int) -> int:
    """
    Find a natural text boundary near the end position.

    Looks for paragraph breaks, then sentence ends, then word boundaries.

    Args:
        text: Full text
        start: Start position
        end: Target end position

    Returns:
        Best boundary position
    """
    # Define boundary markers in order of preference
    markers = [
        "\n\n",  # Paragraph break
        ".\n",   # Sentence + newline
        ". ",    # Sentence end
        "! ",    # Exclamation
        "? ",    # Question
        "\n",    # Line break
        " ",     # Word boundary
    ]

    # Search backwards from end for a boundary
    search_start = max(start, end - 200)  # Don't search too far back

    for marker in markers:
        pos = text.rfind(marker, search_start, end)
        if pos > start:
            return pos + len(marker)

    # No boundary found, use the original end
    return end


def chunk_document_for_interrogation(
    text: str,
    document_id: Optional[str] = None,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> List[DocumentChunk]:
    """
    Chunk a document for the interrogation workflow.

    Creates chunks suitable for embedding and retrieval during
    document Q&A sessions.

    Args:
        text: Document text to chunk
        document_id: Optional document ID (generated if not provided)
        chunk_size: Maximum characters per chunk
        chunk_overlap: Overlap between chunks

    Returns:
        List of DocumentChunk objects ready for embedding
    """
    if document_id is None:
        document_id = str(uuid.uuid4())

    return chunk_text(
        text=text,
        document_id=document_id,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
```

## Implementation Steps

### Step 1: Install dependencies

```bash
uv add fastembed
```

### Step 2: Implement embeddings.py

Create the LiteEmbedder class with FastEmbed integration.

### Step 3: Implement chroma_embeddings.py

Create the ChromaDB embedding function wrapper.

### Step 4: Implement chunking.py

Create the document chunking utilities.

### Step 5: Update __init__.py

```python
"""BMLibrarian Lite - Lightweight version without PostgreSQL dependency."""

from .config import LiteConfig
from .storage import LiteStorage
from .embeddings import LiteEmbedder
from .chroma_embeddings import create_embedding_function
from .chunking import chunk_text, chunk_document_for_interrogation

__all__ = [
    "LiteConfig",
    "LiteStorage",
    "LiteEmbedder",
    "create_embedding_function",
    "chunk_text",
    "chunk_document_for_interrogation",
]
```

### Step 6: Add tests

```python
# tests/lite/test_embeddings.py

import pytest
from bmlibrarian.lite.embeddings import LiteEmbedder


@pytest.fixture(scope="module")
def embedder():
    """Create embedder once for all tests (model loading is slow)."""
    return LiteEmbedder()


def test_embedder_initialization(embedder):
    """Test that embedder initializes correctly."""
    assert embedder.dimensions == 384
    assert embedder.model_name == "BAAI/bge-small-en-v1.5"


def test_embed_single(embedder):
    """Test single text embedding."""
    embedding = embedder.embed_single("This is a test sentence.")
    assert len(embedding) == 384
    assert all(isinstance(x, float) for x in embedding)


def test_embed_multiple(embedder):
    """Test multiple text embedding."""
    texts = [
        "First sentence about medicine.",
        "Second sentence about health.",
        "Third sentence about research.",
    ]
    embeddings = embedder.embed(texts)
    assert len(embeddings) == 3
    assert all(len(e) == 384 for e in embeddings)


def test_embed_empty_list(embedder):
    """Test embedding empty list."""
    embeddings = embedder.embed([])
    assert embeddings == []


def test_list_supported_models():
    """Test listing supported models."""
    models = LiteEmbedder.list_supported_models()
    assert "BAAI/bge-small-en-v1.5" in models
    assert "BAAI/bge-base-en-v1.5" in models
```

```python
# tests/lite/test_chunking.py

import pytest
from bmlibrarian.lite.chunking import chunk_text, chunk_document_for_interrogation


def test_chunk_text_basic():
    """Test basic text chunking."""
    text = "A" * 1000
    chunks = chunk_text(text, "doc-1", chunk_size=100, chunk_overlap=20)

    assert len(chunks) > 1
    assert all(len(c.text) <= 100 for c in chunks)
    assert chunks[0].document_id == "doc-1"


def test_chunk_text_overlap():
    """Test that chunks have proper overlap."""
    text = "Word " * 200  # 1000 chars
    chunks = chunk_text(text, "doc-1", chunk_size=200, chunk_overlap=50)

    # Check that consecutive chunks share content
    for i in range(len(chunks) - 1):
        chunk1_end = chunks[i].text[-50:]
        chunk2_start = chunks[i + 1].text[:50]
        # Some overlap should exist
        assert len(set(chunk1_end.split()) & set(chunk2_start.split())) > 0


def test_chunk_text_empty():
    """Test chunking empty text."""
    chunks = chunk_text("", "doc-1")
    assert chunks == []


def test_chunk_text_small():
    """Test chunking text smaller than chunk size."""
    text = "Small text."
    chunks = chunk_text(text, "doc-1", chunk_size=1000)
    assert len(chunks) == 1
    assert chunks[0].text == text


def test_chunk_invalid_parameters():
    """Test that invalid parameters raise errors."""
    with pytest.raises(ValueError):
        chunk_text("text", "doc-1", chunk_size=0)

    with pytest.raises(ValueError):
        chunk_text("text", "doc-1", chunk_overlap=-1)

    with pytest.raises(ValueError):
        chunk_text("text", "doc-1", chunk_size=100, chunk_overlap=100)
```

## Integration with Storage

```python
# Example usage showing embedding + storage integration

from bmlibrarian.lite.storage import LiteStorage
from bmlibrarian.lite.chroma_embeddings import create_embedding_function
from bmlibrarian.lite.chunking import chunk_document_for_interrogation
from bmlibrarian.lite.data_models import LiteDocument, DocumentSource

# Initialize
storage = LiteStorage()
embed_fn = create_embedding_function()

# Add a document with automatic embedding
doc = LiteDocument(
    id="pmid-12345",
    title="Example Study",
    abstract="This study investigates the effects of...",
    authors=["Smith J", "Jones A"],
    year=2024,
    source=DocumentSource.PUBMED,
)

storage.add_document(doc, embedding_function=embed_fn)

# Search by semantic similarity
results = storage.search_documents(
    query="effects of treatment on outcome",
    n_results=10,
    embedding_function=embed_fn,
)

# Chunk a document for interrogation
chunks = chunk_document_for_interrogation(
    text="Full document text here...",
    document_id="doc-uuid-123",
)

# Add chunks to storage
chunk_collection = storage.get_chunks_collection(embed_fn)
chunk_collection.add(
    ids=[c.id for c in chunks],
    documents=[c.text for c in chunks],
    metadatas=[{"document_id": c.document_id, "index": c.chunk_index} for c in chunks],
)
```

## Performance Considerations

1. **Model Loading**: Load the embedding model once and reuse
2. **Batch Processing**: Use `embed()` for multiple texts, not `embed_single()` in a loop
3. **Memory**: Use `embed_generator()` for very large datasets
4. **Caching**: ChromaDB caches embeddings, no need for external caching

## Golden Rules Checklist

- [x] No magic numbers - chunk sizes in constants.py
- [x] No hardcoded paths - cache_dir from config
- [x] Type hints on all parameters
- [x] Docstrings on all functions/classes
- [x] Error handling with logging
- [x] Input validation in chunk_text
