"""
Abstract Base Class for Iterative Context Processing

This module provides the abstract base class for hierarchical map-reduce
context processing. Subclasses implement specific extraction logic while
the base class handles batching, recursion, and consolidation.

The pattern solves the problem of processing content that exceeds LLM
context limits by:
1. Batching items to fit within context limits
2. Extracting relevant information from each batch
3. Recursively consolidating extracted results until they fit

This is a generalization of patterns found in:
- Citation extraction (processing documents iteratively)
- Semantic search consolidation (combining chunk results)
- Document interrogation (chunking and synthesis)
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional, Tuple

from .data_types import (
    Batch,
    ExtractionResult,
    ProcessingConfig,
    ProcessingResult,
    ProcessingStatus,
    ProgressInfo,
)

logger = logging.getLogger(__name__)


# Type alias for progress callbacks
ProgressCallback = Callable[[ProgressInfo], None]


class IterativeContextProcessor(ABC):
    """
    Abstract base class for hierarchical context processing.

    Subclasses implement the extraction logic; this class handles:
    - Batching items to fit within context limits
    - Recursive consolidation of extracted results
    - Progress tracking and error handling

    The processing algorithm:
    1. Format and batch items to fit within max_context_chars
    2. Extract from each batch → yields list of ExtractionResults
    3. If results fit in single context → return consolidated
    4. Otherwise, recursively process the results as new items

    Example subclass implementation:
        class SemanticChunkProcessor(IterativeContextProcessor):
            def format_item(self, item: Tuple[str, float], index: int) -> str:
                text, score = item
                return f"[Chunk {index + 1}, Score: {score:.2f}]\\n{text}"

            def extract_from_batch(self, batch_content, query, metadata):
                # Use LLM to extract key information from batch
                ...
    """

    def __init__(
        self,
        config: Optional[ProcessingConfig] = None,
        progress_callback: Optional[ProgressCallback] = None,
    ):
        """
        Initialize the context processor.

        Args:
            config: Processing configuration. Uses defaults if not provided.
            progress_callback: Optional callback for progress updates.
        """
        self.config = config or ProcessingConfig()
        self.progress_callback = progress_callback
        self._processing_stats: Dict[str, Any] = {}

    @abstractmethod
    def format_item(self, item: Any, index: int) -> str:
        """
        Format a single item for inclusion in a batch.

        Subclasses must implement this to convert items to strings
        suitable for LLM processing.

        Args:
            item: The item to format (type depends on processor).
            index: The index of this item in the current batch.

        Returns:
            Formatted string representation of the item.
        """
        pass

    @abstractmethod
    def extract_from_batch(
        self,
        batch_content: str,
        query: str,
        batch_metadata: Dict[str, Any],
    ) -> ExtractionResult:
        """
        Extract relevant information from a single batch.

        Subclasses must implement this to perform the actual extraction
        using an LLM or other processing method.

        Args:
            batch_content: The formatted, concatenated batch content.
            query: The query or question guiding the extraction.
            batch_metadata: Metadata about the batch (index, item count, etc.).

        Returns:
            ExtractionResult containing extracted content and metadata.
        """
        pass

    def _report_progress(
        self,
        stage: str,
        current_item: int = 0,
        total_items: int = 0,
        current_batch: int = 0,
        total_batches: int = 0,
        recursion_level: int = 0,
        message: str = "",
    ) -> None:
        """
        Report progress through the callback if available.

        Args:
            stage: Current processing stage name.
            current_item: Current item index.
            total_items: Total items to process.
            current_batch: Current batch index.
            total_batches: Total batches.
            recursion_level: Current recursion depth.
            message: Human-readable progress message.
        """
        if self.progress_callback:
            info = ProgressInfo(
                stage=stage,
                current_item=current_item,
                total_items=total_items,
                current_batch=current_batch,
                total_batches=total_batches,
                recursion_level=recursion_level,
                message=message,
            )
            try:
                self.progress_callback(info)
            except Exception as e:
                logger.warning(f"Progress callback failed: {e}")

    def _create_batches(
        self,
        items: List[Any],
        config: ProcessingConfig,
    ) -> List[Batch]:
        """
        Group items into batches that fit within max_context_chars.

        Uses greedy bin-packing: add items to current batch until
        the limit would be exceeded.

        Args:
            items: List of items to batch.
            config: Processing configuration with limits.

        Returns:
            List of Batch objects containing grouped items.
        """
        if not items:
            return []

        batches: List[Batch] = []
        current_items: List[Any] = []
        current_indices: List[int] = []
        current_chars = 0
        separator_len = len(config.separator)

        for idx, item in enumerate(items):
            # Format the item to get its character count
            formatted = self.format_item(item, len(current_items))
            item_chars = len(formatted)

            # Account for separator if not first item in batch
            separator_cost = separator_len if current_items else 0
            total_new_chars = item_chars + separator_cost

            # Would this item exceed the limit?
            if current_chars + total_new_chars > config.max_context_chars:
                # Save current batch (if not empty) and start new one
                if current_items:
                    batches.append(
                        Batch(
                            items=current_items,
                            item_indices=current_indices,
                            total_chars=current_chars,
                            batch_index=len(batches),
                        )
                    )
                # Start new batch with this item
                current_items = [item]
                current_indices = [idx]
                current_chars = item_chars
            else:
                # Add to current batch
                current_items.append(item)
                current_indices.append(idx)
                current_chars += total_new_chars

        # Don't forget the last batch
        if current_items:
            batches.append(
                Batch(
                    items=current_items,
                    item_indices=current_indices,
                    total_chars=current_chars,
                    batch_index=len(batches),
                )
            )

        logger.debug(
            f"Created {len(batches)} batches from {len(items)} items "
            f"(max_chars={config.max_context_chars})"
        )

        return batches

    def _format_batch_content(
        self,
        batch: Batch,
        config: ProcessingConfig,
    ) -> str:
        """
        Format all items in a batch into a single string.

        Args:
            batch: The batch to format.
            config: Processing configuration.

        Returns:
            Concatenated string of all formatted items.
        """
        formatted_items = [
            self.format_item(item, idx) for idx, item in enumerate(batch.items)
        ]
        return config.separator.join(formatted_items)

    def _merge_results(
        self,
        results: List[ExtractionResult],
        config: ProcessingConfig,
        recursion_level: int = 0,
    ) -> ExtractionResult:
        """
        Merge multiple extraction results into a single result.

        Combines content with separators and aggregates metadata.

        Args:
            results: List of ExtractionResult objects to merge.
            config: Processing configuration.
            recursion_level: Current recursion depth.

        Returns:
            Merged ExtractionResult.
        """
        if not results:
            return ExtractionResult(
                content="",
                metadata={},
                source_indices=[],
                confidence=0.0,
                recursion_level=recursion_level,
            )

        if len(results) == 1:
            return results[0]

        # Merge content
        merged_content = config.separator.join(r.content for r in results if r.content)

        # Aggregate source indices
        all_sources: List[int] = []
        for r in results:
            all_sources.extend(r.source_indices)

        # Calculate average confidence
        confidences = [r.confidence for r in results if r.confidence > 0]
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

        # Merge metadata if configured to preserve it
        merged_metadata: Dict[str, Any] = {}
        if config.preserve_metadata:
            merged_metadata["merged_from"] = len(results)
            merged_metadata["source_metadata"] = [r.metadata for r in results]

        return ExtractionResult(
            content=merged_content,
            metadata=merged_metadata,
            source_indices=all_sources,
            confidence=avg_confidence,
            recursion_level=recursion_level,
        )

    def _process_level(
        self,
        items: List[Any],
        query: str,
        config: ProcessingConfig,
        recursion_level: int,
        intermediate_results: Optional[List[List[ExtractionResult]]],
    ) -> Tuple[List[ExtractionResult], bool]:
        """
        Process items at a single recursion level.

        Args:
            items: Items to process.
            query: Query guiding extraction.
            config: Processing configuration.
            recursion_level: Current recursion depth.
            intermediate_results: List to store intermediate results.

        Returns:
            Tuple of (extraction_results, needs_recursion).
        """
        # Create batches
        batches = self._create_batches(items, config)

        self._report_progress(
            stage="batching",
            total_items=len(items),
            total_batches=len(batches),
            recursion_level=recursion_level,
            message=f"Created {len(batches)} batches from {len(items)} items",
        )

        # Extract from each batch
        extraction_results: List[ExtractionResult] = []

        for batch in batches:
            self._report_progress(
                stage="extracting",
                current_batch=batch.batch_index + 1,
                total_batches=len(batches),
                recursion_level=recursion_level,
                message=f"Processing batch {batch.batch_index + 1}/{len(batches)}",
            )

            batch_content = self._format_batch_content(batch, config)
            batch_metadata = {
                "batch_index": batch.batch_index,
                "item_count": batch.size,
                "total_chars": batch.total_chars,
                "item_indices": batch.item_indices,
                "recursion_level": recursion_level,
            }

            try:
                result = self.extract_from_batch(
                    batch_content=batch_content,
                    query=query,
                    batch_metadata=batch_metadata,
                )
                result.batch_index = batch.batch_index
                result.recursion_level = recursion_level
                result.source_indices = batch.item_indices
                extraction_results.append(result)
            except Exception as e:
                logger.error(
                    f"Extraction failed for batch {batch.batch_index} "
                    f"at level {recursion_level}: {e}"
                )
                # Create a failed result to preserve partial progress
                extraction_results.append(
                    ExtractionResult(
                        content="",
                        metadata={"error": str(e)},
                        source_indices=batch.item_indices,
                        confidence=0.0,
                        batch_index=batch.batch_index,
                        recursion_level=recursion_level,
                    )
                )

        # Store intermediate results if requested
        if intermediate_results is not None:
            intermediate_results.append(extraction_results)

        # Check if consolidation is needed
        total_content_length = sum(len(r.content) for r in extraction_results)
        total_with_separators = total_content_length + (
            len(config.separator) * max(0, len(extraction_results) - 1)
        )

        needs_recursion = total_with_separators > config.max_context_chars

        return extraction_results, needs_recursion

    def process(
        self,
        items: List[Any],
        query: str,
        config: Optional[ProcessingConfig] = None,
        store_intermediate: bool = False,
    ) -> ProcessingResult:
        """
        Process items through iterative batching and consolidation.

        Main entry point for the hierarchical map-reduce algorithm.

        Args:
            items: List of items to process.
            query: Query or question guiding the extraction.
            config: Optional config override (uses instance config if None).
            store_intermediate: If True, stores intermediate results for debugging.

        Returns:
            ProcessingResult containing final result and statistics.
        """
        config = config or self.config
        intermediate_results: Optional[List[List[ExtractionResult]]] = (
            [] if store_intermediate else None
        )

        # Reset statistics
        self._processing_stats = {
            "total_items": len(items),
            "batches_per_level": [],
            "items_per_level": [len(items)],
        }

        # Handle empty input
        if not items:
            return ProcessingResult(
                final_result=ExtractionResult(
                    content="",
                    metadata={},
                    source_indices=[],
                    confidence=0.0,
                ),
                status=ProcessingStatus.COMPLETED,
                total_items_processed=0,
                batches_created=0,
                recursion_levels_used=0,
                intermediate_results=intermediate_results,
                processing_stats=self._processing_stats,
            )

        self._report_progress(
            stage="starting",
            total_items=len(items),
            message=f"Starting processing of {len(items)} items",
        )

        # Process iteratively
        current_items = items
        recursion_level = 0
        total_batches = 0
        status = ProcessingStatus.COMPLETED

        while True:
            # Process current level
            results, needs_recursion = self._process_level(
                items=current_items,
                query=query,
                config=config,
                recursion_level=recursion_level,
                intermediate_results=intermediate_results,
            )

            # Track statistics
            batches_at_level = len(
                self._create_batches(current_items, config)
            )
            self._processing_stats["batches_per_level"].append(batches_at_level)
            total_batches += batches_at_level

            # Check if we're done
            if not needs_recursion:
                # Results fit - merge and return
                final_result = self._merge_results(results, config, recursion_level)
                break

            # Check recursion limit
            if recursion_level >= config.max_recursion_depth:
                logger.warning(
                    f"Max recursion depth ({config.max_recursion_depth}) reached. "
                    f"Returning truncated result."
                )
                status = ProcessingStatus.TRUNCATED
                final_result = self._merge_results(results, config, recursion_level)
                break

            # Check minimum items for recursion
            if len(results) < config.min_items_for_recursion:
                logger.info(
                    f"Below minimum items for recursion ({len(results)} < "
                    f"{config.min_items_for_recursion}). Returning merged result."
                )
                final_result = self._merge_results(results, config, recursion_level)
                break

            # Prepare for next level: treat results as new items
            self._report_progress(
                stage="recursing",
                recursion_level=recursion_level + 1,
                message=f"Recursing to level {recursion_level + 1} "
                f"with {len(results)} results",
            )

            # Convert ExtractionResults to items for next level
            # Use (content, metadata) tuples as items
            current_items = [(r.content, r.metadata) for r in results]
            self._processing_stats["items_per_level"].append(len(current_items))
            recursion_level += 1

        self._report_progress(
            stage="complete",
            recursion_level=recursion_level,
            message=f"Processing complete after {recursion_level} recursion levels",
        )

        return ProcessingResult(
            final_result=final_result,
            status=status,
            total_items_processed=len(items),
            batches_created=total_batches,
            recursion_levels_used=recursion_level,
            intermediate_results=intermediate_results,
            processing_stats=self._processing_stats,
        )

    def format_consolidated_item(
        self,
        item: Tuple[str, Dict[str, Any]],
        index: int,
    ) -> str:
        """
        Format a consolidated item (content, metadata tuple) for recursion.

        This is called when processing ExtractionResults from a previous
        level as items for the next consolidation pass.

        Override this method if you need custom formatting for consolidated items.

        Args:
            item: Tuple of (content, metadata) from previous level.
            index: Index of this item in the current batch.

        Returns:
            Formatted string representation.
        """
        content, metadata = item
        # Default: just return the content
        # Subclasses can override to include metadata
        return content
