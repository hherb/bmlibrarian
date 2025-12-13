"""
Constants for the LLM abstraction layer.

This module defines all constant values used across the LLM module,
following the golden rule of "no magic numbers or hardcoded values".
"""

# Default embedding model for semantic search
# This must match the model_id=1 in the database embedding_models table
DEFAULT_EMBEDDING_MODEL = "snowflake-arctic-embed2:latest"

# Default Ollama host URL
DEFAULT_OLLAMA_HOST = "http://localhost:11434"

# Default generation parameters
DEFAULT_TEMPERATURE = 0.7
DEFAULT_TOP_P = 0.9

# Retry configuration
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_DELAY = 1.0  # seconds
RETRY_BACKOFF_MULTIPLIER = 2  # exponential backoff multiplier

# Default max tokens for providers that require it (e.g., Anthropic)
DEFAULT_ANTHROPIC_MAX_TOKENS = 4096

# Request timeout in seconds
DEFAULT_REQUEST_TIMEOUT = 120.0

# Nanoseconds per second for timing conversions
NANOSECONDS_PER_SECOND = 1_000_000_000
