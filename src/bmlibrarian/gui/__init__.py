"""
GUI Module for BMLibrarian

Provides graphical interfaces for both Flet and Qt frameworks.
- flet: Flet-based GUI components (configuration, research applications)
- qt: Qt/PySide6-based GUI components (advanced plugin system)

For backwards compatibility, Flet exports are re-exported from this module.
"""

import importlib
from typing import Any

# Flet components are re-exported for backwards compatibility, but resolved
# lazily (PEP 562): the Qt GUI imports ``bmlibrarian.gui.qt`` through this
# package and must keep working when Flet is missing or incompatible.
_FLET_EXPORTS = (
    'BMLibrarianConfigApp',
    'ResearchGUI',
    'StepCard',
    'DialogManager',
    'WorkflowExecutor',
    'initialize_agents_in_main_thread',
    'cleanup_agents',
    'InteractiveHandler',
    'QueryProcessor',
    'WorkflowStepsHandler',
    'ReportBuilder',
    'UnifiedDocumentCard',
    'DocumentCardContext',
    'create_literature_card',
    'create_scored_card',
    'create_citation_card',
    'CardFactory',
    'create_document_cards_for_tab',
)


def __getattr__(name: str) -> Any:
    """Resolve a Flet re-export on first access (PEP 562 module ``__getattr__``).

    Args:
        name: Attribute requested from this package

    Returns:
        The exported object from ``bmlibrarian.gui.flet``

    Raises:
        AttributeError: If ``name`` is not a known export
    """
    if name not in _FLET_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(importlib.import_module('.flet', __name__), name)
    globals()[name] = value  # cache for subsequent lookups
    return value


# Re-export shared base classes used by both Flet and Qt (backwards compatibility)
from .document_card_factory_base import (
    CardContext,
    PDFButtonState,
    DocumentCardData,
    DocumentCardFactoryBase,
    MAX_AUTHORS_BEFORE_ET_AL,
    SCORE_THRESHOLD_EXCELLENT,
    SCORE_THRESHOLD_GOOD,
    SCORE_THRESHOLD_MODERATE,
    SCORE_COLOR_EXCELLENT,
    SCORE_COLOR_GOOD,
    SCORE_COLOR_MODERATE,
    SCORE_COLOR_POOR,
)

__all__ = [
    # Flet exports (backwards compatibility)
    'BMLibrarianConfigApp',
    'ResearchGUI',
    'StepCard',
    'DialogManager',
    'WorkflowExecutor',
    'initialize_agents_in_main_thread',
    'cleanup_agents',
    'InteractiveHandler',
    'QueryProcessor',
    'WorkflowStepsHandler',
    'ReportBuilder',
    'UnifiedDocumentCard',
    'DocumentCardContext',
    'create_literature_card',
    'create_scored_card',
    'create_citation_card',
    'CardFactory',
    'create_document_cards_for_tab',
    # Shared base classes (used by both Flet and Qt)
    'CardContext',
    'PDFButtonState',
    'DocumentCardData',
    'DocumentCardFactoryBase',
    'MAX_AUTHORS_BEFORE_ET_AL',
    'SCORE_THRESHOLD_EXCELLENT',
    'SCORE_THRESHOLD_GOOD',
    'SCORE_THRESHOLD_MODERATE',
    'SCORE_COLOR_EXCELLENT',
    'SCORE_COLOR_GOOD',
    'SCORE_COLOR_MODERATE',
    'SCORE_COLOR_POOR',
]
