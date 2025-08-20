"""
BMLibrarian CLI Module

This package contains the command-line interface components for BMLibrarian,
organized into focused modules for better maintainability.

Modules:
- config: Configuration management and command-line parsing
- ui: User interface components and display functions
- query_processing: Query validation, editing, and search orchestration
- formatting: Report formatting and export utilities
- workflow: Main research workflow orchestration
"""

from .config import CLIConfig
from .ui import UserInterface
from .query_processing import QueryProcessor
from .formatting import ReportFormatter
from .workflow import WorkflowOrchestrator

__all__ = [
    'CLIConfig',
    'UserInterface', 
    'QueryProcessor',
    'ReportFormatter',
    'WorkflowOrchestrator'
]