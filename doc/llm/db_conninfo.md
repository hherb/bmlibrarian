# Building libpq connection strings

**Rule: never build a PostgreSQL connection string by concatenating or
f-string-interpolating values.** A password or hostname containing a space or
a `'` silently corrupts the string, and a crafted value can inject extra libpq
parameters (e.g. a password `"x host=evil"` overriding the host).

## The one helper

Always use `bmlibrarian.db_conninfo.build_conninfo(**params)`:

```python
from bmlibrarian.db_conninfo import build_conninfo

conninfo = build_conninfo(
    host=host, port=port, dbname=dbname, user=user, password=password
)
conn = psycopg.connect(conninfo, connect_timeout=...)
```

- Delegates to `psycopg.conninfo.make_conninfo`, which quotes/escapes every
  value.
- Drops `None` and empty-string values so unset secrets never appear in the
  string.
- Has **no import-time side effects** and only depends on `psycopg.conninfo`,
  so it is safe to import from GUI code that runs *before* a
  `DatabaseManager` exists (e.g. the login dialog) — which is why it lives in
  its own module rather than in `database.py` (importing that runs
  `load_dotenv`).

Callers as of 2026-07-22: `database.py` (`DatabaseManager._init_pool`),
`gui/qt/core/application.py` (auto-login), `gui/qt/dialogs/login_dialog.py`
(test-connection + `_get_db_connection`), `paperchecker/database.py`
(`PaperCheckDB._create_connection`), and `migrate_config_to_db.py`
(`get_db_connection`). This is the only sanctioned way to build a libpq
connection string — do not add new hand-concatenated sites.

## Pagination and other SQL values

Same principle inside SQL: bind values as `%s` parameters, never interpolate.
`database.py`'s `find_abstracts` uses `build_pagination_clause(max_rows,
offset)` which returns a `LIMIT %s [OFFSET %s]` suffix plus the ordered param
list. The f-string source-id filters in `search_with_bm25` /
`search_with_fulltext_function` are the remaining interpolation site (not
injectable — IDs are DB-sourced ints — but tracked in
`doc/TODO_code_review_2026-07.md`).
