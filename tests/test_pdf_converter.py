"""
Tests for PDF converter abstraction.

Tests the ConversionResult dataclass, PDFConverter abstract base,
and PyMuPDFConverter implementation.
"""

import pytest
from pathlib import Path

from bmlibrarian.importers.pdf_converter import (
    ConversionResult,
    PDFConverter,
    PyMuPDFConverter,
    get_converter,
    list_converters,
    CONVERTER_PYMUPDF,
    DEFAULT_CONVERTER,
)


class TestConversionResult:
    """Test ConversionResult dataclass."""

    def test_successful_result(self) -> None:
        """Test creating a successful conversion result."""
        result = ConversionResult(
            success=True,
            text="Sample extracted text",
            format="plaintext",
            page_count=5,
            converted_pages=5,
            char_count=21,
            converter_name="pymupdf",
            converter_version="1.0.0",
        )

        assert result.success is True
        assert result.text == "Sample extracted text"
        assert result.format == "plaintext"
        assert result.page_count == 5
        assert result.converted_pages == 5
        assert result.char_count == 21
        assert result.is_complete is True
        assert result.completion_ratio == 1.0

    def test_incomplete_result(self) -> None:
        """Test incomplete conversion (not all pages converted)."""
        result = ConversionResult(
            success=True,
            text="Partial text",
            format="plaintext",
            page_count=10,
            converted_pages=7,
            char_count=12,
            converter_name="pymupdf",
            converter_version="1.0.0",
        )

        assert result.success is True
        assert result.is_complete is False
        assert result.completion_ratio == 0.7

    def test_failed_result(self) -> None:
        """Test failed conversion result."""
        result = ConversionResult(
            success=False,
            text="",
            format="plaintext",
            page_count=5,
            converted_pages=0,
            char_count=0,
            converter_name="pymupdf",
            converter_version="1.0.0",
            error_message="Invalid PDF",
        )

        assert result.success is False
        assert result.is_complete is False
        assert result.error_message == "Invalid PDF"
        assert result.completion_ratio == 0.0

    def test_zero_pages(self) -> None:
        """Test result with zero pages (edge case)."""
        result = ConversionResult(
            success=True,
            text="",
            format="plaintext",
            page_count=0,
            converted_pages=0,
            char_count=0,
            converter_name="pymupdf",
            converter_version="1.0.0",
        )

        assert result.completion_ratio == 0.0
        assert result.is_complete is False  # No chars

    def test_str_representation(self) -> None:
        """Test string representation."""
        result = ConversionResult(
            success=True,
            text="Test",
            format="plaintext",
            page_count=5,
            converted_pages=5,
            char_count=100,
            converter_name="pymupdf",
            converter_version="1.0.0",
        )

        str_repr = str(result)
        assert "SUCCESS" in str_repr
        assert "complete" in str_repr
        assert "5/5" in str_repr

    def test_warnings_list(self) -> None:
        """Test warnings are properly stored."""
        result = ConversionResult(
            success=True,
            text="Test",
            format="plaintext",
            page_count=5,
            converted_pages=5,
            char_count=4,
            warnings=["Warning 1", "Warning 2"],
            converter_name="pymupdf",
            converter_version="1.0.0",
        )

        assert len(result.warnings) == 2
        assert "Warning 1" in result.warnings

    def test_metadata_dict(self) -> None:
        """Test metadata dictionary storage."""
        metadata = {"title": "Test Paper", "author": "John Doe"}
        result = ConversionResult(
            success=True,
            text="Test",
            format="plaintext",
            page_count=1,
            converted_pages=1,
            char_count=4,
            metadata=metadata,
            converter_name="pymupdf",
            converter_version="1.0.0",
        )

        assert result.metadata["title"] == "Test Paper"
        assert result.metadata["author"] == "John Doe"


class TestPDFConverterBase:
    """Test PDFConverter abstract base class."""

    def test_validate_pdf_path_not_exists(self, tmp_path: Path) -> None:
        """Test validation raises error for non-existent file."""
        converter = PyMuPDFConverter()
        fake_path = tmp_path / "nonexistent.pdf"

        with pytest.raises(FileNotFoundError, match="PDF file not found"):
            converter.validate_pdf_path(fake_path)

    def test_validate_pdf_path_is_directory(self, tmp_path: Path) -> None:
        """Test validation raises error for directory."""
        converter = PyMuPDFConverter()

        with pytest.raises(ValueError, match="Path is not a file"):
            converter.validate_pdf_path(tmp_path)

    def test_validate_pdf_path_not_pdf(self, tmp_path: Path) -> None:
        """Test validation raises error for non-PDF file."""
        converter = PyMuPDFConverter()
        txt_file = tmp_path / "test.txt"
        txt_file.write_text("Not a PDF")

        with pytest.raises(ValueError, match="File is not a PDF"):
            converter.validate_pdf_path(txt_file)

    def test_validate_pdf_path_success(self, tmp_path: Path) -> None:
        """Test validation succeeds for valid PDF path."""
        converter = PyMuPDFConverter()
        pdf_file = tmp_path / "test.pdf"
        # Create minimal PDF-like file (validation only checks extension)
        pdf_file.write_bytes(b"%PDF-1.4 minimal content")

        # Should not raise
        converter.validate_pdf_path(pdf_file)


class TestPyMuPDFConverter:
    """Test PyMuPDFConverter implementation."""

    def test_name_property(self) -> None:
        """Test name property returns correct value."""
        converter = PyMuPDFConverter()
        assert converter.name == CONVERTER_PYMUPDF
        assert converter.name == "pymupdf"

    def test_version_property(self) -> None:
        """Test version property returns a version string."""
        converter = PyMuPDFConverter()
        version = converter.version
        assert isinstance(version, str)
        assert len(version) > 0

    def test_convert_nonexistent_file(self, tmp_path: Path) -> None:
        """Test converting non-existent file raises error."""
        converter = PyMuPDFConverter()
        fake_path = tmp_path / "nonexistent.pdf"

        with pytest.raises(FileNotFoundError):
            converter.convert(fake_path)

    def test_convert_invalid_pdf(self, tmp_path: Path) -> None:
        """Test converting invalid PDF returns error result."""
        # Create a file that's not a valid PDF
        pdf_file = tmp_path / "invalid.pdf"
        pdf_file.write_bytes(b"not a pdf content")

        converter = PyMuPDFConverter()

        # PyMuPDF will fail to open this invalid content
        result = converter.convert(pdf_file)

        # Should either fail or succeed with warnings depending on PyMuPDF version
        # The important thing is it doesn't crash
        if not result.success:
            assert result.error_message is not None


class TestConverterFactory:
    """Test get_converter factory function."""

    def test_get_default_converter(self) -> None:
        """Test getting default converter."""
        converter = get_converter()
        assert isinstance(converter, PyMuPDFConverter)

    def test_get_pymupdf_converter(self) -> None:
        """Test getting PyMuPDF converter by name."""
        converter = get_converter("pymupdf")
        assert isinstance(converter, PyMuPDFConverter)

    def test_get_unknown_converter(self) -> None:
        """Test getting unknown converter raises error."""
        with pytest.raises(ValueError, match="Unknown converter"):
            get_converter("unknown_converter")

    def test_default_converter_constant(self) -> None:
        """Test DEFAULT_CONVERTER constant."""
        assert DEFAULT_CONVERTER == "pymupdf"


class TestListConverters:
    """Test list_converters function."""

    def test_list_converters(self) -> None:
        """Test listing available converters."""
        converters = list_converters()

        assert isinstance(converters, list)
        assert "pymupdf" in converters
        assert len(converters) >= 1

    def test_list_converters_returns_strings(self) -> None:
        """Test that list_converters returns strings."""
        converters = list_converters()
        assert all(isinstance(c, str) for c in converters)
