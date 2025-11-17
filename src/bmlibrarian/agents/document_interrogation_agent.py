"""
Document Interrogation Agent for answering questions about documents.

Processes large documents using a sliding window approach to extract
information needed to answer user questions. Supports both sequential
chunk processing and embedding-based semantic search.
"""

import json
import logging
from typing import List, Optional, Callable, Dict, Any, Tuple
from dataclasses import dataclass
from enum import Enum

from .base import BaseAgent
from .text_chunking import TextChunker, TextChunk, DEFAULT_CHUNK_SIZE, DEFAULT_CHUNK_OVERLAP

logger = logging.getLogger(__name__)


class ProcessingMode(Enum):
    """Processing modes for document interrogation."""
    SEQUENTIAL = "sequential"  # Process all chunks sequentially
    EMBEDDING = "embedding"    # Use embeddings for semantic search
    HYBRID = "hybrid"          # Combine both approaches


@dataclass
class RelevantSection:
    """Represents a section of text relevant to answering the question."""
    text: str
    chunk_index: int
    start_pos: int
    end_pos: int
    relevance_score: float  # 0-1, confidence this section answers the question
    reasoning: Optional[str] = None  # Why this section is relevant


@dataclass
class DocumentAnswer:
    """Complete answer to a question about a document."""
    question: str
    answer: str
    relevant_sections: List[RelevantSection]
    processing_mode: ProcessingMode
    chunks_processed: int
    chunks_total: int
    confidence: float  # 0-1, overall confidence in answer
    metadata: Optional[Dict[str, Any]] = None


class DocumentInterrogationAgent(BaseAgent):
    """
    Agent for answering questions about documents using sliding window processing.

    This agent splits large documents into overlapping chunks and processes them
    to extract information needed to answer user questions. It supports two
    processing modes:

    1. Sequential: Processes all chunks in order, extracting relevant sections
       from each, then synthesizes a final answer
    2. Embedding: Embeds chunks and only processes those with high semantic
       similarity to the question (requires Ollama embedding model)

    The sequential approach is thorough but slower, while the embedding approach
    is faster but may miss relevant information if embeddings don't capture
    the semantic relationship well.

    Example:
        >>> agent = DocumentInterrogationAgent()
        >>> result = agent.process_document(
        ...     document_text=pdf_text,
        ...     question="What are the cardiovascular benefits?",
        ...     mode=ProcessingMode.SEQUENTIAL
        ... )
        >>> print(result.answer)
    """

    def __init__(self,
                 model: str = "gpt-oss:20b",
                 embedding_model: str = "snowflake-arctic-embed2:latest",
                 host: str = "http://localhost:11434",
                 temperature: float = 0.1,
                 top_p: float = 0.9,
                 chunk_size: int = DEFAULT_CHUNK_SIZE,
                 chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
                 embedding_threshold: float = 0.5,
                 callback: Optional[Callable[[str, str], None]] = None,
                 orchestrator=None,
                 show_model_info: bool = True):
        """
        Initialize the DocumentInterrogationAgent.

        Args:
            model: The Ollama model for text generation (default: gpt-oss:20b)
            embedding_model: The Ollama model for embeddings (default: snowflake-arctic-embed2:latest)
            host: The Ollama server host URL (default: http://localhost:11434)
            temperature: Model temperature (default: 0.1 for focused answers)
            top_p: Model top-p sampling parameter (default: 0.9)
            chunk_size: Maximum chunk size in characters (default: 10000)
            chunk_overlap: Overlap between chunks in characters (default: 250)
            embedding_threshold: Minimum cosine similarity for chunk selection (default: 0.5)
            callback: Optional callback function for progress updates
            orchestrator: Optional orchestrator for queue-based processing
            show_model_info: Whether to display model information
        """
        super().__init__(
            model=model,
            host=host,
            temperature=temperature,
            top_p=top_p,
            callback=callback,
            orchestrator=orchestrator,
            show_model_info=show_model_info
        )
        self.embedding_model = embedding_model
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.embedding_threshold = embedding_threshold

        # Initialize text chunker
        self.chunker = TextChunker(chunk_size=chunk_size, overlap=chunk_overlap)

        self.agent_type = "document_interrogation_agent"

    def get_agent_type(self) -> str:
        """Get the agent type identifier."""
        return "document_interrogation_agent"

    def process_document(self,
                        document_text: str,
                        question: str,
                        mode: ProcessingMode = ProcessingMode.SEQUENTIAL,
                        max_sections: int = 10) -> DocumentAnswer:
        """
        Process a document to answer a question.

        Args:
            document_text: The full document text to process
            question: The question to answer about the document
            mode: Processing mode (SEQUENTIAL, EMBEDDING, or HYBRID)
            max_sections: Maximum number of relevant sections to extract (default: 10)

        Returns:
            DocumentAnswer with the answer and supporting sections

        Raises:
            ValueError: If document_text or question is empty
        """
        if not document_text or not document_text.strip():
            raise ValueError("document_text cannot be empty")
        if not question or not question.strip():
            raise ValueError("question cannot be empty")

        # Validate processing mode
        if not isinstance(mode, ProcessingMode):
            raise ValueError(f"Unknown processing mode: {mode}. Must be a ProcessingMode enum value.")

        self._call_callback("document_interrogation_start",
                          f"Processing document ({len(document_text)} chars) with mode: {mode.value}")

        # Chunk the document
        chunks = self.chunker.chunk_text(document_text)
        chunk_info = self.chunker.get_chunk_info(document_text)

        self._call_callback("chunking_complete",
                          f"Created {len(chunks)} chunks (size={self.chunk_size}, overlap={self.chunk_overlap})")

        # Process based on mode
        if mode == ProcessingMode.SEQUENTIAL:
            relevant_sections = self._process_sequential(chunks, question, max_sections)
        elif mode == ProcessingMode.EMBEDDING:
            relevant_sections = self._process_with_embeddings(chunks, question, max_sections)
        elif mode == ProcessingMode.HYBRID:
            relevant_sections = self._process_hybrid(chunks, question, max_sections)
        else:
            raise ValueError(f"Unknown processing mode: {mode}")

        self._call_callback("section_extraction_complete",
                          f"Extracted {len(relevant_sections)} relevant sections")

        # Synthesize final answer from relevant sections
        answer, confidence = self._synthesize_answer(question, relevant_sections)

        self._call_callback("answer_synthesis_complete",
                          f"Generated answer with confidence: {confidence:.2f}")

        return DocumentAnswer(
            question=question,
            answer=answer,
            relevant_sections=relevant_sections,
            processing_mode=mode,
            chunks_processed=len(chunks),
            chunks_total=len(chunks),
            confidence=confidence,
            metadata={
                'chunk_info': chunk_info,
                'model': self.model,
                'temperature': self.temperature
            }
        )

    def _process_sequential(self,
                           chunks: List[TextChunk],
                           question: str,
                           max_sections: int) -> List[RelevantSection]:
        """
        Process all chunks sequentially to extract relevant sections.

        This is the thorough approach that examines every chunk but is slower.

        Args:
            chunks: List of text chunks to process
            question: The question to answer
            max_sections: Maximum number of sections to extract

        Returns:
            List of relevant sections, sorted by relevance score
        """
        relevant_sections = []

        for chunk in chunks:
            self._call_callback("processing_chunk",
                              f"Chunk {chunk.chunk_index + 1}/{chunk.total_chunks}")

            # Extract relevant sections from this chunk
            sections = self._extract_relevant_sections_from_chunk(chunk, question)
            relevant_sections.extend(sections)

        # Sort by relevance score and limit to max_sections
        relevant_sections.sort(key=lambda s: s.relevance_score, reverse=True)
        return relevant_sections[:max_sections]

    def _process_with_embeddings(self,
                                 chunks: List[TextChunk],
                                 question: str,
                                 max_sections: int) -> List[RelevantSection]:
        """
        Use embeddings to select relevant chunks, then extract sections.

        This is faster but may miss relevant information if embeddings don't
        capture the semantic relationship well.

        Args:
            chunks: List of text chunks to process
            question: The question to answer
            max_sections: Maximum number of sections to extract

        Returns:
            List of relevant sections from semantically similar chunks
        """
        # Get embeddings for question
        self._call_callback("embedding_question", "Generating question embedding")
        question_embedding = self._get_embedding(question)

        # Get embeddings for all chunks and calculate similarity
        chunk_similarities = []
        for chunk in chunks:
            self._call_callback("embedding_chunk",
                              f"Embedding chunk {chunk.chunk_index + 1}/{chunk.total_chunks}")

            chunk_embedding = self._get_embedding(chunk.content)
            similarity = self._cosine_similarity(question_embedding, chunk_embedding)

            if similarity >= self.embedding_threshold:
                chunk_similarities.append((chunk, similarity))

        # Sort by similarity
        chunk_similarities.sort(key=lambda x: x[1], reverse=True)

        self._call_callback("embedding_selection_complete",
                          f"Selected {len(chunk_similarities)} chunks above threshold "
                          f"{self.embedding_threshold:.2f}")

        # Process only the most similar chunks
        relevant_sections = []
        for chunk, similarity in chunk_similarities[:max_sections]:
            self._call_callback("processing_relevant_chunk",
                              f"Processing chunk {chunk.chunk_index + 1} (similarity: {similarity:.2f})")

            sections = self._extract_relevant_sections_from_chunk(chunk, question)
            relevant_sections.extend(sections)

        # Sort by relevance score and limit
        relevant_sections.sort(key=lambda s: s.relevance_score, reverse=True)
        return relevant_sections[:max_sections]

    def _process_hybrid(self,
                       chunks: List[TextChunk],
                       question: str,
                       max_sections: int) -> List[RelevantSection]:
        """
        Hybrid approach: Use embeddings for initial filtering, then sequential processing.

        Args:
            chunks: List of text chunks to process
            question: The question to answer
            max_sections: Maximum number of sections to extract

        Returns:
            List of relevant sections combining both approaches
        """
        # Use embedding approach but process more chunks
        embedding_sections = self._process_with_embeddings(chunks, question, max_sections * 2)

        # Get indices of chunks we've already processed
        processed_indices = {s.chunk_index for s in embedding_sections}

        # Process remaining high-value chunks sequentially
        # (e.g., first and last chunks which might contain intro/conclusion)
        remaining_chunks = [c for c in chunks if c.chunk_index not in processed_indices]

        # Process first and last few chunks if not already processed
        priority_chunks = []
        if remaining_chunks:
            # First 2 chunks
            priority_chunks.extend([c for c in remaining_chunks[:2]])
            # Last 2 chunks
            if len(remaining_chunks) > 2:
                priority_chunks.extend([c for c in remaining_chunks[-2:]])

        for chunk in priority_chunks:
            sections = self._extract_relevant_sections_from_chunk(chunk, question)
            embedding_sections.extend(sections)

        # Sort and limit
        embedding_sections.sort(key=lambda s: s.relevance_score, reverse=True)
        return embedding_sections[:max_sections]

    def _extract_relevant_sections_from_chunk(self,
                                             chunk: TextChunk,
                                             question: str) -> List[RelevantSection]:
        """
        Extract relevant sections from a single chunk.

        Args:
            chunk: The text chunk to process
            question: The question to answer

        Returns:
            List of relevant sections found in this chunk
        """
        system_prompt = """You are an expert at analyzing documents to answer questions.
Your task is to identify specific passages in the provided text that help answer the question.

For each relevant passage:
1. Extract the exact text from the document (preserve formatting)
2. Rate its relevance from 0.0 to 1.0
3. Explain why it's relevant

Return your findings as a JSON array of objects with these fields:
- "text": the exact passage from the document
- "relevance_score": float between 0.0 and 1.0
- "reasoning": brief explanation of why this passage is relevant

If no relevant passages are found, return an empty array []."""

        user_prompt = f"""Question: {question}

Document Text:
{chunk.content}

Find all passages in the document that help answer the question.
Return JSON array format as specified."""

        try:
            response = self.client.chat(
                model=self.model,
                messages=[
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': user_prompt}
                ],
                options=self._get_ollama_options()
            )

            response_text = response['message']['content'].strip()

            # Parse JSON response
            # Handle markdown code blocks if present
            if response_text.startswith('```'):
                # Extract JSON from markdown code block
                lines = response_text.split('\n')
                json_lines = []
                in_code_block = False
                for line in lines:
                    if line.strip().startswith('```'):
                        in_code_block = not in_code_block
                        continue
                    if in_code_block or (not line.strip().startswith('```')):
                        json_lines.append(line)
                response_text = '\n'.join(json_lines)

            sections_data = json.loads(response_text)

            # Convert to RelevantSection objects
            sections = []
            for section_data in sections_data:
                section = RelevantSection(
                    text=section_data.get('text', ''),
                    chunk_index=chunk.chunk_index,
                    start_pos=chunk.start_pos,
                    end_pos=chunk.end_pos,
                    relevance_score=float(section_data.get('relevance_score', 0.0)),
                    reasoning=section_data.get('reasoning')
                )
                sections.append(section)

            return sections

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON response from chunk {chunk.chunk_index}: {e}")
            return []
        except Exception as e:
            logger.error(f"Error extracting sections from chunk {chunk.chunk_index}: {e}")
            return []

    def _synthesize_answer(self,
                          question: str,
                          relevant_sections: List[RelevantSection]) -> Tuple[str, float]:
        """
        Synthesize a final answer from the extracted relevant sections.

        Args:
            question: The original question
            relevant_sections: List of relevant sections extracted from chunks

        Returns:
            Tuple of (answer_text, confidence_score)
        """
        if not relevant_sections:
            return "I could not find information in the document to answer this question.", 0.0

        # Build context from relevant sections
        context_parts = []
        for i, section in enumerate(relevant_sections, 1):
            context_parts.append(f"[Section {i}] (relevance: {section.relevance_score:.2f})\n{section.text}")

        context = "\n\n".join(context_parts)

        system_prompt = """You are an expert at synthesizing information from documents to answer questions.

Your task is to:
1. Analyze the provided relevant sections from the document
2. Synthesize a clear, accurate answer to the question
3. Only use information present in the sections
4. If the sections don't fully answer the question, say so
5. Rate your confidence in the answer from 0.0 to 1.0

Return a JSON object with these fields:
- "answer": your synthesized answer
- "confidence": float between 0.0 and 1.0"""

        user_prompt = f"""Question: {question}

Relevant sections from the document:
{context}

Synthesize an answer to the question based on these sections.
Return JSON format: {{"answer": "...", "confidence": 0.0-1.0}}"""

        try:
            response = self.client.chat(
                model=self.model,
                messages=[
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': user_prompt}
                ],
                options=self._get_ollama_options()
            )

            response_text = response['message']['content'].strip()

            # Parse JSON response
            if response_text.startswith('```'):
                # Extract JSON from markdown code block
                lines = response_text.split('\n')
                json_lines = []
                in_code_block = False
                for line in lines:
                    if line.strip().startswith('```'):
                        in_code_block = not in_code_block
                        continue
                    if in_code_block or (not line.strip().startswith('```')):
                        json_lines.append(line)
                response_text = '\n'.join(json_lines)

            result = json.loads(response_text)
            answer = result.get('answer', 'Unable to synthesize answer.')
            confidence = float(result.get('confidence', 0.5))

            return answer, confidence

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON response during synthesis: {e}")
            # Fallback: return raw response
            return response_text, 0.5
        except Exception as e:
            logger.error(f"Error synthesizing answer: {e}")
            return f"Error generating answer: {str(e)}", 0.0

    def _get_embedding(self, text: str) -> List[float]:
        """
        Get embedding vector for text using Ollama.

        Reuses the BaseAgent._generate_embedding() method which handles
        logging and error handling consistently with other agents.

        Args:
            text: The text to embed

        Returns:
            Embedding vector as list of floats

        Raises:
            Exception: If embedding generation fails
        """
        # Use BaseAgent's _generate_embedding method with our embedding_model
        return self._generate_embedding(text, model=self.embedding_model)

    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """
        Calculate cosine similarity between two vectors.

        Args:
            vec1: First vector
            vec2: Second vector

        Returns:
            Cosine similarity score between -1 and 1

        Raises:
            ValueError: If vectors have different lengths
        """
        if len(vec1) != len(vec2):
            raise ValueError(f"Vectors must have same length: {len(vec1)} vs {len(vec2)}")

        # Calculate dot product
        dot_product = sum(a * b for a, b in zip(vec1, vec2))

        # Calculate magnitudes
        mag1 = sum(a * a for a in vec1) ** 0.5
        mag2 = sum(b * b for b in vec2) ** 0.5

        # Avoid division by zero
        if mag1 == 0 or mag2 == 0:
            return 0.0

        return dot_product / (mag1 * mag2)

    def test_connection(self) -> bool:
        """
        Test connection to Ollama server and verify models are available.

        Returns:
            True if connection successful, False otherwise
        """
        try:
            # Test main model
            models = self.client.list()
            model_names = [m.model for m in models.models]

            if self.model not in model_names:
                logger.warning(f"Model {self.model} not found in Ollama")
                return False

            # Test embedding model
            if self.embedding_model not in model_names:
                logger.warning(f"Embedding model {self.embedding_model} not found in Ollama")
                return False

            return True

        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return False
