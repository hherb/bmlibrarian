"""
Embeddings module for BMLibrarian

Provides functionality for generating and managing document embeddings.
"""

from .document_embedder import DocumentEmbedder
from .chunk_embedder import (
    ChunkEmbedder,
    ChunkPosition,
    chunk_text,
    DEFAULT_CHUNK_SIZE,
    DEFAULT_CHUNK_OVERLAP,
)

__all__ = [
    'DocumentEmbedder',
    'ChunkEmbedder',
    'ChunkPosition',
    'chunk_text',
    'DEFAULT_CHUNK_SIZE',
    'DEFAULT_CHUNK_OVERLAP',
]
