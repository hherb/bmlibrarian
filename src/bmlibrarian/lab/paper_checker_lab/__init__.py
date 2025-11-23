"""
PaperChecker Laboratory Package

PySide6/Qt laboratory GUI for medical abstract fact-checking with full
visual workflow progress and evidence inspection.

Modules:
    constants: UI constants (no magic numbers) - importable without Qt
    utils: Pure utility functions for text formatting - importable without Qt
    worker: Background thread for paper checking (requires Qt)
    dialogs: Dialog classes (full text, export preview, PMID lookup) (requires Qt)
    widgets: Custom widgets (workflow cards, citations, verdicts) (requires Qt)
    main_window: Main application window (requires Qt)

Usage:
    # Full import (requires Qt/display):
    from bmlibrarian.lab.paper_checker_lab import PaperCheckerLab, main

    # Constants/utils only (no Qt needed):
    from bmlibrarian.lab.paper_checker_lab.constants import WORKFLOW_STEPS
    from bmlibrarian.lab.paper_checker_lab.utils import validate_abstract

    # Or run directly:
    uv run python paper_checker_lab.py
"""

# Import non-Qt modules directly - always available
from .constants import *
from .utils import *

# Qt-dependent modules are imported lazily to allow
# constants/utils to be used without a display


def _import_qt_modules():
    """Import Qt-dependent modules lazily."""
    global PaperCheckerLab, main
    global PaperCheckWorker, DocumentFetchWorker
    global FullTextDialog, ExportPreviewDialog, PMIDLookupDialog
    global StatusSpinnerWidget, WorkflowStepCard, VerdictBadge
    global StatChipWidget, CitationCardWidget, StatisticsSection
    global InputTab, PDFUploadTab, WorkflowTab, ResultsTab

    from .main_window import PaperCheckerLab, main
    from .worker import PaperCheckWorker, DocumentFetchWorker
    from .dialogs import FullTextDialog, ExportPreviewDialog, PMIDLookupDialog
    from .widgets import (
        StatusSpinnerWidget, WorkflowStepCard, VerdictBadge,
        StatChipWidget, CitationCardWidget, StatisticsSection
    )
    from .tabs import InputTab, PDFUploadTab, WorkflowTab, ResultsTab

    return (
        PaperCheckerLab, main,
        PaperCheckWorker, DocumentFetchWorker,
        FullTextDialog, ExportPreviewDialog, PMIDLookupDialog,
        StatusSpinnerWidget, WorkflowStepCard, VerdictBadge,
        StatChipWidget, CitationCardWidget, StatisticsSection,
        InputTab, PDFUploadTab, WorkflowTab, ResultsTab
    )


# Attempt to import Qt modules if possible
try:
    _import_qt_modules()
except ImportError:
    # Qt not available - only constants and utils are available
    PaperCheckerLab = None
    main = None
    PaperCheckWorker = None
    DocumentFetchWorker = None
    FullTextDialog = None
    ExportPreviewDialog = None
    PMIDLookupDialog = None
    StatusSpinnerWidget = None
    WorkflowStepCard = None
    VerdictBadge = None
    StatChipWidget = None
    CitationCardWidget = None
    StatisticsSection = None
    InputTab = None
    PDFUploadTab = None
    WorkflowTab = None
    ResultsTab = None


__all__ = [
    # Main (requires Qt)
    'PaperCheckerLab',
    'main',
    # Workers (requires Qt)
    'PaperCheckWorker',
    'DocumentFetchWorker',
    # Dialogs (requires Qt)
    'FullTextDialog',
    'ExportPreviewDialog',
    'PMIDLookupDialog',
    # Widgets (requires Qt)
    'StatusSpinnerWidget',
    'WorkflowStepCard',
    'VerdictBadge',
    'StatChipWidget',
    'CitationCardWidget',
    'StatisticsSection',
    # Tabs (requires Qt)
    'InputTab',
    'PDFUploadTab',
    'WorkflowTab',
    'ResultsTab',
    # Constants (no Qt needed) - from constants.py
    'APP_TITLE',
    'APP_SUBTITLE',
    'WINDOW_MIN_WIDTH',
    'WINDOW_MIN_HEIGHT',
    'WINDOW_DEFAULT_WIDTH',
    'WINDOW_DEFAULT_HEIGHT',
    'PROGRESS_PENDING',
    'PROGRESS_RUNNING',
    'PROGRESS_COMPLETE',
    'PROGRESS_ERROR',
    'SPINNER_ANIMATION_INTERVAL_MS',
    'SPINNER_FRAMES',
    'TAB_INDEX_INPUT',
    'TAB_INDEX_PDF_UPLOAD',
    'TAB_INDEX_WORKFLOW',
    'TAB_INDEX_RESULTS',
    'WORKFLOW_STEPS',
    'WORKFLOW_STEP_COUNT',
    'MIN_ABSTRACT_LENGTH',
    'MAX_ABSTRACT_LENGTH',
    'PMID_MAX_LENGTH',
    'VERDICT_COLORS',
    'CONFIDENCE_COLORS',
    'STATEMENT_TYPE_COLORS',
    'SEARCH_STRATEGY_COLORS',
    # Utils (no Qt needed) - from utils.py
    'validate_abstract',
    'validate_pmid',
    'format_verdict_display',
    'format_confidence_display',
    'format_statement_type_display',
    'format_search_strategy_display',
    'format_score',
    'format_score_badge',
    'truncate_with_ellipsis',
    'truncate_authors',
    'truncate_title',
    'truncate_passage',
    'format_datetime',
    'format_duration',
    'format_document_metadata',
    'format_ama_citation',
    'format_search_stats',
    'get_workflow_step_index',
    'calculate_workflow_progress',
    'map_agent_progress_to_step',
]
