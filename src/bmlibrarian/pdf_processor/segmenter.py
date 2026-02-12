"""
Section segmentation for biomedical publications using NLP and heuristics.
"""

import re
from typing import List, Tuple, Optional, Dict, Pattern
from bmlibrarian.pdf_processor.models import TextBlock, Section, SectionType, Document


class SectionSegmenter:
    """Segment biomedical publications into standard sections."""

    # Common section headers and their variations
    SECTION_PATTERNS = {
        SectionType.ABSTRACT: [
            r'^abstract$',
            r'^summary$',
        ],
        SectionType.INTRODUCTION: [
            r'^introduction$',
            r'^background\s+and\s+introduction$',
        ],
        SectionType.BACKGROUND: [
            r'^background$',
            r'^literature\s+review$',
        ],
        SectionType.METHODS: [
            r'^methods$',
            r'^methodology$',
            r'^materials\s+and\s+methods$',
            r'^methods\s+and\s+materials$',
            r'^experimental\s+procedures?$',
            r'^experimental\s+methods$',
        ],
        SectionType.RESULTS: [
            r'^results$',
            r'^findings$',
            r'^results\s+and\s+discussion$',
        ],
        SectionType.DISCUSSION: [
            r'^discussion$',
            r'^discussion\s+and\s+conclusion$',
        ],
        SectionType.CONCLUSION: [
            r'^conclusion$',
            r'^conclusions$',
            r'^concluding\s+remarks$',
            r'^summary\s+and\s+conclusions?$',
        ],
        SectionType.ACKNOWLEDGMENTS: [
            r'^acknowledgments?$',
            r'^acknowledgements?$',
        ],
        SectionType.REFERENCES: [
            r'^references$',
            r'^bibliography$',
            r'^literature\s+cited$',
            r'^works\s+cited$',
        ],
        SectionType.SUPPLEMENTARY: [
            r'^supplementary\s+materials?$',
            r'^supplementary\s+information$',
            r'^supporting\s+information$',
            r'^appendices$',
        ],
        SectionType.FUNDING: [
            r'^funding$',
            r'^funding\s+sources?$',
            r'^financial\s+support$',
            r'^financial\s+disclosure$',
            r'^grant\s+support$',
            r'^funding\s+and\s+acknowledgments?$',
            r'^funding\s+and\s+acknowledgements?$',
            r'^funding\s+information$',
            r'^funding\s+statement$',
            r'^source\s+of\s+funding$',
            r'^sources?\s+of\s+support$',
        ],
        SectionType.CONFLICTS: [
            r'^conflicts?\s+of\s+interest$',
            r'^competing\s+interests?$',
            r'^disclosures?$',
            r'^declaration\s+of\s+interests?$',
            r'^financial\s+disclosures?$',
            r'^conflict\s+of\s+interest\s+statement$',
            r'^declaration\s+of\s+competing\s+interests?$',
            r'^potential\s+conflicts?\s+of\s+interest$',
        ],
        SectionType.DATA_AVAILABILITY: [
            r'^data\s+availability$',
            r'^data\s+sharing$',
            r'^data\s+access$',
            r'^availability\s+of\s+data$',
            r'^data\s+availability\s+statement$',
            r'^data\s+and\s+materials?\s+availability$',
            r'^code\s+and\s+data\s+availability$',
        ],
        SectionType.AUTHOR_CONTRIBUTIONS: [
            r'^author\s+contributions?$',
            r'^contributors?$',
            r'^credit\s+authorship$',
            r'^authorship\s+contributions?$',
            r'^authors?\s*\'\s*contributions?$',
        ],
    }

    def __init__(self, font_size_threshold: float = 1.2, min_heading_size: float = 10.0):
        """
        Initialize section segmenter.

        Args:
            font_size_threshold: Multiplier for detecting heading font sizes
            min_heading_size: Minimum font size to consider as heading
        """
        self.font_size_threshold = font_size_threshold
        self.min_heading_size = min_heading_size

        # Pre-compile regex patterns for better performance
        self.compiled_patterns: Dict[SectionType, List[Pattern]] = {
            section_type: [re.compile(pattern, re.IGNORECASE) for pattern in patterns]
            for section_type, patterns in self.SECTION_PATTERNS.items()
        }

    def segment_document(self, blocks: List[TextBlock], metadata: dict) -> Document:
        """
        Segment a document into sections based on text blocks.

        Args:
            blocks: List of text blocks extracted from PDF
            metadata: Document metadata

        Returns:
            Document object with identified sections

        Raises:
            TypeError: If blocks is not a list or metadata is not a dict
            ValueError: If blocks contains invalid TextBlock objects
        """
        # Validate inputs
        if not isinstance(blocks, list):
            raise TypeError(f"blocks must be a list, got {type(blocks).__name__}")

        if not isinstance(metadata, dict):
            raise TypeError(f"metadata must be a dict, got {type(metadata).__name__}")

        # Validate that all blocks are TextBlock instances
        for i, block in enumerate(blocks):
            if not isinstance(block, TextBlock):
                raise ValueError(f"blocks[{i}] must be a TextBlock instance, got {type(block).__name__}")

        # Calculate average font size for body text
        avg_font_size = self._calculate_avg_font_size(blocks)

        # Identify section boundaries
        section_markers = self._identify_section_markers(blocks, avg_font_size)

        # Extract sections
        sections = self._extract_sections(blocks, section_markers)

        # Create document
        doc = Document(
            file_path=metadata.get('file_path', ''),
            title=self._extract_title(blocks, metadata),
            sections=sections,
            metadata=metadata
        )

        return doc

    def _calculate_avg_font_size(self, blocks: List[TextBlock]) -> float:
        """
        Calculate the average font size for body text.

        Returns:
            Median font size, or 12.0 if no blocks or all have zero font size
        """
        if not blocks:
            return 12.0

        # Use median to avoid outliers from headings
        # Filter out zero or negative font sizes
        sizes = [block.font_size for block in blocks if block.font_size > 0]

        if not sizes:
            # If all blocks have zero font size, return default
            return 12.0

        sizes.sort()
        mid = len(sizes) // 2

        if len(sizes) % 2 == 0:
            return (sizes[mid - 1] + sizes[mid]) / 2
        else:
            return sizes[mid]

    def _identify_section_markers(
        self, blocks: List[TextBlock], avg_font_size: float
    ) -> List[Tuple[int, SectionType, str, float]]:
        """
        Identify potential section markers based on formatting and content.

        Returns:
            List of (block_index, section_type, title, confidence) tuples
        """
        markers = []

        for i, block in enumerate(blocks):
            # Check if this looks like a section header
            if not self._is_potential_header(block, avg_font_size):
                continue

            # Try to match against known section patterns
            section_type, confidence = self._match_section_type(block.text)

            if section_type != SectionType.UNKNOWN:
                markers.append((i, section_type, block.text, confidence))

        return markers

    def _is_potential_header(self, block: TextBlock, avg_font_size: float) -> bool:
        """
        Determine if a text block is likely a section header.

        Criteria:
        - Larger font size than body text
        - Bold formatting
        - Relatively short text
        - Not just numbers (for numbered sections)
        """
        # Font size check
        if block.font_size < self.min_heading_size:
            return False

        if block.font_size < avg_font_size * self.font_size_threshold:
            # If not significantly larger, must be bold
            if not block.is_bold:
                return False

        # Length check (headers are usually short)
        if len(block.text) > 100:
            return False

        # Should have some alphabetic characters
        if not any(c.isalpha() for c in block.text):
            return False

        return True

    def _match_section_type(self, text: str) -> Tuple[SectionType, float]:
        """
        Match text against known section patterns using pre-compiled regex.

        Returns:
            (section_type, confidence) tuple
        """
        # Normalize text for matching
        normalized = text.lower().strip()

        # Remove leading numbers and punctuation (e.g., "1. Introduction" -> "introduction")
        normalized = re.sub(r'^[\d\.\s\)\]]+', '', normalized)
        normalized = re.sub(r'[:\.\?!]+$', '', normalized)

        # Try exact matches first using pre-compiled patterns
        for section_type, compiled_patterns in self.compiled_patterns.items():
            for pattern in compiled_patterns:
                if pattern.match(normalized):
                    return (section_type, 1.0)

        # Try partial matches with lower confidence
        for section_type, patterns in self.SECTION_PATTERNS.items():
            for pattern in patterns:
                pattern_text = pattern.strip('^$')
                if pattern_text in normalized or normalized in pattern_text:
                    return (section_type, 0.7)

        return (SectionType.UNKNOWN, 0.0)

    def _extract_sections(
        self,
        blocks: List[TextBlock],
        markers: List[Tuple[int, SectionType, str, float]]
    ) -> List[Section]:
        """
        Extract section content between markers.

        Args:
            blocks: All text blocks
            markers: List of (block_index, section_type, title, confidence) tuples

        Returns:
            List of Section objects
        """
        if not markers:
            # If no markers found, return all content as unknown section
            content = '\n'.join(block.text for block in blocks)
            return [Section(
                section_type=SectionType.UNKNOWN,
                title="Full Text",
                content=content,
                page_start=blocks[0].page_num if blocks else 0,
                page_end=blocks[-1].page_num if blocks else 0,
                confidence=0.5
            )]

        sections = []

        for i, (start_idx, section_type, title, confidence) in enumerate(markers):
            # Determine end of this section
            if i + 1 < len(markers):
                end_idx = markers[i + 1][0]
            else:
                end_idx = len(blocks)

            # Extract content blocks for this section
            section_blocks = blocks[start_idx + 1:end_idx]

            if not section_blocks:
                continue

            # Combine text from blocks
            content_lines = []
            prev_y = None

            for block in section_blocks:
                # Add paragraph breaks based on vertical spacing
                if prev_y is not None and block.y - prev_y > block.height * 1.5:
                    content_lines.append('')  # Add blank line

                content_lines.append(block.text)
                prev_y = block.y + block.height

            content = '\n'.join(content_lines)

            # Create section
            section = Section(
                section_type=section_type,
                title=title,
                content=content,
                page_start=section_blocks[0].page_num,
                page_end=section_blocks[-1].page_num,
                confidence=confidence
            )
            sections.append(section)

        return sections

    def _extract_title(self, blocks: List[TextBlock], metadata: dict) -> Optional[str]:
        """
        Extract document title from blocks or metadata.

        Args:
            blocks: Text blocks from PDF
            metadata: PDF metadata

        Returns:
            Document title or None
        """
        # Try metadata first
        if metadata.get('title'):
            return metadata['title']

        # Try to find title from first page (usually largest font)
        if not blocks:
            return None

        # Get blocks from first page only
        first_page_blocks = [b for b in blocks if b.page_num == 0]

        if not first_page_blocks:
            return None

        # Find block with largest font size on first page
        title_block = max(first_page_blocks, key=lambda b: b.font_size)

        # Only use if significantly larger than average
        avg_size = self._calculate_avg_font_size(blocks)
        if title_block.font_size > avg_size * 1.5:
            return title_block.text

        return None
