"""
Writing module for BMLibrarian.

Provides the citation-aware markdown editor functionality including:
- Citation parsing and formatting
- Document persistence with autosave
- Multiple citation styles (Vancouver, APA, Harvard, Chicago)
"""

from .models import (
    Citation,
    DocumentMetadata,
    FormattedReference,
    WritingDocument,
    DocumentVersion,
    CitationStyle,
)
from .citation_parser import CitationParser
from .citation_formatter import CitationFormatter
from .document_store import DocumentStore
from .reference_builder import ReferenceBuilder
from .constants import (
    AUTOSAVE_INTERVAL_SECONDS,
    MAX_VERSIONS,
    DEFAULT_CITATION_STYLE,
    CITATION_PATTERN,
)

__all__ = [
    # Models
    'Citation',
    'DocumentMetadata',
    'FormattedReference',
    'WritingDocument',
    'DocumentVersion',
    'CitationStyle',
    # Classes
    'CitationParser',
    'CitationFormatter',
    'DocumentStore',
    'ReferenceBuilder',
    # Constants
    'AUTOSAVE_INTERVAL_SECONDS',
    'MAX_VERSIONS',
    'DEFAULT_CITATION_STYLE',
    'CITATION_PATTERN',
]
