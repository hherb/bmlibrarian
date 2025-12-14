"""
ChromaDB embedding function using FastEmbed.

This module provides a ChromaDB-compatible embedding function that
uses FastEmbed for local embedding generation. This allows ChromaDB
to automatically generate embeddings when documents are added or queried.

Usage:
    from bmlibrarian.lite.chroma_embeddings import create_embedding_function
    from bmlibrarian.lite.storage import LiteStorage

    embed_fn = create_embedding_function()
    storage = LiteStorage()

    # Use with document collection
    collection = storage.get_documents_collection(embed_fn)
    collection.add(
        ids=["doc-1"],
        documents=["Text to embed"],
    )

    # Query automatically embeds the query text
    results = collection.query(query_texts=["search query"], n_results=10)
"""

import logging
from typing import Optional

from chromadb import Documents, EmbeddingFunction, Embeddings

from .embeddings import LiteEmbedder
from .constants import DEFAULT_EMBEDDING_MODEL

logger = logging.getLogger(__name__)


class FastEmbedFunction(EmbeddingFunction[Documents]):
    """
    ChromaDB embedding function using FastEmbed.

    This class wraps LiteEmbedder to provide a ChromaDB-compatible
    interface. ChromaDB will automatically call this function when
    documents are added or queries are made.

    Example:
        >>> embed_fn = FastEmbedFunction()
        >>> embeddings = embed_fn(["Hello", "World"])
        >>> print(len(embeddings))
        2
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
        logger.debug(f"FastEmbedFunction initialized with {model_name}")

    def __call__(self, input: Documents) -> Embeddings:
        """
        Generate embeddings for documents.

        This method is called by ChromaDB when documents are added
        or queries are made.

        Args:
            input: List of document texts

        Returns:
            List of embedding vectors
        """
        return self._embedder.embed(input)

    @property
    def dimensions(self) -> int:
        """
        Return embedding dimensions.

        Returns:
            Number of dimensions in embedding vectors
        """
        return self._embedder.dimensions

    @property
    def model_name(self) -> str:
        """
        Return the model name.

        Returns:
            Name of the embedding model
        """
        return self._embedder.model_name


def create_embedding_function(
    model_name: str = DEFAULT_EMBEDDING_MODEL,
    cache_dir: Optional[str] = None,
) -> FastEmbedFunction:
    """
    Create a ChromaDB embedding function.

    This is the recommended way to create an embedding function
    for use with LiteStorage.

    Args:
        model_name: FastEmbed model name. Options:
            - "BAAI/bge-small-en-v1.5" (default, 384d, fast)
            - "BAAI/bge-base-en-v1.5" (768d, better quality)
            - "intfloat/multilingual-e5-small" (384d, multi-language)
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
        >>>
        >>> # Add documents - embeddings generated automatically
        >>> collection.add(
        ...     ids=["doc-1", "doc-2"],
        ...     documents=["First document", "Second document"],
        ... )
        >>>
        >>> # Query - query embedding generated automatically
        >>> results = collection.query(
        ...     query_texts=["search query"],
        ...     n_results=5,
        ... )
    """
    return FastEmbedFunction(model_name=model_name, cache_dir=cache_dir)


# Singleton instance for convenience
_default_embedding_function: Optional[FastEmbedFunction] = None


def get_default_embedding_function() -> FastEmbedFunction:
    """
    Get the default embedding function (singleton).

    This is useful when you want to reuse the same embedding function
    across multiple operations without reloading the model.

    Returns:
        Default FastEmbedFunction instance

    Example:
        >>> embed_fn = get_default_embedding_function()
        >>> # Same instance is returned on subsequent calls
        >>> embed_fn2 = get_default_embedding_function()
        >>> assert embed_fn is embed_fn2
    """
    global _default_embedding_function
    if _default_embedding_function is None:
        _default_embedding_function = create_embedding_function()
    return _default_embedding_function
