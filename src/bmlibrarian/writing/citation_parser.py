"""
Citation parser for extracting and manipulating citation markers.

Parses the [@id:12345:Smith2023] format from document text and provides
utilities for citation manipulation.
"""

import re
import logging
from typing import List, Set, Dict, Tuple, Optional
from dataclasses import dataclass

from .constants import CITATION_PATTERN, CITATION_ID_PATTERN
from .models import Citation

logger = logging.getLogger(__name__)


class CitationParser:
    """
    Parser for extracting and manipulating citation markers in text.

    The citation format is: [@id:12345:Smith2023]
    - @id: prefix indicating document ID follows
    - 12345: the actual document ID (integer)
    - Smith2023: human-readable label (author + year)
    """

    def __init__(self) -> None:
        """Initialize the citation parser."""
        self._pattern = CITATION_PATTERN
        self._id_pattern = CITATION_ID_PATTERN

    def parse_citations(self, text: str) -> List[Citation]:
        """
        Extract all citations from the text.

        Args:
            text: Document text with citation markers

        Returns:
            List of Citation objects in order of appearance
        """
        citations = []

        for match in self._pattern.finditer(text):
            try:
                doc_id = int(match.group(1))
                label = match.group(2)
                position = match.start()
                full_text = match.group(0)

                citation = Citation(
                    document_id=doc_id,
                    label=label,
                    position=position,
                    text=full_text
                )
                citations.append(citation)

            except (ValueError, IndexError) as e:
                logger.warning(f"Failed to parse citation at position {match.start()}: {e}")
                continue

        return citations

    def get_unique_document_ids(self, text: str) -> List[int]:
        """
        Get unique document IDs from citations in order of first appearance.

        Args:
            text: Document text with citation markers

        Returns:
            List of unique document IDs in order of first appearance
        """
        seen: Set[int] = set()
        ordered_ids: List[int] = []

        for match in self._pattern.finditer(text):
            try:
                doc_id = int(match.group(1))
                if doc_id not in seen:
                    seen.add(doc_id)
                    ordered_ids.append(doc_id)
            except (ValueError, IndexError):
                continue

        return ordered_ids

    def count_citations(self, text: str) -> int:
        """
        Count total number of citations in text.

        Args:
            text: Document text with citation markers

        Returns:
            Total citation count
        """
        return len(self._pattern.findall(text))

    def count_unique_citations(self, text: str) -> int:
        """
        Count unique cited documents in text.

        Args:
            text: Document text with citation markers

        Returns:
            Count of unique document IDs
        """
        return len(self.get_unique_document_ids(text))

    def get_citation_positions(self, text: str) -> Dict[int, List[int]]:
        """
        Get all positions where each document is cited.

        Args:
            text: Document text with citation markers

        Returns:
            Dictionary mapping document_id to list of character positions
        """
        positions: Dict[int, List[int]] = {}

        for match in self._pattern.finditer(text):
            try:
                doc_id = int(match.group(1))
                pos = match.start()

                if doc_id not in positions:
                    positions[doc_id] = []
                positions[doc_id].append(pos)

            except (ValueError, IndexError):
                continue

        return positions

    def create_citation_marker(
        self,
        document_id: int,
        label: str
    ) -> str:
        """
        Create a citation marker string.

        Args:
            document_id: Database document ID
            label: Human-readable label (e.g., "Smith2023")

        Returns:
            Formatted citation marker: [@id:12345:Smith2023]
        """
        return f"[@id:{document_id}:{label}]"

    def replace_citation_with_number(
        self,
        text: str,
        document_id: int,
        number: int
    ) -> str:
        """
        Replace all citations of a document with a numbered reference.

        Args:
            text: Document text with citation markers
            document_id: Document ID to replace
            number: Reference number to use

        Returns:
            Text with citations replaced
        """
        # Pattern to match this specific document's citation
        specific_pattern = re.compile(rf'\[@id:{document_id}:[^\]]+\]')
        return specific_pattern.sub(f'[{number}]', text)

    def replace_all_citations_with_numbers(
        self,
        text: str,
        id_to_number: Dict[int, int]
    ) -> str:
        """
        Replace all citations with their reference numbers.

        Args:
            text: Document text with citation markers
            id_to_number: Mapping of document_id to reference number

        Returns:
            Text with all citations replaced with numbers
        """
        def replace_match(match: re.Match) -> str:
            try:
                doc_id = int(match.group(1))
                if doc_id in id_to_number:
                    return f'[{id_to_number[doc_id]}]'
                else:
                    # Keep original if not in mapping
                    return match.group(0)
            except (ValueError, IndexError):
                return match.group(0)

        return self._pattern.sub(replace_match, text)

    def get_citations_in_range(
        self,
        text: str,
        start: int,
        end: int
    ) -> List[Citation]:
        """
        Get citations within a character range.

        Args:
            text: Document text with citation markers
            start: Start character position
            end: End character position

        Returns:
            List of citations within the range
        """
        all_citations = self.parse_citations(text)
        return [c for c in all_citations if start <= c.position < end]

    def find_adjacent_citations(self, text: str) -> List[List[Citation]]:
        """
        Find groups of adjacent citations (for combining like [1,2,3]).

        Adjacent citations are those separated only by whitespace or commas.

        Args:
            text: Document text with citation markers

        Returns:
            List of citation groups (each group is a list of adjacent citations)
        """
        citations = self.parse_citations(text)
        if not citations:
            return []

        groups: List[List[Citation]] = []
        current_group: List[Citation] = [citations[0]]

        for i in range(1, len(citations)):
            prev = citations[i - 1]
            curr = citations[i]

            # Calculate gap between citations
            prev_end = prev.position + len(prev.text)
            gap = text[prev_end:curr.position]

            # Check if only whitespace/comma between them
            if re.match(r'^[\s,]*$', gap):
                current_group.append(curr)
            else:
                if current_group:
                    groups.append(current_group)
                current_group = [curr]

        # Don't forget the last group
        if current_group:
            groups.append(current_group)

        return groups

    def format_citation_group(
        self,
        citations: List[Citation],
        id_to_number: Dict[int, int],
        combine_sequential: bool = True
    ) -> str:
        """
        Format a group of citations as a combined reference.

        Args:
            citations: List of adjacent citations
            id_to_number: Mapping of document_id to reference number
            combine_sequential: Whether to combine sequential numbers (e.g., 1-3)

        Returns:
            Formatted reference like "[1,2,3]" or "[1-3]"
        """
        if not citations:
            return ""

        numbers = sorted(set(
            id_to_number.get(c.document_id, 0)
            for c in citations
            if c.document_id in id_to_number
        ))

        if not numbers:
            return ""

        if not combine_sequential or len(numbers) <= 2:
            return f"[{','.join(str(n) for n in numbers)}]"

        # Try to combine sequential numbers
        ranges: List[str] = []
        start = numbers[0]
        end = numbers[0]

        for n in numbers[1:]:
            if n == end + 1:
                end = n
            else:
                if end > start + 1:
                    ranges.append(f"{start}-{end}")
                elif end > start:
                    ranges.append(f"{start},{end}")
                else:
                    ranges.append(str(start))
                start = end = n

        # Handle the last range
        if end > start + 1:
            ranges.append(f"{start}-{end}")
        elif end > start:
            ranges.append(f"{start},{end}")
        else:
            ranges.append(str(start))

        return f"[{','.join(ranges)}]"

    def validate_citation(self, citation_text: str) -> Tuple[bool, Optional[str]]:
        """
        Validate a citation marker string.

        Args:
            citation_text: Citation marker to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        match = self._pattern.match(citation_text)
        if not match:
            return False, "Invalid citation format. Expected: [@id:NUMBER:LABEL]"

        try:
            doc_id = int(match.group(1))
            if doc_id <= 0:
                return False, "Document ID must be a positive integer"
        except ValueError:
            return False, "Document ID must be an integer"

        label = match.group(2)
        if not label or len(label) > 100:
            return False, "Label must be 1-100 characters"

        return True, None

    def extract_label_from_citation(self, citation_text: str) -> Optional[str]:
        """
        Extract the label from a citation marker.

        Args:
            citation_text: Citation marker string

        Returns:
            Label string or None if invalid
        """
        match = self._pattern.match(citation_text)
        if match:
            return match.group(2)
        return None

    def extract_document_id_from_citation(self, citation_text: str) -> Optional[int]:
        """
        Extract the document ID from a citation marker.

        Args:
            citation_text: Citation marker string

        Returns:
            Document ID or None if invalid
        """
        match = self._pattern.match(citation_text)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                pass
        return None
