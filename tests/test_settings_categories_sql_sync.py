"""Keep the SQL settings-category lists in step with VALID_SETTINGS_CATEGORIES.

The bmlsettings schema repeats the category whitelist in four places: the
CHECK constraints of ``user_settings`` and ``default_settings``, the
``v_user_complete_settings`` view and the ``get_all_user_settings()``
function. Each is (re)defined by migrations, so the schema a database ends up
with is the latest definition across ``migrations/*.sql``. This test reads
those files (no database needed) and fails when a category is added to
``config.VALID_SETTINGS_CATEGORIES`` without a migration that extends all
four lists (issue #231).

Out of scope: a CHECK constraint re-added under a different name is not
recognised.
"""

import re
from pathlib import Path

import pytest

from bmlibrarian.config import VALID_SETTINGS_CATEGORIES

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"

_FLAGS = re.IGNORECASE | re.DOTALL
_IF_EXISTS = r"(?:IF\s+EXISTS\s+)?"
_OR_REPLACE = r"(?:OR\s+REPLACE\s+)?"
# Text up to the list without leaving the statement; function bodies contain
# ';', so there the limit is the next CREATE instead.
_IN_STATEMENT = r"[^;]*?"
_IN_FUNCTION = r"(?:(?!\bCREATE\b).)*?"
# Group 1 is the quoted list: ``IN (...)`` or the ``= ANY (ARRAY[...])`` form
# that pg_dump prints.
_CHECK_LIST = (
    r"CHECK\s*\(\s*\(?\s*category\s*"
    r"(?:IN\s*\(|=\s*ANY\s*\(\s*(?:ARRAY\s*)?\[)([^)\]]*)"
)
_UNNEST_LIST = r"unnest\s*\(\s*ARRAY\s*\[([^\]]*)\]"

# Each SQL list, with the statements that (re)define or drop it. Group 1 is
# the list; a match without it (a DROP, or a redefinition that no longer
# holds a literal list) leaves no list.
SQL_CATEGORY_LISTS: dict[str, list[str]] = {
    "user_settings CHECK": [
        r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?bmlsettings\.user_settings\s*\("
        rf"(?:{_IN_STATEMENT}{_CHECK_LIST})?",
        rf"ADD\s+CONSTRAINT\s+user_settings_category_check\s+{_CHECK_LIST}",
        rf"DROP\s+CONSTRAINT\s+{_IF_EXISTS}user_settings_category_check\b",
        rf"DROP\s+TABLE\s+{_IF_EXISTS}bmlsettings\.user_settings\b",
    ],
    "default_settings CHECK": [
        r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?bmlsettings\.default_settings\s*\("
        rf"(?:{_IN_STATEMENT}{_CHECK_LIST})?",
        rf"ADD\s+CONSTRAINT\s+default_settings_category_check\s+{_CHECK_LIST}",
        rf"DROP\s+CONSTRAINT\s+{_IF_EXISTS}default_settings_category_check\b",
        rf"DROP\s+TABLE\s+{_IF_EXISTS}bmlsettings\.default_settings\b",
    ],
    "v_user_complete_settings view": [
        rf"CREATE\s+{_OR_REPLACE}VIEW\s+bmlsettings\.v_user_complete_settings\s+AS"
        rf"(?:{_IN_STATEMENT}{_UNNEST_LIST})?",
        rf"DROP\s+VIEW\s+{_IF_EXISTS}bmlsettings\.v_user_complete_settings\b",
    ],
    "get_all_user_settings function": [
        rf"CREATE\s+{_OR_REPLACE}FUNCTION\s+bmlsettings\.get_all_user_settings\s*\("
        rf"(?:{_IN_FUNCTION}{_UNNEST_LIST})?",
        rf"DROP\s+FUNCTION\s+{_IF_EXISTS}bmlsettings\.get_all_user_settings\b",
    ],
}


def _strip_sql_comments(sql: str) -> str:
    """Remove ``--`` and ``/* */`` comments so their text cannot affect matching.

    Args:
        sql: SQL source text.

    Returns:
        The text without comments; whichever comment form starts first wins.
    """
    return re.sub(r"--[^\n]*|/\*.*?\*/", "", sql, flags=re.DOTALL)


def latest_category_list(sql_files: list[str], patterns: list[str]) -> set[str] | None:
    """Find the categories of the last definition of a list across migrations.

    Args:
        sql_files: SQL texts in the order the migrations run.
        patterns: Regexes for the statements that define or drop the list;
            group 1, when present and matched, is the quoted list.

    Returns:
        The categories of the last match in run order (the last within a file
        wins), or None when no file defines the list or the last match leaves
        none (a DROP, or a redefinition without a literal list).
    """
    latest: set[str] | None = None
    for sql in sql_files:
        text = _strip_sql_comments(sql)
        matches = [m for p in patterns for m in re.finditer(p, text, _FLAGS)]
        if matches:
            last = max(matches, key=lambda m: m.start())
            listed = last.group(1) if last.re.groups else None
            latest = None if listed is None else set(re.findall(r"'([^']*)'", listed))
    return latest


def _migration_texts() -> list[str]:
    """Read every migration in the order MigrationManager applies them.

    Returns:
        The SQL text of each ``migrations/*.sql`` file, sorted by file name.
    """
    files = sorted(MIGRATIONS_DIR.glob("*.sql"), key=lambda p: p.name)
    assert files, f"no migrations found in {MIGRATIONS_DIR}"
    return [p.read_text(encoding="utf-8") for p in files]


@pytest.mark.parametrize("name", sorted(SQL_CATEGORY_LISTS))
def test_sql_category_list_matches_python(name: str) -> None:
    """The latest migration definition of each SQL list equals the Python set."""
    categories = latest_category_list(_migration_texts(), SQL_CATEGORY_LISTS[name])
    assert categories is not None, (
        f"migrations leave no {name} category list (never defined, dropped, "
        "or redefined without a literal list)"
    )
    expected = set(VALID_SETTINGS_CATEGORIES)
    assert categories == expected, (
        f"{name} is out of step with config.VALID_SETTINGS_CATEGORIES: "
        f"missing in SQL={sorted(expected - categories)}, "
        f"extra in SQL={sorted(categories - expected)}. "
        "Add a migration that extends every SQL category list."
    )


_TABLE = (
    "CREATE TABLE bmlsettings.user_settings (\n"
    "    category TEXT NOT NULL CHECK (category IN (\n"
    "        'models', -- note (with parens)\n"
    "        'gui'\n"
    "    )),\n"
    "    settings JSONB\n"
    ");"
)
_ADD_PDF = (
    "ALTER TABLE bmlsettings.user_settings\n"
    "    ADD CONSTRAINT user_settings_category_check CHECK (category IN (\n"
    "        'models', 'gui', 'pdf'\n"
    "    ));"
)
_FUNCTION = (
    "CREATE OR REPLACE FUNCTION bmlsettings.get_all_user_settings(p INTEGER)\n"
    "RETURNS JSONB AS $$ DECLARE v JSONB := '{}'::jsonb; BEGIN\n"
    "  FOR c IN SELECT unnest(ARRAY['models', 'gui']) LOOP END LOOP;\n"
    "END; $$ LANGUAGE plpgsql;"
)


@pytest.mark.parametrize(
    ("name", "sql_files", "expected"),
    [
        ("user_settings CHECK", [_TABLE], {"models", "gui"}),
        ("user_settings CHECK", [_TABLE, _ADD_PDF], {"models", "gui", "pdf"}),
        ("user_settings CHECK", [_TABLE + _ADD_PDF], {"models", "gui", "pdf"}),
        (
            "user_settings CHECK",
            [_TABLE, "alter table bmlsettings.user_settings add constraint\n"
                     "  user_settings_category_check\n  check (category  in ('pdf'));"],
            {"pdf"},
        ),
        (
            "user_settings CHECK",
            [_TABLE, "ADD CONSTRAINT user_settings_category_check CHECK "
                     "((category = ANY (ARRAY['pdf'::text, 'gui'::text])));"],
            {"pdf", "gui"},
        ),
        (
            "user_settings CHECK",
            [_TABLE, "ALTER TABLE bmlsettings.user_settings "
                     "DROP CONSTRAINT IF EXISTS user_settings_category_check;"],
            None,
        ),
        (
            "user_settings CHECK",
            [_TABLE, "/* ADD CONSTRAINT user_settings_category_check "
                     "CHECK (category IN ('zzz')) */ SELECT 1;"],
            {"models", "gui"},
        ),
        (
            "v_user_complete_settings view",
            ["CREATE VIEW bmlsettings.v_user_complete_settings AS SELECT "
             "ARRAY['k'] AS tags, c FROM unnest(ARRAY['a', 'b']) AS c;"],
            {"a", "b"},
        ),
        ("get_all_user_settings function", [_FUNCTION], {"models", "gui"}),
        (
            "get_all_user_settings function",
            [_FUNCTION, "CREATE OR REPLACE FUNCTION bmlsettings.get_all_user_settings(p INTEGER)\n"
                        "RETURNS JSONB AS $$ SELECT '{}'::jsonb; $$ LANGUAGE sql;\n"
                        "CREATE VIEW x AS SELECT unnest(ARRAY['zzz']);"],
            None,
        ),
        ("user_settings CHECK", ["SELECT 1;"], None),
    ],
)
def test_latest_category_list_parsing(
    name: str, sql_files: list[str], expected: set[str] | None
) -> None:
    """The parser follows the latest definition across formatting variants."""
    assert latest_category_list(sql_files, SQL_CATEGORY_LISTS[name]) == expected
