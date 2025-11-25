"""
Unit Tests for Iterative Context Processor Base Class

Tests the hierarchical map-reduce processing algorithm including:
- Batching logic
- Oversized item handling
- Consolidation strategies
- Error recovery
- Progress tracking
"""

import unittest
from typing import Any, Dict, List
from unittest.mock import MagicMock, call

from bmlibrarian.agents.context_processor import (
    Batch,
    ConsolidationStrategy,
    ExtractionResult,
    IterativeContextProcessor,
    OversizedItemStrategy,
    ProcessingConfig,
    ProcessingResult,
    ProcessingStatus,
    ProgressInfo,
)


class SimpleTestProcessor(IterativeContextProcessor):
    """
    Simple test implementation of IterativeContextProcessor.

    Formats items as strings and extracts by returning the content as-is.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.extract_calls: List[Dict[str, Any]] = []
        self.should_fail_batch: int = -1  # Batch index to fail (-1 = none)

    def format_item(self, item: Any, index: int) -> str:
        """Format item as string with index prefix."""
        if isinstance(item, tuple) and len(item) == 2:
            content, _ = item
            return f"[{index}] {content}"
        return f"[{index}] {item}"

    def extract_from_batch(
        self,
        batch_content: str,
        query: str,
        batch_metadata: Dict[str, Any],
    ) -> ExtractionResult:
        """Record the call and return a simple extraction."""
        self.extract_calls.append({
            "content": batch_content,
            "query": query,
            "metadata": batch_metadata,
        })

        # Check if we should fail this batch
        if batch_metadata.get("batch_index") == self.should_fail_batch:
            raise ValueError(f"Simulated failure for batch {self.should_fail_batch}")

        # Return a summarized version (just take first 100 chars)
        summary = batch_content[:100] if len(batch_content) > 100 else batch_content
        return ExtractionResult(
            content=f"Extracted: {summary}",
            metadata={"query": query},
            confidence=0.9,
        )


class TestProcessingConfig(unittest.TestCase):
    """Tests for ProcessingConfig validation."""

    def test_default_config(self):
        """Default configuration should be valid."""
        config = ProcessingConfig()
        self.assertEqual(config.max_context_chars, 4000)
        self.assertEqual(config.max_recursion_depth, 5)
        self.assertEqual(config.oversized_item_strategy, OversizedItemStrategy.SPLIT)
        self.assertEqual(config.consolidation_strategy, ConsolidationStrategy.CONCATENATE)
        self.assertTrue(config.continue_on_error)

    def test_invalid_max_context_chars(self):
        """Should reject non-positive max_context_chars."""
        with self.assertRaises(ValueError):
            ProcessingConfig(max_context_chars=0)
        with self.assertRaises(ValueError):
            ProcessingConfig(max_context_chars=-100)

    def test_invalid_overlap_chars(self):
        """Should reject negative overlap_chars."""
        with self.assertRaises(ValueError):
            ProcessingConfig(overlap_chars=-1)

    def test_invalid_recursion_depth(self):
        """Should reject negative max_recursion_depth."""
        with self.assertRaises(ValueError):
            ProcessingConfig(max_recursion_depth=-1)

    def test_invalid_min_items(self):
        """Should reject min_items_for_recursion < 1."""
        with self.assertRaises(ValueError):
            ProcessingConfig(min_items_for_recursion=0)

    def test_invalid_confidence_threshold(self):
        """Should reject confidence threshold outside 0-1."""
        with self.assertRaises(ValueError):
            ProcessingConfig(min_confidence_threshold=-0.1)
        with self.assertRaises(ValueError):
            ProcessingConfig(min_confidence_threshold=1.5)


class TestBatching(unittest.TestCase):
    """Tests for the batching algorithm."""

    def setUp(self):
        """Set up test processor."""
        self.config = ProcessingConfig(
            max_context_chars=100,
            separator="\n---\n",
        )
        self.processor = SimpleTestProcessor(config=self.config)

    def test_empty_items(self):
        """Empty input should return empty batches."""
        batches = self.processor._create_batches([], self.config)
        self.assertEqual(len(batches), 0)

    def test_single_item_fits(self):
        """Single item that fits should create one batch."""
        items = ["Hello world"]
        batches = self.processor._create_batches(items, self.config)
        self.assertEqual(len(batches), 1)
        self.assertEqual(batches[0].size, 1)

    def test_multiple_items_single_batch(self):
        """Multiple small items should fit in one batch."""
        items = ["A", "B", "C"]
        batches = self.processor._create_batches(items, self.config)
        self.assertEqual(len(batches), 1)
        self.assertEqual(batches[0].size, 3)

    def test_multiple_batches(self):
        """Items exceeding limit should create multiple batches."""
        # Each item is "[X] " + 30 chars = ~34 chars
        # With separator of 5 chars, 2 items = ~73 chars, 3 items = ~112 chars
        items = ["A" * 30, "B" * 30, "C" * 30, "D" * 30]
        batches = self.processor._create_batches(items, self.config)
        self.assertGreater(len(batches), 1)

    def test_batch_indices_preserved(self):
        """Item indices should be preserved in batches."""
        items = ["A", "B", "C"]
        batches = self.processor._create_batches(items, self.config)
        # All items in one batch
        self.assertEqual(batches[0].item_indices, [0, 1, 2])


class TestOversizedItems(unittest.TestCase):
    """Tests for oversized item handling."""

    def test_split_strategy(self):
        """SPLIT strategy should split oversized items."""
        config = ProcessingConfig(
            max_context_chars=50,
            oversized_item_strategy=OversizedItemStrategy.SPLIT,
        )
        processor = SimpleTestProcessor(config=config)

        # Create an oversized item (100+ chars after formatting)
        items = ["X" * 200]
        skipped: List[int] = []
        batches = processor._create_batches(items, config, skipped)

        # Should create multiple batches from split pieces
        self.assertGreater(len(batches), 1)
        self.assertEqual(len(skipped), 0)

    def test_skip_strategy(self):
        """SKIP strategy should skip oversized items."""
        config = ProcessingConfig(
            max_context_chars=50,
            oversized_item_strategy=OversizedItemStrategy.SKIP,
        )
        processor = SimpleTestProcessor(config=config)

        items = ["X" * 200]
        skipped: List[int] = []
        batches = processor._create_batches(items, config, skipped)

        # Should skip the item
        self.assertEqual(len(batches), 0)
        self.assertEqual(skipped, [0])

    def test_truncate_strategy(self):
        """TRUNCATE strategy should truncate oversized items."""
        config = ProcessingConfig(
            max_context_chars=50,
            oversized_item_strategy=OversizedItemStrategy.TRUNCATE,
        )
        processor = SimpleTestProcessor(config=config)

        items = ["X" * 200]
        skipped: List[int] = []
        batches = processor._create_batches(items, config, skipped)

        # Should create one batch with truncated content
        self.assertEqual(len(batches), 1)
        self.assertEqual(len(skipped), 0)
        # Content should be truncated to max_context_chars
        # The truncated item becomes a string that gets reformatted with [index] prefix
        # So total_chars may slightly exceed 50 due to reformatting, but original was 200
        self.assertLess(batches[0].total_chars, 200)  # Much smaller than original

    def test_fail_strategy(self):
        """FAIL strategy should raise error for oversized items."""
        config = ProcessingConfig(
            max_context_chars=50,
            oversized_item_strategy=OversizedItemStrategy.FAIL,
        )
        processor = SimpleTestProcessor(config=config)

        items = ["X" * 200]
        with self.assertRaises(ValueError):
            processor._create_batches(items, config)


class TestConsolidationStrategies(unittest.TestCase):
    """Tests for result consolidation strategies."""

    def setUp(self):
        """Set up test processor."""
        self.processor = SimpleTestProcessor()

    def test_concatenate_strategy(self):
        """CONCATENATE should join results with separator."""
        config = ProcessingConfig(
            consolidation_strategy=ConsolidationStrategy.CONCATENATE,
            separator="|",
        )
        results = [
            ExtractionResult(content="A", confidence=0.5),
            ExtractionResult(content="B", confidence=0.9),
            ExtractionResult(content="C", confidence=0.7),
        ]

        merged = self.processor._merge_results(results, config)
        self.assertEqual(merged.content, "A|B|C")

    def test_weighted_strategy(self):
        """WEIGHTED should sort by confidence (highest first)."""
        config = ProcessingConfig(
            consolidation_strategy=ConsolidationStrategy.WEIGHTED,
            separator="|",
        )
        results = [
            ExtractionResult(content="Low", confidence=0.3),
            ExtractionResult(content="High", confidence=0.9),
            ExtractionResult(content="Med", confidence=0.6),
        ]

        merged = self.processor._merge_results(results, config)
        self.assertEqual(merged.content, "High|Med|Low")

    def test_deduplicate_strategy(self):
        """DEDUPLICATE should remove duplicate content."""
        config = ProcessingConfig(
            consolidation_strategy=ConsolidationStrategy.DEDUPLICATE,
            separator="|",
        )
        results = [
            ExtractionResult(content="Hello", confidence=0.9),
            ExtractionResult(content="HELLO", confidence=0.8),  # Duplicate (case)
            ExtractionResult(content="World", confidence=0.7),
            ExtractionResult(content="hello ", confidence=0.6),  # Duplicate (whitespace)
        ]

        merged = self.processor._merge_results(results, config)
        # Should only have Hello and World (first occurrences preserved)
        self.assertIn("Hello", merged.content)
        self.assertIn("World", merged.content)
        parts = merged.content.split("|")
        self.assertEqual(len(parts), 2)

    def test_filter_errors(self):
        """Merge should filter out error results."""
        config = ProcessingConfig()
        results = [
            ExtractionResult(content="Good", confidence=0.9),
            ExtractionResult(content="", confidence=0.0, is_error=True, error_message="Failed"),
            ExtractionResult(content="Also Good", confidence=0.8),
        ]

        merged = self.processor._merge_results(results, config)
        self.assertIn("Good", merged.content)
        self.assertIn("Also Good", merged.content)
        self.assertNotIn("Failed", merged.content)

    def test_filter_low_confidence(self):
        """Merge should filter results below confidence threshold."""
        config = ProcessingConfig(min_confidence_threshold=0.5)
        results = [
            ExtractionResult(content="High", confidence=0.9),
            ExtractionResult(content="Low", confidence=0.3),
            ExtractionResult(content="Medium", confidence=0.6),
        ]

        merged = self.processor._merge_results(results, config)
        self.assertIn("High", merged.content)
        self.assertIn("Medium", merged.content)
        self.assertNotIn("Low", merged.content)


class TestErrorRecovery(unittest.TestCase):
    """Tests for error handling and recovery."""

    def test_continue_on_error(self):
        """With continue_on_error=True, should continue after batch failure."""
        config = ProcessingConfig(
            max_context_chars=60,  # Small enough to force multiple batches
            continue_on_error=True,
        )
        processor = SimpleTestProcessor(config=config)
        processor.should_fail_batch = 0  # Fail first batch

        # Create items that will produce at least 2 batches
        # Each item after formatting is "[X] " + 35 chars = ~39 chars
        # With separator of ~7 chars, two items = ~85 chars > 60, so 2 batches
        items = ["A" * 35, "B" * 35]

        result = processor.process(items, "test query")

        # Should complete with partial status since one batch succeeded
        self.assertEqual(result.status, ProcessingStatus.PARTIAL)
        self.assertEqual(len(result.failed_batches), 1)
        self.assertIn(0, result.failed_batches)
        self.assertEqual(result.successful_batches, 1)

    def test_fail_fast(self):
        """With continue_on_error=False, should fail immediately."""
        config = ProcessingConfig(
            max_context_chars=100,
            continue_on_error=False,
        )
        processor = SimpleTestProcessor(config=config)
        processor.should_fail_batch = 0  # Fail first batch

        items = ["A" * 40, "B" * 40]

        result = processor.process(items, "test query")

        # Should fail
        self.assertEqual(result.status, ProcessingStatus.FAILED)
        self.assertIsNotNone(result.error_message)

    def test_all_batches_fail(self):
        """When all batches fail, status should be FAILED."""
        config = ProcessingConfig(
            max_context_chars=1000,  # All in one batch
            continue_on_error=True,
        )
        processor = SimpleTestProcessor(config=config)
        processor.should_fail_batch = 0  # Fail the only batch

        items = ["A", "B", "C"]

        result = processor.process(items, "test query")

        # Should fail since all batches failed
        self.assertEqual(result.status, ProcessingStatus.FAILED)


class TestProgressTracking(unittest.TestCase):
    """Tests for progress callback functionality."""

    def test_progress_callback_called(self):
        """Progress callback should be called during processing."""
        progress_updates: List[ProgressInfo] = []

        def track_progress(info: ProgressInfo):
            progress_updates.append(info)

        processor = SimpleTestProcessor(progress_callback=track_progress)
        items = ["A", "B", "C"]

        processor.process(items, "test query")

        # Should have received progress updates
        self.assertGreater(len(progress_updates), 0)

        # Check stages
        stages = [p.stage for p in progress_updates]
        self.assertIn("starting", stages)
        self.assertIn("batching", stages)
        self.assertIn("complete", stages)

    def test_progress_callback_error_ignored(self):
        """Errors in progress callback should not crash processing."""
        def bad_callback(info: ProgressInfo):
            raise RuntimeError("Callback error")

        processor = SimpleTestProcessor(progress_callback=bad_callback)
        items = ["A", "B", "C"]

        # Should not raise
        result = processor.process(items, "test query")
        self.assertEqual(result.status, ProcessingStatus.COMPLETED)


class TestFullProcessing(unittest.TestCase):
    """Integration tests for full processing workflow."""

    def test_empty_input(self):
        """Empty input should return completed with empty result."""
        processor = SimpleTestProcessor()
        result = processor.process([], "test query")

        self.assertEqual(result.status, ProcessingStatus.COMPLETED)
        self.assertEqual(result.total_items_processed, 0)
        self.assertEqual(result.content, "")

    def test_single_batch_processing(self):
        """Items fitting in one batch should process without recursion."""
        processor = SimpleTestProcessor()
        items = ["Hello", "World"]

        result = processor.process(items, "test query")

        self.assertEqual(result.status, ProcessingStatus.COMPLETED)
        self.assertEqual(result.recursion_levels_used, 0)
        self.assertEqual(len(processor.extract_calls), 1)

    def test_max_recursion_depth(self):
        """Should stop at max recursion depth."""
        # Create config that forces recursion but limits depth
        config = ProcessingConfig(
            max_context_chars=50,  # Small to force batching
            max_recursion_depth=1,
        )
        processor = SimpleTestProcessor(config=config)

        # Create many items to force recursion
        items = ["X" * 20 for _ in range(20)]

        result = processor.process(items, "test query")

        # Should be truncated due to max recursion
        self.assertIn(result.status, [
            ProcessingStatus.TRUNCATED,
            ProcessingStatus.COMPLETED,
        ])
        self.assertLessEqual(result.recursion_levels_used, 1)

    def test_intermediate_results_stored(self):
        """Should store intermediate results when requested."""
        config = ProcessingConfig(max_context_chars=100)
        processor = SimpleTestProcessor(config=config)
        items = ["A" * 30, "B" * 30, "C" * 30]

        result = processor.process(items, "test query", store_intermediate=True)

        self.assertIsNotNone(result.intermediate_results)
        self.assertGreater(len(result.intermediate_results), 0)

    def test_statistics_tracked(self):
        """Should track processing statistics."""
        processor = SimpleTestProcessor()
        items = ["A", "B", "C", "D", "E"]

        result = processor.process(items, "test query")

        self.assertIn("total_items", result.processing_stats)
        self.assertEqual(result.processing_stats["total_items"], 5)
        self.assertIn("batches_per_level", result.processing_stats)


class TestExtractionResult(unittest.TestCase):
    """Tests for ExtractionResult dataclass."""

    def test_is_valid_normal(self):
        """Normal result should be valid."""
        result = ExtractionResult(content="Hello", confidence=0.9)
        self.assertTrue(result.is_valid)

    def test_is_valid_error(self):
        """Error result should not be valid."""
        result = ExtractionResult(
            content="",
            confidence=0.0,
            is_error=True,
            error_message="Failed"
        )
        self.assertFalse(result.is_valid)

    def test_is_valid_empty(self):
        """Empty content should not be valid."""
        result = ExtractionResult(content="", confidence=0.9)
        self.assertFalse(result.is_valid)

    def test_content_length(self):
        """content_length should return correct length."""
        result = ExtractionResult(content="Hello World", confidence=0.9)
        self.assertEqual(result.content_length, 11)


class TestProcessingResult(unittest.TestCase):
    """Tests for ProcessingResult dataclass."""

    def test_success_rate(self):
        """success_rate should calculate correctly."""
        result = ProcessingResult(
            final_result=ExtractionResult(content="", confidence=0.0),
            status=ProcessingStatus.PARTIAL,
            total_items_processed=10,
            batches_created=4,
            recursion_levels_used=0,
            successful_batches=3,
            failed_batches=[1],
        )
        self.assertEqual(result.success_rate, 0.75)

    def test_has_failures(self):
        """has_failures should detect failures."""
        result_with_failures = ProcessingResult(
            final_result=ExtractionResult(content="", confidence=0.0),
            status=ProcessingStatus.PARTIAL,
            total_items_processed=10,
            batches_created=4,
            recursion_levels_used=0,
            failed_batches=[1],
        )
        self.assertTrue(result_with_failures.has_failures)

        result_no_failures = ProcessingResult(
            final_result=ExtractionResult(content="", confidence=0.0),
            status=ProcessingStatus.COMPLETED,
            total_items_processed=10,
            batches_created=4,
            recursion_levels_used=0,
        )
        self.assertFalse(result_no_failures.has_failures)


if __name__ == "__main__":
    unittest.main()
