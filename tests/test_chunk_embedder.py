"""
Tests for chunk embedder module.

Tests the ChunkPosition dataclass and chunk_text function for proper
character-based text splitting with configurable overlap.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from bmlibrarian.embeddings.chunk_embedder import (
    ChunkEmbedder,
    ChunkPosition,
    chunk_text,
    DEFAULT_CHUNK_SIZE,
    DEFAULT_CHUNK_OVERLAP,
)


class TestChunkPosition:
    """Test ChunkPosition dataclass."""

    def test_chunk_position_creation(self) -> None:
        """Test creating a ChunkPosition."""
        pos = ChunkPosition(chunk_no=0, start_pos=0, end_pos=99)

        assert pos.chunk_no == 0
        assert pos.start_pos == 0
        assert pos.end_pos == 99
        assert pos.length == 100

    def test_chunk_position_length_property(self) -> None:
        """Test ChunkPosition.length property."""
        pos = ChunkPosition(chunk_no=0, start_pos=50, end_pos=149)
        assert pos.length == 100

    def test_extract_text(self) -> None:
        """Test extracting text from source using positions."""
        source = "ABCDEFGHIJ" * 10  # 100 characters
        pos = ChunkPosition(chunk_no=0, start_pos=0, end_pos=9)

        extracted = pos.extract_text(source)
        assert extracted == "ABCDEFGHIJ"

    def test_extract_text_middle(self) -> None:
        """Test extracting text from middle of source."""
        source = "0123456789" * 10
        pos = ChunkPosition(chunk_no=1, start_pos=30, end_pos=39)

        extracted = pos.extract_text(source)
        assert extracted == "0123456789"


class TestChunkText:
    """Test chunk_text pure function."""

    def test_default_parameters(self) -> None:
        """
        Test that the chunking defaults are coherent.

        This asserted 350/50 — the values when it was written. They were
        retuned deliberately since (1800/320, then 1000/100 in 2995951,
        "smaller chunks provide better semantic granularity"), and the
        test was never updated, so it has been failing rather than
        guarding anything.

        Pinning the exact numbers again would just restate the source and
        re-break on the next tuning pass. What actually matters is the
        relationship: overlap has to be a real but minor fraction of the
        chunk, or chunks either lose continuity or duplicate wholesale.
        """
        assert DEFAULT_CHUNK_SIZE > 0
        assert 0 < DEFAULT_CHUNK_OVERLAP < DEFAULT_CHUNK_SIZE // 2

    def test_empty_text(self) -> None:
        """Test chunking empty text returns empty list."""
        chunks = chunk_text("", chunk_size=100, overlap=20)
        assert chunks == []

    def test_short_text(self) -> None:
        """Test chunking text shorter than chunk_size."""
        text = "Short text"
        chunks = chunk_text(text, chunk_size=100, overlap=20)

        assert len(chunks) == 1
        assert chunks[0].chunk_no == 0
        assert chunks[0].start_pos == 0
        assert chunks[0].end_pos == len(text) - 1
        assert chunks[0].extract_text(text) == text

    def test_exact_chunk_size(self) -> None:
        """Test text exactly equal to chunk_size."""
        text = "A" * 100
        chunks = chunk_text(text, chunk_size=100, overlap=20)

        assert len(chunks) == 1
        assert chunks[0].length == 100

    def test_two_chunks_needed(self) -> None:
        """Test text that requires two chunks."""
        text = "A" * 150
        chunks = chunk_text(text, chunk_size=100, overlap=20)

        assert len(chunks) == 2

        # First chunk: positions 0-99
        assert chunks[0].chunk_no == 0
        assert chunks[0].start_pos == 0
        assert chunks[0].end_pos == 99
        assert chunks[0].length == 100

        # Second chunk: starts at 80 (100 - 20 overlap)
        assert chunks[1].chunk_no == 1
        assert chunks[1].start_pos == 80
        assert chunks[1].end_pos == 149
        assert chunks[1].length == 70

    def test_overlap_correct(self) -> None:
        """Test that overlap between chunks is correct."""
        text = "0123456789" * 20  # 200 characters
        chunks = chunk_text(text, chunk_size=100, overlap=20)

        assert len(chunks) >= 2

        # Verify overlap content matches
        first_chunk_end = chunks[0].extract_text(text)[-20:]
        second_chunk_start = chunks[1].extract_text(text)[:20]
        assert first_chunk_end == second_chunk_start

    def test_multiple_chunks(self) -> None:
        """Test text that requires multiple chunks."""
        text = "A" * 350
        chunks = chunk_text(text, chunk_size=100, overlap=20)

        # Should have several chunks
        assert len(chunks) >= 3

        # Verify chunk numbers are sequential
        for i, chunk in enumerate(chunks):
            assert chunk.chunk_no == i

        # Verify positions progress
        for i in range(len(chunks) - 1):
            assert chunks[i + 1].start_pos > chunks[i].start_pos

    def test_zero_overlap(self) -> None:
        """Test chunking with zero overlap."""
        text = "A" * 200
        chunks = chunk_text(text, chunk_size=100, overlap=0)

        assert len(chunks) == 2
        assert chunks[0].start_pos == 0
        assert chunks[0].end_pos == 99
        assert chunks[1].start_pos == 100
        assert chunks[1].end_pos == 199

    def test_invalid_chunk_size(self) -> None:
        """Test that invalid chunk_size raises ValueError."""
        with pytest.raises(ValueError, match="chunk_size must be positive"):
            chunk_text("test", chunk_size=0, overlap=0)

        with pytest.raises(ValueError, match="chunk_size must be positive"):
            chunk_text("test", chunk_size=-10, overlap=0)

    def test_invalid_overlap_negative(self) -> None:
        """Test that negative overlap raises ValueError."""
        with pytest.raises(ValueError, match="overlap cannot be negative"):
            chunk_text("test", chunk_size=100, overlap=-5)

    def test_invalid_overlap_exceeds_chunk_size(self) -> None:
        """Test that overlap >= chunk_size raises ValueError."""
        with pytest.raises(ValueError, match="overlap .* must be less than chunk_size"):
            chunk_text("test", chunk_size=100, overlap=100)

        with pytest.raises(ValueError, match="overlap .* must be less than chunk_size"):
            chunk_text("test", chunk_size=100, overlap=150)

    def test_preserves_content(self) -> None:
        """Test that all content can be reconstructed from chunks."""
        text = "ABCDEFGHIJ" * 50  # 500 chars
        chunks = chunk_text(text, chunk_size=100, overlap=20)

        # Reconstruct non-overlapping parts
        reconstructed_parts = []
        for i, chunk in enumerate(chunks):
            chunk_text_content = chunk.extract_text(text)
            if i == 0:
                reconstructed_parts.append(chunk_text_content)
            else:
                # Skip overlap portion
                reconstructed_parts.append(chunk_text_content[20:])

        reconstructed = ''.join(reconstructed_parts)
        assert reconstructed == text

    def test_unicode_text(self) -> None:
        """Test chunking handles Unicode correctly."""
        text = "Hello 世界! " * 50
        chunks = chunk_text(text, chunk_size=100, overlap=20)

        # Verify all chunks have valid content
        for chunk in chunks:
            extracted = chunk.extract_text(text)
            assert len(extracted) > 0

    def test_small_final_chunk_handling(self) -> None:
        """Test that very small final chunks are avoided."""
        # With chunk_size=100, overlap=20, step=80
        # Text of 175 chars would naively create a 15-char final chunk
        # Our algorithm should avoid this if it's smaller than overlap
        text = "A" * 175
        chunks = chunk_text(text, chunk_size=100, overlap=20)

        # All chunks should be at least overlap size (or we stop before tiny chunks)
        for chunk in chunks:
            # Last chunk might be smaller, but not tiny
            if chunk.chunk_no == len(chunks) - 1:
                assert chunk.length >= 20 or chunk.length >= (175 - chunks[-2].end_pos - 1)


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_very_small_chunks(self) -> None:
        """Test with very small chunk size."""
        text = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        chunks = chunk_text(text, chunk_size=10, overlap=2)

        assert len(chunks) > 2
        for chunk in chunks:
            assert chunk.length <= 10

    def test_large_overlap(self) -> None:
        """Test with large overlap (but still valid)."""
        text = "A" * 300
        chunks = chunk_text(text, chunk_size=100, overlap=90)

        # With 90% overlap, stride is only 10, so many chunks
        assert len(chunks) > 20

    def test_whitespace_preservation(self) -> None:
        """Test that whitespace is preserved."""
        text = "Line 1\n\nLine 2\n\nLine 3"
        chunks = chunk_text(text, chunk_size=50, overlap=10)

        # Verify whitespace is in chunks
        all_content = ''.join(chunk.extract_text(text) for chunk in chunks)
        assert '\n\n' in all_content

    def test_single_character_text(self) -> None:
        """Test single character text."""
        text = "X"
        chunks = chunk_text(text, chunk_size=100, overlap=20)

        assert len(chunks) == 1
        assert chunks[0].extract_text(text) == "X"


class TestBatchEmbeddingCallsTheLlmLayer:
    """
    Cover the ollama backend's batch path.

    The rest of this module exercises pure chunking functions and never
    constructs a ChunkEmbedder. That gap let a stale `if ollama is None`
    guard survive the migration onto the LLM abstraction: the module no
    longer imports ollama, so the check raised NameError before its own
    try block, taking out the whole semantic chunking pipeline on its
    first batch. These tests instantiate the embedder so the batch path
    is executed at least once.
    """

    @staticmethod
    def _embedder() -> ChunkEmbedder:
        """Build a ChunkEmbedder with its collaborators stubbed out."""
        embedder = ChunkEmbedder.__new__(ChunkEmbedder)
        embedder.backend = "ollama"
        embedder.model_name = "snowflake-arctic-embed2:latest"
        embedder._llm_client = MagicMock()
        return embedder

    def test_batch_embedding_returns_one_vector_per_text(self) -> None:
        """The batch path runs and preserves input order."""
        embedder = self._embedder()
        embedder._llm_client.embed_batch.return_value = SimpleNamespace(
            embeddings=[[0.1, 0.2], [0.3, 0.4]],
        )

        result = embedder._create_embeddings_batch_ollama(["first", "second"], 1)

        assert result == [[0.1, 0.2], [0.3, 0.4]]

    def test_batch_embedding_keeps_empty_texts_aligned(self) -> None:
        """An empty input yields None in place, not a shifted vector."""
        embedder = self._embedder()
        embedder._llm_client.embed_batch.return_value = SimpleNamespace(
            embeddings=[[0.1, 0.2]],
        )

        result = embedder._create_embeddings_batch_ollama(["", "second"], 1)

        assert result == [None, [0.1, 0.2]]


class TestChunkAndEmbedKeepsOldChunksOnFailure:
    """Issue #435: a failed embed or store must not cost the stored chunks."""

    @staticmethod
    def _embedder(embeddings: list) -> tuple:
        """An embedder over a mock database whose three chunks embed as given."""
        embedder = ChunkEmbedder.__new__(ChunkEmbedder)
        embedder.model_id = 4
        embedder.db_manager = MagicMock()
        embedder.get_document_full_text = MagicMock(return_value="text")
        embedder.create_embeddings_batch = MagicMock(return_value=embeddings)
        conn = embedder.db_manager.get_connection.return_value.__enter__.return_value
        cursor = conn.cursor.return_value.__enter__.return_value
        return embedder, conn, cursor

    @staticmethod
    def _positions() -> list:
        """Three chunk positions."""
        return [SimpleNamespace(chunk_no=n, start_pos=n, end_pos=n + 1, text=f"c{n}")
                for n in range(3)]

    @staticmethod
    def _statements(cursor: MagicMock) -> list:
        """The SQL texts the cursor executed, in order."""
        return [c.args[0] for c in cursor.execute.call_args_list]

    def _stored(self) -> list:
        """Stored rows whose positions match ``_positions`` (unchanged text)."""
        return [(p.chunk_no, p.start_pos, p.end_pos) for p in self._positions()]

    def test_missing_embedding_keeps_matching_chunks(self, monkeypatch) -> None:
        """One chunk without an embedding: old chunks that fit the text survive."""
        from bmlibrarian.embeddings import chunk_embedder

        monkeypatch.setattr(chunk_embedder, "adaptive_chunker_with_positions",
                            lambda *a, **k: self._positions())
        embedder, conn, cursor = self._embedder([[0.1], None, [0.3]])
        cursor.fetchall.return_value = self._stored()

        with pytest.raises(chunk_embedder.ChunkEmbeddingError,
                           match="1 of 3.*existing chunks kept"):
            embedder.chunk_and_embed(1, batch_size=10)
        statements = self._statements(cursor)
        assert len(statements) == 1 and "SELECT chunk_no" in statements[0]
        conn.transaction.assert_not_called()

    def test_missing_embedding_removes_chunks_of_older_text(self, monkeypatch) -> None:
        """Old chunks whose offsets no longer fit the changed text are deleted."""
        from bmlibrarian.embeddings import chunk_embedder

        monkeypatch.setattr(chunk_embedder, "adaptive_chunker_with_positions",
                            lambda *a, **k: self._positions())
        embedder, _, cursor = self._embedder([[0.1], None, [0.3]])
        cursor.fetchall.return_value = [(0, 0, 40), (1, 30, 80)]
        cursor.fetchone.return_value = (2,)

        with pytest.raises(chunk_embedder.ChunkEmbeddingError, match="stale chunks"):
            embedder.chunk_and_embed(1)
        assert "delete_chunks" in self._statements(cursor)[-1]

    def test_short_embedding_list_counts_as_missing(self, monkeypatch) -> None:
        """A batch answer with fewer vectors than chunks fails the document."""
        from bmlibrarian.embeddings import chunk_embedder

        monkeypatch.setattr(chunk_embedder, "adaptive_chunker_with_positions",
                            lambda *a, **k: self._positions())
        embedder, conn, cursor = self._embedder([[0.1], [0.2]])
        cursor.fetchall.return_value = []

        with pytest.raises(chunk_embedder.ChunkEmbeddingError,
                           match="1 of 3.*no chunks stored"):
            embedder.chunk_and_embed(1)
        conn.transaction.assert_not_called()

    def test_batches_are_accumulated_in_order(self, monkeypatch) -> None:
        """With batch_size=1 each chunk is inserted with its own vector."""
        from bmlibrarian.embeddings import chunk_embedder

        monkeypatch.setattr(chunk_embedder, "adaptive_chunker_with_positions",
                            lambda *a, **k: self._positions())
        embedder, _, cursor = self._embedder([])
        embedder.create_embeddings_batch = MagicMock(
            side_effect=[[[0.1]], [[0.2]], [[0.3]]])

        assert embedder.chunk_and_embed(1, batch_size=1) == 3
        assert embedder.create_embeddings_batch.call_count == 3
        inserted = [c.args[1][-1] for c in cursor.execute.call_args_list[1:]]
        assert inserted == ["[0.1]", "[0.2]", "[0.3]"]

    def test_no_overwrite_skips_a_document_with_chunks(self) -> None:
        """overwrite=False returns 0 without embedding when chunks exist."""
        embedder, _, _ = self._embedder([[0.1]] * 3)
        embedder.has_chunks = MagicMock(return_value=True)

        assert embedder.chunk_and_embed(1, overwrite=False) == 0
        embedder.create_embeddings_batch.assert_not_called()

    def test_no_overwrite_inserts_without_deleting(self, monkeypatch) -> None:
        """overwrite=False on an unchunked document only inserts."""
        from bmlibrarian.embeddings import chunk_embedder

        monkeypatch.setattr(chunk_embedder, "adaptive_chunker_with_positions",
                            lambda *a, **k: self._positions())
        embedder, _, cursor = self._embedder([[0.1]] * 3)
        embedder.has_chunks = MagicMock(return_value=False)

        assert embedder.chunk_and_embed(1, overwrite=False) == 3
        statements = self._statements(cursor)
        assert len(statements) == 3
        assert all("INSERT INTO semantic.chunks" in s for s in statements)

    def test_insert_failure_raises_out_of_the_transaction(self, monkeypatch) -> None:
        """A failed insert escapes the single transaction, so it rolls back."""
        from bmlibrarian.embeddings import chunk_embedder

        monkeypatch.setattr(chunk_embedder, "adaptive_chunker_with_positions",
                            lambda *a, **k: self._positions())
        embedder, conn, cursor = self._embedder([[0.1]] * 3)
        cursor.execute.side_effect = [None, RuntimeError("insert failed"), None]
        cursor.fetchall.return_value = self._stored()

        with pytest.raises(chunk_embedder.ChunkEmbeddingError,
                           match="storing 3 chunks failed.*existing chunks kept"):
            embedder.chunk_and_embed(1)
        exit_args = conn.transaction.return_value.__exit__.call_args.args
        assert exit_args[0] is RuntimeError  # the transaction saw the error

    def test_success_deletes_then_inserts_in_one_transaction(self, monkeypatch) -> None:
        """Delete and all inserts share one transaction; the count is returned."""
        from bmlibrarian.embeddings import chunk_embedder

        monkeypatch.setattr(chunk_embedder, "adaptive_chunker_with_positions",
                            lambda *a, **k: self._positions())
        embedder, conn, cursor = self._embedder([[0.1]] * 3)

        assert embedder.chunk_and_embed(1) == 3
        assert conn.transaction.call_count == 1
        statements = [c.args[0] for c in cursor.execute.call_args_list]
        assert "delete_chunks" in statements[0]
        assert all("INSERT INTO semantic.chunks" in s for s in statements[1:])
        assert len(statements) == 4

    def test_process_queue_keeps_a_failed_document_queued(self) -> None:
        """A ChunkEmbeddingError records the error instead of dequeuing."""
        from bmlibrarian.embeddings import chunk_embedder

        embedder, _, cursor = self._embedder([])
        cursor.fetchall.return_value = [(7,)]
        embedder.chunk_and_embed = MagicMock(
            side_effect=chunk_embedder.ChunkEmbeddingError("2 of 3 chunks"))
        embedder._remove_from_queue = MagicMock()
        embedder._update_queue_error = MagicMock()

        assert embedder.process_queue() == (0, 1)
        embedder._remove_from_queue.assert_not_called()
        embedder._update_queue_error.assert_called_once_with(7, "2 of 3 chunks")
