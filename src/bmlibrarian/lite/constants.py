"""
Constants for BMLibrarian Lite.

All magic numbers and default values are defined here to ensure
consistency and easy configuration. No hardcoded values should
appear elsewhere in the lite module.
"""

from pathlib import Path

# =============================================================================
# Data Directory
# =============================================================================

# Default data directory - can be overridden by config
DEFAULT_DATA_DIR = Path.home() / ".bmlibrarian_lite"

# =============================================================================
# ChromaDB Settings
# =============================================================================

# Collection names for ChromaDB
CHROMA_DOCUMENTS_COLLECTION = "documents"
CHROMA_CHUNKS_COLLECTION = "chunks"

# =============================================================================
# Embedding Model Settings
# =============================================================================

# Default FastEmbed model
# BAAI/bge-small-en-v1.5: Good balance of speed and quality
# Alternatives:
#   - BAAI/bge-base-en-v1.5: Better quality, slower
#   - intfloat/multilingual-e5-small: Multi-language support
DEFAULT_EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
DEFAULT_EMBEDDING_DIMENSIONS = 384

# Supported embedding models with their specifications
EMBEDDING_MODEL_SPECS = {
    "BAAI/bge-small-en-v1.5": {
        "dimensions": 384,
        "size_mb": 50,
        "description": "Fast, good quality (default)",
    },
    "BAAI/bge-base-en-v1.5": {
        "dimensions": 768,
        "size_mb": 130,
        "description": "Better quality, slower",
    },
    "intfloat/multilingual-e5-small": {
        "dimensions": 384,
        "size_mb": 50,
        "description": "Multi-language support",
    },
}

# =============================================================================
# SQLite Database Settings
# =============================================================================

# SQLite database filename
SQLITE_DATABASE_NAME = "metadata.db"

# =============================================================================
# PubMed API Settings
# =============================================================================

# Cache TTL for PubMed API responses (24 hours)
PUBMED_CACHE_TTL_SECONDS = 86400

# Default maximum results for PubMed searches
PUBMED_DEFAULT_MAX_RESULTS = 200

# Batch size for fetching PubMed article details
PUBMED_BATCH_SIZE = 200

# =============================================================================
# Document Chunking Settings
# =============================================================================

# Default chunk size in characters
DEFAULT_CHUNK_SIZE = 8000

# Default overlap between chunks in characters
DEFAULT_CHUNK_OVERLAP = 200

# Minimum chunk size (smaller chunks are merged with previous)
MIN_CHUNK_SIZE = 100

# =============================================================================
# Search Settings
# =============================================================================

# Default similarity threshold for vector search (0.0 - 1.0)
DEFAULT_SIMILARITY_THRESHOLD = 0.5

# Default maximum results for vector search
DEFAULT_MAX_RESULTS = 20

# =============================================================================
# LLM Settings
# =============================================================================

# Default LLM provider
DEFAULT_LLM_PROVIDER = "anthropic"

# Default LLM model
DEFAULT_LLM_MODEL = "claude-sonnet-4-20250514"

# Default temperature for LLM requests
DEFAULT_LLM_TEMPERATURE = 0.3

# Default max tokens for LLM responses
DEFAULT_LLM_MAX_TOKENS = 4096

# =============================================================================
# Timeout Settings (milliseconds)
# =============================================================================

# Timeout for embedding generation
EMBEDDING_TIMEOUT_MS = 30000

# Timeout for LLM requests
LLM_TIMEOUT_MS = 120000

# Timeout for PubMed API requests
PUBMED_TIMEOUT_MS = 30000

# =============================================================================
# Scoring Settings
# =============================================================================

# Default minimum score for including documents in results
DEFAULT_MIN_SCORE = 3

# Score range
SCORE_MIN = 1
SCORE_MAX = 5

# =============================================================================
# Network Retry Settings
# =============================================================================

# Maximum number of retry attempts for network operations
DEFAULT_MAX_RETRIES = 3

# Initial delay between retries in seconds
DEFAULT_RETRY_BASE_DELAY = 1.0

# Maximum delay between retries in seconds
DEFAULT_RETRY_MAX_DELAY = 10.0

# Exponential backoff multiplier
DEFAULT_RETRY_EXPONENTIAL_BASE = 2.0
