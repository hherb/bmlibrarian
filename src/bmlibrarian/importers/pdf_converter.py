"""
PDF Converter Abstraction for BMLibrarian.

Pluggable PDF to text conversion, prioritizing completeness of information
over formatting aesthetics.

This module is a re-export shim: the implementation lives in
``bmlib.fulltext.pdf_converter``, which was ported from this file. The
extracted ``text`` is unchanged; upstream adds a failed result for a
password-protected PDF (previously a success with no text), the text of each
page that yielded any (``ConversionResult.page_texts``; pages without text are
omitted, so it is not indexable by page number), a corroborated
``ConversionResult.title``, line-level ``extract_blocks()`` (``TextBlock``s
with font and position metadata; raises on encrypted or corrupt files where
``convert()`` returns a failed result) and ``render_html()``.

Example usage:
    from bmlibrarian.importers.pdf_converter import get_converter, ConversionResult

    converter = get_converter("pymupdf")
    result = converter.convert(Path("/path/to/paper.pdf"))

    if result.success and result.is_complete:
        print(f"Converted {result.page_count} pages, {result.char_count} characters")
        print(result.text)
"""

from bmlib.fulltext.pdf_converter import (
    CONVERTER_PYMUPDF,
    DEFAULT_CONVERTER,
    ConversionResult,
    LayoutExtractor,
    PDFConverter,
    PyMuPDFConverter,
    get_converter,
    list_converters,
    render_html,
)

__all__ = [
    "CONVERTER_PYMUPDF",
    "DEFAULT_CONVERTER",
    "ConversionResult",
    "LayoutExtractor",
    "PDFConverter",
    "PyMuPDFConverter",
    "get_converter",
    "list_converters",
    "render_html",
]
