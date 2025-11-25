"""
Data Types for Iterative Context Processing

This module defines the core dataclasses used by the iterative context
processor for handling large contexts that exceed LLM limits.

The hierarchical map-reduce pattern processes items in batches, extracts
relevant information, and recursively consolidates results until they
fit within the target context size.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from enum import Enum


class ProcessingStatus(Enum):
    """Status of a processing operation."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    TRUNCATED = "truncated"  # Max recursion reached, partial results
    PARTIAL = "partial"  # Some batches failed but others succeeded


class OversizedItemStrategy(Enum):
    """Strategy for handling items larger than max_context_chars."""

    SPLIT = "split"  # Split the item into smaller pieces (requires split_oversized_item)
    TRUNCATE = "truncate"  # Truncate to max_context_chars (loses information)
    SKIP = "skip"  # Skip the item entirely (logs warning)
    FAIL = "fail"  # Raise an error (strict mode)


class ConsolidationStrategy(Enum):
    """Strategy for merging extraction results."""

    CONCATENATE = "concatenate"  # Simple concatenation with separator
    WEIGHTED = "weighted"  # Weight by confidence scores
    DEDUPLICATE = "deduplicate"  # Remove duplicate content before merging


# Default configuration constants
DEFAULT_MAX_CONTEXT_CHARS = 4000
DEFAULT_OVERLAP_CHARS = 0
DEFAULT_MAX_RECURSION_DEPTH = 5
DEFAULT_MIN_ITEMS_FOR_RECURSION = 2
DEFAULT_SEPARATOR = "\n\n---\n\n"


@dataclass
class ProcessingConfig:
    """
    Configuration for iterative context processing.

    Controls batching, recursion limits, and formatting options.

    Attributes:
        max_context_chars: Maximum characters allowed per batch/context window.
            Items are grouped into batches that fit within this limit.
        overlap_chars: Number of characters to overlap between batches when
            processing continuous text. Set to 0 for discrete items.
        max_recursion_depth: Maximum levels of recursive consolidation allowed.
            Prevents infinite loops when content cannot be sufficiently reduced.
        min_items_for_recursion: Minimum number of items required before
            recursive consolidation is attempted. Below this, results are
            returned even if they exceed the context limit.
        separator: String used to separate items within a batch.
        preserve_metadata: If True, metadata from source items is preserved
            through consolidation levels.
        oversized_item_strategy: How to handle items larger than max_context_chars.
        consolidation_strategy: How to merge extraction results.
        continue_on_error: If True, continue processing when batch extraction fails.
            If False, fail immediately on first error.
        min_confidence_threshold: Minimum confidence score to include a result
            in consolidation. Results below this are filtered out.
    """

    max_context_chars: int = DEFAULT_MAX_CONTEXT_CHARS
    overlap_chars: int = DEFAULT_OVERLAP_CHARS
    max_recursion_depth: int = DEFAULT_MAX_RECURSION_DEPTH
    min_items_for_recursion: int = DEFAULT_MIN_ITEMS_FOR_RECURSION
    separator: str = DEFAULT_SEPARATOR
    preserve_metadata: bool = True
    oversized_item_strategy: OversizedItemStrategy = OversizedItemStrategy.SPLIT
    consolidation_strategy: ConsolidationStrategy = ConsolidationStrategy.CONCATENATE
    continue_on_error: bool = True
    min_confidence_threshold: float = 0.0

    def __post_init__(self) -> None:
        """Validate configuration parameters."""
        if self.max_context_chars <= 0:
            raise ValueError(
                f"max_context_chars must be positive, got {self.max_context_chars}"
            )
        if self.overlap_chars < 0:
            raise ValueError(
                f"overlap_chars must be non-negative, got {self.overlap_chars}"
            )
        if self.max_recursion_depth < 0:
            raise ValueError(
                f"max_recursion_depth must be non-negative, got {self.max_recursion_depth}"
            )
        if self.min_items_for_recursion < 1:
            raise ValueError(
                f"min_items_for_recursion must be at least 1, got {self.min_items_for_recursion}"
            )
        if not 0.0 <= self.min_confidence_threshold <= 1.0:
            raise ValueError(
                f"min_confidence_threshold must be between 0.0 and 1.0, "
                f"got {self.min_confidence_threshold}"
            )


@dataclass
class ExtractionResult:
    """
    Result from a single extraction pass.

    Represents the extracted/summarized content from processing a batch
    of items. Can be used as input for subsequent consolidation passes.

    Attributes:
        content: The extracted or summarized content from this batch.
        metadata: Additional metadata to preserve through processing.
            May include source information, scores, or processing details.
        source_indices: Indices of the original items that contributed
            to this result. Enables traceability back to source data.
        confidence: Confidence score for the extraction (0.0 to 1.0).
            May be set by the LLM or computed from source item scores.
        batch_index: Index of the batch this result came from (if applicable).
        recursion_level: The recursion depth at which this result was created.
            Level 0 is the initial extraction, higher levels are consolidations.
        is_error: True if this result represents a failed extraction.
        error_message: Error message if extraction failed.
    """

    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    source_indices: List[int] = field(default_factory=list)
    confidence: float = 1.0
    batch_index: Optional[int] = None
    recursion_level: int = 0
    is_error: bool = False
    error_message: Optional[str] = None

    @property
    def content_length(self) -> int:
        """Get the length of the content in characters."""
        return len(self.content)

    @property
    def is_valid(self) -> bool:
        """Check if this is a valid (non-error) result with content."""
        return not self.is_error and bool(self.content)

    def __repr__(self) -> str:
        """Provide a concise string representation."""
        if self.is_error:
            return f"ExtractionResult(ERROR: {self.error_message})"
        preview = self.content[:50] + "..." if len(self.content) > 50 else self.content
        return (
            f"ExtractionResult(content='{preview}', "
            f"confidence={self.confidence:.2f}, "
            f"sources={len(self.source_indices)})"
        )


@dataclass
class Batch:
    """
    A batch of items to be processed together.

    Groups items that fit within the context limit for a single
    LLM extraction pass.

    Attributes:
        items: List of items in this batch (type depends on processor).
        item_indices: Original indices of items in the source list.
        total_chars: Total character count of formatted items in batch.
        batch_index: Sequential index of this batch in the processing run.
    """

    items: List[Any]
    item_indices: List[int] = field(default_factory=list)
    total_chars: int = 0
    batch_index: int = 0

    @property
    def size(self) -> int:
        """Get the number of items in this batch."""
        return len(self.items)

    def __repr__(self) -> str:
        """Provide a concise string representation."""
        return (
            f"Batch(items={self.size}, chars={self.total_chars}, "
            f"index={self.batch_index})"
        )


@dataclass
class ProcessingResult:
    """
    Complete result from iterative context processing.

    Contains the final consolidated result along with processing
    statistics and any intermediate results for debugging.

    Attributes:
        final_result: The final consolidated ExtractionResult.
        status: Processing status (completed, truncated, failed, partial).
        total_items_processed: Total number of original items processed.
        batches_created: Number of batches created in the initial pass.
        recursion_levels_used: Number of recursive consolidation passes.
        intermediate_results: Optional list of results from each level
            for debugging or analysis.
        error_message: Error message if processing failed.
        processing_stats: Additional statistics about the processing run.
        failed_batches: List of batch indices that failed extraction.
        skipped_items: List of item indices that were skipped (oversized).
        successful_batches: Number of batches that succeeded.
    """

    final_result: ExtractionResult
    status: ProcessingStatus
    total_items_processed: int
    batches_created: int
    recursion_levels_used: int
    intermediate_results: Optional[List[List[ExtractionResult]]] = None
    error_message: Optional[str] = None
    processing_stats: Dict[str, Any] = field(default_factory=dict)
    failed_batches: List[int] = field(default_factory=list)
    skipped_items: List[int] = field(default_factory=list)
    successful_batches: int = 0

    @property
    def is_complete(self) -> bool:
        """Check if processing completed without truncation or failure."""
        return self.status == ProcessingStatus.COMPLETED

    @property
    def is_partial(self) -> bool:
        """Check if processing completed with some failures."""
        return self.status == ProcessingStatus.PARTIAL

    @property
    def has_failures(self) -> bool:
        """Check if any batches failed or items were skipped."""
        return bool(self.failed_batches) or bool(self.skipped_items)

    @property
    def content(self) -> str:
        """Convenience accessor for the final result content."""
        return self.final_result.content

    @property
    def success_rate(self) -> float:
        """Calculate the success rate of batch processing (0.0 to 1.0)."""
        if self.batches_created == 0:
            return 1.0
        return self.successful_batches / self.batches_created

    def __repr__(self) -> str:
        """Provide a concise string representation."""
        base = (
            f"ProcessingResult(status={self.status.value}, "
            f"items={self.total_items_processed}, "
            f"batches={self.batches_created}, "
            f"recursion={self.recursion_levels_used}"
        )
        if self.failed_batches:
            base += f", failed={len(self.failed_batches)}"
        if self.skipped_items:
            base += f", skipped={len(self.skipped_items)}"
        return base + ")"


@dataclass
class ProgressInfo:
    """
    Progress information for callbacks during processing.

    Enables UI feedback during long-running processing operations.

    Attributes:
        stage: Current processing stage name.
        current_item: Current item index being processed.
        total_items: Total number of items to process.
        current_batch: Current batch index.
        total_batches: Total number of batches.
        recursion_level: Current recursion depth.
        message: Human-readable progress message.
    """

    stage: str
    current_item: int = 0
    total_items: int = 0
    current_batch: int = 0
    total_batches: int = 0
    recursion_level: int = 0
    message: str = ""

    @property
    def progress_percent(self) -> float:
        """Calculate progress as a percentage (0.0 to 100.0)."""
        if self.total_items == 0:
            return 0.0
        return (self.current_item / self.total_items) * 100.0

    def __repr__(self) -> str:
        """Provide a concise string representation."""
        return (
            f"ProgressInfo(stage='{self.stage}', "
            f"progress={self.progress_percent:.1f}%, "
            f"level={self.recursion_level})"
        )
