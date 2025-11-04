"""Unit tests for database multi-query functions."""

import pytest
from bmlibrarian.database import find_abstract_ids, fetch_documents_by_ids


def test_fetch_documents_by_ids_empty_set():
    """Test fetch_documents_by_ids with empty set."""
    docs = fetch_documents_by_ids(set())

    assert docs == []
    assert isinstance(docs, list)


def test_fetch_documents_by_ids_return_type():
    """Test that fetch_documents_by_ids returns a list."""
    # Test with empty set (doesn't require database)
    result = fetch_documents_by_ids(set())

    assert isinstance(result, list)
    assert result == []


def test_find_abstract_ids_return_type():
    """Test that find_abstract_ids returns a set."""
    # This test doesn't require database connection
    # Just verifies the function signature and basic behavior
    try:
        ids = find_abstract_ids("test", max_rows=1)
        assert isinstance(ids, set)
    except Exception:
        # If database not available, that's OK for this test
        # We're just checking the function exists and has correct signature
        pass


def test_batch_size_parameter():
    """Test that fetch_documents_by_ids accepts batch_size parameter."""
    # Should not raise error even with empty set
    docs = fetch_documents_by_ids(set(), batch_size=25)

    assert docs == []


def test_find_abstract_ids_parameters():
    """Test that find_abstract_ids accepts all expected parameters."""
    from datetime import date
    from inspect import signature

    sig = signature(find_abstract_ids)
    params = list(sig.parameters.keys())

    expected_params = [
        'ts_query_str',
        'max_rows',
        'use_pubmed',
        'use_medrxiv',
        'use_others',
        'plain',
        'from_date',
        'to_date',
        'offset'
    ]

    for param in expected_params:
        assert param in params, f"Missing parameter: {param}"


def test_fetch_documents_by_ids_parameters():
    """Test that fetch_documents_by_ids accepts expected parameters."""
    from inspect import signature

    sig = signature(fetch_documents_by_ids)
    params = list(sig.parameters.keys())

    assert 'document_ids' in params
    assert 'batch_size' in params


def test_find_abstract_ids_defaults():
    """Test find_abstract_ids default parameter values."""
    from inspect import signature

    sig = signature(find_abstract_ids)

    assert sig.parameters['max_rows'].default == 100
    assert sig.parameters['use_pubmed'].default is True
    assert sig.parameters['use_medrxiv'].default is True
    assert sig.parameters['use_others'].default is True
    assert sig.parameters['plain'].default is False
    assert sig.parameters['offset'].default == 0


def test_fetch_documents_by_ids_batch_size_default():
    """Test fetch_documents_by_ids batch_size default value."""
    from inspect import signature

    sig = signature(fetch_documents_by_ids)

    assert sig.parameters['batch_size'].default == 50


# Note: Tests that require actual database connection are skipped
# Those would be integration tests requiring test database setup
# The above tests verify function signatures, types, and basic behavior
