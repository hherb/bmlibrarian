"""
Local embedding generation using FastEmbed (ONNX runtime).

FastEmbed provides CPU-optimized embeddings without requiring GPU
or external services like Ollama. Models are downloaded automatically
on first use.

Usage:
    from bmlibrarian_lite.embeddings import LiteEmbedder

    embedder = LiteEmbedder()

    # Single text
    embedding = embedder.embed_single("Some text to embed")

    # Multiple texts (more efficient)
    embeddings = embedder.embed(["Text 1", "Text 2", "Text 3"])
"""

import logging
from typing import Generator, Optional

from fastembed import TextEmbedding

from .constants import (
    DEFAULT_EMBEDDING_MODEL,
    EMBEDDING_MODEL_SPECS,
)

logger = logging.getLogger(__name__)


class LiteEmbedder:
    """
    Lightweight local embeddings using FastEmbed.

    Uses ONNX runtime for CPU-optimized inference. No GPU or external
    API required. Models are downloaded automatically on first use.

    Supported models:
    - BAAI/bge-small-en-v1.5 (384 dimensions, ~50MB) - default, fast
    - BAAI/bge-base-en-v1.5 (768 dimensions, ~130MB) - better quality
    - intfloat/multilingual-e5-small (384 dimensions) - multi-language

    Example:
        >>> embedder = LiteEmbedder()
        >>> embedding = embedder.embed_single("Hello world")
        >>> print(f"Dimensions: {len(embedding)}")
        Dimensions: 384
    """

    def __init__(
        self,
        model_name: str = DEFAULT_EMBEDDING_MODEL,
        cache_dir: Optional[str] = None,
    ) -> None:
        """
        Initialize the embedder.

        Args:
            model_name: FastEmbed model name. See list_supported_models()
                       for recommended options.
            cache_dir: Optional directory for model cache. If None,
                      uses FastEmbed's default cache location.
        """
        self.model_name = model_name
        self._validate_model(model_name)

        logger.info(f"Loading embedding model: {model_name}")

        # Initialize FastEmbed with optional cache directory
        kwargs: dict = {"model_name": model_name}
        if cache_dir:
            kwargs["cache_dir"] = cache_dir

        self._model = TextEmbedding(**kwargs)
        self._dimensions = self._get_dimensions(model_name)

        logger.info(f"Embedding model loaded: {model_name} ({self._dimensions}d)")

    @property
    def dimensions(self) -> int:
        """
        Return embedding dimensions.

        Returns:
            Number of dimensions in the embedding vector
        """
        return self._dimensions

    def _validate_model(self, model_name: str) -> None:
        """
        Validate that the model is supported.

        Args:
            model_name: Model name to validate

        Note:
            FastEmbed supports many models beyond our recommended list.
            We log a warning for unknown models but don't fail, as users
            may want to experiment with other models.
        """
        if model_name in EMBEDDING_MODEL_SPECS:
            return

        # For other models, log a warning but don't fail
        logger.warning(
            f"Model {model_name} not in recommended list. "
            f"Recommended models: {list(EMBEDDING_MODEL_SPECS.keys())}"
        )

    def _get_dimensions(self, model_name: str) -> int:
        """
        Get embedding dimensions for a model.

        Args:
            model_name: Model name

        Returns:
            Number of dimensions
        """
        if model_name in EMBEDDING_MODEL_SPECS:
            return EMBEDDING_MODEL_SPECS[model_name]["dimensions"]

        # For unknown models, we need to generate a test embedding
        logger.debug(f"Unknown model {model_name}, detecting dimensions...")
        test_embedding = list(self._model.embed(["test"]))[0]
        return len(test_embedding)

    def embed(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embeddings for multiple texts.

        This is more efficient than calling embed_single() in a loop
        because FastEmbed can batch the inference.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors (each is a list of floats)

        Example:
            >>> embedder = LiteEmbedder()
            >>> embeddings = embedder.embed(["Hello", "World"])
            >>> print(len(embeddings))
            2
        """
        if not texts:
            return []

        # FastEmbed returns a generator of numpy arrays, convert to list of Python floats
        # ChromaDB requires standard Python floats, not np.float32
        embeddings = list(self._model.embed(texts))

        logger.debug(f"Generated {len(embeddings)} embeddings")
        return [[float(x) for x in emb] for emb in embeddings]

    def embed_single(self, text: str) -> list[float]:
        """
        Generate embedding for a single text.

        For multiple texts, use embed() instead for better efficiency.

        Args:
            text: Text to embed

        Returns:
            Embedding vector as list of floats

        Example:
            >>> embedder = LiteEmbedder()
            >>> embedding = embedder.embed_single("Hello world")
            >>> print(len(embedding))
            384
        """
        embeddings = self.embed([text])
        return embeddings[0] if embeddings else []

    def embed_generator(
        self,
        texts: list[str],
    ) -> Generator[list[float], None, None]:
        """
        Generate embeddings as a generator (memory efficient).

        Use this for very large lists of texts where you don't want
        to hold all embeddings in memory at once.

        Args:
            texts: List of texts to embed

        Yields:
            Embedding vectors one at a time

        Example:
            >>> embedder = LiteEmbedder()
            >>> for embedding in embedder.embed_generator(large_text_list):
            ...     process(embedding)
        """
        for embedding in self._model.embed(texts):
            yield [float(x) for x in embedding]

    @classmethod
    def list_supported_models(cls) -> list[str]:
        """
        List supported/recommended models.

        Returns:
            List of model names that are tested and recommended
        """
        return list(EMBEDDING_MODEL_SPECS.keys())

    @classmethod
    def get_model_info(cls, model_name: str) -> dict:
        """
        Get information about a model.

        Args:
            model_name: Model name

        Returns:
            Dictionary with model info (dimensions, size_mb, description)
            or empty dict if model is unknown

        Example:
            >>> info = LiteEmbedder.get_model_info("BAAI/bge-small-en-v1.5")
            >>> print(info["dimensions"])
            384
        """
        return EMBEDDING_MODEL_SPECS.get(model_name, {})
