"""Unit tests for connection-string and pagination SQL helpers.

These guard the injection-surface hardening that replaced hand-concatenated
libpq connection strings (``build_conninfo``) and the f-string ``LIMIT``/
``OFFSET`` in ``find_abstracts`` (``build_pagination_clause``), and the
f-string ``source_id`` filters in the BM25/fulltext search helpers
(``build_source_filter_clause``).

Hermetic: no Ollama or PostgreSQL required.
"""

from typing import Any, Dict, List, Tuple
from unittest.mock import MagicMock, patch

import pytest
from psycopg.conninfo import conninfo_to_dict

from bmlibrarian.db_conninfo import build_conninfo
from bmlibrarian import database
from bmlibrarian.database import build_pagination_clause, build_source_filter_clause


class TestBuildConninfo:
    """Tests for :func:`bmlibrarian.db_conninfo.build_conninfo`."""

    def test_basic_params_round_trip(self) -> None:
        """All supplied params appear in the parsed connection string."""
        conninfo = build_conninfo(
            host="localhost", port=5432, dbname="knowledgebase", user="alice"
        )
        parsed = conninfo_to_dict(conninfo)
        assert parsed["host"] == "localhost"
        assert parsed["port"] == "5432"
        assert parsed["dbname"] == "knowledgebase"
        assert parsed["user"] == "alice"

    def test_password_with_space_is_escaped_not_concatenated(self) -> None:
        """A password containing a space must survive as a single value.

        Naive concatenation (``password=p w``) would split into two params and
        corrupt the string; the helper must quote it.
        """
        conninfo = build_conninfo(user="u", password="p w")
        parsed = conninfo_to_dict(conninfo)
        assert parsed["password"] == "p w"
        assert parsed["user"] == "u"

    def test_value_with_quote_and_backslash_is_escaped(self) -> None:
        """Values with libpq-special characters round-trip intact."""
        tricky = "a'b\\c d"
        parsed = conninfo_to_dict(build_conninfo(password=tricky))
        assert parsed["password"] == tricky

    def test_injection_attempt_stays_a_single_value(self) -> None:
        """A crafted password cannot inject an extra libpq parameter."""
        parsed = conninfo_to_dict(build_conninfo(dbname="db", password="x host=evil"))
        # The whole crafted string is the password; host is not overridden.
        assert parsed["password"] == "x host=evil"
        assert parsed.get("host") in (None, "")

    def test_none_and_empty_values_are_dropped(self) -> None:
        """``None``/empty values are omitted rather than emitted as ``key=``."""
        parsed = conninfo_to_dict(
            build_conninfo(host="h", password=None, user="", dbname="d")
        )
        assert "password" not in parsed
        assert "user" not in parsed
        assert parsed["host"] == "h"
        assert parsed["dbname"] == "d"

    def test_empty_params_yield_empty_string(self) -> None:
        """No usable params produces an empty (but valid) conninfo."""
        assert build_conninfo(host=None, password="") == ""


class TestBuildPaginationClause:
    """Tests for :func:`bmlibrarian.database.build_pagination_clause`."""

    def test_limit_only(self) -> None:
        """Positive max_rows, zero offset -> LIMIT placeholder only."""
        clause, params = build_pagination_clause(100, 0)
        assert clause == " LIMIT %s"
        assert params == [100]

    def test_limit_and_offset(self) -> None:
        """Both positive -> LIMIT then OFFSET, params in placeholder order."""
        clause, params = build_pagination_clause(50, 20)
        assert clause == " LIMIT %s OFFSET %s"
        assert params == [50, 20]

    def test_offset_only(self) -> None:
        """Zero max_rows, positive offset -> OFFSET placeholder only."""
        clause, params = build_pagination_clause(0, 30)
        assert clause == " OFFSET %s"
        assert params == [30]

    def test_neither(self) -> None:
        """Zero/negative for both -> no clause and no params."""
        assert build_pagination_clause(0, 0) == ("", [])
        assert build_pagination_clause(-5, -5) == ("", [])

    def test_values_are_bound_not_interpolated(self) -> None:
        """The clause uses %s placeholders; raw values never appear in SQL."""
        clause, params = build_pagination_clause(100, 20)
        assert "100" not in clause
        assert "20" not in clause
        assert params == [100, 20]


SOURCE_IDS: Dict[str, Any] = {"pubmed": 1, "medrxiv": 2, "others": [3, 4]}


class TestBuildSourceFilterClause:
    """Tests for :func:`bmlibrarian.database.build_source_filter_clause`."""

    def test_all_sources_selected_means_no_filter(self) -> None:
        """With every source selected there is nothing to filter."""
        assert build_source_filter_clause(SOURCE_IDS) == ("", [])

    def test_selected_ids_bound_as_one_array(self) -> None:
        """Selected ids are collected into a single bound array param."""
        clause, params = build_source_filter_clause(SOURCE_IDS, use_medrxiv=False)
        assert clause == " AND source_id = ANY(%s)"
        assert params == [[1, 3, 4]]

    def test_subset_of_sources(self) -> None:
        """Deselected sources are left out of the bound ids."""
        _, params = build_source_filter_clause(
            SOURCE_IDS, use_pubmed=True, use_medrxiv=False, use_others=False
        )
        assert params == [[1]]

    def test_scalar_others(self) -> None:
        """A scalar 'others' id is accepted as well as a list."""
        _, params = build_source_filter_clause({"others": 7}, use_pubmed=False)
        assert params == [[7]]

    def test_empty_map_means_no_filter(self) -> None:
        """Without a source map the selection cannot be applied."""
        assert build_source_filter_clause({}, use_pubmed=False) == ("", [])

    def test_selection_resolving_to_nothing_matches_nothing(self) -> None:
        """Nothing selected, or only an empty 'others' -> no rows (as find_abstracts)."""
        assert build_source_filter_clause(
            SOURCE_IDS, use_pubmed=False, use_medrxiv=False, use_others=False
        ) == (" AND FALSE", [])
        assert build_source_filter_clause(
            {"pubmed": 1, "others": []}, use_pubmed=False, use_medrxiv=False
        ) == (" AND FALSE", [])

    def test_ids_never_appear_in_sql(self) -> None:
        """The clause is a placeholder; ids only travel as parameters."""
        clause, _ = build_source_filter_clause({"pubmed": 12345}, use_medrxiv=False)
        assert "12345" not in clause

    @pytest.mark.parametrize("bad_id", ["1); DROP TABLE document; --", None, True])
    def test_non_integer_id_rejected(self, bad_id: Any) -> None:
        """A non-integer id raises ValueError naming the source."""
        with pytest.raises(ValueError, match="pubmed"):
            build_source_filter_clause({"pubmed": bad_id}, use_medrxiv=False)


def _capture_search_sql(search_fn: Any, **flags: bool) -> Tuple[str, Tuple[Any, ...]]:
    """Run a search generator against a mocked cursor; return (sql, params)."""
    cursor = MagicMock()
    cursor.__iter__.return_value = iter([])
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cursor
    manager = MagicMock()
    manager.get_connection.return_value.__enter__.return_value = conn
    manager.get_cached_source_ids.return_value = SOURCE_IDS
    with patch.object(database, "get_db_manager", return_value=manager):
        list(search_fn("diabetes & treatment", max_results=10, **flags))
    sql, params = cursor.execute.call_args.args
    return sql, params


SEARCH_FNS = [database.search_with_bm25, database.search_with_fulltext_function]


@pytest.mark.parametrize("search_fn", SEARCH_FNS)
@pytest.mark.parametrize(
    "flags, expected_ids",
    [
        ({"use_medrxiv": False}, [1, 3, 4]),
        ({"use_pubmed": False}, [2, 3, 4]),
        ({"use_others": False}, [1, 2]),
    ],
)
def test_search_helpers_bind_source_ids(
    search_fn: Any, flags: Dict[str, bool], expected_ids: List[int]
) -> None:
    """BM25/fulltext search bind the selected source ids, in the right order."""
    sql, params = _capture_search_sql(search_fn, **flags)
    assert "source_id = ANY(%s)" in sql
    assert "ARRAY[" not in sql
    assert params == ("diabetes & treatment", 10, expected_ids)


@pytest.mark.parametrize("search_fn", SEARCH_FNS)
def test_search_helpers_all_sources_unfiltered(search_fn: Any) -> None:
    """With every source selected no source filter is added."""
    sql, params = _capture_search_sql(search_fn)
    assert "source_id = ANY" not in sql
    assert params == ("diabetes & treatment", 10)
