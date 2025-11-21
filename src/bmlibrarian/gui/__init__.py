"""
GUI Module for BMLibrarian

Provides graphical interfaces for both Flet and Qt frameworks.
- flet: Flet-based GUI components (configuration, research applications)
- qt: Qt/PySide6-based GUI components (advanced plugin system)

For backwards compatibility, Flet exports are re-exported from this module.
"""

# Re-export Flet components for backwards compatibility
from .flet import (
    BMLibrarianConfigApp,
    ResearchGUI,
    StepCard,
    DialogManager,
    WorkflowExecutor,
    initialize_agents_in_main_thread,
    cleanup_agents,
    InteractiveHandler,
    QueryProcessor,
    WorkflowStepsHandler,
    ReportBuilder,
    UnifiedDocumentCard,
    DocumentCardContext,
    create_literature_card,
    create_scored_card,
    create_citation_card,
    CardFactory,
    create_document_cards_for_tab
)

# Re-export shared base classes used by both Flet and Qt (backwards compatibility)
from .flet.document_card_factory_base import (
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
