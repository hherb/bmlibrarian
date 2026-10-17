"""
search_hybrid must report the strategies that failed.

Each strategy's exception is logged and swallowed so the others can still
contribute, which makes a database outage look like an empty result. The
``strategies_failed`` metadata lets callers (the fact-checker, issue #273)
tell "found nothing" from "could not search". Hermetic: the strategy
functions are patched, no database is touched.
"""

from typing import Any, Iterator
from unittest.mock import patch

from bmlibrarian.database import search_hybrid

BM25_AND_FULLTEXT = {
    'semantic': {'enabled': False},
    'bm25': {'enabled': True, 'max_results': 10},
    'fulltext': {'enabled': True, 'max_results': 10},
}


def _raise(*_args: Any, **_kwargs: Any) -> Iterator[dict]:
    """A strategy whose database call fails."""
    raise ConnectionError("connection refused")


def _one_doc(*_args: Any, **_kwargs: Any) -> Iterator[dict]:
    """A strategy that finds one document."""
    yield {'id': 1, 'title': 't', 'rank': 0.5, 'bm25_score': 1.0}


def _nothing(*_args: Any, **_kwargs: Any) -> Iterator[dict]:
    """A strategy that runs and finds nothing."""
    return iter(())


def _search(bm25: Any, fulltext: Any) -> tuple[list, dict]:
    """Run search_hybrid with the given BM25 and fulltext implementations."""
    with patch('bmlibrarian.database.search_with_bm25', side_effect=bm25), patch(
        'bmlibrarian.database.search_with_fulltext_function', side_effect=fulltext
    ):
        return search_hybrid('question', 'query', search_config=BM25_AND_FULLTEXT)


def test_every_strategy_failing_is_recorded() -> None:
    """An outage yields no documents and lists every failed strategy."""
    documents, metadata = _search(_raise, _raise)

    assert documents == []
    assert metadata['strategies_used'] == []
    assert [f['strategy'] for f in metadata['strategies_failed']] == ['bm25', 'fulltext']
    assert all('connection refused' in f['error'] for f in metadata['strategies_failed'])


def test_partial_failure_keeps_the_other_strategy_results() -> None:
    """One failed strategy is recorded; the other's documents are returned."""
    documents, metadata = _search(_raise, _one_doc)

    assert [doc['id'] for doc in documents] == [1]
    assert metadata['strategies_used'] == ['fulltext']
    assert [f['strategy'] for f in metadata['strategies_failed']] == ['bm25']


def test_empty_search_without_failures_has_no_failed_strategies() -> None:
    """Strategies that ran and matched nothing are not failures."""
    documents, metadata = _search(_nothing, _nothing)

    assert documents == []
    assert metadata['strategies_used'] == ['bm25', 'fulltext']
    assert metadata['strategies_failed'] == []
