"""
Sentence Transformers Embedding Provider for BMLibrarian.

Uses sentence-transformers for direct, stable embedding generation.
This is the native library for models like snowflake-arctic-embed2
and provides the most reliable embeddings.

Usage:
    from bmlibrarian.embeddings.sentence_transformer_embedder import SentenceTransformerEmbedder

    # Initialize with model name (will download if needed)
    embedder = SentenceTransformerEmbedder(model_name="Snowflake/snowflake-arctic-embed-l-v2.0")

    # Generate single embedding
    embedding = embedder.embed("Some text to embed")

    # Generate batch embeddings (efficient)
    embeddings = embedder.embed_batch(["Text 1", "Text 2", "Text 3"])
"""

import logging
from typing import List, Optional

logger = logging.getLogger(__name__)

# Default model - snowflake-arctic-embed2 large variant
DEFAULT_ST_MODEL = "Snowflake/snowflake-arctic-embed-l-v2.0"

# Embedding dimension for snowflake-arctic-embed-l-v2.0
EMBEDDING_DIMENSION = 1024


class SentenceTransformerEmbedder:
    """
    Embedding provider using sentence-transformers library.

    This provides stable, efficient embeddings without network instability
    issues. The model runs locally after initial download.
    """

    def __init__(
        self,
        model_name: str = DEFAULT_ST_MODEL,
        device: Optional[str] = None,
        trust_remote_code: bool = True,
    ) -> None:
        """
        Initialize the sentence-transformers embedder.

        Args:
            model_name: HuggingFace model name or path.
            device: Device to use ('cpu', 'cuda', 'mps', or None for auto).
            trust_remote_code: Whether to trust remote code (required for some models).

        Raises:
            ImportError: If sentence-transformers is not installed.
        """
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as e:
            raise ImportError(
                "sentence-transformers is required. Install with: uv add sentence-transformers"
            ) from e

        logger.info(f"Loading sentence-transformer model: {model_name}")

        self.model = SentenceTransformer(
            model_name,
            device=device,
            trust_remote_code=trust_remote_code,
        )

        self.model_name = model_name
        self._embedding_dim = self.model.get_sentence_embedding_dimension()

        logger.info(
            f"SentenceTransformerEmbedder initialized: {model_name} "
            f"(dim={self._embedding_dim}, device={self.model.device})"
        )

    def embed(self, text: str) -> Optional[List[float]]:
        """
        Generate embedding for a single text.

        Args:
            text: Text to embed.

        Returns:
            Embedding vector as list of floats, or None on failure.
        """
        if not text or not text.strip():
            logger.warning("Cannot embed empty text")
            return None

        try:
            # encode() returns numpy array, convert to list
            embedding = self.model.encode(text, convert_to_numpy=True)
            return embedding.tolist()

        except Exception as e:
            logger.error(f"Embedding generation failed: {e}")
            return None

    def embed_batch(self, texts: List[str]) -> List[Optional[List[float]]]:
        """
        Generate embeddings for multiple texts efficiently.

        sentence-transformers handles batching internally for optimal performance.

        Args:
            texts: List of texts to embed.

        Returns:
            List of embedding vectors (or None for failed/empty texts).
        """
        if not texts:
            return []

        # Track which texts are valid
        valid_texts = []
        valid_indices = []

        for i, text in enumerate(texts):
            if text and text.strip():
                valid_texts.append(text)
                valid_indices.append(i)

        if not valid_texts:
            logger.warning("All texts in batch are empty")
            return [None] * len(texts)

        try:
            # Batch encode - sentence-transformers handles this efficiently
            embeddings = self.model.encode(
                valid_texts,
                convert_to_numpy=True,
                show_progress_bar=False,
            )

            # Build result list with None for invalid texts
            result: List[Optional[List[float]]] = [None] * len(texts)
            for idx, embedding in zip(valid_indices, embeddings):
                result[idx] = embedding.tolist()

            return result

        except Exception as e:
            logger.error(f"Batch embedding generation failed: {e}")
            return [None] * len(texts)

    def get_embedding_dimension(self) -> int:
        """
        Get the embedding dimension for this model.

        Returns:
            Embedding dimension.
        """
        return self._embedding_dim


# Mapping from Ollama model names to HuggingFace model names
OLLAMA_TO_HF_MODEL_MAP = {
    "snowflake-arctic-embed2:latest": "Snowflake/snowflake-arctic-embed-l-v2.0",
    "snowflake-arctic-embed2": "Snowflake/snowflake-arctic-embed-l-v2.0",
    "nomic-embed-text:latest": "nomic-ai/nomic-embed-text-v1.5",
    "nomic-embed-text": "nomic-ai/nomic-embed-text-v1.5",
    "all-minilm:latest": "sentence-transformers/all-MiniLM-L6-v2",
    "all-minilm": "sentence-transformers/all-MiniLM-L6-v2",
}


def get_hf_model_name(ollama_model_name: str) -> str:
    """
    Convert Ollama model name to HuggingFace model name.

    Args:
        ollama_model_name: Ollama-style model name.

    Returns:
        HuggingFace model name.
    """
    # Check direct mapping
    if ollama_model_name in OLLAMA_TO_HF_MODEL_MAP:
        return OLLAMA_TO_HF_MODEL_MAP[ollama_model_name]

    # If it looks like a HuggingFace model name already (contains /), use as-is
    if "/" in ollama_model_name:
        return ollama_model_name

    # Default: assume it's already a valid model name
    logger.warning(
        f"Unknown model '{ollama_model_name}', using as-is. "
        f"Known models: {list(OLLAMA_TO_HF_MODEL_MAP.keys())}"
    )
    return ollama_model_name
