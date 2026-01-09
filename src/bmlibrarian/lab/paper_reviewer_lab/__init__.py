"""
Paper Reviewer Laboratory Package

PySide6/Qt laboratory GUI for comprehensive paper assessment with
DOI/PMID/PDF/text input, visual workflow progress, and results export.

Modules:
    constants: UI constants (no magic numbers) - importable without Qt
    worker: Background thread for paper review (requires Qt)
    widgets: Custom widgets (step cards) (requires Qt)
    tabs: Tab panels (input, workflow, results) (requires Qt)
    main_window: Main application window (requires Qt)

Usage:
    # Full import (requires Qt/display):
    from bmlibrarian.lab.paper_reviewer_lab import PaperReviewerLab, main

    # Constants only (no Qt needed):
    from bmlibrarian.lab.paper_reviewer_lab.constants import WORKFLOW_STEPS

    # Or run directly:
    uv run python -m bmlibrarian.lab.paper_reviewer_lab
"""

# Import non-Qt modules directly - always available
from .constants import *

# Qt-dependent modules are imported lazily to allow
# constants to be used without a display


def _import_qt_modules():
    """Import Qt-dependent modules lazily."""
    global PaperReviewerLab, main, APP_TITLE, APP_SUBTITLE
    global ReviewWorker, ReviewThread
    global StepCard
    global InputPanel, WorkflowPanel, ResultsPanel

    from .main_window import PaperReviewerLab, main, APP_TITLE, APP_SUBTITLE
    from .worker import ReviewWorker, ReviewThread
    from .widgets import StepCard
    from .tabs import InputPanel, WorkflowPanel, ResultsPanel

    return (
        PaperReviewerLab, main, APP_TITLE, APP_SUBTITLE,
        ReviewWorker, ReviewThread,
        StepCard,
        InputPanel, WorkflowPanel, ResultsPanel
    )


# Attempt to import Qt modules if possible
try:
    _import_qt_modules()
except ImportError:
    # Qt not available - only constants are available
    PaperReviewerLab = None
    main = None
    APP_TITLE = None
    APP_SUBTITLE = None
    ReviewWorker = None
    ReviewThread = None
    StepCard = None
    InputPanel = None
    WorkflowPanel = None
    ResultsPanel = None


__all__ = [
    # Main (requires Qt)
    'PaperReviewerLab',
    'main',
    'APP_TITLE',
    'APP_SUBTITLE',
    # Workers (requires Qt)
    'ReviewWorker',
    'ReviewThread',
    # Widgets (requires Qt)
    'StepCard',
    # Tabs (requires Qt)
    'InputPanel',
    'WorkflowPanel',
    'ResultsPanel',
    # Constants (no Qt needed) - from constants.py
    'VERSION',
    'WINDOW_MIN_WIDTH_MULTIPLIER',
    'WINDOW_MIN_HEIGHT_MULTIPLIER',
    'WINDOW_DEFAULT_WIDTH_MULTIPLIER',
    'WINDOW_DEFAULT_HEIGHT_MULTIPLIER',
    'INPUT_PANEL_RATIO',
    'WORKFLOW_PANEL_RATIO',
    'RESULTS_PANEL_RATIO',
    'TAB_INPUT',
    'TAB_PDF',
    'TAB_WORKFLOW',
    'TAB_RESULTS',
    'WORKFLOW_STEPS',
    'STEP_WEIGHTS',
    'STATUS_PENDING',
    'STATUS_IN_PROGRESS',
    'STATUS_COMPLETED',
    'STATUS_SKIPPED',
    'STATUS_FAILED',
    'STATUS_COLORS',
    'INPUT_TYPE_DOI',
    'INPUT_TYPE_PMID',
    'INPUT_TYPE_PDF',
    'INPUT_TYPE_TEXT',
    'INPUT_TYPE_FILE',
    'PDF_FILE_FILTER',
    'TEXT_FILE_FILTER',
    'EXPORT_FORMAT_MARKDOWN',
    'EXPORT_FORMAT_PDF',
    'EXPORT_FORMAT_JSON',
    'EXPORT_FILE_FILTERS',
    'PROGRESS_UPDATE_INTERVAL_MS',
    'STEP_EXPAND_ANIMATION_MS',
    'DOI_PATTERN',
    'PMID_PATTERN',
]
