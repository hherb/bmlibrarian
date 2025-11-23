"""
PaperChecker Laboratory - UI Constants

Centralized constants for the PaperChecker Laboratory.
No magic numbers - all values are named and documented.

This module can be imported without Qt dependencies.
"""

from typing import Dict, List

# =============================================================================
# Application Metadata
# =============================================================================

APP_TITLE = "PaperChecker Laboratory"
APP_SUBTITLE = "Interactive medical abstract fact-checking"


# =============================================================================
# Window Dimensions (will be scaled by DPI)
# =============================================================================

WINDOW_MIN_WIDTH = 1200
WINDOW_MIN_HEIGHT = 750
WINDOW_DEFAULT_WIDTH = 1400
WINDOW_DEFAULT_HEIGHT = 950


# =============================================================================
# Progress Indicator Symbols
# =============================================================================

PROGRESS_PENDING = "⊡"
PROGRESS_RUNNING = "⟳"
PROGRESS_COMPLETE = "✓"
PROGRESS_ERROR = "✗"


# =============================================================================
# Status Spinner Configuration
# =============================================================================

SPINNER_ANIMATION_INTERVAL_MS = 100  # Milliseconds between animation frames
SPINNER_FRAMES: List[str] = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


# =============================================================================
# Tab Indices
# =============================================================================

TAB_INDEX_INPUT = 0
TAB_INDEX_PDF_UPLOAD = 1
TAB_INDEX_WORKFLOW = 2
TAB_INDEX_RESULTS = 3

# Results sub-tab indices
RESULTS_TAB_INDEX_SUMMARY = 0
RESULTS_TAB_INDEX_STATEMENTS = 1
RESULTS_TAB_INDEX_EVIDENCE = 2
RESULTS_TAB_INDEX_VERDICTS = 3
RESULTS_TAB_INDEX_EXPORT = 4


# =============================================================================
# Workflow Steps
# =============================================================================

WORKFLOW_STEPS: List[str] = [
    "Initializing",
    "Extracting statements",
    "Generating counter-statements",
    "Searching for counter-evidence",
    "Scoring documents",
    "Extracting citations",
    "Generating counter-report",
    "Analyzing verdict",
    "Generating overall assessment",
    "Saving results",
    "Complete"
]

WORKFLOW_STEP_COUNT = len(WORKFLOW_STEPS)


# =============================================================================
# Input Validation
# =============================================================================

MIN_ABSTRACT_LENGTH = 50  # Minimum characters for a valid abstract
MAX_ABSTRACT_LENGTH = 50000  # Maximum characters (sanity check)
PMID_MAX_LENGTH = 12  # Maximum digits in a PMID


# =============================================================================
# Colors (Qt-compatible hex strings)
# =============================================================================

# Primary application colors
COLOR_PRIMARY = "#1976D2"  # Blue 700
COLOR_PRIMARY_LIGHT = "#42A5F5"  # Blue 400
COLOR_PRIMARY_DARK = "#0D47A1"  # Blue 900

# Status colors
COLOR_SUCCESS = "#43A047"  # Green 600
COLOR_WARNING = "#FB8C00"  # Orange 600
COLOR_ERROR = "#E53935"  # Red 600
COLOR_INFO = "#1E88E5"  # Blue 600

# Grey palette
COLOR_GREY_50 = "#FAFAFA"
COLOR_GREY_100 = "#F5F5F5"
COLOR_GREY_200 = "#EEEEEE"
COLOR_GREY_300 = "#E0E0E0"
COLOR_GREY_400 = "#BDBDBD"
COLOR_GREY_500 = "#9E9E9E"
COLOR_GREY_600 = "#757575"
COLOR_GREY_700 = "#616161"
COLOR_GREY_800 = "#424242"
COLOR_GREY_900 = "#212121"

# Basic colors
COLOR_WHITE = "#FFFFFF"
COLOR_BLACK = "#000000"

# Verdict-specific colors
VERDICT_COLORS: Dict[str, str] = {
    "supports": "#43A047",     # Green 600
    "contradicts": "#E53935",  # Red 600
    "undecided": "#FB8C00"     # Orange 600
}

# Confidence level colors
CONFIDENCE_COLORS: Dict[str, str] = {
    "high": "#43A047",    # Green 600
    "medium": "#FB8C00",  # Orange 600
    "low": "#E53935"      # Red 600
}

# Statement type colors
STATEMENT_TYPE_COLORS: Dict[str, str] = {
    "hypothesis": "#7E57C2",   # Deep Purple 400
    "finding": "#42A5F5",      # Blue 400
    "conclusion": "#66BB6A"    # Green 400
}

# Search strategy colors (for provenance display)
SEARCH_STRATEGY_COLORS: Dict[str, str] = {
    "semantic": "#42A5F5",  # Blue 400
    "hyde": "#AB47BC",      # Purple 400
    "keyword": "#26A69A"    # Teal 400
}


# =============================================================================
# Tree Widget Configuration (for evidence/citations display)
# =============================================================================

TREE_COL_TITLE = 0
TREE_COL_SCORE = 1
TREE_COL_STRATEGIES = 2
TREE_COL_PASSAGE = 3

# Column widths in characters (scaled by char_width)
TREE_COL_WIDTH_TITLE = 40
TREE_COL_WIDTH_SCORE = 8
TREE_COL_WIDTH_STRATEGIES = 15


# =============================================================================
# Display Limits (not data truncation - UI display only)
# =============================================================================

AUTHOR_DISPLAY_MAX_LENGTH = 100  # Max chars for author list in compact display
TITLE_DISPLAY_MAX_LENGTH = 150   # Max chars for title in compact display
PASSAGE_PREVIEW_LENGTH = 200     # Preview length for citation passages


# =============================================================================
# Document Matching (for PDF upload)
# =============================================================================

TITLE_SIMILARITY_THRESHOLD = 0.3  # Minimum similarity for title matching
ALTERNATIVE_MATCHES_LIMIT = 5     # Max alternative matches to show


# =============================================================================
# Source Types
# =============================================================================

SOURCE_ID_OTHER = 3  # Source ID for user-uploaded documents


# =============================================================================
# Score Display
# =============================================================================

SCORE_MIN = 1
SCORE_MAX = 5
SCORE_DECIMALS = 1


# =============================================================================
# Export
# =============================================================================

EXPORT_JSON_INDENT = 2  # JSON indentation spaces


# =============================================================================
# Module Exports
# =============================================================================

__all__ = [
    # Application
    'APP_TITLE',
    'APP_SUBTITLE',
    # Window
    'WINDOW_MIN_WIDTH',
    'WINDOW_MIN_HEIGHT',
    'WINDOW_DEFAULT_WIDTH',
    'WINDOW_DEFAULT_HEIGHT',
    # Progress
    'PROGRESS_PENDING',
    'PROGRESS_RUNNING',
    'PROGRESS_COMPLETE',
    'PROGRESS_ERROR',
    # Spinner
    'SPINNER_ANIMATION_INTERVAL_MS',
    'SPINNER_FRAMES',
    # Tab indices
    'TAB_INDEX_INPUT',
    'TAB_INDEX_PDF_UPLOAD',
    'TAB_INDEX_WORKFLOW',
    'TAB_INDEX_RESULTS',
    'RESULTS_TAB_INDEX_SUMMARY',
    'RESULTS_TAB_INDEX_STATEMENTS',
    'RESULTS_TAB_INDEX_EVIDENCE',
    'RESULTS_TAB_INDEX_VERDICTS',
    'RESULTS_TAB_INDEX_EXPORT',
    # Workflow
    'WORKFLOW_STEPS',
    'WORKFLOW_STEP_COUNT',
    # Validation
    'MIN_ABSTRACT_LENGTH',
    'MAX_ABSTRACT_LENGTH',
    'PMID_MAX_LENGTH',
    # Colors
    'COLOR_PRIMARY',
    'COLOR_PRIMARY_LIGHT',
    'COLOR_PRIMARY_DARK',
    'COLOR_SUCCESS',
    'COLOR_WARNING',
    'COLOR_ERROR',
    'COLOR_INFO',
    'COLOR_GREY_50',
    'COLOR_GREY_100',
    'COLOR_GREY_200',
    'COLOR_GREY_300',
    'COLOR_GREY_400',
    'COLOR_GREY_500',
    'COLOR_GREY_600',
    'COLOR_GREY_700',
    'COLOR_GREY_800',
    'COLOR_GREY_900',
    'COLOR_WHITE',
    'COLOR_BLACK',
    'VERDICT_COLORS',
    'CONFIDENCE_COLORS',
    'STATEMENT_TYPE_COLORS',
    'SEARCH_STRATEGY_COLORS',
    # Tree columns
    'TREE_COL_TITLE',
    'TREE_COL_SCORE',
    'TREE_COL_STRATEGIES',
    'TREE_COL_PASSAGE',
    'TREE_COL_WIDTH_TITLE',
    'TREE_COL_WIDTH_SCORE',
    'TREE_COL_WIDTH_STRATEGIES',
    # Display limits
    'AUTHOR_DISPLAY_MAX_LENGTH',
    'TITLE_DISPLAY_MAX_LENGTH',
    'PASSAGE_PREVIEW_LENGTH',
    # Document matching
    'TITLE_SIMILARITY_THRESHOLD',
    'ALTERNATIVE_MATCHES_LIMIT',
    # Source
    'SOURCE_ID_OTHER',
    # Score
    'SCORE_MIN',
    'SCORE_MAX',
    'SCORE_DECIMALS',
    # Export
    'EXPORT_JSON_INDENT',
]
