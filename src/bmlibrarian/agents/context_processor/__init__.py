"""
Iterative Context Processor Module

Provides a reusable abstraction for processing content that exceeds
LLM context limits through hierarchical map-reduce batching.

The pattern:
1. Batch items to fit within context limits
2. Extract relevant information from each batch
3. Recursively consolidate results until they fit

Usage:
    from bmlibrarian.agents.context_processor import (
        IterativeContextProcessor,
        ProcessingConfig,
        ExtractionResult,
        ProcessingResult,
    )

    class MyProcessor(IterativeContextProcessor):
        def format_item(self, item, index):
            return f"[{index}] {item}"

        def extract_from_batch(self, batch_content, query, metadata):
            # Use LLM to extract relevant info
            ...

    processor = MyProcessor()
    result = processor.process(items, query="What are the key findings?")
"""

from .base import IterativeContextProcessor, ProgressCallback
from .data_types import (
    Batch,
    ExtractionResult,
    ProcessingConfig,
    ProcessingResult,
    ProcessingStatus,
    ProgressInfo,
    # Constants
    DEFAULT_MAX_CONTEXT_CHARS,
    DEFAULT_MAX_RECURSION_DEPTH,
    DEFAULT_MIN_ITEMS_FOR_RECURSION,
    DEFAULT_OVERLAP_CHARS,
    DEFAULT_SEPARATOR,
)

__all__ = [
    # Core classes
    "IterativeContextProcessor",
    "ProgressCallback",
    # Data types
    "Batch",
    "ExtractionResult",
    "ProcessingConfig",
    "ProcessingResult",
    "ProcessingStatus",
    "ProgressInfo",
    # Constants
    "DEFAULT_MAX_CONTEXT_CHARS",
    "DEFAULT_MAX_RECURSION_DEPTH",
    "DEFAULT_MIN_ITEMS_FOR_RECURSION",
    "DEFAULT_OVERLAP_CHARS",
    "DEFAULT_SEPARATOR",
]
