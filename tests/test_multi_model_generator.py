"""Unit tests for multi-model query generator."""

import pytest
from bmlibrarian.agents.query_generation.generator import MultiModelQueryGenerator
from bmlibrarian.agents.query_generation.data_types import QueryGenerationResult


def test_query_deduplication():
    """Test that duplicate queries are removed (case-insensitive)."""
    generator = MultiModelQueryGenerator("http://localhost:11434")

    queries = [
        "aspirin & heart",
        "Aspirin & Heart",  # Same but different case
        "diabetes & kidney",
        "aspirin & heart",  # Exact duplicate
        "Diabetes & Kidney"  # Case variation
    ]

    unique = generator._deduplicate_queries(queries)

    assert len(unique) == 2  # Only 2 unique queries
    assert "aspirin & heart" in unique or "Aspirin & Heart" in unique
    assert "diabetes & kidney" in unique or "Diabetes & Kidney" in unique


def test_deduplication_preserves_original_case():
    """Test that deduplication preserves the first occurrence's case."""
    generator = MultiModelQueryGenerator("http://localhost:11434")

    queries = [
        "Aspirin & Heart",  # This case should be preserved
        "aspirin & heart",
        "ASPIRIN & HEART"
    ]

    unique = generator._deduplicate_queries(queries)

    assert len(unique) == 1
    # First occurrence is preserved
    assert unique[0] == "Aspirin & Heart"


def test_deduplication_empty_list():
    """Test deduplication with empty list."""
    generator = MultiModelQueryGenerator("http://localhost:11434")

    unique = generator._deduplicate_queries([])

    assert unique == []


def test_deduplication_single_query():
    """Test deduplication with single query."""
    generator = MultiModelQueryGenerator("http://localhost:11434")

    queries = ["test & query"]
    unique = generator._deduplicate_queries(queries)

    assert len(unique) == 1
    assert unique[0] == "test & query"


def test_deduplication_filters_empty_strings():
    """Test that empty strings are filtered out."""
    generator = MultiModelQueryGenerator("http://localhost:11434")

    queries = [
        "aspirin & heart",
        "",
        "   ",  # Whitespace only
        "diabetes & kidney",
        ""
    ]

    unique = generator._deduplicate_queries(queries)

    assert len(unique) == 2
    assert "" not in unique
    assert "   " not in unique


def test_generator_initialization():
    """Test MultiModelQueryGenerator initialization."""
    generator = MultiModelQueryGenerator(
        ollama_host="http://localhost:11434",
        callback=None
    )

    assert generator.ollama_host == "http://localhost:11434"
    assert generator.callback is None
    assert generator.client is not None


def test_generator_with_callback():
    """Test generator with callback function."""
    callback_calls = []

    def test_callback(event, data):
        callback_calls.append((event, data))

    generator = MultiModelQueryGenerator(
        ollama_host="http://localhost:11434",
        callback=test_callback
    )

    assert generator.callback == test_callback
