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
from .embeddings import LiteEmbedder
from .chroma_embeddings import (
    FastEmbedFunction,
    create_embedding_function,
    get_default_embedding_function,
)
from .chunking import (
    chunk_text,
    chunk_document_for_interrogation,
    estimate_chunk_count,
)
from .agents import (
    LiteBaseAgent,
    LiteSearchAgent,
    LiteScoringAgent,
    LiteCitationAgent,
    LiteReportingAgent,
    LiteInterrogationAgent,
)

# GUI imports are optional (require PySide6)
try:
    from .gui import (
        LiteMainWindow,
        run_lite_app,
        SystematicReviewTab,
        DocumentInterrogationTab,
        SettingsDialog,
    )
    _GUI_AVAILABLE = True
except ImportError:
    _GUI_AVAILABLE = False

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
    # Embeddings
    "LiteEmbedder",
    "FastEmbedFunction",
    "create_embedding_function",
    "get_default_embedding_function",
    # Chunking
    "chunk_text",
    "chunk_document_for_interrogation",
    "estimate_chunk_count",
    # Agents
    "LiteBaseAgent",
    "LiteSearchAgent",
    "LiteScoringAgent",
    "LiteCitationAgent",
    "LiteReportingAgent",
    "LiteInterrogationAgent",
    # GUI (optional, requires PySide6)
    "_GUI_AVAILABLE",
]

# Add GUI exports if available
if _GUI_AVAILABLE:
    __all__.extend([
        "LiteMainWindow",
        "run_lite_app",
        "SystematicReviewTab",
        "DocumentInterrogationTab",
        "SettingsDialog",
    ])
