"""Tests for BMLibrarian Lite embedding module."""

import pytest

from bmlibrarian.lite.embeddings import LiteEmbedder
from bmlibrarian.lite.chroma_embeddings import (
    FastEmbedFunction,
    create_embedding_function,
    get_default_embedding_function,
)
from bmlibrarian.lite.constants import DEFAULT_EMBEDDING_MODEL


def _can_load_embedding_model() -> bool:
    """Check if the embedding model can be loaded."""
    try:
        # Try to load the model - this will download if not cached
        from fastembed import TextEmbedding
        TextEmbedding(model_name=DEFAULT_EMBEDDING_MODEL)
        return True
    except Exception:
        return False


# Skip embedding tests if model cannot be downloaded (e.g., network restrictions)
# These tests require downloading the embedding model on first run
pytestmark = pytest.mark.skipif(
    not _can_load_embedding_model(),
    reason="Embedding model not available (network may be restricted)",
)


class TestLiteEmbedder:
    """Tests for LiteEmbedder class."""

    @pytest.fixture(scope="class")
    def embedder(self) -> LiteEmbedder:
        """Create embedder once for all tests (model loading is slow)."""
        return LiteEmbedder()

    def test_embedder_initialization(self, embedder: LiteEmbedder) -> None:
        """Test that embedder initializes correctly."""
        assert embedder.dimensions == 384
        assert embedder.model_name == DEFAULT_EMBEDDING_MODEL

    def test_embed_single(self, embedder: LiteEmbedder) -> None:
        """Test single text embedding."""
        embedding = embedder.embed_single("This is a test sentence about medicine.")

        assert isinstance(embedding, list)
        assert len(embedding) == 384
        assert all(isinstance(x, float) for x in embedding)

    def test_embed_multiple(self, embedder: LiteEmbedder) -> None:
        """Test multiple text embedding."""
        texts = [
            "First sentence about cardiovascular disease.",
            "Second sentence about health outcomes.",
            "Third sentence about medical research.",
        ]
        embeddings = embedder.embed(texts)

        assert len(embeddings) == 3
        assert all(len(e) == 384 for e in embeddings)
        assert all(isinstance(e, list) for e in embeddings)

    def test_embed_empty_list(self, embedder: LiteEmbedder) -> None:
        """Test embedding empty list returns empty list."""
        embeddings = embedder.embed([])
        assert embeddings == []

    def test_embed_single_empty_string(self, embedder: LiteEmbedder) -> None:
        """Test embedding empty string still returns valid embedding."""
        embedding = embedder.embed_single("")
        # FastEmbed may handle this differently, just ensure no crash
        assert isinstance(embedding, list)

    def test_embed_generator(self, embedder: LiteEmbedder) -> None:
        """Test generator-based embedding."""
        texts = ["Text one", "Text two", "Text three"]
        embeddings = list(embedder.embed_generator(texts))

        assert len(embeddings) == 3
        assert all(len(e) == 384 for e in embeddings)

    def test_list_supported_models(self) -> None:
        """Test listing supported models."""
        models = LiteEmbedder.list_supported_models()

        assert isinstance(models, list)
        assert len(models) >= 3
        assert "BAAI/bge-small-en-v1.5" in models
        assert "BAAI/bge-base-en-v1.5" in models
        assert "intfloat/multilingual-e5-small" in models

    def test_get_model_info(self) -> None:
        """Test getting model information."""
        info = LiteEmbedder.get_model_info("BAAI/bge-small-en-v1.5")

        assert isinstance(info, dict)
        assert info["dimensions"] == 384
        assert info["size_mb"] == 50
        assert "description" in info

    def test_get_model_info_unknown(self) -> None:
        """Test getting info for unknown model returns empty dict."""
        info = LiteEmbedder.get_model_info("unknown/model")
        assert info == {}

    def test_embeddings_are_normalized(self, embedder: LiteEmbedder) -> None:
        """Test that embeddings have reasonable magnitude."""
        embedding = embedder.embed_single("Test text")

        # Calculate magnitude
        import math
        magnitude = math.sqrt(sum(x * x for x in embedding))

        # BGE models typically produce normalized embeddings (magnitude ~1.0)
        assert 0.5 < magnitude < 2.0

    def test_different_texts_different_embeddings(
        self, embedder: LiteEmbedder
    ) -> None:
        """Test that different texts produce different embeddings."""
        emb1 = embedder.embed_single("Cardiovascular disease treatment")
        emb2 = embedder.embed_single("Quantum physics experiments")

        # Embeddings should be different
        assert emb1 != emb2

        # Calculate cosine similarity
        dot_product = sum(a * b for a, b in zip(emb1, emb2))
        mag1 = sum(x * x for x in emb1) ** 0.5
        mag2 = sum(x * x for x in emb2) ** 0.5
        similarity = dot_product / (mag1 * mag2)

        # Unrelated topics should have lower similarity
        assert similarity < 0.9

    def test_similar_texts_similar_embeddings(
        self, embedder: LiteEmbedder
    ) -> None:
        """Test that similar texts produce similar embeddings."""
        emb1 = embedder.embed_single("Heart disease treatment options")
        emb2 = embedder.embed_single("Cardiovascular disease therapy")

        # Calculate cosine similarity
        dot_product = sum(a * b for a, b in zip(emb1, emb2))
        mag1 = sum(x * x for x in emb1) ** 0.5
        mag2 = sum(x * x for x in emb2) ** 0.5
        similarity = dot_product / (mag1 * mag2)

        # Related topics should have higher similarity
        assert similarity > 0.5


class TestFastEmbedFunction:
    """Tests for ChromaDB embedding function."""

    @pytest.fixture(scope="class")
    def embed_fn(self) -> FastEmbedFunction:
        """Create embedding function once for all tests."""
        return create_embedding_function()

    def test_create_embedding_function(self, embed_fn: FastEmbedFunction) -> None:
        """Test creating embedding function."""
        assert embed_fn.dimensions == 384
        assert embed_fn.model_name == DEFAULT_EMBEDDING_MODEL

    def test_call_embedding_function(self, embed_fn: FastEmbedFunction) -> None:
        """Test calling embedding function with documents."""
        documents = ["Document one", "Document two"]
        embeddings = embed_fn(documents)

        assert len(embeddings) == 2
        assert all(len(e) == 384 for e in embeddings)

    def test_get_default_embedding_function_singleton(self) -> None:
        """Test that get_default_embedding_function returns singleton."""
        fn1 = get_default_embedding_function()
        fn2 = get_default_embedding_function()

        assert fn1 is fn2

    def test_create_with_custom_model(self) -> None:
        """Test creating with custom model name."""
        # This will log a warning but should still work
        embed_fn = create_embedding_function(model_name="BAAI/bge-small-en-v1.5")
        assert embed_fn.model_name == "BAAI/bge-small-en-v1.5"
