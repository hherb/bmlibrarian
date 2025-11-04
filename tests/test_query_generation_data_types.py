"""Unit tests for query generation data types."""

import pytest
from bmlibrarian.agents.query_generation.data_types import (
    QueryGenerationResult,
    MultiModelQueryResult
)


def test_query_generation_result_creation():
    """Test QueryGenerationResult creation with all fields."""
    result = QueryGenerationResult(
        model="test-model",
        query="test & query",
        generation_time=0.5,
        temperature=0.1,
        attempt_number=1,
        error=None
    )

    assert result.model == "test-model"
    assert result.query == "test & query"
    assert result.generation_time == 0.5
    assert result.temperature == 0.1
    assert result.attempt_number == 1
    assert result.error is None


def test_query_generation_result_with_error():
    """Test QueryGenerationResult with error."""
    result = QueryGenerationResult(
        model="test-model",
        query="",
        generation_time=0.0,
        temperature=0.1,
        attempt_number=1,
        error="Connection failed"
    )

    assert result.error == "Connection failed"
    assert result.query == ""


def test_multi_model_query_result_creation():
    """Test MultiModelQueryResult aggregation."""
    query_results = [
        QueryGenerationResult(
            model="model1",
            query="aspirin & heart",
            generation_time=0.5,
            temperature=0.1,
            attempt_number=1
        ),
        QueryGenerationResult(
            model="model2",
            query="aspirin & cardiac",
            generation_time=0.6,
            temperature=0.1,
            attempt_number=1
        )
    ]

    result = MultiModelQueryResult(
        all_queries=query_results,
        unique_queries=["aspirin & heart", "aspirin & cardiac"],
        model_count=2,
        total_queries=2,
        total_generation_time=1.1,
        question="What are aspirin benefits?"
    )

    assert result.model_count == 2
    assert result.total_queries == 2
    assert len(result.unique_queries) == 2
    assert result.total_generation_time == 1.1
    assert result.question == "What are aspirin benefits?"


def test_multi_model_query_result_with_duplicates():
    """Test that MultiModelQueryResult tracks both all and unique queries."""
    query_results = [
        QueryGenerationResult(
            model="model1",
            query="aspirin & heart",
            generation_time=0.5,
            temperature=0.1,
            attempt_number=1
        ),
        QueryGenerationResult(
            model="model2",
            query="aspirin & heart",  # Duplicate
            generation_time=0.6,
            temperature=0.1,
            attempt_number=1
        ),
        QueryGenerationResult(
            model="model3",
            query="aspirin & cardiac",
            generation_time=0.7,
            temperature=0.1,
            attempt_number=1
        )
    ]

    result = MultiModelQueryResult(
        all_queries=query_results,
        unique_queries=["aspirin & heart", "aspirin & cardiac"],  # Deduplicated
        model_count=3,
        total_queries=3,
        total_generation_time=1.8,
        question="test"
    )

    assert result.total_queries == 3  # All queries
    assert len(result.unique_queries) == 2  # Deduplicated
    assert result.model_count == 3


def test_query_generation_result_dataclass_behavior():
    """Test that dataclass features work correctly."""
    result1 = QueryGenerationResult(
        model="test",
        query="query1",
        generation_time=0.5,
        temperature=0.1,
        attempt_number=1
    )

    result2 = QueryGenerationResult(
        model="test",
        query="query1",
        generation_time=0.5,
        temperature=0.1,
        attempt_number=1
    )

    # Dataclasses support equality
    assert result1 == result2

    # Can be converted to dict (via dataclasses.asdict if needed)
    assert hasattr(result1, 'model')
    assert hasattr(result1, 'query')
