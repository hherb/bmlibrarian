"""
Paper Weight Laboratory - UI Constants

Centralized constants for the Paper Weight Assessment Laboratory.
No magic numbers - all values are named and documented.
"""

# =============================================================================
# Window Dimensions (will be scaled by DPI)
# =============================================================================

WINDOW_MIN_WIDTH = 1000
WINDOW_MIN_HEIGHT = 700
WINDOW_DEFAULT_WIDTH = 1200
WINDOW_DEFAULT_HEIGHT = 900


# =============================================================================
# Progress Indicator Symbols
# =============================================================================

PROGRESS_PENDING = "⊡"
PROGRESS_ANALYZING = "⟳"
PROGRESS_COMPLETE = "✓"
PROGRESS_ERROR = "✗"


# =============================================================================
# Score Display
# =============================================================================

SCORE_MAX = 10.0
SCORE_DECIMALS = 2


# =============================================================================
# Tree Widget Column Configuration
# =============================================================================

TREE_COL_COMPONENT = 0
TREE_COL_VALUE = 1
TREE_COL_SCORE = 2
TREE_COL_EVIDENCE = 3

# Column widths in characters (will be scaled by char_width)
TREE_COL_WIDTH_COMPONENT = 25
TREE_COL_WIDTH_VALUE = 20
TREE_COL_WIDTH_SCORE = 10


# =============================================================================
# Weight Slider Configuration
# =============================================================================

WEIGHT_SLIDER_MIN = 0
WEIGHT_SLIDER_MAX = 100
WEIGHT_SLIDER_PRECISION = 100  # Divide by this to get actual weight (0.00-1.00)


# =============================================================================
# Author Display
# =============================================================================

AUTHOR_DISPLAY_MAX_LENGTH = 100  # Max chars before truncation in metadata display


# =============================================================================
# Status Spinner Configuration
# =============================================================================

SPINNER_ANIMATION_INTERVAL_MS = 100  # Milliseconds between spinner animation frames
SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]  # Braille spinner


# =============================================================================
# Tab Indices
# =============================================================================

TAB_INDEX_SEARCH = 0
TAB_INDEX_PDF_UPLOAD = 1
TAB_INDEX_RESULTS = 2


# =============================================================================
# Source Types
# =============================================================================

SOURCE_ID_OTHER = 3  # Source ID for user-uploaded documents


# =============================================================================
# Document Matching
# =============================================================================

TITLE_SIMILARITY_THRESHOLD = 0.3  # Minimum similarity score for title matching
ALTERNATIVE_MATCHES_LIMIT = 5  # Maximum number of alternative matches to show


# =============================================================================
# Worker Thread Configuration
# =============================================================================

WORKER_TERMINATE_TIMEOUT_MS = 3000  # Maximum time to wait for worker thread termination


# =============================================================================
# Input Validation
# =============================================================================

# PMID validation (PubMed IDs are positive integers, typically 1-8 digits)
PMID_MIN_VALUE = 1
PMID_MAX_VALUE = 99999999  # 8 digits max

# Publication year validation
YEAR_MIN_VALUE = 1800  # Oldest reasonable publication year
YEAR_MAX_VALUE = 2100  # Future upper bound for pre-prints

# DOI pattern (basic validation: 10.xxxx/...)
DOI_PATTERN = r'^10\.\d{4,}/\S+$'

# PDF file size limit (in megabytes)
PDF_MAX_FILE_SIZE_MB = 50  # Warn for files larger than 50MB
PDF_MAX_FILE_SIZE_BYTES = PDF_MAX_FILE_SIZE_MB * 1024 * 1024


__all__ = [
    # Window
    'WINDOW_MIN_WIDTH',
    'WINDOW_MIN_HEIGHT',
    'WINDOW_DEFAULT_WIDTH',
    'WINDOW_DEFAULT_HEIGHT',
    # Progress
    'PROGRESS_PENDING',
    'PROGRESS_ANALYZING',
    'PROGRESS_COMPLETE',
    'PROGRESS_ERROR',
    # Score
    'SCORE_MAX',
    'SCORE_DECIMALS',
    # Tree columns
    'TREE_COL_COMPONENT',
    'TREE_COL_VALUE',
    'TREE_COL_SCORE',
    'TREE_COL_EVIDENCE',
    'TREE_COL_WIDTH_COMPONENT',
    'TREE_COL_WIDTH_VALUE',
    'TREE_COL_WIDTH_SCORE',
    # Weight slider
    'WEIGHT_SLIDER_MIN',
    'WEIGHT_SLIDER_MAX',
    'WEIGHT_SLIDER_PRECISION',
    # Display
    'AUTHOR_DISPLAY_MAX_LENGTH',
    # Spinner
    'SPINNER_ANIMATION_INTERVAL_MS',
    'SPINNER_FRAMES',
    # Tabs
    'TAB_INDEX_SEARCH',
    'TAB_INDEX_PDF_UPLOAD',
    'TAB_INDEX_RESULTS',
    # Source
    'SOURCE_ID_OTHER',
    # Document Matching
    'TITLE_SIMILARITY_THRESHOLD',
    'ALTERNATIVE_MATCHES_LIMIT',
    # Worker Thread
    'WORKER_TERMINATE_TIMEOUT_MS',
    # Input Validation
    'PMID_MIN_VALUE',
    'PMID_MAX_VALUE',
    'YEAR_MIN_VALUE',
    'YEAR_MAX_VALUE',
    'DOI_PATTERN',
    'PDF_MAX_FILE_SIZE_MB',
    'PDF_MAX_FILE_SIZE_BYTES',
]
