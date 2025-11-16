"""
Reusable Qt widgets for BMLibrarian GUI.

This module provides a collection of reusable widgets used across
different tabs and plugins.
"""

from .document_card import DocumentCard
from .citation_card import CitationCard
from .markdown_viewer import MarkdownViewer
from .collapsible_section import CollapsibleSection
from .pdf_viewer import PDFViewerWidget
from .progress_widget import (
    ProgressWidget,
    StepProgressWidget,
    SpinnerWidget,
    CompactProgressWidget
)

__all__ = [
    'DocumentCard',
    'CitationCard',
    'MarkdownViewer',
    'CollapsibleSection',
    'PDFViewerWidget',
    'ProgressWidget',
    'StepProgressWidget',
    'SpinnerWidget',
    'CompactProgressWidget',
]
