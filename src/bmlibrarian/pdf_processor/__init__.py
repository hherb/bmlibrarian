"""
PDF Processor Module for Biomedical Publications

This module provides tools for extracting and segmenting biomedical publications
into their standard sections (abstract, introduction, methods, results, discussion, etc.)
using advanced NLP techniques and PDF layout analysis.
"""

from bmlibrarian.pdf_processor.models import Section, Document, SectionType, TextBlock
from bmlibrarian.pdf_processor.extractor import PDFExtractor
from bmlibrarian.pdf_processor.segmenter import SectionSegmenter

__all__ = [
    'Section',
    'Document',
    'SectionType',
    'TextBlock',
    'PDFExtractor',
    'SectionSegmenter',
]
