"""
Citation editor widget package.

A citation-aware markdown editor for academic writing with:
- Markdown syntax highlighting
- Citation marker support ([@id:12345:Smith2023])
- Semantic search integration for finding references
- Multiple citation styles (Vancouver, APA, Harvard, Chicago)
- Autosave and version history
- Export with formatted reference lists
"""

from .citation_editor_widget import CitationEditorWidget
from .markdown_editor import MarkdownEditorWidget
from .markdown_preview import CitationMarkdownPreview
from .search_panel import CitationSearchPanel
from .document_panel import CitationDocumentPanel
from .citation_manager import CitationManager

__all__ = [
    'CitationEditorWidget',
    'MarkdownEditorWidget',
    'CitationMarkdownPreview',
    'CitationSearchPanel',
    'CitationDocumentPanel',
    'CitationManager',
]
