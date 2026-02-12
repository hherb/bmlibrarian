"""
Data models for PDF document structure and sections.
"""

from dataclasses import dataclass, field
from typing import List, Optional
from enum import Enum


class SectionType(Enum):
    """Standard sections in biomedical publications."""
    TITLE = "title"
    ABSTRACT = "abstract"
    INTRODUCTION = "introduction"
    BACKGROUND = "background"
    METHODS = "methods"
    MATERIALS_AND_METHODS = "materials_and_methods"
    RESULTS = "results"
    DISCUSSION = "discussion"
    CONCLUSION = "conclusion"
    CONCLUSIONS = "conclusions"
    ACKNOWLEDGMENTS = "acknowledgments"
    REFERENCES = "references"
    SUPPLEMENTARY = "supplementary"
    APPENDIX = "appendix"
    FUNDING = "funding"
    CONFLICTS = "conflicts"
    DATA_AVAILABILITY = "data_availability"
    AUTHOR_CONTRIBUTIONS = "author_contributions"
    UNKNOWN = "unknown"


@dataclass
class TextBlock:
    """A block of text extracted from PDF with layout information."""
    text: str
    page_num: int
    font_size: float
    font_name: str
    is_bold: bool
    is_italic: bool
    x: float  # X coordinate
    y: float  # Y coordinate
    width: float
    height: float

    def __str__(self) -> str:
        return f"TextBlock(page={self.page_num}, font={self.font_size:.1f}, text='{self.text[:50]}...')"


@dataclass
class Section:
    """A section of a biomedical publication."""
    section_type: SectionType
    title: str
    content: str
    page_start: int
    page_end: int
    confidence: float = 1.0  # Confidence in section detection (0-1)
    subsections: List['Section'] = field(default_factory=list)

    def to_markdown(self) -> str:
        """Convert section to markdown format."""
        level = "#" if self.section_type == SectionType.TITLE else "##"
        md = f"{level} {self.title}\n\n{self.content}\n"

        # Add subsections if present
        for subsection in self.subsections:
            md += f"\n### {subsection.title}\n\n{subsection.content}\n"

        return md

    def __str__(self) -> str:
        return f"Section({self.section_type.value}, pages={self.page_start}-{self.page_end}, len={len(self.content)})"


@dataclass
class Document:
    """A parsed biomedical publication document."""
    file_path: str
    title: Optional[str] = None
    authors: List[str] = field(default_factory=list)
    sections: List[Section] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def get_section(self, section_type: SectionType) -> Optional[Section]:
        """Get a specific section by type."""
        for section in self.sections:
            if section.section_type == section_type:
                return section
        return None

    def to_markdown(self) -> str:
        """Convert entire document to markdown format."""
        md_parts = []

        # Add title if present
        if self.title:
            md_parts.append(f"# {self.title}\n")

        # Add authors if present
        if self.authors:
            md_parts.append(f"**Authors:** {', '.join(self.authors)}\n")

        # Add sections with separators
        for section in self.sections:
            md_parts.append("\n---\n")
            md_parts.append(f"**{section.title.upper()}**")
            md_parts.append("\n---\n\n")
            md_parts.append(section.to_markdown())

        return '\n'.join(md_parts)

    def __str__(self) -> str:
        return f"Document({self.file_path}, sections={len(self.sections)})"
