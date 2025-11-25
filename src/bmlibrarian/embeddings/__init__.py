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
from .adaptive_chunker import adaptive_chunker
from .fast_sentence_chunker import fast_sentence_chunker

__all__ = [
    'DocumentEmbedder',
    'ChunkEmbedder',
    'ChunkPosition',
    'chunk_text',
    'DEFAULT_CHUNK_SIZE',
    'DEFAULT_CHUNK_OVERLAP',
    'adaptive_chunker',
    'fast_sentence_chunker',
]
