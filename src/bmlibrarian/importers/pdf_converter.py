"""
PDF Converter Abstraction for BMLibrarian.

Provides a pluggable interface for PDF to text conversion, prioritizing
completeness of information over formatting aesthetics.

Example usage:
    from bmlibrarian.importers.pdf_converter import get_converter, ConversionResult

    converter = get_converter("pymupdf")
    result = converter.convert(Path("/path/to/paper.pdf"))

    if result.success and result.is_complete:
        print(f"Converted {result.page_count} pages, {result.char_count} characters")
        print(result.text)
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)

# Supported converter names
CONVERTER_PYMUPDF = "pymupdf"
DEFAULT_CONVERTER = CONVERTER_PYMUPDF


@dataclass
class ConversionResult:
    """
    Result of PDF to text conversion.

    Provides a stable interface for all PDF converters, including
    validation methods to ensure conversion completeness.
    """

    success: bool
    text: str
    format: str  # 'plaintext' or 'markdown'
    page_count: int
    converted_pages: int
    char_count: int
    warnings: List[str] = field(default_factory=list)
    converter_name: str = ""
    converter_version: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    error_message: Optional[str] = None

    @property
    def is_complete(self) -> bool:
        """Check if all pages were converted successfully."""
        return (
            self.success
            and self.page_count == self.converted_pages
            and self.char_count > 0
        )

    @property
    def completion_ratio(self) -> float:
        """Return the ratio of converted pages to total pages."""
        if self.page_count == 0:
            return 0.0
        return self.converted_pages / self.page_count

    def __str__(self) -> str:
        """Return human-readable summary of conversion result."""
        status = "SUCCESS" if self.success else "FAILED"
        completeness = "complete" if self.is_complete else "incomplete"
        return (
            f"ConversionResult({status}, {completeness}, "
            f"{self.converted_pages}/{self.page_count} pages, "
            f"{self.char_count} chars, converter={self.converter_name})"
        )


class PDFConverter(ABC):
    """
    Abstract base class for PDF converters.

    All PDF converters must implement this interface to ensure
    consistent behavior across different conversion backends.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the converter name identifier."""
        ...

    @property
    @abstractmethod
    def version(self) -> str:
        """Return the converter version string."""
        ...

    @abstractmethod
    def convert(self, pdf_path: Path) -> ConversionResult:
        """
        Convert PDF to text.

        Args:
            pdf_path: Path to the PDF file to convert.

        Returns:
            ConversionResult with text and metadata.

        Raises:
            FileNotFoundError: If the PDF file does not exist.
            ValueError: If the file is not a valid PDF.
        """
        ...

    def validate_pdf_path(self, pdf_path: Path) -> None:
        """
        Validate that the PDF path exists and is a file.

        Args:
            pdf_path: Path to validate.

        Raises:
            FileNotFoundError: If the path does not exist.
            ValueError: If the path is not a file or not a PDF.
        """
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")
        if not pdf_path.is_file():
            raise ValueError(f"Path is not a file: {pdf_path}")
        if pdf_path.suffix.lower() != ".pdf":
            raise ValueError(f"File is not a PDF: {pdf_path}")


class PyMuPDFConverter(PDFConverter):
    """
    PDF converter using PyMuPDF (fitz).

    Prioritizes reliability and completeness over formatting.
    This is the recommended converter for production use.
    """

    def __init__(self) -> None:
        """Initialize the PyMuPDF converter."""
        try:
            import fitz
            self._fitz = fitz
        except ImportError as e:
            raise ImportError(
                "PyMuPDF (fitz) is required for PDF conversion. "
                "Install with: pip install pymupdf"
            ) from e

    @property
    def name(self) -> str:
        """Return the converter name."""
        return CONVERTER_PYMUPDF

    @property
    def version(self) -> str:
        """Return the PyMuPDF version."""
        return self._fitz.version[0]

    def convert(self, pdf_path: Path) -> ConversionResult:
        """
        Convert PDF to plaintext using PyMuPDF.

        Extracts text from all pages, preserving reading order.
        Prioritizes completeness - all text is extracted even if
        formatting is imperfect.

        Args:
            pdf_path: Path to the PDF file.

        Returns:
            ConversionResult with extracted text and metadata.
        """
        self.validate_pdf_path(pdf_path)

        warnings: List[str] = []
        text_parts: List[str] = []
        converted_pages = 0
        page_count = 0
        metadata: Dict[str, Any] = {}

        try:
            doc = self._fitz.open(str(pdf_path))
            page_count = len(doc)

            # Extract metadata
            try:
                pdf_metadata = doc.metadata
                metadata = {
                    "title": pdf_metadata.get("title", ""),
                    "author": pdf_metadata.get("author", ""),
                    "subject": pdf_metadata.get("subject", ""),
                    "keywords": pdf_metadata.get("keywords", ""),
                    "creator": pdf_metadata.get("creator", ""),
                    "producer": pdf_metadata.get("producer", ""),
                    "creation_date": pdf_metadata.get("creationDate", ""),
                    "modification_date": pdf_metadata.get("modDate", ""),
                }
            except Exception as e:
                warnings.append(f"Failed to extract metadata: {e}")
                logger.warning(f"Metadata extraction failed for {pdf_path}: {e}")

            # Extract text from each page
            for page_num in range(page_count):
                try:
                    page = doc[page_num]
                    page_text = page.get_text()

                    if page_text.strip():
                        text_parts.append(page_text)
                        converted_pages += 1
                    else:
                        # Page exists but has no extractable text (image-only?)
                        warnings.append(f"Page {page_num + 1}: No extractable text")
                        converted_pages += 1  # Still count as converted (page was processed)

                except Exception as e:
                    warnings.append(f"Page {page_num + 1}: Extraction failed - {e}")
                    logger.warning(f"Page {page_num + 1} extraction failed: {e}")

            doc.close()

            # Combine text with double newlines between pages
            full_text = "\n\n".join(text_parts)

            return ConversionResult(
                success=True,
                text=full_text,
                format="plaintext",
                page_count=page_count,
                converted_pages=converted_pages,
                char_count=len(full_text),
                warnings=warnings,
                converter_name=self.name,
                converter_version=self.version,
                metadata=metadata,
            )

        except self._fitz.FileDataError as e:
            error_msg = f"Invalid or corrupted PDF: {e}"
            logger.error(f"PDF conversion failed for {pdf_path}: {error_msg}")
            return ConversionResult(
                success=False,
                text="",
                format="plaintext",
                page_count=page_count,
                converted_pages=0,
                char_count=0,
                warnings=warnings,
                converter_name=self.name,
                converter_version=self.version,
                error_message=error_msg,
            )

        except Exception as e:
            error_msg = f"PDF conversion failed: {e}"
            logger.error(f"PDF conversion failed for {pdf_path}: {error_msg}")
            return ConversionResult(
                success=False,
                text="",
                format="plaintext",
                page_count=page_count,
                converted_pages=converted_pages,
                char_count=0,
                warnings=warnings,
                converter_name=self.name,
                converter_version=self.version,
                error_message=error_msg,
            )


# Registry of available converters
_CONVERTER_REGISTRY: Dict[str, type] = {
    CONVERTER_PYMUPDF: PyMuPDFConverter,
    # Future converters can be added here:
    # "pymupdf4llm": PyMuPDF4LLMConverter,  # When stable
    # "docling": DoclingConverter,
    # "marker": MarkerConverter,
}


def get_converter(name: str = DEFAULT_CONVERTER) -> PDFConverter:
    """
    Factory function to get a PDF converter by name.

    Args:
        name: Converter name. Currently supported: "pymupdf".

    Returns:
        Initialized PDFConverter instance.

    Raises:
        ValueError: If the converter name is not recognized.
        ImportError: If the converter's dependencies are not installed.
    """
    if name not in _CONVERTER_REGISTRY:
        available = ", ".join(_CONVERTER_REGISTRY.keys())
        raise ValueError(
            f"Unknown converter: '{name}'. Available converters: {available}"
        )

    converter_class = _CONVERTER_REGISTRY[name]
    return converter_class()


def list_converters() -> List[str]:
    """
    List all available converter names.

    Returns:
        List of converter name strings.
    """
    return list(_CONVERTER_REGISTRY.keys())
