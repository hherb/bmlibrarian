"""
Paper Weight Assessment Laboratory Package

PySide6/Qt laboratory GUI for paper weight assessment with full
visual inspection of all assessment steps and audit trails.

Modules:
    constants: UI constants (no magic numbers) - importable without Qt
    utils: Pure utility functions for text formatting - importable without Qt
    worker: Background thread for assessment (requires Qt)
    dialogs: Dialog classes (weight config, search, full text) (requires Qt)
    widgets: Custom widgets (audit trail tree) (requires Qt)
    main_window: Main application window (requires Qt)

Usage:
    # Full import (requires Qt/display):
    from bmlibrarian.lab.paper_weight_lab import PaperWeightLab, main

    # Constants/utils only (no Qt needed):
    from bmlibrarian.lab.paper_weight_lab.constants import SCORE_MAX
    from bmlibrarian.lab.paper_weight_lab.utils import format_dimension_name

    # Or run directly:
    uv run python paper_weight_lab.py
"""

# Import non-Qt modules directly - always available
from .constants import *
from .utils import *

# Qt-dependent modules are imported lazily to allow
# constants/utils to be used without a display


def _import_qt_modules():
    """Import Qt-dependent modules lazily."""
    global PaperWeightLab, main, AssessmentWorker
    global DimensionWeightDialog, DocumentSearchDialog, FullTextDialog
    global AuditTrailTreeWidget, AuditTrailSection

    from .main_window import PaperWeightLab, main
    from .worker import AssessmentWorker
    from .dialogs import DimensionWeightDialog, DocumentSearchDialog, FullTextDialog
    from .widgets import AuditTrailTreeWidget, AuditTrailSection

    return (
        PaperWeightLab, main, AssessmentWorker,
        DimensionWeightDialog, DocumentSearchDialog, FullTextDialog,
        AuditTrailTreeWidget, AuditTrailSection
    )


# Attempt to import Qt modules if possible
try:
    _import_qt_modules()
except ImportError:
    # Qt not available - only constants and utils are available
    PaperWeightLab = None
    main = None
    AssessmentWorker = None
    DimensionWeightDialog = None
    DocumentSearchDialog = None
    FullTextDialog = None
    AuditTrailTreeWidget = None
    AuditTrailSection = None


__all__ = [
    # Main (requires Qt)
    'PaperWeightLab',
    'main',
    # Worker (requires Qt)
    'AssessmentWorker',
    # Dialogs (requires Qt)
    'DimensionWeightDialog',
    'DocumentSearchDialog',
    'FullTextDialog',
    # Widgets (requires Qt)
    'AuditTrailTreeWidget',
    'AuditTrailSection',
    # Constants (no Qt needed) - from constants.py
    'WINDOW_MIN_WIDTH',
    'WINDOW_MIN_HEIGHT',
    'WINDOW_DEFAULT_WIDTH',
    'WINDOW_DEFAULT_HEIGHT',
    'PROGRESS_PENDING',
    'PROGRESS_ANALYZING',
    'PROGRESS_COMPLETE',
    'PROGRESS_ERROR',
    'SCORE_MAX',
    'SCORE_DECIMALS',
    'TREE_COL_COMPONENT',
    'TREE_COL_VALUE',
    'TREE_COL_SCORE',
    'TREE_COL_EVIDENCE',
    'TREE_COL_WIDTH_COMPONENT',
    'TREE_COL_WIDTH_VALUE',
    'TREE_COL_WIDTH_SCORE',
    'WEIGHT_SLIDER_MIN',
    'WEIGHT_SLIDER_MAX',
    'WEIGHT_SLIDER_PRECISION',
    'AUTHOR_DISPLAY_MAX_LENGTH',
    # Utils (no Qt needed) - from utils.py
    'format_dimension_name',
    'format_score',
    'format_score_with_max',
    'format_datetime',
    'truncate_with_ellipsis',
    'truncate_authors',
    'format_document_metadata',
    'format_recent_assessment_display',
    'extract_dimension_score_data',
    'prepare_tree_item_data',
    'validate_weights_sum',
    'slider_value_to_weight',
    'weight_to_slider_value',
]
