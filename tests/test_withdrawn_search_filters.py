"""
Searches must never return withdrawn records (document.withdrawn_date set).

PubMed withdrawals (DeleteCitation) are kept in the database for referential
integrity and marked in document.withdrawn_date (migrations 032/033). The first
revision of that work used a new column that no SQL search function knew
about, so withdrawn records stayed searchable. These hermetic checks pin the
invariant at both layers:

- every SQL search function's latest definition filters on withdrawn_date;
- every full-text query on ``document`` written in Python does too.
"""

import ast
import re
from pathlib import Path
from typing import Iterator, Tuple

import pytest

REPO = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = REPO / "migrations"
SOURCE_DIR = REPO / "src" / "bmlibrarian"
WITHDRAWN_FILTER = "withdrawn_date IS NULL"
# Python queries may use the shared filter constant from bmlibrarian.database.
FILTER_MARKERS = ("withdrawn_date", "NOT_WITHDRAWN_SQL")
SEARCH_FUNCTIONS = ("fulltext_search", "bm25", "semantic_docsearch", "chunksearch",
                    "chunksearch_document", "hybrid_chunksearch_document")
NEXT_STATEMENT = re.compile(r"\n\s*CREATE\s", re.IGNORECASE)


def latest_definition(function: str) -> str:
    """Text of the last migration's CREATE FUNCTION for ``function`` (up to the next CREATE)."""
    pattern = re.compile(rf"CREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION\s+(?:\w+\.)?{function}\s*\(", re.IGNORECASE)
    found = ""
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        sql = path.read_text(encoding="utf-8")
        for match in pattern.finditer(sql):
            rest = sql[match.start():]
            end = NEXT_STATEMENT.search(rest, 1)
            found = rest[:end.start()] if end else rest
    return found


@pytest.mark.parametrize("function", SEARCH_FUNCTIONS)
def test_sql_search_functions_exclude_withdrawn(function: str) -> None:
    """The latest definition of each SQL search function filters on withdrawn_date."""
    definition = latest_definition(function)
    assert definition, f"no migration defines {function}()"
    assert WITHDRAWN_FILTER in definition


def python_sql_strings() -> Iterator[Tuple[str, int, str]]:
    """(path, line, text) of every string literal / f-string in the package (f-string fields as {expr})."""
    for path in SOURCE_DIR.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        fstring_parts = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.JoinedStr):
                fstring_parts.update(id(v) for v in node.values)
                text = "".join(v.value if isinstance(v, ast.Constant) else "{" + ast.unparse(v.value) + "}"
                               for v in node.values)
                yield str(path.relative_to(REPO)), node.lineno, text
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in fstring_parts:
                yield str(path.relative_to(REPO)), node.lineno, node.value


def test_python_fulltext_queries_on_document_exclude_withdrawn() -> None:
    """No full-text query on document in src/ omits the withdrawn filter."""
    offenders = [f"{path}:{line}" for path, line, text in python_sql_strings()
                 if "search_vector @@" in text and "FROM document" in text
                 and not any(marker in text for marker in FILTER_MARKERS)]
    assert offenders == [], f"full-text queries that return withdrawn records: {offenders}"


def test_scan_sees_the_known_queries() -> None:
    """Guard against the scan silently matching nothing."""
    hits = [path for path, _line, text in python_sql_strings()
            if "search_vector @@" in text and "FROM document" in text]
    assert any(path.endswith("database.py") for path in hits)
    assert any(path.endswith("search_coordinator.py") for path in hits)
