"""
BMLibrarian Lab Module

Experimental PySide6/Qt interfaces for testing and developing BMLibrarian
components. Each lab lives in its own module or subpackage; exports are
resolved lazily (PEP 562) so importing one lab never imports the others.

The PICO, PRISMA 2020, Query and Study Assessment labs are tabs of the main Qt
application (``gui/qt/plugins``); ``scripts/*_lab.py`` open them standalone.
"""

import importlib
from typing import Any, Dict

# Public name -> submodule (relative to this package) that defines it
_LAZY_EXPORTS: Dict[str, str] = {
    'ImporterTestLab': '.importer_test_lab',
    'PaperCheckerLab': '.paper_checker_lab',
    'PaperReviewerLab': '.paper_reviewer_lab',
    'PubMedSearchLabWindow': '.pubmed_search_lab',
    'run_pubmed_search_lab': '.pubmed_search_lab',
}

__all__ = list(_LAZY_EXPORTS)


def __getattr__(name: str) -> Any:
    """Import a lab export on first access (PEP 562 module ``__getattr__``).

    Args:
        name: Attribute requested from this package

    Returns:
        The exported object

    Raises:
        AttributeError: If ``name`` is not a known export
    """
    module_name = _LAZY_EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(importlib.import_module(module_name, __name__), name)
    globals()[name] = value  # cache for subsequent lookups
    return value


def __dir__() -> list[str]:
    """List module attributes including the lazy exports."""
    return sorted(set(globals()) | set(__all__))
