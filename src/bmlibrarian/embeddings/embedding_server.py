"""
Embedding Server Client for BMLibrarian.

Provides a clean, stable interface to Ollama's embedding API using raw HTTP requests.
This bypasses the ollama Python library which can have connection stability issues.

Uses the /api/embed endpoint which supports native batch embedding.

Usage:
    from bmlibrarian.embeddings.embedding_server import EmbeddingServer

    # Initialize with defaults
    server = EmbeddingServer()

    # Single embedding
    embedding = server.embed("Some text to embed")

    # Batch embedding (more efficient)
    embeddings = server.embed_batch(["Text 1", "Text 2", "Text 3"])

    # Check server availability
    if server.is_available():
        print("Server is ready")
"""

import logging
from typing import List, Optional
from dataclasses import dataclass

import requests

logger = logging.getLogger(__name__)

# Default configuration
DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_MODEL = "snowflake-arctic-embed2:latest"
DEFAULT_TIMEOUT_SECONDS = 120
DEFAULT_CONNECT_TIMEOUT_SECONDS = 5


@dataclass
class EmbeddingServerConfig:
    """Configuration for the embedding server client."""

    base_url: str = DEFAULT_OLLAMA_URL
    model: str = DEFAULT_MODEL
    timeout: float = DEFAULT_TIMEOUT_SECONDS
    connect_timeout: float = DEFAULT_CONNECT_TIMEOUT_SECONDS

    @property
    def embed_url(self) -> str:
        """Return the full URL for the embed endpoint."""
        return f"{self.base_url}/api/embed"

    @property
    def tags_url(self) -> str:
        """Return the full URL for listing models."""
        return f"{self.base_url}/api/tags"


class EmbeddingServer:
    """
    Client for Ollama's embedding API using raw HTTP requests.

    This provides a more stable interface than the ollama Python library,
    especially for batch operations and long-running embedding tasks.

    Features:
    - Native batch embedding via /api/embed endpoint
    - Configurable timeouts
    - Connection health checking
    - Detailed error logging
    """

    def __init__(
        self,
        base_url: str = DEFAULT_OLLAMA_URL,
        model: str = DEFAULT_MODEL,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        connect_timeout: float = DEFAULT_CONNECT_TIMEOUT_SECONDS,
    ) -> None:
        """
        Initialize the embedding server client.

        Args:
            base_url: Ollama server URL (default: http://localhost:11434).
            model: Embedding model name (default: snowflake-arctic-embed2:latest).
            timeout: Request timeout in seconds (default: 120).
            connect_timeout: Connection timeout in seconds (default: 5).
        """
        self.config = EmbeddingServerConfig(
            base_url=base_url.rstrip("/"),
            model=model,
            timeout=timeout,
            connect_timeout=connect_timeout,
        )
        self._session = requests.Session()
        logger.info(
            f"EmbeddingServer initialized: {self.config.base_url} "
            f"model={self.config.model}"
        )

    def is_available(self) -> bool:
        """
        Check if the embedding server is available.

        Returns:
            True if server is reachable and responding.
        """
        try:
            response = self._session.get(
                self.config.tags_url,
                timeout=self.config.connect_timeout,
            )
            return response.status_code == 200
        except requests.RequestException as e:
            logger.warning(f"Embedding server not available: {e}")
            return False

    def list_models(self) -> List[str]:
        """
        List available models on the server.

        Returns:
            List of model names.
        """
        try:
            response = self._session.get(
                self.config.tags_url,
                timeout=self.config.connect_timeout,
            )
            response.raise_for_status()
            data = response.json()
            return [model["name"] for model in data.get("models", [])]
        except requests.RequestException as e:
            logger.error(f"Failed to list models: {e}")
            return []

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

        result = self.embed_batch([text])
        return result[0] if result else None

    def embed_batch(self, texts: List[str]) -> List[Optional[List[float]]]:
        """
        Generate embeddings for multiple texts in a single API call.

        This is more efficient than calling embed() multiple times as it
        uses Ollama's native batch embedding support.

        Args:
            texts: List of texts to embed.

        Returns:
            List of embedding vectors (or None for failed/empty texts).
            Same length as input list.
        """
        if not texts:
            return []

        # Track valid texts and their indices
        valid_texts: List[str] = []
        valid_indices: List[int] = []

        for i, text in enumerate(texts):
            if text and text.strip():
                valid_texts.append(text)
                valid_indices.append(i)

        if not valid_texts:
            logger.warning("All texts in batch are empty")
            return [None] * len(texts)

        try:
            response = self._session.post(
                self.config.embed_url,
                json={
                    "model": self.config.model,
                    "input": valid_texts,
                },
                timeout=(self.config.connect_timeout, self.config.timeout),
            )

            if response.status_code != 200:
                logger.error(
                    f"Embedding request failed: HTTP {response.status_code} - "
                    f"{response.text[:500]}"
                )
                return [None] * len(texts)

            data = response.json()

            if "embeddings" not in data:
                logger.error(f"Unexpected response format: {data}")
                return [None] * len(texts)

            embeddings = data["embeddings"]

            if len(embeddings) != len(valid_texts):
                logger.error(
                    f"Embedding count mismatch: expected {len(valid_texts)}, "
                    f"got {len(embeddings)}"
                )
                return [None] * len(texts)

            # Build result list with None for empty/invalid texts
            result: List[Optional[List[float]]] = [None] * len(texts)
            for idx, embedding in zip(valid_indices, embeddings):
                result[idx] = embedding

            return result

        except requests.Timeout:
            logger.error(
                f"Embedding request timed out after {self.config.timeout}s "
                f"for {len(valid_texts)} texts"
            )
            return [None] * len(texts)

        except requests.RequestException as e:
            logger.error(f"Embedding request failed: {e}")
            return [None] * len(texts)

        except Exception as e:
            logger.error(f"Unexpected error during embedding: {e}")
            return [None] * len(texts)

    def get_embedding_dimension(self) -> Optional[int]:
        """
        Get the embedding dimension by generating a test embedding.

        Returns:
            Embedding dimension, or None if unable to determine.
        """
        test_embedding = self.embed("test")
        if test_embedding:
            return len(test_embedding)
        return None

    def close(self) -> None:
        """Close the HTTP session."""
        self._session.close()

    def __enter__(self) -> "EmbeddingServer":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.close()


# Module-level convenience functions
_default_server: Optional[EmbeddingServer] = None


def get_default_server(
    base_url: str = DEFAULT_OLLAMA_URL,
    model: str = DEFAULT_MODEL,
) -> EmbeddingServer:
    """
    Get or create the default embedding server instance.

    This provides a singleton-like pattern for common usage.

    Args:
        base_url: Ollama server URL.
        model: Embedding model name.

    Returns:
        EmbeddingServer instance.
    """
    global _default_server
    if _default_server is None:
        _default_server = EmbeddingServer(base_url=base_url, model=model)
    return _default_server


def embed(text: str, model: str = DEFAULT_MODEL) -> Optional[List[float]]:
    """
    Convenience function to embed a single text.

    Args:
        text: Text to embed.
        model: Model name (default: snowflake-arctic-embed2:latest).

    Returns:
        Embedding vector or None on failure.
    """
    server = get_default_server(model=model)
    return server.embed(text)


def embed_batch(
    texts: List[str], model: str = DEFAULT_MODEL
) -> List[Optional[List[float]]]:
    """
    Convenience function to embed multiple texts.

    Args:
        texts: List of texts to embed.
        model: Model name (default: snowflake-arctic-embed2:latest).

    Returns:
        List of embedding vectors (or None for failures).
    """
    server = get_default_server(model=model)
    return server.embed_batch(texts)
