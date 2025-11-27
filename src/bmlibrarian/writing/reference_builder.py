"""
Reference builder for constructing citation reference lists.

Fetches document metadata from the database and builds
formatted reference lists using the citation formatter.
"""

import logging
from typing import List, Dict, Optional, Tuple, Any, TYPE_CHECKING

from .models import Citation, DocumentMetadata, FormattedReference
from .citation_parser import CitationParser
from .citation_formatter import CitationFormatter
from .constants import CitationStyle, COMBINE_SEQUENTIAL_CITATIONS

if TYPE_CHECKING:
    from bmlibrarian.database import DatabaseManager

logger = logging.getLogger(__name__)


class ReferenceBuilder:
    """
    Builds reference lists from citations in document text.

    Workflow:
    1. Parse citations from text
    2. Fetch document metadata from database
    3. Assign sequential numbers (order of first appearance)
    4. Format references according to citation style
    5. Replace citation markers with numbers/inline citations
    6. Generate reference list
    """

    def __init__(
        self,
        style: CitationStyle = CitationStyle.VANCOUVER
    ) -> None:
        """
        Initialize reference builder.

        Args:
            style: Citation formatting style
        """
        self._parser = CitationParser()
        self._formatter = CitationFormatter(style)
        self._db_manager = None

    def _get_db_manager(self) -> "DatabaseManager":
        """
        Lazy load database manager.

        Returns:
            DatabaseManager instance
        """
        if self._db_manager is None:
            from bmlibrarian.database import get_db_manager
            self._db_manager = get_db_manager()
        return self._db_manager

    @property
    def style(self) -> CitationStyle:
        """Get current citation style."""
        return self._formatter.style

    @style.setter
    def style(self, new_style: CitationStyle) -> None:
        """Set citation style."""
        self._formatter.style = new_style

    def build_references(
        self,
        text: str
    ) -> Tuple[str, List[FormattedReference]]:
        """
        Build formatted document with reference list.

        Args:
            text: Document text with citation markers

        Returns:
            Tuple of (formatted_text, reference_list)
        """
        # Get unique document IDs in order of appearance
        doc_ids = self._parser.get_unique_document_ids(text)

        if not doc_ids:
            return text, []

        # Fetch metadata for all cited documents
        metadata_map = self._fetch_document_metadata(doc_ids)

        # Create number mapping
        id_to_number = {doc_id: i + 1 for i, doc_id in enumerate(doc_ids)}

        # Build reference list
        references = []
        for doc_id in doc_ids:
            metadata = metadata_map.get(doc_id)
            if metadata:
                number = id_to_number[doc_id]
                formatted_text = self._formatter.format_reference(metadata, number)
                references.append(FormattedReference(
                    number=number,
                    document_id=doc_id,
                    formatted_text=formatted_text,
                    metadata=metadata
                ))
            else:
                # Document not found - create placeholder
                number = id_to_number[doc_id]
                references.append(FormattedReference(
                    number=number,
                    document_id=doc_id,
                    formatted_text=f"{number}. [Document {doc_id} not found]",
                    metadata=None
                ))

        # Replace citations with numbers
        formatted_text = self._replace_citations(text, id_to_number)

        return formatted_text, references

    def format_document(
        self,
        text: str,
        include_reference_list: bool = True
    ) -> str:
        """
        Format document with citations replaced and optional reference list.

        Args:
            text: Document text with citation markers
            include_reference_list: Whether to append reference list

        Returns:
            Formatted markdown document
        """
        formatted_text, references = self.build_references(text)

        if include_reference_list and references:
            reference_section = self._formatter.format_reference_list(references)
            formatted_text += reference_section

        return formatted_text

    def get_citation_preview(
        self,
        document_id: int,
        number: Optional[int] = None
    ) -> Dict[str, str]:
        """
        Get preview information for a citation tooltip.

        Args:
            document_id: Document database ID
            number: Optional reference number

        Returns:
            Dictionary with title, authors, year, inline citation
        """
        metadata = self._fetch_single_metadata(document_id)

        if not metadata:
            return {
                'title': 'Document not found',
                'authors': '',
                'year': '',
                'journal': '',
                'inline': f'[{number}]' if number else f'[@id:{document_id}]'
            }

        return {
            'title': metadata.title,
            'authors': ', '.join(metadata.authors[:3]) + ('...' if len(metadata.authors) > 3 else ''),
            'year': str(metadata.year) if metadata.year else 'n.d.',
            'journal': metadata.journal or '',
            'inline': self._formatter.format_inline_citation(metadata, number)
        }

    def _fetch_document_metadata(
        self,
        document_ids: List[int]
    ) -> Dict[int, DocumentMetadata]:
        """
        Fetch metadata for multiple documents.

        Args:
            document_ids: List of document IDs

        Returns:
            Dictionary mapping document_id to DocumentMetadata
        """
        if not document_ids:
            return {}

        db = self._get_db_manager()
        metadata_map = {}

        with db.get_connection() as conn:
            with conn.cursor() as cur:
                # Use ANY for array lookup
                # Note: authors are stored as text[] in document table
                # Note: volume/issue/pages columns don't exist in schema
                cur.execute(
                    """
                    SELECT
                        d.id,
                        d.title,
                        d.doi,
                        d.abstract,
                        d.publication,
                        EXTRACT(YEAR FROM d.publication_date)::INTEGER as year,
                        d.publication_date,
                        CASE WHEN d.source_id = 1 THEN d.external_id ELSE NULL END as pmid,
                        array_to_string(d.authors, '; ') as authors
                    FROM public.document d
                    WHERE d.id = ANY(%s)
                    """,
                    (document_ids,)
                )
                rows = cur.fetchall()

        for row in rows:
            doc_id = row[0]
            authors_str = row[8] or ""
            authors = [a.strip() for a in authors_str.split(';') if a.strip()]

            metadata_map[doc_id] = DocumentMetadata(
                document_id=doc_id,
                title=row[1] or "",
                doi=row[2],
                journal=row[4],  # publication column
                volume=None,
                issue=None,
                pages=None,
                year=row[5],
                publication_date=str(row[6]) if row[6] else None,
                pmid=row[7],
                authors=authors
            )

        return metadata_map

    def _fetch_single_metadata(
        self,
        document_id: int
    ) -> Optional[DocumentMetadata]:
        """
        Fetch metadata for a single document.

        Args:
            document_id: Document ID

        Returns:
            DocumentMetadata or None
        """
        result = self._fetch_document_metadata([document_id])
        return result.get(document_id)

    def _replace_citations(
        self,
        text: str,
        id_to_number: Dict[int, int]
    ) -> str:
        """
        Replace citation markers with formatted references.

        For Vancouver style: replaces with [N]
        For other styles: replaces with inline citation format

        Handles adjacent citations by combining them.

        Args:
            text: Document text with citation markers
            id_to_number: Mapping of document_id to reference number

        Returns:
            Text with citations replaced
        """
        if self._formatter.style == CitationStyle.VANCOUVER:
            # Find and combine adjacent citations
            groups = self._parser.find_adjacent_citations(text)

            # Process groups in reverse order to preserve positions
            for group in reversed(groups):
                if len(group) == 1:
                    # Single citation
                    citation = group[0]
                    number = id_to_number.get(citation.document_id, 0)
                    replacement = f"[{number}]"
                else:
                    # Multiple adjacent citations - combine them
                    replacement = self._parser.format_citation_group(
                        group, id_to_number, COMBINE_SEQUENTIAL_CITATIONS
                    )

                # Calculate the span of text to replace
                start = group[0].position
                end = group[-1].position + len(group[-1].text)

                text = text[:start] + replacement + text[end:]

            return text
        else:
            # Author-date styles - replace individually
            return self._parser.replace_all_citations_with_numbers(text, id_to_number)

    def generate_label(self, document_id: int) -> str:
        """
        Generate a citation label for a document.

        Args:
            document_id: Document database ID

        Returns:
            Label like "Smith2023"
        """
        metadata = self._fetch_single_metadata(document_id)
        if metadata:
            return metadata.generate_label()
        return f"Doc{document_id}"

    def create_citation_marker(self, document_id: int) -> str:
        """
        Create a complete citation marker for a document.

        Args:
            document_id: Document database ID

        Returns:
            Citation marker like [@id:12345:Smith2023]
        """
        label = self.generate_label(document_id)
        return self._parser.create_citation_marker(document_id, label)

    def validate_citations(
        self,
        text: str
    ) -> List[Dict[str, Any]]:
        """
        Validate all citations in text.

        Checks that:
        - All cited documents exist in the database
        - Citation format is correct

        Args:
            text: Document text with citation markers

        Returns:
            List of validation issues (empty if all valid)
        """
        issues = []
        citations = self._parser.parse_citations(text)

        if not citations:
            return issues

        # Get all document IDs
        doc_ids = list(set(c.document_id for c in citations))

        # Check which exist
        metadata_map = self._fetch_document_metadata(doc_ids)

        for citation in citations:
            if citation.document_id not in metadata_map:
                issues.append({
                    'type': 'missing_document',
                    'document_id': citation.document_id,
                    'position': citation.position,
                    'text': citation.text,
                    'message': f"Document {citation.document_id} not found in database"
                })

        return issues
