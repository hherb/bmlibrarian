"""
JSON repair utilities for handling malformed LLM responses.

This module is a re-export shim: the implementation lives in
``bmlib.llm.json_repair``, which was ported from this file. Import from here
or from bmlib directly; both name the same objects. ``repair_json`` and
``safe_json_loads`` behave as before (including the ``MAX_JSON_LENGTH`` guard).
Changes in bmlib 0.10:

- ``extract_and_repair_json`` no longer stops at the first JSON span. If that
  span cannot be parsed or repaired it tries the next one, so it can return a
  *later* object (e.g. an example quoted in surrounding prose) with
  ``was_repaired=False``. It also closes truncated JSON (``'{"a": "x'`` ->
  ``'{"a": "x"}'``, ``was_repaired=True``) where it used to raise, so a
  repaired result may hold cut-off values. Callers must check the keys they
  need and treat ``was_repaired=True`` with suspicion. With ``repair=False``
  a parse failure raises plain ``ValueError`` (was ``json.JSONDecodeError``).
- A candidate nested deeper than the recursion limit is skipped rather than
  raising ``RecursionError``.
- ``salvage_json_fields()`` is new: it recovers individual fields from a
  response that will not parse as a whole.
- Truncated arrays of objects (``'[{"a": 1}, {"b": 2'``) still cannot be
  repaired; that fix is unreleased upstream (bmlib #299).
"""

from bmlib.llm.json_repair import (
    MAX_JSON_LENGTH,
    MAX_REPAIR_ATTEMPTS,
    JSONRepairError,
    extract_and_repair_json,
    repair_json,
    safe_json_loads,
    salvage_json_fields,
)

__all__ = [
    "MAX_JSON_LENGTH",
    "MAX_REPAIR_ATTEMPTS",
    "JSONRepairError",
    "extract_and_repair_json",
    "repair_json",
    "safe_json_loads",
    "salvage_json_fields",
]
