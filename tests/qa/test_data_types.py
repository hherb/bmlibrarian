"""Tests for qa/data_types.py."""

import pytest
from bmlibrarian.qa.data_types import (
    AnswerSource,
    QAError,
    ChunkContext,
    SemanticSearchAnswer,
    DocumentTextStatus,
)


class TestAnswerSource:
    """Tests for AnswerSource enum."""

    def test_values(self):
        """Test that all expected values exist."""
        assert AnswerSource.FULLTEXT_SEMANTIC.value == "fulltext_semantic"
        assert AnswerSource.ABSTRACT.value == "abstract"

    def test_enum_members(self):
        """Test enum has exactly the expected members."""
        members = list(AnswerSource)
        assert len(members) == 2


class TestQAError:
    """Tests for QAError enum."""

    def test_all_errors_have_descriptions(self):
        """Test that all errors have descriptions."""
        for error in QAError:
            assert error.description, f"{error.name} has no description"
            assert isinstance(error.description, str)

    def test_specific_descriptions(self):
        """Test specific error descriptions."""
        assert "not found" in QAError.DOCUMENT_NOT_FOUND.description.lower()
        assert "download" in QAError.DOWNLOAD_FAILED.description.lower()
        assert "llm" in QAError.LLM_ERROR.description.lower()


class TestChunkContext:
    """Tests for ChunkContext dataclass."""

    def test_basic_creation(self):
        """Test creating a ChunkContext."""
        chunk = ChunkContext(chunk_no=0, text="Test text", score=0.85)
        assert chunk.chunk_no == 0
        assert chunk.text == "Test text"
        assert chunk.score == 0.85
        assert chunk.chunk_id is None

    def test_with_chunk_id(self):
        """Test creating with chunk_id."""
        chunk = ChunkContext(chunk_no=1, text="More text", score=0.75, chunk_id=123)
        assert chunk.chunk_id == 123

    def test_repr_short_text(self):
        """Test repr with short text."""
        chunk = ChunkContext(chunk_no=0, text="Short", score=0.9)
        repr_str = repr(chunk)
        assert "ChunkContext" in repr_str
        assert "Short" in repr_str
        assert "0.900" in repr_str

    def test_repr_long_text(self):
        """Test repr truncates long text."""
        long_text = "A" * 100
        chunk = ChunkContext(chunk_no=0, text=long_text, score=0.5)
        repr_str = repr(chunk)
        assert "..." in repr_str
        assert len(repr_str) < len(long_text) + 50


class TestDocumentTextStatus:
    """Tests for DocumentTextStatus dataclass."""

    def test_basic_creation(self):
        """Test creating a DocumentTextStatus."""
        status = DocumentTextStatus(document_id=123)
        assert status.document_id == 123
        assert status.has_abstract is False
        assert status.has_fulltext is False

    def test_can_use_fulltext_semantic(self):
        """Test fulltext semantic availability check."""
        # Neither fulltext nor chunks
        status = DocumentTextStatus(document_id=1)
        assert status.can_use_fulltext_semantic is False

        # Has fulltext but no chunks
        status = DocumentTextStatus(document_id=1, has_fulltext=True)
        assert status.can_use_fulltext_semantic is False

        # Has both
        status = DocumentTextStatus(
            document_id=1, has_fulltext=True, has_fulltext_chunks=True
        )
        assert status.can_use_fulltext_semantic is True

    def test_can_use_abstract_semantic(self):
        """Test abstract semantic availability check."""
        status = DocumentTextStatus(
            document_id=1, has_abstract=True, has_abstract_embeddings=True
        )
        assert status.can_use_abstract_semantic is True

        status = DocumentTextStatus(document_id=1, has_abstract=True)
        assert status.can_use_abstract_semantic is False

    def test_has_any_text(self):
        """Test any text availability check."""
        status = DocumentTextStatus(document_id=1)
        assert status.has_any_text is False

        status = DocumentTextStatus(document_id=1, has_abstract=True)
        assert status.has_any_text is True

        status = DocumentTextStatus(document_id=1, has_fulltext=True)
        assert status.has_any_text is True


class TestSemanticSearchAnswer:
    """Tests for SemanticSearchAnswer dataclass."""

    def test_successful_answer(self):
        """Test creating a successful answer."""
        answer = SemanticSearchAnswer(
            answer="The study found positive results.",
            source=AnswerSource.FULLTEXT_SEMANTIC,
            model_used="gpt-oss:20b",
            document_id=123,
            question="What were the results?",
        )
        assert answer.success is True
        assert answer.error is None
        assert answer.used_fulltext is True

    def test_error_answer(self):
        """Test creating an error answer."""
        answer = SemanticSearchAnswer(
            answer="",
            error=QAError.DOCUMENT_NOT_FOUND,
            error_message="Document 999 not found",
            document_id=999,
            question="What is this?",
        )
        assert answer.success is False
        assert answer.error == QAError.DOCUMENT_NOT_FOUND

    def test_with_reasoning(self):
        """Test answer with thinking/reasoning."""
        answer = SemanticSearchAnswer(
            answer="The methodology was sound.",
            reasoning="First, I analyzed the methods section...",
            source=AnswerSource.FULLTEXT_SEMANTIC,
        )
        assert answer.reasoning is not None
        assert "analyzed" in answer.reasoning

    def test_to_dict(self):
        """Test serialization to dictionary."""
        chunks = [ChunkContext(chunk_no=0, text="Context text", score=0.8)]
        answer = SemanticSearchAnswer(
            answer="Result",
            source=AnswerSource.ABSTRACT,
            chunks_used=chunks,
            model_used="test-model",
            document_id=1,
            question="Test?",
        )

        d = answer.to_dict()
        assert d["answer"] == "Result"
        assert d["source"] == "abstract"
        assert d["success"] is True
        assert len(d["chunks_used"]) == 1
        assert d["chunks_used"][0]["score"] == 0.8

    def test_repr_success(self):
        """Test repr for successful answer."""
        answer = SemanticSearchAnswer(
            answer="Short answer",
            source=AnswerSource.ABSTRACT,
        )
        repr_str = repr(answer)
        assert "SemanticSearchAnswer" in repr_str
        assert "abstract" in repr_str

    def test_repr_error(self):
        """Test repr for error answer."""
        answer = SemanticSearchAnswer(
            answer="",
            error=QAError.LLM_ERROR,
            error_message="Model failed",
        )
        repr_str = repr(answer)
        assert "error=llm_error" in repr_str

    def test_long_answer_repr_truncation(self):
        """Test that long answers are truncated in repr."""
        long_answer = "X" * 200
        answer = SemanticSearchAnswer(answer=long_answer)
        repr_str = repr(answer)
        assert "..." in repr_str
