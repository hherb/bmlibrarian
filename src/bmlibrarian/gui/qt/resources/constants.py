"""
Constants for Qt GUI styling and configuration.

This module defines all magic numbers, colors, and styling constants used
throughout the Qt GUI to ensure consistency and maintainability.
"""

from typing import Final

# ============================================================================
# Color Constants
# ============================================================================

# PDF Button Colors (Light Theme)
class PDFButtonColors:
    """Colors for PDF button states in light theme."""
    VIEW_BG: Final[str] = "#1976D2"  # Blue - View existing PDF
    VIEW_BG_HOVER: Final[str] = "#1565C0"  # Darker blue

    FETCH_BG: Final[str] = "#F57C00"  # Orange - Fetch from URL
    FETCH_BG_HOVER: Final[str] = "#EF6C00"  # Darker orange

    UPLOAD_BG: Final[str] = "#388E3C"  # Green - Upload manual
    UPLOAD_BG_HOVER: Final[str] = "#2E7D32"  # Darker green

    TEXT_COLOR: Final[str] = "white"


# PDF Button Colors (Dark Theme)
class PDFButtonColorsDark:
    """Colors for PDF button states in dark theme."""
    VIEW_BG: Final[str] = "#1976D2"  # Blue - View existing PDF
    VIEW_BG_HOVER: Final[str] = "#2196F3"  # Lighter blue

    FETCH_BG: Final[str] = "#F57C00"  # Orange - Fetch from URL
    FETCH_BG_HOVER: Final[str] = "#FB8C00"  # Lighter orange

    UPLOAD_BG: Final[str] = "#388E3C"  # Green - Upload manual
    UPLOAD_BG_HOVER: Final[str] = "#43A047"  # Lighter green

    TEXT_COLOR: Final[str] = "white"


# Score Colors
class ScoreColors:
    """Colors for document relevance scores."""
    EXCELLENT: Final[str] = "#2E7D32"  # Dark green (>= 4.5)
    GOOD: Final[str] = "#1976D2"  # Blue (>= 3.5)
    MODERATE: Final[str] = "#F57C00"  # Orange (>= 2.5)
    POOR: Final[str] = "#C62828"  # Red (< 2.5)


# Document Card Colors
class DocumentCardColors:
    """Colors for document card sections."""
    # Title/metadata header background (very pale blue)
    HEADER_BG: Final[str] = "#F0F7FF"
    HEADER_BG_HOVER: Final[str] = "#E5F0FC"

    # AI reasoning backgrounds
    AI_REASONING_POSITIVE_BG: Final[str] = "#F0FFF4"  # Very pale green (supportive)
    AI_REASONING_WARNING_BG: Final[str] = "#FFF8E6"  # Very pale orange/amber (contradicts/warns)

    # Abstract background
    ABSTRACT_BG: Final[str] = "#FAFAFA"

    # Text colors
    METADATA_TEXT: Final[str] = "#555555"
    AI_REASONING_TEXT: Final[str] = "#333333"
    ABSTRACT_TEXT: Final[str] = "#444444"


# ============================================================================
# Size Constants
# ============================================================================

class ButtonSizes:
    """Size constants for buttons."""
    MIN_HEIGHT: Final[int] = 30  # Minimum button height in pixels (reduced for compact design)
    PADDING_HORIZONTAL: Final[int] = 10  # Horizontal padding in pixels
    PADDING_VERTICAL: Final[int] = 5  # Vertical padding in pixels (reduced for compact design)
    BORDER_RADIUS: Final[int] = 4  # Border radius in pixels


class LayoutSpacing:
    """Spacing constants for layouts."""
    PDF_BUTTON_TOP_MARGIN: Final[int] = 6  # Top margin for PDF button container (reduced)
    CONTAINER_MARGIN: Final[int] = 0  # Margin for containers


# ============================================================================
# Threshold Constants
# ============================================================================

class ScoreThresholds:
    """Thresholds for score-based decisions."""
    EXCELLENT: Final[float] = 4.5  # Threshold for excellent score
    GOOD: Final[float] = 3.5  # Threshold for good score
    MODERATE: Final[float] = 2.5  # Threshold for moderate score

    # Abstract truncation threshold
    ABSTRACT_TRUNCATION_RATIO: Final[float] = 0.7  # Must retain at least 70% of desired length


class DefaultLimits:
    """Default limits for various operations."""
    MAX_AUTHORS_DISPLAY: Final[int] = 3  # Maximum authors before "et al."
    ABSTRACT_MAX_LENGTH: Final[int] = 500  # Maximum abstract length before truncation
    MAX_VISIBLE_LINES: Final[int] = 10  # Max lines before scrollable overflow
    AI_REASONING_MAX_LINES: Final[int] = 10  # Max visible lines for AI reasoning
    ABSTRACT_MAX_LINES: Final[int] = 10  # Max visible lines for abstract


# ============================================================================
# PDF Operation Constants
# ============================================================================

class PDFOperationSettings:
    """Settings for PDF operations."""
    RETRY_ATTEMPTS: Final[int] = 3  # Number of retry attempts for failed operations
    RETRY_DELAY_MS: Final[int] = 1000  # Delay between retries in milliseconds
    DOWNLOAD_TIMEOUT_SECONDS: Final[int] = 30  # Timeout for PDF downloads


# ============================================================================
# File System Constants
# ============================================================================

class FileSystemDefaults:
    """Default file system paths and settings."""
    PDF_SUBDIRECTORY: Final[str] = "pdf"  # Subdirectory name for PDFs
    KNOWLEDGEBASE_DIR: Final[str] = "knowledgebase"  # Main directory name
    PDF_EXTENSION: Final[str] = ".pdf"  # PDF file extension
    PDF_FILE_FILTER: Final[str] = "PDF Files (*.pdf)"  # File dialog filter
