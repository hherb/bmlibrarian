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
import json
import logging
import os

from .constants import (
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
    """

    llm: LLMConfig = field(default_factory=LLMConfig)
    embeddings: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    pubmed: PubMedConfig = field(default_factory=PubMedConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    search: SearchConfig = field(default_factory=SearchConfig)

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

        Args:
            config_path: Optional path to save to.
                        If None, saves to data_dir/config.json
        """
        if config_path is None:
            config_path = self.storage.data_dir / "config.json"

        # Ensure directory exists
        config_path.parent.mkdir(parents=True, exist_ok=True)

        # Write config
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

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
