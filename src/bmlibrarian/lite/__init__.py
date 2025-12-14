"""
BMLibrarian Lite - Lightweight version without PostgreSQL dependency.

A simplified version of BMLibrarian that uses:
- ChromaDB for vector storage (embedded)
- SQLite for metadata (embedded)
- FastEmbed for local embeddings (ONNX, CPU-optimized)
- Anthropic Claude for LLM inference (online)
- NCBI E-utilities for PubMed search (online)

Usage:
    from bmlibrarian.lite import LiteConfig, LiteStorage

    config = LiteConfig.load()
    storage = LiteStorage(config)

    # Add documents
    from bmlibrarian.lite.data_models import LiteDocument, DocumentSource

    doc = LiteDocument(
        id="pmid-12345",
        title="Example Study",
        abstract="This is the abstract...",
        source=DocumentSource.PUBMED,
    )
    storage.add_document(doc)
"""

from .config import LiteConfig
from .constants import (
    DEFAULT_DATA_DIR,
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_EMBEDDING_DIMENSIONS,
    DEFAULT_CHUNK_SIZE,
    DEFAULT_CHUNK_OVERLAP,
)
from .data_models import (
    DocumentSource,
    LiteDocument,
    DocumentChunk,
    SearchSession,
    ScoredDocument,
    Citation,
    ReviewCheckpoint,
    InterrogationSession,
)
from .storage import LiteStorage

__all__ = [
    # Configuration
    "LiteConfig",
    # Constants
    "DEFAULT_DATA_DIR",
    "DEFAULT_EMBEDDING_MODEL",
    "DEFAULT_EMBEDDING_DIMENSIONS",
    "DEFAULT_CHUNK_SIZE",
    "DEFAULT_CHUNK_OVERLAP",
    # Data models
    "DocumentSource",
    "LiteDocument",
    "DocumentChunk",
    "SearchSession",
    "ScoredDocument",
    "Citation",
    "ReviewCheckpoint",
    "InterrogationSession",
    # Storage
    "LiteStorage",
]
