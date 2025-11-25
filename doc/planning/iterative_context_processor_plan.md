# Iterative Context Processor Implementation Plan

**Created**: 2025-11-25
**Updated**: 2025-11-25
**Status**: Phase 3 Complete (PRISMA Integration)
**Related Issue**: PR #175 - Memory Management / Context Overstuffing

## Executive Summary

This document outlines the implementation plan for a generalized iterative context processing abstraction. The pattern addresses the problem of LLM context limits by implementing a hierarchical map-reduce approach that processes content in batches, extracts relevant information, and recursively consolidates results.

## Problem Statement

### Current Issue

In `prisma2020_agent.py` (lines 1575-1580), context is truncated to fit within limits:

```python
# VIOLATES NO TRUNCATION RULE
context = "\n\n---\n\n".join(
    f"[Chunk Score: {score:.2f}]\n{text}"
    for text, score in chunks
)
# Later truncated with [:SEMANTIC_CONTEXT_MAX_CHARS]
```

This truncation loses information. The correct approach is iterative extraction.

### Pattern Description

The solution implements a hierarchical map-reduce pattern:

```
Input Items → [Batch 1] → Extract → Result 1  ┐
            → [Batch 2] → Extract → Result 2  │→ Stack
            → [Batch N] → Extract → Result N  ┘
                                               ↓
                              [If stack > limit: recurse]
                                               ↓
                              Final Consolidated Result
```

**Key Principle**: Instead of truncating, we iteratively extract key information, preserving semantic content while reducing size.

## Completed Work (Phase 1)

### 1.1 Document ID Validation Fix

**File**: `src/bmlibrarian/agents/prisma2020_agent.py:1237-1245`

Added parameter validation before database operations:

```python
# Validate document_id parameter before any database operations
if document_id is None:
    logger.warning("get_document_text_status called with None document_id")
    return None
if not isinstance(document_id, int) or document_id <= 0:
    logger.warning(
        f"Invalid document_id: {document_id} (must be positive integer)"
    )
    return None
```

### 1.2 Module Structure Created

**Location**: `src/bmlibrarian/agents/context_processor/`

```
context_processor/
├── __init__.py      # Module exports
├── data_types.py    # Core dataclasses
└── base.py          # Abstract base class with algorithm
```

### 1.3 Data Types (`data_types.py`)

Core dataclasses for the processing system:

| Class | Purpose |
|-------|---------|
| `ProcessingConfig` | Configuration (max chars, recursion depth, etc.) |
| `ExtractionResult` | Result from a single extraction pass |
| `Batch` | Group of items to process together |
| `ProcessingResult` | Complete result with statistics |
| `ProgressInfo` | Progress information for callbacks |
| `ProcessingStatus` | Enum for processing states |

**Configuration Constants**:
- `DEFAULT_MAX_CONTEXT_CHARS = 4000`
- `DEFAULT_MAX_RECURSION_DEPTH = 5`
- `DEFAULT_MIN_ITEMS_FOR_RECURSION = 2`
- `DEFAULT_SEPARATOR = "\n\n---\n\n"`

### 1.4 Abstract Base Class (`base.py`)

The `IterativeContextProcessor` class provides:

1. **Batching Algorithm** (`_create_batches`):
   - Greedy bin-packing of items into batches
   - Respects `max_context_chars` limit
   - Tracks item indices for traceability

2. **Recursive Processing** (`process`):
   - Main entry point
   - Handles empty input gracefully
   - Tracks statistics per level
   - Returns `ProcessingResult` with full metadata

3. **Abstract Methods** (to be implemented by subclasses):
   - `format_item(item, index)` - Format item for batch
   - `extract_from_batch(content, query, metadata)` - LLM extraction

4. **Progress Tracking**:
   - Callback-based progress reporting
   - Stage-aware progress info
   - Non-blocking (catches callback errors)

## Completed Work (Phase 2)

### 2.1 Oversized Item Handling

Added `OversizedItemStrategy` enum with four strategies:
- `SPLIT`: Split oversized items into smaller pieces (default)
- `TRUNCATE`: Truncate to max_context_chars
- `SKIP`: Skip oversized items (logs warning)
- `FAIL`: Raise error for strict mode

Added `split_oversized_item()` method with default string splitting and overlap support.

### 2.2 Consolidation Strategies

Added `ConsolidationStrategy` enum:
- `CONCATENATE`: Simple concatenation with separator (default)
- `WEIGHTED`: Sort by confidence, highest first
- `DEDUPLICATE`: Remove duplicate content before merging

### 2.3 Error Recovery

Enhanced error handling with:
- `continue_on_error` config option
- `ProcessingStatus.PARTIAL` for mixed success/failure
- Tracking of `failed_batches` and `skipped_items`
- `success_rate` property on `ProcessingResult`

### 2.4 Unit Tests

Created `tests/test_context_processor_base.py` with 36 comprehensive tests covering:
- Configuration validation
- Batching algorithm
- Oversized item strategies
- Consolidation strategies
- Error recovery modes
- Progress tracking
- Full processing workflow

## Completed Work (Phase 3)

### 3.1 SemanticChunkProcessor

Created `semantic_chunk_processor.py` with:
- `SemanticChunkProcessor` class for processing (text, score) tuples
- Custom prompt templates for extraction and consolidation
- Structured JSON output mode (optional)
- `create_prisma_chunk_processor()` factory for PRISMA-specific configuration

### 3.2 PRISMA Agent Refactoring

Modified `prisma2020_agent.py`:
- Added `_process_semantic_chunks_for_context()` method
- Added `_fallback_first_chunk()` for graceful degradation
- Replaced truncation with iterative context processor
- **Removed truncation at line 1443** - context no longer truncated

### 3.3 Integration Tests

Created `tests/test_semantic_chunk_processor.py` with 20 tests covering:
- Item formatting (original chunks, consolidated tuples, strings)
- Oversized chunk splitting
- LLM extraction calls
- Prompt template selection by recursion level
- Error handling and graceful degradation
- PRISMA-specific processor factory
- Structured output parsing

## Remaining Work (Future Phases)

### Phase 4: Citation Agent Integration (Optional)

| Task | File | Description | Effort |
|------|------|-------------|--------|
| 4.1 | `context_processor/citation_consolidator.py` | Consolidate large citation sets | 1 hr |
| 4.2 | `reporting_agent.py` | Integrate with report generation | 1 hr |
| 4.3 | `tests/test_citation_consolidator.py` | Integration tests | 1 hr |

**Use Case**: When generating reports with many citations, consolidate them in batches to avoid context overflow.

### Phase 5: Documentation

| Task | File | Description | Effort |
|------|------|-------------|--------|
| 5.1 | `doc/users/iterative_context_processing.md` | User guide with examples | 30 min |
| 5.2 | `doc/developers/context_processor_system.md` | Technical documentation | 45 min |
| 5.3 | `doc/llm/context_processor_patterns.md` | AI assistant guidance | 30 min |

## Architecture Decisions

### Why Hierarchical Map-Reduce?

1. **No Information Loss**: Unlike truncation, extraction preserves semantic content
2. **Scalable**: Works for any amount of content through recursion
3. **Configurable**: Limits and strategies are adjustable per use case
4. **Traceable**: Source indices preserved through consolidation

### Why Abstract Base Class?

1. **Reusability**: Same algorithm for different item types
2. **Testability**: Mock implementations for unit testing
3. **Separation of Concerns**: Algorithm vs. extraction logic
4. **Type Safety**: Clear interfaces with type hints

### Configuration Choices

| Parameter | Default | Rationale |
|-----------|---------|-----------|
| `max_context_chars` | 4000 | Conservative limit for prompt + response |
| `max_recursion_depth` | 5 | Prevents infinite loops, allows 5 levels of consolidation |
| `min_items_for_recursion` | 2 | Don't recurse for single items |
| `separator` | `\n\n---\n\n` | Clear visual separation between items |

## Testing Strategy

### Unit Tests (Phase 2.4)

```python
class TestIterativeContextProcessor(unittest.TestCase):

    def test_single_item_no_batching(self):
        """Single item that fits returns without batching."""

    def test_multiple_items_single_batch(self):
        """Multiple items that fit create one batch."""

    def test_multiple_batches_no_recursion(self):
        """Items split into batches, results fit in context."""

    def test_recursive_consolidation(self):
        """Results require one level of recursive consolidation."""

    def test_max_recursion_depth_respected(self):
        """Processing stops at max_recursion_depth with TRUNCATED status."""

    def test_empty_items(self):
        """Empty input returns empty result with COMPLETED status."""

    def test_progress_callback_called(self):
        """Progress callback receives updates at each stage."""

    def test_extraction_error_handling(self):
        """Extraction failures don't crash processing."""
```

### Integration Tests (Phase 3.3)

```python
class TestSemanticChunkProcessor(unittest.TestCase):

    def test_prisma_semantic_search_integration(self):
        """Processor works with PRISMA agent semantic search."""

    def test_large_chunk_set_consolidation(self):
        """50+ chunks properly consolidated."""

    def test_llm_extraction_quality(self):
        """Extracted content preserves key information."""
```

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| LLM quality degrades with recursion | Medium | High | Add quality checks, limit recursion |
| Performance overhead | Low | Medium | Parallel batch processing (future) |
| Configuration complexity | Low | Low | Sensible defaults, validation |

## Success Criteria

1. **No Truncation**: Context is never cut off mid-content
2. **Information Preserved**: Key findings survive consolidation
3. **Configurable**: Users can adjust limits per use case
4. **Testable**: >90% code coverage on new modules
5. **Documented**: User and developer docs complete

## Timeline Estimate

| Phase | Tasks | Status | Actual Effort |
|-------|-------|--------|---------------|
| Phase 1 | Foundation | COMPLETE | 2.5 hours |
| Phase 2 | Algorithm Refinement | COMPLETE | 2.75 hours |
| Phase 3 | PRISMA Integration | COMPLETE | 3 hours |
| Phase 4 | Citation Integration | Optional | - |
| Phase 5 | Documentation | Pending | - |
| **Total (Phases 1-3)** | | **COMPLETE** | **8.25 hours** |

## Related Files

### Modified
- `src/bmlibrarian/agents/prisma2020_agent.py` - Document ID validation fix, iterative context processing integration

### Created (Phase 1)
- `src/bmlibrarian/agents/context_processor/__init__.py`
- `src/bmlibrarian/agents/context_processor/data_types.py`
- `src/bmlibrarian/agents/context_processor/base.py`
- `doc/planning/iterative_context_processor_plan.md` (this file)

### Created (Phase 2)
- `tests/test_context_processor_base.py` - 36 unit tests

### Created (Phase 3)
- `src/bmlibrarian/agents/context_processor/semantic_chunk_processor.py`
- `tests/test_semantic_chunk_processor.py` - 20 integration tests

### To Be Created (Future Phases)
- `src/bmlibrarian/agents/context_processor/citation_consolidator.py`
- `doc/users/iterative_context_processing.md`
- `doc/developers/context_processor_system.md`

## Appendix: Algorithm Pseudocode

```
FUNCTION process(items, query, config):
    IF items is empty:
        RETURN empty result with COMPLETED status

    current_items = items
    recursion_level = 0

    WHILE true:
        # Create batches that fit within context limit
        batches = create_batches(current_items, config.max_context_chars)

        # Extract from each batch
        results = []
        FOR each batch in batches:
            batch_content = format_and_join(batch.items)
            result = extract_from_batch(batch_content, query)
            results.append(result)

        # Check if consolidation fits in context
        total_size = sum(len(r.content) for r in results)

        IF total_size <= config.max_context_chars:
            # Done - merge and return
            RETURN merge_results(results)

        IF recursion_level >= config.max_recursion_depth:
            # Hit limit - return truncated
            RETURN merge_results(results) with TRUNCATED status

        IF len(results) < config.min_items_for_recursion:
            # Too few items to recurse
            RETURN merge_results(results)

        # Recurse: treat results as new items
        current_items = [(r.content, r.metadata) for r in results]
        recursion_level += 1
```
