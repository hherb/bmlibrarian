"""
Tests for SemanticChunkProcessor

Tests the concrete implementation of IterativeContextProcessor for
processing semantic search chunks from PRISMA assessments and other agents.
"""

import unittest
from unittest.mock import MagicMock, patch
from typing import Dict, Any

from bmlibrarian.agents.context_processor import (
    SemanticChunkProcessor,
    ProcessingConfig,
    ProcessingStatus,
    ExtractionResult,
    create_prisma_chunk_processor,
    DEFAULT_EXTRACTION_PROMPT,
    DEFAULT_CONSOLIDATION_PROMPT,
)


class MockOllamaClient:
    """Mock Ollama client for testing without LLM calls."""

    def __init__(self, responses: list = None, should_fail: bool = False):
        """
        Initialize mock client.

        Args:
            responses: List of response strings to return in order.
            should_fail: If True, raise exception on chat calls.
        """
        self.responses = responses or ["Extracted content from batch."]
        self.response_index = 0
        self.should_fail = should_fail
        self.call_history: list = []

    def chat(
        self,
        model: str,
        messages: list,
        options: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Mock chat method."""
        self.call_history.append({
            "model": model,
            "messages": messages,
            "options": options,
        })

        if self.should_fail:
            raise RuntimeError("Mock LLM failure")

        response = self.responses[self.response_index % len(self.responses)]
        self.response_index += 1
        return {"message": {"content": response}}


class TestSemanticChunkProcessor(unittest.TestCase):
    """Tests for SemanticChunkProcessor class."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_client = MockOllamaClient()
        self.processor = SemanticChunkProcessor(
            llm_client=self.mock_client,
            model="test-model",
            config=ProcessingConfig(max_context_chars=200),
        )

    def test_format_item_original_chunk(self):
        """Test formatting of original (text, score) chunk tuples."""
        chunk = ("This is test content", 0.85)
        formatted = self.processor.format_item(chunk, 0)

        self.assertIn("[Chunk 1, Score: 0.85]", formatted)
        self.assertIn("This is test content", formatted)

    def test_format_item_consolidated_tuple(self):
        """Test formatting of consolidated (content, metadata) tuples."""
        item = ("Consolidated content", {"recursion_level": 1})
        formatted = self.processor.format_item(item, 2)

        self.assertIn("[Consolidated Level 1, Item 3]", formatted)
        self.assertIn("Consolidated content", formatted)

    def test_format_item_string(self):
        """Test formatting of plain string items."""
        formatted = self.processor.format_item("Plain text", 0)

        self.assertIn("[Item 1]", formatted)
        self.assertIn("Plain text", formatted)

    def test_split_oversized_chunk(self):
        """Test splitting of oversized (text, score) chunks."""
        large_text = "A" * 100
        chunk = (large_text, 0.9)

        pieces = self.processor.split_oversized_item(chunk, max_chars=50)

        self.assertGreater(len(pieces), 1)
        # Each piece should preserve the score
        for piece_text, piece_score in pieces:
            self.assertLessEqual(len(piece_text), 50)
            self.assertEqual(piece_score, 0.9)

    def test_split_consolidated_item(self):
        """Test splitting of consolidated (content, metadata) items."""
        large_content = "B" * 100
        metadata = {"source": "test"}
        item = (large_content, metadata)

        pieces = self.processor.split_oversized_item(item, max_chars=50)

        self.assertGreater(len(pieces), 1)
        for piece_content, piece_metadata in pieces:
            self.assertLessEqual(len(piece_content), 50)
            self.assertEqual(piece_metadata["source"], "test")

    def test_extract_from_batch_calls_llm(self):
        """Test that extract_from_batch calls the LLM client."""
        batch_content = "Test batch content"
        query = "What is the search strategy?"
        batch_metadata = {"batch_index": 0, "recursion_level": 0}

        result = self.processor.extract_from_batch(
            batch_content, query, batch_metadata
        )

        self.assertEqual(len(self.mock_client.call_history), 1)
        call = self.mock_client.call_history[0]
        self.assertEqual(call["model"], "test-model")
        self.assertIn(query, call["messages"][0]["content"])
        self.assertIn(batch_content, call["messages"][0]["content"])
        self.assertIsInstance(result, ExtractionResult)
        self.assertEqual(result.content, "Extracted content from batch.")

    def test_extract_uses_extraction_prompt_at_level_0(self):
        """Test that extraction uses extraction prompt at recursion level 0."""
        batch_metadata = {"batch_index": 0, "recursion_level": 0}

        self.processor.extract_from_batch(
            "content", "query", batch_metadata
        )

        prompt = self.mock_client.call_history[0]["messages"][0]["content"]
        self.assertIn("Extract the key information", prompt)

    def test_extract_uses_consolidation_prompt_at_level_1(self):
        """Test that extraction uses consolidation prompt at recursion level > 0."""
        batch_metadata = {"batch_index": 0, "recursion_level": 1}

        self.processor.extract_from_batch(
            "content", "query", batch_metadata
        )

        prompt = self.mock_client.call_history[0]["messages"][0]["content"]
        self.assertIn("Consolidate and synthesize", prompt)

    def test_extract_failure_raises_runtime_error(self):
        """Test that LLM failure raises RuntimeError."""
        failing_client = MockOllamaClient(should_fail=True)
        processor = SemanticChunkProcessor(
            llm_client=failing_client,
            model="test-model",
        )

        with self.assertRaises(RuntimeError) as ctx:
            processor.extract_from_batch(
                "content", "query", {"batch_index": 0, "recursion_level": 0}
            )

        self.assertIn("LLM extraction failed", str(ctx.exception))

    def test_process_small_chunks_single_batch(self):
        """Test that small chunks fit in a single batch and complete successfully."""
        # Create chunks that fit within limit
        small_chunks = [
            ("Short text", 0.9),
            ("More text", 0.8),
        ]

        # Processor with large context limit - chunks fit in one batch
        processor = SemanticChunkProcessor(
            llm_client=self.mock_client,
            model="test-model",
            config=ProcessingConfig(max_context_chars=1000),
        )

        result = processor.process(small_chunks, "query")

        self.assertEqual(result.status, ProcessingStatus.COMPLETED)
        # Single batch creates single LLM call
        self.assertEqual(len(self.mock_client.call_history), 1)
        # Content is extracted (mock returns "Extracted content from batch.")
        self.assertEqual(result.content, "Extracted content from batch.")

    def test_process_large_chunks_uses_llm(self):
        """Test that large chunk sets trigger LLM extraction."""
        # Create chunks that exceed the limit
        large_chunks = [
            ("A" * 100, 0.9),
            ("B" * 100, 0.8),
            ("C" * 100, 0.7),
        ]

        processor = SemanticChunkProcessor(
            llm_client=self.mock_client,
            model="test-model",
            config=ProcessingConfig(max_context_chars=150),
        )

        result = processor.process(large_chunks, "query")

        # Should have made LLM calls
        self.assertGreater(len(self.mock_client.call_history), 0)
        self.assertEqual(result.status, ProcessingStatus.COMPLETED)

    def test_process_handles_llm_failure_gracefully(self):
        """Test that processing handles LLM failure with continue_on_error."""
        failing_client = MockOllamaClient(should_fail=True)
        processor = SemanticChunkProcessor(
            llm_client=failing_client,
            model="test-model",
            config=ProcessingConfig(
                max_context_chars=50,
                continue_on_error=True,
            ),
        )

        chunks = [("Text " * 20, 0.9)]
        result = processor.process(chunks, "query")

        # Should fail gracefully with error status
        self.assertIn(result.status, [ProcessingStatus.FAILED, ProcessingStatus.PARTIAL])

    def test_custom_prompt_templates(self):
        """Test using custom prompt templates."""
        custom_extraction = "Custom extraction: {query}\n{content}"
        custom_consolidation = "Custom consolidation: {query}\n{content}"

        processor = SemanticChunkProcessor(
            llm_client=self.mock_client,
            model="test-model",
            extraction_prompt_template=custom_extraction,
            consolidation_prompt_template=custom_consolidation,
        )

        processor.extract_from_batch(
            "content", "test query", {"batch_index": 0, "recursion_level": 0}
        )

        prompt = self.mock_client.call_history[0]["messages"][0]["content"]
        self.assertIn("Custom extraction:", prompt)

    def test_invalid_prompt_template_raises_error(self):
        """Test that missing placeholders raise ValueError."""
        with self.assertRaises(ValueError) as ctx:
            SemanticChunkProcessor(
                llm_client=self.mock_client,
                model="test-model",
                extraction_prompt_template="No placeholders here",
            )

        self.assertIn("{query}", str(ctx.exception))


class TestCreatePrismaChunkProcessor(unittest.TestCase):
    """Tests for the PRISMA-specific processor factory."""

    def test_creates_configured_processor(self):
        """Test that factory creates properly configured processor."""
        mock_client = MockOllamaClient()

        processor = create_prisma_chunk_processor(
            llm_client=mock_client,
            model="test-model",
            item_name="search_strategy",
            item_description="Full search strategy for at least one database",
            original_score=1.0,
            original_explanation="Partial description found",
            document_title="Test Paper",
        )

        self.assertIsInstance(processor, SemanticChunkProcessor)
        self.assertEqual(processor.model, "test-model")

    def test_prisma_prompts_include_context(self):
        """Test that PRISMA prompts include item context."""
        mock_client = MockOllamaClient()

        processor = create_prisma_chunk_processor(
            llm_client=mock_client,
            model="test-model",
            item_name="search_strategy",
            item_description="Full search strategy",
            original_score=1.0,
            original_explanation="Partial",
            document_title="My Paper",
        )

        # Trigger extraction to check prompt content
        processor.extract_from_batch(
            "batch content", "query", {"batch_index": 0, "recursion_level": 0}
        )

        prompt = mock_client.call_history[0]["messages"][0]["content"]
        self.assertIn("My Paper", prompt)
        self.assertIn("Search Strategy", prompt)  # Title case
        self.assertIn("1.0", prompt)
        self.assertIn("Partial", prompt)


class TestStructuredOutput(unittest.TestCase):
    """Tests for structured JSON output mode."""

    def test_structured_output_parses_json(self):
        """Test that structured output mode parses JSON responses."""
        json_response = '{"extracted_content": "Parsed content", "confidence": 0.95}'
        mock_client = MockOllamaClient(responses=[json_response])

        processor = SemanticChunkProcessor(
            llm_client=mock_client,
            model="test-model",
            use_structured_output=True,
        )

        result = processor.extract_from_batch(
            "content", "query", {"batch_index": 0, "recursion_level": 0}
        )

        self.assertEqual(result.content, "Parsed content")
        self.assertEqual(result.confidence, 0.95)

    def test_structured_output_handles_invalid_json(self):
        """Test that invalid JSON falls back to raw content."""
        mock_client = MockOllamaClient(responses=["Not valid JSON"])

        processor = SemanticChunkProcessor(
            llm_client=mock_client,
            model="test-model",
            use_structured_output=True,
        )

        result = processor.extract_from_batch(
            "content", "query", {"batch_index": 0, "recursion_level": 0}
        )

        # Should use raw content as fallback
        self.assertEqual(result.content, "Not valid JSON")


class TestIntegrationWithPRISMA(unittest.TestCase):
    """Integration tests simulating PRISMA agent usage."""

    def test_process_prisma_semantic_chunks(self):
        """Test processing chunks as PRISMA agent would."""
        # Simulate semantic search results
        chunks = [
            ("We searched PubMed, Embase, and Cochrane databases using keywords.", 0.92),
            ("Search strategy included Boolean operators AND, OR, NOT.", 0.88),
            ("No date restrictions were applied. Languages limited to English.", 0.75),
        ]

        mock_client = MockOllamaClient(responses=[
            "The search strategy used PubMed, Embase, and Cochrane databases with Boolean operators."
        ])

        processor = create_prisma_chunk_processor(
            llm_client=mock_client,
            model="gpt-oss:20b",
            item_name="search_strategy",
            item_description="Full search strategy for at least one database",
            original_score=1.0,
            original_explanation="Abstract mentions database search but lacks detail",
            document_title="Systematic Review of Interventions",
            max_context_chars=200,  # Force batching
        )

        result = processor.process(chunks, "search strategy database keywords")

        self.assertEqual(result.status, ProcessingStatus.COMPLETED)
        self.assertTrue(len(result.content) > 0)

    def test_handles_empty_chunks(self):
        """Test handling of empty chunk list."""
        mock_client = MockOllamaClient()
        processor = SemanticChunkProcessor(
            llm_client=mock_client,
            model="test-model",
        )

        result = processor.process([], "query")

        self.assertEqual(result.status, ProcessingStatus.COMPLETED)
        self.assertEqual(result.content, "")
        self.assertEqual(len(mock_client.call_history), 0)


if __name__ == "__main__":
    unittest.main()
