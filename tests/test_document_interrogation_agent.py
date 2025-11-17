"""
Tests for DocumentInterrogationAgent.

Tests the document interrogation agent's ability to process large documents
using sliding window chunk processing with both sequential and embedding-based
approaches.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from bmlibrarian.agents.document_interrogation_agent import (
    DocumentInterrogationAgent,
    DocumentAnswer,
    RelevantSection,
    ProcessingMode
)
from bmlibrarian.agents.text_chunking import TextChunk


class TestProcessingMode:
    """Test ProcessingMode enum."""

    def test_processing_modes_exist(self):
        """Test that all processing modes are defined."""
        assert ProcessingMode.SEQUENTIAL.value == "sequential"
        assert ProcessingMode.EMBEDDING.value == "embedding"
        assert ProcessingMode.HYBRID.value == "hybrid"


class TestRelevantSection:
    """Test RelevantSection dataclass."""

    def test_relevant_section_creation(self):
        """Test creating a RelevantSection."""
        section = RelevantSection(
            text="Test passage",
            chunk_index=0,
            start_pos=100,
            end_pos=200,
            relevance_score=0.85,
            reasoning="Answers the question directly"
        )

        assert section.text == "Test passage"
        assert section.chunk_index == 0
        assert section.start_pos == 100
        assert section.end_pos == 200
        assert section.relevance_score == 0.85
        assert section.reasoning == "Answers the question directly"


class TestDocumentAnswer:
    """Test DocumentAnswer dataclass."""

    def test_document_answer_creation(self):
        """Test creating a DocumentAnswer."""
        sections = [
            RelevantSection(
                text="Section 1",
                chunk_index=0,
                start_pos=0,
                end_pos=100,
                relevance_score=0.9
            )
        ]

        answer = DocumentAnswer(
            question="What is the answer?",
            answer="The answer is 42",
            relevant_sections=sections,
            processing_mode=ProcessingMode.SEQUENTIAL,
            chunks_processed=5,
            chunks_total=5,
            confidence=0.85,
            metadata={"model": "test-model"}
        )

        assert answer.question == "What is the answer?"
        assert answer.answer == "The answer is 42"
        assert len(answer.relevant_sections) == 1
        assert answer.processing_mode == ProcessingMode.SEQUENTIAL
        assert answer.chunks_processed == 5
        assert answer.chunks_total == 5
        assert answer.confidence == 0.85
        assert answer.metadata["model"] == "test-model"


class TestDocumentInterrogationAgent:
    """Test DocumentInterrogationAgent class."""

    @pytest.fixture
    def mock_ollama_client(self):
        """Create a mock Ollama client."""
        with patch('bmlibrarian.agents.base.ollama') as mock_ollama:
            mock_client = Mock()
            mock_ollama.Client.return_value = mock_client
            yield mock_client

    @pytest.fixture
    def agent(self, mock_ollama_client):
        """Create a DocumentInterrogationAgent with mocked Ollama."""
        agent = DocumentInterrogationAgent(
            model="test-model",
            embedding_model="test-embedding",
            chunk_size=100,
            chunk_overlap=20,
            show_model_info=False
        )
        return agent

    def test_initialization(self, agent):
        """Test agent initialization."""
        assert agent.model == "test-model"
        assert agent.embedding_model == "test-embedding"
        assert agent.chunk_size == 100
        assert agent.chunk_overlap == 20
        assert agent.embedding_threshold == 0.5
        assert agent.agent_type == "document_interrogation_agent"

    def test_get_agent_type(self, agent):
        """Test get_agent_type method."""
        assert agent.get_agent_type() == "document_interrogation_agent"

    def test_initialization_custom_params(self, mock_ollama_client):
        """Test initialization with custom parameters."""
        agent = DocumentInterrogationAgent(
            model="custom-model",
            embedding_model="custom-embedding",
            chunk_size=5000,
            chunk_overlap=500,
            embedding_threshold=0.7,
            temperature=0.2,
            top_p=0.95,
            show_model_info=False
        )

        assert agent.model == "custom-model"
        assert agent.embedding_model == "custom-embedding"
        assert agent.chunk_size == 5000
        assert agent.chunk_overlap == 500
        assert agent.embedding_threshold == 0.7
        assert agent.temperature == 0.2
        assert agent.top_p == 0.95

    def test_process_document_empty_text_raises_error(self, agent):
        """Test that processing empty document raises ValueError."""
        # Empty string - should be caught by the validation
        with pytest.raises(ValueError, match="document_text cannot be empty"):
            agent.process_document(
                question="What is this about?",
                document_text=""
            )

        # Whitespace only - should be caught by the validation
        with pytest.raises(ValueError, match="document_text cannot be empty"):
            agent.process_document(
                question="What is this about?",
                document_text="   "
            )

        # None - should be caught by different validation
        with pytest.raises(ValueError, match="Must provide either document_text or document_id"):
            agent.process_document(
                question="What is this about?",
                document_text=None
            )

    def test_process_document_empty_question_raises_error(self, agent):
        """Test that processing with empty question raises ValueError."""
        with pytest.raises(ValueError, match="question cannot be empty"):
            agent.process_document(
                question="",
                document_text="Some document text"
            )

        with pytest.raises(ValueError, match="question cannot be empty"):
            agent.process_document(
                question="   ",
                document_text="Some document text"
            )

    def test_process_document_sequential_mode(self, agent, mock_ollama_client):
        """Test document processing in sequential mode."""
        # Mock LLM responses for section extraction and synthesis
        # Need to mock both chunks (2 chunks for 150 chars) + synthesis
        mock_ollama_client.chat.side_effect = [
            # First chunk: section extraction
            {'message': {'content': '[{"text": "Relevant passage 1", "relevance_score": 0.9, "reasoning": "Direct answer"}]'}},
            # Second chunk: section extraction
            {'message': {'content': '[]'}},  # No relevant sections in second chunk
            # Synthesis
            {'message': {'content': '{"answer": "The document discusses topic X", "confidence": 0.85}'}}
        ]

        document = "A" * 150  # Creates 2 chunks with chunk_size=100, overlap=20
        question = "What is this about?"

        result = agent.process_document(
            question=question,
            document_text=document,
            mode=ProcessingMode.SEQUENTIAL,
            max_sections=10
        )

        assert isinstance(result, DocumentAnswer)
        assert result.question == question
        assert "topic X" in result.answer
        assert result.processing_mode == ProcessingMode.SEQUENTIAL
        assert result.chunks_total >= 1
        assert result.confidence == 0.85

    def test_cosine_similarity_identical_vectors(self, agent):
        """Test cosine similarity with identical vectors."""
        vec1 = [1.0, 2.0, 3.0, 4.0]
        vec2 = [1.0, 2.0, 3.0, 4.0]

        similarity = agent._cosine_similarity(vec1, vec2)
        assert abs(similarity - 1.0) < 0.0001  # Should be 1.0

    def test_cosine_similarity_orthogonal_vectors(self, agent):
        """Test cosine similarity with orthogonal vectors."""
        vec1 = [1.0, 0.0, 0.0]
        vec2 = [0.0, 1.0, 0.0]

        similarity = agent._cosine_similarity(vec1, vec2)
        assert abs(similarity - 0.0) < 0.0001  # Should be 0.0

    def test_cosine_similarity_opposite_vectors(self, agent):
        """Test cosine similarity with opposite vectors."""
        vec1 = [1.0, 2.0, 3.0]
        vec2 = [-1.0, -2.0, -3.0]

        similarity = agent._cosine_similarity(vec1, vec2)
        assert abs(similarity - (-1.0)) < 0.0001  # Should be -1.0

    def test_cosine_similarity_different_lengths_raises_error(self, agent):
        """Test that cosine similarity with different length vectors raises error."""
        vec1 = [1.0, 2.0, 3.0]
        vec2 = [1.0, 2.0]

        with pytest.raises(ValueError, match="Vectors must have same length"):
            agent._cosine_similarity(vec1, vec2)

    def test_cosine_similarity_zero_vectors(self, agent):
        """Test cosine similarity with zero vectors."""
        vec1 = [0.0, 0.0, 0.0]
        vec2 = [1.0, 2.0, 3.0]

        similarity = agent._cosine_similarity(vec1, vec2)
        assert similarity == 0.0  # Should handle division by zero

    def test_extract_relevant_sections_valid_json(self, agent, mock_ollama_client):
        """Test extracting relevant sections with valid JSON response."""
        mock_ollama_client.chat.return_value = {
            'message': {
                'content': '[{"text": "Passage 1", "relevance_score": 0.9, "reasoning": "Relevant"}]'
            }
        }

        chunk = TextChunk(
            content="Test content",
            start_pos=0,
            end_pos=12,
            chunk_index=0,
            total_chunks=1
        )

        sections = agent._extract_relevant_sections_from_chunk(chunk, "What is this?")

        assert len(sections) == 1
        assert sections[0].text == "Passage 1"
        assert sections[0].relevance_score == 0.9
        assert sections[0].chunk_index == 0

    def test_extract_relevant_sections_markdown_json(self, agent, mock_ollama_client):
        """Test extracting sections when LLM returns JSON in markdown code block."""
        mock_ollama_client.chat.return_value = {
            'message': {
                'content': '```json\n[{"text": "Passage 1", "relevance_score": 0.8, "reasoning": "Good"}]\n```'
            }
        }

        chunk = TextChunk(
            content="Test content",
            start_pos=0,
            end_pos=12,
            chunk_index=0,
            total_chunks=1
        )

        sections = agent._extract_relevant_sections_from_chunk(chunk, "Question?")

        assert len(sections) == 1
        assert sections[0].text == "Passage 1"
        assert sections[0].relevance_score == 0.8

    def test_extract_relevant_sections_empty_array(self, agent, mock_ollama_client):
        """Test extracting sections when no relevant sections found."""
        mock_ollama_client.chat.return_value = {
            'message': {'content': '[]'}
        }

        chunk = TextChunk(
            content="Irrelevant content",
            start_pos=0,
            end_pos=17,
            chunk_index=0,
            total_chunks=1
        )

        sections = agent._extract_relevant_sections_from_chunk(chunk, "Unrelated question?")

        assert sections == []

    def test_extract_relevant_sections_invalid_json(self, agent, mock_ollama_client):
        """Test that invalid JSON is handled gracefully."""
        mock_ollama_client.chat.return_value = {
            'message': {'content': 'This is not JSON'}
        }

        chunk = TextChunk(
            content="Test content",
            start_pos=0,
            end_pos=12,
            chunk_index=0,
            total_chunks=1
        )

        sections = agent._extract_relevant_sections_from_chunk(chunk, "Question?")

        # Should return empty list on JSON parse error
        assert sections == []

    def test_synthesize_answer_with_sections(self, agent, mock_ollama_client):
        """Test synthesizing answer from relevant sections."""
        mock_ollama_client.chat.return_value = {
            'message': {
                'content': '{"answer": "The answer is 42", "confidence": 0.95}'
            }
        }

        sections = [
            RelevantSection(
                text="Section 1",
                chunk_index=0,
                start_pos=0,
                end_pos=100,
                relevance_score=0.9,
                reasoning="Relevant"
            ),
            RelevantSection(
                text="Section 2",
                chunk_index=1,
                start_pos=80,
                end_pos=180,
                relevance_score=0.85,
                reasoning="Also relevant"
            )
        ]

        answer, confidence = agent._synthesize_answer("What is the answer?", sections)

        assert "42" in answer
        assert confidence == 0.95

    def test_synthesize_answer_no_sections(self, agent):
        """Test synthesizing answer when no relevant sections found."""
        answer, confidence = agent._synthesize_answer("Question?", [])

        assert "could not find information" in answer.lower()
        assert confidence == 0.0

    def test_synthesize_answer_markdown_json(self, agent, mock_ollama_client):
        """Test synthesis when LLM returns JSON in markdown code block."""
        mock_ollama_client.chat.return_value = {
            'message': {
                'content': '```json\n{"answer": "Test answer", "confidence": 0.75}\n```'
            }
        }

        sections = [
            RelevantSection(
                text="Test",
                chunk_index=0,
                start_pos=0,
                end_pos=10,
                relevance_score=0.8
            )
        ]

        answer, confidence = agent._synthesize_answer("Question?", sections)

        assert "Test answer" in answer
        assert confidence == 0.75

    def test_callback_invocation(self, mock_ollama_client):
        """Test that callback is invoked during processing."""
        callback_calls = []

        def test_callback(step: str, data: str):
            callback_calls.append((step, data))

        agent = DocumentInterrogationAgent(
            model="test-model",
            chunk_size=50,
            chunk_overlap=10,
            callback=test_callback,
            show_model_info=False
        )

        # Mock responses
        mock_ollama_client.chat.side_effect = [
            {'message': {'content': '[]'}},  # Chunk 1
            {'message': {'content': '[]'}},  # Chunk 2
            {'message': {'content': '{"answer": "Test", "confidence": 0.5}'}}  # Synthesis
        ]

        document = "A" * 100  # Creates multiple chunks
        agent.process_document(question="Question?", document_text=document, mode=ProcessingMode.SEQUENTIAL)

        # Verify callbacks were made
        assert len(callback_calls) > 0
        step_names = [call[0] for call in callback_calls]
        assert "document_interrogation_start" in step_names
        assert "chunking_complete" in step_names

    def test_process_document_invalid_mode_raises_error(self, agent):
        """Test that invalid processing mode raises ValueError."""
        with pytest.raises(ValueError, match="Unknown processing mode"):
            # Use a string that's not a valid enum
            agent.process_document(
                question="Question?",
                document_text="Test",
                mode="invalid_mode"  # This will fail type checking, but test runtime behavior
            )

    def test_get_embedding(self, agent, mock_ollama_client):
        """Test getting embeddings from Ollama."""
        mock_ollama_client.embeddings.return_value = {
            'embedding': [0.1, 0.2, 0.3, 0.4, 0.5]
        }

        embedding = agent._get_embedding("Test text")

        assert embedding == [0.1, 0.2, 0.3, 0.4, 0.5]
        mock_ollama_client.embeddings.assert_called_once_with(
            model="test-embedding",
            prompt="Test text"
        )

    def test_process_with_embeddings_mode(self, agent, mock_ollama_client):
        """Test document processing with embedding-based mode."""
        # Mock embeddings (question and chunks)
        mock_ollama_client.embeddings.side_effect = [
            {'embedding': [1.0, 0.0, 0.0]},  # Question embedding
            {'embedding': [0.9, 0.1, 0.0]},  # Chunk 1 (high similarity)
            {'embedding': [0.1, 0.9, 0.0]},  # Chunk 2 (low similarity)
        ]

        # Mock LLM responses
        mock_ollama_client.chat.side_effect = [
            {'message': {'content': '[{"text": "Found it!", "relevance_score": 0.9, "reasoning": "Match"}]'}},
            {'message': {'content': '{"answer": "The answer", "confidence": 0.9}'}}
        ]

        document = "A" * 150  # Multiple chunks
        result = agent.process_document(
            question="Question?",
            document_text=document,
            mode=ProcessingMode.EMBEDDING,
            max_sections=5
        )

        assert isinstance(result, DocumentAnswer)
        assert result.processing_mode == ProcessingMode.EMBEDDING

    def test_test_connection_success(self, agent, mock_ollama_client):
        """Test connection test with successful connection."""
        mock_model = Mock()
        mock_model.model = "test-model"

        mock_embedding_model = Mock()
        mock_embedding_model.model = "test-embedding"

        mock_list = Mock()
        mock_list.models = [mock_model, mock_embedding_model]
        mock_ollama_client.list.return_value = mock_list

        assert agent.test_connection() is True

    def test_test_connection_missing_model(self, agent, mock_ollama_client):
        """Test connection test when model is not available."""
        mock_model = Mock()
        mock_model.model = "other-model"

        mock_list = Mock()
        mock_list.models = [mock_model]
        mock_ollama_client.list.return_value = mock_list

        assert agent.test_connection() is False

    def test_test_connection_failure(self, agent, mock_ollama_client):
        """Test connection test with connection failure."""
        mock_ollama_client.list.side_effect = Exception("Connection failed")

        assert agent.test_connection() is False

    def test_process_document_requires_text_or_id(self, agent):
        """Test that either document_text or document_id must be provided."""
        # Neither provided
        with pytest.raises(ValueError, match="Must provide either document_text or document_id"):
            agent.process_document(question="Question?")

        # Both provided
        with pytest.raises(ValueError, match="Provide either document_text OR document_id, not both"):
            agent.process_document(
                question="Question?",
                document_text="Some text",
                document_id=123
            )

    def test_process_document_with_database_chunks(self, agent, mock_ollama_client):
        """Test processing document using pre-chunked database chunks."""
        # Mock database retrieval
        with patch('bmlibrarian.agents.document_interrogation_agent.get_db_manager') as mock_db_manager:
            # Set up nested context managers for connection and cursor
            mock_cursor = MagicMock()
            mock_conn = MagicMock()
            mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
            mock_db_manager.return_value.get_connection.return_value.__enter__.return_value = mock_conn

            # Mock database chunks
            mock_cursor.fetchall.return_value = [
                (1, "First chunk text", 0, [0.1, 0.2, 0.3]),
                (2, "Second chunk text", 1, [0.4, 0.5, 0.6])
            ]

            # Mock LLM responses
            mock_ollama_client.chat.side_effect = [
                {'message': {'content': '[{"text": "Relevant!", "relevance_score": 0.9, "reasoning": "Match"}]'}},
                {'message': {'content': '[]'}},
                {'message': {'content': '{"answer": "Database answer", "confidence": 0.9}'}}
            ]

            result = agent.process_document(
                question="What is this?",
                document_id=123,
                mode=ProcessingMode.SEQUENTIAL
            )

            assert isinstance(result, DocumentAnswer)
            assert "Database answer" in result.answer
            assert result.metadata['chunk_info']['source'] == 'database'
            assert result.metadata['chunk_info']['document_id'] == 123
