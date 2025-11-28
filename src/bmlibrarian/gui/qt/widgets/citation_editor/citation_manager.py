"""
Citation manager for coordinating citation operations.

Acts as the central coordinator between:
- Markdown editor (text with citations)
- Search panel (finding documents)
- Document panel (viewing and inserting)
- Reference builder (formatting)
"""

import logging
from typing import Optional, Dict, List, Set, Callable

from PySide6.QtCore import QObject, Signal

from bmlibrarian.writing import (
    CitationParser, CitationFormatter, ReferenceBuilder,
    Citation, FormattedReference, DocumentMetadata, CitationStyle
)

logger = logging.getLogger(__name__)


class CitationManager(QObject):
    """
    Central manager for citation operations.

    Coordinates between UI components and the writing module.

    Signals:
        citations_updated: Emitted when citation count changes
        reference_list_ready: Emitted when references are formatted
        validation_complete: Emitted with validation issues
    """

    citations_updated = Signal(int, int)  # total_citations, unique_citations
    reference_list_ready = Signal(str, list)  # formatted_text, references
    validation_complete = Signal(list)  # list of issues

    def __init__(
        self,
        style: CitationStyle = CitationStyle.VANCOUVER,
        parent: Optional[QObject] = None
    ) -> None:
        """
        Initialize citation manager.

        Args:
            style: Initial citation style
            parent: Parent QObject
        """
        super().__init__(parent)

        self._parser = CitationParser()
        self._formatter = CitationFormatter(style)
        self._builder = ReferenceBuilder(style)

        self._current_text = ""
        self._citation_metadata_cache: Dict[int, Dict] = {}

    @property
    def style(self) -> CitationStyle:
        """Get current citation style."""
        return self._formatter.style

    @style.setter
    def style(self, new_style: CitationStyle) -> None:
        """Set citation style."""
        self._formatter.style = new_style
        self._builder.style = new_style

    def update_text(self, text: str) -> None:
        """
        Update the current text and emit citation count.

        Args:
            text: Document text with citation markers
        """
        self._current_text = text

        total = self._parser.count_citations(text)
        unique = self._parser.count_unique_citations(text)

        self.citations_updated.emit(total, unique)

    def get_citation_count(self) -> tuple:
        """
        Get current citation counts.

        Returns:
            Tuple of (total_citations, unique_citations)
        """
        return (
            self._parser.count_citations(self._current_text),
            self._parser.count_unique_citations(self._current_text)
        )

    def get_citations(self) -> List[Citation]:
        """
        Get all citations from current text.

        Returns:
            List of Citation objects
        """
        return self._parser.parse_citations(self._current_text)

    def get_unique_document_ids(self) -> List[int]:
        """
        Get unique document IDs in order of appearance.

        Returns:
            List of document IDs
        """
        return self._parser.get_unique_document_ids(self._current_text)

    def create_citation_marker(self, document_id: int, label: str) -> str:
        """
        Create a citation marker.

        Args:
            document_id: Database document ID
            label: Human-readable label

        Returns:
            Citation marker string
        """
        return self._parser.create_citation_marker(document_id, label)

    def generate_label(self, document_id: int) -> str:
        """
        Generate label for a document.

        Args:
            document_id: Database document ID

        Returns:
            Label like "Smith2023"
        """
        return self._builder.generate_label(document_id)

    def format_citations(self, text: Optional[str] = None) -> tuple:
        """
        Format document with numbered citations and reference list.

        Args:
            text: Text to format (uses current text if None)

        Returns:
            Tuple of (formatted_text, references)
        """
        if text is None:
            text = self._current_text

        formatted_text, references = self._builder.build_references(text)
        self.reference_list_ready.emit(formatted_text, references)

        return formatted_text, references

    def format_full_document(
        self,
        text: Optional[str] = None,
        include_references: bool = True
    ) -> str:
        """
        Format complete document with optional reference list.

        Args:
            text: Text to format (uses current text if None)
            include_references: Whether to append reference list

        Returns:
            Complete formatted document
        """
        if text is None:
            text = self._current_text

        return self._builder.format_document(text, include_references)

    def validate_citations(self, text: Optional[str] = None) -> List[Dict]:
        """
        Validate all citations in text.

        Args:
            text: Text to validate (uses current text if None)

        Returns:
            List of validation issues
        """
        if text is None:
            text = self._current_text

        issues = self._builder.validate_citations(text)
        self.validation_complete.emit(issues)

        return issues

    def get_citation_preview(
        self,
        document_id: int,
        number: Optional[int] = None
    ) -> Dict[str, str]:
        """
        Get preview information for citation tooltip.

        Args:
            document_id: Document database ID
            number: Optional reference number

        Returns:
            Dictionary with title, authors, year, inline citation
        """
        return self._builder.get_citation_preview(document_id, number)

    def get_citation_metadata_for_preview(self) -> Dict[int, Dict]:
        """
        Get metadata for all citations for preview tooltips.

        Returns:
            Dictionary mapping document_id to metadata dict
        """
        doc_ids = self.get_unique_document_ids()

        if not doc_ids:
            return {}

        # Check cache first
        missing_ids = [id_ for id_ in doc_ids if id_ not in self._citation_metadata_cache]

        if missing_ids:
            # Fetch missing metadata
            for doc_id in missing_ids:
                preview = self._builder.get_citation_preview(doc_id)
                self._citation_metadata_cache[doc_id] = preview

        return {id_: self._citation_metadata_cache[id_] for id_ in doc_ids}

    def clear_cache(self) -> None:
        """Clear the metadata cache."""
        self._citation_metadata_cache = {}

    def get_available_styles(self) -> List[CitationStyle]:
        """Get list of available citation styles."""
        return CitationFormatter.get_available_styles()

    def get_style_description(self, style: CitationStyle) -> str:
        """Get description of a citation style."""
        return CitationFormatter.get_style_description(style)

    def replace_citation_markers_for_export(
        self,
        text: Optional[str] = None,
        style: Optional[CitationStyle] = None
    ) -> str:
        """
        Replace citation markers for export, including reference list.

        Args:
            text: Text to process (uses current text if None)
            style: Override citation style (uses current style if None)

        Returns:
            Formatted text with references
        """
        if text is None:
            text = self._current_text

        if style is not None and style != self._builder.style:
            # Temporarily change style
            original_style = self._builder.style
            self._builder.style = style
            result = self._builder.format_document(text, include_reference_list=True)
            self._builder.style = original_style
            return result

        return self._builder.format_document(text, include_reference_list=True)

    def get_raw_text_for_export(self) -> str:
        """
        Get text with citation markers intact (no formatting).

        Returns:
            Raw text with citation markers
        """
        return self._current_text

    def find_citation_at_position(self, position: int) -> Optional[Citation]:
        """
        Find citation at a character position.

        Args:
            position: Character position in text

        Returns:
            Citation at position or None
        """
        citations = self._parser.parse_citations(self._current_text)

        for citation in citations:
            end_pos = citation.position + len(citation.text)
            if citation.position <= position < end_pos:
                return citation

        return None

    def is_citation_already_used(self, document_id: int) -> bool:
        """
        Check if a citation for a document is already in the text.

        Args:
            document_id: Database document ID

        Returns:
            True if citation already exists
        """
        existing_ids = self._parser.get_unique_document_ids(self._current_text)
        return document_id in existing_ids

    def generate_reference_entry(self, document_id: int) -> str:
        """
        Generate a formatted reference entry for a document.

        Uses the current citation style to format the reference.
        The reference is not numbered (numbers are assigned during export).

        Args:
            document_id: Database document ID

        Returns:
            Formatted reference string (e.g., "- Smith J, et al. Title...")
        """
        preview = self._builder.get_citation_preview(document_id)

        # Build a simple reference line without numbering
        parts = []

        authors = preview.get('authors', 'Unknown')
        if authors:
            parts.append(authors + ".")

        title = preview.get('title', 'Untitled')
        if title:
            if not title.endswith('.'):
                title += '.'
            parts.append(title)

        journal = preview.get('journal', '')
        year = preview.get('year', '')
        if journal or year:
            journal_part = f"*{journal}*" if journal else ""
            if year:
                journal_part += f" {year}." if journal_part else f"{year}."
            parts.append(journal_part)

        return "- " + " ".join(parts)
