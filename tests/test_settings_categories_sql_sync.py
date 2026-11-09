"""Keep the SQL settings-category lists in step with VALID_SETTINGS_CATEGORIES.

The bmlsettings schema repeats the category whitelist in three places: the
CHECK constraints of ``user_settings`` and ``default_settings`` and the
``v_user_complete_settings`` view. Each is (re)defined by migrations, so the
schema a database ends up with is the latest definition across
``migrations/*.sql``. This test reads those files (no database needed) and
fails when a category is added to ``config.VALID_SETTINGS_CATEGORIES``
without a migration that extends all three lists (issue #231).
"""

import re
from pathlib import Path

import pytest

from bmlibrarian.config import VALID_SETTINGS_CATEGORIES

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"

# Each SQL list, with the statements that (re)define it; group 1 is the list.
SQL_CATEGORY_LISTS: dict[str, list[str]] = {
    "user_settings CHECK": [
        r"CREATE TABLE (?:IF NOT EXISTS )?bmlsettings\.user_settings\s*\("
        r"[^;]*?CHECK \(category IN \(([^)]*)\)",
        r"ADD CONSTRAINT user_settings_category_check CHECK \(category IN \(([^)]*)\)",
    ],
    "default_settings CHECK": [
        r"CREATE TABLE (?:IF NOT EXISTS )?bmlsettings\.default_settings\s*\("
        r"[^;]*?CHECK \(category IN \(([^)]*)\)",
        r"ADD CONSTRAINT default_settings_category_check CHECK \(category IN \(([^)]*)\)",
    ],
    "v_user_complete_settings view": [
        r"CREATE (?:OR REPLACE )?VIEW bmlsettings\.v_user_complete_settings AS"
        r"[^;]*?ARRAY\[([^\]]*)\]",
    ],
}


def _strip_sql_comments(sql: str) -> str:
    """Remove ``--`` line comments so their text cannot affect matching.

    Args:
        sql: SQL source text.

    Returns:
        The text with every ``--`` comment removed up to the end of its line.
    """
    return re.sub(r"--[^\n]*", "", sql)


def latest_category_list(sql_files: list[str], patterns: list[str]) -> tuple[str, set[str]] | None:
    """Find the last definition of a category list across migration files.

    Args:
        sql_files: SQL texts in the order the migrations run.
        patterns: Regexes whose group 1 is the comma-separated quoted list.

    Returns:
        ``(match text, categories)`` of the last match in run order (the last
        within a file wins), or None when no file defines the list.
    """
    latest = None
    for sql in sql_files:
        text = _strip_sql_comments(sql)
        matches = [m for p in patterns for m in re.finditer(p, text)]
        if matches:
            last = max(matches, key=lambda m: m.start())
            latest = (last.group(0), set(re.findall(r"'([^']*)'", last.group(1))))
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
    latest = latest_category_list(_migration_texts(), SQL_CATEGORY_LISTS[name])
    assert latest is not None, f"no migration defines the {name} category list"
    _, categories = latest
    expected = set(VALID_SETTINGS_CATEGORIES)
    assert categories == expected, (
        f"{name} is out of step with config.VALID_SETTINGS_CATEGORIES: "
        f"missing in SQL={sorted(expected - categories)}, "
        f"extra in SQL={sorted(categories - expected)}. "
        "Add a migration that extends every SQL category list."
    )


def test_latest_definition_wins() -> None:
    """A later migration's list replaces an earlier one; comments are ignored."""
    patterns = SQL_CATEGORY_LISTS["user_settings CHECK"]
    older = (
        "CREATE TABLE bmlsettings.user_settings (\n"
        "    category TEXT NOT NULL CHECK (category IN (\n"
        "        'models', -- note (with parens)\n"
        "        'gui'\n"
        "    )),\n"
        "    settings JSONB\n"
        ");"
    )
    newer = (
        "ALTER TABLE bmlsettings.user_settings\n"
        "    ADD CONSTRAINT user_settings_category_check CHECK (category IN (\n"
        "        'models', 'gui', 'pdf'\n"
        "    ));"
    )
    assert latest_category_list([older], patterns)[1] == {"models", "gui"}
    assert latest_category_list([older, newer], patterns)[1] == {"models", "gui", "pdf"}
    assert latest_category_list(["SELECT 1;"], patterns) is None
