"""
Flet-based GUI Module for BMLibrarian

Provides graphical interfaces including configuration and research applications using Flet.

Exports are resolved lazily (PEP 562): importing a Flet-free submodule such as
``document_card_factory_base`` (shared with the Qt GUI) must not import the
``flet`` package, so a missing or incompatible Flet only breaks the Flet GUIs.
"""

import importlib
from typing import Any, Dict

# Public name -> submodule (relative to this package) that defines it
_LAZY_EXPORTS: Dict[str, str] = {
    'BMLibrarianConfigApp': '.config_app',
    'ResearchGUI': '.research_app',
    'StepCard': '.components',
    'DialogManager': '.dialogs',
    'WorkflowExecutor': '.workflow',
    'initialize_agents_in_main_thread': '.workflow',
    'cleanup_agents': '.workflow',
    'InteractiveHandler': '.interactive_handler',
    'QueryProcessor': '.query_processor',
    'WorkflowStepsHandler': '.workflow_steps_handler',
    'ReportBuilder': '.report_builder',
    'UnifiedDocumentCard': '.unified_document_card',
    'DocumentCardContext': '.unified_document_card',
    'create_literature_card': '.unified_document_card',
    'create_scored_card': '.unified_document_card',
    'create_citation_card': '.unified_document_card',
    'CardFactory': '.card_factory',
    'create_document_cards_for_tab': '.card_factory',
}

__all__ = list(_LAZY_EXPORTS)


def __getattr__(name: str) -> Any:
    """Import a Flet export on first access (PEP 562 module ``__getattr__``).

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
