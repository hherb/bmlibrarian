"""Tests for BMLibrarian Lite configuration."""

import json
import tempfile
from pathlib import Path

import pytest

from bmlibrarian.lite.config import (
    EmbeddingConfig,
    LiteConfig,
    LLMConfig,
    PubMedConfig,
    SearchConfig,
    StorageConfig,
)
from bmlibrarian.lite.constants import (
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_CHUNK_SIZE,
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_LLM_MODEL,
    DEFAULT_LLM_PROVIDER,
)


class TestLLMConfig:
    """Tests for LLMConfig dataclass."""

    def test_default_values(self) -> None:
        """Test default values are set correctly."""
        config = LLMConfig()
        assert config.provider == DEFAULT_LLM_PROVIDER
        assert config.model == DEFAULT_LLM_MODEL
        assert config.temperature == 0.3
        assert config.max_tokens == 4096


class TestEmbeddingConfig:
    """Tests for EmbeddingConfig dataclass."""

    def test_default_values(self) -> None:
        """Test default values are set correctly."""
        config = EmbeddingConfig()
        assert config.model == DEFAULT_EMBEDDING_MODEL
        assert config.cache_dir is None


class TestStorageConfig:
    """Tests for StorageConfig dataclass."""

    def test_derived_paths(self) -> None:
        """Test that derived paths are calculated correctly."""
        config = StorageConfig(data_dir=Path("/test/data"))

        assert config.chroma_dir == Path("/test/data/chroma_db")
        assert config.sqlite_path == Path("/test/data/metadata.db")
        assert config.reviews_dir == Path("/test/data/reviews")
        assert config.exports_dir == Path("/test/data/exports")
        assert config.cache_dir == Path("/test/data/cache")
        assert config.env_file == Path("/test/data/.env")


class TestSearchConfig:
    """Tests for SearchConfig dataclass."""

    def test_default_values(self) -> None:
        """Test default values are set correctly."""
        config = SearchConfig()
        assert config.chunk_size == DEFAULT_CHUNK_SIZE
        assert config.chunk_overlap == DEFAULT_CHUNK_OVERLAP
        assert config.similarity_threshold == 0.5
        assert config.max_results == 20


class TestLiteConfig:
    """Tests for main LiteConfig class."""

    def test_default_initialization(self) -> None:
        """Test that LiteConfig initializes with defaults."""
        config = LiteConfig()

        assert isinstance(config.llm, LLMConfig)
        assert isinstance(config.embeddings, EmbeddingConfig)
        assert isinstance(config.pubmed, PubMedConfig)
        assert isinstance(config.storage, StorageConfig)
        assert isinstance(config.search, SearchConfig)

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        config = LiteConfig()
        data = config.to_dict()

        assert "llm" in data
        assert "embeddings" in data
        assert "pubmed" in data
        assert "storage" in data
        assert "search" in data

        assert data["llm"]["provider"] == DEFAULT_LLM_PROVIDER
        assert data["embeddings"]["model"] == DEFAULT_EMBEDDING_MODEL

    def test_save_and_load(self) -> None:
        """Test saving and loading configuration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"

            # Create and modify config
            config = LiteConfig()
            config.llm.model = "test-model"
            config.pubmed.email = "test@example.com"
            config.storage = StorageConfig(data_dir=Path(tmpdir))

            # Save
            config.save(config_path)
            assert config_path.exists()

            # Load
            loaded = LiteConfig.load(config_path)
            assert loaded.llm.model == "test-model"
            assert loaded.pubmed.email == "test@example.com"

    def test_load_nonexistent_file(self) -> None:
        """Test loading from nonexistent file returns defaults."""
        config = LiteConfig.load(Path("/nonexistent/config.json"))

        # Should return defaults
        assert config.llm.provider == DEFAULT_LLM_PROVIDER
        assert config.embeddings.model == DEFAULT_EMBEDDING_MODEL

    def test_load_invalid_json(self) -> None:
        """Test loading invalid JSON file returns defaults."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"

            # Write invalid JSON
            config_path.write_text("not valid json {{{")

            # Should return defaults
            config = LiteConfig.load(config_path)
            assert config.llm.provider == DEFAULT_LLM_PROVIDER

    def test_from_dict(self) -> None:
        """Test creating config from dictionary."""
        data = {
            "llm": {
                "provider": "anthropic",
                "model": "claude-3-opus",
                "temperature": 0.5,
                "max_tokens": 8192,
            },
            "embeddings": {
                "model": "BAAI/bge-base-en-v1.5",
            },
            "pubmed": {
                "email": "user@example.com",
                "api_key": "abc123",
            },
            "storage": {
                "data_dir": "/custom/path",
            },
            "search": {
                "chunk_size": 5000,
                "chunk_overlap": 100,
            },
        }

        config = LiteConfig._from_dict(data)

        assert config.llm.model == "claude-3-opus"
        assert config.llm.temperature == 0.5
        assert config.embeddings.model == "BAAI/bge-base-en-v1.5"
        assert config.pubmed.email == "user@example.com"
        assert config.pubmed.api_key == "abc123"
        assert config.storage.data_dir == Path("/custom/path")
        assert config.search.chunk_size == 5000

    def test_ensure_directories(self) -> None:
        """Test that ensure_directories creates required directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = LiteConfig()
            config.storage = StorageConfig(data_dir=Path(tmpdir) / "new_dir")

            config.ensure_directories()

            assert config.storage.data_dir.exists()
            assert config.storage.chroma_dir.exists()
            assert config.storage.reviews_dir.exists()
            assert config.storage.exports_dir.exists()
            assert config.storage.cache_dir.exists()

    def test_partial_config_loading(self) -> None:
        """Test loading config with only some fields specified."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"

            # Write partial config
            partial_data = {
                "llm": {
                    "model": "custom-model",
                }
            }
            config_path.write_text(json.dumps(partial_data))

            # Load - should have custom model but default other values
            config = LiteConfig.load(config_path)
            assert config.llm.model == "custom-model"
            assert config.llm.provider == DEFAULT_LLM_PROVIDER  # Default
            assert config.embeddings.model == DEFAULT_EMBEDDING_MODEL  # Default
