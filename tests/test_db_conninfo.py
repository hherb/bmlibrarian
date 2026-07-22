"""Unit tests for connection-string and pagination SQL helpers.

These guard the injection-surface hardening that replaced hand-concatenated
libpq connection strings (``build_conninfo``) and the f-string ``LIMIT``/
``OFFSET`` in ``find_abstracts`` (``build_pagination_clause``).

Hermetic: no Ollama or PostgreSQL required.
"""

from psycopg.conninfo import conninfo_to_dict

from bmlibrarian.db_conninfo import build_conninfo
from bmlibrarian.database import build_pagination_clause


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
