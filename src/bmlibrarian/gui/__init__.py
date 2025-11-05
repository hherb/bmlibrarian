"""
GUI Module for BMLibrarian

Provides graphical interfaces including configuration and research applications using Flet.
"""

from .config_app import BMLibrarianConfigApp
from .research_app import ResearchGUI
from .components import StepCard
from .dialogs import DialogManager
from .workflow import WorkflowExecutor, initialize_agents_in_main_thread, cleanup_agents
from .interactive_handler import InteractiveHandler
from .query_processor import QueryProcessor
from .workflow_steps_handler import WorkflowStepsHandler
from .report_builder import ReportBuilder
from .unified_document_card import (
    UnifiedDocumentCard,
    DocumentCardContext,
    create_literature_card,
    create_scored_card,
    create_citation_card
)
from .card_factory import CardFactory, create_document_cards_for_tab

__all__ = [
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
    'create_document_cards_for_tab'
]