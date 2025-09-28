"""
GUI Module for BMLibrarian

Provides graphical interfaces including configuration and research applications using Flet.
"""

from .config_app import BMLibrarianConfigApp
from .research_app import ResearchGUI
from .components import StepCard
from .dialogs import DialogManager
from .workflow import WorkflowExecutor, initialize_agents_in_main_thread
from .interactive_handler import InteractiveHandler
from .query_processor import QueryProcessor
from .workflow_steps_handler import WorkflowStepsHandler
from .report_builder import ReportBuilder

__all__ = [
    'BMLibrarianConfigApp',
    'ResearchGUI', 
    'StepCard',
    'DialogManager',
    'WorkflowExecutor',
    'initialize_agents_in_main_thread',
    'InteractiveHandler',
    'QueryProcessor',
    'WorkflowStepsHandler',
    'ReportBuilder'
]