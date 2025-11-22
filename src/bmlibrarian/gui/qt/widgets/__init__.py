"""
Reusable Qt widgets for BMLibrarian GUI.

This module provides a collection of reusable widgets used across
different tabs and plugins.
"""

from .document_card import DocumentCard
from .collapsible_document_card import CollapsibleDocumentCard
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
from .user_profile_widget import UserProfileWidget
from . import card_utils

__all__ = [
    'DocumentCard',
    'CollapsibleDocumentCard',
    'CitationCard',
    'MarkdownViewer',
    'CollapsibleSection',
    'PDFViewerWidget',
    'ProgressWidget',
    'StepProgressWidget',
    'SpinnerWidget',
    'CompactProgressWidget',
    'UserProfileWidget',
    'card_utils',
]
