"""
Configuration management for BMLibrarian Lite.

Provides dataclass-based configuration with sensible defaults and
JSON file persistence. Configuration is loaded from:
    ~/.bmlibrarian_lite/config.json

All paths are resolved relative to the data directory.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Any
import hashlib
import json
import logging
import os
import stat

from .constants import (
    CONFIG_DIR_PERMISSIONS,
    CONFIG_FILE_PERMISSIONS,
    DEFAULT_DATA_DIR,
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_CHUNK_SIZE,
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_SIMILARITY_THRESHOLD,
    DEFAULT_MAX_RESULTS,
    DEFAULT_LLM_PROVIDER,
    DEFAULT_LLM_MODEL,
    DEFAULT_LLM_TEMPERATURE,
    DEFAULT_LLM_MAX_TOKENS,
    SQLITE_DATABASE_NAME,
    MIN_CHUNK_SIZE,
    EMBEDDING_MODEL_SPECS,
)

logger = logging.getLogger(__name__)


@dataclass
class LLMConfig:
    """LLM provider configuration."""

    provider: str = DEFAULT_LLM_PROVIDER
    model: str = DEFAULT_LLM_MODEL
    temperature: float = DEFAULT_LLM_TEMPERATURE
    max_tokens: int = DEFAULT_LLM_MAX_TOKENS


@dataclass
class EmbeddingConfig:
    """Embedding model configuration."""

    model: str = DEFAULT_EMBEDDING_MODEL
    cache_dir: Optional[Path] = None


@dataclass
class PubMedConfig:
    """PubMed API configuration."""

    email: str = ""  # Required by NCBI for polite access
    api_key: Optional[str] = None  # Optional, increases rate limit to 10 req/sec


@dataclass
class OpenAthensConfig:
    """OpenAthens institutional access configuration."""

    enabled: bool = False  # Whether OpenAthens is configured
    institution_url: str = ""  # Institution's OpenAthens login URL (HTTPS required)
    session_max_age_hours: int = 24  # Maximum session age before re-authentication


@dataclass
class DiscoveryConfig:
    """PDF discovery and download configuration."""

    unpaywall_email: str = ""  # Email for Unpaywall API (enables additional PDF sources)


@dataclass
class StorageConfig:
    """Storage configuration with derived paths."""

    data_dir: Path = field(default_factory=lambda: DEFAULT_DATA_DIR)

    @property
    def chroma_dir(self) -> Path:
        """Directory for ChromaDB storage."""
        return self.data_dir / "chroma_db"

    @property
    def sqlite_path(self) -> Path:
        """Path to SQLite database file."""
        return self.data_dir / SQLITE_DATABASE_NAME

    @property
    def reviews_dir(self) -> Path:
        """Directory for review checkpoints."""
        return self.data_dir / "reviews"

    @property
    def exports_dir(self) -> Path:
        """Directory for exported reports."""
        return self.data_dir / "exports"

    @property
    def cache_dir(self) -> Path:
        """Directory for temporary cache."""
        return self.data_dir / "cache"

    @property
    def env_file(self) -> Path:
        """Path to .env file for API keys."""
        return self.data_dir / ".env"


@dataclass
class SearchConfig:
    """Search configuration."""

    chunk_size: int = DEFAULT_CHUNK_SIZE
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP
    similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD
    max_results: int = DEFAULT_MAX_RESULTS


@dataclass
class LiteConfig:
    """
    Main configuration for BMLibrarian Lite.

    Combines all sub-configurations and provides load/save functionality.

    Usage:
        # Load from default location
        config = LiteConfig.load()

        # Load from specific path
        config = LiteConfig.load(Path("/path/to/config.json"))

        # Use defaults
        config = LiteConfig()

        # Modify and save
        config.llm.model = "claude-3-haiku-20240307"
        config.save()

    Validation Caching:
        Validation results are cached based on a hash of configuration values.
        The cache is automatically invalidated when configuration changes.
        Use invalidate_validation_cache() to force re-validation.
    """

    llm: LLMConfig = field(default_factory=LLMConfig)
    embeddings: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    pubmed: PubMedConfig = field(default_factory=PubMedConfig)
    discovery: DiscoveryConfig = field(default_factory=DiscoveryConfig)
    openathens: OpenAthensConfig = field(default_factory=OpenAthensConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    search: SearchConfig = field(default_factory=SearchConfig)

    # Validation cache (not serialized)
    _validation_cache: dict[str, list[str]] = field(
        default_factory=dict, repr=False, compare=False
    )

    @classmethod
    def load(cls, config_path: Optional[Path] = None) -> "LiteConfig":
        """
        Load configuration from file or use defaults.

        Args:
            config_path: Optional path to config file.
                        If None, uses ~/.bmlibrarian_lite/config.json

        Returns:
            Loaded configuration
        """
        if config_path is None:
            config_path = DEFAULT_DATA_DIR / "config.json"

        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                config = cls._from_dict(data)
                logger.debug(f"Loaded config from {config_path}")
                return config
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                logger.warning(f"Failed to load config from {config_path}: {e}")
                logger.info("Using default configuration")

        return cls()

    @classmethod
    def _from_dict(cls, data: dict[str, Any]) -> "LiteConfig":
        """
        Create config from dictionary.

        Args:
            data: Configuration dictionary

        Returns:
            LiteConfig instance
        """
        config = cls()

        if "llm" in data:
            llm_data = data["llm"]
            config.llm = LLMConfig(
                provider=llm_data.get("provider", DEFAULT_LLM_PROVIDER),
                model=llm_data.get("model", DEFAULT_LLM_MODEL),
                temperature=float(llm_data.get("temperature", DEFAULT_LLM_TEMPERATURE)),
                max_tokens=int(llm_data.get("max_tokens", DEFAULT_LLM_MAX_TOKENS)),
            )

        if "embeddings" in data:
            embed_data = data["embeddings"]
            cache_dir = embed_data.get("cache_dir")
            config.embeddings = EmbeddingConfig(
                model=embed_data.get("model", DEFAULT_EMBEDDING_MODEL),
                cache_dir=Path(cache_dir).expanduser() if cache_dir else None,
            )

        if "pubmed" in data:
            pubmed_data = data["pubmed"]
            config.pubmed = PubMedConfig(
                email=pubmed_data.get("email", ""),
                api_key=pubmed_data.get("api_key"),
            )

        if "discovery" in data:
            discovery_data = data["discovery"]
            config.discovery = DiscoveryConfig(
                unpaywall_email=discovery_data.get("unpaywall_email", ""),
            )

        if "openathens" in data:
            openathens_data = data["openathens"]
            config.openathens = OpenAthensConfig(
                enabled=bool(openathens_data.get("enabled", False)),
                institution_url=openathens_data.get("institution_url", ""),
                session_max_age_hours=int(openathens_data.get("session_max_age_hours", 24)),
            )

        if "storage" in data:
            storage_data = data["storage"]
            data_dir = storage_data.get("data_dir", str(DEFAULT_DATA_DIR))
            config.storage = StorageConfig(
                data_dir=Path(data_dir).expanduser(),
            )

        if "search" in data:
            search_data = data["search"]
            config.search = SearchConfig(
                chunk_size=int(search_data.get("chunk_size", DEFAULT_CHUNK_SIZE)),
                chunk_overlap=int(search_data.get("chunk_overlap", DEFAULT_CHUNK_OVERLAP)),
                similarity_threshold=float(
                    search_data.get("similarity_threshold", DEFAULT_SIMILARITY_THRESHOLD)
                ),
                max_results=int(search_data.get("max_results", DEFAULT_MAX_RESULTS)),
            )

        return config

    def to_dict(self) -> dict[str, Any]:
        """
        Convert configuration to dictionary for serialization.

        Returns:
            Configuration dictionary
        """
        return {
            "llm": {
                "provider": self.llm.provider,
                "model": self.llm.model,
                "temperature": self.llm.temperature,
                "max_tokens": self.llm.max_tokens,
            },
            "embeddings": {
                "model": self.embeddings.model,
                "cache_dir": str(self.embeddings.cache_dir) if self.embeddings.cache_dir else None,
            },
            "pubmed": {
                "email": self.pubmed.email,
                "api_key": self.pubmed.api_key,
            },
            "discovery": {
                "unpaywall_email": self.discovery.unpaywall_email,
            },
            "openathens": {
                "enabled": self.openathens.enabled,
                "institution_url": self.openathens.institution_url,
                "session_max_age_hours": self.openathens.session_max_age_hours,
            },
            "storage": {
                "data_dir": str(self.storage.data_dir),
            },
            "search": {
                "chunk_size": self.search.chunk_size,
                "chunk_overlap": self.search.chunk_overlap,
                "similarity_threshold": self.search.similarity_threshold,
                "max_results": self.search.max_results,
            },
        }

    def save(self, config_path: Optional[Path] = None) -> None:
        """
        Save configuration to file.

        The configuration file is saved with restricted permissions (600)
        to protect sensitive data like API keys.

        Args:
            config_path: Optional path to save to.
                        If None, saves to data_dir/config.json
        """
        if config_path is None:
            config_path = self.storage.data_dir / "config.json"

        # Ensure directory exists with secure permissions
        config_path.parent.mkdir(parents=True, exist_ok=True)

        # Write config
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

        # Set secure file permissions (owner read/write only)
        # This protects API keys and other sensitive configuration
        try:
            os.chmod(config_path, CONFIG_FILE_PERMISSIONS)
            logger.debug(f"Set file permissions to {oct(CONFIG_FILE_PERMISSIONS)} for {config_path}")
        except OSError as e:
            # Log but don't fail - permissions may not be settable on all filesystems
            logger.warning(f"Could not set file permissions for {config_path}: {e}")

        # Invalidate validation cache after save
        self._validation_cache.clear()

        logger.info(f"Configuration saved to {config_path}")

    def ensure_directories(self) -> None:
        """Create all required directories if they don't exist."""
        directories = [
            self.storage.data_dir,
            self.storage.chroma_dir,
            self.storage.reviews_dir,
            self.storage.exports_dir,
            self.storage.cache_dir,
        ]
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)

    def load_env(self) -> None:
        """
        Load environment variables from .env file.

        This loads API keys and other sensitive configuration that
        should not be stored in the main config file.
        """
        env_file = self.storage.env_file
        if not env_file.exists():
            return

        try:
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        key, value = line.split("=", 1)
                        os.environ[key.strip()] = value.strip()
            logger.debug(f"Loaded environment from {env_file}")
        except Exception as e:
            logger.warning(f"Failed to load .env file: {e}")

    def _compute_config_hash(self) -> str:
        """
        Compute a hash of the current configuration values.

        Used for validation caching - the cache is invalidated when
        the configuration changes.

        Returns:
            MD5 hash of the configuration dictionary
        """
        config_str = json.dumps(self.to_dict(), sort_keys=True)
        return hashlib.md5(config_str.encode()).hexdigest()

    def invalidate_validation_cache(self) -> None:
        """
        Manually invalidate the validation cache.

        Call this method to force re-validation on the next validate() call.
        The cache is also automatically invalidated when save() is called.
        """
        self._validation_cache.clear()
        logger.debug("Validation cache invalidated")

    def validate(self) -> list[str]:
        """
        Validate configuration values.

        Checks all configuration parameters for valid ranges and formats.
        Returns a list of error messages if any validation fails.

        Validation results are cached based on configuration values.
        The cache is automatically invalidated when configuration changes.

        Returns:
            List of validation error messages (empty if all valid)

        Example:
            config = LiteConfig.load()
            errors = config.validate()
            if errors:
                for error in errors:
                    print(f"Config error: {error}")
                raise ConfigurationError(f"Invalid configuration: {errors}")
        """
        # Check cache first
        config_hash = self._compute_config_hash()
        if config_hash in self._validation_cache:
            logger.debug("Returning cached validation result")
            return self._validation_cache[config_hash]

        errors: list[str] = []

        # Email validation
        if self.pubmed.email and "@" not in self.pubmed.email:
            errors.append("Invalid email format for PubMed configuration")

        # LLM temperature range (0.0 to 1.0)
        if not 0.0 <= self.llm.temperature <= 1.0:
            errors.append(
                f"LLM temperature must be between 0.0 and 1.0, got {self.llm.temperature}"
            )

        # LLM max tokens (must be positive)
        if self.llm.max_tokens < 1:
            errors.append(
                f"LLM max_tokens must be a positive integer, got {self.llm.max_tokens}"
            )

        # LLM provider validation
        valid_providers = ["anthropic", "openai", "ollama"]
        if self.llm.provider not in valid_providers:
            errors.append(
                f"LLM provider must be one of {valid_providers}, got '{self.llm.provider}'"
            )

        # Embedding model validation
        if self.embeddings.model not in EMBEDDING_MODEL_SPECS:
            valid_models = list(EMBEDDING_MODEL_SPECS.keys())
            errors.append(
                f"Embedding model must be one of {valid_models}, got '{self.embeddings.model}'"
            )

        # Chunk size validation
        if self.search.chunk_size < MIN_CHUNK_SIZE:
            errors.append(
                f"Chunk size must be >= {MIN_CHUNK_SIZE}, got {self.search.chunk_size}"
            )

        # Chunk overlap validation
        if self.search.chunk_overlap < 0:
            errors.append(
                f"Chunk overlap must be >= 0, got {self.search.chunk_overlap}"
            )

        if self.search.chunk_overlap >= self.search.chunk_size:
            errors.append(
                f"Chunk overlap ({self.search.chunk_overlap}) must be less than "
                f"chunk size ({self.search.chunk_size})"
            )

        # Similarity threshold validation (0.0 to 1.0)
        if not 0.0 <= self.search.similarity_threshold <= 1.0:
            errors.append(
                f"Similarity threshold must be between 0.0 and 1.0, "
                f"got {self.search.similarity_threshold}"
            )

        # Max results validation
        if self.search.max_results < 1:
            errors.append(
                f"Max results must be a positive integer, got {self.search.max_results}"
            )

        # Data directory validation
        if not self.storage.data_dir:
            errors.append("Data directory path cannot be empty")

        # Cache the result
        self._validation_cache[config_hash] = errors
        logger.debug(f"Cached validation result for config hash {config_hash[:8]}...")

        return errors

    def is_valid(self) -> bool:
        """
        Check if configuration is valid.

        Convenience method that returns True if no validation errors.

        Returns:
            True if configuration is valid, False otherwise

        Example:
            if not config.is_valid():
                print("Configuration is invalid, using defaults")
                config = LiteConfig()
        """
        return len(self.validate()) == 0
