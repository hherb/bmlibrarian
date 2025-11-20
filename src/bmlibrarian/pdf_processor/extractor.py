"""
PDF text extraction with layout and formatting information.
"""

import fitz  # PyMuPDF
from typing import List, Dict, Optional
from bmlibrarian.pdf_processor.models import TextBlock


class PDFExtractor:
    """Extract text from PDF files with layout and formatting information."""

    def __init__(self, pdf_path: str):
        """
        Initialize PDF extractor.

        Args:
            pdf_path: Path to the PDF file
        """
        self.pdf_path = pdf_path
        self.doc = fitz.open(pdf_path)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self):
        """Close the PDF document."""
        if self.doc:
            self.doc.close()

    def extract_text_blocks(self) -> List[TextBlock]:
        """
        Extract text blocks with layout information from all pages.

        Returns:
            List of TextBlock objects with text and formatting info
        """
        blocks = []

        for page_num in range(len(self.doc)):
            page = self.doc[page_num]
            page_blocks = self._extract_page_blocks(page, page_num)
            blocks.extend(page_blocks)

        return blocks

    def _extract_page_blocks(self, page, page_num: int) -> List[TextBlock]:
        """
        Extract text blocks from a single page.

        Args:
            page: PyMuPDF page object
            page_num: Page number (0-indexed)

        Returns:
            List of TextBlock objects from this page
        """
        blocks = []

        # Get text blocks with formatting
        text_dict = page.get_text("dict")

        for block in text_dict.get("blocks", []):
            # Skip image blocks
            if block.get("type") != 0:
                continue

            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = span.get("text", "").strip()
                    if not text:
                        continue

                    # Extract formatting information
                    font_size = span.get("size", 12.0)
                    font_name = span.get("font", "")
                    flags = span.get("flags", 0)

                    # Determine bold and italic from flags
                    # Flags: bit 0 = superscript, bit 1 = italic, bit 2 = serifed, bit 3 = monospaced, bit 4 = bold
                    is_bold = bool(flags & 2**4)
                    is_italic = bool(flags & 2**1)

                    # Get bounding box
                    bbox = span.get("bbox", (0, 0, 0, 0))
                    x, y, x1, y1 = bbox
                    width = x1 - x
                    height = y1 - y

                    block = TextBlock(
                        text=text,
                        page_num=page_num,
                        font_size=font_size,
                        font_name=font_name,
                        is_bold=is_bold,
                        is_italic=is_italic,
                        x=x,
                        y=y,
                        width=width,
                        height=height
                    )
                    blocks.append(block)

        return blocks

    def extract_metadata(self) -> Dict:
        """
        Extract PDF metadata.

        Returns:
            Dictionary with metadata (title, author, subject, etc.)
        """
        metadata = self.doc.metadata

        return {
            'title': metadata.get('title', ''),
            'author': metadata.get('author', ''),
            'subject': metadata.get('subject', ''),
            'keywords': metadata.get('keywords', ''),
            'creator': metadata.get('creator', ''),
            'producer': metadata.get('producer', ''),
            'creation_date': metadata.get('creationDate', ''),
            'modification_date': metadata.get('modDate', ''),
            'num_pages': len(self.doc),
        }

    def extract_raw_text(self) -> str:
        """
        Extract all text from the PDF as a single string.

        Returns:
            Combined text from all pages
        """
        text_parts = []
        for page_num in range(len(self.doc)):
            page = self.doc[page_num]
            text_parts.append(page.get_text())

        return '\n\n'.join(text_parts)

    def get_page_count(self) -> int:
        """Get the total number of pages."""
        return len(self.doc)
