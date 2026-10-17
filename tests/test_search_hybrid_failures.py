"""
search_hybrid must report the strategies that failed.

Each strategy's exception is logged and swallowed so the others can still
contribute, which makes a database outage look like an empty result. The
``strategies_failed`` metadata lets callers (the fact-checker, issue #273)
tell "found nothing" from "could not search". Hermetic: the strategy
functions are patched, no database is touched.
"""

from typing import Any, Iterator
from unittest.mock import Mock, patch

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


SEMANTIC_ONLY = {
    'semantic': {'enabled': True, 'max_results': 10},
    'bm25': {'enabled': False},
    'fulltext': {'enabled': False},
}
BM25_ONLY = {
    'semantic': {'enabled': False},
    'bm25': {'enabled': True, 'max_results': 10},
    'fulltext': {'enabled': False},
}
NOTHING_ENABLED = {
    'semantic': {'enabled': False},
    'bm25': {'enabled': False},
    'fulltext': {'enabled': False},
}


class _FailsThenFinds:
    """A strategy that raises ``error`` on its first call, then finds one document."""

    def __init__(self, error: Exception) -> None:
        """Remember the error for the first call."""
        self.error = error
        self.calls = 0

    def __call__(self, *_args: Any, **_kwargs: Any) -> Iterator[dict]:
        """Raise on the first call; yield one document afterwards."""
        self.calls += 1
        if self.calls == 1:
            raise self.error
        yield {'id': 1, 'title': 't', 'rank': 0.5}


def _yields_then_fails(*_args: Any, **_kwargs: Any) -> Iterator[dict]:
    """A strategy that returns a row and then fails mid-stream."""
    yield {'id': 9, 'title': 'partial', 'rank': 0.5}
    raise RuntimeError("cursor broke")


def test_semantic_failure_is_recorded() -> None:
    """A missing embedder is a failed strategy, not an empty result."""
    with patch('bmlibrarian.database.search_with_semantic', side_effect=_raise):
        documents, metadata = search_hybrid('question', 'query', search_config=SEMANTIC_ONLY)

    assert documents == []
    assert [f['strategy'] for f in metadata['strategies_failed']] == ['semantic']


def test_failed_strategies_do_not_silently_switch_to_fulltext() -> None:
    """Fulltext is a fallback for 'nothing enabled', not for 'everything failed'."""
    fulltext = Mock()
    with patch('bmlibrarian.database.search_with_bm25', side_effect=_raise), patch(
        'bmlibrarian.database.search_with_fulltext_function', fulltext
    ):
        documents, metadata = search_hybrid('question', 'query', search_config=BM25_ONLY)

    fulltext.assert_not_called()
    assert documents == []
    assert [f['strategy'] for f in metadata['strategies_failed']] == ['bm25']
    assert metadata['fallback_used'] is None


def test_fulltext_fallback_is_recorded_when_nothing_is_enabled() -> None:
    """Callers can see that the configured strategies were not the ones used."""
    with patch('bmlibrarian.database.search_with_fulltext_function', side_effect=_one_doc):
        documents, metadata = search_hybrid('question', 'query', search_config=NOTHING_ENABLED)

    assert [doc['id'] for doc in documents] == [1]
    assert metadata['fallback_used'] == 'fulltext'


def test_transient_strategy_failure_is_retried(_no_backoff_waits: list) -> None:
    """A dropped connection is retried with backoff and the strategy recovers."""
    bm25 = _FailsThenFinds(ConnectionError("server closed the connection"))
    with patch('bmlibrarian.database.search_with_bm25', side_effect=bm25):
        documents, metadata = search_hybrid('question', 'query', search_config=BM25_ONLY)

    assert [doc['id'] for doc in documents] == [1]
    assert metadata['strategies_failed'] == []
    assert bm25.calls == 2
    assert len(_no_backoff_waits) == 1


def test_non_transient_strategy_failure_is_not_retried() -> None:
    """A bug (e.g. bad SQL) fails at once."""
    bm25 = _FailsThenFinds(RuntimeError("syntax error"))
    with patch('bmlibrarian.database.search_with_bm25', side_effect=bm25):
        _, metadata = search_hybrid('question', 'query', search_config=BM25_ONLY)

    assert bm25.calls == 1
    assert [f['strategy'] for f in metadata['strategies_failed']] == ['bm25']


def test_retry_attempts_come_from_the_search_config() -> None:
    """search_strategy.retry.max_attempts bounds the attempts."""
    config = {**BM25_ONLY, 'retry': {'max_attempts': 1}}
    bm25 = _FailsThenFinds(ConnectionError("down"))
    with patch('bmlibrarian.database.search_with_bm25', side_effect=bm25):
        _, metadata = search_hybrid('question', 'query', search_config=config)

    assert bm25.calls == 1
    assert [f['strategy'] for f in metadata['strategies_failed']] == ['bm25']


def test_rows_from_a_strategy_that_failed_midway_are_discarded() -> None:
    """A failed strategy contributes nothing, not a partial result."""
    with patch('bmlibrarian.database.search_with_bm25', side_effect=_yields_then_fails):
        documents, metadata = search_hybrid('question', 'query', search_config=BM25_ONLY)

    assert documents == []
    assert [f['strategy'] for f in metadata['strategies_failed']] == ['bm25']


def test_query_agent_reports_failed_strategies() -> None:
    """Callers that do not read the metadata still hear about a failed strategy."""
    from bmlibrarian.agents.query_agent import QueryAgent

    events = []
    agent = QueryAgent(
        model="test-model", show_model_info=False,
        callback=lambda step, data: events.append((step, data)),
    )
    metadata = {'strategies_used': [], 'strategies_failed': [
        {'strategy': 'semantic', 'error': 'no embedder'}
    ]}
    with patch.object(QueryAgent, 'convert_question', return_value="aspirin"), patch(
        'bmlibrarian.agents.query_agent.search_hybrid', return_value=([], metadata)
    ):
        assert list(agent.find_abstracts("Does aspirin help?")) == []

    failed = [data for step, data in events if step == "search_strategies_failed"]
    assert failed == ["semantic: no embedder"]
