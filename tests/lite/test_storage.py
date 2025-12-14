"""Tests for BMLibrarian Lite storage layer."""

import json
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from bmlibrarian.lite.config import LiteConfig, StorageConfig
from bmlibrarian.lite.constants import DEFAULT_EMBEDDING_MODEL
from bmlibrarian.lite.data_models import DocumentSource, LiteDocument
from bmlibrarian.lite.storage import LiteStorage


def _can_load_embedding_model() -> bool:
    """Check if the embedding model can be loaded."""
    try:
        from fastembed import TextEmbedding
        TextEmbedding(model_name=DEFAULT_EMBEDDING_MODEL)
        return True
    except Exception:
        return False


# Marker for tests that require embedding model
requires_embedding = pytest.mark.skipif(
    not _can_load_embedding_model(),
    reason="Embedding model not available (network may be restricted)",
)


@pytest.fixture
def temp_storage() -> LiteStorage:
    """Create a temporary storage instance for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = LiteConfig()
        config.storage = StorageConfig(data_dir=Path(tmpdir))
        storage = LiteStorage(config)
        yield storage


@pytest.fixture
def sample_document() -> LiteDocument:
    """Create a sample document for testing."""
    return LiteDocument(
        id="test-pmid-12345",
        title="Test Document Title",
        abstract="This is a test abstract about cardiovascular disease and treatment options.",
        authors=["Smith J", "Jones A", "Brown B"],
        year=2024,
        journal="Test Journal",
        doi="10.1234/test.12345",
        pmid="12345",
        source=DocumentSource.PUBMED,
    )


class TestLiteStorageInitialization:
    """Tests for storage initialization."""

    def test_storage_initialization(self, temp_storage: LiteStorage) -> None:
        """Test that storage initializes correctly."""
        stats = temp_storage.get_statistics()
        assert stats["documents"] == 0
        assert stats["chunks"] == 0
        assert stats["search_sessions"] == 0
        assert stats["checkpoints"] == 0

    def test_directories_created(self, temp_storage: LiteStorage) -> None:
        """Test that required directories are created."""
        config = temp_storage.config
        assert config.storage.data_dir.exists()
        assert config.storage.chroma_dir.exists()
        assert config.storage.reviews_dir.exists()
        assert config.storage.exports_dir.exists()
        assert config.storage.cache_dir.exists()


@requires_embedding
class TestDocumentOperations:
    """Tests for document CRUD operations."""

    def test_add_and_get_document(
        self,
        temp_storage: LiteStorage,
        sample_document: LiteDocument,
    ) -> None:
        """Test adding and retrieving a document."""
        # Add document
        doc_id = temp_storage.add_document(sample_document)
        assert doc_id == sample_document.id

        # Retrieve document
        retrieved = temp_storage.get_document(sample_document.id)
        assert retrieved is not None
        assert retrieved.id == sample_document.id
        assert retrieved.title == sample_document.title
        assert retrieved.abstract == sample_document.abstract
        assert retrieved.authors == sample_document.authors
        assert retrieved.year == sample_document.year

    def test_add_multiple_documents(self, temp_storage: LiteStorage) -> None:
        """Test adding multiple documents at once."""
        documents = [
            LiteDocument(
                id=f"doc-{i}",
                title=f"Document {i}",
                abstract=f"Abstract for document {i}",
                source=DocumentSource.PUBMED,
            )
            for i in range(5)
        ]

        ids = temp_storage.add_documents(documents)
        assert len(ids) == 5

        stats = temp_storage.get_statistics()
        assert stats["documents"] == 5

    def test_get_nonexistent_document(self, temp_storage: LiteStorage) -> None:
        """Test retrieving a document that doesn't exist."""
        result = temp_storage.get_document("nonexistent-id")
        assert result is None

    def test_delete_document(
        self,
        temp_storage: LiteStorage,
        sample_document: LiteDocument,
    ) -> None:
        """Test deleting a document."""
        temp_storage.add_document(sample_document)

        # Verify it exists
        assert temp_storage.get_document(sample_document.id) is not None

        # Delete it
        success = temp_storage.delete_document(sample_document.id)
        assert success is True

        # Verify it's gone
        assert temp_storage.get_document(sample_document.id) is None

    def test_search_documents(self, temp_storage: LiteStorage) -> None:
        """Test semantic search (without embedding function, uses default)."""
        # Add some documents
        documents = [
            LiteDocument(
                id="doc-cardio",
                title="Cardiovascular Study",
                abstract="This study examines heart disease and cardiac function.",
                source=DocumentSource.PUBMED,
            ),
            LiteDocument(
                id="doc-neuro",
                title="Neuroscience Research",
                abstract="This paper discusses brain function and neural pathways.",
                source=DocumentSource.PUBMED,
            ),
        ]
        temp_storage.add_documents(documents)

        # Search (without embedding function, ChromaDB uses default)
        # Note: This tests the API, not semantic quality
        results = temp_storage.search_documents("heart disease", n_results=5)
        assert len(results) <= 5


class TestSearchSessionOperations:
    """Tests for search session operations."""

    def test_create_search_session(self, temp_storage: LiteStorage) -> None:
        """Test creating a search session."""
        session = temp_storage.create_search_session(
            query="cancer treatment",
            natural_language_query="What are the best cancer treatments?",
            document_count=50,
        )

        assert session.id is not None
        assert session.query == "cancer treatment"
        assert session.natural_language_query == "What are the best cancer treatments?"
        assert session.document_count == 50
        assert isinstance(session.created_at, datetime)

    def test_get_search_sessions(self, temp_storage: LiteStorage) -> None:
        """Test retrieving search sessions."""
        # Create multiple sessions
        for i in range(3):
            temp_storage.create_search_session(
                query=f"query-{i}",
                natural_language_query=f"Question {i}",
                document_count=i * 10,
            )

        sessions = temp_storage.get_search_sessions()
        assert len(sessions) == 3

        # Should be in reverse chronological order
        for i, session in enumerate(sessions):
            assert session.query == f"query-{2 - i}"

    def test_get_search_session_by_id(self, temp_storage: LiteStorage) -> None:
        """Test retrieving a specific search session."""
        session = temp_storage.create_search_session(
            query="test query",
            natural_language_query="Test question?",
            document_count=25,
        )

        retrieved = temp_storage.get_search_session(session.id)
        assert retrieved is not None
        assert retrieved.id == session.id
        assert retrieved.query == session.query


class TestCheckpointOperations:
    """Tests for checkpoint operations."""

    def test_create_checkpoint(self, temp_storage: LiteStorage) -> None:
        """Test creating a checkpoint."""
        checkpoint = temp_storage.create_checkpoint(
            research_question="What is the effect of X on Y?"
        )

        assert checkpoint.id is not None
        assert checkpoint.research_question == "What is the effect of X on Y?"
        assert checkpoint.step == "start"
        assert isinstance(checkpoint.created_at, datetime)

    def test_update_checkpoint(self, temp_storage: LiteStorage) -> None:
        """Test updating a checkpoint."""
        checkpoint = temp_storage.create_checkpoint(
            research_question="Test question?"
        )

        # Update the step
        temp_storage.update_checkpoint(checkpoint.id, step="scoring")

        # Retrieve and verify
        updated = temp_storage.get_checkpoint(checkpoint.id)
        assert updated is not None
        assert updated.step == "scoring"
        assert updated.updated_at > checkpoint.created_at

    def test_update_checkpoint_with_report(self, temp_storage: LiteStorage) -> None:
        """Test updating a checkpoint with a report."""
        checkpoint = temp_storage.create_checkpoint(
            research_question="Test question?"
        )

        report_text = "# Research Report\n\nThis is the report content."
        temp_storage.update_checkpoint(
            checkpoint.id,
            step="complete",
            report=report_text,
        )

        updated = temp_storage.get_checkpoint(checkpoint.id)
        assert updated is not None
        assert updated.report == report_text

    def test_get_recent_checkpoints(self, temp_storage: LiteStorage) -> None:
        """Test retrieving recent checkpoints."""
        for i in range(5):
            temp_storage.create_checkpoint(
                research_question=f"Question {i}?"
            )

        checkpoints = temp_storage.get_recent_checkpoints(limit=3)
        assert len(checkpoints) == 3

    def test_delete_checkpoint(self, temp_storage: LiteStorage) -> None:
        """Test deleting a checkpoint."""
        checkpoint = temp_storage.create_checkpoint(
            research_question="To be deleted"
        )

        success = temp_storage.delete_checkpoint(checkpoint.id)
        assert success is True

        # Verify it's gone
        assert temp_storage.get_checkpoint(checkpoint.id) is None


class TestCacheOperations:
    """Tests for PubMed cache operations."""

    def test_cache_and_retrieve(self, temp_storage: LiteStorage) -> None:
        """Test caching and retrieving a PubMed response."""
        query_hash = "abc123"
        response = json.dumps({"pmids": [1, 2, 3]})

        # Cache the response
        temp_storage.cache_pubmed_response(query_hash, response)

        # Retrieve it
        cached = temp_storage.get_cached_pubmed_response(query_hash)
        assert cached == response

    def test_cache_expiry(self, temp_storage: LiteStorage) -> None:
        """Test that expired cache entries are not returned."""
        query_hash = "expired123"
        response = json.dumps({"pmids": []})

        # Cache with 0 TTL (expires immediately)
        temp_storage.cache_pubmed_response(query_hash, response, ttl_seconds=0)

        # Should not be returned (expired)
        cached = temp_storage.get_cached_pubmed_response(query_hash)
        assert cached is None

    def test_clear_expired_cache(self, temp_storage: LiteStorage) -> None:
        """Test clearing expired cache entries."""
        # Add an expired entry
        temp_storage.cache_pubmed_response("expired", "data", ttl_seconds=0)

        # Clear expired
        count = temp_storage.clear_expired_cache()
        assert count >= 1


class TestUtilityMethods:
    """Tests for utility methods."""

    @requires_embedding
    def test_get_statistics(self, temp_storage: LiteStorage) -> None:
        """Test getting storage statistics."""
        # Add some data
        temp_storage.add_document(LiteDocument(
            id="doc-1",
            title="Test",
            abstract="Test abstract",
            source=DocumentSource.PUBMED,
        ))
        temp_storage.create_search_session(
            query="test",
            natural_language_query="test?",
        )

        stats = temp_storage.get_statistics()
        assert stats["documents"] == 1
        assert stats["search_sessions"] == 1
        assert "data_dir" in stats

    def test_clear_all_requires_confirmation(self, temp_storage: LiteStorage) -> None:
        """Test that clear_all requires confirmation."""
        with pytest.raises(ValueError, match="confirm=True"):
            temp_storage.clear_all()

    @requires_embedding
    def test_clear_all_with_confirmation(self, temp_storage: LiteStorage) -> None:
        """Test clearing all data with confirmation."""
        # Add some data
        temp_storage.add_document(LiteDocument(
            id="doc-1",
            title="Test",
            abstract="Test abstract",
            source=DocumentSource.PUBMED,
        ))
        temp_storage.create_checkpoint(research_question="Test?")

        # Clear with confirmation
        temp_storage.clear_all(confirm=True)

        # Verify everything is cleared
        stats = temp_storage.get_statistics()
        assert stats["documents"] == 0
        assert stats["checkpoints"] == 0
