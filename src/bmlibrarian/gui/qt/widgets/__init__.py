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
from .pdf_upload_widget import PDFUploadWidget
from .pdf_upload_workers import (
    QuickExtractWorker,
    LLMExtractWorker,
    QuickMatchResult,
    LLMExtractResult,
)
from .validators import (
    validate_pmid,
    validate_doi,
    validate_year,
    validate_title,
    validate_pdf_file,
    classify_extraction_error,
    sanitize_llm_input,
    ValidationStatus,
    WORKER_TERMINATE_TIMEOUT_MS,
    LLM_MAX_TEXT_LENGTH,
)
from .document_create_dialog import DocumentCreateDialog
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
    'PDFUploadWidget',
    'QuickExtractWorker',
    'LLMExtractWorker',
    'QuickMatchResult',
    'LLMExtractResult',
    # Validators
    'validate_pmid',
    'validate_doi',
    'validate_year',
    'validate_title',
    'validate_pdf_file',
    'classify_extraction_error',
    'sanitize_llm_input',
    'ValidationStatus',
    'WORKER_TERMINATE_TIMEOUT_MS',
    'LLM_MAX_TEXT_LENGTH',
    # Document creation
    'DocumentCreateDialog',
    # Progress widgets
    'ProgressWidget',
    'StepProgressWidget',
    'SpinnerWidget',
    'CompactProgressWidget',
    'UserProfileWidget',
    'card_utils',
]
