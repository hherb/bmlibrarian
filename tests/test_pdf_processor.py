"""
Comprehensive unit tests for the PDF Processor library.

Tests cover:
- PDFExtractor error handling and edge cases
- SectionSegmenter validation and segmentation logic
- TextBlock and Section data models
- Font size calculations
- Section type matching
- Error recovery
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
from bmlibrarian.pdf_processor import PDFExtractor, SectionSegmenter
from bmlibrarian.pdf_processor.models import TextBlock, Section, SectionType, Document


class TestPDFExtractor:
    """Test PDFExtractor class."""

    def test_invalid_pdf_path_raises_error(self):
        """Test that opening a non-existent PDF raises an error."""
        with pytest.raises((FileNotFoundError, ValueError), match="(PDF file not found|Failed to open PDF)"):
            PDFExtractor("nonexistent_file.pdf")

    def test_corrupted_pdf_raises_error(self):
        """Test that opening a corrupted PDF raises ValueError."""
        with patch('fitz.open', side_effect=RuntimeError("Corrupted PDF")):
            with pytest.raises(ValueError, match="file may be corrupted"):
                PDFExtractor("corrupted.pdf")

    def test_invalid_file_type_raises_error(self):
        """Test that opening a non-PDF file raises ValueError."""
        with patch('fitz.open', side_effect=Exception("Not a PDF")):
            with pytest.raises(ValueError, match="Failed to open PDF"):
                PDFExtractor("not_a_pdf.txt")

    @patch('fitz.open')
    def test_context_manager_closes_document(self, mock_fitz_open):
        """Test that context manager properly closes the document."""
        mock_doc = MagicMock()
        mock_fitz_open.return_value = mock_doc

        with PDFExtractor("test.pdf") as extractor:
            pass

        mock_doc.close.assert_called_once()

    @patch('fitz.open')
    def test_extract_text_blocks_error_handling(self, mock_fitz_open):
        """Test that extract_text_blocks handles errors gracefully."""
        mock_doc = MagicMock()
        mock_doc.__len__.return_value = 1
        mock_doc.__getitem__.side_effect = Exception("Page error")
        mock_fitz_open.return_value = mock_doc

        extractor = PDFExtractor("test.pdf")

        with pytest.raises(RuntimeError, match="Failed to extract text blocks"):
            extractor.extract_text_blocks()

    @patch('fitz.open')
    def test_extract_metadata_error_handling(self, mock_fitz_open):
        """Test that extract_metadata handles errors gracefully."""
        mock_doc = MagicMock()
        mock_doc.metadata = property(Mock(side_effect=Exception("Metadata error")))
        mock_fitz_open.return_value = mock_doc

        extractor = PDFExtractor("test.pdf")

        with pytest.raises(RuntimeError, match="Failed to extract PDF metadata"):
            extractor.extract_metadata()

    @patch('fitz.open')
    def test_extract_raw_text_error_handling(self, mock_fitz_open):
        """Test that extract_raw_text handles errors gracefully."""
        mock_doc = MagicMock()
        mock_doc.__len__.return_value = 1
        mock_doc.__getitem__.side_effect = Exception("Text error")
        mock_fitz_open.return_value = mock_doc

        extractor = PDFExtractor("test.pdf")

        with pytest.raises(RuntimeError, match="Failed to extract raw text"):
            extractor.extract_raw_text()

    @patch('fitz.open')
    def test_get_page_count(self, mock_fitz_open):
        """Test that get_page_count returns correct page count."""
        mock_doc = MagicMock()
        mock_doc.__len__.return_value = 5
        mock_fitz_open.return_value = mock_doc

        extractor = PDFExtractor("test.pdf")

        assert extractor.get_page_count() == 5

    @patch('fitz.open')
    def test_font_flag_interpretation(self, mock_fitz_open):
        """Test that font flags are correctly interpreted (bold/italic)."""
        mock_doc = MagicMock()
        mock_page = MagicMock()
        mock_doc.__len__.return_value = 1
        mock_doc.__getitem__.return_value = mock_page

        # Create mock text data with specific font flags
        mock_page.get_text.return_value = {
            "blocks": [
                {
                    "type": 0,
                    "lines": [
                        {
                            "spans": [
                                {
                                    "text": "Bold text",
                                    "size": 12.0,
                                    "font": "Times-Bold",
                                    "flags": 16,  # Bit 4 set (bold)
                                    "bbox": (0, 0, 100, 12)
                                },
                                {
                                    "text": "Italic text",
                                    "size": 12.0,
                                    "font": "Times-Italic",
                                    "flags": 2,  # Bit 1 set (italic)
                                    "bbox": (0, 12, 100, 24)
                                },
                                {
                                    "text": "Bold and italic",
                                    "size": 12.0,
                                    "font": "Times-BoldItalic",
                                    "flags": 18,  # Bits 1 and 4 set
                                    "bbox": (0, 24, 100, 36)
                                }
                            ]
                        }
                    ]
                }
            ]
        }
        mock_fitz_open.return_value = mock_doc

        extractor = PDFExtractor("test.pdf")
        blocks = extractor.extract_text_blocks()

        assert len(blocks) == 3
        assert blocks[0].is_bold is True
        assert blocks[0].is_italic is False
        assert blocks[1].is_bold is False
        assert blocks[1].is_italic is True
        assert blocks[2].is_bold is True
        assert blocks[2].is_italic is True

    @patch('fitz.open')
    def test_empty_pdf_extraction(self, mock_fitz_open):
        """Test extraction from an empty PDF."""
        mock_doc = MagicMock()
        mock_page = MagicMock()
        mock_doc.__len__.return_value = 1
        mock_doc.__getitem__.return_value = mock_page
        mock_page.get_text.return_value = {"blocks": []}
        mock_fitz_open.return_value = mock_doc

        extractor = PDFExtractor("test.pdf")
        blocks = extractor.extract_text_blocks()

        assert len(blocks) == 0


class TestSectionSegmenter:
    """Test SectionSegmenter class."""

    def test_invalid_blocks_type_raises_error(self):
        """Test that invalid blocks type raises TypeError."""
        segmenter = SectionSegmenter()

        with pytest.raises(TypeError, match="blocks must be a list"):
            segmenter.segment_document("not a list", {})

    def test_invalid_metadata_type_raises_error(self):
        """Test that invalid metadata type raises TypeError."""
        segmenter = SectionSegmenter()

        with pytest.raises(TypeError, match="metadata must be a dict"):
            segmenter.segment_document([], "not a dict")

    def test_invalid_block_objects_raise_error(self):
        """Test that non-TextBlock objects in blocks raise ValueError."""
        segmenter = SectionSegmenter()

        with pytest.raises(ValueError, match="must be a TextBlock instance"):
            segmenter.segment_document([{"text": "invalid"}], {})

    def test_empty_blocks_list(self):
        """Test segmentation with empty blocks list."""
        segmenter = SectionSegmenter()
        document = segmenter.segment_document([], {"file_path": "test.pdf"})

        assert len(document.sections) == 1
        assert document.sections[0].section_type == SectionType.UNKNOWN

    def test_font_size_calculation_with_empty_blocks(self):
        """Test font size calculation with empty blocks returns default."""
        segmenter = SectionSegmenter()
        avg_size = segmenter._calculate_avg_font_size([])

        assert avg_size == 12.0

    def test_font_size_calculation_with_zero_sizes(self):
        """Test font size calculation filters out zero font sizes."""
        segmenter = SectionSegmenter()

        # Create blocks with zero font sizes
        blocks = [
            TextBlock("text1", 0, 0.0, "Times", False, False, 0, 0, 100, 12),
            TextBlock("text2", 0, 0.0, "Times", False, False, 0, 0, 100, 12),
            TextBlock("text3", 0, 0.0, "Times", False, False, 0, 0, 100, 12),
        ]

        avg_size = segmenter._calculate_avg_font_size(blocks)

        # Should return default since all sizes are zero
        assert avg_size == 12.0

    def test_font_size_calculation_median_even_count(self):
        """Test median calculation with even number of blocks."""
        segmenter = SectionSegmenter()

        blocks = [
            TextBlock("text1", 0, 10.0, "Times", False, False, 0, 0, 100, 12),
            TextBlock("text2", 0, 12.0, "Times", False, False, 0, 0, 100, 12),
            TextBlock("text3", 0, 12.0, "Times", False, False, 0, 0, 100, 12),
            TextBlock("text4", 0, 14.0, "Times", False, False, 0, 0, 100, 12),
        ]

        avg_size = segmenter._calculate_avg_font_size(blocks)

        # Median of [10, 12, 12, 14] = (12 + 12) / 2 = 12.0
        assert avg_size == 12.0

    def test_font_size_calculation_median_odd_count(self):
        """Test median calculation with odd number of blocks."""
        segmenter = SectionSegmenter()

        blocks = [
            TextBlock("text1", 0, 10.0, "Times", False, False, 0, 0, 100, 12),
            TextBlock("text2", 0, 12.0, "Times", False, False, 0, 0, 100, 12),
            TextBlock("text3", 0, 14.0, "Times", False, False, 0, 0, 100, 12),
        ]

        avg_size = segmenter._calculate_avg_font_size(blocks)

        # Median of [10, 12, 14] = 12.0
        assert avg_size == 12.0

    def test_section_type_matching_abstract(self):
        """Test section type matching for abstract."""
        segmenter = SectionSegmenter()

        section_type, confidence = segmenter._match_section_type("Abstract")
        assert section_type == SectionType.ABSTRACT
        assert confidence == 1.0

    def test_section_type_matching_introduction(self):
        """Test section type matching for introduction."""
        segmenter = SectionSegmenter()

        section_type, confidence = segmenter._match_section_type("1. Introduction")
        assert section_type == SectionType.INTRODUCTION
        assert confidence == 1.0

    def test_section_type_matching_methods(self):
        """Test section type matching for methods with variations."""
        segmenter = SectionSegmenter()

        # Test various method section names
        for title in ["Methods", "Methodology", "Materials and Methods", "Experimental Procedures"]:
            section_type, confidence = segmenter._match_section_type(title)
            assert section_type == SectionType.METHODS
            assert confidence == 1.0

    def test_section_type_matching_results(self):
        """Test section type matching for results."""
        segmenter = SectionSegmenter()

        section_type, confidence = segmenter._match_section_type("3. Results")
        assert section_type == SectionType.RESULTS
        assert confidence == 1.0

    def test_section_type_matching_discussion(self):
        """Test section type matching for discussion."""
        segmenter = SectionSegmenter()

        section_type, confidence = segmenter._match_section_type("Discussion")
        assert section_type == SectionType.DISCUSSION
        assert confidence == 1.0

    def test_section_type_matching_conclusion(self):
        """Test section type matching for conclusion."""
        segmenter = SectionSegmenter()

        section_type, confidence = segmenter._match_section_type("Conclusions")
        assert section_type == SectionType.CONCLUSION
        assert confidence == 1.0

    def test_section_type_matching_references(self):
        """Test section type matching for references."""
        segmenter = SectionSegmenter()

        section_type, confidence = segmenter._match_section_type("References")
        assert section_type == SectionType.REFERENCES
        assert confidence == 1.0

    def test_section_type_matching_unknown(self):
        """Test section type matching for unknown sections."""
        segmenter = SectionSegmenter()

        section_type, confidence = segmenter._match_section_type("Random Section")
        assert section_type == SectionType.UNKNOWN
        assert confidence == 0.0

    def test_section_type_matching_partial(self):
        """Test partial section type matching with lower confidence."""
        segmenter = SectionSegmenter()

        # This should match partially
        section_type, confidence = segmenter._match_section_type("intro")
        assert section_type == SectionType.INTRODUCTION
        assert confidence == 0.7

    def test_potential_header_detection_font_size(self):
        """Test header detection based on font size."""
        segmenter = SectionSegmenter()

        # Header with large font
        header_block = TextBlock("Introduction", 0, 16.0, "Times-Bold", True, False, 0, 0, 100, 16)
        assert segmenter._is_potential_header(header_block, 12.0) is True

        # Body text with normal font
        body_block = TextBlock("This is body text.", 0, 12.0, "Times", False, False, 0, 0, 100, 12)
        assert segmenter._is_potential_header(body_block, 12.0) is False

    def test_potential_header_detection_bold(self):
        """Test header detection based on bold formatting."""
        segmenter = SectionSegmenter()

        # Bold header with slightly larger font
        header_block = TextBlock("Methods", 0, 13.0, "Times-Bold", True, False, 0, 0, 100, 13)
        assert segmenter._is_potential_header(header_block, 12.0) is True

        # Not bold and not large enough
        body_block = TextBlock("Some text", 0, 12.5, "Times", False, False, 0, 0, 100, 12)
        assert segmenter._is_potential_header(body_block, 12.0) is False

    def test_potential_header_detection_length(self):
        """Test header detection rejects very long text."""
        segmenter = SectionSegmenter()

        # Very long text should not be a header
        long_text = "A" * 150
        long_block = TextBlock(long_text, 0, 16.0, "Times-Bold", True, False, 0, 0, 100, 16)
        assert segmenter._is_potential_header(long_block, 12.0) is False

    def test_potential_header_detection_alphabetic(self):
        """Test header detection requires alphabetic characters."""
        segmenter = SectionSegmenter()

        # Only numbers should not be a header
        number_block = TextBlock("123456", 0, 16.0, "Times-Bold", True, False, 0, 0, 100, 16)
        assert segmenter._is_potential_header(number_block, 12.0) is False

    def test_regex_pattern_compilation(self):
        """Test that regex patterns are pre-compiled in __init__."""
        segmenter = SectionSegmenter()

        # Check that compiled_patterns is a dict
        assert isinstance(segmenter.compiled_patterns, dict)

        # Check that each section type has compiled patterns
        for section_type in SectionType:
            if section_type in segmenter.SECTION_PATTERNS:
                assert section_type in segmenter.compiled_patterns
                assert len(segmenter.compiled_patterns[section_type]) > 0

    def test_segment_document_with_sections(self):
        """Test complete document segmentation with multiple sections."""
        segmenter = SectionSegmenter()

        # Create mock blocks for a simple document
        blocks = [
            # Title
            TextBlock("Study Title", 0, 18.0, "Times-Bold", True, False, 0, 10, 200, 18),
            # Abstract header
            TextBlock("Abstract", 0, 14.0, "Times-Bold", True, False, 0, 40, 100, 14),
            # Abstract content
            TextBlock("This is the abstract.", 0, 12.0, "Times", False, False, 0, 60, 200, 12),
            # Introduction header
            TextBlock("Introduction", 0, 14.0, "Times-Bold", True, False, 0, 90, 120, 14),
            # Introduction content
            TextBlock("This is the introduction.", 0, 12.0, "Times", False, False, 0, 110, 200, 12),
        ]

        metadata = {"file_path": "test.pdf", "title": "Study Title"}
        document = segmenter.segment_document(blocks, metadata)

        assert len(document.sections) >= 2
        assert document.title == "Study Title"

        # Check that we found abstract and introduction
        section_types = [s.section_type for s in document.sections]
        assert SectionType.ABSTRACT in section_types
        assert SectionType.INTRODUCTION in section_types

    def test_section_with_no_content(self):
        """Test that sections with only headers (no content) are handled."""
        segmenter = SectionSegmenter()

        blocks = [
            # Header only, no content before next section
            TextBlock("Abstract", 0, 14.0, "Times-Bold", True, False, 0, 40, 100, 14),
            # Next header immediately
            TextBlock("Introduction", 0, 14.0, "Times-Bold", True, False, 0, 60, 120, 14),
            # Content for introduction
            TextBlock("This is content.", 0, 12.0, "Times", False, False, 0, 80, 200, 12),
        ]

        metadata = {"file_path": "test.pdf"}
        document = segmenter.segment_document(blocks, metadata)

        # Abstract section should be skipped since it has no content
        # Only introduction should be present
        assert len(document.sections) == 1
        assert document.sections[0].section_type == SectionType.INTRODUCTION


class TestDataModels:
    """Test data models (TextBlock, Section, Document)."""

    def test_textblock_creation(self):
        """Test TextBlock creation and attributes."""
        block = TextBlock(
            text="Sample text",
            page_num=0,
            font_size=12.0,
            font_name="Times",
            is_bold=True,
            is_italic=False,
            x=10.0,
            y=20.0,
            width=100.0,
            height=12.0
        )

        assert block.text == "Sample text"
        assert block.page_num == 0
        assert block.font_size == 12.0
        assert block.is_bold is True
        assert block.is_italic is False

    def test_section_creation(self):
        """Test Section creation and attributes."""
        section = Section(
            section_type=SectionType.ABSTRACT,
            title="Abstract",
            content="This is the abstract content.",
            page_start=0,
            page_end=0,
            confidence=1.0
        )

        assert section.section_type == SectionType.ABSTRACT
        assert section.title == "Abstract"
        assert section.confidence == 1.0

    def test_document_creation(self):
        """Test Document creation and attributes."""
        sections = [
            Section(SectionType.ABSTRACT, "Abstract", "Content", 0, 0, 1.0)
        ]

        document = Document(
            file_path="test.pdf",
            title="Test Document",
            sections=sections,
            metadata={"author": "Test Author"}
        )

        assert document.title == "Test Document"
        assert len(document.sections) == 1
        assert document.metadata["author"] == "Test Author"

    def test_document_to_markdown(self):
        """Test Document to_markdown conversion."""
        sections = [
            Section(SectionType.ABSTRACT, "Abstract", "This is abstract.", 0, 0, 1.0),
            Section(SectionType.INTRODUCTION, "Introduction", "This is intro.", 0, 1, 1.0)
        ]

        document = Document(
            file_path="test.pdf",
            title="Test Document",
            sections=sections,
            metadata={"author": "Test Author"}
        )

        markdown = document.to_markdown()

        assert "# Test Document" in markdown
        assert "## Abstract" in markdown
        assert "## Introduction" in markdown
        assert "This is abstract." in markdown
        assert "This is intro." in markdown


class TestEdgeCases:
    """Test edge cases and error recovery."""

    @patch('fitz.open')
    def test_pdf_with_no_text(self, mock_fitz_open):
        """Test handling of PDF with no extractable text."""
        mock_doc = MagicMock()
        mock_page = MagicMock()
        mock_doc.__len__.return_value = 1
        mock_doc.__getitem__.return_value = mock_page
        mock_page.get_text.return_value = {"blocks": []}
        mock_fitz_open.return_value = mock_doc

        extractor = PDFExtractor("test.pdf")
        blocks = extractor.extract_text_blocks()

        assert blocks == []

    @patch('fitz.open')
    def test_pdf_with_only_images(self, mock_fitz_open):
        """Test handling of PDF with only image blocks."""
        mock_doc = MagicMock()
        mock_page = MagicMock()
        mock_doc.__len__.return_value = 1
        mock_doc.__getitem__.return_value = mock_page
        mock_page.get_text.return_value = {
            "blocks": [
                {"type": 1}  # Image block (type != 0)
            ]
        }
        mock_fitz_open.return_value = mock_doc

        extractor = PDFExtractor("test.pdf")
        blocks = extractor.extract_text_blocks()

        assert blocks == []

    def test_segmenter_with_mixed_font_sizes(self):
        """Test segmenter with blocks having varied font sizes."""
        segmenter = SectionSegmenter()

        blocks = [
            TextBlock("Title", 0, 20.0, "Times-Bold", True, False, 0, 0, 100, 20),
            TextBlock("Body 1", 0, 10.0, "Times", False, False, 0, 30, 100, 10),
            TextBlock("Body 2", 0, 12.0, "Times", False, False, 0, 50, 100, 12),
            TextBlock("Body 3", 0, 11.0, "Times", False, False, 0, 70, 100, 11),
        ]

        avg_size = segmenter._calculate_avg_font_size(blocks)

        # Median of [10, 11, 12, 20] = (11 + 12) / 2 = 11.5
        assert avg_size == 11.5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
