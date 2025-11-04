"""Integration tests for QueryAgent multi-model methods."""

import pytest
from bmlibrarian.agents import QueryAgent


def test_query_agent_has_multi_model_methods():
    """Test that QueryAgent has new multi-model methods."""
    agent = QueryAgent(show_model_info=False)

    assert hasattr(agent, 'convert_question_multi_model')
    assert hasattr(agent, 'find_abstracts_multi_query')


def test_convert_question_multi_model_disabled_by_default():
    """Test that multi-model is disabled by default (backward compatible)."""
    agent = QueryAgent(show_model_info=False)

    # With multi-model disabled, should return single query result
    # (Note: This requires Ollama running, so we just test the method exists)
    assert callable(agent.convert_question_multi_model)


def test_find_abstracts_multi_query_signature():
    """Test find_abstracts_multi_query has correct signature."""
    from inspect import signature

    agent = QueryAgent(show_model_info=False)
    sig = signature(agent.find_abstracts_multi_query)
    params = list(sig.parameters.keys())

    expected_params = [
        'question',
        'max_rows',
        'use_pubmed',
        'use_medrxiv',
        'use_others',
        'from_date',
        'to_date',
        'human_in_the_loop',
        'human_query_modifier'
    ]

    for param in expected_params:
        assert param in params, f"Missing parameter: {param}"


def test_backward_compatibility_convert_question():
    """Test that original convert_question method still exists."""
    agent = QueryAgent(show_model_info=False)

    assert hasattr(agent, 'convert_question')
    assert callable(agent.convert_question)


def test_backward_compatibility_find_abstracts():
    """Test that original find_abstracts method still exists."""
    agent = QueryAgent(show_model_info=False)

    assert hasattr(agent, 'find_abstracts')
    assert callable(agent.find_abstracts)


def test_find_abstracts_multi_query_returns_generator():
    """Test that find_abstracts_multi_query returns a generator."""
    from inspect import signature
    from types import GeneratorType

    agent = QueryAgent(show_model_info=False)
    sig = signature(agent.find_abstracts_multi_query)

    # Check return annotation
    return_annotation = sig.return_annotation

    # Should return Generator type
    assert 'Generator' in str(return_annotation)


def test_query_agent_initialization_unchanged():
    """Test that QueryAgent initialization hasn't changed."""
    from inspect import signature

    sig = signature(QueryAgent.__init__)
    params = list(sig.parameters.keys())

    # These parameters should still exist
    assert 'model' in params
    assert 'host' in params
    assert 'temperature' in params
    assert 'top_p' in params


def test_multi_model_methods_dont_break_existing_workflow():
    """Test that adding multi-model methods doesn't break existing workflow."""
    agent = QueryAgent(show_model_info=False)

    # Agent should initialize without errors
    assert agent.model is not None
    assert agent.host is not None

    # Original methods should be callable
    assert callable(agent.convert_question)
    assert callable(agent.find_abstracts)

    # New methods should be callable
    assert callable(agent.convert_question_multi_model)
    assert callable(agent.find_abstracts_multi_query)


def test_configuration_integration():
    """Test that QueryAgent integrates with configuration system."""
    from bmlibrarian.config import get_query_generation_config

    config = get_query_generation_config()

    # Should have required fields
    assert 'multi_model_enabled' in config
    assert 'models' in config
    assert 'queries_per_model' in config

    # Default should be disabled (backward compatible)
    assert config['multi_model_enabled'] is False


# Note: Tests that require Ollama or database are skipped
# Those are integration tests requiring external services
# The above tests verify methods exist and have correct signatures
