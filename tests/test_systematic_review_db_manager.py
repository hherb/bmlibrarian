"""
The systematic review reads the database its agent was given (#285).

Searches, document fetches and the results cache used to go through the
global ``get_db_manager()`` (the default ``.env``) while evaluations went to
the agent's ``db_manager``, so a review built for database B searched A.
These tests pass a manager explicitly and make the global one fail, so any
path that still falls back to it shows up.
"""

from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

from bmlibrarian import database
from bmlibrarian.agents.systematic_review.config import SystematicReviewConfig
from bmlibrarian.agents.systematic_review.executor import SearchExecutor
from bmlibrarian.agents.systematic_review.planner import PlannedQuery, QueryType
from bmlibrarian.agents.systematic_review.quality import QualityAssessor


@pytest.fixture
def no_global_manager() -> Any:
    """Fail any use of the global manager."""
    with patch.object(
        database, "get_db_manager", side_effect=AssertionError("global db_manager used")
    ):
        yield


def make_manager(rows: List[Dict[str, Any]]) -> MagicMock:
    """A DatabaseManager whose cursors return ``rows`` (sources: PubMed = 7)."""
    manager = MagicMock()
    manager.get_cached_source_ids.return_value = {"pubmed": 7, "medrxiv": 8, "others": [9]}
    manager.get_cached_source_id_names.return_value = {7: "pubmed"}
    cursor = manager.get_connection.return_value.__enter__.return_value \
        .cursor.return_value.__enter__.return_value
    cursor.fetchall.return_value = rows
    cursor.fetchmany.side_effect = [rows, []]
    cursor.__iter__.return_value = iter(rows)
    return manager


def make_query(query_type: QueryType) -> PlannedQuery:
    """A planned query of ``query_type``."""
    return PlannedQuery(
        query_id="q1",
        query_text="statin & cardiovascular",
        query_type=query_type,
        purpose="test",
        expected_coverage="test",
    )


class TestDatabaseHelpersUseGivenManager:
    """The module-level helpers query the manager they are handed."""

    def test_fetch_documents_by_ids(self, no_global_manager: None) -> None:
        """Fetched rows come from the given manager."""
        manager = make_manager([{"id": 1, "title": "t"}])
        assert database.fetch_documents_by_ids({1}, db_manager=manager) == [
            {"id": 1, "title": "t"}
        ]
        manager.get_connection.assert_called_once()

    def test_find_abstracts_resolves_sources_from_given_manager(
        self, no_global_manager: None
    ) -> None:
        """Source filtering uses the searched database's source ids."""
        manager = make_manager([])
        list(database.find_abstracts(
            "statin", use_medrxiv=False, use_others=False, db_manager=manager
        ))
        manager.get_cached_source_ids.assert_called()
        cursor = manager.get_connection.return_value.__enter__.return_value \
            .cursor.return_value.__enter__.return_value
        assert 7 in cursor.execute.call_args.args[1]  # PubMed only

    @pytest.mark.parametrize("strategy", ["semantic", "bm25", "fulltext"])
    def test_search_hybrid_passes_manager_to_strategies(self, strategy: str) -> None:
        """Every strategy of a hybrid search gets the caller's manager."""
        manager = make_manager([])
        target = {
            "semantic": "search_with_semantic",
            "bm25": "search_with_bm25",
            "fulltext": "search_with_fulltext_function",
        }[strategy]
        with patch.object(database, target, return_value=iter([])) as fake:
            database.search_hybrid(
                "question", "query",
                search_config={strategy: {"enabled": True}},
                db_manager=manager,
            )
        assert fake.call_args.kwargs["db_manager"] is manager


class TestSearchExecutorUsesAgentManager:
    """``SearchExecutor`` hands its manager to every search and fetch."""

    @pytest.fixture
    def manager(self) -> MagicMock:
        """The agent's manager."""
        return MagicMock()

    @pytest.fixture
    def executor(self, manager: MagicMock) -> SearchExecutor:
        """An executor built with ``manager``."""
        config = SystematicReviewConfig(model="test-model", host="http://localhost:11434")
        return SearchExecutor(config=config, db_manager=manager)

    def test_semantic(self, executor: SearchExecutor, manager: MagicMock) -> None:
        """Semantic search reads the agent's database."""
        with patch.object(database, "search_with_semantic", return_value=iter([])) as fake:
            assert executor._execute_semantic_query(
                make_query(QueryType.SEMANTIC), True, True, True
            ).success
        assert fake.call_args.kwargs["db_manager"] is manager

    def test_keyword(self, executor: SearchExecutor, manager: MagicMock) -> None:
        """Keyword search reads the agent's database."""
        with patch.object(database, "find_abstracts", return_value=iter([])) as fake:
            assert executor._execute_keyword_query(
                make_query(QueryType.KEYWORD), True, True, True
            ).success
        assert fake.call_args.kwargs["db_manager"] is manager

    def test_hybrid(self, executor: SearchExecutor, manager: MagicMock) -> None:
        """Hybrid search reads the agent's database."""
        with patch.object(database, "search_hybrid", return_value=([], {})) as fake:
            assert executor._execute_hybrid_query(
                make_query(QueryType.HYBRID), True, True, True
            ).success
        assert fake.call_args.kwargs["db_manager"] is manager

    def test_fetch(self, executor: SearchExecutor, manager: MagicMock) -> None:
        """Paper data is fetched from the agent's database."""
        with patch.object(database, "fetch_documents_by_ids", return_value=[]) as fake:
            executor._fetch_paper_data({1})
        assert fake.call_args.kwargs["db_manager"] is manager


def test_quality_assessor_cache_uses_given_manager(no_global_manager: None) -> None:
    """The results cache is read from and written to the agent's database."""
    manager = MagicMock()
    config = SystematicReviewConfig(
        model="test-model", host="http://localhost:11434", use_results_cache=True
    )
    assessor = QualityAssessor(config=config, db_manager=manager)
    assert assessor._cache_manager is not None
    assert assessor._cache_manager.db_manager is manager
