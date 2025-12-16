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

# Jitter factor for retry delays (0.0 to 1.0)
# Adds randomness to prevent thundering herd effects
DEFAULT_RETRY_JITTER_FACTOR = 0.2

# =============================================================================
# Security Settings
# =============================================================================

# File permissions for configuration files (owner read/write only)
# 0o600 = -rw------- (only owner can read/write)
CONFIG_FILE_PERMISSIONS = 0o600

# Directory permissions for configuration directories
# 0o700 = drwx------ (only owner can access)
CONFIG_DIR_PERMISSIONS = 0o700

# =============================================================================
# Quality Filtering Settings
# =============================================================================

# Default quality tier threshold for filtering (3 = controlled observational and above)
# Quality tiers: 5=systematic, 4=experimental, 3=controlled, 2=observational, 1=anecdotal
DEFAULT_QUALITY_TIER_THRESHOLD = 3

# Default minimum quality score (0.0 - 1.0)
DEFAULT_QUALITY_SCORE_THRESHOLD = 0.5

# Default confidence threshold for accepting LLM classifications (0.0 - 1.0)
DEFAULT_QUALITY_CONFIDENCE_THRESHOLD = 0.7

# =============================================================================
# Quality Assessment LLM Settings
# =============================================================================

# Model for quick study design classification (Tier 2)
# Claude Haiku: Fast, cheap (~$0.00025/doc)
QUALITY_CLASSIFIER_MODEL = "claude-3-5-haiku-20241022"

# Model for detailed quality assessment (Tier 3)
# Claude Sonnet: More thorough, higher cost (~$0.003/doc)
QUALITY_ASSESSOR_MODEL = "claude-sonnet-4-20250514"

# Temperature for quality classification (lower = more deterministic)
QUALITY_LLM_TEMPERATURE = 0.1

# Max tokens for classification response
QUALITY_CLASSIFIER_MAX_TOKENS = 256

# Max tokens for detailed assessment response
QUALITY_ASSESSOR_MAX_TOKENS = 1024

# =============================================================================
# Quality Metadata Confidence Levels
# =============================================================================

# Confidence when PubMed publication type matches exactly
METADATA_HIGH_CONFIDENCE = 0.95

# Confidence when PubMed publication type matches partially
METADATA_PARTIAL_MATCH_CONFIDENCE = 0.80

# Confidence when publication types present but unrecognized
METADATA_UNKNOWN_TYPE_CONFIDENCE = 0.30

# Confidence when no publication types available
METADATA_NO_TYPE_CONFIDENCE = 0.0

# =============================================================================
# Quality Classification Confidence Levels
# =============================================================================

# Confidence threshold for accepting Haiku classification
CLASSIFIER_ACCEPTANCE_CONFIDENCE = 0.75

# Confidence boost when multiple indicators agree
CLASSIFIER_MULTI_INDICATOR_BOOST = 0.10

# Maximum confidence from LLM classification
CLASSIFIER_MAX_CONFIDENCE = 0.90

# =============================================================================
# Quality Assessment Batch Settings
# =============================================================================

# Number of documents to classify in parallel
QUALITY_BATCH_SIZE = 10

# Delay between API calls in seconds (rate limiting)
QUALITY_API_DELAY_SECONDS = 0.1

# Maximum documents to assess with detailed Sonnet analysis
QUALITY_MAX_DETAILED_ASSESSMENTS = 20

# =============================================================================
# JSON Parsing Security Settings
# =============================================================================

# Maximum size for JSON responses from LLM (in bytes)
# This prevents DoS attacks via oversized responses
JSON_MAX_RESPONSE_SIZE_BYTES = 65536  # 64 KB

# =============================================================================
# Classification Parsing Constants
# =============================================================================

# Valid values for blinding level (Cochrane terminology)
VALID_BLINDING_VALUES = frozenset({"none", "single", "double", "triple"})

# Valid values for bias risk assessment
VALID_BIAS_RISK_VALUES = frozenset({"low", "unclear", "high"})

# Default confidence value - used when parsing fails
# This is intentionally LOW to signal uncertainty
CONFIDENCE_PARSE_FAILURE_DEFAULT = 0.0

# =============================================================================
# Abstract Processing Settings
# =============================================================================

# Maximum abstract length for single-pass LLM processing
# Abstracts longer than this will be processed in chunks
ABSTRACT_MAX_SINGLE_PASS_LENGTH = 8000

# Chunk size for processing long abstracts
ABSTRACT_CHUNK_SIZE = 4000

# Overlap between chunks for context preservation
ABSTRACT_CHUNK_OVERLAP = 500

# =============================================================================
# Batch Processing Retry Settings
# =============================================================================

# Maximum retry attempts for failed classifications
CLASSIFICATION_MAX_RETRIES = 3

# Base delay between retries in seconds
CLASSIFICATION_RETRY_BASE_DELAY = 1.0

# Exponential backoff multiplier for retries
CLASSIFICATION_RETRY_BACKOFF_MULTIPLIER = 2.0

# Jitter factor for retry delays (0.0 to 1.0)
# Adds randomness to prevent thundering herd effects (per golden rule 22)
CLASSIFICATION_RETRY_JITTER_FACTOR = 0.2
