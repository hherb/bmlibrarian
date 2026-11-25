"""
Tests for Document Embedder

These tests verify the basic functionality of the document embedder module.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from src.bmlibrarian.embeddings.document_embedder import DocumentEmbedder


class TestDocumentEmbedder:
    """Test cases for DocumentEmbedder class."""

    @patch('src.bmlibrarian.embeddings.document_embedder.LLMClient')
    @patch('src.bmlibrarian.embeddings.document_embedder.list_ollama_models')
    @patch('src.bmlibrarian.embeddings.document_embedder.get_db_manager')
    def test_create_embedding(self, mock_db, mock_list_models, mock_llm_client):
        """Test embedding creation."""
        # Mock Ollama response
        mock_list_models.return_value = ['test-model:latest']
        mock_llm_client.return_value.embed.return_value = Mock(
            embedding=[0.1] * 768
        )

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
        mock_llm_client.return_value.embed.assert_called_once()

    @patch('src.bmlibrarian.embeddings.document_embedder.LLMClient')
    @patch('src.bmlibrarian.embeddings.document_embedder.list_ollama_models')
    @patch('src.bmlibrarian.embeddings.document_embedder.get_db_manager')
    def test_model_registration(self, mock_db, mock_list_models, mock_llm_client):
        """Test that model is properly registered."""
        mock_list_models.return_value = ['test-model:latest']

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

    @patch('src.bmlibrarian.embeddings.document_embedder.LLMClient')
    @patch('src.bmlibrarian.embeddings.document_embedder.list_ollama_models')
    @patch('src.bmlibrarian.embeddings.document_embedder.get_db_manager')
    def test_count_documents_without_embeddings(self, mock_db, mock_list_models, mock_llm_client):
        """Test counting documents without embeddings."""
        mock_list_models.return_value = ['test-model:latest']

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

    @patch('src.bmlibrarian.embeddings.document_embedder.LLMClient')
    @patch('src.bmlibrarian.embeddings.document_embedder.list_ollama_models')
    @patch('src.bmlibrarian.embeddings.document_embedder.get_db_manager')
    def test_embedding_dimension_detection(self, mock_db, mock_list_models, mock_llm_client):
        """Test that embedding dimension is correctly detected."""
        mock_list_models.return_value = ['test-model:latest']

        # Return different dimension
        mock_llm_client.return_value.embed.return_value = Mock(
            embedding=[0.1] * 1024
        )

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


class TestEmbedDocumentsPaging:
    """embed_documents pages through candidates instead of loading them all (#442)."""

    @staticmethod
    def _embedder(pages):
        """Build a DocumentEmbedder without a database, fed from ``pages``."""
        embedder = DocumentEmbedder.__new__(DocumentEmbedder)
        calls = []

        def fake_get(source_name=None, limit=None, after_id=0):
            calls.append((limit, after_id))
            return pages.pop(0) if pages else []

        embedder._get_documents_without_embeddings = fake_get
        embedder.create_embedding = lambda text: [0.1] * 4
        embedder._store_chunk_and_embedding = lambda *args: 7
        return embedder, calls

    @staticmethod
    def _docs(*ids):
        return [{'id': i, 'title': f't{i}', 'abstract': f'a{i}'} for i in ids]

    def test_pages_by_last_id_until_empty(self):
        embedder, calls = self._embedder([self._docs(1, 2), self._docs(5, 9), []])
        stats = embedder.embed_documents(batch_size=2)
        assert calls == [(2, 0), (2, 2), (2, 9)]
        assert stats == {'total_processed': 4, 'embedded_count': 4, 'failed_count': 0}

    def test_limit_shrinks_last_page(self):
        embedder, calls = self._embedder([self._docs(1, 2), self._docs(3)])
        stats = embedder.embed_documents(limit=3, batch_size=2)
        assert calls == [(2, 0), (1, 2)]
        assert stats['total_processed'] == 3

    def test_failed_document_is_counted_and_skipped(self):
        embedder, calls = self._embedder([self._docs(1, 2), []])
        embedder.create_embedding = lambda text: [] if text == 'a1' else [0.1]
        stats = embedder.embed_documents(batch_size=2)
        assert stats == {'total_processed': 2, 'embedded_count': 1, 'failed_count': 1}

    def test_query_has_no_full_text_and_uses_keyset(self):
        embedder = DocumentEmbedder.__new__(DocumentEmbedder)
        embedder.model_id = 3
        cursor = MagicMock()
        cursor.description = [('id',), ('title',), ('abstract',), ('source_name',)]
        cursor.fetchall.return_value = [(4, 't', 'a', 'pubmed')]
        conn = MagicMock()
        conn.cursor.return_value.__enter__.return_value = cursor
        embedder.db_manager = MagicMock()
        embedder.db_manager.get_connection.return_value.__enter__.return_value = conn

        rows = embedder._get_documents_without_embeddings('PubMed', 50, after_id=10)

        sql, params = cursor.execute.call_args[0]
        assert 'full_text' not in sql
        assert 'd.id > %s' in sql
        assert params == (3, 10, '%pubmed%', 50)
        assert rows == [{'id': 4, 'title': 't', 'abstract': 'a', 'source_name': 'pubmed'}]

    def test_rejects_zero_batch_size(self):
        embedder, _ = self._embedder([])
        with pytest.raises(ValueError):
            embedder.embed_documents(batch_size=0)


def test_module_constants():
    """Test that module can be imported."""
    from src.bmlibrarian.embeddings import DocumentEmbedder
    assert DocumentEmbedder is not None


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
