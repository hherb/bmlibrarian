"""
Research plugin for BMLibrarian Qt GUI.

This module provides the research workflow interface including:
- ResearchTabWidget: Main widget for research workflow
- Tab builders: Pure functions for creating UI tabs
- Tab updaters: Pure functions for updating tab content
- Workflow handlers: Signal handlers for workflow execution
- Export utilities: File I/O for saving reports
"""

from .research_tab import ResearchTabWidget
from .constants import UIConstants, StyleSheets
from .tab_builders import (
    build_search_tab,
    build_literature_tab,
    build_scoring_tab,
    build_citations_tab,
    build_preliminary_tab,
    build_counterfactual_tab,
    build_report_tab,
    TabRefs,
)

__all__ = [
    'ResearchTabWidget',
    'UIConstants',
    'StyleSheets',
    'build_search_tab',
    'build_literature_tab',
    'build_scoring_tab',
    'build_citations_tab',
    'build_preliminary_tab',
    'build_counterfactual_tab',
    'build_report_tab',
    'TabRefs',
]
