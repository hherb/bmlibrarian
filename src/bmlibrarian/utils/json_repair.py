"""
JSON repair utilities for handling malformed LLM responses.

This module is a re-export shim: the implementation lives in
``bmlib.llm.json_repair``, which was ported from this file and has since been
hardened upstream (truncated arrays recovered whole, a whole span preferred
over a nested fragment, field-level salvage). Import from here or from bmlib
directly; both name the same objects.
"""

from bmlib.llm.json_repair import (
    MAX_REPAIR_ATTEMPTS,
    JSONRepairError,
    extract_and_repair_json,
    repair_json,
    safe_json_loads,
    salvage_json_fields,
)

__all__ = [
    "MAX_REPAIR_ATTEMPTS",
    "JSONRepairError",
    "extract_and_repair_json",
    "repair_json",
    "safe_json_loads",
    "salvage_json_fields",
]
