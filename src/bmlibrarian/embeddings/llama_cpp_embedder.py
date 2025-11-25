"""
LlamaCpp Embedding Provider for BMLibrarian.

Uses llama-cpp-python for direct, stable embedding generation without
going through Ollama's proxy layer. This is more robust for batch
processing large numbers of documents.

Usage:
    from bmlibrarian.embeddings.llama_cpp_embedder import LlamaCppEmbedder

    # Initialize with GGUF model path
    embedder = LlamaCppEmbedder(model_path="/path/to/model.gguf")

    # Generate single embedding
    embedding = embedder.embed("Some text to embed")

    # Generate batch embeddings
    embeddings = embedder.embed_batch(["Text 1", "Text 2", "Text 3"])
"""

import logging
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

# Default model path - can be overridden
DEFAULT_MODEL_PATH = Path.home() / ".ollama" / "models" / "blobs"

# Embedding dimension for snowflake-arctic-embed2
EMBEDDING_DIMENSION = 1024

# Context size for embeddings (snowflake-arctic-embed2 supports 8192 tokens)
DEFAULT_CONTEXT_SIZE = 8192


class LlamaCppEmbedder:
    """
    Embedding provider using llama-cpp-python for direct GGUF model inference.

    This bypasses Ollama's server layer for more stable, predictable performance
    when processing large batches of documents.
    """

    def __init__(
        self,
        model_path: str,
        n_ctx: int = DEFAULT_CONTEXT_SIZE,
        n_batch: int = 512,
        n_threads: Optional[int] = None,
        verbose: bool = False,
    ) -> None:
        """
        Initialize the LlamaCpp embedder.

        Args:
            model_path: Path to the GGUF model file.
            n_ctx: Context window size (default: 8192 for snowflake-arctic-embed2).
            n_batch: Batch size for prompt processing.
            n_threads: Number of CPU threads (None = auto-detect).
            verbose: Enable verbose llama.cpp output.

        Raises:
            ImportError: If llama-cpp-python is not installed.
            FileNotFoundError: If model file doesn't exist.
        """
        try:
            from llama_cpp import Llama
        except ImportError as e:
            raise ImportError(
                "llama-cpp-python is required. Install with: uv add llama-cpp-python"
            ) from e

        model_file = Path(model_path)
        if not model_file.exists():
            raise FileNotFoundError(f"Model file not found: {model_path}")

        logger.info(f"Loading GGUF model from: {model_path}")

        # Initialize the model with embedding mode enabled
        self.model = Llama(
            model_path=str(model_file),
            n_ctx=n_ctx,
            n_batch=n_batch,
            n_threads=n_threads,
            embedding=True,  # Enable embedding mode
            verbose=verbose,
        )

        self.model_path = model_path
        self.n_ctx = n_ctx
        logger.info(f"LlamaCpp embedder initialized (n_ctx={n_ctx})")

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
            # llama-cpp-python's embed() method
            embedding = self.model.embed(text)

            if embedding is None:
                logger.error("Model returned None for embedding")
                return None

            # Ensure it's a flat list (not nested)
            if isinstance(embedding, list) and len(embedding) > 0:
                if isinstance(embedding[0], list):
                    # Nested list - take first element
                    embedding = embedding[0]

            return embedding

        except Exception as e:
            logger.error(f"Embedding generation failed: {e}")
            return None

    def embed_batch(self, texts: List[str]) -> List[Optional[List[float]]]:
        """
        Generate embeddings for multiple texts.

        Args:
            texts: List of texts to embed.

        Returns:
            List of embedding vectors (or None for failed texts).
        """
        if not texts:
            return []

        results: List[Optional[List[float]]] = []

        for text in texts:
            if text and text.strip():
                embedding = self.embed(text)
                results.append(embedding)
            else:
                results.append(None)

        return results

    def get_embedding_dimension(self) -> int:
        """
        Get the embedding dimension for this model.

        Returns:
            Embedding dimension.
        """
        # Try to get from model metadata
        try:
            return self.model.n_embd()
        except Exception:
            return EMBEDDING_DIMENSION


def find_ollama_model_path(model_name: str) -> Optional[str]:
    """
    Find the GGUF file path for an Ollama model.

    Ollama stores models in ~/.ollama/models/blobs/ with SHA256 hashes.
    This function attempts to find the correct blob for a given model.

    Args:
        model_name: Ollama model name (e.g., "snowflake-arctic-embed2:latest").

    Returns:
        Path to the GGUF blob file, or None if not found.
    """
    import json

    ollama_dir = Path.home() / ".ollama" / "models"
    manifests_dir = ollama_dir / "manifests" / "registry.ollama.ai" / "library"

    # Parse model name (e.g., "snowflake-arctic-embed2:latest" -> "snowflake-arctic-embed2", "latest")
    if ":" in model_name:
        name, tag = model_name.split(":", 1)
    else:
        name, tag = model_name, "latest"

    # Find manifest file
    manifest_path = manifests_dir / name / tag
    if not manifest_path.exists():
        logger.warning(f"Ollama manifest not found: {manifest_path}")
        return None

    try:
        with open(manifest_path) as f:
            manifest = json.load(f)

        # Find the model layer (mediaType contains "model")
        for layer in manifest.get("layers", []):
            media_type = layer.get("mediaType", "")
            if "model" in media_type:
                digest = layer.get("digest", "")
                if digest.startswith("sha256:"):
                    blob_name = digest.replace(":", "-")
                    blob_path = ollama_dir / "blobs" / blob_name
                    if blob_path.exists():
                        logger.info(f"Found Ollama model blob: {blob_path}")
                        return str(blob_path)

        logger.warning(f"No model layer found in manifest for {model_name}")
        return None

    except Exception as e:
        logger.error(f"Error reading Ollama manifest: {e}")
        return None
