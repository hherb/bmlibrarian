"""
BMLibrarian Lite - Lightweight biomedical literature research tool.

A simplified interface for:
- Systematic literature review (search, score, extract, report)
- Document interrogation (Q&A with loaded documents)

Features:
- ChromaDB for vector storage (embedded, no PostgreSQL)
- SQLite for metadata (embedded)
- FastEmbed for local embeddings (CPU-optimized, no PyTorch)
- Anthropic Claude or Ollama for LLM inference
- NCBI E-utilities for PubMed search (online)

No PostgreSQL required.
"""

from .config import LiteConfig
from .storage import LiteStorage
from .embeddings import LiteEmbedder
from .data_models import (
    LiteDocument,
    LiteChunk,
    SearchSession,
    ReviewCheckpoint,
    ScoredDocument,
    Citation,
    InterrogationSession,
)
from .exceptions import (
    LiteError,
    ConfigurationError,
    StorageError,
    EmbeddingError,
    AgentError,
)

__version__ = "0.1.0"


def main() -> int:
    """
    Main entry point for BMLibrarian Lite.

    This is a convenience wrapper that imports and calls the main function
    from the CLI module.

    Returns:
        Application exit code
    """
    import sys
    import os

    # Suppress tokenizers parallelism warning
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

    from .gui.app import run_lite_app
    return run_lite_app()


__all__ = [
    # Configuration
    "LiteConfig",
    # Storage
    "LiteStorage",
    "LiteEmbedder",
    # Data models
    "LiteDocument",
    "LiteChunk",
    "SearchSession",
    "ReviewCheckpoint",
    "ScoredDocument",
    "Citation",
    "InterrogationSession",
    # Exceptions
    "LiteError",
    "ConfigurationError",
    "StorageError",
    "EmbeddingError",
    "AgentError",
    # Version
    "__version__",
]
