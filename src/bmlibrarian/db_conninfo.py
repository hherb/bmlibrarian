"""Pure helpers for building libpq connection strings safely.

This module deliberately has no import-time side effects and no heavy
dependencies (only ``psycopg.conninfo``) so it can be imported from anywhere,
including GUI code that runs *before* a :class:`~bmlibrarian.database.DatabaseManager`
is configured.

Golden rule #1 (never trust input): connection strings must never be built by
string concatenation/interpolation. A password or hostname containing a space
or a ``'`` would silently corrupt the string or allow a crafted value to inject
extra libpq parameters. :func:`psycopg.conninfo.make_conninfo` quotes and
escapes every value, so all connection-string construction routes through the
single helper below.
"""

from typing import Any

from psycopg.conninfo import make_conninfo

__all__ = ["build_conninfo"]


def build_conninfo(**params: Any) -> str:
    """Build a properly-escaped libpq connection string from keyword params.

    Values that are ``None`` or empty strings are omitted so libpq falls back
    to its own defaults (and so unset secrets never appear in the string). All
    remaining values are escaped by :func:`psycopg.conninfo.make_conninfo`,
    which safely quotes values containing spaces or special characters.

    Args:
        **params: libpq connection parameters, e.g. ``host``, ``port``,
            ``dbname``, ``user``, ``password``, ``connect_timeout``. Values may
            be strings or ints; ``None``/``""`` values are dropped.

    Returns:
        A libpq-format connection string safe to pass to ``psycopg.connect``
        or ``psycopg_pool.ConnectionPool``.
    """
    clean = {k: v for k, v in params.items() if v is not None and v != ""}
    return make_conninfo(**clean)
