"""
BMLibrarian Lab Module

Experimental interfaces and tools for testing and developing BMLibrarian components.
"""

from .query_lab import QueryAgentLab
from .citation_lab import CitationAgentLab
from .pico_lab import PICOLab
from .importer_test_lab import ImporterTestLab

# PaperCheckerLab is now a package - import lazily to avoid Qt dependency issues
try:
    from .paper_checker_lab import PaperCheckerLab
except ImportError:
    # Qt not available
    PaperCheckerLab = None

# Legacy Flet-based PaperCheckerLab
try:
    from .paper_checker_lab_flet import PaperCheckerLab as PaperCheckerLabFlet
except ImportError:
    PaperCheckerLabFlet = None

__all__ = [
    'QueryAgentLab',
    'CitationAgentLab',
    'PICOLab',
    'PaperCheckerLab',
    'PaperCheckerLabFlet',
    'ImporterTestLab',
]