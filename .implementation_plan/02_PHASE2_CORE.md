# Phase 2: Core Query Generation Architecture

**Estimated Time**: 6-8 hours

## Objectives
1. Create data classes for query results
2. Implement serial multi-model query generator
3. Update QueryAgent with new methods
4. Maintain 100% backward compatibility

## New Files to Create

### 1. src/bmlibrarian/agents/query_generation/__init__.py
```python
"""Query generation module for multi-model support."""

from .data_types import QueryGenerationResult, MultiModelQueryResult
from .generator import MultiModelQueryGenerator

__all__ = ['QueryGenerationResult', 'MultiModelQueryResult', 'MultiModelQueryGenerator']
```

### 2. src/bmlibrarian/agents/query_generation/data_types.py

**Purpose**: Data classes for type safety

```python
from dataclasses import dataclass
from typing import List, Optional

@dataclass
class QueryGenerationResult:
    """Result from a single query generation attempt."""
    model: str
    query: str
    generation_time: float
    temperature: float
    attempt_number: int  # 1, 2, or 3
    error: Optional[str] = None

@dataclass
class MultiModelQueryResult:
    """Aggregated results from multi-model generation."""
    all_queries: List[QueryGenerationResult]
    unique_queries: List[str]  # De-duplicated
    model_count: int
    total_queries: int
    total_generation_time: float
    question: str
```

### 3. src/bmlibrarian/agents/query_generation/generator.py

**Purpose**: Core multi-model query generation logic (SERIAL execution)

**Key Implementation Details**:
```python
class MultiModelQueryGenerator:
    """Generates queries using multiple models (SERIAL execution)."""

    def __init__(self, ollama_host: str, callback: Optional[Callable] = None):
        self.ollama_host = ollama_host
        self.callback = callback

    def generate_queries(
        self,
        question: str,
        system_prompt: str,
        models: List[str],
        queries_per_model: int,
        temperature: float = 0.1,
        top_p: float = 0.9
    ) -> MultiModelQueryResult:
        """
        Generate queries SERIALLY (not parallel).

        Process:
        1. For each model (serial loop):
            a. For each attempt (1 to queries_per_model):
                - Generate one query
                - Track time and result
        2. De-duplicate queries (case-insensitive comparison)
        3. Return MultiModelQueryResult
        """
        all_queries = []
        start_time = time.time()

        for model in models:
            for attempt in range(1, queries_per_model + 1):
                result = self._generate_single_query(
                    model=model,
                    question=question,
                    system_prompt=system_prompt,
                    temperature=temperature,
                    top_p=top_p,
                    attempt=attempt
                )
                all_queries.append(result)

                if self.callback:
                    self.callback("query_generated", {
                        "model": model,
                        "attempt": attempt,
                        "query": result.query
                    })

        # De-duplicate
        unique_queries = self._deduplicate_queries([q.query for q in all_queries])

        return MultiModelQueryResult(
            all_queries=all_queries,
            unique_queries=unique_queries,
            model_count=len(models),
            total_queries=len(all_queries),
            total_generation_time=time.time() - start_time,
            question=question
        )

    def _generate_single_query(self, ...) -> QueryGenerationResult:
        """Generate single query using BaseAgent._make_ollama_request logic."""
        # Copy from QueryAgent.convert_question() but return QueryGenerationResult
        pass

    def _deduplicate_queries(self, queries: List[str]) -> List[str]:
        """Remove duplicate queries (case-insensitive, normalized)."""
        seen = set()
        unique = []
        for q in queries:
            normalized = q.lower().strip()
            if normalized not in seen:
                seen.add(normalized)
                unique.append(q)
        return unique
```

## Files to Modify

### 4. src/bmlibrarian/agents/query_agent.py

**Add new method** (around line 398, after find_abstracts):

```python
def convert_question_multi_model(
    self,
    question: str
) -> 'MultiModelQueryResult':
    """
    Convert question using multiple models.

    Returns:
        MultiModelQueryResult with all queries and metadata
    """
    from bmlibrarian.config import get_query_generation_config
    from .query_generation import MultiModelQueryGenerator

    # Get config
    qg_config = get_query_generation_config()

    # Check if multi-model enabled
    if not qg_config.get('multi_model_enabled', False):
        # Fallback: single model, single query
        single_query = self.convert_question(question)
        from .query_generation.data_types import QueryGenerationResult, MultiModelQueryResult

        single_result = QueryGenerationResult(
            model=self.model,
            query=single_query,
            generation_time=0.0,
            temperature=self.temperature,
            attempt_number=1
        )

        return MultiModelQueryResult(
            all_queries=[single_result],
            unique_queries=[single_query],
            model_count=1,
            total_queries=1,
            total_generation_time=0.0,
            question=question
        )

    # Multi-model generation (SERIAL)
    generator = MultiModelQueryGenerator(self.host, self.callback)
    return generator.generate_queries(
        question=question,
        system_prompt=self.system_prompt,
        models=qg_config['models'],
        queries_per_model=qg_config['queries_per_model'],
        temperature=self.temperature,
        top_p=self.top_p
    )
```

**DO NOT modify** existing methods:
- `convert_question()` - unchanged
- `find_abstracts()` - unchanged
- Keep 100% backward compatibility

## Testing Phase 2

### Unit Test
Create `tests/test_multi_model_query_generation.py`:

```python
def test_single_model_generation():
    """Test with 1 model, 1 query (backward compatible)."""
    # Should behave like original convert_question()

def test_multi_model_serial_generation():
    """Test with 3 models, 1 query each."""
    # Should generate 3 queries serially

def test_query_deduplication():
    """Test duplicate queries are removed."""
    # Generate same query twice, should dedupe

def test_multi_query_per_model():
    """Test 2 models, 2 queries each = 4 total."""
    pass
```

## Completion Criteria
- [x] Data types created
- [x] MultiModelQueryGenerator implemented (SERIAL)
- [x] QueryAgent.convert_question_multi_model() added
- [x] Backward compatibility verified
- [x] Unit tests pass

## Next Step
Update `00_OVERVIEW.md`, read `03_PHASE3_DATABASE.md`.

## Key Implementation Notes
- **SERIAL execution only** - simple for-loops
- **No ThreadPoolExecutor** - not needed for local instances
- **De-duplication**: case-insensitive string comparison
- **Backward compatible**: Original methods unchanged
