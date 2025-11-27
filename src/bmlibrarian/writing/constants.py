"""
Constants for the writing module.

Defines default values for autosave intervals, version limits,
citation patterns, and other configuration parameters.
"""

import re
from enum import Enum
from typing import Final


# ============================================================================
# Autosave Configuration
# ============================================================================

# Default autosave interval in seconds
AUTOSAVE_INTERVAL_SECONDS: Final[int] = 60

# Maximum number of autosave versions to keep per document
MAX_VERSIONS: Final[int] = 10


# ============================================================================
# Citation Patterns
# ============================================================================

# Citation marker format: [@id:12345:Smith2023]
# - id: prefix indicating document ID follows
# - 12345: the actual document ID (integer)
# - Smith2023: human-readable label (author + year)
CITATION_PATTERN: Final[re.Pattern] = re.compile(
    r'\[@id:(\d+):([^\]]+)\]'
)

# Pattern for extracting just the ID portion
CITATION_ID_PATTERN: Final[re.Pattern] = re.compile(
    r'@id:(\d+)'
)

# Pattern for detecting incomplete citations (user typing)
CITATION_INCOMPLETE_PATTERN: Final[re.Pattern] = re.compile(
    r'\[@(?:id:)?(?:\d*)?(?::)?'
)


# ============================================================================
# Citation Styles
# ============================================================================

class CitationStyle(str, Enum):
    """Supported citation formatting styles."""

    VANCOUVER = "vancouver"  # Numbered, common in medical journals
    APA = "apa"              # Author-date style
    HARVARD = "harvard"      # Author-date variant
    CHICAGO = "chicago"      # Chicago Manual of Style

    @classmethod
    def get_default(cls) -> "CitationStyle":
        """Get the default citation style for medical writing."""
        return cls.VANCOUVER


# Default citation style (Vancouver for medical writing)
DEFAULT_CITATION_STYLE: Final[CitationStyle] = CitationStyle.VANCOUVER


# ============================================================================
# Editor Configuration
# ============================================================================

# Default editor font settings
DEFAULT_EDITOR_FONT_FAMILY: Final[str] = "monospace"
DEFAULT_EDITOR_FONT_SIZE: Final[int] = 12

# Show line numbers in editor
DEFAULT_SHOW_LINE_NUMBERS: Final[bool] = True

# Sync scroll between editor and preview
DEFAULT_PREVIEW_SYNC_SCROLL: Final[bool] = True


# ============================================================================
# Semantic Search Configuration
# ============================================================================

# Default similarity threshold for semantic search
SEMANTIC_SEARCH_THRESHOLD: Final[float] = 0.5

# Default number of results for semantic search
SEMANTIC_SEARCH_LIMIT: Final[int] = 20


# ============================================================================
# Reference Formatting
# ============================================================================

# Maximum authors to show before "et al."
MAX_AUTHORS_BEFORE_ET_AL: Final[int] = 6

# Separator between multiple citations
CITATION_SEPARATOR: Final[str] = ","

# Format for combined citations (e.g., [1,2,3] or [1-3])
COMBINE_SEQUENTIAL_CITATIONS: Final[bool] = True
