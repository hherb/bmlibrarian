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

# PubMed Search Lab - Qt-based
try:
    from .pubmed_search_lab import PubMedSearchLabWindow, run_pubmed_search_lab
except ImportError:
    # Qt not available
    PubMedSearchLabWindow = None
    run_pubmed_search_lab = None

# Paper Reviewer Lab - Qt-based comprehensive paper assessment
try:
    from .paper_reviewer_lab import PaperReviewerLab
except ImportError:
    # Qt not available
    PaperReviewerLab = None

__all__ = [
    'QueryAgentLab',
    'CitationAgentLab',
    'PICOLab',
    'PaperCheckerLab',
    'PaperReviewerLab',
    'ImporterTestLab',
    'PubMedSearchLabWindow',
    'run_pubmed_search_lab',
]