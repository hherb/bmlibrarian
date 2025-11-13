"""
Tests for Document Embedder

These tests verify the basic functionality of the document embedder module.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from src.bmlibrarian.embeddings.document_embedder import DocumentEmbedder


class TestDocumentEmbedder:
    """Test cases for DocumentEmbedder class."""

    @patch('src.bmlibrarian.embeddings.document_embedder.ollama')
    @patch('src.bmlibrarian.embeddings.document_embedder.get_db_manager')
    def test_create_embedding(self, mock_db, mock_ollama):
        """Test embedding creation."""
        # Mock Ollama response
        mock_ollama.list.return_value = {
            'models': [{'model': 'test-model:latest'}]
        }
        mock_ollama.embeddings.return_value = {
            'embedding': [0.1] * 768
        }

        # Mock database operations
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_db.return_value.get_connection.return_value.__enter__.return_value = mock_conn

        # Mock database queries
        mock_cursor.fetchone.side_effect = [
            (1,),  # model_id
            (1,),  # provider_id
            (1,),  # chunking_strategy_id
            (1,)   # chunktype_id
        ]

        embedder = DocumentEmbedder(model_name='test-model:latest')

        # Test embedding creation
        text = "This is a test abstract."
        embedding = embedder.create_embedding(text)

        assert len(embedding) == 768
        assert embedder.embedding_dimension == 768
        mock_ollama.embeddings.assert_called_once()

    @patch('src.bmlibrarian.embeddings.document_embedder.ollama')
    @patch('src.bmlibrarian.embeddings.document_embedder.get_db_manager')
    def test_model_registration(self, mock_db, mock_ollama):
        """Test that model is properly registered."""
        mock_ollama.list.return_value = {
            'models': [{'model': 'test-model:latest'}]
        }

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_db.return_value.get_connection.return_value.__enter__.return_value = mock_conn

        # Mock that model doesn't exist
        mock_cursor.fetchone.side_effect = [
            None,  # Model doesn't exist
            (1,),  # Provider ID
            (2,),  # New model ID
            (1,),  # chunking_strategy_id
            (1,)   # chunktype_id
        ]

        embedder = DocumentEmbedder(model_name='test-model:latest')

        assert embedder.model_id == 2

    @patch('src.bmlibrarian.embeddings.document_embedder.ollama')
    @patch('src.bmlibrarian.embeddings.document_embedder.get_db_manager')
    def test_count_documents_without_embeddings(self, mock_db, mock_ollama):
        """Test counting documents without embeddings."""
        mock_ollama.list.return_value = {
            'models': [{'model': 'test-model:latest'}]
        }

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_db.return_value.get_connection.return_value.__enter__.return_value = mock_conn

        # Mock database queries - include one for count
        mock_cursor.fetchone.side_effect = [
            (1,),    # model_id
            (1,),    # chunking_strategy_id
            (1,),    # chunktype_id
            (42,)    # count result
        ]

        embedder = DocumentEmbedder(model_name='test-model:latest')
        count = embedder.count_documents_without_embeddings(source_name='medrxiv')

        assert count == 42

    @patch('src.bmlibrarian.embeddings.document_embedder.ollama')
    @patch('src.bmlibrarian.embeddings.document_embedder.get_db_manager')
    def test_embedding_dimension_detection(self, mock_db, mock_ollama):
        """Test that embedding dimension is correctly detected."""
        mock_ollama.list.return_value = {
            'models': [{'model': 'test-model:latest'}]
        }

        # Return different dimension
        mock_ollama.embeddings.return_value = {
            'embedding': [0.1] * 1024
        }

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_db.return_value.get_connection.return_value.__enter__.return_value = mock_conn

        mock_cursor.fetchone.side_effect = [
            (1,),  # model_id
            (1,),  # chunking_strategy_id
            (1,)   # chunktype_id
        ]

        embedder = DocumentEmbedder(model_name='test-model:latest')

        # Create first embedding
        embedding = embedder.create_embedding("Test text")

        assert embedder.embedding_dimension == 1024
        assert len(embedding) == 1024


def test_module_constants():
    """Test that module can be imported."""
    from src.bmlibrarian.embeddings import DocumentEmbedder
    assert DocumentEmbedder is not None


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
